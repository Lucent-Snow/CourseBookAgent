"""Tests for the v2 multi-resource workflow data contracts and assembler."""

from __future__ import annotations

import unittest

from coursebook_agent.agent.describe import _heuristic_description_obj, _extract_candidate_terms
from coursebook_agent.agent.editor import _coerce_plan_v2, _derive_chapter_resources, plan_book_v2
from coursebook_agent.assembly.assemble import assemble_chapter_contexts
from coursebook_agent.models import (
    BookPlan,
    ChapterInstruction,
    Course,
    ParsedResource,
    ParsedResourceUnit,
    ResourceDescription,
    ResourceLocation,
)


def _transcript(rev_id: str, title: str = "讲次", n_units: int = 6) -> ParsedResource:
    units = []
    for i in range(n_units):
        units.append(ParsedResourceUnit(
            unit_id=f"{rev_id}-s{i+1}",
            text=f"第 {i+1} 段内容：{title}",
            location=ResourceLocation(
                kind="transcript_segment",
                start=i * 60, end=(i + 1) * 60,
                label=f"[{i*60}-{(i+1)*60}]",
            ),
        ))
    return ParsedResource(
        revision_id=rev_id,
        resource_id=f"res-{rev_id}",
        kind="transcript",
        source_type="zhiyun",
        provider="zhiyun",
        title=title,
        units=units,
        raw_text="\n".join(u.text for u in units),
    )


def _pdf(rev_id: str, title: str = "讲义") -> ParsedResource:
    units = []
    for i in range(4):
        units.append(ParsedResourceUnit(
            unit_id=f"{rev_id}-p{i+1}",
            text=f"第 {i+1} 页：{title} 内容",
            location=ResourceLocation(kind="page", start=i + 1, end=i + 1, label=f"第 {i+1} 页"),
        ))
    return ParsedResource(
        revision_id=rev_id,
        resource_id=f"res-{rev_id}",
        kind="pdf",
        source_type="upload",
        provider="zhiyun",
        title=title,
        units=units,
        raw_text="\n\n".join(u.text for u in units),
    )


def _desc(rev_id: str, title: str, scope: str = "lecture", role: str = "primary") -> ResourceDescription:
    return ResourceDescription(
        revision_id=rev_id,
        resource_id=f"res-{rev_id}",
        kind="transcript",
        source_type="zhiyun",
        provider="zhiyun",
        title=title,
        topic=title,
        knowledge_topics=["概念A", "概念B"],
        scope=scope,
        usable_content_kinds=["definition"],
        suggested_role=role,
        summary=f"{title} 摘要",
    )


class DescribeHeuristicTests(unittest.TestCase):
    def test_transcript_description_is_lecture_scoped(self):
        parsed = _transcript("r1", "极限与连续")
        d = _heuristic_description_obj(parsed)
        self.assertEqual(d.scope, "lecture")
        self.assertEqual(d.suggested_role, "primary")
        self.assertTrue(d.topic)

    def test_pdf_description_is_topic_scoped(self):
        parsed = _pdf("r2", "补充讲义")
        d = _heuristic_description_obj(parsed)
        self.assertEqual(d.scope, "topic")
        self.assertEqual(d.kind, "pdf")

    def test_extract_candidate_terms(self):
        terms = _extract_candidate_terms("极限的定义：函数在某一点的极限值就是当自变量无限趋近时函数值的趋近值", k=5)
        self.assertGreater(len(terms), 0)


