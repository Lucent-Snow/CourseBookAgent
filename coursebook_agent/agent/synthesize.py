"""Layer 4: Book-level synthesizer."""

from __future__ import annotations

import json

from coursebook_agent.agent.llm import LLMClient
from coursebook_agent.models import BookPlan, ChapterInstruction, Course, CourseBook, LectureDraft


SYSTEM = """你是教辅书终审编辑。把多章讲义合成为一本连贯的书。

规则：
1. 不新增课堂未出现的知识点。
2. 可以重写前言、使用说明、知识地图、章首衔接提示。
3. 对章节正文只做必要的术语统一与轻微衔接修补。
4. 术语必须全课一致。
5. 只返回 JSON。"""


async def synthesize_book(
    course: Course,
    chapters: list[LectureDraft],
    plan: BookPlan | None = None,
    client: LLMClient | None = None,
) -> CourseBook:
    llm = client or LLMClient(max_retries=2, timeout=120)
    compact = []
    for ch in chapters:
        compact.append({
            "lecture_id": ch.lecture_id,
            "title": ch.title,
            "module_name": ch.module_name,
            "chapter_role": ch.chapter_role,
            "overview": ch.overview,
            "learning_goals": ch.learning_goals,
            "key_points": ch.key_points,
            "common_mistakes": ch.common_mistakes,
            "concepts": ch.concepts[:10],
            "summary": ch.summary,
            "bridge_from_prev": ch.bridge_from_prev,
            "bridge_to_next": ch.bridge_to_next,
        })

    plan_data = plan.model_dump() if plan else {}
    prompt = f"""基于全书蓝图与各章摘要，生成合成层。

返回 JSON：
{{
  "title": "书名",
  "preface": "800-1200字前言",
  "how_to_use": ["使用建议"],
  "knowledge_map": ["模块/主线说明"],
  "learning_path": ["建议复习路径"],
  "glossary": ["术语：释义，40-80条"],
  "key_point_index": ["【模块/章】要点"],
  "continuity_notes": ["衔接风险与阅读提示"],
  "chapter_patches": [{{"lecture_id": "...", "title": "可选微调", "bridge_from_prev": "...", "bridge_to_next": "..."}}],
  "quality_notes": ["质量判断"],
  "warnings": ["风险"]
}}

课程：{json.dumps(course.model_dump(), ensure_ascii=False)[:500]}
蓝图：{json.dumps(plan_data, ensure_ascii=False)[:8000]}
各章：{json.dumps(compact, ensure_ascii=False)}"""

    try:
        data = await llm.complete_json(SYSTEM, prompt, max_tokens=10000)
    except Exception:
        data = {}

    # Apply patches
    patched = {ch.lecture_id: ch.model_copy(deep=True) for ch in chapters}
    for item in data.get("chapter_patches") or []:
        if not isinstance(item, dict):
            continue
        lid = str(item.get("lecture_id") or "")
        if lid not in patched:
            continue
        ch = patched[lid]
        if item.get("title"):
            ch.title = str(item["title"])
        if item.get("bridge_from_prev"):
            ch.bridge_from_prev = str(item["bridge_from_prev"])
        if item.get("bridge_to_next"):
            ch.bridge_to_next = str(item["bridge_to_next"])

    ordered = [patched[ch.lecture_id] for ch in chapters]
    fallback = synthesize_book_fallback(course, ordered, plan=plan)

    glossary = [str(x) for x in (data.get("glossary") or []) if str(x).strip()] or fallback.glossary
    key_point_index = [str(x) for x in (data.get("key_point_index") or []) if str(x).strip()] or fallback.key_point_index
    knowledge_map = [str(x) for x in (data.get("knowledge_map") or []) if str(x).strip()] or fallback.knowledge_map
    how_to_use = [str(x) for x in (data.get("how_to_use") or []) if str(x).strip()] or fallback.how_to_use
    learning_path = [str(x) for x in (data.get("learning_path") or []) if str(x).strip()] or fallback.learning_path
    continuity_notes = [str(x) for x in (data.get("continuity_notes") or []) if str(x).strip()] or fallback.continuity_notes
    quality_notes = [str(x) for x in (data.get("quality_notes") or []) if str(x).strip()] or fallback.quality_notes
    preface = str(data.get("preface") or "").strip() or fallback.preface

    source_index = [f"{ch.title}：{r}" for ch in ordered for r in ch.source_ranges]

    return CourseBook(
        course=course,
        title=str(data.get("title") or fallback.title),
        chapters=ordered,
        glossary=glossary[:80],
        source_index=source_index,
        warnings=[str(x) for x in (data.get("warnings") or []) if str(x).strip()],
        preface=preface,
        how_to_use=how_to_use,
        knowledge_map=knowledge_map,
        learning_path=learning_path,
        key_point_index=key_point_index,
        continuity_notes=continuity_notes,
        quality_notes=quality_notes,
        components=plan.components if plan else fallback.components,
        render_config=plan.render_config if plan else fallback.render_config,
    )


