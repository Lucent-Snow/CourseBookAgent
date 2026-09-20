"""FastAPI entrypoint for CourseBookAgent.

The product workbench routes live in ``coursebook_agent.product.api``. This
file owns the cross-cutting run lifecycle (``/api/generate``, ``/api/runs``)
and shared infrastructure endpoints (settings, cache, zhiyun auth,
health).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from coursebook_agent.agent.llm import LLMClient, LLMError, UsageMetrics, usage_tracking
from coursebook_agent.config import config, normalize_llm_base_url, save_llm_settings
from coursebook_agent.models import JobState, LectureDraft
from coursebook_agent.pipeline import CourseBookPipeline
from coursebook_agent.storage import atomic_write_text
from coursebook_agent.sources.zhiyun import ZhiyunError, ZhiyunSource
from coursebook_agent.product.api import router as product_router

app = FastAPI(title="CourseBookAgent", version="0.1.0")
app.include_router(product_router)
jobs: dict[str, JobState] = {}
generation_lock = asyncio.Lock()
tasks: dict[str, asyncio.Task] = {}
JOB_DIR = config.data_dir / "jobs"
JOB_DIR.mkdir(parents=True, exist_ok=True)


def _job_path(job_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
        raise HTTPException(status_code=400, detail="任务标识无效")
    return JOB_DIR / f"{job_id}.json"


def _persist_job(state: JobState) -> None:
    """Persist job state atomically so status survives an app restart."""
    path = _job_path(state.job_id)
    event = {"status": state.status, "step": state.step, "progress": state.progress,
             "message": state.message, "at": datetime.now(timezone.utc).isoformat(),
             "error_code": state.error_code, "retryable": state.status in {"failed", "partial", "interrupted"},
             "attempt": state.retry_count + 1}
    state.events.append(event)
    state.events = state.events[-200:]
    try:
        history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        history = {}
    history["state"] = json.loads(state.model_dump_json())
    history["events"] = (history.get("events") or []) + [event]
    history["events"] = history["events"][-200:]
    atomic_write_text(path, json.dumps(history, ensure_ascii=False, indent=2))


def _update_job_metrics(state: JobState, snapshot: dict) -> None:
    state.metrics = snapshot


def _record_model_event(state: JobState, event: dict) -> None:
    pass  # placeholder kept for API stability; events are persisted via _persist_job.


def _new_job_metrics(state: JobState) -> UsageMetrics:
    in_price = state.request.get("input_price_per_million")
    out_price = state.request.get("output_price_per_million")
    return UsageMetrics(
        input_price_per_million=float(in_price) if in_price not in (None, "") else None,
        output_price_per_million=float(out_price) if out_price not in (None, "") else None,
    )


def _attach_job_metrics(state: JobState, metrics: UsageMetrics) -> None:
    state.metrics = metrics.snapshot()


def _load_jobs() -> None:
    """Rehydrate persisted jobs and mark anything that was running as interrupted.

    A running job cannot survive a process restart, so flipping it to
    'interrupted' is the honest state. The operator can then retry it.
    """
    if not JOB_DIR.exists():
        return
    for path in JOB_DIR.glob("*.json"):
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
            state = JobState.model_validate(history["state"])
            if state.status == "running":
                state.status = "interrupted"
                state.step = "中断"
                state.message = "进程重启中断，可手动恢复"
                state.error_code = "process_restart"
                _persist_job(state)
            jobs[state.job_id] = state
        except (OSError, ValueError, KeyError):
            continue


_load_jobs()


# ── Index ─────────────────────────────────────────────────────────────────


@app.get("/", include_in_schema=False)
async def index() -> RedirectResponse:
    """Redirect the root URL into the React product workbench."""
    return RedirectResponse(url="/datasets", status_code=307)


# ── Generation entry ──────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    course_id: str | None = None
    snapshot_id: str | None = None
    regenerate: bool = False
    review: bool = True
    concurrency: int = Field(default=3, ge=1, le=8)
    chapter_indices: list[int] | None = None


def _schedule(job_id: str, coroutine) -> None:
    task = asyncio.create_task(coroutine)
    tasks[job_id] = task
    task.add_done_callback(lambda finished: tasks.pop(job_id, None) if tasks.get(job_id) is finished else None)


@app.post("/api/generate", status_code=202)
async def generate(request: GenerateRequest):
    if not request.snapshot_id:
        raise HTTPException(status_code=400, detail="snapshot_id 必须提供；系统不再以课程为主键。")
    # Resolve dataset_id from snapshot so the run is bound to its source
    # dataset instead of a course.
    from coursebook_agent.product.service import ProductService
    snapshot_obj = ProductService().get_snapshot(request.snapshot_id)
    job_id = uuid.uuid4().hex[:12]
    job_state = JobState(
        job_id=job_id,
        course_id=request.course_id or "",
        request=request.model_dump(),
        status="queued", step="排队", progress=0,
        message="多资料工作流准备",
    )
    # Dataset binding lives in request so projections can find it.
    job_state.request["dataset_id"] = snapshot_obj.dataset_id
    job_state.request["dataset_name"] = ProductService().get_dataset(snapshot_obj.dataset_id).name
    jobs[job_id] = job_state
    _persist_job(job_state)
    _schedule(job_id, _run_job(job_id, request))
    return job_state.model_dump()


async def _run_job(job_id: str, request: GenerateRequest) -> None:
    state = jobs[job_id]
    async with generation_lock:
        state.status, state.step, state.message = "running", "读取快照", "多资料工作流启动"
        _persist_job(state)
        await _generate_locked(state, request)


async def _generate_locked(state: JobState, request: GenerateRequest) -> None:
    # Promote dataset binding to top-level fields so projection can render it.
    state.dataset_id = state.request.get("dataset_id", state.dataset_id)
    state.dataset_name = state.request.get("dataset_name", state.dataset_name)

    def progress(done: float, total: float, message: str, chapter: dict | None = None) -> None:
        try:
            pct = int(min(done / total, 1.0) * 95)
        except ZeroDivisionError:
            pct = 0
        state.progress = pct
        head = message.strip().split(" ", 1)[0]
        state.step = head[:4] if len(head) > 4 else head
        state.message = message
        if chapter:
            cid = chapter.get("chapter_id") or chapter.get("index")
            if chapter.get("chapter_id") and "index" not in chapter:
                chapter = {**chapter, "index": chapter.get("index", len(state.chapters) + 1)}
            state.chapters = sorted(
                [c for c in state.chapters if c.get("chapter_id", c.get("index")) != cid] + [chapter],
                key=lambda c: c.get("index", 0),
            )
        _persist_job(state)

    metrics = _new_job_metrics(state)
    _attach_job_metrics(state, metrics)
    state.metrics = metrics.snapshot()
    _persist_job(state)
    try:
        pipeline = CourseBookPipeline()
        with usage_tracking(metrics):
            book = await asyncio.wait_for(pipeline.run(
                snapshot_id=request.snapshot_id,
                course_id=request.course_id,
                dataset_name=state.dataset_name,
                regenerate=request.regenerate,
                review=request.review,
                concurrency=request.concurrency,
                progress=progress,
                chapter_indices=request.chapter_indices,
            ), timeout=5400)
        if any(c.get("status") == "failed" for c in state.chapters):
            state.status, state.progress, state.step, state.message, state.book = "partial", 100, "部分完成", "部分章节生成失败，可重试失败章节", book
        else:
            state.status, state.progress, state.step, state.message, state.book = "completed", 100, "完成", "课程教辅已生成", book
        _persist_job(state)
    except asyncio.TimeoutError:
        state.error_code = "task_timeout"
        state.status, state.step, state.error, state.message = "failed", "超时", "任务超过 90 分钟", "生成超时，可恢复已完成章节"
        _persist_job(state)
    except Exception as exc:
        state.error_code = getattr(exc, "code", "generation_error")
        state.status, state.step, state.error, state.message = "failed", "失败", str(exc), "生成失败"
        _persist_job(state)
    except asyncio.CancelledError:
        state.status, state.step, state.message = "interrupted", "中断", "生成中断，可手动恢复"
        _persist_job(state)
        raise


# ── Run lifecycle ────────────────────────────────────────────────────────


def _get_job(job_id: str) -> JobState:
    if job_id not in jobs:
        path = _job_path(job_id)
        if path.exists():
            try:
                jobs[job_id] = JobState.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="任务不存在")
    return jobs[job_id]


@app.get("/api/runs/{run_id}")
async def run_status(run_id: str):
    return _get_job(run_id).model_dump()


@app.post("/api/runs/{run_id}/retry", status_code=202)
async def retry_run(run_id: str):
    state = _get_job(run_id)
    if state.status not in {"failed", "partial", "interrupted"}:
        raise HTTPException(status_code=409, detail="只有失败或部分完成的任务可以重试")
    if not state.request.get("snapshot_id"):
        raise HTTPException(status_code=409, detail="任务缺少 snapshot_id，无法重试")

    state.retry_count += 1
    state.status = "queued"
    state.step = "排队"
    state.progress = 0
    state.error = None
    state.error_code = None
    state.message = "准备恢复任务"
    _persist_job(state)
    _schedule(run_id, _run_job(run_id, GenerateRequest(**state.request)))
    return {"job_id": state.job_id, **state.model_dump()}


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    state = _get_job(run_id)
    task = tasks.get(run_id)
    if state.status not in {"queued", "running"} or not task:
        raise HTTPException(status_code=409, detail="任务未在运行")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    state.status, state.step, state.message = "interrupted", "中断", "用户停止任务，可手动恢复"
    _persist_job(state)
    return state.model_dump()


@app.get("/api/runs/{run_id}/download.md")
async def download_run_markdown(run_id: str):
    state = _get_job(run_id)
    if state.status not in {"completed", "partial"} or not state.book:
        raise HTTPException(status_code=409, detail="教辅尚未完成")
    course_id = state.book.course.course_id or run_id
    path = config.output_dir / f"coursebook-{course_id}.md"
    return FileResponse(
        path,
        media_type="text/markdown; charset=utf-8",
        filename=f"coursebook-{course_id}.md",
    )


# ── Health & zhiyun auth ──────────────────────────────────────────────────


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "llm_configured": bool(config.llm.api_key and config.llm.base_url and config.llm.model),
        "zhiyun_live_configured": config.zhiyun.has_credentials,
    }


class ZhiyunLoginRequest(BaseModel):
    username: str
    password: str
    webvpn: bool = False


@app.get("/api/zhiyun/auth")
async def zhiyun_auth_status():
    return ZhiyunSource().auth_status()


@app.post("/api/zhiyun/login")
async def zhiyun_login(request: ZhiyunLoginRequest):
    try:
        return await ZhiyunSource().login(request.username, request.password, webvpn=request.webvpn)
    except ZhiyunError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


# ── Settings ──────────────────────────────────────────────────────────────


def _dir_size(path: Path) -> int:
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    except OSError:
        pass
    return total


@app.get("/api/settings")
async def settings():
    zhiyun = ZhiyunSource().auth_status()
    intermediate = config.data_dir / "intermediate"
    course_count = len(list(intermediate.glob("coursebook-*.json"))) if intermediate.exists() else 0
    return {
        "llm": {
            "base_url": config.llm.base_url,
            "model": config.llm.model,
            "api_key_set": bool(config.llm.api_key),
            "configured": bool(config.llm.api_key and config.llm.base_url and config.llm.model),
            "input_price_per_million": config.llm.input_price_per_million,
            "output_price_per_million": config.llm.output_price_per_million,
        },
        "zhiyun": zhiyun,
        "data": {
            "cache_bytes": _dir_size(config.data_dir) if config.data_dir.exists() else 0,
            "course_count": course_count,
        },
    }


class LLMSettingsRequest(BaseModel):
    base_url: str
    model: str
    api_key: str = ""
    input_price_per_million: float | None = Field(default=None, ge=0)
    output_price_per_million: float | None = Field(default=None, ge=0)


@app.put("/api/settings/llm")
async def update_llm_settings(request: LLMSettingsRequest):
    base_url = normalize_llm_base_url(request.base_url)
    model = request.model.strip()
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="端点与模型名不能为空")
    api_key = request.api_key.strip() or config.llm.api_key
    save_llm_settings(
        base_url, model, api_key,
        request.input_price_per_million,
        request.output_price_per_million,
    )
    return {
        "ok": True,
        "configured": bool(config.llm.base_url and model and api_key),
        "api_key_set": bool(api_key),
        "base_url": config.llm.base_url,
        "input_price_per_million": config.llm.input_price_per_million,
        "output_price_per_million": config.llm.output_price_per_million,
    }


@app.post("/api/settings/llm/test")
async def test_llm_connection():
    if not (config.llm.base_url and config.llm.model and config.llm.api_key):
        raise HTTPException(status_code=400, detail="请先完成大模型配置")
    start = time.monotonic()
    metrics = UsageMetrics(
        input_price_per_million=config.llm.input_price_per_million,
        output_price_per_million=config.llm.output_price_per_million,
    )
    try:
        with usage_tracking(metrics):
            await LLMClient(max_retries=1, timeout=30).complete(
                "你是连接测试助手。", "请只回复两个字符：OK", max_tokens=8, temperature=0
            )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"连接失败：{exc}") from exc
    return {
        "ok": True,
        "model": config.llm.model,
        "latency_ms": int((time.monotonic() - start) * 1000),
        "usage": metrics.snapshot(),
    }


@app.delete("/api/cache")
async def clear_cache():
    if generation_lock.locked() or any(s.status in {"queued", "running"} for s in jobs.values()):
        raise HTTPException(status_code=409, detail="生成任务运行中，不能清除缓存")
    # 保留 data/cache（原始字幕）与 data/plans（蓝图），只清派生产物
    removed = []
    for sub in ("intermediate", "output", "experiments"):
        p = config.data_dir / sub
        if p.exists():
            shutil.rmtree(p)
            removed.append(sub)
    return {"ok": True, "removed": removed}


# ── Run reports and quality ───────────────────────────────────────────────


@app.get("/api/runs")
async def list_runs():
    runs_dir = config.data_dir / "runs"
    items = [{k: v for k, v in _job_report(s).items() if k != "results"}
             for s in reversed(list(jobs.values())) if s.book]
    for report_path in sorted(runs_dir.glob("*/report/pilot-quality-report.json"), reverse=True):
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        run_id = data.get("run_id") or report_path.parent.parent.name
        course_id = data.get("course_id") or (run_id.split("-", 1)[0] if "-" in run_id else "")
        items.append({
            "run_id": run_id,
            "course_id": course_id,
            "accepted": data.get("accepted", 0),
            "rejected": data.get("rejected", 0),
            "indices": data.get("indices", []),
        })
    return {"data": items}


@app.get("/api/runs/{run_id}/report")
async def run_report(run_id: str):
    if run_id in jobs:
        return _job_report(jobs[run_id])
    path = config.data_dir / "runs" / run_id / "report" / "pilot-quality-report.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="运行报告不存在")
    return json.loads(path.read_text(encoding="utf-8"))


def _job_report(state: JobState) -> dict:
    results = []
    chapters = state.book.chapters if state.book else []
    # A single-lecture job stores the merged book for reading, but its quality
    # report must only cover the lecture generated by this job.
    requested = [int(i) for i in state.request.get("only_indices", []) if str(i).isdigit()]
    indices = requested or list(range(1, len(chapters) + 1))
    for index in indices:
        if requested and len(chapters) == len(requested):
            chapter = chapters[requested.index(index)]
        else:
            chapter = chapters[index - 1] if 1 <= index <= len(chapters) else None
        if chapter is None:
            continue
        report = dict(chapter.quality_report)
        confirmation = JOB_DIR / state.job_id / f"confirm-{index}.json"
        confirmed = json.loads(confirmation.read_text(encoding="utf-8")) if confirmation.exists() else None
        results.append({"index": index, "lecture_id": chapter.lecture_id,
                        "accepted": bool(report.get("accepted")), "corrections": 0,
                        **report, "confirmation": confirmed})
    return {"run_id": state.job_id, "course_id": state.course_id, "profile_version": "current",
            "indices": [r["index"] for r in results], "results": results,
            "accepted": sum(r["accepted"] for r in results),
            "rejected": sum(not r["accepted"] for r in results)}


class ConfirmRequest(BaseModel):
    note: str = ""


@app.post("/api/runs/{run_id}/chapters/{lecture_index}/confirm")
async def confirm_run_chapter(run_id: str, lecture_index: int, request: ConfirmRequest):
    if run_id in jobs:
        book = jobs[run_id].book
        if not book or not 1 <= lecture_index <= len(book.chapters):
            raise HTTPException(status_code=404, detail="章节不存在")
        atomic_write_text(JOB_DIR / run_id / f"confirm-{lecture_index}.json",
                          json.dumps({"confirmed": True, "note": request.note,
                                      "at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False))
        return {"ok": True}
    run_dir = config.data_dir / "runs" / run_id
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="运行不存在")
    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / f"confirm-{lecture_index:02d}.json").write_text(
        json.dumps(
            {"confirmed": True, "note": request.note, "at": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("coursebook_agent.app:app", host=config.server.host, port=config.server.port, reload=config.server.debug)
