"""Deterministic transcript cleanup; no facts are invented here."""

from __future__ import annotations

import re
from pathlib import Path

from coursebook_agent.models import TimedChunk, TranscriptSegment

FILLERS = {
    "嗯", "嗯嗯", "呃", "啊", "哦", "噢", "对", "对对", "是", "是的", "好的", "好", "就是", "这个", "那个",
    "行", "可以", "没问题", "知道了", "明白", "对吧", "是吧", "是不是", "然后", "然后呢",
    "接下来", "下面", "那什么", "什么", "哪个", "那个啥", "咱们", "大家", "大家啊",
    "同学们", "同学们啊", "来", "来来", "看一下", "看一下啊", "好吧", "好了",
    "那么", "所以说", "所以说呢", "其实", "其实呢", "反正",
    "那个", "这样", "这样子", "那样", "这样子啊",
}
REPEATED_PUNCTUATION = re.compile(r"([，。！？、,.!?])\1+")


def _normalize(text: str) -> str:
    text = re.sub(r"\s+", "", text).strip()
    text = REPEATED_PUNCTUATION.sub(r"\1", text)
    return text


def clean_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    cleaned: list[TranscriptSegment] = []
    previous = ""
    for segment in segments:
        text = _normalize(segment.text)
        if not text or text in FILLERS:
            continue
        if text == previous:
            continue
        cleaned.append(segment.model_copy(update={"text": text}))
        previous = text

    # Merge broken short sentences
    merged: list[TranscriptSegment] = []
    for seg in cleaned:
        if merged and len(seg.text) < 15:
            gap = seg.start_sec - merged[-1].end_sec
            if gap <= 3:
                merged[-1] = merged[-1].model_copy(
                    update={"text": merged[-1].text + seg.text, "end_sec": seg.end_sec}
                )
                continue
        merged.append(seg)
    return merged


def chunk_segments(segments: list[TranscriptSegment], max_chars: int = 900, max_gap_sec: int = 18) -> list[TimedChunk]:
    from coursebook_agent.preprocess.teaching_signals import extract_signals
    chunks: list[TimedChunk] = []
    current: list[TranscriptSegment] = []
    char_count = 0

    def flush() -> None:
        nonlocal current, char_count
        if not current:
            return
        text = "".join(item.text for item in current)
        signals = extract_signals(text)
        chunks.append(TimedChunk(
            chunk_id=f"c{len(chunks)+1:03d}", lecture_id=current[0].lecture_id,
            start_sec=current[0].start_sec, end_sec=current[-1].end_sec,
            text=text, source_segment_indices=[item.index for item in current],
            signals=signals,
        ))
        current = []
        char_count = 0

    for segment in segments:
        gap = segment.start_sec - current[-1].end_sec if current else 0
        should_flush = False
        if current and (char_count + len(segment.text) > max_chars or gap > max_gap_sec):
            should_flush = True
        if should_flush:
            flush()
        current.append(segment)
        char_count += len(segment.text)
    flush()
    return chunks


ADMIN_KEYWORDS = {"签到", "作业", "考试", "通知", "助教", "提交", "钉钉", "考勤", "成绩", "总评", "小测", "期末", "请假"}


def apply_canonical_terms(chunks: list[TimedChunk], profile_path=None):
    """Apply canonical term aliases from course profile to chunk text."""
    if profile_path is None or not Path(profile_path).exists():
        return chunks, []
    from coursebook_agent.agent.quality import load_profile
    try:
        profile = load_profile(profile_path)
    except Exception:
        return chunks, []
    aliases = []
    for entry in profile.canonical_terms:
        for alias in entry.aliases:
            if alias and alias != entry.term:
                aliases.append((alias, entry.term))
    aliases.sort(key=lambda pair: len(pair[0]), reverse=True)
    logs = []
    result = []
    for chunk in chunks:
        text = chunk.text
        for raw, normalized in aliases:
            if raw in text:
                text = text.replace(raw, normalized)
                logs.append({"chunk_id": chunk.chunk_id, "raw": raw, "normalized": normalized})
        result.append(chunk.model_copy(update={"text": text}))
    return result, logs
