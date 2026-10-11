import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

import httpx

from coursebook_agent.config import config, save_llm_settings
from coursebook_agent.hosting.blob_store import BlobWorkspace, WriteConflict
from coursebook_agent.hosting.replay import ModelReplay, StepPending
from coursebook_agent.hosting.workspaces import issue_cookie, verify_cookie, workspace_scope


class MemoryStore:
    def __init__(self):
        self.entries = {}
        self.version = 0

    def get(self, key):
        return self.entries.get(key, (None, None))

    def put(self, key, content, etag=None):
        old = self.entries.get(key)
        if (etag and (not old or old[1] != etag)) or (not etag and old):
            raise WriteConflict(key)
        self.version += 1
        self.entries[key] = content, str(self.version)
        return str(self.version)


class HostingTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_guest_apis_and_settings(self):
        from coursebook_agent.app import app
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'COURSEBOOK_GUEST_MODE':'1','COURSEBOOK_SESSION_SECRET':'a'*48}), patch.object(config, 'data_dir', Path(directory)):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url='http://test') as a, httpx.AsyncClient(transport=transport, base_url='http://test') as b:
                await a.get('/api/session')
                await b.get('/api/session')
                dataset = (await a.post('/api/product/datasets', json={'name':'Private'})).json()
                response = await b.get('/api/product/datasets/'+dataset['dataset_id'])
                self.assertEqual(response.status_code, 404)
                self.assertEqual((await b.get('/api/product/datasets')).json()['data'], [])
                await a.put('/api/settings/llm', json={'base_url':'https://example.com/v1','model':'private-model','api_key':'private-key'})
                self.assertNotEqual((await b.get('/api/settings')).json()['llm']['model'], 'private-model')
                tampered = a.cookies.get('coursebook_guest')[:-1] + 'z'
                b.cookies.set('coursebook_guest', tampered)
                self.assertEqual((await b.get('/api/product/datasets')).json()['data'], [])
                self.assertEqual((await a.post('/api/product/datasets', json={'name':'CSRF'}, headers={'Origin':'https://other.example'})).status_code, 403)

    async def test_model_replay_does_not_repeat_paid_call(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            async def invoke():
                calls.append('called')
                return 'written chapter'
            first = ModelReplay(Path(directory))
            self.assertEqual(await first.complete(None,'system','one',0.2,invoke), 'written chapter')
            with self.assertRaises(StepPending):
                await first.complete(None,'system','two',0.2,invoke)
            second = ModelReplay(Path(directory))
            self.assertEqual(await second.complete(None,'system','one',0.2,invoke), 'written chapter')
            await second.complete(None,'system','two',0.2,invoke)
            self.assertEqual(len(calls), 2)

    async def test_parallel_batch_finishes_before_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            replay = ModelReplay(Path(directory), concurrency=2)
            release = asyncio.Event()
            calls = []
            async def invoke():
                calls.append(1)
                await release.wait()
                return 'saved'
            tasks = [asyncio.create_task(replay.complete(None, 's', str(i), 0.2, invoke)) for i in range(3)]
            await asyncio.sleep(0)
            self.assertEqual(len(calls), 2)
            self.assertFalse(tasks[2].done())
            release.set()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self.assertEqual(results[:2], ['saved', 'saved'])
            self.assertIsInstance(results[2], StepPending)
            self.assertEqual(len(list(Path(directory).glob('*.json'))), 2)

    async def test_failed_workflow_becomes_resumable(self):
        from coursebook_agent.models import JobState
        from coursebook_agent.hosting.workflows import reconcile
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'COURSEBOOK_GUEST_MODE':'1'}), workspace_scope('a'*48, Path(directory)):
            path = Path(directory)/'workflow-runs'/'failed.json'
            path.parent.mkdir()
            path.write_text(json.dumps({'run_id':'test-run'}))
            state = JobState(job_id='failed', status='queued', step='排队')
            with patch('coursebook_agent.hosting.workflows.workflow.Run') as run:
                run.return_value.status = AsyncMock(return_value='failed')
                self.assertEqual((await reconcile(state)).status, 'failed')
                self.assertEqual(state.error_code, 'cloud_workflow_failed')
            self.assertTrue((Path(directory)/'jobs'/'failed.json').exists())

    async def test_manifest_merge_and_same_file_conflict(self):
        store = MemoryStore()
        with tempfile.TemporaryDirectory() as directory:
            owner = 'a' * 48
            roots = [Path(directory) / str(i) for i in range(4)]
            for root in roots: root.mkdir()
            a, b = [BlobWorkspace(store, owner, root) for root in roots[:2]]
            a.checkout(); b.checkout()
            (a.root/'one').write_text('one'); a.flush()
            (b.root/'two').write_text('two'); b.flush()
            c = BlobWorkspace(store, owner, roots[2]); c.checkout()
            d = BlobWorkspace(store, owner, roots[3]); d.checkout()
            self.assertEqual((c.root/'one').read_text(), 'one')
            self.assertEqual((c.root/'two').read_text(), 'two')
            (c.root/'one').write_text('new'); c.flush()
            (d.root/'one').write_text('stale')
            with self.assertRaises(WriteConflict): d.flush()
            # A different owner cannot see any of these files.
            self.assertEqual(store.get('workspaces/'+'b'*48+'/manifest.json'), (None,None))

    async def test_cookie_signature(self):
        with patch.dict(os.environ, {'COURSEBOOK_SESSION_SECRET':'a'*48}):
            cookie = issue_cookie()
            self.assertIsNotNone(verify_cookie(cookie))
            self.assertIsNone(verify_cookie(cookie[:-1]+'z'))

    async def test_large_upload_survives_chunks_and_is_private(self):
        from coursebook_agent.app import app
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'COURSEBOOK_GUEST_MODE':'1','COURSEBOOK_SESSION_SECRET':'a'*48}), patch.object(config, 'data_dir', Path(directory)):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url='http://test') as a, httpx.AsyncClient(transport=transport, base_url='http://test') as b:
                await a.get('/api/session'); await b.get('/api/session')
                dataset = (await a.post('/api/product/datasets', json={'name':'Course'})).json()
                content = b'# Probability\n' + b'Course text\n' * 300000
                upload = (await a.post('/api/product/uploads', json={'dataset_id':dataset['dataset_id'],'filename':'notes.md','size':len(content)})).json()
                base = '/api/product/uploads/'+upload['upload_id']
                self.assertEqual((await b.put(base+'/chunks/0', content=content[:upload['chunk_size']])).status_code,404)
                self.assertEqual((await a.post(base+'/finish')).status_code,409)
                for index, offset in enumerate(range(0,len(content),upload['chunk_size'])):
                    self.assertEqual((await a.put(base+f'/chunks/{index}', content=content[offset:offset+upload['chunk_size']])).status_code,200)
                result = await a.post(base+'/finish')
                self.assertEqual(result.status_code,201)
                revision = result.json()['current_revision']
                self.assertEqual(revision['size_bytes'],len(content))
                preview = '/api/product/resource-revisions/'+revision['revision_id']+'/preview'
                self.assertEqual((await a.get(preview)).status_code,200)
                self.assertEqual((await b.get(preview)).status_code,404)
                self.assertEqual((await b.get('/api/runs/unknown-job')).status_code,404)

    async def test_manifest_requests_strong_etag_without_cdn_cache(self):
        from coursebook_agent.hosting.blob_store import PrivateBlobStore
        observed = []
        def handler(request):
            observed.append(request)
            if request.method == 'GET':
                self.assertEqual(request.headers['accept-encoding'], 'identity')
                self.assertEqual(request.url.params['cache'], '0')
                return httpx.Response(200, content=b'{}', headers={'etag':'"strong"'})
            self.assertEqual(request.headers['x-if-match'], '"strong"')
            self.assertEqual(request.headers['x-vercel-blob-access'], 'private')
            return httpx.Response(200,json={'etag':'"new"'})
        store = PrivateBlobStore('vercel_blob_rw_test_secret', transport=httpx.MockTransport(handler))
        body, etag = store.get('workspaces/manifest.json')
        store.put('workspaces/manifest.json', body, etag=etag)
        self.assertEqual(len(observed),2)
        store.close()
