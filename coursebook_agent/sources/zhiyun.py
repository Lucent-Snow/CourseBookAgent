"""Small, cache-first adapter around the zju-scholar CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from coursebook_agent.config import config
from coursebook_agent.models import Course, Lecture, TranscriptSegment


class ZhiyunError(RuntimeError):
    pass


class ZhiyunSource:
    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or config.data_dir / "cache" / "zhiyun"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, name: str) -> Path:
        return self.cache_dir / f"{name}.json"

    def _run(self, *args: str, cache_name: str | None = None, refresh: bool = False) -> dict[str, Any]:
        path = self._cache_path(cache_name) if cache_name else None
        if path and path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        command = [config.zhiyun.python_bin, str(config.zhiyun.zhiyun_script), *args]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ZhiyunError(f"智云命令执行失败: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()[-1000:]
            raise ZhiyunError(f"智云命令返回 {completed.returncode}: {detail}")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ZhiyunError(f"智云返回不是合法 JSON: {completed.stdout[-500:]}") from exc
        if not payload.get("ok"):
            raise ZhiyunError(payload.get("error", {}).get("message", "智云接口失败"))
        if path:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def list_courses(self, refresh: bool = False) -> list[Course]:
        payload = self._run("my-courses", cache_name="my-courses", refresh=refresh)
        return [Course(course_id=str(row["course_id"]), name=row.get("title", ""), teacher=row.get("teacher"), term=row.get("term")) for row in payload.get("data", [])]

    def get_course(self, course_id: str, refresh: bool = False) -> Course:
        for course in self.list_courses(refresh=refresh):
            if course.course_id == str(course_id):
                return course
        raise ZhiyunError(f"找不到课程: {course_id}")

    def list_lectures(self, course_id: str, refresh: bool = False) -> list[Lecture]:
        payload = self._run("videos", "--course-id", str(course_id), cache_name=f"videos-{course_id}", refresh=refresh)
        rows = list(payload.get("data", []))
        rows.reverse()  # CLI returns newest first; book order is chronological.
        lectures = []
        for index, row in enumerate(rows, start=1):
            sub_id = str(row.get("sub_id", ""))
            lectures.append(Lecture(lecture_id=sub_id, course_id=str(course_id), title=row.get("title") or f"第 {index} 讲", index=index, duration=row.get("duration") or None, lecturer_name=row.get("lecturer_name")))
        return lectures

    def get_transcript(self, lecture: Lecture, refresh: bool = False) -> list[TranscriptSegment]:
        payload = self._run("transcript", "--sub-id", lecture.lecture_id, cache_name=f"transcript-{lecture.lecture_id}", refresh=refresh)
        rows = payload.get("data", {}).get("segments", [])
        return [TranscriptSegment(lecture_id=lecture.lecture_id, index=index, start_sec=int(row.get("start_sec", 0)), end_sec=int(row.get("end_sec", 0)), text=str(row.get("text", "")).strip()) for index, row in enumerate(rows)]
