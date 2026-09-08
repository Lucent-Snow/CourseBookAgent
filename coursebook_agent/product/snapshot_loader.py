"""Translate a product InputSnapshot into generation-ready parsed resources.

The product workbench owns resource storage, parsing and SHA-256 content
addressing.  The generation core owns the BookPlan/chapter Agent.  This
loader is the thin bridge that turns an InputSnapshot into the list of
``ParsedResource`` units the main Agent consumes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coursebook_agent.config import config
from coursebook_agent.models import (
    ParsedResource,
    ParsedResourceUnit,
    ResourceLocation,
)
from coursebook_agent.product.parsers import parse_document
from coursebook_agent.product.service import ProductService
from coursebook_agent.sources.zhiyun import ZhiyunSource

logger = logging.getLogger(__name__)


@dataclass
class LoadedResources:
    course: Any | None
    resources: list[ParsedResource]


def _build_units_from_parsed_text(
    revision_id: str,
    text: str,
    *,
    page_count: int | None,
    kind: str,
) -> list[ParsedResourceUnit]:
    """Turn a flat parsed text into small units with location info."""
    if not text:
        return []
    units: list[ParsedResourceUnit] = []
    if kind in {"pdf", "pptx"}:
        # parsers.py tags each page with "[第 N 页]" / "[第 N 张幻灯片]"
        blocks = [b for b in text.split("\n\n") if b.strip()]
        for index, block in enumerate(blocks, start=1):
            label = ""
            if block.startswith("[第") and ("]" in block):
                label = block.split("]", 1)[0] + "]"
            units.append(ParsedResourceUnit(
                unit_id=f"{revision_id}-u{index}",
                text=block.strip(),
                location=ResourceLocation(
                    kind="page" if kind == "pdf" else "slide",
                    start=index,
                    end=index,
                    label=label,
                ),
            ))
    elif kind == "docx":
        blocks = [b for b in text.split("\n\n") if b.strip()]
        for index, block in enumerate(blocks, start=1):
            units.append(ParsedResourceUnit(
                unit_id=f"{revision_id}-u{index}",
                text=block.strip(),
                location=ResourceLocation(kind="section", start=index, end=index),
            ))
    else:
        # Fallback: split into ~600-char chunks.
        chunk_size = 600
        for index, start in enumerate(range(0, max(len(text), 1), chunk_size), start=1):
            chunk = text[start:start + chunk_size]
            if not chunk.strip():
                continue
            units.append(ParsedResourceUnit(
                unit_id=f"{revision_id}-u{index}",
                text=chunk,
                location=ResourceLocation(kind="section", start=start, end=start + len(chunk)),
            ))
    if page_count is not None:
        return units
    return units


def _parse_zhiyun_transcript_units(
    revision_id: str,
    text: str,
) -> list[ParsedResourceUnit]:
    """Parse a Zhiyun transcript text into timed units.

    The product service writes the transcript as::

        [start-end] text

    One line per segment.  We map each into a TranscriptSegment unit.
    """
    units: list[ParsedResourceUnit] = []
    for index, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and "]" in line:
            stamp, body = line[1:].split("]", 1)
            body = body.strip()
            start_s, _, end_s = stamp.partition("-")
            try:
                start_i = int(start_s.strip() or "0")
                end_i = int(end_s.strip() or start_s.strip() or "0")
            except ValueError:
                start_i, end_i = 0, 0
            units.append(ParsedResourceUnit(
                unit_id=f"{revision_id}-s{index}",
                text=body,
                location=ResourceLocation(
                    kind="transcript_segment",
                    start=start_i,
                    end=end_i,
                    label=stamp,
                ),
            ))
        else:
            units.append(ParsedResourceUnit(
                unit_id=f"{revision_id}-s{index}",
                text=line,
                location=ResourceLocation(kind="section", start=index, end=index),
            ))
    return units


def _zhiyun_courseware_units(
    revision_id: str,
    text: str,
) -> list[ParsedResourceUnit]:
    units: list[ParsedResourceUnit] = []
    for index, block in enumerate(text.split("\n\n"), start=1):
        block = block.strip()
        if not block:
            continue
        units.append(ParsedResourceUnit(
            unit_id=f"{revision_id}-cw{index}",
            text=block,
            location=ResourceLocation(kind="slide", start=index, end=index),
        ))
    return units


def load_snapshot(snapshot_id: str) -> LoadedResources:
    """Resolve a snapshot into ParsedResource objects + a best-effort Course."""
    service = ProductService()
    snapshot = service.get_snapshot(snapshot_id)
    parsed_list: list[ParsedResource] = []
    course_obj: Any | None = None
    for revision_id in snapshot.resource_revision_ids:
        try:
            revision = service.get_revision(revision_id)
        except KeyError:
            logger.warning("snapshot %s missing revision %s", snapshot_id, revision_id)
            continue
        resource = service.get_resource(revision.resource_id)
        text_path = service.text_path_for(revision)
        raw_text = ""
        page_count = revision.page_count
        meta = dict(revision.metadata or {})
        kind = resource.kind or "text"
        units: list[ParsedResourceUnit] = []
        if text_path and text_path.exists():
            try:
                raw_text = text_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("failed to read text %s: %s", text_path, exc)
        if not raw_text and revision.metadata.get("source") == "upload":
            # The original blob is still on disk; re-parse on demand.
            blob = service.blob_path_for(revision)
            if blob and blob.exists():
                try:
                    parsed = parse_document(revision.filename, blob.read_bytes())
                    raw_text = parsed.text
                    page_count = parsed.page_count or page_count
                    meta.update(parsed.metadata or {})
                except Exception as exc:  # noqa: BLE001
                    logger.warning("re-parse failed for %s: %s", revision_id, exc)
        if kind == "transcript":
            units = _parse_zhiyun_transcript_units(revision_id, raw_text)
        elif resource.source_type == "zhiyun" and kind == "courseware":
            units = _zhiyun_courseware_units(revision_id, raw_text)
        else:
            units = _build_units_from_parsed_text(
                revision_id, raw_text, page_count=page_count, kind=kind,
            )
        if not units and raw_text:
            units = [ParsedResourceUnit(
                unit_id=f"{revision_id}-u1",
                text=raw_text,
                location=ResourceLocation(kind="section", start=0, end=len(raw_text)),
            )]
        parsed_list.append(ParsedResource(
            revision_id=revision_id,
            resource_id=resource.resource_id,
            kind=kind,
            source_type=resource.source_type,
            provider=resource.provider or "zhiyun",
            title=resource.title or revision.filename,
            units=units,
            raw_text=raw_text,
            page_count=page_count,
            meta={**meta, "filename": revision.filename, "source_ref": resource.source_ref},
        ))
        # Try to recover course info from any resource that carries it.
        if course_obj is None:
            cid = meta.get("course_id")
            cname = meta.get("course_name")
            if cid and cname:
                from coursebook_agent.models import Course
                course_obj = Course(
                    course_id=str(cid), name=cname,
                    teacher=meta.get("teacher"), term=meta.get("term"),
                )
    return LoadedResources(course=course_obj, resources=parsed_list)


def load_course_resources_from_zhiyun(
    course_id: str,
    *,
    include_courseware: bool = True,
) -> LoadedResources:
    """Legacy path: build ParsedResources from the in-repo Zhiyun cache.

    Used when the request did not come with a snapshot_id.  This path
    exists so the v2 pipeline can also drive non-product-workbench runs.
    """
    source = ZhiyunSource()
    course = source.get_course(course_id)
    lectures = source.list_lectures(course_id)
    parsed_list: list[ParsedResource] = []
    for lecture in lectures:
        transcript_path = source._cache_path(f"transcript-{lecture.lecture_id}")
        if transcript_path.exists():
            try:
                payload = json.loads(transcript_path.read_text(encoding="utf-8"))
                rows = payload.get("data", [])
                if isinstance(rows, dict):
                    rows = rows.get("segments", [])
                lines = []
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    s = int(row.get("start_sec", 0))
                    e = int(row.get("end_sec", 0))
                    lines.append(f"[{s}-{e}] {row.get('text', '').strip()}")
                raw_text = "\n".join(lines)
                units = _parse_zhiyun_transcript_units(lecture.lecture_id, raw_text)
                parsed_list.append(ParsedResource(
                    revision_id=f"zhiyun-transcript-{lecture.lecture_id}",
                    resource_id=f"zhiyun-lecture-{lecture.lecture_id}",
                    kind="transcript",
                    source_type="zhiyun",
                    provider="zhiyun",
                    title=f"{lecture.title}",
                    units=units,
                    raw_text=raw_text,
                    page_count=None,
                    meta={"lecture_id": lecture.lecture_id, "index": lecture.index},
                ))
            except (OSError, ValueError) as exc:
                logger.warning("transcript cache unreadable for %s: %s", lecture.lecture_id, exc)
        if include_courseware:
            cw_path = source._cache_path(f"courseware-{lecture.lecture_id}")
            if cw_path.exists():
                try:
                    payload = json.loads(cw_path.read_text(encoding="utf-8"))
                    rows = payload.get("data", [])
                    raw_text = "\n\n".join(
                        f"[第 {i} 页] {row.get('title', '')}\n{row.get('image_url', '')}"
                        for i, row in enumerate(rows, start=1)
                        if isinstance(row, dict)
                    )
                    units = _zhiyun_courseware_units(lecture.lecture_id, raw_text)
                    parsed_list.append(ParsedResource(
                        revision_id=f"zhiyun-courseware-{lecture.lecture_id}",
                        resource_id=f"zhiyun-cw-{lecture.lecture_id}",
                        kind="courseware",
                        source_type="zhiyun",
                        provider="zhiyun",
                        title=f"{lecture.title} · 课件",
                        units=units,
                        raw_text=raw_text,
                        page_count=len(rows),
                        meta={"lecture_id": lecture.lecture_id},
                    ))
                except (OSError, ValueError) as exc:
                    logger.warning("courseware cache unreadable for %s: %s", lecture.lecture_id, exc)
    return LoadedResources(course=course, resources=parsed_list)