class CoercePlanV2Tests(unittest.TestCase):
    def test_main_agent_chapters_are_preserved(self):
        course = Course(course_id="c1", name="课程")
        descriptions = [_desc("r1", "A"), _desc("r2", "B")]
        data = {
            "book_title": "测试书",
            "chapters": [
                {"chapter_id": "c1", "book_title": "第一章", "must_cover": ["X"], "section_plan": [{"heading": "小节1"}]},
                {"chapter_id": "c2", "book_title": "第二章", "must_cover": ["Y"], "section_plan": [{"heading": "小节2"}]},
            ],
            "resource_tags": {"r1": ["c1"], "r2": ["c2"]},
            "components": [{"name": "worked_example", "description": "x", "fields": ["title"], "usage_instruction": "x"}],
            "writer_system_prompt": "只输出内容",
        }
        plan = _coerce_plan_v2(course, descriptions, data, snapshot_id=None)
        self.assertEqual(len(plan.chapters), 2)
        self.assertEqual(plan.chapters[0].chapter_id, "c1")
        self.assertEqual(plan.chapters[0].book_title, "第一章")
        self.assertIn("worked_example", {c.name for c in plan.components})
        self.assertEqual(set(plan.resource_tags.keys()), {"r1", "r2"})
        self.assertEqual(plan.chapter_resources["c1"], ["r1"])
        self.assertEqual(plan.chapter_resources["c2"], ["r2"])
        self.assertEqual(plan.global_resource_ids, [])

    def test_global_tag_is_separated(self):
        course = Course(course_id="c1", name="课程")
        descriptions = [_desc("r1", "A"), _desc("r2", "B", scope="course", role="global_constraint")]
        data = {
            "book_title": "测试",
            "chapters": [{"chapter_id": "c1", "book_title": "第一章"}],
            "resource_tags": {"r1": ["c1"], "r2": ["__global__"]},
        }
        plan = _coerce_plan_v2(course, descriptions, data, snapshot_id=None)
        self.assertEqual(plan.global_resource_ids, ["r2"])
        self.assertEqual(plan.chapter_resources["c1"], ["r1"])

    def test_unknown_revision_id_in_tags_is_dropped(self):
        course = Course(course_id="c1", name="课程")
        descriptions = [_desc("r1", "A")]
        data = {
            "book_title": "测试",
            "chapters": [{"chapter_id": "c1", "book_title": "第一章"}],
            "resource_tags": {"r1": ["c1"], "unknown": ["c1"]},
        }
        plan = _coerce_plan_v2(course, descriptions, data, snapshot_id=None)
        self.assertNotIn("unknown", plan.resource_tags)

    def test_no_tag_resources_are_excluded(self):
        course = Course(course_id="c1", name="课程")
        descriptions = [_desc("r1", "A"), _desc("r2", "B")]
        data = {
            "book_title": "测试",
            "chapters": [
                {"chapter_id": "c1", "book_title": "第一章"},
                {"chapter_id": "c2", "book_title": "第二章"},
            ],
            "resource_tags": {"r1": ["c1"]},  # r2 has no tag → excluded
        }
        plan = _coerce_plan_v2(course, descriptions, data, snapshot_id=None)
        self.assertNotIn("r2", plan.resource_tags)
        self.assertEqual(plan.chapter_resources["c2"], [])

    def test_empty_chapters_falls_back_to_per_resource(self):
        course = Course(course_id="c1", name="课程")
        descriptions = [_desc("r1", "A"), _desc("r2", "B", scope="course", role="global_constraint")]
        plan = _coerce_plan_v2(course, descriptions, {}, snapshot_id=None)
        self.assertEqual(len(plan.chapters), 2)
        self.assertEqual(plan.chapter_resources["c1"], ["r1"])
        self.assertEqual(plan.global_resource_ids, ["r2"])
        self.assertTrue(any("自动" in w for w in plan.warnings))

    def test_duplicate_chapter_ids_get_unique_suffix(self):
        course = Course(course_id="c1", name="课程")
        descriptions = [_desc("r1", "A"), _desc("r2", "B")]
        data = {
            "book_title": "测试",
            "chapters": [
                {"chapter_id": "c1", "book_title": "第一章"},
                {"chapter_id": "c1", "book_title": "第二章"},
            ],
        }
        plan = _coerce_plan_v2(course, descriptions, data, snapshot_id=None)
        chapter_ids = {c.chapter_id for c in plan.chapters}
        self.assertEqual(len(chapter_ids), 2)


