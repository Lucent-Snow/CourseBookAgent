"""In-repository Zhiyun Classroom HTTP client.

Only the library layer needed by CourseBookAgent is retained here. Command-line
wrappers, skill cache management, and skill-local session handling are not part
of this vendored integration.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import httpx
import os
import re
import json
import struct

from .auth import _ssl_context_allow_legacy_dh

URL_SEARCH = "https://classroom.zju.edu.cn/pptnote/v1/searchlist"
URL_DETAIL = "https://yjapi.cmc.zju.edu.cn/courseapi/v3/multi-search/get-course-detail"
URL_CATALOGUE = "https://yjapi.cmc.zju.edu.cn/courseapi/v2/course/catalogue"
URL_TRANS = "https://yjapi.cmc.zju.edu.cn/courseapi/v3/web-socket/search-trans-result"
URL_PPT = "https://classroom.zju.edu.cn/pptnote/v1/schedule/search-ppt"
URL_MY_COURSES = (
    "https://education.cmc.zju.edu.cn/personal/courseapi/"
    "vlabpassportapi/v1/account-profile/course"
)
URL_MY_STUDY = (
    "https://education.cmc.zju.edu.cn/personal/courseapi/"
    "vlabpassportapi/v1/account-profile/study"
)

DEFAULT_TENANT_ID = "112"
DEFAULT_PER_PAGE = 16
DEFAULT_TENANT_CODE = "112"
FILLER_PREFIX_RE = re.compile(r"^(?:嗯+|啊+|呃+|额+|噢+|哦+|哎+|诶+|欸+)[，。！？；：、,.!?;:\s]*")
LOW_INFORMATION_TEXTS = {
    "嗯",
    "啊",
    "呃",
    "额",
    "哦",
    "噢",
    "哎",
    "诶",
    "欸",
    "是",
    "对",
    "行",
    "到",
    "我",
    "你",
    "他",
    "她",
    "它",
    "这个",
    "那个",
    "没有",
    "不是",
    "什么",
    "感觉",
}


class ZhiyunApi:
    """智云课堂 API client."""

    def __init__(
        self,
        jwt: str,
        student_id: str = "",
        user_id: str = "",
        timeout: float = 15.0,
        webvpn=None,
    ):
        self.jwt = jwt
        self.student_id = student_id
        self.user_id = str(user_id or self._extract_user_id_from_jwt(jwt) or "")
        self.timeout = timeout
        self._webvpn = webvpn
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Authorization": f"Bearer {jwt}" if not jwt.startswith("Bearer ") else jwt,
        }

    @staticmethod
    def _extract_user_id_from_jwt(jwt: str) -> str:
        import base64
        import json

        token = jwt.split(" ", 1)[-1] if jwt.startswith("Bearer ") else jwt
        parts = token.split(".")
        if len(parts) < 2:
            return ""

        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        try:
            claims = json.loads(base64.urlsafe_b64decode(payload))
        except Exception:
            return ""

        user_id = claims.get("sub")
        return str(user_id) if user_id is not None else ""

    @staticmethod
    def _course_matches(course: dict, keyword: str = "", teacher_name: str = "") -> bool:
        title = course.get("title", "")
        teacher = course.get("teacher", "")
        if keyword and keyword not in title:
            return False
        if teacher_name and teacher_name not in teacher:
            return False
        return True

    @staticmethod
    def _parse_course_information(raw: dict) -> dict:
        import json

        info = raw.get("information", {})
        if isinstance(info, str):
            try:
                info = json.loads(info)
            except Exception:
                info = {}
        return info if isinstance(info, dict) else {}

    def _normalize_my_course(self, raw: dict) -> dict:
        info = self._parse_course_information(raw)

        teachers = raw.get("Teachers") or raw.get("teachers") or []
        teacher_names = []
        for item in teachers:
            if not isinstance(item, dict):
                continue
            name = item.get("Realname") or item.get("realname") or ""
            if name:
                teacher_names.append(name)

        teacher = (
            ",".join(teacher_names)
            or raw.get("Teacher")
            or raw.get("teacher_search")
            or raw.get("realname")
            or ""
        )

        return {
            "course_id": raw.get("Id") or raw.get("id"),
            "title": raw.get("Title") or raw.get("title", "未知课程"),
            "term": raw.get("TermName") or raw.get("term_name", "未知学期"),
            "teacher": teacher,
            "college": raw.get("KkxyName") or raw.get("kkxy_name", ""),
            "course_code": info.get("kcdm", ""),
            "course_key": info.get("kcwybm", ""),
            "prev_sub_id": raw.get("PrevSubjectId") or raw.get("course_subject_id") or 0,
            "progress": raw.get("progress", {}),
            "source": "my_courses",
        }

    def _url(self, url: str) -> str:
        if self._webvpn and self._webvpn.logged_in:
            from .webvpn import convert_url
            return convert_url(url)
        return url

    def _make_client(self, **kwargs) -> httpx.AsyncClient:
        kwargs.setdefault("timeout", self.timeout)
        if self._webvpn and self._webvpn.logged_in:
            kwargs.setdefault("verify", True)
            return self._webvpn.make_client(**kwargs)
        kwargs.setdefault("verify", _ssl_context_allow_legacy_dh())
        return httpx.AsyncClient(**kwargs)

    @staticmethod
    def _clean_text(text: str) -> str:
        if text is None:
            return ""
        text = str(text).replace("\r", " ").replace("\n", " ").strip()
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        if re.search(r"[\u4e00-\u9fff]", text):
            text = re.sub(r"\s+", "", text)
        return text.strip()

    @classmethod
    def _normalize_search_text(cls, text: str) -> str:
        return cls._text_core(cls._clean_text(text)).lower()

    @classmethod
    def _keyword_variants(cls, keyword: str) -> list[str]:
        base = cls._normalize_search_text(keyword)
        if not base:
            return []

        variants = OrderedDict()

        def add(value: str):
            value = cls._normalize_search_text(value)
            if len(value) >= 2:
                variants[value] = None

        add(base)
        if len(base) >= 4:
            add(base[:4])
            add(base[-4:])
        if len(base) >= 3:
            add(base[:3])
            add(base[-3:])
        if len(base) >= 2:
            add(base[:2])
            add(base[-2:])
        if len(base) <= 8:
            for size in range(min(4, len(base)), 1, -1):
                for start in range(0, len(base) - size + 1):
                    add(base[start:start + size])

        return list(variants.keys())

    def _normalize_search_result(self, item: dict) -> dict:
        return {
            "course_id": item.get("course_id"),
            "title": item.get("title", "未知课程"),
            "term": item.get("term_name", item.get("term", "未知学期")),
            "teacher": item.get("lecturer_name", item.get("realname", item.get("teacher", ""))),
            "college": item.get("kkxy_name", item.get("college", "")),
            "subject_title": item.get("subject_title", ""),
        }

    @classmethod
    def _search_result_matches(
        cls,
        course: dict,
        *,
        keyword: str = "",
        teacher_name: str = "",
    ) -> bool:
        if teacher_name:
            teacher_norm = cls._normalize_search_text(course.get("teacher", ""))
            if cls._normalize_search_text(teacher_name) not in teacher_norm:
                return False

        if keyword:
            keyword_norm = cls._normalize_search_text(keyword)
            haystacks = [
                cls._normalize_search_text(course.get("title", "")),
                cls._normalize_search_text(course.get("subject_title", "")),
                cls._normalize_search_text(course.get("teacher", "")),
                cls._normalize_search_text(course.get("college", "")),
            ]
            if not any(keyword_norm and keyword_norm in text for text in haystacks if text):
                return False

        return True

    async def _search_courses_once(
        self,
        *,
        teacher_name: str = "",
        keyword: str = "",
        page: int = 1,
        per_page: int = DEFAULT_PER_PAGE,
        max_pages: int = 8,
    ) -> list[dict]:
        params = {
            "tenant_id": DEFAULT_TENANT_ID,
            "page": page,
            "per_page": per_page,
            "tenant_code": DEFAULT_TENANT_CODE,
        }
        if teacher_name:
            params["realname"] = teacher_name
        if keyword:
            params["keyword"] = keyword
        if self.student_id:
            params["user_name"] = self.student_id
        if self.user_id:
            params["user_id"] = self.user_id

        if not params.get("user_name") or not params.get("user_id"):
            raise RuntimeError("智云 search 缺少 user_name/user_id，无法发起搜索。")

        all_courses = []

        async with self._make_client() as client:
            current_page = page
            while current_page < page + max_pages:
                params["page"] = current_page
                resp = await client.get(self._url(URL_SEARCH), headers=self._headers, params=params)
                data = resp.json()

                if data.get("code") not in (None, 0):
                    raise RuntimeError(f"智云 search 失败: {data.get('msg', 'unknown error')}")

                raw_list = []
                if "data" in data and "list" in data["data"]:
                    raw_list = data["data"]["list"]
                elif isinstance(data.get("total"), dict):
                    raw_list = data["total"].get("list", [])

                if not raw_list:
                    break

                all_courses.extend(self._normalize_search_result(item) for item in raw_list)

                if len(raw_list) < per_page:
                    break
                current_page += 1

        return all_courses

    @staticmethod
    def _strip_leading_fillers(text: str) -> str:
        previous = None
        while text and text != previous:
            previous = text
            text = FILLER_PREFIX_RE.sub("", text).strip()
        return text

    @staticmethod
    def _text_core(text: str) -> str:
        return re.sub(r"[，。！？；：、,.!?;:（）()\[\]{}\"'“”‘’·\-\s]", "", text)

    @classmethod
    def _is_low_information_text(cls, text: str) -> bool:
        core = cls._text_core(text)
        if not core:
            return True
        if core.isdigit():
            return True
        if core in LOW_INFORMATION_TEXTS:
            return True
        if len(core) <= 2 and all(ch in "嗯啊呃额哦噢哎诶欸哈呀" for ch in core):
            return True
        return False

    async def search_courses(
        self,
        teacher_name: str = "",
        keyword: str = "",
        page: int = 1,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> list[dict]:
        """搜索智云课程。可按老师名或关键词搜索。

        Returns list of {course_id, title, term, teacher, college}
        """
        variants = self._keyword_variants(keyword) if keyword else [""]
        if not variants:
            variants = [keyword]

        dedup: OrderedDict[str, dict] = OrderedDict()
        for variant in variants:
            raw_courses = await self._search_courses_once(
                teacher_name=teacher_name,
                keyword=variant,
                page=page,
                per_page=per_page,
            )
            for course in raw_courses:
                if not self._search_result_matches(course, keyword=variant, teacher_name=teacher_name):
                    continue
                key = f"{course.get('course_id')}|{course.get('title', '')}|{course.get('teacher', '')}"
                dedup.setdefault(key, course)

            if dedup:
                break

        return sorted(
            dedup.values(),
            key=lambda item: int(item.get("course_id") or 0),
            reverse=True,
        )

    async def get_my_courses(
        self,
        keyword: str = "",
        teacher_name: str = "",
        page: int = 1,
        per_page: int = 100,
    ) -> list[dict]:
        """获取当前账号的课程列表，比全站搜索更适合拿课程 ID。"""
        params = {
            "nowpage": page,
            "per-page": per_page,
            "force_mycourse": 0,
        }
        headers = self._headers.copy()
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Referer"] = "https://education.cmc.zju.edu.cn/personal/"

        all_courses = []

        async with self._make_client() as client:
            current_page = page
            while True:
                params["nowpage"] = current_page
                resp = await client.get(self._url(URL_MY_COURSES), headers=headers, params=params)
                data = resp.json()

                raw_result = data.get("params", {}).get("result", {})
                raw_list = raw_result.get("data", []) or raw_result.get("models", [])
                if not raw_list:
                    break

                normalized = [self._normalize_my_course(item) for item in raw_list]
                all_courses.extend(
                    course
                    for course in normalized
                    if self._course_matches(course, keyword=keyword, teacher_name=teacher_name)
                )

                if len(raw_list) < per_page:
                    break
                current_page += 1

        return all_courses

    async def get_recent_learning(self, per_page: int = 10) -> list[dict]:
        """获取最近学习，用于更快定位近期课程和最近的 sub_id。"""
        params = {
            "nowpage": 1,
            "per-page": per_page,
        }
        headers = self._headers.copy()
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["Referer"] = "https://education.cmc.zju.edu.cn/personal/"

        async with self._make_client() as client:
            resp = await client.get(self._url(URL_MY_STUDY), headers=headers, params=params)
            data = resp.json()

        raw_result = data.get("params", {}).get("result", {})
        raw_list = raw_result.get("models", []) or raw_result.get("data", [])

        results = []
        for item in raw_list:
            results.append({
                "course_id": item.get("id"),
                "title": item.get("title", "未知课程"),
                "teacher": item.get("realname", ""),
                "term": item.get("term_name", ""),
                "sub_id": item.get("course_subject_id"),
                "updated_at": item.get("record_update") or item.get("updated_at", ""),
                "source": "recent_learning",
            })

        return results

    @staticmethod
    def _parse_embedded_json(raw):
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return {}
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    async def get_course_videos(
        self,
        course_id: int | str,
        *,
        teacher_name: str = "",
        with_subtitles_only: bool = False,
    ) -> list[dict]:
        headers = self._headers.copy()
        headers["Referer"] = (
            f"https://classroom.zju.edu.cn/coursedetail?course_id={course_id}&tenant_code=112"
        )

        async with self._make_client() as client:
            resp = await client.get(
                self._url(URL_CATALOGUE),
                headers=headers,
                params={"course_id": str(course_id)},
            )
            data = resp.json()

        raw_list = data.get("result", {}).get("data", []) or data.get("data", [])
        videos = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            lecturer = item.get("lecturer_name", "") or item.get("realname", "")
            if teacher_name and teacher_name not in lecturer:
                continue

            status = str(item.get("status", item.get("sub_status", "")))
            if with_subtitles_only and status != "6":
                continue

            content = self._parse_embedded_json(item.get("content"))
            playback = content.get("playback", {}) if isinstance(content, dict) else {}

            videos.append(
                {
                    "course_id": item.get("course_id", course_id),
                    "sub_id": item.get("sub_id") or item.get("id"),
                    "title": item.get("title") or item.get("sub_title", "未知视频"),
                    "lecturer_name": lecturer,
                    "status": status,
                    "start_at": item.get("start_at", ""),
                    "end_at": item.get("end_at", ""),
                    "duration": item.get("duration", 0),
                    "playback_url": playback.get("url", ""),
                    "has_subtitle": status == "6",
                    "raw": item,
                }
            )

        videos.sort(key=lambda item: int(item.get("sub_id") or 0), reverse=True)
        return videos

    async def get_ppt_timeline(
        self,
        course_id: int | str,
        sub_id: int | str,
        *,
        per_page: int = 100,
    ) -> list[dict]:
        headers = self._headers.copy()
        headers["Referer"] = f"https://classroom.zju.edu.cn/livingroom?sub_id={sub_id}"

        timeline = []
        async with self._make_client() as client:
            page = 1
            while True:
                resp = await client.get(
                    self._url(URL_PPT),
                    headers=headers,
                    params={
                        "course_id": str(course_id),
                        "sub_id": str(sub_id),
                        "page": page,
                        "per_page": per_page,
                    },
                )
                data = resp.json()
                raw_list = data.get("list", [])
                if not raw_list:
                    break

                for item in raw_list:
                    content = self._parse_embedded_json(item.get("content"))
                    timeline.append(
                        {
                            "course_id": str(course_id),
                            "sub_id": str(sub_id),
                            "slide_id": item.get("id"),
                            "created_sec": int(item.get("created_sec", 0) or 0),
                            "image_url": content.get("pptimgurl", ""),
                            "title": content.get("title", ""),
                            "raw": item,
                        }
                    )

                if len(raw_list) < per_page:
                    break
                page += 1

        timeline.sort(key=lambda item: item["created_sec"])
        return timeline

    async def get_course_detail(self, course_id: int | str, teacher_name: str = "") -> list[dict]:
        """获取课程视频列表。只返回 sub_status=6 (有字幕) 的视频。

        Returns list of {sub_id, sub_title, lecturer_name}
        """
        params = {
            "course_id": str(course_id),
        }
        if self.student_id:
            params["student"] = self.student_id

        headers = self._headers.copy()
        headers["Referer"] = (
            f"https://classroom.zju.edu.cn/coursedetail?course_id={course_id}&tenant_code=112"
        )

        async with self._make_client() as client:
            resp = await client.get(self._url(URL_DETAIL), headers=headers, params=params)
            data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"获取课程详情失败: {data.get('msg', 'unknown error')}")

        course_data = data.get("data", {})
        sub_list_raw = course_data.get("sub_list", {})

        valid_subs = []

        def extract_videos(obj):
            if isinstance(obj, list):
                for item in obj:
                    if isinstance(item, dict) and "sub_title" in item:
                        sub_status = str(item.get("sub_status", ""))
                        if sub_status != "6":
                            continue
                        lecturer = item.get("lecturer_name", "")
                        if teacher_name and teacher_name not in lecturer:
                            continue
                        valid_subs.append({
                            "sub_id": item["id"],
                            "sub_title": item["sub_title"],
                            "lecturer_name": lecturer,
                        })
            elif isinstance(obj, dict):
                for value in obj.values():
                    extract_videos(value)

        extract_videos(sub_list_raw)
        valid_subs.sort(key=lambda item: int(item.get("sub_id", 0)), reverse=True)
        return valid_subs

    async def get_transcript(self, sub_id: int | str) -> dict | None:
        """获取字幕 JSON 数据。"""
        import sys
        params = {
            "sub_id": str(sub_id),
            "format": "json",
        }
        headers = self._headers.copy()
        headers["Referer"] = f"https://classroom.zju.edu.cn/livingroom?sub_id={sub_id}"

        actual_url = self._url(URL_TRANS)
        async with self._make_client() as client:
            resp = await client.get(actual_url, headers=headers, params=params)

        if resp.status_code != 200:
            print(f"[zhiyun] transcript API HTTP {resp.status_code} for sub_id={sub_id}", file=sys.stderr)
            return None

        # 先尝试 JSON 解析（不管 Content-Type 是什么）
        try:
            data = resp.json()
        except Exception:
            # JSON 解析失败，检查是否为认证重定向（真正的 HTML 登录页）
            ct = resp.headers.get("content-type", "")
            if "text/html" in ct:
                print(f"[zhiyun] transcript API returned HTML login page for sub_id={sub_id} (JWT expired?)", file=sys.stderr)
            else:
                print(f"[zhiyun] transcript API non-JSON response for sub_id={sub_id}, ct={ct}", file=sys.stderr)
            return None

        # Check for valid transcript data
        if "list" in data and data["list"]:
            return data
        if "data" in data and isinstance(data["data"], dict):
            if "list" in data["data"] and data["data"]["list"]:
                return data

        # 没有找到字幕数据——打印响应以便调试
        print(f"[zhiyun] transcript API returned 200 but no transcript data for sub_id={sub_id}", file=sys.stderr)
        print(f"[zhiyun] response keys: {list(data.keys())}", file=sys.stderr)
        return None

    @staticmethod
    def _extract_transcript_segments(transcript: dict | None) -> list[dict]:
        if not transcript:
            return []
        segments = transcript.get("list", [])
        if not segments and "data" in transcript:
            segments = transcript.get("data", {}).get("list", [])

        # 某些智云字幕接口会返回 list=[{all_content:[...]}]
        if segments and isinstance(segments, list):
            first = segments[0]
            if isinstance(first, dict) and isinstance(first.get("all_content"), list):
                segments = first["all_content"]

        return segments if isinstance(segments, list) else []

    @classmethod
    def _normalize_transcript_segments(
        cls,
        transcript: dict | None,
        include_translation: bool = False,
    ) -> list[dict]:
        normalized = []
        last_text = None
        for seg in cls._extract_transcript_segments(transcript):
            start_raw = seg.get(
                "start_time",
                seg.get("startTime", seg.get("BeginSec", 0)),
            )
            end_raw = seg.get(
                "end_time",
                seg.get("endTime", seg.get("EndSec", start_raw)),
            )
            text = cls._clean_text(seg.get("text", seg.get("content", seg.get("Text", ""))))
            translation = cls._clean_text(
                seg.get(
                    "translation",
                    seg.get("translate", seg.get("TransText", "")),
                )
            )
            if not text:
                continue
            if text == last_text:
                continue

            start_int = int(start_raw or 0)
            end_int = int(end_raw or start_raw or 0)
            if "BeginSec" in seg and "start_time" not in seg and "startTime" not in seg:
                start_sec = start_int
                end_sec = end_int
            else:
                start_sec = start_int // 1000
                end_sec = end_int // 1000

            item = {
                "start_sec": start_sec,
                "end_sec": end_sec,
                "text": text,
            }
            if include_translation and translation:
                item["translation"] = translation

            normalized.append(item)
            last_text = text

        return normalized

    @staticmethod
    def _format_timestamp(total_seconds: int) -> str:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"[{minutes:02d}:{seconds:02d}]"

    @classmethod
    def format_subtitle_text(
        cls,
        transcript: dict | None,
        *,
        timestamps: bool = False,
        include_translation: bool = False,
        filter_fillers: bool = True,
    ) -> str | None:
        segments = cls._normalize_transcript_segments(
            transcript,
            include_translation=include_translation,
        )
        if not segments:
            return None

        if filter_fillers:
            filtered_segments = []
            for seg in segments:
                cleaned_text = cls._strip_leading_fillers(seg["text"])
                if cls._is_low_information_text(cleaned_text):
                    continue

                normalized_seg = dict(seg)
                normalized_seg["text"] = cleaned_text
                filtered_segments.append(normalized_seg)

            if filtered_segments:
                segments = filtered_segments

        if timestamps:
            lines = []
            for seg in segments:
                line = f"{cls._format_timestamp(seg['start_sec'])} {seg['text']}"
                if include_translation and seg.get("translation"):
                    line = f"{line}\n{seg['translation']}"
                lines.append(line)
            return "\n".join(lines) if lines else None

        paragraphs = []
        current = ""
        prev_end = None

        for seg in segments:
            text = seg["text"]
            gap = (seg["start_sec"] - prev_end) if prev_end is not None else 0
            should_break = (
                not current
                or gap >= 12
                or len(current) >= 180
                or (
                    current.endswith(("。", "！", "？", "；"))
                    and len(current) >= 60
                )
            )
            if should_break and current:
                paragraphs.append(current.strip())
                current = ""

            if current and not text.startswith(("，", "。", "！", "？", "；", "：", "、", ",", ".", "!", "?", ";", ":", ")", "）")):
                if re.search(r"[\u4e00-\u9fff]", current[-1] + text[:1]):
                    current += ""
                else:
                    current += " "
            current += text
            if include_translation and seg.get("translation"):
                current += f"\n{seg['translation']}"
            prev_end = seg["end_sec"] or seg["start_sec"]

        if current:
            paragraphs.append(current.strip())

        return "\n\n".join(paragraphs) if paragraphs else None

    async def get_subtitle_text(
        self,
        sub_id: int | str,
        *,
        timestamps: bool = False,
        include_translation: bool = False,
        filter_fillers: bool = True,
    ) -> str | None:
        """获取适合阅读的字幕文本，默认纯文本、默认不带翻译。"""
        transcript = await self.get_transcript(sub_id)
        return self.format_subtitle_text(
            transcript,
            timestamps=timestamps,
            include_translation=include_translation,
            filter_fillers=filter_fillers,
        )

