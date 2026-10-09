"""Per-resource description generator.

The description is the unit that the main Agent actually reads before
planning chapters and assigning resource Tags.  Design (agreed 2026-09-26,
see docs/DECOMPOSITION.md):

1. Every material type goes through the LLM.  The description is a lossy
   compression optimised for planning decisions — transcripts are the
   densest case and need it most, so there is no transcript fast path.
2. The body is a fixed five-part Markdown document covering form, content
   blocks, unique value, terminology/keywords and placement suggestions.
   The frame is carrier-agnostic: transcripts, slides, notes, papers and
   syllabi all fit the same five questions.
3. The heuristic extractor only runs when the LLM fails, so the workflow
   can still continue; such descriptions are clearly marked as fallback.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import Path

from coursebook_agent.agent.llm import LLMClient, LLMError
from coursebook_agent.models import (
    ParsedResource,
    ResourceDescription,
)

logger = logging.getLogger(__name__)


SYSTEM = """你是一名高校课程资料编目员。你的读者是"课程成书"工作流的主 Agent：它无法阅读资料原文，只能靠你的描述来规划全书章节、决定每份资料用在哪些章节。你的描述是它决策的全部依据。

这份资料可能是课堂转写、课件、讲义、论文、教学大纲、习题等任意一种。无论载体是什么，请输出一份 Markdown 描述，必须包含以下五个二级标题（顺序固定）：

## 形态与性质
3-5 条：资料类型（讲授转写/课件/讲义/论文/大纲/习题…）、形式特征、来源与载体质量（噪声、乱码、缺失、不可辨处）、体量。资料类型必须明确判定；载体质量问题必须写。

## 内容板块
按内容出现顺序分块，数量由内容决定（一般 4-8 块）。每块写：主题名 + 2-4 句（讲了什么、怎么讲/怎么呈现的）+ 篇幅占比。硬性要求：覆盖全文，各块占比合计约 100%，不许只挑重点。

## 独特价值
3-6 条：只写这份资料独有的内容——讲解、点评、案例、推导、直觉解释。每条注明出自哪个板块。不许写其他资料也有的通用内容。

## 术语、关键词与可用性
术语与关键词 5-15 条：核心术语、人名/模型名/缩写的规范写法；若资料中的写法有误或不一致（转写错字、简称、异写），给出「资料写法 → 规范写法」对照。可用性 2-5 条：可跳过或压缩的部分、不完整处、口语化/噪声程度。

## 章节归属建议
2-5 条：这份资料适合进入教辅书的哪些主题章节，角色是什么（主干素材/案例/附录）。每条带一句理由。这是建议，不是结论。

忠实性规则：
1. 只写资料中出现的内容，禁止用外部知识补充细节或顺手介绍背景。
2. 原文听不清、自相矛盾或明显有误之处，标注 [待核]。
3. 数字、人名、研究结论必须来自原文。
4. 全文 1200-2500 字。"""

REPAIR_TEMPLATE = """下面是一份课程资料描述，但它没有按规定的五个二级标题组织。请把它整理为规定格式，只保留原描述中出现过的内容，不要新增事实。

规定格式（顺序固定）：
## 形态与性质
## 内容板块
## 独特价值
## 术语、关键词与可用性
## 章节归属建议

原描述：
<<<
{output}
>>>"""

HEADINGS = (
    "## 形态与性质",
    "## 内容板块",
    "## 独特价值",
    "## 术语、关键词与可用性",
    "## 章节归属建议",
)

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


def _build_user_prompt(parsed: ParsedResource) -> str:
    """Carrier facts + full parsed text.  The filename/position in the title
    is real evidence and is passed through; inferring "lecture N" from it is
    the LLM's judgement, not ours."""
    page_info = f"{parsed.page_count} 页" if parsed.page_count else "页数未知"
    return (
        "资料载体事实：\n"
        f"- 标题/文件名：{parsed.title}\n"
        f"- 资料类型：{parsed.kind}\n"
        f"- 来源：{parsed.provider or parsed.source_type}\n"
        f"- 结构单元数：{len(parsed.units)}（{page_info}）\n\n"
        "资料原文：\n<<<\n"
        f"{parsed.raw_text}\n"
        ">>>"
    )


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t)
        t = re.sub(r"\n```$", "", t)
    return t.strip()


def _five_part_ok(body: str) -> bool:
    if not body:
        return False
    return "## 内容板块" in body and sum(h in body for h in HEADINGS) >= 4


