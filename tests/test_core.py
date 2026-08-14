import unittest

from coursebook_agent.agent.chapter import _apply_statistical_guardrails, _collect_ranges
from coursebook_agent.agent.llm import extract_json_object
from coursebook_agent.models import (
    ChapterComponent,
    ChapterSection,
    Course,
    KnowledgePoint,
    Lecture,
    LectureDigest,
    LectureDraft,
    TimedChunk,
    TranscriptSegment,
)
from coursebook_agent.preprocess.transcript import chunk_segments, clean_segments
from coursebook_agent.sources.zhiyun import ZhiyunSource
from coursebook_agent.renderer.markdown import render_chapter, render_coursebook, _render_component
from coursebook_agent.agent.synthesize import synthesize_book_fallback
from coursebook_agent.agent.quality import (
    CourseProfile,
    TermEntry,
    deterministic_quality_gate,
    enforce_component_contract,
    normalize_chunks,
    sanitize_examples,
)


class TranscriptTests(unittest.TestCase):
    def test_filters_fillers_and_preserves_times(self):
        segments = [
            TranscriptSegment(lecture_id="l1", index=0, start_sec=0, end_sec=1, text="嗯"),
            TranscriptSegment(lecture_id="l1", index=1, start_sec=2, end_sec=5, text="假设检验用于统计推断。"),
            TranscriptSegment(lecture_id="l1", index=2, start_sec=6, end_sec=8, text="假设检验用于统计推断。"),
        ]
        cleaned = clean_segments(segments)
        self.assertEqual(len(cleaned), 1)
        chunks = chunk_segments(cleaned)
        self.assertEqual(chunks[0].start_sec, 2)
        self.assertEqual(chunks[0].end_sec, 5)

    def test_splits_on_large_gap(self):
        segments = [
            TranscriptSegment(lecture_id="l1", index=0, start_sec=0, end_sec=5, text="第一部分。"),
            TranscriptSegment(lecture_id="l1", index=1, start_sec=40, end_sec=45, text="第二部分。"),
        ]
        self.assertEqual(len(chunk_segments(segments)), 2)


class GenerationSafetyTests(unittest.TestCase):
    def test_extracts_fenced_json(self):
        self.assertEqual(extract_json_object('```json\n{"ok": true}\n```'), {"ok": True})

    def test_guardrails_soften_claims(self):
        draft = LectureDraft(
            lecture_id="l1", title="标题", overview="不能拒绝时研究假设不成立",
            sections=[ChapterSection(
                heading="案例", content="这证明隐性歧视存在，判断标准（β）移动，样本落在α对应的临界区域之外。", source_chunk_ids=["c001"],
                components=[ChapterComponent(component_type="warning", data={"body": "接受虚无假设时结论成立"})],
            )],
            summary=["接受错误H0", "np或nq≥5"],
        )
        revised = _apply_statistical_guardrails(draft)
        self.assertIn("未获支持", revised.overview)
        self.assertIn("提供支持", revised.sections[0].content)
        self.assertNotIn("（β）", revised.sections[0].content)
        self.assertIn("临界区域内", revised.sections[0].content)
        self.assertIn("未能拒绝", revised.summary[0])
        self.assertIn("np和nq均", revised.summary[1])
        self.assertIn("未拒绝虚无假设", revised.sections[0].components[0].data["body"])

    def test_source_ranges_are_well_formed(self):
        chunks = [
            TimedChunk(chunk_id="c001", lecture_id="l1", start_sec=10, end_sec=50, text="a"),
            TimedChunk(chunk_id="c002", lecture_id="l1", start_sec=50, end_sec=90, text="b"),
        ]
        sections = [ChapterSection(heading="原理", content="正文", source_chunk_ids=["c001", "c002"])]
        self.assertEqual(_collect_ranges(sections, chunks), ["原理：字幕 00:10–01:30"])

    def test_markdown_contains_teaching_aid_sections(self):
        draft = LectureDraft(
            lecture_id="l1", title="第 1 讲：导论",
            overview="这是导读概述，用于说明本章在全书中的位置。" * 3,
            learning_goals=["能说明假设检验逻辑"],
            key_points=["反证法是核心"],
            common_mistakes=["把未拒绝H0当成证明H0"],
            bridge_from_prev="上一章建立了描述统计基础。",
            bridge_to_next="下一章将进入多组比较。",
            sections=[ChapterSection(heading="主题", content="正文" * 40, source_chunk_ids=["c001"], emphasis="key")],
            summary=["结论一", "结论二", "结论三"],
            source_ranges=["主题：字幕 00:10–01:30"],
            module_name="推断基础",
            chapter_role="core",
        )
        text = render_chapter(draft)
        for heading in ["承上", "学习目标", "本章导读", "本章重点", "易错点", "本章小结", "启下", "来源", "（重点）"]:
            self.assertIn(heading, text)


