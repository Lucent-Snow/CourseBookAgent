"""Layer 2: Editor-in-chief — builds the complete book plan.

Receives 14 LectureDigests (dense knowledge-point maps).
Outputs: BookPlan with structure + components + per-chapter instructions + shared prompt.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from coursebook_agent.agent.llm import LLMClient, LLMError, extract_json_object
from coursebook_agent.config import config
from coursebook_agent.models import (  # noqa: E402
    BookPlan,
    ChapterInstruction,
    ComponentSpec,
    Course,
    LectureDigest,
    ResourceDescription,
)

logger = logging.getLogger(__name__)

SYSTEM = """你是高校课程教辅书的总编辑。

你收到的是各讲的"知识点地图"——压缩过的课堂内容摘要，告诉你老师讲了什么、怎么讲的、有哪些知识点和例子。你不需要重新理解统计学概念，你需要理解的是这门课的老师是如何教授这些概念的。

你的任务：
1. 把 14 讲按知识主线组织成一本教辅书，而不是按课堂时间序拼接。
2. 定义书里用到的组件（例题框、Tips、易错警告等），让分章写作者有统一的格式。
3. 为每一章写具体的写作指令：覆盖什么、压缩什么、用什么组件、写到什么深度。
4. 每章的 section_plan 必须带内容锚点：每个小节对应哪些知识点、哪些 chunk_refs、有什么教学信号。这样分章写作者拿到的是"带素材的结构图"而不是"空标题列表"。
5. 写一份给所有分章写作者的共享系统 prompt。
5. 定义渲染配置（Web 版需要时间戳链接，PDF 版不需要等）。

只返回 JSON。"""


async def plan_book(
    course: Course,
    digests: list[LectureDigest],
    client: LLMClient | None = None,
    *,
    profile_context: str = "",
) -> BookPlan:
    if not digests:
        raise ValueError("没有可用于规划的讲次摘要")

    llm = client or LLMClient(max_retries=3, timeout=max(180, config.llm.timeout))
    payload = {
        "course": course.model_dump(),
        "digests": [d.model_dump() for d in digests],
    }

    prompt = f"""请为下列课程设计一本教辅书。

输入是各讲的知识点地图。你知道统计学概念，但你需要关注老师具体怎么教的。

{profile_context}

V2 蓝图不可降级：必须完整填写 components、writer_system_prompt、每章 component_usage、depth_guidance 和 common_mistakes。章节类型（core / guest / review / mixed）必须按课程编辑配置中的模板区分，不得用同一套模板套所有讲次。

返回严格 JSON：
{{
  "course_id": "{course.course_id}",
  "book_title": "书名",
  "audience": "目标读者",
  "book_positioning": "2-4 句话：这本书帮读者解决什么复习问题",
  "learning_path": ["建议的复习路径"],
  "modules": [
    {{"name": "模块名", "lecture_indices": [1,2,3], "purpose": "模块目的", "climax": "模块核心收获"}}
  ],
  "global_emphasis": ["全书反复强调的主线"],
  "canonical_glossary": ["术语：标准释义"],

  "components": [
    {{
      "name": "worked_example",
      "description": "课堂例题的标准化展示",
      "fields": ["title", "problem", "steps", "conclusion", "source_ref"],
      "usage_instruction": "每章至少 1 个；步骤必须来自字幕",
      "example": "【例题】某校 40 名学生..."
    }},
    {{
      "name": "tip_box",
      "description": "小贴士框：帮助理解的补充说明",
      "fields": ["title", "body"],
      "usage_instruction": "每章 1-3 个；用于澄清易混概念或记忆技巧",
      "example": ""
    }},
    {{
      "name": "warning",
      "description": "易错警告：红色高亮的常见错误",
      "fields": ["title", "body"],
      "usage_instruction": "每章 2-4 个；必须是课堂上实际涉及的易错点",
      "example": ""
    }},
    {{
      "name": "side_note",
      "description": "旁注：补充但不打断主线的信息",
      "fields": ["body", "source_ref"],
      "usage_instruction": "可选；用于教师口述的背景故事或延伸",
      "example": ""
    }},
    {{
      "name": "procedure",
      "description": "步骤流程：标准化的方法步骤",
      "fields": ["title", "steps", "when_to_use"],
      "usage_instruction": "核心方法章必须有；步骤来自课堂讲解",
      "example": ""
    }}
  ],

  "writer_system_prompt": "你写给分章写作者的共享 prompt：定义写作风格、术语标准、禁忌、组件使用规范等。200-400字。",

  "continuity_notes": ["给分章写作者的衔接注意事项"],

  "chapters": [
    {{
      "lecture_id": "与输入一致",
      "index": 1,
      "book_title": "第 N 章：标题",
      "module_name": "所属模块",
      "chapter_role": "core|review|guest|admin|mixed",
      "narrative_purpose": "这章为什么必须存在",
      "learning_goals": ["学完应能..."],
      "must_cover": ["不可省略的知识点/步骤"],
      "de_emphasize": ["应压缩的内容"],
      "prerequisite_concepts": ["依赖的前序概念"],
      "bridge_from_prev": "承上",
      "bridge_to_next": "启下",
      "canonical_terms": ["本章应使用的标准术语"],
      "common_mistakes": ["本章应点破的易错点"],
      "section_plan": [{"heading": "小节标题", "knowledge_points": ["知识点名"], "chunk_refs": ["c001", "c005"], "teaching_signals": "emphasis, question", "writing_focus": "为什么需要\u2192原理\u2192步骤"}],
      "component_usage": ["用 procedure 展示 F 检验步骤", "用 worked_example 展示完整计算"],
      "depth_guidance": "这章需要逐步计算演示" 或 "这章以概念梳理为主",
      "must_verify": ["字幕支撑不足的知识点：原因（如 '公式推导：字幕只有结论没有过程'）"]
    }}
  ],

  "render_config": {{
    "pdf_omit_timestamp_links": true,
    "web_timestamp_links": true,
    "component_style": "compact"
  }},

  "warnings": ["规划中的不确定点"]
}}

