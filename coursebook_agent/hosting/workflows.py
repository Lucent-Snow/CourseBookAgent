"""Vercel durable orchestration around the existing pipeline and HTTP Jobs."""
from vercel import workflow

wf = workflow.Workflows(sandbox_policy=workflow.SandboxPolicy(share_sandboxes=True))


@wf.step(max_retries=2)
async def advance(owner: str, job_id: str, attempt: int) -> bool:
    import asyncio
    import tempfile
    from pathlib import Path
    from coursebook_agent.hosting.blob_store import BlobWorkspace, PrivateBlobStore
    from coursebook_agent.hosting.replay import ModelReplay, StepPending, StepBudgetExceeded, execution_context
    from coursebook_agent.hosting.workspaces import workspace_scope
    from coursebook_agent.app import GenerateRequest, _generate_locked, _get_job, _persist_job
    with tempfile.TemporaryDirectory(prefix='coursebook-step-') as directory:
        store = PrivateBlobStore()
        workspace = BlobWorkspace(store, owner, Path(directory))
        try:
            await asyncio.to_thread(workspace.checkout)
            with workspace_scope(owner, Path(directory)):
                state = _get_job(job_id)
                if state.status not in ('queued', 'running') or state.retry_count != attempt:
                    return True
                state.status, state.step = 'running', '生成中'
                _persist_job(state)
                await asyncio.to_thread(workspace.flush)
                replay = ModelReplay(Path(directory) / 'replay' / job_id, concurrency=state.request.get('concurrency', 3))
                token = execution_context.set(replay)
                initial_tasks = set(asyncio.all_tasks())
                try:
                    await asyncio.wait_for(_generate_locked(state, GenerateRequest(**state.request)), timeout=250)
                except StepPending:
                    state.message = '已存档本步结果，继续生成'
                    _persist_job(state)
                except (StepBudgetExceeded, asyncio.TimeoutError):
                    state.status, state.error_code = 'failed', 'cloud_step_timeout'
                    state.error = '本次模型调用超过免费平台单步时限，请恢复任务或换用更快的模型'
                    state.message = '已保留完成的步骤，可继续恢复'
                    _persist_job(state)
                finally:
                    execution_context.reset(token)
                    # Pipeline's gather/as_completed may leave sibling chapters pending.
                    remaining = set(asyncio.all_tasks()) - initial_tasks
                    for task in remaining:
                        task.cancel()
                    if remaining:
                        await asyncio.gather(*remaining, return_exceptions=True)
                await asyncio.to_thread(workspace.flush)
                return state.status not in ('queued', 'running')
        finally:
            store.close()


@wf.workflow
async def generate_book(owner: str, job_id: str, attempt: int):
    while not await advance(owner, job_id, attempt):
        pass
    return {'job_id': job_id}


async def launch(job_id: str, attempt: int):
    import asyncio
    import json
    from coursebook_agent.config import config
    from coursebook_agent.hosting.workspaces import owner_context, request_workspace
    from coursebook_agent.storage import atomic_write_text
    workspace = request_workspace.get()
    # Persist the input and queued Job before the first step can start.
    await asyncio.to_thread(workspace.flush)
    run = await workflow.start(generate_book, owner_context.get(), job_id, attempt)
    atomic_write_text(config.data_dir / 'workflow-runs' / f'{job_id}.json', json.dumps({'run_id': run.run_id}))
    return run.run_id


async def terminate(job_id: str):
    import json
    from coursebook_agent.config import config
    path = config.data_dir / 'workflow-runs' / f'{job_id}.json'
    if path.exists():
        run_id = json.loads(path.read_text())['run_id']
        await workflow.Run(run_id).terminate(reason='Guest requested stop')


async def reconcile(state):
    """Reflect orchestration failures so a Job cannot remain queued forever."""
    import asyncio
    import json
    from coursebook_agent.config import config
    from coursebook_agent.app import _persist_job
    if state.status not in ('queued', 'running'):
        return state
    path = config.data_dir / 'workflow-runs' / f'{state.job_id}.json'
    if not path.exists():
        return state
    try:
        status = await asyncio.wait_for(workflow.Run(json.loads(path.read_text())['run_id']).status(), 8)
    except Exception:
        # A temporarily unavailable control plane does not imply task failure.
        return state
    if status in ('failed', 'cancelled', 'completed'):
        state.status = 'interrupted' if status == 'cancelled' else 'failed'
        state.step = '中断' if status == 'cancelled' else '失败'
        state.error_code = 'cloud_workflow_' + status
        state.error = '云端执行已结束，但教辅尚未完成'
        state.message = '已保留完成的步骤，可恢复任务'
        _persist_job(state)
    return state
