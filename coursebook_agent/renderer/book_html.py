"""Published paper-book HTML rendering.

Renders a CourseBook into a standalone, offline-capable HTML file that keeps
the reading experience of the paper template and links every "字幕时间段"
back to the matching lecture video node.

The template embeds its own Markdown renderer and viewer engine, so the
output has no runtime dependency on CDNs or the workbench.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from coursebook_agent.config import config
from coursebook_agent.models import CourseBook
from coursebook_agent.renderer.markdown import render_coursebook

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
REPLAY_HOST = "https://interactivemeta.cmc.zju.edu.cn"
DEFAULT_TENANT_CODE = "112"


def replay_page_url(course_id: str, sub_id: str, tenant_code: str = DEFAULT_TENANT_CODE) -> str:
    return (
        f"{REPLAY_HOST}/#/replay?course_id={course_id}&sub_id={sub_id}"
        f"&tenant_code={tenant_code}"
    )


def _first_url(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("url") or ""
    if isinstance(value, (list, tuple)):
        value = next((str(item) for item in value if item), "")
    return str(value or "")


def _videos_from_resources(resources: Iterable[Any] | None) -> dict[str, dict[str, str]]:
    """Video references carried by parsed resources (subtitle metadata)."""
    found: dict[str, dict[str, str]] = {}
    for resource in resources or ():
        meta = getattr(resource, "meta", None) or {}
        if not isinstance(meta, dict):
            continue
        lecture_id = str(meta.get("lecture_id") or "")
        if not lecture_id:
            continue
        entry = {
            "file": str(meta.get("video_url") or ""),
            "link": str(meta.get("replay_url") or ""),
        }
        if entry["file"] or entry["link"]:
            found[lecture_id] = entry
    return found


def _videos_from_cache(course_id: str) -> tuple[dict[str, dict[str, str]], list[tuple[str, dict[str, str]]]]:
    """Offline fallback: the cached zhiyun videos list for this course."""
    if not course_id:
        return {}, []
    path = config.data_dir / "cache" / "zhiyun" / f"videos-{course_id}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, []
    rows = [row for row in (payload.get("data") or []) if isinstance(row, dict)]

    def sort_key(row: dict) -> int:
        try:
            return int(row.get("sub_id") or 0)
        except (TypeError, ValueError):
            return 0

    rows.sort(key=sort_key)
    by_lecture: dict[str, dict[str, str]] = {}
    ordered: list[tuple[str, dict[str, str]]] = []
    for row in rows:
        sub_id = str(row.get("sub_id") or "")
        if not sub_id:
            continue
        entry = {
            "file": _first_url(row.get("playback_url") or row.get("playback")),
            "link": replay_page_url(course_id, sub_id),
        }
        by_lecture[sub_id] = entry
        ordered.append((str(row.get("title") or ""), entry))
    return by_lecture, ordered


def resolve_video_index(
    book: CourseBook, resources: Iterable[Any] | None = None
) -> dict[str, dict[str, str]]:
    """Map chapter title -> {"file": mp4, "link": replay page}.

    Priority: parsed-resource metadata (generation time, no network), then the
    cached videos list. Chapters without a lecture match fall back to date in
    title, then to chronological order.
    """
    by_lecture = _videos_from_resources(resources)
    by_date: dict[str, dict[str, str]] = {}
    ordered: list[dict[str, str]] = []
    cached_by_lecture, cached_ordered = _videos_from_cache(str(getattr(book.course, "course_id", "") or ""))
    for lecture_id, entry in cached_by_lecture.items():
        by_lecture.setdefault(lecture_id, entry)
    for title, entry in cached_ordered:
        match = re.search(r"(\d{4}-\d{2}-\d{2})", title)
        if match:
            by_date.setdefault(match.group(1), entry)
        ordered.append(entry)

    index: dict[str, dict[str, str]] = {}
    for position, chapter in enumerate(book.chapters):
        entry = by_lecture.get(str(chapter.lecture_id or ""))
        if not entry:
            match = re.search(r"(\d{4}-\d{2}-\d{2})", chapter.title or "")
            if match:
                entry = by_date.get(match.group(1))
        if not entry and position < len(ordered):
            entry = ordered[position]
        if entry and (entry.get("file") or entry.get("link")):
            index[chapter.title] = dict(entry)
    return index


def _asset(name: str) -> str:
    return (ASSETS_DIR / name).read_text(encoding="utf-8")


def render_coursebook_html(book: CourseBook) -> str:
    """Render a CourseBook to a standalone paper-style HTML document."""
    markdown = render_coursebook(book, include_time_links=True)
    index = {}
    if isinstance(book.render_config, dict):
        raw = book.render_config.get("video_index")
        if isinstance(raw, dict):
            index = {str(k): v for k, v in raw.items() if isinstance(v, dict)}
    links = {title: str(v.get("link") or "") for title, v in index.items() if v.get("link")}
    files = {title: str(v.get("file") or "") for title, v in index.items() if v.get("file")}

    markdown_safe = markdown.replace("</script", "<\\/script").replace("<!--", "<\\!--")
    html = _asset("book-template.html")
    html = html.replace("__MARKED_JS__", _asset("marked.min.js"))
    html = html.replace("__ENGINE_JS__", _asset("engine.js"))
    html = html.replace("__SAMPLE_MD__", markdown_safe)
    html = html.replace("__VIDEO_LINKS_JSON__", json.dumps(links, ensure_ascii=False))
    html = html.replace("__VIDEO_FILES_JSON__", json.dumps(files, ensure_ascii=False))
    safe_title = (book.title or "课程教辅").replace("<", "&lt;").replace(">", "&gt;")
    html = html.replace("<title>课程教辅 · 纸书预览</title>", f"<title>{safe_title}</title>")
    return html
