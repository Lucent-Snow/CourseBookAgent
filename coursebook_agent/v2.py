"""Versioned v2 generation workflow.

V2 keeps source data immutable, writes every derived artifact to an isolated run
folder, and treats a chapter as accepted only after deterministic and LLM review.
"""

from __future__ import annotations

import asyncio
import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from coursebook_agent.agent.chapter import generate_chapter
from coursebook_agent.agent.digest import compress_lecture
from coursebook_agent.agent.editor import plan_book
from coursebook_agent.agent.llm import LLMClient, LLMError
from coursebook_agent.agent.synthesize import synthesize_book
from coursebook_agent.config import config
from coursebook_agent.models import BookPlan, ChapterInstruction, CourseBook, KnowledgePoint, Lecture, LectureDigest, LectureDraft, TimedChunk
from coursebook_agent.preprocess.transcript import chunk_segments, clean_segments
from coursebook_agent.renderer.markdown import render_chapter, render_coursebook
from coursebook_agent.sources.zhiyun import ZhiyunSource

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
                    if data.get(key):
                        parts.append(str(data[key]))
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


@dataclass
class QualityResult:
    accepted: bool
    issues: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def deterministic_quality_gate(draft: LectureDraft, instruction: ChapterInstruction, profile: CourseProfile, chunks: list[TimedChunk] | None = None) -> QualityResult:
    template = template_for(instruction.chapter_role, profile)
    text_chars = sum(len(section.content.strip()) for section in draft.sections)
    component_types = [c.component_type for section in draft.sections for c in section.components]
    issues: list[str] = []
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
    metrics = {"sections": len(draft.sections), "body_chars": text_chars, "components": component_types}
    return QualityResult(not issues, issues, metrics)


