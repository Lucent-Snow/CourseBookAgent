"""Deterministic transcript cleanup; no facts are invented here."""

from __future__ import annotations

import re

from coursebook_agent.models import TimedChunk, TranscriptSegment

FILLERS = {"嗯", "嗯嗯", "呃", "啊", "哦", "噢", "对", "对对", "是", "是的", "好的", "好", "就是", "这个", "那个"}
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
    return cleaned


def chunk_segments(segments: list[TranscriptSegment], max_chars: int = 900, max_gap_sec: int = 18) -> list[TimedChunk]:
    chunks: list[TimedChunk] = []
    current: list[TranscriptSegment] = []
    char_count = 0

    def flush() -> None:
        nonlocal current, char_count
        if not current:
            return
        chunks.append(TimedChunk(chunk_id=f"c{len(chunks)+1:03d}", lecture_id=current[0].lecture_id, start_sec=current[0].start_sec, end_sec=current[-1].end_sec, text="".join(item.text for item in current), source_segment_indices=[item.index for item in current]))
        current = []
        char_count = 0

    for segment in segments:
        gap = segment.start_sec - current[-1].end_sec if current else 0
        if current and (char_count + len(segment.text) > max_chars or gap > max_gap_sec):
            flush()
        current.append(segment)
        char_count += len(segment.text)
    flush()
    return chunks
