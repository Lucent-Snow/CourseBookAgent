"""Layer 1: Dense transcript compression for the smart editor.

The editor knows what hypothesis testing is.
It just needs: "this lecture teaches it via X, Y, Z; teacher flowed A→B→C;
key example at 12:30; ASR quality is mediocre."
"""

from __future__ import annotations

import json

from coursebook_agent.agent.llm import LLMClient
from coursebook_agent.config import config
from coursebook_agent.models import (
    KnowledgePoint,
    Lecture,
    LectureDigest,
    TimedChunk,
)

SYSTEM = """你是课堂字幕压缩器。目标读者是一位聪明的总编辑，她知道所有统计学概念是什么，但不知道这门课的老师具体怎么讲的。

你的任务：把一讲完整字幕压缩成知识点地图。

压缩原则：
1. 总编辑知道假设检验是什么，你不需要解释假设检验。你只需要说"老师用反证法引入 H0/H1，区分了 α/β 错误"。
2. 不要写散文。写知识点列表。
3. 每个知识点必须标注它出现在字幕的哪一段（用 chunk_id）。
4. 关键例子要记录：是什么例子、用来说明什么、在字幕哪里出现。
5. 老师的授课流向很重要：先讲了什么、然后转向什么、用什么过渡。
6. 行政内容（签到、作业通知）简要记录即可，不展开。
7. ASR 质量问题单独记录。
8. 只返回 JSON。"""


def _chunks_to_source(chunks: list[TimedChunk]) -> str:
    return "\n\n".join(
        f"[{c.chunk_id} | {c.citation}]\n{c.text}"
        for c in chunks
    )


async def compress_lecture(
    lecture: Lecture,
    chunks: list[TimedChunk],
    client: LLMClient | None = None,
) -> LectureDigest:
    """Compress a full lecture transcript into a dense digest for the editor."""
    if not chunks:
        raise ValueError(f"讲次 {lecture.lecture_id} 没有可用字幕")

    llm = client or LLMClient(max_retries=3, timeout=max(120, config.llm.timeout))
    source = _chunks_to_source(chunks)
    total_chars = sum(len(c.text) for c in chunks)

    prompt = f"""请压缩以下课堂字幕为知识点地图。

讲次信息：第 {lecture.index} 讲，标题“{lecture.title}”，共 {len(chunks)} 段字幕，约 {total_chars} 字。

返回严格 JSON：
{{
  "lecture_id": "{lecture.lecture_id}",
  "index": {lecture.index},
  "raw_title": "{lecture.title}",
  "teacher_flow": "2-4 句话描述老师的授课流向：先讲了什么→然后转向什么→最后收束于什么",
  "knowledge_points": [
    {{
      "name": "知识点名（简洁，如 'α错误' 'F统计量' '最小二乘法'）",
      "description": "一句话说明老师怎么讲的这个点（不解释概念本身，描述教学方式）",
      "category": "concept|formula|example|procedure|fact",
      "chunk_refs": ["c001", "c005"],
      "time_refs": ["05:30-12:40"],
      "sufficiency": "sufficient|partial|insufficient",
      "sufficiency_note": "对该知识点字幕支撑度的简要评估（如：只有口头描述缺少具体数值；公式符号可能不准确；有完整例题演示）"
    }}
  ],
  "key_examples": ["例：用物理考试成绩演示 z 检验（c015, 12:30-18:00）"],
  "administrative_content": ["助教介绍评分标准（c001-c003）"],
  "transitions": ["老师从假设检验转向两类错误时，用信号检测论做类比"],
  "duration_estimate": "01:45:00",
  "chunk_count": {len(chunks)},
  "total_chars": {total_chars},
  "asr_quality_notes": ["公式符号普遍不准确", "专有名词需人工核实"]
}}

压缩约束：
1. knowledge_points 覆盖所有实质知识点，不遗漏。宁多勿少。
2. 每个 point 的 chunk_refs 必须真实存在。可用的 chunk_id：{json.dumps([c.chunk_id for c in chunks])}
3. 不要写成讲义或摘要。这是给主编看的"原始素材清单"。
4. 老师讲了但没解释清楚的概念，在 description 里注明。
5. 公式用文字描述，不要试图用 LaTeX。
6. sufficiency 评估标准：sufficient = 字幕有完整讲解含步骤/数值/例子；partial = 提及但不完整，缺关键环节；insufficient = 仅一笔带过或只有名词。每个知识点都必须评估。

字幕材料：
{source}"""

    data = await llm.complete_json(SYSTEM, prompt, max_tokens=12000)
    return _coerce_digest(data, lecture, chunks, total_chars)