class ZhiyunSourceTests(unittest.TestCase):
    def test_reads_legacy_cached_transcript_without_external_script(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            (cache_dir / "transcript-l1.json").write_text(json.dumps({
                "ok": True, "data": {"sub_id": "l1", "segments": [
                    {"start_sec": 2, "end_sec": 5, "text": "字幕内容"}
                ]},
            }), encoding="utf-8")
            source = ZhiyunSource(cache_dir=cache_dir)
            lecture = Lecture(lecture_id="l1", course_id="c1", title="测试", index=1)
            segments = source.get_transcript(lecture)
            self.assertEqual([(x.start_sec, x.end_sec, x.text) for x in segments], [(2, 5, "字幕内容")])


class V2WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.profile = CourseProfile(
            course_id="test", subject="统计学", course_theme="测试主题", audience="学生", teaching_goal="可复习",
            canonical_terms=[TermEntry(term="随机区组设计", aliases=["随机机组设计"])],
            chapter_templates={"core": {"section_range": [2, 3], "body_chars": [20, 500], "required_components": ["procedure", "worked_example", "warning"]}},
        )

    def test_normalization_is_traceable_and_keeps_raw_chunk(self):
        raw = TimedChunk(chunk_id="c001", lecture_id="l1", start_sec=0, end_sec=10, text="随机机组设计。")
        normalized, corrections = normalize_chunks([raw], self.profile)
        self.assertEqual(raw.text, "随机机组设计。")
        self.assertEqual(normalized[0].text, "随机区组设计。")
        self.assertEqual(corrections[0].raw, "随机机组设计")

    def test_component_and_example_contract_repairs_machine_residue(self):
        draft = LectureDraft(
            lecture_id="l1", title="标题", overview="导读" * 30,
            learning_goals=["目标"], common_mistakes=["错误"],
            examples=["{'example': '例子', 'source_chunk_ids': ['c001']}"],
            sections=[
                ChapterSection(heading="一", content="正文" * 30, source_chunk_ids=["c001"], time_links=["00:00-00:10"], components=[
                    ChapterComponent(component_type="tipped_box", data={"title": "提示", "body": "内容"}),
                    ChapterComponent(component_type="procedure", data={"title": "步骤", "steps": "1. 做"}),
                    ChapterComponent(component_type="worked_example", data={"title": "例题", "problem": "题目", "conclusion": "结论"}),
                    ChapterComponent(component_type="warning", data={"title": "警告", "body": "注意"}),
                ]),
                ChapterSection(heading="二", content="正文" * 30, source_chunk_ids=["c002"], time_links=["00:10-00:20"]),
            ], summary=["小结"],
        )
        draft = sanitize_examples(enforce_component_contract(draft))
        self.assertEqual(draft.sections[0].components[0].component_type, "tip_box")
        self.assertIn("例子", draft.examples[0])
        self.assertNotIn("{'example'", draft.examples[0])
        self.assertIn("1. 做", draft.sections[0].components[1].data["body"])
        instruction = type("Instruction", (), {"chapter_role": "core"})()
        self.assertTrue(deterministic_quality_gate(draft, instruction, self.profile).accepted)

    def test_quality_gate_rejects_source_time_beyond_video(self):
        draft = LectureDraft(
            lecture_id="l1", title="标题", overview="导读" * 30,
            learning_goals=["目标"], common_mistakes=["错误"],
            sections=[
                ChapterSection(heading="一", content="正文" * 30, source_chunk_ids=["c001"], time_links=["00:00-00:10"], components=[
                    ChapterComponent(component_type="procedure", data={"body": "步骤"}),
                    ChapterComponent(component_type="worked_example", data={"body": "例题"}),
                    ChapterComponent(component_type="warning", data={"body": "警告"}),
                ]),
                ChapterSection(heading="二", content="正文" * 30, source_chunk_ids=["c001"], time_links=["00:00-00:10"]),
            ], summary=["小结"], source_ranges=["一：字幕 00:00–01:00"],
        )
        instruction = type("Instruction", (), {"chapter_role": "core"})()
        chunks = [TimedChunk(chunk_id="c001", lecture_id="l1", start_sec=0, end_sec=20, text="证据")]
        result = deterministic_quality_gate(draft, instruction, self.profile, chunks)
        self.assertFalse(result.accepted)
        self.assertIn("超出视频范围", result.issues[0])


class ComponentTests(unittest.TestCase):
    def test_worked_example_render(self):
        comp = ChapterComponent(
            component_type="worked_example",
            data={"title": "z检验", "problem": "某校40名学生...", "conclusion": "拒绝H0", "source_ref": "c005@12:30"},
        )
        text = _render_component(comp)
        self.assertIn("例题", text)
        self.assertIn("z检验", text)
        self.assertIn("c005@12:30", text)

    def test_warning_render(self):
        comp = ChapterComponent(component_type="warning", data={"title": "易错", "body": "不要把未拒绝当证明"})
        text = _render_component(comp)
        self.assertIn("⚠️", text)
        self.assertIn("未拒绝", text)

    def test_section_components_in_chapter(self):
        draft = LectureDraft(
            lecture_id="l1", title="测试章", overview="概述" * 30,
            sections=[ChapterSection(
                heading="检验步骤", content="正文" * 30,
                source_chunk_ids=["c001"],
                time_links=["05:30-12:40"],
                components=[ChapterComponent(component_type="procedure", data={"title": "F检验步骤", "body": "1. 计算SSB\n2. 计算SSW"})],
            )],
            summary=["s1", "s2", "s3"],
        )
        text = render_chapter(draft)
        self.assertIn("步骤", text)
        self.assertIn("字幕时间段", text)


class BookWorkflowTests(unittest.TestCase):
    def test_fallback_synthesis_and_render(self):
        course = Course(course_id="1", name="测试课", teacher="张三", term="2025")
        chapters = [
            LectureDraft(
                lecture_id="a", title="第 1 讲：开篇",
                overview="概述内容足够长，用于渲染测试。" * 2,
                concepts=["概念A：解释"],
                sections=[ChapterSection(heading="节", content="正文" * 50, source_chunk_ids=["c001"])],
                summary=["s1", "s2", "s3"], key_points=["重点1"],
                source_ranges=["节：字幕 00:01–00:10"], module_name="基础",
            )
        ]
        book = synthesize_book_fallback(course, chapters)
        text = render_coursebook(book)
        self.assertIn("如何使用本书", text)
        self.assertIn("要点速记", text)
        self.assertIn("全课术语表", text)

    def test_digest_model(self):
        kp = KnowledgePoint(name="α错误", description="拒真错误", category="concept", chunk_refs=["c001"], time_refs=["05:00-10:00"])
        digest = LectureDigest(
            lecture_id="l1", index=1, raw_title="假设检验",
            teacher_flow="先讲H0/H1，再讲两类错误",
            knowledge_points=[kp],
            key_examples=["z检验例题"],
            chunk_count=20, total_chars=15000,
        )
        self.assertEqual(len(digest.knowledge_points), 1)
        self.assertEqual(digest.knowledge_points[0].name, "α错误")


if __name__ == "__main__":
    unittest.main()
