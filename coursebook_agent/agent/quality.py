"""Quality gates for chapter drafts.

Extracted from the former v2 pilot so the main pipeline can enforce the same
traceable quality contract: deterministic checks plus an evidence-grounded LLM
reviewer. A chapter is accepted only when both pass.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from coursebook_agent.agent.llm import LLMClient, LLMError
from coursebook_agent.models import ChapterInstruction, LectureDraft, TimedChunk

KNOWN_COMPONENTS = {"worked_example", "tip_box", "warning", "side_note", "procedure"}
COMPONENT_ALIASES = {"tipped_box": "tip_box", "tips_box": "tip_box", "example": "worked_example"}


class TermEntry(BaseModel):
    term: str
    aliases: list[str] = Field(default_factory=list)
    category: str = ""


class CourseProfile(BaseModel):
    course_id: str
    profile_version: str = "v2"
    subject: str
    course_theme: str
    audience: str
    teaching_goal: str
    canonical_terms: list[TermEntry] = Field(default_factory=list)
    asr_policy: str = "保守可追溯：只有术语表别名与上下文一致时才能标准化；不确定的数值、公式、人名不得猜测。"
    chapter_templates: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def prompt_context(self) -> str:
        terms = "\n".join(
            f"- {x.term}（可能转写：{'、'.join(x.aliases) or '无'}；{x.category}）" for x in self.canonical_terms
        )
        templates = json.dumps(self.chapter_templates, ensure_ascii=False)
        return f"""【课程编辑配置（必须服从）】
课程主题：{self.course_theme}
学科：{self.subject}
读者：{self.audience}
教学目标：{self.teaching_goal}
ASR 处理原则：{self.asr_policy}

标准术语表：
{terms}

章节类型模板（章节的 section 数、字数、必备组件和结构均按此执行）：
{templates}