约束：
1. chapters 数量必须与 digests 一致。
2. components 至少定义 worked_example、tip_box、warning 三种。
3. writer_system_prompt 必须包含：只用字幕内容、不编造、术语统一、组件格式。
4. bridge_from_prev/bridge_to_next 必须具体。
5. component_usage 必须引用 components 中定义的 name。
6. 关注各讲 digest 中 knowledge_points 的 sufficiency 字段：sufficiency 为 insufficient 或 partial 的知识点必须列入 must_verify，并注明原因。不能把字幕支撑不足的知识点当作确定事实呈现。\n7. section_plan 中每个小节必须填写 knowledge_points、chunk_refs、teaching_signals，不能只给空标题。

课程与摘要：
{json.dumps(payload, ensure_ascii=False)}"""

    data = await llm.complete_json(SYSTEM, prompt, max_tokens=16000)
    plan = _coerce_plan(course, digests, data)
    return plan


def _coerce_plan(course: Course, digests: list[LectureDigest], data: dict) -> BookPlan:
    # Coerce components
    components: list[ComponentSpec] = []
    for item in data.get("components") or []:
        if not isinstance(item, dict):
            continue
        components.append(ComponentSpec(
            name=str(item.get("name") or ""),
            description=str(item.get("description") or ""),
            fields=[str(f) for f in (item.get("fields") or [])],
            usage_instruction=str(item.get("usage_instruction") or ""),
            example=str(item.get("example") or ""),
        ))

    # Ensure minimum components
    existing_names = {c.name for c in components}
    defaults = {
        "worked_example": ("课堂例题展示", ["title", "problem", "steps", "conclusion", "source_ref"], "每章至少 1 个"),
        "tip_box": ("补充说明", ["title", "body"], "每章 1-3 个"),
        "warning": ("易错警告", ["title", "body"], "每章 2-4 个"),
    }
    for name, (desc, fields, usage) in defaults.items():
        if name not in existing_names:
            components.append(ComponentSpec(name=name, description=desc, fields=fields, usage_instruction=usage))

    # Coerce chapters
    raw_chapters = data.get("chapters") or []
    by_id = {item.get("lecture_id"): item for item in raw_chapters if isinstance(item, dict)}
    by_index = {item.get("index"): item for item in raw_chapters if isinstance(item, dict)}

    chapters: list[ChapterInstruction] = []
    for digest in digests:
        raw = by_id.get(digest.lecture_id) or by_index.get(digest.index) or {}
        chapters.append(ChapterInstruction(
            lecture_id=digest.lecture_id,
            index=digest.index,
            book_title=str(raw.get("book_title") or f"第 {digest.index} 章：{digest.raw_title}"),
            module_name=str(raw.get("module_name") or ""),
            chapter_role=str(raw.get("chapter_role") or "core"),
            narrative_purpose=str(raw.get("narrative_purpose") or ""),
            learning_goals=_str_list(raw.get("learning_goals")),
            must_cover=_str_list(raw.get("must_cover")),
            de_emphasize=_str_list(raw.get("de_emphasize")),
            prerequisite_concepts=_str_list(raw.get("prerequisite_concepts")),
            bridge_from_prev=str(raw.get("bridge_from_prev") or ""),
            bridge_to_next=str(raw.get("bridge_to_next") or ""),
            canonical_terms=_str_list(raw.get("canonical_terms")),
            common_mistakes=_str_list(raw.get("common_mistakes")),
            section_plan=_section_plan_list(raw.get("section_plan")),
            component_usage=_str_list(raw.get("component_usage")),
            depth_guidance=str(raw.get("depth_guidance") or ""),
            must_verify=_str_list(raw.get("must_verify")),
        ))

    return BookPlan(
        course_id=course.course_id,
        book_title=str(data.get("book_title") or f"{course.name}：课堂精讲与复习教辅"),
        audience=str(data.get("audience") or ""),
        book_positioning=str(data.get("book_positioning") or ""),
        learning_path=_str_list(data.get("learning_path")),
        modules=list(data.get("modules") or []) if isinstance(data.get("modules"), list) else [],
        global_emphasis=_str_list(data.get("global_emphasis")),
        canonical_glossary=_str_list(data.get("canonical_glossary")),
        continuity_notes=_str_list(data.get("continuity_notes")),
        components=components,
        chapters=chapters,
        writer_system_prompt=str(data.get("writer_system_prompt") or ""),
        render_config=dict(data.get("render_config") or {}),
        warnings=_str_list(data.get("warnings")),
    )


def _section_plan_list(value) -> list[str]:
    """Extract section headings from section_plan, supporting both old (str list) and new (dict list) formats."""
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict):
            heading = item.get("heading", "")
            if heading:
                result.append(str(heading).strip())
        elif str(item).strip():
            result.append(str(item).strip())
    return result


def _str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def save_plan(plan: BookPlan, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")


def load_plan(path: Path) -> BookPlan:
    return BookPlan.model_validate_json(path.read_text(encoding="utf-8"))


# ── v2: main Agent consumes ResourceDescriptions ────────────────────────────


V2_SYSTEM = """你是高校课程教辅书的**主 Agent（主编 + 资料编排）**。

