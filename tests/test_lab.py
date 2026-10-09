"""Tests for the lab service: cache, force, status, clear.

These tests do NOT call any LLM. We monkey-patch the underlying
``describe_with_cache``, ``plan_book_from_descriptions``,
``generate_chapter_from_context_with_fallback`` and ``synthesize_book``
to return deterministic fixtures, so we can verify the lab
control-plane (cache, force, status) without a real model.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from coursebook_agent.config import config
from coursebook_agent.lab import LabService, StageStatus
from coursebook_agent.models import (
    BookPlan,
    ChapterContext,
    ChapterInstruction,
    ChapterSection,
    Course,
    LectureDraft,
    ResourceDescription,
)


SNAPSHOT_ID = "lab-test-snap"


def _course() -> Course:
    return Course(course_id="lab-course", name="Lab 课程")


def _resource(rev_id: str, kind: str = "transcript", provider: str = "zhiyun_course") -> MagicMock:
    """Build a ParsedResource stand-in with just the attributes the lab reads."""
    r = MagicMock()
    r.revision_id = rev_id
    r.kind = kind
    r.provider = provider
    r.title = f"doc {rev_id}"
    r.meta = {"filename": f"{rev_id}.md"}
    r.units = []
    return r


def _description(rev_id: str, topic: str = "topic") -> ResourceDescription:
    return ResourceDescription(
        revision_id=rev_id,
        resource_id=rev_id,
        kind="transcript",
        source_type="transcript",
        provider="zhiyun_course",
        title=f"doc {rev_id}",
        topic=topic,
        summary="一段总结",
        knowledge_topics=["A", "B"],
        scope="course",
        suggested_role="core",
        usable_content_kinds=["transcript"],
    )


def _chapter_instruction(idx: int, chap_id: str) -> ChapterInstruction:
    return ChapterInstruction(
        chapter_id=chap_id,
        lecture_id=f"l{idx}",
        index=idx,
        book_title=f"第 {idx} 章",
        module_name="",
        chapter_role="core",
        narrative_purpose="",
        learning_goals=["目标"],
        must_cover=["要覆盖"],
        de_emphasize=[],
        prerequisite_concepts=[],
        bridge_from_prev="",
        bridge_to_next="",
        canonical_terms=["术语"],
        common_mistakes=["易错"],
        section_plan=[],
        component_usage=[],
        depth_guidance="",
        must_verify=[],
    )


def _plan() -> BookPlan:
    return BookPlan(
        course_id="lab-course",
        chapters=[_chapter_instruction(1, "c1"), _chapter_instruction(2, "c2")],
        global_resource_ids=[],
        chapter_resources={"r1": ["c1"], "r2": ["c2"]},
        book_title="Lab Book",
    )


def _draft(chap_id: str) -> LectureDraft:
    return LectureDraft(
        chapter_id=chap_id,
        title=f"章节 {chap_id}",
        overview="本章导读。" * 20,
        sections=[ChapterSection(heading="一", content="内容" * 50, source_chunk_ids=["c1"])],
        learning_goals=["目标"],
    )


class LabServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        for obj, key, value in [
            (config, "data_dir", base),
            (config, "output_dir", base / "output"),
        ]:
            p = patch.object(obj, key, value)
            p.start()
            self.addCleanup(p.stop)

        # Snapshot → dataset lookup stub
        self.snapshot_stub = MagicMock()
        self.snapshot_stub.dataset_name = "Lab 课程"
        self.snapshot_stub.name = "Lab 课程"
        self.snapshot_stub.dataset_id = "ds-1"

        self.resources = [_resource("r1"), _resource("r2")]

        # Snapshot loader stub
        loaded = MagicMock()
        loaded.course = _course()
        loaded.resources = self.resources

        self._loaded = loaded
        self._loader_patcher = patch(
            "coursebook_agent.lab.load_snapshot",
            return_value=loaded,
        )
        self._loader_patcher.start()
        self.addCleanup(self._loader_patcher.stop)

        self._product_stub = MagicMock()
        self._product_stub.get_snapshot.return_value = self.snapshot_stub
        self._product_patcher = patch(
            "coursebook_agent.lab.ProductService",
            return_value=self._product_stub,
        )
        self._product_patcher.start()
        self.addCleanup(self._product_patcher.stop)

    def _service(self) -> LabService:
        return LabService(snapshot_id=SNAPSHOT_ID)

    async def test_status_empty_when_no_caches(self):
        s = self._service()
        status = s.status()
        for stage, st in status.items():
            self.assertEqual(st.state, "empty", f"{stage} should be empty initially")
            self.assertEqual(st.count, 0)

    async def test_describe_caches_each_resource(self):
        s = self._service()
        with patch(
            "coursebook_agent.agent.describe.describe_resource",
            AsyncMock(side_effect=lambda p, **kw: _description(p.revision_id)),
        ):
            results = await s.run_describe()
        self.assertEqual(len(results), 2)
        # Cache files now exist
        self.assertTrue((config.data_dir / "intermediate" / "descriptions" / "description-r1.json").exists())
        self.assertTrue((config.data_dir / "intermediate" / "descriptions" / "description-r2.json").exists())

    async def test_describe_skips_cache_when_no_force(self):
        s = self._service()
        call_count = 0

        async def counting(p, **kw):
            nonlocal call_count
            call_count += 1
            return _description(p.revision_id)

        with patch("coursebook_agent.agent.describe.describe_resource", AsyncMock(side_effect=counting)):
            await s.run_describe()
            await s.run_describe()  # second call should hit cache, not invoke the model
        self.assertEqual(call_count, 2, "second describe call should not invoke the model")

    async def test_describe_force_reruns_all(self):
        s = self._service()
        call_count = 0

        async def counting(p, **kw):
            nonlocal call_count
            call_count += 1
            return _description(p.revision_id)

        with patch("coursebook_agent.agent.describe.describe_resource", AsyncMock(side_effect=counting)):
            await s.run_describe()
            self.assertEqual(call_count, 2)
            s.clear_descriptions()
            await s.run_describe(force=True)
            self.assertEqual(call_count, 4)

    async def test_describe_force_only_one_revision(self):
        s = self._service()
        call_count = 0

        async def counting(p, **kw):
            nonlocal call_count
            call_count += 1
            return _description(p.revision_id)

        with patch("coursebook_agent.agent.describe.describe_resource", AsyncMock(side_effect=counting)):
            await s.run_describe()
            self.assertEqual(call_count, 2)
            await s.run_describe(force=True, revision_id="r1")
            self.assertEqual(call_count, 3, "force --revision should re-run only that one resource")

    async def test_plan_uses_descriptions_and_caches(self):
        s = self._service()
        # Seed descriptions
        for r in self.resources:
            atomic = config.data_dir / "intermediate" / "descriptions" / f"description-{r.revision_id}.json"
            atomic.parent.mkdir(parents=True, exist_ok=True)
            atomic.write_text(_description(r.revision_id).model_dump_json(), encoding="utf-8")

        with patch(
            "coursebook_agent.lab.plan_book_from_descriptions",
            AsyncMock(return_value=_plan()),
        ):
            plan = await s.run_plan()
        self.assertEqual(len(plan.chapters), 2)
        self.assertTrue(s.plan_path().exists())

    async def test_plan_without_descriptions_raises(self):
        s = self._service()
        with self.assertRaisesRegex(RuntimeError, "describe"):
            await s.run_plan()

    async def test_plan_force_clears_cache(self):
        s = self._service()
        for r in self.resources:
            atomic = config.data_dir / "intermediate" / "descriptions" / f"description-{r.revision_id}.json"
            atomic.parent.mkdir(parents=True, exist_ok=True)
            atomic.write_text(_description(r.revision_id).model_dump_json(), encoding="utf-8")
        with patch(
            "coursebook_agent.lab.plan_book_from_descriptions",
            AsyncMock(return_value=_plan()),
        ):
            await s.run_plan()
            self.assertTrue(s.plan_path().exists())
            s.clear_plan()
            self.assertFalse(s.plan_path().exists())
            await s.run_plan(force=True)
            self.assertTrue(s.plan_path().exists())

    async def test_generate_writes_per_chapter_cache(self):
        s = self._service()
        # Seed plan + descriptions
        for r in self.resources:
            atomic = config.data_dir / "intermediate" / "descriptions" / f"description-{r.revision_id}.json"
            atomic.parent.mkdir(parents=True, exist_ok=True)
            atomic.write_text(_description(r.revision_id).model_dump_json(), encoding="utf-8")
        plan = _plan()
        s.plan_path().parent.mkdir(parents=True, exist_ok=True)
        s.plan_path().write_text(plan.model_dump_json(), encoding="utf-8")

        with patch(
            "coursebook_agent.lab.generate_chapter_from_context_with_fallback",
            AsyncMock(side_effect=lambda ctx, **kw: _draft(ctx.chapter.chapter_id)),
        ):
            draft = await s.run_generate(chapter_id="c1")
        self.assertEqual(draft.chapter_id, "c1")
        cached_path = config.data_dir / "intermediate" / "chapter-lab-test-snap-c1.json"
        self.assertTrue(cached_path.exists())

    async def test_synthesize_writes_coursebook_cache(self):
        s = self._service()
        for r in self.resources:
            atomic = config.data_dir / "intermediate" / "descriptions" / f"description-{r.revision_id}.json"
            atomic.parent.mkdir(parents=True, exist_ok=True)
            atomic.write_text(_description(r.revision_id).model_dump_json(), encoding="utf-8")
        plan = _plan()
        s.plan_path().parent.mkdir(parents=True, exist_ok=True)
        s.plan_path().write_text(plan.model_dump_json(), encoding="utf-8")
        for cid in ("c1", "c2"):
            path = config.data_dir / "intermediate" / f"chapter-lab-test-snap-{cid}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_draft(cid).model_dump_json(), encoding="utf-8")

        from coursebook_agent.models import CourseBook

        book = CourseBook(course=_course(), title="Lab Book", chapters=[_draft("c1"), _draft("c2")])

        with patch("coursebook_agent.lab.synthesize_book", AsyncMock(return_value=book)):
            result = await s.run_synthesize()
        self.assertEqual(len(result.chapters), 2)
        # Course id from snapshot ends up in the path; the lab uses loaded course id.
        cached = config.data_dir / "intermediate" / "coursebook-lab-course.json"
        self.assertTrue(cached.exists())

    async def test_clear_methods_remove_files(self):
        s = self._service()
        for r in self.resources:
            atomic = config.data_dir / "intermediate" / "descriptions" / f"description-{r.revision_id}.json"
            atomic.parent.mkdir(parents=True, exist_ok=True)
            atomic.write_text(_description(r.revision_id).model_dump_json(), encoding="utf-8")
        s.plan_path().parent.mkdir(parents=True, exist_ok=True)
        s.plan_path().write_text(_plan().model_dump_json(), encoding="utf-8")

        self.assertEqual(s.clear_descriptions(), 2)
        self.assertEqual(s.clear_descriptions("r1"), 0)
        self.assertEqual(s.clear_plan(), 1)

    async def test_status_reflects_cached_stages(self):
        s = self._service()
        for r in self.resources:
            atomic = config.data_dir / "intermediate" / "descriptions" / f"description-{r.revision_id}.json"
            atomic.parent.mkdir(parents=True, exist_ok=True)
            atomic.write_text(_description(r.revision_id).model_dump_json(), encoding="utf-8")
        s.plan_path().parent.mkdir(parents=True, exist_ok=True)
        s.plan_path().write_text(_plan().model_dump_json(), encoding="utf-8")

        status = s.status()
        self.assertEqual(status["describe"].state, "cached")
        self.assertEqual(status["describe"].count, 2)
        self.assertEqual(status["plan"].state, "cached")
        self.assertEqual(status["assemble"].state, "cached")
        self.assertEqual(status["assemble"].count, 2)
        self.assertEqual(status["generate"].state, "empty")
        self.assertEqual(status["synthesize"].state, "empty")


if __name__ == "__main__":
    unittest.main()