严格禁令：不得用学科常识补造课堂未能确认的数值、公式、人名或结果；术语表不能支持的可疑 ASR 必须在 warnings 标注，而不是静默改写。"""


@dataclass
class Correction:
    chunk_id: str
    raw: str
    normalized: str
    reason: str
    confidence: str = "high"


@dataclass
class QualityResult:
    accepted: bool
    issues: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def load_profile(path: str | Path) -> CourseProfile:
    return CourseProfile.model_validate_json(Path(path).read_text(encoding="utf-8"))


def normalize_chunks(chunks: list[TimedChunk], profile: CourseProfile) -> tuple[list[TimedChunk], list[Correction]]:
    """Apply only explicit profile aliases; never overwrite the raw cache."""
    aliases: list[tuple[str, str]] = []
    for entry in profile.canonical_terms:
        for alias in entry.aliases:
            if alias and alias != entry.term:
                aliases.append((alias, entry.term))
    aliases.sort(key=lambda pair: len(pair[0]), reverse=True)
    corrections: list[Correction] = []
    result: list[TimedChunk] = []
    for chunk in chunks:
        text = chunk.text
        for raw, normalized in aliases:
            if raw in text:
                text = text.replace(raw, normalized)
                corrections.append(Correction(chunk.chunk_id, raw, normalized, "profile canonical-term alias"))
        result.append(chunk.model_copy(update={"text": text}))
    return result, corrections


def template_for(role: str, profile: CourseProfile) -> dict[str, Any]:
    return profile.chapter_templates.get(role) or profile.chapter_templates.get("core") or {}


def enforce_component_contract(draft: LectureDraft) -> LectureDraft:
    """Make known, safely repairable component deviations explicit and renderable."""
    for section in draft.sections:
        repaired = []
        for component in section.components:
            component.component_type = COMPONENT_ALIASES.get(component.component_type, component.component_type)
            if component.component_type not in KNOWN_COMPONENTS:
                draft.warnings.append(f"未知组件类型：{component.component_type}")
                continue
            data = component.data
            if not data.get("body"):
                parts = []
                for key in ("problem", "steps", "conclusion", "description", "example"):
                    value = data.get(key)
                    if isinstance(value, list):
                        parts.extend(str(v) for v in value)
                    elif value:
                        parts.append(str(value))
                if parts:
                    data["body"] = "\n".join(parts)
            repaired.append(component)
        section.components = repaired
    return draft


def _dict_example_to_text(item: Any) -> str:
    if isinstance(item, str) and item.lstrip().startswith("{"):
        try:
            parsed = ast.literal_eval(item)
            if isinstance(parsed, dict):
                item = parsed
        except (SyntaxError, ValueError):
            pass
    if not isinstance(item, dict):
        return str(item).strip()
    title = str(item.get("title") or item.get("example") or "课堂例子").strip()
    body = str(item.get("description") or item.get("body") or item.get("problem") or "").strip()
    refs = item.get("source_chunk_ids") or []
    suffix = f"（来源：{', '.join(map(str, refs))}）" if refs else ""
    return "：".join(x for x in (title, body) if x) + suffix


def sanitize_examples(draft: LectureDraft) -> LectureDraft:
    draft.examples = [_dict_example_to_text(x) for x in draft.examples if str(x).strip()]
    return draft


def traceability_metrics(draft: LectureDraft, chunks: list[TimedChunk]) -> dict[str, Any]:
    """Summarize whether chapter sections point to real transcript evidence."""
    known_chunk_ids = {chunk.chunk_id for chunk in chunks}
    total_sections = len(draft.sections)
    sections_with_sources = sum(bool(section.source_chunk_ids) for section in draft.sections)
    referenced_ids = {
        chunk_id
        for section in draft.sections
        for chunk_id in section.source_chunk_ids
    }
    valid_referenced_ids = referenced_ids & known_chunk_ids
    invalid_referenced_ids = referenced_ids - known_chunk_ids
    return {
        "total_sections": total_sections,
        "sections_with_sources": sections_with_sources,
        "source_coverage": round(sections_with_sources / total_sections, 3) if total_sections else 0.0,
        "referenced_chunks": len(referenced_ids),
        "valid_referenced_chunks": len(valid_referenced_ids),
        "invalid_referenced_chunks": len(invalid_referenced_ids),
    }


def deterministic_quality_gate(
    draft: LectureDraft,
    instruction: ChapterInstruction,
    profile: CourseProfile,
    chunks: list[TimedChunk] | None = None,
) -> QualityResult:
    template = template_for(instruction.chapter_role, profile)
    text_chars = sum(len(section.content.strip()) for section in draft.sections)
    component_types = [c.component_type for section in draft.sections for c in section.components]
    issues: list[str] = []
    metrics = {"sections": len(draft.sections), "body_chars": text_chars, "components": component_types}
    if chunks:
        metrics["traceability"] = traceability_metrics(draft, chunks)
    min_sections, max_sections = template.get("section_range", [2, 12])
    min_chars, max_chars = template.get("body_chars", [800, 8000])
    if not min_sections <= len(draft.sections) <= max_sections:
        issues.append(f"小节数 {len(draft.sections)} 不符合模板 {min_sections}-{max_sections}")
    if not min_chars <= text_chars <= max_chars:
        issues.append(f"正文 {text_chars} 字不符合模板 {min_chars}-{max_chars}")
    for section in draft.sections:
        if not section.source_chunk_ids:
            issues.append(f"小节“{section.heading}”没有来源")
        if not section.time_links:
            issues.append(f"小节“{section.heading}”没有时间段")
        if chunks:
            known_chunk_ids = {chunk.chunk_id for chunk in chunks}
            unknown_refs = sorted(set(section.source_chunk_ids) - known_chunk_ids)
            if unknown_refs:
                issues.append(
                    f"小节“{section.heading}”引用了不存在的字幕块：{', '.join(unknown_refs)}"
                )
    if chunks:
        max_end = max(chunk.end_sec for chunk in chunks)
        for source_range in draft.source_ranges:
            matched = re.findall(r"(?:(\d{2}):)?(\d{2}):(\d{2})", source_range)
            if len(matched) >= 2:
                hours, minutes, seconds = matched[-1]
                end_sec = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
                if end_sec > max_end:
                    issues.append(f"来源时间超出视频范围：{source_range}")
    required = set(template.get("required_components", []))
    missing = required - set(component_types)
    if missing:
        issues.append(f"缺少必备组件：{', '.join(sorted(missing))}")
    if any(example.lstrip().startswith("{") for example in draft.examples):
        issues.append("课堂例子含未解析 JSON 对象")
    if not draft.learning_goals or not draft.common_mistakes:
        issues.append("缺少学习目标或易错点")
    return QualityResult(not issues, issues, metrics)


async def llm_quality_gate(
    draft: LectureDraft,
    instruction: ChapterInstruction,
    profile: CourseProfile,
    chunks: list[TimedChunk],
) -> QualityResult:
    """Evidence-grounded reviewer. It can reject but never silently approve omissions."""
    evidence = "\n".join(f"[{c.chunk_id}] {c.text}" for c in chunks)
    prompt = f"""你是严格的高校教辅质检编辑。根据课程配置、章节合同、字幕证据，判断草稿是否允许进入成书。

{profile.prompt_context()}

章节合同：{instruction.model_dump_json()}

字幕证据：{evidence}

草稿：{draft.model_dump_json()}

只返回 JSON：
{{"status":"pass|revise|human_review","issues":["可执行问题"],"missing_must_cover":["遗漏项"],"unsupported_claims":["无字幕支持的具体主张"],"asr_uncertainties":["需人工确认项"]}}

规则：must_cover 任一项缺失即 revise；不能确认的数值、公式、专名不能批准为确定事实；不要以文笔好为由忽略覆盖问题。"""
    try:
        response = await LLMClient(max_retries=2, timeout=180).complete_json(
            "你是只依据提供证据审校的编辑。只输出 JSON。", prompt, max_tokens=5000
        )
    except LLMError as exc:
        return QualityResult(False, [f"LLM 审校失败：{exc}"], {"review_status": "failed"})
    issues = [str(x) for key in ("issues", "missing_must_cover", "unsupported_claims") for x in (response.get(key) or []) if str(x).strip()]
    status = str(response.get("status", "revise"))
    if response.get("asr_uncertainties"):
        issues.extend(f"ASR 待人工确认：{x}" for x in response["asr_uncertainties"])
        status = "human_review"
    return QualityResult(status == "pass" and not issues, issues, {"review_status": status, "raw": response})
