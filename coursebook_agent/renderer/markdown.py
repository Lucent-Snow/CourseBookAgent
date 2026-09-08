"""Markdown renderer with component support."""

from __future__ import annotations

from coursebook_agent.models import CourseBook, LectureDraft, ChapterSection, ChapterComponent
from coursebook_agent.quality_categories import group_warnings


def _is_empty_chapter(chapter: LectureDraft) -> bool:
    """判断章节是否为空/失败（无正文且导读极短）。"""
    return not chapter.sections and len(chapter.overview.strip()) < 20


_COMPONENT_HEADERS = {
    "worked_example": "【例题】",
    "tip_box": "【小贴士】",
    "warning": "⚠️ 【易错警告】",
    "procedure": "【步骤】",
    "side_note": "【旁注】",
}

_FIELD_LABELS = {
    "title": "标题", "problem": "题目", "problem_statement": "问题陈述",
    "goal": "目标", "key_inequality": "关键不等式", "δ_or_N_choice": "δ/N 的选取",
    "delta_or_N_choice": "δ/N 的选取", "verification_step": "验证步骤",
    "common_fallacy": "常见误区", "context": "语境", "tip": "提示",
    "why_it_works": "原理", "mistake_pattern": "错误模式", "why_wrong": "错误原因",
    "correct_pattern": "正确写法", "evidence_from_class": "课堂证据",
    "body": "正文", "steps": "步骤", "conclusion": "结论",
    "source_ref": "来源", "when_to_use": "适用场景",
}


def _as_lines(value) -> list[str]:
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str):
        return value.splitlines()
    return [str(value)]


def _render_component(comp: ChapterComponent) -> str:
    """Render a component instance to Markdown.

    兼容 v1（title/body/source_ref）与 v2（problem_statement/goal/…、
    context/tip/why_it_works、mistake_pattern/why_wrong/…）两套字段。
    """
    d = comp.data or {}
    header = _COMPONENT_HEADERS.get(comp.component_type, "【补充说明】")
    title = str(d.get("title") or "").strip()
    lines = [f"> **{header}" + (f"：{title}" if title else "") + "**"]

    # 正文块：procedure 优先 steps，其余类型优先 body，二者都有则都渲染。
    block_keys = ["steps", "body"] if comp.component_type == "procedure" else ["body", "steps"]
    for key in block_keys:
        value = d.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        for line in _as_lines(value):
            if str(line).strip():
                lines.append(f"> {line}")

    for key, value in d.items():
        if key in {"title", "body", "steps"}:
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        label = _FIELD_LABELS.get(key, key)
        if key == "source_ref":
            lines.append(f"> *来源：{value}*")
        elif key == "when_to_use":
            lines.append(f"> *适用：{value}*")
        else:
            for line in _as_lines(value):
                if str(line).strip():
                    lines.append(f"> **{label}**：{line}")
    return "\n".join(lines) + "\n"


