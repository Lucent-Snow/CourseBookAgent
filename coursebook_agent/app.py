"""FastAPI entrypoint for the coursebook demo."""

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
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from coursebook_agent.agent.llm import LLMClient, LLMError
from coursebook_agent.config import config, normalize_llm_base_url, save_llm_settings
from coursebook_agent.models import CourseBook, JobState, LectureDraft
from coursebook_agent.pipeline import CourseBookPipeline
from coursebook_agent.storage import atomic_write_text
from coursebook_agent.renderer.markdown import render_coursebook
from coursebook_agent.sources.zhiyun import ZhiyunError, ZhiyunSource

app = FastAPI(title="CourseBookAgent", version="0.1.0")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
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
             "message": state.message, "at": datetime.now(timezone.utc).isoformat()}
    if not state.events or any(state.events[-1].get(k) != event[k] for k in ("status", "step", "progress", "message")):
        state.events.append(event)
    atomic_write_text(path, state.model_dump_json(indent=2))


def _load_jobs() -> None:
    for path in JOB_DIR.glob("*.json"):
        try:
            state = JobState.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if path.stem != state.job_id:
            continue
        if state.status in {"running", "queued"}:
            state.status, state.step, state.message = "interrupted", "中断", "服务重启，等待手动恢复"
            _persist_job(state)
        jobs[state.job_id] = state


_load_jobs()


class GenerateRequest(BaseModel):
    course_id: str = Field(default="82493", pattern=r"^[A-Za-z0-9_-]+$")
    refresh_source: bool = False
    regenerate: bool = False
    review: bool = False


def _schedule(job_id: str, coroutine) -> None:
    task = asyncio.create_task(coroutine)
    tasks[job_id] = task
    task.add_done_callback(lambda finished: tasks.pop(job_id, None) if tasks.get(job_id) is finished else None)


class ZhiyunLoginRequest(BaseModel):
    username: str
    password: str
    webvpn: bool = False


class LLMSettingsRequest(BaseModel):
    base_url: str
    model: str
    api_key: str = ""


class ConfirmRequest(BaseModel):
    note: str = ""


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "llm_configured": bool(config.llm.api_key and config.llm.base_url and config.llm.model),
        "zhiyun_live_configured": config.zhiyun.has_credentials,
        "demo_course_id": "82493",
    }


@app.get("/api/zhiyun/auth")
async def zhiyun_auth_status():
    return ZhiyunSource().auth_status()


@app.post("/api/zhiyun/login")
async def zhiyun_login(request: ZhiyunLoginRequest):
    try:
        return await ZhiyunSource().login(request.username, request.password, webvpn=request.webvpn)
    except ZhiyunError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/api/courses")
async def courses():
    try:
        values = await asyncio.to_thread(ZhiyunSource().list_courses)
        return {"data": [item.model_dump() for item in values]}
    except ZhiyunError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/courses/{course_id}/lectures")
async def course_lectures(course_id: str):
    try:
        values = await asyncio.to_thread(ZhiyunSource().list_lectures, course_id)
        return {"data": [item.model_dump() for item in values]}
    except ZhiyunError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/generate", status_code=202)
async def generate(request: GenerateRequest):
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = JobState(job_id=job_id, course_id=request.course_id, request=request.model_dump(), status="queued", step="排队", progress=0, message="准备生成")
    _persist_job(jobs[job_id])
    _schedule(job_id, _run_job(job_id, request))
    return jobs[job_id].model_dump()


async def _run_job(job_id: str, request: GenerateRequest) -> None:
    state = jobs[job_id]
    if generation_lock.locked():
        state.status, state.step, state.message = "queued", "排队", "已有生成任务运行，等待执行"
        _persist_job(state)
    async with generation_lock:
        state.status, state.step, state.message = "running", "获取字幕", "正在读取课程讲次和字幕"
        _persist_job(state)
        await _generate_locked(state, request)


