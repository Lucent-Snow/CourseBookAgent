"""FastAPI entrypoint for the coursebook demo."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from coursebook_agent.config import config
from coursebook_agent.models import CourseBook, JobState
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


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/health")
async def health():
    return {"ok": True, "llm_configured": bool(config.llm.api_key), "demo_course_id": "82493"}


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("coursebook_agent.app:app", host=config.server.host, port=config.server.port, reload=config.server.debug)