def render_chapter(chapter: LectureDraft) -> str:
    role_label = {
        "core": "核心方法", "review": "复习整合", "guest": "专题/嘉宾",
        "admin": "课程说明", "mixed": "综合",
    }.get(chapter.chapter_role, chapter.chapter_role or "")

    lines = [f"# {chapter.title}", ""]
    meta_bits = []
    if chapter.module_name:
        meta_bits.append(f"模块：{chapter.module_name}")
    if role_label:
        meta_bits.append(f"角色：{role_label}")
    if meta_bits:
        lines.extend([f"> {' · '.join(meta_bits)}", ""])

    if chapter.bridge_from_prev:
        lines.extend(["## 承上", "", chapter.bridge_from_prev.strip(), ""])

    if chapter.learning_goals:
        lines.extend(["## 学习目标", ""])
        lines.extend(f"- {x}" for x in chapter.learning_goals)
        lines.append("")

    lines.extend(["## 本章导读", "", chapter.overview.strip(), ""])

    if chapter.key_points:
        lines.extend(["## 本章重点", ""])
        lines.extend(f"- {x}" for x in chapter.key_points)
        lines.append("")

    if chapter.concepts:
        lines.extend(["## 核心概念", ""])
        lines.extend(f"- {x}" for x in chapter.concepts)
        lines.append("")

    if chapter.prerequisite_concepts:
        lines.extend(["## 先修概念", ""])
        lines.extend(f"- {x}" for x in chapter.prerequisite_concepts)
        lines.append("")

    for index, section in enumerate(chapter.sections, start=1):
        marker = {"key": "（重点）", "review": "（回顾）"}.get(section.emphasis, "")
        lines.extend([f"## {index}. {section.heading}{marker}", ""])
        lines.extend([section.content.strip(), ""])

        # Section-level components
        for comp in section.components:
            lines.append(_render_component(comp))

        # Time links
        if section.time_links:
            time_str = " | ".join(section.time_links)
            lines.append(f"*字幕时间段：{time_str}*")
            lines.append("")

    if chapter.examples:
        lines.extend(["## 课堂例子与补充", ""])
        lines.extend(f"- {x}" for x in chapter.examples)
        lines.append("")

    if chapter.common_mistakes:
        lines.extend(["## 易错点", ""])
        lines.extend(f"- {x}" for x in chapter.common_mistakes)
        lines.append("")

    lines.extend(["## 本章小结", ""])
    lines.extend(f"- {x}" for x in chapter.summary)

    if chapter.bridge_to_next:
        lines.extend(["", "## 启下", "", chapter.bridge_to_next.strip()])

    lines.extend(["", "## 来源", ""])
    lines.extend(f"- {x}" for x in chapter.source_ranges)
    if chapter.warnings:
        lines.extend(["", "## 教师备注", ""])
        for group in group_warnings(chapter.warnings):
            lines.append(f"### {group['label']}")
            lines.extend(f"- {x}" for x in group["items"])
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_coursebook(book: CourseBook) -> str:
    lines = [
        f"# {book.title}",
        "",
        f"> 根据智云课堂字幕自动整理为复习教辅。课程：{book.course.name}；教师：{book.course.teacher or '未提供'}；学期：{book.course.term or '未提供'}。",
        "",
    ]

    if book.preface:
        lines.extend(["## 前言", "", book.preface.strip(), ""])

    if book.how_to_use:
        lines.extend(["## 如何使用本书", ""])
        lines.extend(f"- {x}" for x in book.how_to_use)
        lines.append("")

    if book.knowledge_map:
        lines.extend(["## 知识地图", ""])
        lines.extend(f"- {x}" for x in book.knowledge_map)
        lines.append("")

    if book.learning_path:
        lines.extend(["## 学习路径", ""])
        lines.extend(f"- {x}" for x in book.learning_path)
        lines.append("")

    lines.extend(["## 目录", ""])
    for chapter in book.chapters:
        if _is_empty_chapter(chapter):
            continue
        suffix = f"（{chapter.module_name}）" if chapter.module_name else ""
        lines.append(f"- [{chapter.title}](#{_anchor(chapter.title)}){suffix}")
    lines.append("")

    for chapter in book.chapters:
        if _is_empty_chapter(chapter):
            lines.extend(["---", "", f"# {chapter.title}", "", f"> **本讲内容待生成**", ""])
            continue
        lines.extend(["---", "", render_chapter(chapter).strip(), ""])

    if book.key_point_index:
        lines.extend(["---", "", "# 要点速记", ""])
        lines.extend(f"- {x}" for x in book.key_point_index)
        lines.append("")

    if book.glossary:
        lines.extend(["---", "", "# 全课术语表", ""])
        lines.extend(f"- {x}" for x in book.glossary)
        lines.append("")

    if book.continuity_notes:
        lines.extend(["# 连贯性阅读提示", ""])
        lines.extend(f"- {x}" for x in book.continuity_notes)
        lines.append("")

    if book.quality_notes:
        lines.extend(["# 成书质量备注", ""])
        lines.extend(f"- {x}" for x in book.quality_notes)
        lines.append("")

    if book.source_index:
        lines.extend(["# 来源索引", ""])
        lines.extend(f"- {x}" for x in book.source_index)

    return "\n".join(lines).strip() + "\n"


def _anchor(title: str) -> str:
    return title.strip().lower().replace(" ", "-").replace("：", "")