async def _generate_locked(state: JobState, request: GenerateRequest, only_indices: list[int] | None = None) -> None:
    def progress(done: int, total: int, message: str, chapter: dict | None = None) -> None:
        state.progress = min(95, int(done / total * 95)) if total else 0
        state.step = message.split(" ", 1)[0]
        state.message = message
        if chapter:
            idx = chapter.get("index")
            state.chapters = sorted(
                [c for c in state.chapters if c.get("index") != idx] + [chapter],
                key=lambda c: c.get("index", 0),
            )
        _persist_job(state)

    try:
        pipeline = CourseBookPipeline()
        book = await asyncio.wait_for(pipeline.generate_course(
            request.course_id,
            refresh_source=request.refresh_source,
            regenerate=request.regenerate,
            review=request.review,
            progress=progress,
            only_indices=only_indices,
            checkpoint_dir=JOB_DIR / state.job_id,
        ), timeout=3600)
        if any(c.get("status") == "failed" for c in state.chapters):
            state.status, state.progress, state.step, state.message, state.book = "partial", 100, "部分完成", "部分讲次生成失败，可重试失败讲次", book
        else:
            state.status, state.progress, state.step, state.message, state.book = "completed", 100, "完成", "课程讲义已生成", book
        _persist_job(state)
    except asyncio.TimeoutError:
        state.error_code = "task_timeout"
        state.status, state.step, state.error, state.message = "failed", "超时", "任务超过 60 分钟", "生成超时，可恢复已完成章节"
        _persist_job(state)
    except Exception as exc:
        state.error_code = getattr(exc, "code", "generation_error")
        state.status, state.step, state.error, state.message = "failed", "失败", str(exc), "生成失败"
        _persist_job(state)
    except asyncio.CancelledError:
        state.status, state.step, state.message = "interrupted", "中断", "生成中断，可手动恢复"
        _persist_job(state)
        raise


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    return _get_job(job_id).model_dump()


@app.post("/api/jobs/{job_id}/retry", status_code=202)
async def retry_failed_job(job_id: str):
    state = _get_job(job_id)
    if state.status not in {"failed", "partial", "interrupted"}:
        raise HTTPException(status_code=409, detail="只有失败或部分完成的任务可以重试")
    failed_indices = sorted(
        int(item["index"])
        for item in state.chapters
        if item.get("status") == "failed" and str(item.get("index", "")).isdigit()
    )
    if not state.course_id:
        raise HTTPException(status_code=409, detail="任务缺少课程信息，无法重试")
    if not failed_indices and state.status == "partial":
        raise HTTPException(status_code=409, detail="没有可重试的失败章节")
    state.status = "queued"
    state.step = "排队"
    state.progress = 0
    state.error = None
    state.error_code = None
    state.message = "准备恢复任务"
    _persist_job(state)
    _schedule(state.job_id, _run_retry_job(state.job_id, state.course_id, failed_indices))
    return {"job_id": state.job_id, "retry_indices": failed_indices, **state.model_dump()}


async def _run_retry_job(job_id: str, course_id: str, retry_indices: list[int]) -> None:
    state = jobs[job_id]
    async with generation_lock:
        state.status, state.step, state.message = "running", "重试", f"正在重试 {len(retry_indices)} 个失败章节"
        _persist_job(state)
        try:
            pipeline = CourseBookPipeline()
            lectures = await asyncio.to_thread(pipeline.source.list_lectures, course_id)
            successful = {c["index"] for c in state.chapters if c.get("status") == "done"}
            successful = {i for i in successful if 1 <= i <= len(lectures)
                          and (JOB_DIR / job_id / f"chapter-{lectures[i-1].lecture_id}.json").exists()}
            retry_indices = sorted(set(retry_indices) | (set(range(1, len(lectures) + 1)) - successful))
        except Exception as exc:
            state.status, state.error, state.message = "failed", str(exc), "恢复准备失败"
            _persist_job(state)
            return
        await _generate_locked(
            state,
            GenerateRequest(course_id=course_id, regenerate=True, refresh_source=False,
                            review=bool(state.request.get("review", False))),
            only_indices=retry_indices,
        )