你的工作是把多份零散的课堂资料**重新组织成一本书**，不是按时间顺序把它们切成一节一节的概要。

你看到的资料可能来源不同（智云课堂字幕、学在浙大课件、上传的 PDF/PPT 等），也可能在时间上重叠或顺序颠倒。每份资料只是一堆原始素材，你需要**先消化、再聚合、最后重组**。

## 你必须遵循的几条硬约束

1. **章节是书籍主题，不是讲次时间**。**绝不**因为"这门课有 15 讲"就分出 15 章。你要把多份资料按主题合并成若干章。一节课可能只撑起一章的某个小节；多节课可能共同构成一章；如果某份资料只重复了另一份的内容，可以合并甚至不单独成章。
2. **章节数由主题决定，不由资料数决定**。一本书 6 章、9 章、12 章都是合理的。资料数 = 15 并不意味着章数 = 15。
3. **章节顺序由主题逻辑决定，不是讲次时间**。"概念 → 方法 → 应用 → 拓展"这种教学顺序优先于"今天讲了什么"。
4. **Tag 携带阅读顺序**。`chapter_id` 用 `c1 / c2 / c3 / …` 按书的阅读顺序递增；同时 `resource_tags[revision_id]` 的 value 是这份资料进入的章节列表（章节顺序即为阅读顺序）。
5. **无主题理由不拆章节**。如果 16 份资料都在讲同一件事，就合成 1 章，宁可少而深。

## 你输出的 BookPlan 字段

- `book_title` / `audience` / `book_positioning`：整本书
- `chapters[]`：每章写一份 `ChapterInstruction`，chapter_id 严格 `c1 / c2 / … / cN`，book_title 含主题不是讲次日期
- `resource_tags`：每份资料的归属
- `components / writer_system_prompt`：全书写作规范
- `modules`：把章节再按主题分块（不是必须 1:1 跟讲次对应）

## 你不做的事

- 不按讲次时间排章节
- 不为每份资料单独建一章
- 不用讲次标题（"第 X 讲"）做章节标题

只返回 JSON。"""


V2_USER_TEMPLATE = """课程信息：{course}

所有资料描述（按 revision_id 列出）：
{descriptions}

请按"主题合并"重新组织成一本书。规划步骤：
1. 通读所有 description，识别共同主题和边界（哪些资料属于同一主题？哪些资料只补充同一章？）。
2. 决定 N 个章节（N 与资料数无关），给出主题型章节标题。
3. 为每份资料打 Tag：进入哪一章（chapter_id 列表），还是 __global__，还是无 Tag。
4. 章节顺序 `c1 / c2 / ...` 按主题教学逻辑排（概念 → 方法 → 应用 → 拓展），不要按讲次时间。

