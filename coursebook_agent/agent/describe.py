"""Per-resource description generator.

The description is the unit that the main Agent actually reads before
planning chapters and assigning resource Tags. It must therefore be:

1. short (cheap to aggregate into one prompt);
2. factual about *what is in the resource* and *how it relates to other
   resources*, not about user value;
3. free of hallucinations: when the LLM call fails, fall back to a
   deterministic extraction from the parsed units so the workflow can
   still run.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path

from coursebook_agent.agent.llm import LLMClient, extract_json_object, LLMError
from coursebook_agent.config import config
from coursebook_agent.models import (
    ParsedResource,
    ResourceDescription,
)

logger = logging.getLogger(__name__)


SYSTEM = """你是一名高校课程资料编目员。

你的任务是阅读一份资料（可能是字幕、PPT、PDF、DOCX、教学大纲等），输出一段严格 JSON，用于让主 Agent 在不直接阅读原文的情况下，准确判断这份资料的内容、覆盖范围与适合的用法。

字段说明：
- topic：用一两句话概括资料的主题。
- knowledge_topics：覆盖到的关键知识点或章节名（数组，最多 12 项）。
- scope：资料覆盖范围，取值 "course" / "module" / "lecture" / "topic"。
- usable_content_kinds：资料中实际包含的内容类型，可多选：definition | derivation | example | procedure | exercise | policy。
- suggested_role：建议主 Agent 如何使用这份资料，取值 primary | global_constraint | auxiliary | ignore。
- summary：3-5 句话描述资料内容；不允许编造原文未出现的事实。
- overlap_notes：与其他资料可能重复或互补的地方（数组，最多 4 项）。

