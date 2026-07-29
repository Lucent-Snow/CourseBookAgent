"""Layer 3: Book-aware chapter generation.

Input: writer_system_prompt (from editor) + ChapterInstruction + full transcript chunks.
Output: LectureDraft with time links, components, and source grounding.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from coursebook_agent.agent.llm import LLMClient, LLMError
from coursebook_agent.models import (
    BookPlan,
    ChapterComponent,
    ChapterInstruction,
    ChapterSection,
    Lecture,
    LectureDraft,
    TimedChunk,
    format_timestamp,
)

SYSTEM = """你是高校课程教辅书的分章写作者。

你拿到的是：
1. 总编辑给你的共享写作规范
2. 总编辑对这一章的具体指令
3. 该讲的完整字幕

你的任务：把字幕整理成教辅书的一章，让读者（可能不太聪明的学生）能读懂。

关键规则：
- 只用字幕内容，不编造
- 核心方法要写清步骤、判定规则、适用条件
- 例题要完整展示解题过程
- 每个知识点标注来源（chunk_id + 时间段）
- 按总编辑定义的组件格式展示例题/Tips/警告
- 不写"根据字幕"等元话语"""


from coursebook_agent.config import config


def _chunks_to_source(chunks: list[TimedChunk]) -> str:
    return "\n\n".join(
        f"[{c.chunk_id} | {c.citation}]\n{c.text}"
        for c in chunks
    )


def _instruction_context(
    instruction: ChapterInstruction | None,
    plan: BookPlan | None,
    prev_draft: LectureDraft | None,
) -> str:
    parts = []
    if plan and plan.writer_system_prompt:
        parts.append(f"【总编辑写作规范】\n{plan.writer_system_prompt}")
    if instruction:
        parts.append(f"【本章指令】\n{json.dumps(instruction.model_dump(), ensure_ascii=False)}")
    if prev_draft:
        parts.append(f"【上一章摘要】\ntitle={prev_draft.title}\nbridge_to_next={prev_draft.bridge_to_next}\nkey_points={prev_draft.key_points[:5]}")
    return "\n\n".join(parts) if parts else "（无额外上下文）"


async def generate_chapter(
    lecture: Lecture,
    chunks: list[TimedChunk],
    client: LLMClient | None = None,
    *,
    review: bool = True,
    instruction: ChapterInstruction | None = None,
    plan: BookPlan | None = None,
    previous_draft: LectureDraft | None = None,
    # Legacy compat
    blueprint=None,
) -> LectureDraft:
    if not chunks:
        raise ValueError(f"讲次 {lecture.lecture_id} 没有可用字幕")

    llm = client or LLMClient(max_retries=3, timeout=max(150, config.timeout if hasattr(config, 'timeout') else 150))
    source = _chunks_to_source(chunks)
    context = _instruction_context(instruction, plan, previous_draft)

    target_title = instruction.book_title if instruction else (blueprint.book_title if blueprint else f"第 {lecture.index} 讲：{lecture.title}")
    role = instruction.chapter_role if instruction else (blueprint.chapter_role if blueprint else "core")
    valid_ids = {c.chunk_id for c in chunks}
    chunk_id_list = json.dumps(list(valid_ids))

    # Build component spec summary for the prompt
    component_specs = ""
    if plan and plan.components:
        component_specs = "\n".join(
            f"- {c.name}：{c.description}（字段：{', '.join(c.fields)}）" for c in plan.components
        )

    prompt = f"""{context}

字幕材料（共 {len(chunks)} 段，约 {sum(len(c.text) for c in chunks)} 字）：
{source}

可用 chunk_id：{chunk_id_list}

请生成章节 JSON：
{{
  "lecture_id": "{lecture.lecture_id}",
  "title": "{target_title}",
  "chapter_role": "{role}",
  "module_name": "{instruction.module_name if instruction else ''}",
  "overview": "150-240字，先定位本章在全书中的位置，再概括内容",
  "learning_goals": ["3-5条可检验的学习目标"],
  "key_points": ["4-7条重点"],
  "common_mistakes": ["2-5条易错点"],
  "bridge_from_prev": "承上一段，80-140字",
  "bridge_to_next": "启下一段，60-120字",
  "prerequisite_concepts": ["依赖的前序概念"],
  "concepts": ["概念名：课堂中的解释"],
  "sections": [
    {{
      "heading": "小节标题",
      "content": "3-5个自然段的讲义正文，写清步骤和判定",
      "source_chunk_ids": ["c001"],
      "emphasis": "key|normal|review",
      "time_links": ["05:30-12:40"],
      "components": [
        {{
          "component_type": "worked_example|tip_box|warning|procedure",
          "data": {{"title": "...", "body": "...", "source_ref": "c005@05:30"}}
        }}
      ]
    }}
  ],
  "examples": ["课堂例子及其说明"],
  "summary": ["3-6条小结"],
  "warnings": ["仅列影响理解且无法确认的ASR问题"],
  "transcript_links": [{{"label": "c005", "start_sec": 330, "end_sec": 760}}]
}}