async def llm_quality_gate(
    draft: LectureDraft, instruction: ChapterInstruction, profile: CourseProfile, chunks: list[TimedChunk]
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


class V2Pipeline:
    def __init__(self, profile: CourseProfile, run_id: str | None = None, source: ZhiyunSource | None = None):
        self.profile = profile
        self.source = source or ZhiyunSource()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = run_id or f"{profile.course_id}-{profile.profile_version}-{stamp}"
        self.run_dir = config.data_dir / "runs" / self.run_id
        for name in ("raw", "normalized", "digests", "plan", "chapters", "review", "output", "report"):
            (self.run_dir / name).mkdir(parents=True, exist_ok=True)
        (self.run_dir / "profile.json").write_text(profile.model_dump_json(indent=2), encoding="utf-8")

    def _write_json(self, subdir: str, name: str, data: Any) -> Path:
        path = self.run_dir / subdir / name
        if hasattr(data, "model_dump_json"):
            path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
        else:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    async def _fresh_material(self, lecture: Lecture) -> tuple[list[TimedChunk], list[TimedChunk], list[Correction]]:
        segments = await asyncio.to_thread(self.source.get_transcript, lecture, False)
        raw = chunk_segments(clean_segments(segments))
        normalized, corrections = normalize_chunks(raw, self.profile)
        self._write_json("raw", f"chunks-{lecture.lecture_id}.json", [x.model_dump() for x in raw])
        self._write_json("normalized", f"chunks-{lecture.lecture_id}.json", [x.model_dump() for x in normalized])
        self._write_json("normalized", f"corrections-{lecture.lecture_id}.json", [x.__dict__ for x in corrections])
        return raw, normalized, corrections

    async def build_plan(self, lectures: list[Lecture]) -> BookPlan:
        digests = []
        for lecture in lectures:
            _, chunks, _ = await self._fresh_material(lecture)
            try:
                digest = await self._retry_stage(
                    f"第 {lecture.index} 讲 Digest",
                    lambda: compress_lecture(lecture, chunks, client=LLMClient(max_retries=3, timeout=180)),
                )
            except LLMError as exc:
                # The artifact is still fresh and traceable: this fallback never
                # reads old chapter/digest caches. It keeps planning alive when a
                # gateway repeatedly refuses a large structured response.
                digest = self._evidence_digest(lecture, chunks, str(exc))
            self._write_json("digests", f"digest-{lecture.lecture_id}.json", digest)
            digests.append(digest)
        course = await asyncio.to_thread(self.source.get_course, self.profile.course_id, False)
        plan = await self._retry_stage(
            "总编辑蓝图",
            lambda: plan_book(course, digests, client=LLMClient(max_retries=3, timeout=180), profile_context=self.profile.prompt_context()),
        )
        missing = []
        if not plan.components:
            missing.append("components")
        if not plan.writer_system_prompt:
            missing.append("writer_system_prompt")
        # Per-chapter component usage and depth are deterministically supplied by
        # the versioned profile below, so they do not depend on model compliance.
        if missing:
            raise LLMError(f"V2 总编辑蓝图缺少必填字段：{', '.join(missing)}；拒绝使用回退蓝图")
        for chapter in plan.chapters:
            template = template_for(chapter.chapter_role, self.profile)
            chapter.depth_guidance = json.dumps(template, ensure_ascii=False)
            chapter.component_usage = list(template.get("required_components", []))
            if not chapter.common_mistakes:
                chapter.common_mistakes = ["不要把未拒绝原假设写成证明原假设", "不满足前提时不得直接套用方法"]
        self._write_json("plan", "bookplan.json", plan)
        return plan

    def _evidence_digest(self, lecture: Lecture, chunks: list[TimedChunk], error: str) -> LectureDigest:
        selected = chunks[: min(12, len(chunks))]
        points = [
            KnowledgePoint(
                name=f"课堂片段 {chunk.chunk_id}",
                description=chunk.text[:420],
                category="evidence",
                chunk_refs=[chunk.chunk_id],
                time_refs=[chunk.citation],
            )
            for chunk in selected
        ]
        return LectureDigest(
            lecture_id=lecture.lecture_id, index=lecture.index, raw_title=lecture.title,
            teacher_flow="Digest 模型调用失败；总编辑须依据以下新鲜字幕证据与课程 Profile 保守规划。",
            knowledge_points=points,
            key_examples=[f"{chunk.chunk_id}：{chunk.text[:180]}" for chunk in selected],
            chunk_count=len(chunks), total_chars=sum(len(chunk.text) for chunk in chunks),
            asr_quality_notes=[f"V2 Digest LLM 失败，使用可追溯证据摘要：{error}"],
        )

    async def _retry_stage(self, label: str, operation, attempts: int = 2):
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                return await operation()
            except LLMError as exc:
                last_error = exc
                if attempt < attempts:
                    await asyncio.sleep(2 * attempt)
        raise LLMError(f"{label} 在 {attempts} 次完整尝试后失败：{last_error}") from last_error

    async def generate_pilot(self, indices: list[int], max_attempts: int = 2) -> dict[str, Any]:
        lectures = await asyncio.to_thread(self.source.list_lectures, self.profile.course_id, False)
        selected = [lecture for lecture in lectures if lecture.index in set(indices)]
        if len(selected) != len(indices):
            raise ValueError("试点讲次不存在")
        # A pilot deliberately plans only the sampled chapter types. This keeps the
        # first experiment focused; the production v2 command will plan all lectures.
        plan = await self.build_plan(selected)
        accepted: list[LectureDraft] = []
        results: list[dict[str, Any]] = []
        previous = None
        for lecture in selected:
            instruction = next(item for item in plan.chapters if item.lecture_id == lecture.lecture_id)
            _, chunks, corrections = await self._fresh_material(lecture)
            feedback: list[str] = []
            final_review: dict[str, Any] = {}
            draft = None
            for attempt in range(1, max_attempts + 1):
                try:
                    draft = await generate_chapter(
                        lecture, chunks, client=LLMClient(max_retries=3, timeout=180), review=False,
                        instruction=instruction, plan=plan, previous_draft=previous,
                        revision_feedback=feedback,
                    )
                except LLMError as exc:
                    feedback = [f"上一稿生成失败：{exc}", "必须返回至少两个带来源的小节和完整 JSON。"]
                    final_review = {"attempt": attempt, "generation_error": str(exc)}
                    continue
                draft = sanitize_examples(enforce_component_contract(draft))
                deterministic = deterministic_quality_gate(draft, instruction, self.profile, chunks)
                semantic = await llm_quality_gate(draft, instruction, self.profile, chunks)
                final_review = {"attempt": attempt, "deterministic": deterministic.__dict__, "semantic": semantic.__dict__}
                if deterministic.accepted and semantic.accepted:
                    break
                feedback = deterministic.issues + semantic.issues
            accepted_flag = bool(
                draft is not None
                and final_review.get("deterministic", {}).get("accepted")
                and final_review.get("semantic", {}).get("accepted")
            )
            if draft is not None:
                self._write_json("chapters", f"chapter-{lecture.index:02d}-{lecture.lecture_id}.json", draft)
                (self.run_dir / "output" / f"lecture-{lecture.index:02d}-{lecture.lecture_id}.md").write_text(render_chapter(draft), encoding="utf-8")
            self._write_json("review", f"chapter-{lecture.index:02d}-{lecture.lecture_id}.json", final_review)
            results.append({"index": lecture.index, "lecture_id": lecture.lecture_id, "accepted": accepted_flag, "corrections": len(corrections), **final_review})
            if accepted_flag:
                accepted.append(draft)
                previous = draft
        report = {
            "run_id": self.run_id, "profile_version": self.profile.profile_version, "indices": indices,
            "accepted": sum(1 for x in results if x["accepted"]), "rejected": sum(1 for x in results if not x["accepted"]),
            "results": results,
        }
        self._write_json("report", "pilot-quality-report.json", report)
        return report


def profile_fingerprint(profile: CourseProfile) -> str:
    return hashlib.sha256(profile.model_dump_json().encode()).hexdigest()[:12]