不要返回 Markdown，只返回 JSON。"""

# Quick heuristics for Chinese "大纲/教学大纲/课程安排/教学要求" → scope=course.
_COURSE_KEYWORDS = ("教学大纲", "课程大纲", "课程安排", "教学要求", "syllabus", "教学日历")
_TOPIC_KEYWORDS = ("补充", "扩展", "练习", "习题", "复习", "总结", "复习提纲")


def _looks_like_course_scope(title: str, raw_text: str) -> bool:
    text = (title + "\n" + raw_text[:2000]).lower()
    return any(kw.lower() in text for kw in _COURSE_KEYWORDS)


def _looks_like_topic_supplement(title: str, raw_text: str) -> bool:
    text = (title + "\n" + raw_text[:2000]).lower()
    return any(kw.lower() in text for kw in _TOPIC_KEYWORDS)


def _extract_candidate_terms(text: str, k: int = 12) -> list[str]:
    """Cheap deterministic extraction of candidate knowledge topics."""
    if not text:
        return []
    # Prefer CJK runs of length >= 2; fall back to latin words.
    cjk = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
    counts = Counter(cjk)
    out: list[str] = []
    seen: set[str] = set()
    for term, _ in counts.most_common():
        if term in seen:
            continue
        # Skip ultra-common stopwords.
        if term in {"我们", "可以", "一个", "什么", "这里", "因此", "所以", "但是"}:
            continue
        seen.add(term)
        out.append(term)
        if len(out) >= k:
            break
    if not out:
        words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", text)
        for w in Counter(words).most_common(k):
            out.append(w[0])
            if len(out) >= k:
                break
    return out


def _build_payload(parsed: ParsedResource) -> dict:
    head_units = parsed.units[:8]
    units_payload = [
        {
            "unit_id": u.unit_id,
            "text": u.text[:280],
            "location": u.location.model_dump() if u.location else None,
        }
        for u in head_units
    ]
    return {
        "kind": parsed.kind,
        "source_type": parsed.source_type,
        "provider": parsed.provider,
        "title": parsed.title,
        "page_count": parsed.page_count,
        "unit_count": len(parsed.units),
        "raw_text_excerpt": parsed.raw_text[:2400],
        "head_units": units_payload,
    }


async def describe_resource(
    parsed: ParsedResource,
    *,
    client: LLMClient | None = None,
) -> ResourceDescription:
    """Generate one resource description; fall back deterministically on failure.

    Transcripts are described heuristically because:
    1. their content is dense and the LLM description adds little signal;
    2. the heuristic captures scope=lecture, role=primary, and topic =
       the lecture title, which is what the main Agent actually needs.
    """

    # Fast path: transcripts skip the LLM (avoid blowing the input budget).
    if parsed.kind == "transcript":
        return _heuristic_description_obj(parsed)

    payload = _build_payload(parsed)
    user = (
        "请为以下课程资料生成描述 JSON。\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    data: dict | None = None
    if parsed.raw_text:
        llm = client or LLMClient(max_retries=2, timeout=120)
        try:
            raw = await llm.complete(SYSTEM, user, max_tokens=2000, temperature=0.1)
            data = extract_json_object(raw)
            if not isinstance(data, dict) or "topic" not in data:
                # Try one repair pass.
                repair_user = (
                    "把以下输出整理为一个合法 JSON 对象，字段必须包含 topic / knowledge_topics / scope / usable_content_kinds / suggested_role / summary。只输出 JSON。\n\n"
                    f"原始任务：\n{user[:4000]}\n\n模型输出：\n{raw[:6000]}"
                )
                repair = await llm.complete(
                    "你是 JSON 生成器。只输出一个合法 JSON 对象。",
                    repair_user,
                    max_tokens=2000, temperature=0,
                )
                data = extract_json_object(repair)
        except (LLMError, ValueError, KeyError, TypeError) as exc:
            logger.warning("describe_resource(%s) LLM failed: %s; using heuristic", parsed.revision_id, exc)
    if not isinstance(data, dict):
        data = _heuristic_description(parsed, reason="llm_failed")
    return _coerce(parsed, data)


def _heuristic_description(parsed: ParsedResource, reason: str = "llm_failed") -> dict:
    text = parsed.raw_text or " ".join(u.text for u in parsed.units[:20])
    topic = (parsed.title or "").strip()
    if not topic and text:
        topic = text.splitlines()[0][:60].strip()
    terms = _extract_candidate_terms(text, k=10)
    if _looks_like_course_scope(parsed.title, text):
        scope = "course"
        suggested_role = "global_constraint"
        usable = ["policy"]
    elif _looks_like_topic_supplement(parsed.title, text):
        scope = "topic"
        suggested_role = "auxiliary"
        usable = ["example", "exercise"]
    elif parsed.kind == "transcript":
        scope = "lecture"
        suggested_role = "primary"
        usable = ["definition", "example"]
    else:
        scope = "topic"
        suggested_role = "primary"
        usable = ["definition"]
    return {
        "topic": topic,
        "knowledge_topics": terms,
        "scope": scope,
        "usable_content_kinds": usable,
        "suggested_role": suggested_role,
        "summary": (
            f"{parsed.kind} 资料，共 {len(parsed.units)} 个结构单元，"
            f"约 {len(text)} 字符。"
            + ("" if reason == "transcript_fast_path" else "（本描述由本地规则生成，因模型调用失败）")
        ),
        "overlap_notes": [],
    }


def _heuristic_description_obj(parsed: ParsedResource) -> ResourceDescription:
    return _coerce(parsed, _heuristic_description(parsed, reason="transcript_fast_path"))


def _coerce(parsed: ParsedResource, data: dict) -> ResourceDescription:
    topic = str(data.get("topic") or parsed.title or "").strip()
    knowledge = [str(x).strip() for x in (data.get("knowledge_topics") or []) if str(x).strip()]
    scope = str(data.get("scope") or "topic")
    if scope not in {"course", "module", "lecture", "topic"}:
        scope = "topic"
    usable = [str(x).strip() for x in (data.get("usable_content_kinds") or []) if str(x).strip()]
    suggested = str(data.get("suggested_role") or "auxiliary")
    if suggested not in {"primary", "global_constraint", "auxiliary", "ignore"}:
        suggested = "auxiliary"
    summary = str(data.get("summary") or "").strip()
    overlap = [str(x).strip() for x in (data.get("overlap_notes") or []) if str(x).strip()]
    return ResourceDescription(
        revision_id=parsed.revision_id,
        resource_id=parsed.resource_id,
        kind=parsed.kind,
        source_type=parsed.source_type,
        provider=parsed.provider,
        title=parsed.title,
        topic=topic,
        knowledge_topics=knowledge,
        scope=scope,
        related_lecture_ids=[],
        usable_content_kinds=usable,
        suggested_role=suggested,
        summary=summary,
        overlap_notes=overlap,
    )


def cache_path_for(cache_dir: Path, revision_id: str) -> Path:
    return cache_dir / f"description-{revision_id}.json"


async def describe_with_cache(
    parsed: ParsedResource,
    *,
    cache_dir: Path,
    client: LLMClient | None = None,
) -> ResourceDescription:
    path = cache_path_for(cache_dir, parsed.revision_id)
    if path.exists():
        try:
            return ResourceDescription.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    desc = await describe_resource(parsed, client=client)
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(desc.model_dump_json(indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("describe cache write failed for %s: %s", parsed.revision_id, exc)
    return desc