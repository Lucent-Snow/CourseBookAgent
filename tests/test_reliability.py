"""Offline regression tests for the multi-resource run lifecycle."""
import asyncio
import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx

from fastapi import HTTPException

from coursebook_agent.agent.quality import traceability_metrics
from coursebook_agent.config import config
from coursebook_agent.models import (
    Course,
    LectureDraft,
    ChapterSection,
    JobState,
    TimedChunk,
)

appmod = importlib.import_module("coursebook_agent.app")


def draft(i: int) -> LectureDraft:
    return LectureDraft(
        lecture_id=f"l{i}",
        title=f"章节{i}",
        overview="示例",
        sections=[ChapterSection(heading="说明", content="真实内容", source_chunk_ids=["c1"])],
    )


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        for obj, key, value in [
            (config, "data_dir", base),
            (config, "output_dir", base / "output"),
            (appmod, "JOB_DIR", base / "jobs"),
            (appmod, "jobs", {}),
            (appmod, "tasks", {}),
            (appmod, "generation_lock", asyncio.Lock()),
        ]:
            p = patch.object(obj, key, value)
            p.start()
            self.addCleanup(p.stop)

    async def test_generate_requires_snapshot_id(self):
        with self.assertRaises(HTTPException) as ctx:
            await appmod.generate(appmod.GenerateRequest())
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_run_status_404_when_missing(self):
        with self.assertRaises(HTTPException) as ctx:
            await appmod.run_status("does-not-exist")
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_cancel_running_task_can_be_resumed(self):
        state = JobState(job_id="cancel", course_id="demo", status="running", step="生成")
        appmod.jobs[state.job_id] = state
        appmod._schedule(state.job_id, asyncio.sleep(100))
        result = await appmod.cancel_run(state.job_id)
        self.assertEqual(result["status"], "interrupted")
        self.assertNotIn(state.job_id, appmod.tasks)

    async def test_cancel_rejects_when_not_running(self):
        appmod.jobs["idle"] = JobState(job_id="idle", status="completed", step="完成")
        with self.assertRaises(HTTPException) as ctx:
            await appmod.cancel_run("idle")
        self.assertEqual(ctx.exception.status_code, 409)

    async def test_restart_marks_running_interrupted_preserves_completed(self):
        for key, status in [("running", "running"), ("done", "completed")]:
            appmod._persist_job(JobState(job_id=key, course_id="demo", status=status, step="生成"))
        appmod.jobs.clear()
        appmod._load_jobs()
        self.assertEqual(appmod.jobs["running"].status, "interrupted")
        self.assertEqual(appmod.jobs["done"].status, "completed")
        self.assertEqual(appmod.jobs["running"].events[-1]["status"], "interrupted")

    async def test_retry_rejects_when_already_running(self):
        appmod.jobs["running"] = JobState(job_id="running", status="running", step="生成")
        with self.assertRaises(HTTPException) as ctx:
            await appmod.retry_run("running")
        self.assertEqual(ctx.exception.status_code, 409)

    async def test_retry_rejects_without_snapshot(self):
        appmod.jobs["no-snap"] = JobState(
            job_id="no-snap",
            status="failed",
            step="失败",
            request={"review": False},
        )
        with self.assertRaises(HTTPException) as ctx:
            await appmod.retry_run("no-snap")
        self.assertEqual(ctx.exception.status_code, 409)

    async def test_retry_reschedules_with_same_request(self):
        state = JobState(
            job_id="retry",
            status="failed",
            step="失败",
            request={
                "snapshot_id": "snap-1",
                "review": True,
                "concurrency": 3,
                "regenerate": True,
            },
        )
        appmod.jobs["retry"] = state
        with patch.object(appmod, "_run_job", AsyncMock()) as run:
            result = await appmod.retry_run(state.job_id)
            self.assertEqual(result["status"], "queued")
            # The retry schedules _run_job inside a Task; let the loop run it
            # so the AsyncMock actually gets awaited.
            await asyncio.sleep(0)
            self.assertIn(state.job_id, appmod.tasks)
            await appmod.tasks[state.job_id]
            self.assertEqual(run.await_count, 1)
            args = run.await_args.args
            request = args[1] if len(args) > 1 else run.await_args.kwargs.get("request")
            self.assertEqual(request.snapshot_id, "snap-1")
            self.assertTrue(request.review)

    async def test_double_retry_is_rejected_after_first(self):
        state = JobState(
            job_id="retry",
            status="failed",
            step="失败",
            request={"snapshot_id": "snap-1", "review": False},
        )
        appmod.jobs["retry"] = state
        with patch.object(appmod, "_run_job", AsyncMock()):
            await appmod.retry_run(state.job_id)
            self.assertEqual(appmod.jobs["retry"].status, "queued")
            with self.assertRaises(HTTPException) as ctx:
                await appmod.retry_run(state.job_id)
            self.assertEqual(ctx.exception.status_code, 409)
            await appmod.tasks[state.job_id]

    async def test_clear_cache_blocked_while_queued(self):
        appmod.jobs["queued"] = JobState(job_id="queued", status="queued", step="排队")
        with self.assertRaises(HTTPException):
            await appmod.clear_cache()

    async def test_report_roundtrip_and_confirmation(self):
        chapter = draft(1)
        chapter.quality_metrics = {"traceability": {"source_coverage": 1}}
        chapter.quality_report = {
            "accepted": False,
            "deterministic": {
                "accepted": True,
                "issues": [],
                "metrics": chapter.quality_metrics,
            },
        }
        from coursebook_agent.models import CourseBook
        state = JobState(
            job_id="report",
            course_id="demo",
            status="completed",
            step="完成",
            book=CourseBook(course=Course(course_id="demo", name="离线课程"), title="教辅", chapters=[chapter]),
        )
        appmod._persist_job(state)
        appmod._load_jobs()
        result = await appmod.run_report("report")
        self.assertEqual(result["results"][0]["deterministic"]["metrics"]["traceability"]["source_coverage"], 1)
        await appmod.confirm_run_chapter("report", 1, appmod.ConfirmRequest(note="核对通过"))
        result = await appmod.run_report("report")
        self.assertTrue(result["results"][0]["confirmation"]["confirmed"])
        self.assertFalse(result["results"][0]["accepted"])

    async def test_http_retry_and_status_contract(self):
        state = JobState(
            job_id="http",
            course_id="demo",
            status="interrupted",
            step="中断",
            request={"snapshot_id": "snap-1", "review": False, "concurrency": 3},
        )
        appmod.jobs["http"] = state
        with patch.object(appmod, "_run_job", AsyncMock()):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=appmod.app), base_url="http://test") as client:
                response = await client.post("/api/runs/http/retry")
                self.assertEqual(response.status_code, 202)
                self.assertEqual(response.json()["course_id"], "demo")
                await appmod.tasks["http"]
                response = await client.post("/api/runs/http/retry")
                self.assertEqual(response.status_code, 409)
                response = await client.get("/api/runs/http")
                self.assertEqual(response.json()["status"], "queued")
                self.assertTrue(response.json()["events"])

    async def test_cache_clear_keeps_jobs_and_runs(self):
        for sub in ["intermediate", "output", "jobs", "runs"]:
            atomic_dir = config.data_dir / sub
            atomic_dir.mkdir(parents=True, exist_ok=True)
            (atomic_dir / "fixture.json").write_text("{}", encoding="utf-8")
        result = await appmod.clear_cache()
        self.assertEqual(set(result["removed"]), {"intermediate", "output"})
        self.assertTrue((config.data_dir / "jobs" / "fixture.json").exists())
        self.assertTrue((config.data_dir / "runs" / "fixture.json").exists())

    async def test_download_md_rejects_incomplete_run(self):
        appmod.jobs["fresh"] = JobState(job_id="fresh", status="running", step="生成")
        with self.assertRaises(HTTPException) as ctx:
            await appmod.download_run_markdown("fresh")
        self.assertEqual(ctx.exception.status_code, 409)


class IntegrityTests(unittest.TestCase):
    def test_atomic_failure_keeps_previous_file(self):
        from coursebook_agent.storage import atomic_write_text
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.json"
            atomic_write_text(path, '{"old": true}')
            with patch("coursebook_agent.storage.os.replace", side_effect=OSError("disk")):
                with self.assertRaises(OSError):
                    atomic_write_text(path, '{"new": true}')
            self.assertEqual(json.loads(path.read_text()), {"old": True})
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_empty_and_cross_lecture_sources_are_not_covered(self):
        chapter = draft(1)
        wrong = TimedChunk(chunk_id="c1", lecture_id="l2", start_sec=0, end_sec=10, text="他课")
        for chunks in ([], [wrong]):
            result = traceability_metrics(chapter, chunks)
            self.assertEqual(result["source_coverage"], 0)
            self.assertEqual(result["invalid_referenced_chunks"], 1)