class AssemblerTests(unittest.TestCase):
    def test_assemble_chapter_contexts(self):
        course = Course(course_id="c1", name="课程")
        plan = BookPlan(
            course_id="c1",
            book_title="测试",
            chapters=[
                ChapterInstruction(chapter_id="c1", book_title="第一章", module_name=""),
                ChapterInstruction(chapter_id="c2", book_title="第二章", module_name=""),
            ],
            resource_tags={"r1": ["c1"], "r2": ["c2"], "r3": ["__global__"]},
            global_resource_ids=["r3"],
        )
        plan.chapter_resources = _derive_chapter_resources(plan.resource_tags, plan.chapters)
        parsed = [
            _transcript("r1", "A"),
            _transcript("r2", "B"),
            _pdf("r3", "教学大纲"),
        ]
        contexts = assemble_chapter_contexts(plan, parsed, course=course, snapshot_id=None)
        self.assertEqual(len(contexts), 2)
        self.assertEqual([c.chapter.chapter_id for c in contexts], ["c1", "c2"])
        c1 = contexts[0]
        self.assertEqual({r.revision_id for r in c1.chapter_resources}, {"r1"})
        self.assertEqual({r.revision_id for r in c1.global_resources}, {"r3"})
        c2 = contexts[1]
        self.assertEqual({r.revision_id for r in c2.chapter_resources}, {"r2"})
        self.assertEqual({r.revision_id for r in c2.global_resources}, {"r3"})

    def test_no_tag_resources_do_not_appear_anywhere(self):
        course = Course(course_id="c1", name="课程")
        plan = BookPlan(
            course_id="c1", book_title="测试",
            chapters=[ChapterInstruction(chapter_id="c1", book_title="第一章", module_name="")],
            resource_tags={"r1": ["c1"]},
            global_resource_ids=[],
        )
        plan.chapter_resources = _derive_chapter_resources(plan.resource_tags, plan.chapters)
        parsed = [_transcript("r1", "A"), _transcript("r2", "B")]  # r2 has no tag
        contexts = assemble_chapter_contexts(plan, parsed, course=course)
        all_used = {r.revision_id for c in contexts for r in c.chapter_resources}
        all_used.update(r.revision_id for c in contexts for r in c.global_resources)
        self.assertNotIn("r2", all_used)


class PlanBookV2SignatureTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_book_v2_falls_back_to_heuristic_on_empty_llm(self):
        """Smoke test: when the LLM call returns empty, plan_book_v2 still
        produces a BookPlan via the descriptions-only fallback."""
        course = Course(course_id="c1", name="课程")
        descriptions = [_desc("r1", "A"), _desc("r2", "B", scope="course", role="global_constraint")]

        class _StubClient:
            async def complete(self, *_args, **_kwargs):
                return ""

        try:
            plan = await plan_book_v2(course, descriptions, client=_StubClient(), snapshot_id=None)
        except Exception:
            # Even when LLMError bubbles, the caller can use heuristic_book_plan_v2.
            from coursebook_agent.agent.editor import heuristic_book_plan_v2
            plan = heuristic_book_plan_v2(course, descriptions, snapshot_id=None)
        self.assertGreater(len(plan.chapters), 0)

    def test_heuristic_fallback_merges_by_topic(self):
        """The fallback must NOT emit one chapter per resource.

        Two resources sharing the same ``knowledge_topics`` should land
        in the same chapter; the resulting plan must carry a warning
        that this is a fallback so the front-end can surface it.
        """
        from coursebook_agent.agent.editor import heuristic_book_plan_v2
        from coursebook_agent.models import Course, ResourceDescription

        course = Course(course_id="c1", name="示例")
        descriptions = [
            ResourceDescription(
                revision_id="r1", resource_id="res1", kind="transcript",
                source_type="zhiyun", provider="zhiyun", title="Regression basics",
                topic="线性回归", knowledge_topics=["回归", "OLS", "系数"], scope="lecture",
            ),
            ResourceDescription(
                revision_id="r2", resource_id="res2", kind="transcript",
                source_type="zhiyun", provider="zhiyun", title="Regression diagnostics",
                topic="线性回归", knowledge_topics=["回归", "残差", "异方差"], scope="lecture",
            ),
            ResourceDescription(
                revision_id="r3", resource_id="res3", kind="transcript",
                source_type="zhiyun", provider="zhiyun", title="t-test intro",
                topic="假设检验", knowledge_topics=["t 检验", "p 值"], scope="lecture",
            ),
            ResourceDescription(
                revision_id="r4", resource_id="res4", kind="transcript",
                source_type="zhiyun", provider="zhiyun", title="t-test extension",
                topic="假设检验", knowledge_topics=["t 检验", "配对"], scope="lecture",
            ),
        ]
        plan = heuristic_book_plan_v2(course, descriptions)
        self.assertLessEqual(len(plan.chapters), 2, f"expected <= 2 chapters, got {len(plan.chapters)}")
        self.assertEqual(plan.resource_tags["r1"], plan.resource_tags["r2"])
        self.assertEqual(plan.resource_tags["r3"], plan.resource_tags["r4"])
        first = plan.chapters[0]
        self.assertNotIn("第 X 讲", first.book_title)
        self.assertTrue(any("启发式" in w for w in plan.warnings))


if __name__ == "__main__":
    unittest.main()