组件规范：
{component_specs or '(无组件规范)'}

质量要求：
1. 读起来像教辅书的一章，让不懂的学生也能读懂。
2. 核心方法章：步骤、判定规则、适用条件必须写清楚。
3. sections 里每个 section 都要有有效 source_chunk_ids。
4. 每个 section 至少有 1 个 time_link。
5. 核心方法章必须有 procedure 组件。
6. 每章至少 1 个 worked_example 组件。"""

    data = await llm.complete_json(SYSTEM, prompt, max_tokens=20000)

    # Retry with narrower contract if first attempt fails
    if not isinstance(data, dict):
        narrow = prompt + "\n\n若上下文过长：sections 只写 4 节，每节 content 2 段。必须返回完整 JSON。"
        data = await LLMClient(max_retries=3, timeout=180).complete_json(SYSTEM, narrow, max_tokens=16000)

    # Review pass
    if review:
        data = await _review_pass(llm, data, instruction, chunks)

    # Normalize and validate
    data = _normalize(data, lecture, instruction, blueprint, role, target_title)
    draft = _validate_and_fix(data, chunks, instruction, blueprint, previous_draft)
    return draft


async def _review_pass(llm: LLMClient, data: dict, instruction: ChapterInstruction | None, chunks: list[TimedChunk]) -> dict:
    must_cover = instruction.must_cover if instruction else []
    try:
        review_result = await LLMClient(max_retries=1, timeout=min(60, llm.timeout)).complete_json(
            SYSTEM,
            f"审校以下讲义草稿，只返回 JSON：{{\"approved\": true, \"issues\": [...], \"missing_must_cover\": [...]}}\n\nmust_cover：{json.dumps(must_cover)}\n\n草稿：{json.dumps(data, ensure_ascii=False)[:8000]}",
            max_tokens=2000,
        )
        warnings = list(data.get("warnings") or [])
        for issue in review_result.get("issues") or []:
            if isinstance(issue, dict):
                warnings.append(f"审校：{issue.get('section', '整体')}：{issue.get('suggestion', issue.get('problem', ''))}")
        for item in review_result.get("missing_must_cover") or []:
            if str(item).strip():
                warnings.append(f"可能遗漏必覆盖点：{item}")
        data["warnings"] = warnings
    except LLMError:
        data.setdefault("warnings", []).append("自动审校超时，建议人工复核。")
    return data


def _normalize(data: dict, lecture, instruction, blueprint, role, target_title) -> dict:
    if not isinstance(data, dict):
        raise LLMError("章节结果不是对象")
    data.setdefault("lecture_id", lecture.lecture_id)
    data.setdefault("title", target_title)
    data.setdefault("chapter_role", role)
    data.setdefault("overview", "")
    data.setdefault("sections", [])
    data.setdefault("summary", [])
    data.setdefault("concepts", [])
    data.setdefault("examples", [])
    data.setdefault("warnings", [])
    data.setdefault("learning_goals", instruction.learning_goals if instruction else (blueprint.learning_goals if blueprint else []))
    data.setdefault("key_points", [])
    data.setdefault("common_mistakes", instruction.common_mistakes if instruction else [])
    data.setdefault("bridge_from_prev", instruction.bridge_from_prev if instruction else (blueprint.bridge_from_prev if blueprint else ""))
    data.setdefault("bridge_to_next", instruction.bridge_to_next if instruction else (blueprint.bridge_to_next if blueprint else ""))
    data.setdefault("prerequisite_concepts", instruction.prerequisite_concepts if instruction else (blueprint.prerequisite_concepts if blueprint else []))
    data.setdefault("module_name", instruction.module_name if instruction else (blueprint.module_name if blueprint else ""))
    data.setdefault("transcript_links", [])

    sections = []
    for item in data.get("sections") or []:
        if not isinstance(item, dict):
            continue
        sections.append({
            "heading": str(item.get("heading") or "未命名小节"),
            "content": str(item.get("content") or ""),
            "source_chunk_ids": [str(x) for x in (item.get("source_chunk_ids") or [])],
            "emphasis": str(item.get("emphasis") or "normal"),
            "time_links": [str(x) for x in (item.get("time_links") or [])],
            "components": [dict(c) for c in (item.get("components") or []) if isinstance(c, dict)],
        })
    data["sections"] = sections

    for key in ("learning_goals", "key_points", "common_mistakes", "concepts", "examples", "summary", "warnings", "prerequisite_concepts"):
        value = data.get(key)
        if isinstance(value, str):
            data[key] = [value]
        elif not isinstance(value, list):
            data[key] = []
        else:
            data[key] = [str(x) for x in value if str(x).strip()]

    return data


def _validate_and_fix(data: dict, chunks: list[TimedChunk], instruction, blueprint, previous_draft) -> LectureDraft:
    valid_ids = {c.chunk_id for c in chunks}

    try:
        draft = LectureDraft.model_validate(data)
    except ValidationError as exc:
        raise LLMError(f"讲义 JSON 结构不符合约定: {exc}") from exc

    if len(draft.sections) < 2:
        raise LLMError(f"讲义小节数量异常: {len(draft.sections)}")
    if len(draft.overview.strip()) < 60:
        draft.warnings.append("本章导读偏短。")

    # Fix source_chunk_ids and time_links
    for section in draft.sections:
        section.source_chunk_ids = [x for x in section.source_chunk_ids if x in valid_ids]
        if not section.source_chunk_ids:
            section.source_chunk_ids = [chunks[0].chunk_id]
            draft.warnings.append(f"小节“{section.heading}”原引用无效，已回退。")
        if section.emphasis not in {"normal", "key", "review"}:
            section.emphasis = "normal"

    # Ensure teaching-aid fields
    if not draft.key_points:
        draft.key_points = draft.summary[:5]
    if not draft.learning_goals and instruction:
        draft.learning_goals = instruction.learning_goals
    if not draft.learning_goals and blueprint:
        draft.learning_goals = blueprint.learning_goals
    if not draft.bridge_from_prev and previous_draft and previous_draft.bridge_to_next:
        draft.bridge_from_prev = previous_draft.bridge_to_next
    if not draft.bridge_from_prev and instruction:
        draft.bridge_from_prev = instruction.bridge_from_prev
    if not draft.bridge_to_next and instruction:
        draft.bridge_to_next = instruction.bridge_to_next

    draft = _apply_statistical_guardrails(draft)
    draft.source_ranges = _collect_ranges(draft.sections, chunks)
    draft.transcript_links = _build_transcript_links(draft.sections, chunks)
    return draft


def _apply_statistical_guardrails(draft: LectureDraft) -> LectureDraft:
    replacements = {
        "判断标准（β）": "判别标准", "判断标准(β)": "判别标准",
        "接受错误H0": "未能拒绝错误H0", "接受错误 H0": "未能拒绝错误 H0",
        "却接受它": "却未能拒绝它", "研究假设不成立": "研究假设未获支持",
        "接受虚无假设": "未拒绝虚无假设",
        "从而推得研究假设成立": "从而为研究假设提供支持",
        "则研究假设得以成立": "则研究假设获得支持",
        "证明隐性歧视存在": "为隐性歧视提供支持",
        "落在α对应的临界区域之外": "落在α对应的临界区域内",
        "np或nq≥5": "np和nq均≥5", "签到占%（": "签到纳入考核（",
    }

    def clean(v: str) -> str:
        for old, new in replacements.items():
            v = v.replace(old, new)
        return v

    draft.overview = clean(draft.overview)
    draft.bridge_from_prev = clean(draft.bridge_from_prev)
    draft.bridge_to_next = clean(draft.bridge_to_next)
    draft.concepts = [clean(x) for x in draft.concepts]
    draft.examples = [clean(x) for x in draft.examples]
    draft.summary = [clean(x) for x in draft.summary]
    draft.learning_goals = [clean(x) for x in draft.learning_goals]
    draft.key_points = [clean(x) for x in draft.key_points]
    draft.common_mistakes = [clean(x) for x in draft.common_mistakes]
    for s in draft.sections:
        s.heading = clean(s.heading)
        s.content = clean(s.content)
    return draft


def _collect_ranges(sections: list[ChapterSection], chunks: list[TimedChunk]) -> list[str]:
    by_id = {c.chunk_id: c for c in chunks}
    seen: set[str] = set()
    result: list[str] = []
    for section in sections:
        selected = [by_id[x] for x in section.source_chunk_ids if x in by_id]
        if not selected:
            continue
        citation = f"{section.heading}：字幕 {format_timestamp(selected[0].start_sec)}–{format_timestamp(selected[-1].end_sec)}"
        if citation not in seen:
            seen.add(citation)
            result.append(citation)
    return result


def _build_transcript_links(sections: list[ChapterSection], chunks: list[TimedChunk]) -> list[dict]:
    by_id = {c.chunk_id: c for c in chunks}
    links = []
    seen = set()
    for section in sections:
        for cid in section.source_chunk_ids:
            if cid in by_id and cid not in seen:
                seen.add(cid)
                c = by_id[cid]
                links.append({"label": cid, "start_sec": c.start_sec, "end_sec": c.end_sec})
    return links


# Need config import at module level
from coursebook_agent.config import config
