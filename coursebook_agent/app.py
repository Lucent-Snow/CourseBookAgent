"""FastAPI entrypoint for the coursebook demo."""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from coursebook_agent.agent.llm import LLMClient, LLMError
from coursebook_agent.config import config, save_llm_settings
from coursebook_agent.models import CourseBook, JobState, LectureDraft
from coursebook_agent.pipeline import CourseBookPipeline
from coursebook_agent.renderer.markdown import render_coursebook
from coursebook_agent.sources.zhiyun import ZhiyunError, ZhiyunSource

app = FastAPI(title="CourseBookAgent", version="0.1.0")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
jobs: dict[str, JobState] = {}
generation_lock = asyncio.Lock()


class GenerateRequest(BaseModel):
    course_id: str = "82493"
    refresh_source: bool = False
    regenerate: bool = False


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
        "llm_configured": bool(config.llm.api_key),
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


@app.post("/api/generate", status_code=202)
async def generate(request: GenerateRequest):
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = JobState(job_id=job_id, status="queued", step="排队", progress=0, message="准备生成")
    asyncio.create_task(_run_job(job_id, request))
    return jobs[job_id].model_dump()


async def _run_job(job_id: str, request: GenerateRequest) -> None:
    state = jobs[job_id]
    if generation_lock.locked():
        state.status, state.step, state.message = "queued", "排队", "已有生成任务运行，等待执行"
    async with generation_lock:
        state.status, state.step, state.message = "running", "获取字幕", "正在读取课程讲次和字幕"
        await _generate_locked(state, request)


async def _generate_locked(state: JobState, request: GenerateRequest) -> None:
    pipeline = CourseBookPipeline()

    def progress(done: int, total: int, message: str) -> None:
        state.progress = int(done / total * 100) if total else 0
        state.step = message.split(" ", 1)[0]
        state.message = message

    try:
        book = await pipeline.generate_course(request.course_id, refresh_source=request.refresh_source, regenerate=request.regenerate, review=False, progress=progress)
        if book.warnings:
            state.status, state.progress, state.step, state.message, state.book = "partial", 100, "部分完成", "部分讲次生成失败，可重试失败讲次", book
        else:
            state.status, state.progress, state.step, state.message, state.book = "completed", 100, "完成", "课程讲义已生成", book
    except Exception as exc:
        state.status, state.step, state.error, state.message = "failed", "失败", str(exc), "生成失败"


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    return _get_job(job_id).model_dump()


@app.get("/api/jobs/{job_id}/book")
async def job_book(job_id: str):
    state = _get_job(job_id)
    if state.status not in {"completed", "partial"} or not state.book:
        raise HTTPException(status_code=409, detail="讲义尚未完成")
    return state.book.model_dump()


@app.get("/api/jobs/{job_id}/download.md")
async def download_markdown(job_id: str):
    state = _get_job(job_id)
    if state.status not in {"completed", "partial"} or not state.book:
        raise HTTPException(status_code=409, detail="讲义尚未完成")
    path = config.output_dir / f"coursebook-{state.book.course.course_id}.md"
    path.write_text(render_coursebook(state.book), encoding="utf-8")
    return FileResponse(path, media_type="text/markdown; charset=utf-8", filename=f"coursebook-{state.book.course.course_id}.md")


@app.get("/api/runs/{run_id}/report")
async def v2_run_report(run_id: str):
    path = config.data_dir / "runs" / run_id / "report" / "pilot-quality-report.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="V2 运行报告不存在")
    import json
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/runs/{run_id}/chapters/{lecture_index}")
async def v2_run_chapter(run_id: str, lecture_index: int):
    base = config.data_dir / "runs" / run_id / "chapters"
    matches = sorted(base.glob(f"chapter-{lecture_index:02d}-*.json"))
    if not matches:
        raise HTTPException(status_code=404, detail="V2 试点章节不存在")
    return LectureDraft.model_validate_json(matches[0].read_text(encoding="utf-8")).model_dump()


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
    base_url = request.base_url.strip()
    model = request.model.strip()
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="端点与模型名不能为空")
    api_key = request.api_key.strip() or config.llm.api_key
    save_llm_settings(base_url, model, api_key)
    return {"ok": True, "configured": bool(base_url and model and api_key)}


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
    # 保留 data/cache（原始字幕）与 data/plans（蓝图），只清派生产物
    removed = []
    for sub in ("intermediate", "output", "experiments", "runs"):
        p = config.data_dir / sub
        if p.exists():
            shutil.rmtree(p)
            removed.append(sub)
    return {"ok": True, "removed": removed}


# ── V2 runs / quality ───────────────────────────────────────────────────

@app.get("/api/runs")
async def list_runs():
    runs_dir = config.data_dir / "runs"
    if not runs_dir.exists():
        return {"data": []}
    items = []
    for report_path in sorted(runs_dir.glob("*/report/pilot-quality-report.json"), reverse=True):
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        run_id = data.get("run_id") or report_path.parent.parent.name
        course_id = run_id.split("-", 1)[0] if "-" in run_id else ""
        items.append({
            "run_id": run_id,
            "course_id": course_id,
            "accepted": data.get("accepted", 0),
            "rejected": data.get("rejected", 0),
            "indices": data.get("indices", []),
        })
    return {"data": items}


@app.post("/api/runs/{run_id}/chapters/{lecture_index}/confirm")
async def confirm_run_chapter(run_id: str, lecture_index: int, request: ConfirmRequest):
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


# ── Single-lecture regeneration ──────────────────────────────────────────

@app.post("/api/courses/{course_id}/lectures/{index}/regenerate", status_code=202)
async def regenerate_lecture(course_id: str, index: int):
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = JobState(job_id=job_id, status="queued", step="排队", progress=0, message="准备重生成该讲")
    asyncio.create_task(_run_regenerate(job_id, course_id, index))
    return jobs[job_id].model_dump()


async def _run_regenerate(job_id: str, course_id: str, index: int) -> None:
    state = jobs[job_id]
    async with generation_lock:
        state.status, state.step, state.message = "running", "生成", f"正在重生成第 {index} 讲"
        try:
            pipeline = CourseBookPipeline()
            await pipeline.generate_lecture(course_id, index, regenerate=True, review=True)
            state.progress, state.step, state.message = 60, "合成", "正在更新全书"
            book = await pipeline.generate_course(
                course_id, regenerate=False, review=False, use_book_plan=True,
                synthesize=True, only_indices=[],
            )
            state.status, state.progress, state.step, state.message = "completed", 100, "完成", f"第 {index} 讲已重新生成"
            state.book = book
        except Exception as exc:
            state.status, state.step, state.error, state.message = "failed", "失败", str(exc), "重生成失败"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("coursebook_agent.app:app", host=config.server.host, port=config.server.port, reload=config.server.debug)