@app.get("/api/jobs/{job_id}/book")
async def job_book(job_id: str):
    state = _get_job(job_id)
    if state.status not in {"completed", "partial"} or not state.book:
        raise HTTPException(status_code=409, detail="讲义尚未完成")
    return state.book.model_dump()


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    state = _get_job(job_id)
    task = tasks.get(job_id)
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


@app.get("/api/jobs/{job_id}/chapters/{index}/sources/{chunk_id}")
async def chapter_source(job_id: str, index: int, chunk_id: str):
    state = _get_job(job_id)
    manifest = JOB_DIR / job_id / "lectures.json"
    if not manifest.exists():
        raise HTTPException(status_code=404, detail="没有保存字幕证据")
    lectures = json.loads(manifest.read_text(encoding="utf-8"))
    if not 1 <= index <= len(lectures):
        raise HTTPException(status_code=404, detail="章节不存在")
    lecture_id = lectures[index - 1]["lecture_id"]
    path = JOB_DIR / state.job_id / f"chunks-{lecture_id}.json"
    if path.exists():
        for chunk in json.loads(path.read_text(encoding="utf-8")):
            if chunk["chunk_id"] == chunk_id and chunk["lecture_id"] == lecture_id:
                return chunk
    raise HTTPException(status_code=404, detail="字幕块不存在")


@app.get("/api/jobs/{job_id}/download.md")
async def download_markdown(job_id: str):
    state = _get_job(job_id)
    if state.status not in {"completed", "partial"} or not state.book:
        raise HTTPException(status_code=409, detail="讲义尚未完成")
    path = config.output_dir / f"coursebook-{state.book.course.course_id}.md"
    atomic_write_text(path, render_coursebook(state.book))
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=f"coursebook-{state.book.course.course_id}.md")


@app.get("/api/runs/{run_id}/report")
async def v2_run_report(run_id: str):
    if run_id in jobs:
        return _job_report(jobs[run_id])
    path = config.data_dir / "runs" / run_id / "report" / "pilot-quality-report.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="V2 运行报告不存在")
    import json
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/runs/{run_id}/chapters/{lecture_index}")
async def v2_run_chapter(run_id: str, lecture_index: int):
    if run_id in jobs and jobs[run_id].book:
        chapters = jobs[run_id].book.chapters
        if 1 <= lecture_index <= len(chapters):
            return chapters[lecture_index - 1].model_dump()
        raise HTTPException(status_code=404, detail="章节不存在")
    base = config.data_dir / "runs" / run_id / "chapters"
    matches = sorted(base.glob(f"chapter-{lecture_index:02d}-*.json"))
    if not matches:
        raise HTTPException(status_code=404, detail="V2 试点章节不存在")
    return LectureDraft.model_validate_json(matches[0].read_text(encoding="utf-8")).model_dump()


@app.get("/api/books")
async def list_books():
    intermediate = config.data_dir / "intermediate"
    items = []
    if intermediate.exists():
        for p in sorted(intermediate.glob("coursebook-*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            items.append({
                "course_id": str(data.get("course", {}).get("course_id", p.stem.replace("coursebook-", ""))),
                "title": data.get("title", ""),
                "chapters": len(data.get("chapters", [])),
            })
    return {"data": items}


@app.get("/api/books/{course_id}")
async def persisted_book(course_id: str):
    path = config.data_dir / "intermediate" / f"coursebook-{course_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="尚无已保存的课程讲义")
    return CourseBook.model_validate_json(path.read_text(encoding="utf-8")).model_dump()


@app.get("/api/books/{course_id}/download.md")
async def download_persisted_markdown(course_id: str):
    path = config.output_dir / f"coursebook-{course_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="尚无已保存的课程讲义")
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=f"coursebook-{course_id}.md")


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
        },
        "zhiyun": zhiyun,
        "data": {
            "cache_bytes": _dir_size(config.data_dir) if config.data_dir.exists() else 0,
            "course_count": course_count,
        },
    }