def synthesize_book_fallback(course: Course, chapters: list[LectureDraft], plan: BookPlan | None = None) -> CourseBook:
    """Deterministic book layer from chapter fields."""
    title = plan.book_title if plan else f"{course.name}：复习教辅"

    knowledge_map = []
    if plan and plan.modules:
        for module in plan.modules:
            if isinstance(module, dict):
                indices = module.get("lecture_indices") or []
                purpose = module.get("purpose") or ""
                climax = module.get("climax") or ""
                knowledge_map.append(
                    f"{module.get('name', '模块')}（讲次 {','.join(str(i) for i in indices)}）：{purpose}"
                    + (f"；收获：{climax}" if climax else "")
                )

    learning_path = list(plan.learning_path) if plan and plan.learning_path else [
        "先读前言与知识地图", "核心方法章按顺序精读", "嘉宾章可后读", "考前用要点速记回看",
    ]

    key_points: list[str] = []
    for ch in chapters:
        role_prefix = {"core": "核心", "review": "复习", "guest": "专题", "mixed": "综合"}.get(ch.chapter_role, "")
        for item in (ch.key_points or ch.summary[:3])[:4]:
            key_points.append(f"【{role_prefix}·{ch.title}】{item}")

    guest_titles = [c.title for c in chapters if c.chapter_role == "guest"]
    continuity_notes = list(plan.continuity_notes) if plan and plan.continuity_notes else []
    if guest_titles:
        continuity_notes.append("专题章（" + "；".join(guest_titles) + "）可后读。")

    preface_parts = [
        plan.book_positioning if plan and plan.book_positioning else f"本书把《{course.name}》课堂讲解整理为可连续复习的教辅文本。",
        "按方法主线组织，不是按课堂录像时间表堆叠。",
        "每章提供学习目标、重点、易错点与来源。",
    ]

    from coursebook_agent.models import ComponentSpec
    default_components = plan.components if plan and plan.components else [
        ComponentSpec(name="worked_example", description="例题", fields=["title", "problem", "steps", "conclusion", "source_ref"], usage_instruction="每章至少1个"),
        ComponentSpec(name="tip_box", description="小贴士", fields=["title", "body"], usage_instruction="每章1-3个"),
        ComponentSpec(name="warning", description="警告", fields=["title", "body"], usage_instruction="每章2-4个"),
    ]

    return CourseBook(
        course=course,
        title=title,
        chapters=chapters,
        glossary=(plan.canonical_glossary[:80] if plan and plan.canonical_glossary else _fallback_glossary(chapters)),
        source_index=[f"{ch.title}：{r}" for ch in chapters for r in ch.source_ranges],
        preface="".join(preface_parts),
        how_to_use=[
            "先读知识地图与学习路径",
            "核心方法章精读：先看目标与重点，再读正文",
            "嘉宾/专题章可选读",
            "考前用要点速记 + 术语表回看",
        ],
        knowledge_map=knowledge_map,
        learning_path=learning_path,
        key_point_index=key_points,
        continuity_notes=continuity_notes,
        quality_notes=[f"共 {len(chapters)} 章，core={sum(1 for c in chapters if c.chapter_role=='core')} guest={sum(1 for c in chapters if c.chapter_role=='guest')}"],
        components=default_components,
        render_config=plan.render_config if plan else {},
    )


def _fallback_glossary(chapters: list[LectureDraft]) -> list[str]:
    seen: set[str] = set()
    glossary: list[str] = []
    for ch in chapters:
        for item in ch.concepts:
            name = item.split("：")[0].split(":")[0].strip().lower()
            if name and name not in seen:
                seen.add(name)
                glossary.append(item)
    return glossary
