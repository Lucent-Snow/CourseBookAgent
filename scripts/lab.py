#!/usr/bin/env python3
"""Stage-by-stage lab runner for prompt iteration.

Usage:
    uv run python scripts/lab.py status    --snapshot snap-1
    uv run python scripts/lab.py describe  --snapshot snap-1 [--force] [--revision rev-abc]
    uv run python scripts/lab.py plan      --snapshot snap-1 [--force]
    uv run python scripts/lab.py assemble  --snapshot snap-1
    uv run python scripts/lab.py generate  --snapshot snap-1 --chapter c1 [--force]
    uv run python scripts/lab.py synthesize --snapshot snap-1 [--force]
    uv run python scripts/lab.py show descriptions|description|plan|chapters|chapter --snapshot snap-1 ...

Output: JSON to stdout, human summary to stderr. The split keeps `jq`
happy while still giving a readable at-a-glance trace in the terminal.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any, Callable

from coursebook_agent.lab import LabService, STAGES, StageStatus


def _emit(payload: Any) -> None:
    """Write the machine-readable result to stdout."""
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, default=_stdout_serializer())
    sys.stdout.write("\n")
    sys.stdout.flush()


def _stdout_serializer():
    """Default JSON encoder that handles Pydantic models and dataclasses."""
    import dataclasses
    from pydantic import BaseModel

    def default(obj: Any) -> Any:
        if isinstance(obj, BaseModel):
            return obj.model_dump(mode="json")
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        if isinstance(obj, set):
            return sorted(obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")
    return default


def _say(message: str) -> None:
    """Write a human-readable progress line to stderr."""
    sys.stderr.write(message.rstrip() + "\n")
    sys.stderr.flush()


async def _timed(coro_factory: Callable[[], Any]) -> tuple[Any, int]:
    """Run an awaitable factory and return (result, duration_ms)."""
    start = time.monotonic()
    result = await coro_factory()
    return result, int((time.monotonic() - start) * 1000)


def _status_summary(status: dict[str, StageStatus]) -> str:
    lines = ["snapshot lab status"]
    for stage in STAGES:
        s = status[stage]
        bar = "✓" if s.state == "cached" else "·"
        detail = ""
        if s.files:
            if len(s.files) <= 3:
                detail = "  ·  " + ", ".join(s.files)
            else:
                detail = f"  ·  {len(s.files)} 个 ({s.files[0]} ...)"
        lines.append(f"  {bar} {stage:<11}  {s.state:<7}  count={s.count}{detail}")
    return "\n".join(lines)


def _describe_summary(results: list[Any]) -> str:
    lines = [f"describe 完成，共 {len(results)} 份 description"]
    for r in results:
        topic = getattr(r, "topic", "") or ""
        summary = (getattr(r, "summary", "") or "")[:80]
        kind = getattr(r, "kind", "?")
        provider = getattr(r, "provider", "?")
        lines.append(f"  · {r.revision_id}  [{provider}/{kind}]  topic={topic!r}")
        if summary:
            lines.append(f"      {summary}...")
    return "\n".join(lines)


def _plan_summary(plan: Any) -> str:
    chapters = list(plan.chapters)
    n_global = len(plan.global_resource_ids)
    n_chapter = sum(len(v) for v in plan.chapter_resources.values())
    lines = [
        f"plan 完成，{len(chapters)} 章 · 全局 {n_global} 份 · 章节 {n_chapter} 份",
        f"  book_title={plan.book_title!r}",
    ]
    for ch in chapters[:8]:
        lines.append(f"  · {ch.chapter_id}  {ch.book_title!r}")
    if len(chapters) > 8:
        lines.append(f"  … 还有 {len(chapters) - 8} 章")
    if plan.warnings:
        lines.append(f"  warnings: {' | '.join(plan.warnings[:3])}")
    return "\n".join(lines)


def _generate_summary(draft: Any) -> str:
    return "\n".join([
        f"generate 完成：chapter_id={draft.chapter_id}",
        f"  title       {draft.title!r}",
        f"  overview    {(draft.overview or '')[:120]}",
        f"  sections    {len(draft.sections)}  ·  components {sum(len(s.components) for s in draft.sections)}",
        f"  warnings    {len(draft.warnings)}",
    ])


def _synthesize_summary(book: Any) -> str:
    return "\n".join([
        f"synthesize 完成：{len(book.chapters)} 章",
        f"  title       {book.title!r}",
        f"  glossary    {len(book.glossary)} 项",
        f"  key_points  {len(book.key_point_index)} 项",
        f"  warnings    {len(book.warnings)}",
    ])


def _assemble_summary(contexts: list[Any]) -> str:
    lines = [f"assemble 完成，{len(contexts)} 个 ChapterContext"]
    for ctx in contexts[:6]:
        chapter = ctx.chapter
        lines.append(
            f"  · {chapter.chapter_id}  global={len(ctx.global_resources)}  chapter={len(ctx.chapter_resources)}"
        )
    if len(contexts) > 6:
        lines.append(f"  … 还有 {len(contexts) - 6} 个")
    return "\n".join(lines)


def _read_description(service: LabService, revision_id: str) -> dict[str, Any]:
    desc = service._read_description(revision_id)
    if desc is None:
        return {"revision_id": revision_id, "cached": False}
    return {"revision_id": revision_id, "cached": True, "description": desc}


def _read_chapter(service: LabService, chapter_id: str) -> dict[str, Any]:
    loaded = service.load()
    cid = course_id_for_path(loaded)
    draft = service._read_chapter(cid, chapter_id)
    if draft is None:
        return {"chapter_id": chapter_id, "cached": False}
    return {"chapter_id": chapter_id, "cached": True, "draft": draft}


def course_id_for_path(loaded: Any) -> str:
    if loaded.course and loaded.course.course_id:
        return loaded.course.course_id
    return ""


# ── Subcommand implementations ────────────────────────────────────────────


async def cmd_status(args: argparse.Namespace) -> int:
    service = LabService(snapshot_id=args.snapshot, course_id=args.course_id)
    status = service.status()
    _emit({"snapshot_id": args.snapshot, "stages": status})
    _say(_status_summary(status))
    return 0


async def cmd_describe(args: argparse.Namespace) -> int:
    service = LabService(snapshot_id=args.snapshot, course_id=args.course_id)
    if not args.force and args.revision is None:
        # Bulk describe: respect cache per resource.
        pass
    if args.force and args.revision is None:
        # Bulk force: clear all description caches first.
        removed = service.clear_descriptions()
        _say(f"force: 已清空 {removed} 个 description 缓存")
    if args.force and args.revision is not None:
        removed = service.clear_descriptions(args.revision)
        _say(f"force: 已清空 {args.revision} 的 description 缓存" if removed else f"force: {args.revision} 没有可清空的缓存")

    _say(f"开始 describe（snapshot={args.snapshot}）")
    results, duration_ms = await _timed(
        lambda: service.run_describe(force=args.force, revision_id=args.revision)
    )
    state = "fresh" if (args.force or args.revision) else "cached-or-fresh"
    _emit({
        "stage": "describe",
        "state": state,
        "duration_ms": duration_ms,
        "count": len(results),
        "descriptions": results,
    })
    _say(_describe_summary(results))
    return 0


async def cmd_plan(args: argparse.Namespace) -> int:
    service = LabService(snapshot_id=args.snapshot, course_id=args.course_id)
    if args.force:
        removed = service.clear_plan()
        _say(f"force: 已清空 plan 缓存" if removed else "force: plan 缓存不存在")
    _say(f"开始 plan（snapshot={args.snapshot}）")
    plan, duration_ms = await _timed(lambda: service.run_plan(force=args.force))
    _emit({
        "stage": "plan",
        "state": "fresh" if args.force else "cached-or-fresh",
        "duration_ms": duration_ms,
        "plan": plan,
    })
    _say(_plan_summary(plan))
    return 0


async def cmd_assemble(args: argparse.Namespace) -> int:
    service = LabService(snapshot_id=args.snapshot, course_id=args.course_id)
    _say(f"assemble（snapshot={args.snapshot}）— 纯函数，每次重算")
    contexts, duration_ms = await _timed(lambda: service.run_assemble())
    _emit({
        "stage": "assemble",
        "duration_ms": duration_ms,
        "count": len(contexts),
        "contexts": [c.model_dump(mode="json") for c in contexts],
    })
    _say(_assemble_summary(contexts))
    return 0


async def cmd_generate(args: argparse.Namespace) -> int:
    if not args.chapter:
        _say("generate 必须指定 --chapter <chapter_id>")
        return 2
    service = LabService(snapshot_id=args.snapshot, course_id=args.course_id)
    if args.force:
        removed = service.clear_chapter(args.chapter)
        _say(f"force: 已清空 {args.chapter} 的 chapter 缓存" if removed else f"force: {args.chapter} 没有可清空的缓存")
    _say(f"开始 generate（snapshot={args.snapshot}，chapter={args.chapter}，review={not args.no_review}）")
    draft, duration_ms = await _timed(
        lambda: service.run_generate(chapter_id=args.chapter, force=args.force, review=not args.no_review)
    )
    _emit({
        "stage": "generate",
        "state": "fresh" if args.force else "cached-or-fresh",
        "duration_ms": duration_ms,
        "draft": draft,
    })
    _say(_generate_summary(draft))
    return 0


async def cmd_synthesize(args: argparse.Namespace) -> int:
    service = LabService(snapshot_id=args.snapshot, course_id=args.course_id)
    if args.force:
        loaded = service.load()
        cid = course_id_for_path(loaded)
        path = service.coursebook_path(cid)
        if path.exists():
            path.unlink()
            _say(f"force: 已清空 CourseBook 缓存")
    _say(f"开始 synthesize（snapshot={args.snapshot}）")
    book, duration_ms = await _timed(lambda: service.run_synthesize(force=args.force))
    _emit({
        "stage": "synthesize",
        "state": "fresh" if args.force else "cached-or-fresh",
        "duration_ms": duration_ms,
        "book": book,
    })
    _say(_synthesize_summary(book))
    return 0


# ── Show ─────────────────────────────────────────────────────────────────


def cmd_show(args: argparse.Namespace) -> int:
    service = LabService(snapshot_id=args.snapshot, course_id=args.course_id)
    target = args.show_target

    if target == "descriptions":
        descriptions = service.list_descriptions()
        _emit({"snapshot_id": args.snapshot, "count": len(descriptions), "descriptions": descriptions})
        _say(_describe_summary(descriptions))
        return 0

    if target == "description":
        if not args.revision:
            _say("show description 需要 --revision <revision_id>")
            return 2
        _emit(_read_description(service, args.revision))
        d = service._read_description(args.revision)
        if d is not None:
            _say(_describe_summary([d]))
        else:
            _say(f"{args.revision} 没有 description 缓存")
        return 0

    if target == "plan":
        plan = service._read_plan()
        if plan is None:
            _emit({"snapshot_id": args.snapshot, "cached": False})
            _say("plan 缓存不存在")
            return 1
        _emit({"snapshot_id": args.snapshot, "cached": True, "plan": plan})
        _say(_plan_summary(plan))
        return 0

    if target == "chapters":
        chapters = service.list_chapters()
        _emit({"snapshot_id": args.snapshot, "count": len(chapters), "chapters": chapters})
        if chapters:
            summary = [f"chapters 缓存共 {len(chapters)} 份"]
            for c in chapters:
                summary.append(f"  · {c.chapter_id}  {c.title!r}")
            _say("\n".join(summary))
        else:
            _say("没有任何 chapter 缓存")
        return 0

    if target == "chapter":
        if not args.chapter:
            _say("show chapter 需要 --chapter <chapter_id>")
            return 2
        data = _read_chapter(service, args.chapter)
        _emit(data)
        d = data.get("draft")
        if d is not None:
            _say(_generate_summary(d))
        else:
            _say(f"{args.chapter} 没有 chapter 缓存")
        return 0

    _say(f"未知 show 子目标：{target}")
    return 2


# ── Argument parser ──────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lab", description="CourseBookAgent 阶段化实验台")
    parser.add_argument("--snapshot", required=True, help="输入快照 ID")
    parser.add_argument("--course-id", default=None, help="可选，覆盖从 snapshot 解析的 course_id")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="查看每个阶段的缓存状态")

    p = sub.add_parser("describe", help="运行 describe 阶段（逐份资料打标）")
    p.add_argument("--force", action="store_true", help="清空缓存后重跑")
    p.add_argument("--revision", default=None, help="只打一份资料的标（保留其他资料的 description）")
    p.set_defaults(func=cmd_describe)

    p = sub.add_parser("plan", help="运行 plan 阶段（主 Agent 生成 BookPlan）")
    p.add_argument("--force", action="store_true", help="清空 plan 缓存后重跑")
    p.set_defaults(func=cmd_plan)

    sub.add_parser("assemble", help="运行 assemble 阶段（按 Tag 装上下文，纯函数）").set_defaults(func=cmd_assemble)

    p = sub.add_parser("generate", help="运行 generate 阶段（单章生成）")
    p.add_argument("--chapter", required=True, help="chapter_id，例如 c1")
    p.add_argument("--force", action="store_true", help="清空该章节缓存后重跑")
    p.add_argument("--no-review", action="store_true", help="跳过 LLM 审校")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("synthesize", help="运行 synthesize 阶段（成书合成）")
    p.add_argument("--force", action="store_true", help="清空 CourseBook 缓存后重跑")
    p.set_defaults(func=cmd_synthesize)

    p = sub.add_parser("show", help="读取并打印阶段产物（不调用 LLM）")
    p.add_argument("show_target", choices=("descriptions", "description", "plan", "chapters", "chapter"))
    p.add_argument("--revision", default=None, help="show description 时指定 revision_id")
    p.add_argument("--chapter", default=None, help="show chapter 时指定 chapter_id")
    p.set_defaults(func=cmd_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    func = args.func
    if asyncio.iscoroutinefunction(func):
        return asyncio.run(func(args))
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
