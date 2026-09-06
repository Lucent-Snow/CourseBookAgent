"""Offline regression tests: no university login or paid model requests."""
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
from coursebook_agent.models import Course, Lecture, LectureDraft, ChapterSection, JobState, TimedChunk, TranscriptSegment, BookPlan
from coursebook_agent.pipeline import CourseBookPipeline
from coursebook_agent.storage import atomic_write_text

appmod = importlib.import_module("coursebook_agent.app")


def draft(i):
    return LectureDraft(lecture_id=f"l{i}", title=f"章节{i}", overview="示例",
                        sections=[ChapterSection(heading="说明", content="真实内容", source_chunk_ids=["c1"])])


class Source:
    def get_course(self, *args):
        return Course(course_id="demo", name="离线课程")

    def list_lectures(self, *args):
        return [Lecture(lecture_id=f"l{i}", course_id="demo", index=i, title=f"讲{i}") for i in (1, 2, 3)]


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        for obj, key, value in [(config, "data_dir", base), (config, "output_dir", base / "output"),
                                (appmod, "JOB_DIR", base / "jobs"), (appmod, "jobs", {}),
                                (appmod, "tasks", {}),
                                (appmod, "generation_lock", asyncio.Lock())]:
            p = patch.object(obj, key, value)
            p.start()
            self.addCleanup(p.stop)

    async def test_failure_retry_reuses_successful_snapshots(self):
        pipeline = CourseBookPipeline(Source())
        checkpoint = config.data_dir / "checkpoint"
        statuses = {}
        def progress(done, total, msg, chapter=None):
            if chapter:
                statuses[chapter["index"]] = chapter["status"]
        async def first(course_id, index, **kwargs):
            if index == 2:
                raise RuntimeError("simulated failure")
            return draft(index)
        with patch.object(pipeline, "generate_lecture", side_effect=first):
            book = await pipeline.generate_course("demo", use_book_plan=False, synthesize=False,
                                                  progress=progress, checkpoint_dir=checkpoint)
        self.assertEqual(statuses, {1: "done", 2: "failed", 3: "done"})
        self.assertTrue(book.warnings)
        generator = AsyncMock(return_value=draft(2))
        with patch.object(pipeline, "generate_lecture", generator):
            book = await pipeline.generate_course("demo", regenerate=True, only_indices=[2],
                use_book_plan=False, synthesize=False, checkpoint_dir=checkpoint)
        self.assertEqual(generator.await_count, 1)
        self.assertEqual(generator.await_args.args[1], 2)
        self.assertEqual([c.lecture_id for c in book.chapters], ["l1", "l2", "l3"])
        with patch.object(pipeline, "generate_lecture", AsyncMock()) as generation:
            await pipeline.generate_course("demo", only_indices=[], use_book_plan=False,
                                           synthesize=False, checkpoint_dir=checkpoint)
            generation.assert_not_awaited()

    async def test_snapshot_plan_is_reused_on_retry(self):
        pipeline = CourseBookPipeline(Source())
        checkpoint = config.data_dir / "checkpoint"
        atomic_write_text(checkpoint / "plan.json", BookPlan(course_id="demo", book_title="原计划").model_dump_json())
        with patch.object(pipeline, "ensure_book_plan", AsyncMock()) as plan:
            with patch.object(pipeline, "generate_lecture", AsyncMock(side_effect=[draft(1), draft(2), draft(3)])):
                await pipeline.generate_course("demo", regenerate=True, synthesize=False, checkpoint_dir=checkpoint)
            plan.assert_not_awaited()

    async def test_chapter_metrics_persist_without_course_profile(self):
        source = Source()
        source.get_transcript = lambda *args: [TranscriptSegment(lecture_id="l1", index=0,
            start_sec=3, end_sec=8, text="这是课堂证据")]
        pipeline = CourseBookPipeline(source)
        async def generate(lecture, chunks, **kwargs):
            result = draft(1)
            result.sections[0].source_chunk_ids = [chunks[0].chunk_id]
            return result
        with patch("coursebook_agent.pipeline.generate_chapter", side_effect=generate):
            result = await pipeline.generate_lecture("demo", 1, use_book_plan=False, review=False)
        saved = LectureDraft.model_validate_json((pipeline.intermediate_dir / "chapter-l1.json").read_text(encoding="utf-8"))
        self.assertEqual(saved.quality_metrics["traceability"]["source_coverage"], 1)
        self.assertFalse(saved.quality_report["accepted"])
        self.assertEqual(saved.transcript_links[0]["start_sec"], 3)
        self.assertIn("00:03", saved.sections[0].time_links[0])
        self.assertEqual(saved, result)

    async def test_cancel_running_task_can_be_resumed(self):
        state = JobState(job_id="cancel", course_id="demo", status="running", step="生成")
        appmod.jobs[state.job_id] = state
        appmod._schedule(state.job_id, asyncio.sleep(100))
        result = await appmod.cancel_job(state.job_id)
        self.assertEqual(result["status"], "interrupted")
        self.assertNotIn(state.job_id, appmod.tasks)

    async def test_full_job_failure_retry_flow(self):
        state = JobState(job_id="flow", course_id="demo", status="running", step="生成")
        appmod.jobs["flow"] = state
        pipeline = CourseBookPipeline(Source())
        async def generate(course_id, index, **kwargs):
            if index == 2:
                raise RuntimeError("temporary")
            return draft(index)
        from coursebook_agent.agent.synthesize import synthesize_book_fallback
        async def synth(course, chapters, **kwargs):
            return synthesize_book_fallback(course, chapters, plan=kwargs.get("plan"))
        with patch.object(appmod, "CourseBookPipeline", return_value=pipeline), patch(
                "coursebook_agent.pipeline.synthesize_book", side_effect=synth), patch.object(
                pipeline, "ensure_book_plan", AsyncMock(return_value=BookPlan(course_id="demo", book_title="计划"))):
            with patch.object(pipeline, "generate_lecture", side_effect=generate):
                await appmod._generate_locked(state, appmod.GenerateRequest(course_id="demo"))
            self.assertEqual(state.status, "partial")
            with patch.object(pipeline, "generate_lecture", AsyncMock(return_value=draft(2))) as gen:
                await appmod._run_retry_job("flow", "demo", [2])
                self.assertEqual(gen.await_count, 1)
            self.assertEqual(state.status, "completed")
            self.assertTrue(all(c["status"] == "done" for c in state.chapters))

    async def test_missing_snapshot_fails_instead_of_silent_incomplete_book(self):
        pipeline = CourseBookPipeline(Source())
        with self.assertRaisesRegex(ValueError, "缓存缺失"):
            await pipeline.generate_course("demo", only_indices=[], use_book_plan=False,
                                           synthesize=False)

    async def test_restart_marks_running_interrupted_preserves_completed(self):
        for key, status in [("running", "running"), ("done", "completed")]:
            appmod._persist_job(JobState(job_id=key, course_id="demo", status=status, step="生成"))
        appmod.jobs.clear()
        appmod._load_jobs()
        self.assertEqual(appmod.jobs["running"].status, "interrupted")
        self.assertEqual(appmod.jobs["done"].status, "completed")
        self.assertEqual(appmod.jobs["running"].events[-1]["status"], "interrupted")

    async def test_retry_rejects_duplicate_and_missing_course(self):
        appmod.jobs["done"] = JobState(job_id="done", status="completed", step="完成")
        with self.assertRaises(HTTPException) as ctx:
            await appmod.retry_failed_job("done")
        self.assertEqual(ctx.exception.status_code, 409)
        appmod.jobs["bad"] = JobState(job_id="bad", status="failed", step="失败")
        with self.assertRaises(HTTPException):
            await appmod.retry_failed_job("bad")

    async def test_interrupted_job_can_retry_before_any_chapter_exists(self):
        state = JobState(job_id="retry", course_id="demo", status="interrupted", step="中断")
        appmod.jobs[state.job_id] = state
        with patch.object(appmod, "_run_retry_job", AsyncMock()):
            result = await appmod.retry_failed_job(state.job_id)
            self.assertEqual(result["status"], "queued")
            with self.assertRaises(HTTPException):
                await appmod.retry_failed_job(state.job_id)
            await asyncio.sleep(0)

    async def test_clear_cache_blocked_while_queued(self):
        appmod.jobs["queued"] = JobState(job_id="queued", status="queued", step="排队")
        with self.assertRaises(HTTPException):
            await appmod.clear_cache()

    async def test_report_roundtrip_and_confirmation(self):
        chapter = draft(1)
        chapter.quality_metrics = {"traceability": {"source_coverage": 1}}
        chapter.quality_report = {"accepted": False, "deterministic": {
            "accepted": True, "issues": [], "metrics": chapter.quality_metrics}}
        from coursebook_agent.models import CourseBook
        state = JobState(job_id="report", course_id="demo", status="completed", step="完成",
                         book=CourseBook(course=Source().get_course(), title="教辅", chapters=[chapter]))
        appmod._persist_job(state)
        appmod._load_jobs()
        result = await appmod.v2_run_report("report")
        self.assertEqual(result["results"][0]["deterministic"]["metrics"]["traceability"]["source_coverage"], 1)
        await appmod.confirm_run_chapter("report", 1, appmod.ConfirmRequest(note="核对通过"))
        result = await appmod.v2_run_report("report")
        self.assertTrue(result["results"][0]["confirmation"]["confirmed"])
        self.assertFalse(result["results"][0]["accepted"])

    async def test_http_retry_and_status_contract(self):
        state = JobState(job_id="http", course_id="demo", status="interrupted", step="中断")
        appmod.jobs["http"] = state
        with patch.object(appmod, "_run_retry_job", AsyncMock()):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=appmod.app), base_url="http://test") as client:
                response = await client.post("/api/jobs/http/retry")
                self.assertEqual(response.status_code, 202)
                self.assertEqual(response.json()["course_id"], "demo")
                response = await client.post("/api/jobs/http/retry")
                self.assertEqual(response.status_code, 409)
                response = await client.get("/api/jobs/http")
                self.assertEqual(response.json()["status"], "queued")
                self.assertTrue(response.json()["events"])
            await asyncio.sleep(0)

    async def test_source_endpoint_serves_saved_evidence(self):
        appmod.jobs["source"] = JobState(job_id="source", course_id="demo", status="completed", step="完成")
        path = appmod.JOB_DIR / "source"
        atomic_write_text(path / "lectures.json", json.dumps([{"lecture_id": "l1"}]))
        atomic_write_text(path / "chunks-l1.json", json.dumps([
            {"chunk_id": "c1", "lecture_id": "l1", "start_sec": 3, "end_sec": 8, "text": "证据"}
        ], ensure_ascii=False))
        response = await appmod.chapter_source("source", 1, "c1")
        self.assertEqual(response["text"], "证据")
        with self.assertRaises(HTTPException):
            await appmod.chapter_source("source", 1, "missing")

    async def test_cache_clear_keeps_reports_and_checkpoints(self):
        for sub in ["intermediate", "output", "jobs", "runs"]:
            atomic_write_text(config.data_dir / sub / "fixture.json", "{}")
        result = await appmod.clear_cache()
        self.assertEqual(set(result["removed"]), {"intermediate", "output"})
        self.assertTrue((config.data_dir / "jobs" / "fixture.json").exists())
        self.assertTrue((config.data_dir / "runs" / "fixture.json").exists())

    async def test_manifest_change_prevents_cross_run_mixing(self):
        pipeline = CourseBookPipeline(Source())
        path = config.data_dir / "checkpoint"
        atomic_write_text(path / "lectures.json", json.dumps([{"lecture_id": "other"}]))
        with self.assertRaisesRegex(ValueError, "讲次已变化"):
            await pipeline.generate_course("demo", only_indices=[], use_book_plan=False,
                                           checkpoint_dir=path, synthesize=False)


class IntegrityTests(unittest.TestCase):
    def test_atomic_failure_keeps_previous_file(self):
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
