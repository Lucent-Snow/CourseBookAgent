"""Cache-first, in-repository adapter for Zhejiang University's Zhiyun Classroom.

The API client is vendored under :mod:`coursebook_agent.vendor.zhiyun`; this
module intentionally has no dependency on a pi skill or an external script.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from coursebook_agent.config import config
from coursebook_agent.models import Course, Lecture, TranscriptSegment
from coursebook_agent.vendor.zhiyun import ZhiyunApi
from coursebook_agent.vendor.zhiyun.auth import ZjuAuth


class ZhiyunError(RuntimeError):
    pass


class ZhiyunSource:
    """Fetch courses and timed subtitles without relying on zju-scholar."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or config.data_dir / "cache" / "zhiyun"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, name: str) -> Path:
        return self.cache_dir / f"{name}.json"

    def _read_cache(self, name: str) -> dict[str, Any] | None:
        path = self._cache_path(name)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ZhiyunError(f"智云缓存损坏：{path}: {exc}") from exc

    def _write_cache(self, name: str, feature: str, data: Any) -> dict[str, Any]:
        payload = {"ok": True, "platform": "zhiyun", "feature": feature, "source": "live", "data": data}
        self._cache_path(name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def _session_path(self) -> Path:
        return config.zhiyun.session_file

    def _load_session(self) -> dict[str, Any]:
        path = self._session_path()
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            raise ZhiyunError(f"智云会话文件无法读取：{path}: {exc}") from exc

    def _make_api(self) -> ZhiyunApi:
        session = self._load_session()
        jwt = str(session.get("zhiyun_jwt") or config.zhiyun.jwt or "")
        if not jwt:
            raise ZhiyunError(
                "未配置智云 JWT。请在 .env 设置 ZHIYUN_JWT，或设置 ZHIYUN_SESSION_FILE 指向已登录的 session.json。"
            )
        webvpn = None
        if session.get("webvpn_enabled") and session.get("webvpn_cookies"):
            try:
                from coursebook_agent.vendor.zhiyun.webvpn import WebVpnSession
            except ImportError as exc:
                raise ZhiyunError("WebVPN 会话需要 pycryptodome；请执行 uv sync 安装项目依赖") from exc
            webvpn = WebVpnSession()
            webvpn.cookies = session["webvpn_cookies"]
            webvpn.logged_in = True
        return ZhiyunApi(
            jwt=jwt,
            student_id=str(session.get("username") or ""),
            user_id=str(session.get("user_id") or ""),
            webvpn=webvpn,
        )

    async def _fetch_courses(self) -> list[dict[str, Any]]:
        return await self._make_api().get_my_courses()

    async def _fetch_videos(self, course_id: str) -> list[dict[str, Any]]:
        return await self._make_api().get_course_videos(course_id, with_subtitles_only=False)

    async def _fetch_transcript(self, lecture: Lecture) -> list[dict[str, Any]]:
        api = self._make_api()
        transcript = await api.get_transcript(lecture.lecture_id)
        if transcript is None:
            raise ZhiyunError(f"未获取到讲次 {lecture.lecture_id} 的字幕；可能是登录过期或该视频没有字幕")
        return api._normalize_transcript_segments(transcript)

    def _load_or_fetch(self, cache_name: str, feature: str, fetch, refresh: bool) -> dict[str, Any]:
        cached = None if refresh else self._read_cache(cache_name)
        if cached is not None:
            return cached
        try:
            data = asyncio.run(fetch())
        except ZhiyunError:
            raise
        except Exception as exc:
            raise ZhiyunError(f"智云 API 请求失败：{exc}") from exc
        if not data:
            raise ZhiyunError(f"智云 API 未返回 {feature} 数据；登录会话可能已过期")
        return self._write_cache(cache_name, feature, data)

    def list_courses(self, refresh: bool = False) -> list[Course]:
        payload = self._load_or_fetch("my-courses", "my_courses", self._fetch_courses, refresh)
        return [
            Course(
                course_id=str(row["course_id"]), name=row.get("title", ""),
                teacher=row.get("teacher"), term=row.get("term"),
            )
            for row in payload.get("data", [])
        ]

    def get_course(self, course_id: str, refresh: bool = False) -> Course:
        for course in self.list_courses(refresh=refresh):
            if course.course_id == str(course_id):
                return course
        raise ZhiyunError(f"找不到课程: {course_id}")

    def list_lectures(self, course_id: str, refresh: bool = False) -> list[Lecture]:
        payload = self._load_or_fetch(
            f"videos-{course_id}", "course_videos", lambda: self._fetch_videos(str(course_id)), refresh,
        )
        rows = list(payload.get("data", []))
        # API returns newest first. CourseBook must be chronological.
        rows.reverse()
        return [
            Lecture(
                lecture_id=str(row.get("sub_id", "")), course_id=str(course_id),
                title=row.get("title") or f"第 {index} 讲", index=index,
                duration=row.get("duration") or None, lecturer_name=row.get("lecturer_name"),
            )
            for index, row in enumerate(rows, start=1)
        ]

    def get_transcript(self, lecture: Lecture, refresh: bool = False) -> list[TranscriptSegment]:
        payload = self._load_or_fetch(
            f"transcript-{lecture.lecture_id}", "transcript_segments", lambda: self._fetch_transcript(lecture), refresh,
        )
        data = payload.get("data", [])
        # Earlier CourseBookAgent releases cached the CLI envelope
        # {data: {sub_id, segments}}. Support that local format without ever
        # calling the removed external script.
        rows = data.get("segments", []) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ZhiyunError(f"字幕缓存格式不正确：{self._cache_path(f'transcript-{lecture.lecture_id}')}")
        return [
            TranscriptSegment(
                lecture_id=lecture.lecture_id, index=index,
                start_sec=int(row.get("start_sec", 0)), end_sec=int(row.get("end_sec", 0)),
                text=str(row.get("text", "")).strip(),
            )
            for index, row in enumerate(rows) if isinstance(row, dict)
        ]

    def auth_status(self) -> dict[str, Any]:
        """Return non-sensitive local session metadata for the UI."""
        session = self._load_session()
        return {
            "authenticated": bool(session.get("zhiyun_jwt") or config.zhiyun.jwt),
            "username": str(session.get("username") or ""),
            "webvpn": bool(session.get("webvpn_enabled")),
        }

    async def login(self, username: str, password: str, *, webvpn: bool = False) -> dict[str, Any]:
        """Authenticate with university credentials and persist only this app's session.

        The password is used for this request only. It is never written to disk;
        the resulting Zhiyun JWT and, when needed, WebVPN cookies are stored in
        the gitignored project data directory.
        """
        username, password = username.strip(), password.strip()
        if not username or not password:
            raise ZhiyunError("请输入学号和密码")
        try:
            if webvpn:
                from coursebook_agent.vendor.zhiyun.webvpn import WebVpnSession

                vpn = WebVpnSession()
                if not await vpn.login(username, password):
                    raise ZhiyunError("WebVPN 登录失败，请检查学号和密码")
                await vpn.sso_login_via_vpn(username, password)
                auth = ZjuAuth(webvpn=vpn)
                jwt = await auth.login_zhiyun()
                session = {
                    "username": username,
                    "zhiyun_jwt": jwt,
                    "webvpn_enabled": True,
                    "webvpn_cookies": vpn.cookies,
                }
            else:
                auth = ZjuAuth()
                await auth.sso_login(username, password)
                jwt = await auth.login_zhiyun()
                session = {"username": username, "zhiyun_jwt": jwt, "webvpn_enabled": False}
        except ZhiyunError:
            raise
        except Exception as exc:
            raise ZhiyunError(f"智云认证失败：{exc}") from exc

        self._session_path().parent.mkdir(parents=True, exist_ok=True)
        self._session_path().write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.auth_status()
