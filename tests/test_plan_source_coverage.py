import unittest
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from coursebook_agent.agent.editor import _coerce_plan_from_descriptions, ensure_plan_source_coverage
from coursebook_agent.models import Course, ResourceDescription, LectureDraft, ChapterSection
from coursebook_agent.pipeline import _can_reuse_chapter


class PlanSourceCoverageTests(unittest.TestCase):
    def descriptions(self):
        return [ResourceDescription(revision_id=f'r{i}', resource_id=f'res{i}', kind='transcript', source_type='zhiyun', provider='zhiyun', title=f'资料{i}') for i in range(1, 4)]

    def test_missing_tags_do_not_assign_source_positions_to_topic_chapters(self):
        data = {'chapters': [{'chapter_id': f'c{i}', 'book_title': f'主题{i}'} for i in range(1, 10)]}
        plan = _coerce_plan_from_descriptions(Course(course_id='test', name='课程'), self.descriptions(), data, snapshot_id='snap-test')
        self.assertEqual(plan.resource_tags, {})
        self.assertTrue(any('Tag' in w for w in plan.warnings))

    def test_explicit_section_sources_restore_missing_tags(self):
        data = {'chapters': [
            {'chapter_id': 'c1', 'book_title': '主题A', 'section_plan': [{'heading': 'A', 'source_revision_ids': ['r2', 'unknown']}]},
            {'chapter_id': 'c2', 'book_title': '主题B', 'section_plan': [{'heading': 'B', 'source_revision_ids': ['r2', 'r3']}]},
        ]}
        plan = _coerce_plan_from_descriptions(Course(course_id='test', name='课程'), self.descriptions(), data, snapshot_id='snap-test')
        self.assertEqual(plan.resource_tags, {'r2': ['c1', 'c2'], 'r3': ['c2']})
        self.assertNotIn('r1', plan.resource_tags)


class PlanRepairTests(unittest.IsolatedAsyncioTestCase):
    def make_plan(self):
        descriptions = PlanSourceCoverageTests().descriptions()
        data = {'chapters': [{'chapter_id': f'c{i}', 'book_title': f'主题{i}'} for i in range(1, 10)], 'resource_tags': {'r1': ['c1'], 'r2': ['c2'], 'r3': ['c3']}}
        return _coerce_plan_from_descriptions(Course(course_id='test', name='课程'), descriptions, data, snapshot_id='snap-test'), descriptions

    async def test_repair_preserves_nine_chapters_and_updates_all_mappings(self):
        plan, descriptions = self.make_plan()
        client = SimpleNamespace(complete=AsyncMock(return_value=json.dumps({'resource_tags': {'r2': [f'c{i}' for i in range(1, 10)], 'unknown': ['c1']}})))
        repaired = await ensure_plan_source_coverage(plan, descriptions, client=client)
        self.assertEqual(len(repaired.chapters), 9)
        self.assertEqual(repaired.chapter_resources['c9'], ['r2'])
        self.assertNotIn('unknown', repaired.resource_tags)
        self.assertTrue(repaired.warnings)
        client.complete.assert_awaited_once()

    async def test_incomplete_repair_blocks_generation(self):
        plan, descriptions = self.make_plan()
        client = SimpleNamespace(complete=AsyncMock(return_value='{"resource_tags":{"r1":["c1"]}}'))
        with self.assertRaisesRegex(ValueError, '仍未覆盖'):
            await ensure_plan_source_coverage(plan, descriptions, client=client)
        self.assertEqual(plan.chapter_resources['c2'], ['r2'])

    async def test_global_sources_cover_all_chapters_without_another_call(self):
        plan, descriptions = self.make_plan()
        plan.resource_tags = {'r1': ['__global__']}
        client = SimpleNamespace(complete=AsyncMock())
        self.assertIs(await ensure_plan_source_coverage(plan, descriptions, client=client), plan)
        client.complete.assert_not_awaited()


class ChapterCacheTests(unittest.TestCase):
    def test_empty_fallback_or_changed_sources_are_not_reused(self):
        context = SimpleNamespace(chapter=SimpleNamespace(chapter_id='c1'), chapter_resources=[SimpleNamespace(revision_id='r1')], global_resources=[])
        draft = LectureDraft(chapter_id='c1', title='章', overview='概述', used_resource_ids=['r1'], sections=[ChapterSection(heading='节', content='正文')])
        self.assertTrue(_can_reuse_chapter(draft, context))
        draft.used_resource_ids = ['r2']
        self.assertFalse(_can_reuse_chapter(draft, context))
        draft.used_resource_ids = ['r1']
        draft.warnings = ['LLM 不可用，已使用确定性回退']
        self.assertFalse(_can_reuse_chapter(draft, context))
        draft.warnings = []
        draft.sections = []
        self.assertFalse(_can_reuse_chapter(draft, context))


if __name__ == '__main__':
    unittest.main()