def _coerce_digest(data: dict, lecture: Lecture, chunks: list[TimedChunk], total_chars: int) -> LectureDigest:
    valid_ids = {c.chunk_id for c in chunks}

    kps: list[KnowledgePoint] = []
    for item in data.get("knowledge_points") or []:
        if not isinstance(item, dict):
            continue
        refs = [str(r) for r in (item.get("chunk_refs") or []) if str(r) in valid_ids]
        kps.append(KnowledgePoint(
            name=str(item.get("name") or "未命名知识点"),
            description=str(item.get("description") or ""),
            category=str(item.get("category") or ""),
            chunk_refs=refs,
            time_refs=[str(t) for t in (item.get("time_refs") or [])],
            sufficiency=str(item.get("sufficiency") or "sufficient"),
            sufficiency_note=str(item.get("sufficiency_note") or ""),
        ))

    return LectureDigest(
        lecture_id=lecture.lecture_id,
        index=lecture.index,
        raw_title=lecture.title,
        teacher_flow=str(data.get("teacher_flow") or ""),
        knowledge_points=kps,
        key_examples=[str(x) for x in (data.get("key_examples") or []) if str(x).strip()],
        administrative_content=[str(x) for x in (data.get("administrative_content") or []) if str(x).strip()],
        transitions=[str(x) for x in (data.get("transitions") or []) if str(x).strip()],
        duration_estimate=str(data.get("duration_estimate") or ""),
        chunk_count=len(chunks),
        total_chars=total_chars,
        asr_quality_notes=[str(x) for x in (data.get("asr_quality_notes") or []) if str(x).strip()],
    )


def compress_lecture_from_cache(
    lecture: Lecture,
    chunks: list[TimedChunk],
    digest_path,
) -> LectureDigest:
    """Build a digest from existing chapter draft as fallback (no LLM call)."""
    from pathlib import Path
    from coursebook_agent.models import LectureDraft

    chapter_path = digest_path.parent / f"chapter-{lecture.lecture_id}.json"
    if not chapter_path.exists():
        return _heuristic_digest(lecture, chunks)

    draft = LectureDraft.model_validate_json(chapter_path.read_text(encoding="utf-8"))
    total_chars = sum(len(c.text) for c in chunks)

    kps: list[KnowledgePoint] = []
    for concept in draft.concepts:
        name = concept.split("：")[0].split(":")[0].strip()
        kps.append(KnowledgePoint(
            name=name,
            description=concept,
            category="concept",
        ))

    examples = []
    for ex in draft.examples[:6]:
        examples.append(ex[:120])

    return LectureDigest(
        lecture_id=lecture.lecture_id,
        index=lecture.index,
        raw_title=lecture.title,
        teacher_flow=draft.overview[:200] if draft.overview else "",
        knowledge_points=kps,
        key_examples=examples,
        administrative_content=[],
        transitions=[],
        duration_estimate=draft.source_ranges[-1] if draft.source_ranges else "",
        chunk_count=len(chunks),
        total_chars=total_chars,
        asr_quality_notes=draft.warnings[:3],
    )


def _heuristic_digest(lecture: Lecture, chunks: list[TimedChunk]) -> LectureDigest:
    total_chars = sum(len(c.text) for c in chunks)
    # Take first 3 chunks as "sample" for teacher_flow
    sample = " ".join(c.text[:200] for c in chunks[:3])
    return LectureDigest(
        lecture_id=lecture.lecture_id,
        index=lecture.index,
        raw_title=lecture.title,
        teacher_flow=f"字幕样本：{sample[:300]}",
        knowledge_points=[],
        key_examples=[],
        administrative_content=[],
        transitions=[],
        chunk_count=len(chunks),
        total_chars=total_chars,
    )