请输出严格 JSON：
{{
  "book_title": "书名（主题型，不要含「第 X 讲」）",
  "audience": "目标读者",
  "book_positioning": "本书解决什么问题，2-4 句",
  "learning_path": ["复习路径"],
  "modules": [{{"name": "模块名", "chapter_ids": ["c1", "c3"], "purpose": "模块目的"}}],
  "global_emphasis": ["全书反复强调的主线"],
  "canonical_glossary": ["术语：标准释义"],
  "components": [
    {{"name": "worked_example", "description": "...", "fields": [...], "usage_instruction": "...", "example": "..."}},
    {{"name": "tip_box", "description": "...", "fields": [...], "usage_instruction": "...", "example": ""}},
    {{"name": "warning", "description": "...", "fields": [...], "usage_instruction": "...", "example": ""}}
  ],
  "writer_system_prompt": "给所有分章写作者的共享 prompt：风格、术语、禁忌、组件使用规范，200-400 字",
  "continuity_notes": ["衔接注意事项"],
  "chapters": [
    {{
      "chapter_id": "c1",
      "book_title": "第 1 章：主题型标题（不要「第 X 讲」「2026-…」这类时间戳）",
      "module_name": "所属模块",
      "chapter_role": "core|review|guest|admin|mixed",
      "narrative_purpose": "为什么这章必须存在",
      "learning_goals": ["学完应能..."],
      "must_cover": ["不可省略的知识点"],
      "de_emphasize": ["应压缩的内容"],
      "prerequisite_concepts": ["前置概念"],
      "bridge_from_prev": "承上",
      "bridge_to_next": "启下",
      "canonical_terms": ["本章标准术语"],
      "common_mistakes": ["本章应点破的易错点"],
      "section_plan": [{{"heading": "小节标题", "knowledge_points": ["..."], "source_revision_ids": ["rev-1"], "writing_focus": "..."}}],
      "component_usage": ["用 procedure 展示..."],
      "depth_guidance": "本章需要逐步演示 / 概述即可",
      "must_verify": ["资料支撑不足须谨慎处理的内容"]
    }}
  ],
  "resource_tags": {{
     "<revision_id>": ["c1", "c3"],
     "<revision_id>": ["__global__"]
  }},
  "warnings": ["规划不确定点"]
}}

约束：
1. **章节数由你按主题决定**，与资料数无关；可能 5 章，也可能 12 章。绝不要 1 章对应 1 份资料。
2. chapter_id 用 "c1"、"c2"…按阅读顺序稳定递增；同一份资料可以出现在多个章节（value 是数组）。
3. 每个 chapter 必须有 must_cover、section_plan（≥1 小节）、depth_guidance、component_usage。
4. resource_tags 的 value 是字符串数组：要么是 chapter_id（资料作为该章节的原始素材），要么是 "__global__"（资料作为全局上下文）。未列入 resource_tags 的资料本次不进入生成。
5. 一份资料可以同时进入多个章节，也可以同时进入全局与某些章节。
6. writer_system_prompt 必须包含：只用资料中的内容、不编造、术语统一、组件格式。
7. components 至少包含 worked_example、tip_box、warning 三种。
8. section_plan 的 source_revision_ids 必须引用下面"所有资料描述"里出现的 revision_id 之一。
9. 资料支撑不足（suggested_role == "auxiliary" 或 summary 显式说明）的内容必须列入 must_verify 或 common_mistakes。