async def describe_resource(
    parsed: ParsedResource,
    *,
    client: LLMClient | None = None,
) -> ResourceDescription:
    """Generate one five-part description via the LLM; fall back on failure."""
    body = ""
    if parsed.raw_text:
        llm = client or LLMClient(max_retries=3, timeout=300)
        user = _build_user_prompt(parsed)
        try:
            raw = await llm.complete(SYSTEM, user, temperature=0.2)
            body = _strip_fences(raw)
            if not _five_part_ok(body):
                # One format-repair pass before giving up on the LLM.
                repair = await llm.complete(
                    SYSTEM,
                    REPAIR_TEMPLATE.format(output=body[:8000]),
                    temperature=0,
                )
                repaired = _strip_fences(repair)
                if _five_part_ok(repaired):
                    body = repaired
        except (LLMError, ValueError, TypeError) as exc:
            logger.warning("describe_resource(%s) LLM failed: %s; using heuristic", parsed.revision_id, exc)
            body = ""
    if not _five_part_ok(body):
        return _heuristic_description_obj(parsed)
    return _coerce(parsed, body)


def _section_text(body: str, heading: str) -> str:
    if heading not in body:
        return ""
    tail = body.split(heading, 1)[1]
    for h in HEADINGS:
        if h != heading and h in tail:
            tail = tail.split(h, 1)[0]
    return tail.strip()


def _first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip().lstrip("#*-—· ").strip()
        if line:
            return line
    return ""


def _derive_structured(parsed: ParsedResource, text: str) -> dict:
    """Deterministic scope/role/usable derivation shared by both paths."""
    if _looks_like_course_scope(parsed.title, text):
        scope, role, usable = "course", "global_constraint", ["policy"]
    elif _looks_like_topic_supplement(parsed.title, text):
        scope, role, usable = "topic", "auxiliary", ["example", "exercise"]
    elif parsed.kind == "transcript":
        scope, role, usable = "lecture", "primary", ["definition", "example"]
    else:
        scope, role, usable = "topic", "primary", ["definition"]
    return {"scope": scope, "suggested_role": role, "usable_content_kinds": usable}


def _heuristic_body(parsed: ParsedResource, text: str, terms: list[str]) -> str:
    """Deterministic five-part body used only when the LLM fails."""
    units = len(parsed.units)
    chars = len(text)
    return (
        "## 形态与性质\n"
        f"- 类型：{parsed.kind}（来源 {parsed.provider or parsed.source_type}），共 {units} 个结构单元，约 {chars} 字符。\n"
        "- **本描述由本地规则生成（模型调用失败或返回不合格式），语义信息缺失，仅保证结构。**\n\n"
        "## 内容板块\n"
        f"- {parsed.title or '未命名资料'}：原文结构单元若干，内容未经理解，需人工或后续重跑补全。\n\n"
        "## 独特价值\n"
        "- 未知（本地规则无法提取语义价值）。\n\n"
        "## 术语、关键词与可用性\n"
        "- 术语候选（按词频机械提取，未校验）：" + "、".join(terms[:10]) + "。\n"
        "- 可用性未知；本描述为降级产物，规划时应列入待核。\n\n"
        "## 章节归属建议\n"
        "- 无法给出可靠建议（降级产物）。\n"
    )


def _heuristic_description_obj(parsed: ParsedResource) -> ResourceDescription:
    text = parsed.raw_text or " ".join(u.text for u in parsed.units[:20])
    terms = _extract_candidate_terms(text, k=10)
    body = _heuristic_body(parsed, text, terms)
    return _coerce(parsed, body, fallback=True)


def _coerce(parsed: ParsedResource, body: str, *, fallback: bool = False) -> ResourceDescription:
    derived = _derive_structured(parsed, body)
    content = _section_text(body, "## 内容板块")
    topic = _first_line(content)[:60] or (parsed.title or "").strip()
    plain = re.sub(r"[#*`>\-—·]", "", body)
    summary = re.sub(r"\s+", " ", plain).strip()[:160]
    knowledge = _extract_candidate_terms(body, k=12)
    return ResourceDescription(
        revision_id=parsed.revision_id,
        resource_id=parsed.resource_id,
        kind=parsed.kind,
        source_type=parsed.source_type,
        provider=parsed.provider,
        title=parsed.title,
        body=body,
        topic=topic,
        knowledge_topics=knowledge,
        scope=derived["scope"],
        related_lecture_ids=[],
        usable_content_kinds=derived["usable_content_kinds"],
        suggested_role=derived["suggested_role"],
        summary=summary if not fallback else (
            f"{parsed.kind} 资料，共 {len(parsed.units)} 个结构单元，约 "
            f"{len(parsed.raw_text)} 字符。（本描述由本地规则生成，因模型调用失败）"
        ),
        overlap_notes=[],
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
