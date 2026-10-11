import asyncio
import unittest
from unittest.mock import patch
from coursebook_agent.models import Course, CourseBook, LectureDraft, ChapterSection, JobState
from coursebook_agent.renderer.markdown import render_coursebook
from coursebook_agent.renderer.presentation import reader_text
import importlib
app = importlib.import_module('coursebook_agent.app')


class BookPresentationTests(unittest.TestCase):
    def test_unclear_claim_is_omitted_without_changing_clear_math(self):
        self.assertEqual(reader_text('概率为 $0.5$。数值为 0.9[待核]。事件互斥。'), '概率为 $0.5$。事件互斥。')

        self.assertEqual(reader_text('定义清楚。相关数值均须以原课件核对。出自原资料的说明。结论成立。'), '定义清楚。结论成立。')

    def test_export_hides_internal_notes_and_preserves_stored_evidence(self):
        book = CourseBook(course=Course(course_id='same', name='概率论'), title='教辅', chapters=[LectureDraft(lecture_id='c1', title='事件', overview='概念说明', sections=[ChapterSection(heading='定义', content='事件是样本空间的子集。', time_links=['01:00'])], warnings=['待核查数值'], source_ranges=['rev-private'])], warnings=['待核查'], source_index=['rev-private'])
        text = render_coursebook(book)
        self.assertIn('事件是样本空间的子集', text)
        for word in ['待核', 'rev-private', '字幕', '来源', '教师备注']:
            self.assertNotIn(word, text)
        self.assertEqual(book.chapters[0].warnings, ['待核查数值'])

    def test_historical_download_renders_its_own_job_book(self):
        for title in ['第一版', '第二版']:
            book = CourseBook(course=Course(course_id='same', name='课程'), title=title)
            state = JobState(job_id=title, status='completed', step='已完成', book=book)
            with patch.object(app, '_get_job', return_value=state):
                response = asyncio.run(app.download_run_markdown(title))
            self.assertIn(title, response.body.decode())
