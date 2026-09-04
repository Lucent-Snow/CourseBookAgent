"""Teaching signal extraction from cleaned subtitle chunks.

Pure rule-based extraction — zero LLM calls. Identifies emphasis, questions,
corrections, examples, and administrative content in classroom transcripts.
"""

from __future__ import annotations

import re

from coursebook_agent.models import TeachingSignal, TimedChunk, TranscriptSegment


# ── Signal patterns ────────────────────────────────────────────────────────

EMPHASIS_PATTERNS = [
    r"重要", r"关键", r"考试", r"记住", r"注意", r"特别", r"必须",
    r"重点", r"核心", r"一定", r"千万", r"务必", r"强调",
    r"这个要掌握", r"这个地方要注意", r"这个很关键",
]

QUESTION_PATTERNS = [
    r"为什么", r"怎么做", r"怎么理解", r"你们觉得",
    r"想一想", r"思考一下", r"谁知道", r"大家想",
]

CORRECTION_PATTERNS = [
    r"不要", r"错误", r"容易错", r"千万别", r"不是.*?而是",
    r"注意.*?不要", r"避免", r"误区", r"误解", r"混淆",
    r"不要写成", r"不能", r"切忌",
]

EXAMPLE_PATTERNS = [
    r"例[如说]?[，,：:]", r"举个例子", r"假设", r"比如",
    r"举个简单的例子", r"以.*?为例", r"例如",
]

ADMIN_KEYWORDS = [
    r"签到", r"作业", r"考试.*?通知", r"通知", r"提交",
    r"助教", r"上课.*?时间", r"下课", r"请假", r"考勤",
    r"成绩", r"总评", r"小测", r"期末", r"钉钉",
    r"上课.*?开始", r"好.*?我们开始", r"我们开始上课",
]


def _has_pattern(text: str, patterns: list[str]) -> list[str]:
    """Return matched patterns found in text."""
    return [p for p in patterns if re.search(p, text)]


def extract_signals(text: str) -> list[TeachingSignal]:
    """Extract teaching signals from a single chunk of text."""
    signals: list[TeachingSignal] = []

    for pattern in EMPHASIS_PATTERNS:
        m = re.search(pattern, text)
        if m:
            signals.append(TeachingSignal(
                signal_type="emphasis",
                matched_text=m.group(),
                confidence=0.9,
            ))
            break  # one emphasis signal per chunk is enough

    for pattern in QUESTION_PATTERNS:
        m = re.search(pattern, text)
        if m:
            signals.append(TeachingSignal(
                signal_type="question",
                matched_text=m.group(),
                confidence=0.85,
            ))
            break

    for pattern in CORRECTION_PATTERNS:
        m = re.search(pattern, text)
        if m:
            signals.append(TeachingSignal(
                signal_type="correction",
                matched_text=m.group(),
                confidence=0.85,
            ))
            break

    for pattern in EXAMPLE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            signals.append(TeachingSignal(
                signal_type="example",
                matched_text=m.group(),
                confidence=0.8,
            ))
            break

    admin_matches = _has_pattern(text, ADMIN_KEYWORDS)
    if admin_matches:
        signals.append(TeachingSignal(
            signal_type="admin",
            matched_text=admin_matches[0],
            confidence=0.7,
        ))

    return signals


def annotate_chunks(chunks: list[TimedChunk]) -> list[TimedChunk]:
    """Add teaching signals to a list of chunks in-place."""
    for chunk in chunks:
        chunk.signals = extract_signals(chunk.text)
    return chunks


def annotate_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    """Add teaching signals to raw transcript segments."""
    for seg in segments:
        signals = extract_signals(seg.text)
        if signals:
            seg.__dict__["_signals"] = [s.signal_type for s in signals]
    return segments


def has_signal(chunk: TimedChunk, signal_type: str) -> bool:
    """Check if a chunk has a specific signal type."""
    return any(s.signal_type == signal_type for s in chunk.signals)


def signal_summary(chunk: TimedChunk) -> str:
    """Human-readable summary of teaching signals in a chunk."""
    if not chunk.signals:
        return ""
    types = [s.signal_type for s in chunk.signals]
    return f"信号：{'、'.join(types)}"
