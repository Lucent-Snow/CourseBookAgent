import unittest

from coursebook_agent.agent.chapter import _build_context_payload
from coursebook_agent.models import ChapterContext, ChapterInstruction, ParsedResource, ParsedResourceUnit


class ChapterSourcePayloadTests(unittest.TestCase):
    def test_source_after_twenty_four_units_is_present_in_prompt(self):
        resource = ParsedResource(revision_id='r1', resource_id='res1', kind='transcript', source_type='zhiyun', provider='zhiyun', title='真实课堂', units=[ParsedResourceUnit(unit_id=f'u{i}', text=f'真实课堂第{i}段') for i in range(1, 31)])
        context = ChapterContext(chapter=ChapterInstruction(chapter_id='c1', book_title='章节', module_name=''), chapter_resources=[resource])
        payload = _build_context_payload(context)
        self.assertIn('真实课堂第30段', payload)
        self.assertEqual(payload.count('真实课堂第'), 30)