@app.put("/api/settings/llm")
async def update_llm_settings(request: LLMSettingsRequest):
    base_url = normalize_llm_base_url(request.base_url)
    model = request.model.strip()
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="端点与模型名不能为空")
    api_key = request.api_key.strip() or config.llm.api_key
    save_llm_settings(base_url, model, api_key)
    return {"ok": True, "configured": bool(config.llm.base_url and model and api_key), "base_url": config.llm.base_url}


@app.post("/api/settings/llm/test")
async def test_llm_connection():
    if not (config.llm.base_url and config.llm.model and config.llm.api_key):
        raise HTTPException(status_code=400, detail="请先完成大模型配置")
    start = time.monotonic()
    try:
        await LLMClient(max_retries=1, timeout=30).complete(
            "你是连接测试助手。", "请只回复两个字符：OK", max_tokens=8, temperature=0
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"连接失败：{exc}") from exc
    return {"ok": True, "model": config.llm.model, "latency_ms": int((time.monotonic() - start) * 1000)}


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


# ── V2 runs / quality ───────────────────────────────────────────────────

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


def _job_report(state: JobState) -> dict:
    results = []
    for index, chapter in enumerate(state.book.chapters if state.book else [], 1):
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
        raise HTTPException(status_code=404, detail="V2 运行不存在")
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


# ── Single-lecture generation / regeneration ──────────────────────────────

async def _start_single_lecture_job(course_id: str, index: int, regenerate: bool) -> JobState:
    job_id = uuid.uuid4().hex[:12]
    state = JobState(
        job_id=job_id,
        course_id=course_id,
        request={"review": True, "only_indices": [index], "regenerate": regenerate},
        status="queued",
        step="排队",
        progress=0,
        message=f"准备{'重新' if regenerate else ''}生成第 {index} 讲",
    )
    jobs[job_id] = state
    _persist_job(state)
    _schedule(job_id, _run_single_lecture(job_id, course_id, index))
    return state


async def _run_single_lecture(job_id: str, course_id: str, index: int) -> None:
    state = jobs[job_id]
    async with generation_lock:
        state.status, state.step, state.message = "running", "生成", f"正在生成第 {index} 讲"
        _persist_job(state)
        try:
            pipeline = CourseBookPipeline()
            book = await asyncio.wait_for(
                pipeline.generate_single_lecture(course_id, index, review=True),
                timeout=3600,
            )
            state.book = book
            lectures = await asyncio.to_thread(pipeline.source.list_lectures, course_id)
            target_id = lectures[index - 1].lecture_id
            chapter = next((c for c in book.chapters if c.lecture_id == target_id), book.chapters[-1])
            state.chapters = [{
                "index": index,
                "title": chapter.title,
                "status": "done",
                "total_chars": sum(len(s.content) for s in chapter.sections),
                "sections": [{"heading": s.heading, "chars": len(s.content), "components": len(s.components), "time_links": len(s.time_links)} for s in chapter.sections],
                "warnings": chapter.warnings[:5],
            }]
            state.status, state.progress, state.step, state.message = "completed", 100, "完成", f"第 {index} 讲已生成"
            _persist_job(state)
        except Exception as exc:
            state.status, state.step, state.error, state.message = "failed", "失败", str(exc), f"第 {index} 讲生成失败"
            _persist_job(state)


@app.post("/api/courses/{course_id}/lectures/{index}/generate", status_code=202)
async def generate_lecture(course_id: str, index: int):
    return (await _start_single_lecture_job(course_id, index, False)).model_dump()

@app.post("/api/courses/{course_id}/lectures/{index}/regenerate", status_code=202)
async def regenerate_lecture(course_id: str, index: int):
    return (await _start_single_lecture_job(course_id, index, True)).model_dump()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("coursebook_agent.app:app", host=config.server.host, port=config.server.port, reload=config.server.debug)
