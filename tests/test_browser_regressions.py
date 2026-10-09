import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coursebook_agent.agent.llm import extract_json_object
from coursebook_agent.models import ChapterSection, JobState, LectureDraft
from coursebook_agent.pipeline import _chapter_progress_summary
from coursebook_agent.product.service import ProductService
from coursebook_agent.product.projections import project_run

appmod = importlib.import_module('coursebook_agent.app')


class BrowserRegressionTests(unittest.TestCase):
    def test_valid_chinese_quotes_do_not_destroy_the_root_object(self):
        payload = {'title': '随机试验', 'sections': [{'heading': '定义', 'content': '称为“随机试验”。', 'components': [{'component_type': 'tip_box', 'data': {'body': '提示'}}]}]}
        raw = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(extract_json_object(raw), payload)
        self.assertEqual(extract_json_object(f'```json\n{raw}\n```'), payload)

    def test_trailing_comma_repair_preserves_content_quotes(self):
        self.assertEqual(extract_json_object('{"body":"称为“事件”",}'), {'body': '称为“事件”'})

    def test_deterministic_fallback_is_failed_in_progress(self):
        draft = LectureDraft(chapter_id='c1', title='章', overview='回退', sections=[ChapterSection(heading='片段', content='嗯')], warnings=['LLM 不可用，已使用确定性回退：0 小节'])
        self.assertEqual(_chapter_progress_summary(draft)['status'], 'failed')

    def test_dataset_history_reads_persisted_state_envelope(self):
        with tempfile.TemporaryDirectory() as root, patch.object(appmod.config, 'data_dir', Path(root)):
            folder = Path(root) / 'jobs'
            folder.mkdir()
            state = {'job_id': 'job1', 'dataset_id': 'ds1', 'status': 'completed', 'book': {'title': '书'}, 'request': {'snapshot_id': 'snap1'}, 'events': [{'at': '2026-10-09T10:00:00Z'}]}
            (folder / 'job1.json').write_text(json.dumps({'state': state, 'events': state['events']}))
            service = ProductService(Path(root) / 'product')
            runs = service.list_runs_by_dataset('ds1')
            self.assertEqual(len(runs), 1)
            self.assertTrue(runs[0]['artifact_available'])
            self.assertEqual(runs[0]['snapshot_id'], 'snap1')

    def test_live_model_metrics_are_attached_to_the_job(self):
        state = JobState(job_id='metrics', status='running', step='章节生成')
        metrics = appmod._new_job_metrics(state)
        appmod._attach_job_metrics(state, metrics)
        metrics.record(model='test', latency_ms=120, usage={'prompt_tokens': 10, 'completion_tokens': 5}, success=True)
        self.assertEqual(state.metrics['request_count'], 1)
        self.assertEqual(state.metrics['total_tokens'], 15)
        self.assertEqual(state.metrics['latency_ms'], 120)

    def test_model_failure_is_visible_without_changing_job_status(self):
        state = JobState(job_id='metrics', status='running', step='章节生成')
        metrics = appmod._new_job_metrics(state)
        appmod._attach_job_metrics(state, metrics)
        with patch.object(appmod, '_persist_job') as persist:
            metrics.record(model='test', latency_ms=100, usage=None, success=False, error_code='service', retryable=True)
            persist.assert_called_once_with(state)
        self.assertEqual(state.status, 'running')
        self.assertEqual(state.metrics['failed_requests'], 1)
        self.assertEqual(state.events[-1]['error_code'], 'service')

    def test_cached_fallback_is_failed_in_the_workbench(self):
        with tempfile.TemporaryDirectory() as root, patch.object(appmod.config, 'data_dir', Path(root)):
            (Path(root) / 'plans').mkdir()
            (Path(root) / 'intermediate').mkdir()
            (Path(root) / 'plans' / 'bookplan-snap-test.json').write_text(json.dumps({'chapters': [{'chapter_id': 'c1', 'book_title': '第一章'}]}))
            draft = LectureDraft(chapter_id='c1', title='第一章', overview='回退', sections=[ChapterSection(heading='片段', content='嗯')], warnings=['已使用确定性回退'])
            (Path(root) / 'intermediate' / 'chapter-snap-test-c1.json').write_text(draft.model_dump_json())
            state = JobState(job_id='cached', status='interrupted', step='中断', request={'snapshot_id': 'snap-test'}, chapters=[{'chapter_id': 'c1', 'status': 'done'}])
            run = project_run(state)
            self.assertEqual(run.agents[0].status, 'failed')
            self.assertEqual(run.stage.chapters_failed, 1)