参考资料描述：
{descriptions}
"""


async def plan_book_v2(
    course: Course,
    descriptions: list,
    client: LLMClient | None = None,
    *,
    snapshot_id: str | None = None,
) -> BookPlan:
    """v2 main Agent: ingest resource descriptions, output BookPlan with resource_tags."""
    if not descriptions:
        raise ValueError("没有任何资料描述可用于规划")

    llm = client or LLMClient(max_retries=3, timeout=max(180, config.llm.timeout))
    # Keep payload small enough to leave room for reasoning + JSON.
    compact_descriptions = []
    for d in descriptions:
        topic = d.topic or d.title or ""
        summary = d.summary or topic
        compact_descriptions.append({
            "revision_id": d.revision_id,
            "kind": d.kind,
            "provider": d.provider,
            "title": (d.title or "")[:80],
            "topic": topic[:120],
            "knowledge_topics": [str(k)[:24] for k in (d.knowledge_topics or [])][:8],
            "scope": d.scope,
            "usable_content_kinds": list(d.usable_content_kinds or [])[:5],
            "suggested_role": d.suggested_role,
            "summary": summary[:160],
        })
    payload = {"course": course.model_dump(), "descriptions": compact_descriptions}
    prompt = V2_USER_TEMPLATE.format(
        course=json.dumps(course.model_dump(), ensure_ascii=False),
        descriptions=json.dumps(payload, ensure_ascii=False),
    )
    raw = await llm.complete(V2_SYSTEM, prompt, max_tokens=24000, temperature=0.2)
    try:
        data = extract_json_object(raw)
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("plan_book_v2: failed to extract JSON: %s", exc)
        data = {}
    if (not isinstance(data, dict)) or not data.get("chapters"):
        # Retry once with a tighter, JSON-only instruction; do not waste tokens.
        repair_user = (
            "把下面的模型输出整理为一个合法 JSON 对象，字段必须包含 chapters / resource_tags / components / writer_system_prompt。"
            "只输出 JSON，不要任何解释或 Markdown。\n\n"
            f"原始任务：\n{prompt[:12000]}\n\n模型输出：\n{raw[:18000]}"
        )
        try:
            repair = await llm.complete(
                "你是 JSON 生成器。只输出一个合法 JSON 对象，不解释。",
                repair_user,
                max_tokens=20000, temperature=0,
            )
            data = extract_json_object(repair)
            if not isinstance(data, dict) or not data.get("chapters"):
                logger.warning("plan_book_v2 repair returned no chapters: %s", str(data)[:200])
        except (LLMError, ValueError, KeyError, TypeError) as exc:
            logger.warning("plan_book_v2 repair failed: %s", exc)
            data = {}
    plan = _coerce_plan_v2(course, descriptions, data, snapshot_id=snapshot_id)
    return plan


def _coerce_plan_v2(
    course: Course,
    descriptions: list,
    data: dict,
    *,
    snapshot_id: str | None,
) -> BookPlan:
    """Coerce + sanitise LLM output into a BookPlan v2.

    If the LLM produced no chapters (model failure / truncated output),
    fall back to a minimal-but-correct v2 plan: each description gets its
    own chapter; resources with scope=course are tagged __global__.
    """
    components: list[ComponentSpec] = []
    for item in (data.get("components") or []):
        if not isinstance(item, dict):
            continue
        components.append(ComponentSpec(
            name=str(item.get("name") or ""),
            description=str(item.get("description") or ""),
            fields=[str(f) for f in (item.get("fields") or [])],
            usage_instruction=str(item.get("usage_instruction") or ""),
            example=str(item.get("example") or ""),
        ))
    existing_names = {c.name for c in components}
    defaults = {
        "worked_example": ("课堂例题展示", ["title", "problem", "steps", "conclusion", "source_ref"], "每章至少 1 个"),
        "tip_box": ("补充说明", ["title", "body"], "每章 1-3 个"),
        "warning": ("易错警告", ["title", "body"], "每章 2-4 个"),
    }
    for name, (desc, fields, usage) in defaults.items():
        if name not in existing_names:
            components.append(ComponentSpec(name=name, description=desc, fields=fields, usage_instruction=usage))

    raw_chapters = [item for item in (data.get("chapters") or []) if isinstance(item, dict)]
    chapters: list[ChapterInstruction] = []
    seen_chapter_ids: set[str] = set()
    for idx, raw in enumerate(raw_chapters, start=1):
        cid = str(raw.get("chapter_id") or f"c{idx}")
        unique = cid
        suffix = 2
        while unique in seen_chapter_ids:
            unique = f"{cid}-{suffix}"
            suffix += 1
        seen_chapter_ids.add(unique)
        chapters.append(ChapterInstruction(
            chapter_id=unique,
            lecture_id=str(raw.get("lecture_id") or ""),
            index=int(raw.get("index") or idx),
            book_title=str(raw.get("book_title") or f"第 {idx} 章"),
            module_name=str(raw.get("module_name") or ""),
            chapter_role=str(raw.get("chapter_role") or "core"),
            narrative_purpose=str(raw.get("narrative_purpose") or ""),
            learning_goals=_str_list(raw.get("learning_goals")),
            must_cover=_str_list(raw.get("must_cover")),
            de_emphasize=_str_list(raw.get("de_emphasize")),
            prerequisite_concepts=_str_list(raw.get("prerequisite_concepts")),
            bridge_from_prev=str(raw.get("bridge_from_prev") or ""),
            bridge_to_next=str(raw.get("bridge_to_next") or ""),
            canonical_terms=_str_list(raw.get("canonical_terms")),
            common_mistakes=_str_list(raw.get("common_mistakes")),
            section_plan=_section_plan_list(raw.get("section_plan")),
            component_usage=_str_list(raw.get("component_usage")),
            depth_guidance=str(raw.get("depth_guidance") or ""),
            must_verify=_str_list(raw.get("must_verify")),
        ))

    # ── Fallback: derive a minimal plan from the descriptions themselves ──
    if not chapters:
        logger.warning("plan_book_v2: empty chapters after coerce; using descriptions-only fallback")
        for idx, d in enumerate(descriptions, start=1):
            cid = f"c{idx}"
            chapters.append(ChapterInstruction(
                chapter_id=cid,
                book_title=f"第 {idx} 章：{(d.title or d.topic or d.revision_id)[:60]}",
                module_name="按资料分章",
                chapter_role="core",
                narrative_purpose=d.summary[:200] or d.topic,
                learning_goals=d.knowledge_topics[:4],
                must_cover=d.knowledge_topics[:8],
                depth_guidance="概述即可",
                component_usage=["用 worked_example 展示典型内容"],
                section_plan=d.knowledge_topics[:6],
                must_verify=[] if d.suggested_role != "auxiliary" else [d.summary or d.topic],
            ))

    known_revs = {d.revision_id for d in descriptions}
    known_chapters = {c.chapter_id for c in chapters}
    raw_tags = data.get("resource_tags") if isinstance(data.get("resource_tags"), dict) else {}
    resource_tags: dict[str, list[str]] = {}
    for rev, tags in raw_tags.items():
        if rev not in known_revs:
            continue
        if not isinstance(tags, list):
            continue
        cleaned: list[str] = []
        for tag in tags:
            s = str(tag).strip()
            if not s:
                continue
            if s == "__global__" or s in known_chapters:
                cleaned.append(s)
        if cleaned:
            resource_tags[rev] = cleaned

    # ── Fallback tags: every description is chapter-tagged; scope=course goes global. ──
    if not resource_tags:
        for idx, d in enumerate(descriptions, start=1):
            cid = f"c{idx}"
            tags: list[str] = []
            if d.scope == "course":
                tags.append("__global__")
            if cid in known_chapters:
                tags.append(cid)
            if tags:
                resource_tags[d.revision_id] = tags

    chapter_resources = _derive_chapter_resources(resource_tags, chapters)

    warnings = _str_list(data.get("warnings"))
    if not isinstance(data, dict) or not data.get("chapters"):
        warnings.append("主 Agent 未产出章节，已按资料自动分章")

    return BookPlan(
        course_id=course.course_id,
        book_title=str(data.get("book_title") or f"{course.name}：课堂精讲与复习教辅"),
        audience=str(data.get("audience") or ""),
        book_positioning=str(data.get("book_positioning") or ""),
        learning_path=_str_list(data.get("learning_path")),
        modules=list(data.get("modules") or []) if isinstance(data.get("modules"), list) else [],
        global_emphasis=_str_list(data.get("global_emphasis")),
        canonical_glossary=_str_list(data.get("canonical_glossary")),
        continuity_notes=_str_list(data.get("continuity_notes")),
        components=components,
        chapters=chapters,
        writer_system_prompt=str(data.get("writer_system_prompt") or ""),
        render_config=dict(data.get("render_config") or {}),
        warnings=warnings,
        resource_tags=resource_tags,
        chapter_resources=chapter_resources,
        global_resource_ids=sorted([rev for rev, tags in resource_tags.items() if "__global__" in tags]),
        snapshot_id=snapshot_id,
    )


def _derive_chapter_resources(
    resource_tags: dict[str, list[str]],
    chapters: list[ChapterInstruction],
) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {c.chapter_id: [] for c in chapters}
    for rev, tags in resource_tags.items():
        for tag in tags:
            if tag in mapping:
                if rev not in mapping[tag]:
                    mapping[tag].append(rev)
    return mapping


def heuristic_book_plan_v2(
    course: Course,
    descriptions: list,
    *,
    snapshot_id: str | None = None,
) -> BookPlan:
    """Deterministic fallback for v2.

    The main Agent is supposed to merge descriptions by theme.  When the
    LLM is unavailable we still must NOT emit one chapter per resource
    (that produced the 15-chapter/15-lecture artefact the user
    complained about).  Instead, we greedily cluster descriptions by
    shared ``knowledge_topics`` words and emit one chapter per cluster.
    The order is by first-seen topic, the chapter title is the dominant
    topic keyword.  This is intentionally coarse; the resulting plan
    always carries a warning that the main Agent should re-plan it.
    """

    # Greedy cluster: a description joins an existing chapter if it
    # shares at least one keyword with the chapter's running topic set;
    # otherwise it starts a new chapter.  This guarantees we collapse
    # near-duplicate lectures that share a subject (the typical case
    # for 16 transcript resources on the same course).
    chapters: list[ChapterInstruction] = []
    resource_tags: dict[str, list[str]] = {}
    chapter_topics: list[set[str]] = []

    def topic_set(d) -> set[str]:
        ks = list(d.knowledge_topics or [])
        # Title words are a fallback signal when the LLM didn't return
        # knowledge_topics (deterministic description path).
        if not ks and d.title:
            ks = [w for w in d.title.split() if len(w) >= 2]
        return {str(k).strip().lower() for k in ks if str(k).strip()}

    for d in descriptions:
        ts = topic_set(d)
        chosen = -1
        best_overlap = 0
        for idx, ct in enumerate(chapter_topics):
            overlap = len(ts & ct)
            if overlap > best_overlap:
                best_overlap = overlap
                chosen = idx
        if chosen < 0 or best_overlap == 0:
            chosen = len(chapters)
            chapter_topics.append(set(ts))
            cid = f"c{chosen + 1}"
            # Title is the first non-empty topic / title word so the
            # chapter carries a real subject label, not a lecture index.
            topic_word = next(iter(ts), None)
            label = topic_word or (d.title or d.topic or cid)
            # Capitalize for readability in Chinese titles.
            display = label if (label and label[:1].isupper() or any('\u4e00' <= ch <= '\u9fff' for ch in label)) else label
            chapters.append(ChapterInstruction(
                chapter_id=cid,
                book_title=f"第 {chosen + 1} 章：{display[:60]}",
                module_name="按主题分章（启发式）",
                chapter_role="core",
                narrative_purpose=d.summary[:200] or d.topic,
                learning_goals=d.knowledge_topics[:4],
                must_cover=d.knowledge_topics[:8],
                de_emphasize=[],
                prerequisite_concepts=[],
                bridge_from_prev="全书从本资料集开始。" if chosen == 0 else f"本章承接上一章《{chapters[chosen - 1].book_title}》。",
                bridge_to_next="",
                canonical_terms=d.knowledge_topics[:8],
                common_mistakes=[],
                section_plan=d.knowledge_topics[:6],
                component_usage=["用 worked_example 展示典型内容"],
                depth_guidance="概述即可",
                must_verify=[] if d.suggested_role != "auxiliary" else [d.summary or d.topic],
            ))
            chapter_topics[chosen] |= ts
        else:
            chapter_topics[chosen] |= ts
        resource_tags.setdefault(d.revision_id, []).append(chapters[chosen].chapter_id)

    default_components = [
        ComponentSpec(name="worked_example", description="课堂例题展示", fields=["title", "problem", "steps", "conclusion", "source_ref"], usage_instruction="每章至少 1 个"),
        ComponentSpec(name="tip_box", description="补充说明", fields=["title", "body"], usage_instruction="每章 1-3 个"),
        ComponentSpec(name="warning", description="易错警告", fields=["title", "body"], usage_instruction="每章 2-4 个"),
    ]

    return BookPlan(
        course_id=course.course_id,
        book_title=f"{course.name}：课堂精讲与复习教辅（启发式）",
        audience="正在修读本课、需要复习的学生",
        book_positioning="把课堂推理压缩成可连续阅读的复习教辅。",
        learning_path=["按章节顺序阅读"],
        modules=[{"name": "按资料分章（启发式）", "chapter_ids": [c.chapter_id for c in chapters], "purpose": "主 Agent 不可用时的回退"}],
        global_emphasis=[],
        canonical_glossary=[],
        continuity_notes=[],
        components=default_components,
        chapters=chapters,
        writer_system_prompt="你是教辅书分章写作者。只用资料内容，不编造。术语统一。每个例题和重点标注来源。",
        render_config={"web_timestamp_links": True, "pdf_omit_timestamp_links": True},
        warnings=["启发式回退：主 Agent 不可用，按主题关键词贪心合并；如需更细粒度请让主 Agent 可用后重跑"],
        resource_tags=resource_tags,
        chapter_resources=_derive_chapter_resources(resource_tags, chapters),
        global_resource_ids=[],
        snapshot_id=snapshot_id,
    )


# ── Heuristic fallback (deterministic, no LLM) ──────────────────────────────

def heuristic_book_plan(course: Course, digests: list[LectureDigest]) -> BookPlan:
    """Deterministic fallback when the planner model is unavailable."""
    modules_spec = [
        ("课程入口与统计复习", {1}, "review"),
        ("假设检验主线", {2, 3}, "core"),
        ("方差分析主线", {4, 5, 6, 7}, "core"),
        ("应用专题：工业心理学", {8}, "guest"),
        ("回归分析主线", {9, 11}, "core"),
        ("应用专题：决策与格式塔", {10}, "guest"),
        ("类别数据与非参数", {12, 13}, "core"),
        ("综合复习", {14}, "review"),
    ]

    def module_for(index: int) -> tuple[str, str]:
        digest = digests[index - 1]
        blob = (digest.raw_title + digest.teacher_flow + " ".join(kp.name for kp in digest.knowledge_points)).lower()
        for name, indices, default_role in modules_spec:
            if index in indices:
                role = default_role
                if any(k in blob for k in ["嘉宾", "工业心理", "人机交互", "战争", "格式塔", "美学"]):
                    role = "guest"
                if index in {1, 14} or ("复习" in blob and index in {7, 14}):
                    role = "review" if index != 7 else role
                if index == 7 and "美学" in blob:
                    role = "mixed"
                return name, role
        return "综合", "core"

    chapters: list[ChapterInstruction] = []
    for i, digest in enumerate(digests):
        module_name, role = module_for(digest.index)
        prev = digests[i - 1] if i > 0 else None
        nxt = digests[i + 1] if i + 1 < len(digests) else None
        kp_names = [kp.name for kp in digest.knowledge_points[:6]]
        bridge_from = (
            f"上一章《{prev.raw_title}》已建立相关基础，本章转入《{digest.raw_title}》。"
            if prev
            else "本书从课程目标与统计基础复习切入。"
        )
        bridge_to = (
            f"下一章《{nxt.raw_title}》将继续沿方法主线加深。"
            if nxt
            else "本章收束全书方法主线。"
        )
        chapters.append(ChapterInstruction(
            lecture_id=digest.lecture_id,
            index=digest.index,
            book_title=f"第 {digest.index} 章：{digest.raw_title}",
            module_name=module_name,
            chapter_role=role,
            narrative_purpose=digest.teacher_flow[:180],
            learning_goals=[f"能复述本章核心问题", f"能辨认：{'、'.join(kp_names[:3])}"],
            must_cover=[kp.name for kp in digest.knowledge_points[:6]],
            de_emphasize=["签到与行政通知", "闲聊"],
            prerequisite_concepts=[kp.name for kp in (prev.knowledge_points[:3] if prev else [])],
            bridge_from_prev=bridge_from,
            bridge_to_next=bridge_to,
            canonical_terms=kp_names,
            common_mistakes=["把未拒绝H0说成证明H0正确", "忽略方法适用条件直接套公式"],
            section_plan=[kp.name for kp in digest.knowledge_points[:5]],
            component_usage=["用 worked_example 展示课堂例题", "用 warning 标注易错点"],
            depth_guidance="核心方法章需逐步演示" if role == "core" else "概述即可",
        ))

    glossary: list[str] = []
    seen: set[str] = set()
    for digest in digests:
        for kp in digest.knowledge_points:
            if kp.name.lower() not in seen:
                seen.add(kp.name.lower())
                glossary.append(f"{kp.name}：{kp.description}")

    default_components = [
        ComponentSpec(name="worked_example", description="课堂例题展示", fields=["title", "problem", "steps", "conclusion", "source_ref"], usage_instruction="每章至少 1 个"),
        ComponentSpec(name="tip_box", description="补充说明", fields=["title", "body"], usage_instruction="每章 1-3 个"),
        ComponentSpec(name="warning", description="易错警告", fields=["title", "body"], usage_instruction="每章 2-4 个"),
        ComponentSpec(name="procedure", description="步骤流程", fields=["title", "steps", "when_to_use"], usage_instruction="核心方法章必须有"),
    ]

    return BookPlan(
        course_id=course.course_id,
        book_title=f"{course.name}：课堂精讲与复习教辅",
        audience="正在修读本课、需要复习的学生",
        book_positioning="把课堂推理压缩成可连续阅读的复习教辅，按方法主线组织而非按时间序堆叠。",
        learning_path=[
            "先修通假设检验逻辑",
            "再进入方差分析的设计与分解",
            "然后掌握回归建模与检验",
            "最后补齐卡方/非参数，并用综合复习回看",
            "嘉宾专题章按兴趣选读",
        ],
        modules=[{"name": name, "lecture_indices": sorted(indices), "purpose": purpose}
                 for name, indices, purpose in [
                     ("课程入口与统计复习", [1], "建立共同语言"),
                     ("假设检验主线", [2, 3], "单组到两组推断"),
                     ("方差分析主线", [4, 5, 6, 7], "多组比较与实验设计"),
                     ("应用专题", [8, 10], "方法在真实问题中的使用"),
                     ("回归与非参数", [9, 11, 12, 13], "预测与放松分布假设"),
                     ("综合复习", [14], "考前整合"),
                 ]],
        global_emphasis=["先问研究问题再选统计量", "始终区分未拒绝与证明成立", "设计决定可分析什么"],
        canonical_glossary=glossary[:80],
        continuity_notes=["核心方法章必须显式承接上一章", "guest 章标明可后读"],
        components=default_components,
        chapters=chapters,
        writer_system_prompt="你是教辅书分章写作者。只用字幕内容，不编造。术语统一。核心方法章要写清步骤和判定。每个例题和重点标注来源。",
        render_config={"web_timestamp_links": True, "pdf_omit_timestamp_links": True},
        warnings=["启发式回退：LLM 规划不可用"],
    )
