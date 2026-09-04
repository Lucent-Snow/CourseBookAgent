"""Markdown renderer with component support."""

from __future__ import annotations

from coursebook_agent.models import CourseBook, LectureDraft, ChapterSection, ChapterComponent


def _render_component(comp: ChapterComponent) -> str:
    """Render a component instance to Markdown."""
    d = comp.data
    title = d.get("title", "")
    body = d.get("body", "")
    source_ref = d.get("source_ref", "")

    if comp.component_type == "worked_example":
        lines = [f"> **【例题】{title}**" if title else "> **【例题】**"]
        if body:
            lines.append(f"> {body}")
        if source_ref:
            lines.append(f"> *来源：{source_ref}*")
        return "\n".join(lines) + "\n"

    if comp.component_type == "tip_box":
        lines = [f"> **{title}**" if title else "> **补充说明**"]
        if body:
            lines.append(f"> {body}")
        return "\n".join(lines) + "\n"

    if comp.component_type == "warning":
        lines = [f"> **【易错】**{title}" if title else "> **【易错】**"]
        if body:
            lines.append(f"> {body}")
        return "\n".join(lines) + "\n"

    if comp.component_type == "procedure":
        lines = [f"> **【步骤】{title}**" if title else "> **【步骤】**"]
        if body:
            for line in body.split("\n"):
                lines.append(f"> {line}")
        when = d.get("when_to_use", "")
        if when:
            lines.append(f"> *适用：{when}*")
        return "\n".join(lines) + "\n"

    if comp.component_type == "side_note":
        lines = [f"> **旁注：**{body}" if body else ""]
        if source_ref:
            lines.append(f"> *来源：{source_ref}*")
        return "\n".join(lines) + "\n"

    # Unknown components are a validation failure upstream. Render their usable
    # content without exposing implementation labels to students as a last resort.
    lines = ["> **补充说明**"]
    if title:
        lines.append(f"> **{title}**")
    if body:
        lines.append(f"> {body}")
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
        lines.extend(["", "## 整理说明", ""])
        lines.extend(f"- {x}" for x in chapter.warnings)
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
        suffix = f"（{chapter.module_name}）" if chapter.module_name else ""
        lines.append(f"- [{chapter.title}](#{_anchor(chapter.title)}){suffix}")
    lines.append("")

    for chapter in book.chapters:
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
