"""End-to-end orchestration for the multi-resource book generation flow.

The single entry point is ``CourseBookPipeline.run``, described in
``docs/WORKFLOW.md`` and ``docs/decisions/009-multi-resource-workflow.md``:

    snapshot -> parse -> describe -> main-Agent plan + Tag -> assemble
    chapter contexts -> one chapter Agent per chapter -> quality gate ->
    synthesise -> render.

The Tag is a context-affinity label assigned by the main Agent:
``chapter`` resources enter one or more specific chapters; ``global``
resources enter every chapter's global context; resources without a tag
are not used in the run.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from coursebook_agent.agent.chapter import generate_chapter_from_context_with_fallback
from coursebook_agent.agent.describe import describe_with_cache
from coursebook_agent.agent.editor import (
    ensure_plan_source_coverage,
    heuristic_plan_by_topic,
    load_plan,
    plan_book_from_descriptions,
    save_plan,
)
from coursebook_agent.agent.llm import LLMClient
from coursebook_agent.agent.synthesize import synthesize_book
from coursebook_agent.assembly.assemble import assemble_chapter_contexts
from coursebook_agent.config import config
from coursebook_agent.models import (
    Course,
    CourseBook,
    LectureDraft,
    ParsedResource,
    ResourceDescription,
)
from coursebook_agent.product.snapshot_loader import (
    load_course_resources_from_zhiyun,
    load_snapshot,
)
from coursebook_agent.renderer.markdown import render_coursebook
from coursebook_agent.sources.zhiyun import ZhiyunSource
from coursebook_agent.storage import atomic_write_text

logger = logging.getLogger(__name__)


class CourseBookPipeline:
    """Pipeline that drives the multi-resource workflow end-to-end."""

    def __init__(self, source: ZhiyunSource | None = None) -> None:
        self.source = source or ZhiyunSource()
        self.intermediate_dir = config.data_dir / "intermediate"
        self.intermediate_dir.mkdir(parents=True, exist_ok=True)
        self.plans_dir = config.data_dir / "plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)

    # ── Path helpers ────────────────────────────────────────────────────────

    def _description_cache_dir(self) -> Path:
        path = config.data_dir / "intermediate" / "descriptions"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _plan_path_for(self, snapshot_id: str) -> Path:
        return self.plans_dir / f"bookplan-{snapshot_id}.json"

    def _chapter_cache_path(self, course_id: str, snapshot_id: str | None, chapter_id: str) -> Path:
        """Resolve the chapter cache file, scoped per snapshot when known.

        chapter_id alone is not unique across runs of different courses or
        snapshots, so the legacy ``chapter-{cid}.json`` filename can leak
        one course's content into another's UI. Scope by snapshot when
        available; fall back to course_id; fall back to chapter_id.
        """
        if snapshot_id:
            return self.intermediate_dir / f"chapter-{snapshot_id}-{chapter_id}.json"
        return self.intermediate_dir / f"chapter-{course_id}-{chapter_id}.json"

    async def _describe_all(
        self, parsed: list[ParsedResource]
    ) -> list[ResourceDescription]:
        cache_dir = self._description_cache_dir()
        sem = asyncio.Semaphore(4)

        async def one(p: ParsedResource) -> ResourceDescription:
            async with sem:
                return await describe_with_cache(p, cache_dir=cache_dir)

        return await asyncio.gather(*[one(p) for p in parsed])

    # ── Top-level entry ─────────────────────────────────────────────────────

    async def run(
        self,
        *,
        snapshot_id: str | None = None,
        course_id: str | None = None,
        dataset_name: str = "",
        regenerate: bool = False,
        review: bool = True,
        concurrency: int = 3,
        progress=None,
        chapter_indices: list[int] | None = None,
    ) -> CourseBook:
        """Run the multi-resource workflow end-to-end.

        Either ``snapshot_id`` or ``course_id`` must be provided; callers
        driven by the product workbench supply ``snapshot_id`` and may
        pass ``course_id`` as metadata.

        Persists (relative to ``config.data_dir``):
          - ``intermediate/descriptions/description-<rev_id>.json``
          - ``plans/bookplan-<snapshot_id>.json``
          - ``intermediate/chapter-<snapshot_id>-<chapter_id>.json``
          - ``intermediate/coursebook-<course_id>.json``
          - ``output/coursebook-<course_id>.md``
        """
        if not snapshot_id and not course_id:
            raise ValueError("snapshot_id 或 course_id 必须提供其一")

        loaded = await asyncio.to_thread(load_snapshot, snapshot_id) if snapshot_id else None
        if loaded is None:
            assert course_id is not None
            loaded = await asyncio.to_thread(load_course_resources_from_zhiyun, course_id)

        # Prefer the dataset name (product workbench metadata) over the
        # Zhiyun course name. course_id is only preserved when the caller
        # actually supplied one.
        course = loaded.course
        if course is None:
            course = Course(course_id="", name=dataset_name or "未命名资料集")
        else:
            if dataset_name and dataset_name != course.name:
                course = Course(
                    course_id=course.course_id if course_id else "",
                    name=dataset_name or course.name,
                    teacher=course.teacher,
                    term=course.term,
                )
            if not course_id:
                course = Course(course_id="", name=course.name, teacher=course.teacher, term=course.term)

        parsed = loaded.resources
        if not parsed:
            raise ValueError("本次运行没有任何可解析的资料")

        # Stage 1: parse already done (load_snapshot / load_course_resources_from_zhiyun).
        if progress:
            progress(0, 7, f"已解析 {len(parsed)} 份资料")

        # Stage 2: per-resource description.
        descriptions = await self._describe_all(parsed)

        if progress:
            progress(1, 7, f"已生成 {len(descriptions)} 份 description")

        plan_path = self._plan_path_for(snapshot_id) if snapshot_id else self.plans_dir / f"bookplan-{course.course_id}.json"
        if plan_path.exists() and not regenerate:
            plan = load_plan(plan_path)
        else:
            try:
                plan = await plan_book_from_descriptions(
                    course, descriptions,
                    client=LLMClient(max_retries=3, timeout=900),
                    snapshot_id=snapshot_id,
                )
            except Exception as exc:
                logger.warning("plan_book_from_descriptions failed (%s); using heuristic fallback", exc)
                plan = heuristic_plan_by_topic(course, descriptions, snapshot_id=snapshot_id)
                plan.warnings.append(f"主 Agent 不可用，已使用按资料逐章的启发式回退：{exc}")
            save_plan(plan, plan_path)

        if not plan.chapters:
            raise ValueError("主 Agent 未产出任何章节")

        if progress:
            progress(2, 7, "校验规划的资料覆盖，必要时修复 Tag")
        plan = await ensure_plan_source_coverage(plan, descriptions)
        save_plan(plan, plan_path)

        # Restrict to a subset of chapters if asked.
        selected = set(chapter_indices or list(range(1, len(plan.chapters) + 1)))
        selected_contexts = [c for i, c in enumerate(plan.chapters, start=1) if i in selected]
        plan_chapter_ids = [c.chapter_id for c in plan.chapters]

        # Stage 3: main Agent has planned (caller-visible message carries the
        # chapter count so the operator can verify Tag semantics).
        if progress:
            n_global = len(plan.global_resource_ids)
            n_chapter_total = sum(len(v) for v in plan.chapter_resources.values())
            progress(
                2, 7,
                f"主 Agent 规划 {len(plan.chapters)} 章（{n_global} 份全局、{n_chapter_total} 份章节资料）",
            )

        contexts = assemble_chapter_contexts(
            plan, parsed, course=course, snapshot_id=snapshot_id,
        )
        # Re-order contexts to match plan order, then filter.
        order_index = {c.chapter.chapter_id: i for i, c in enumerate(contexts)}
        contexts.sort(key=lambda c: order_index.get(c.chapter.chapter_id, 1_000_000))
        contexts = [c for c in contexts if c.chapter.chapter_id in {sc.chapter_id for sc in selected_contexts}]

        # Stage 4: assemble chapter contexts by Tag.
        if progress:
            progress(3, 7, f"已按 Tag 组装 {len(contexts)} 个章节上下文")

        sem = asyncio.Semaphore(max(1, concurrency))
        results: list[LectureDraft] = []
        failures: list[str] = []
        done = 0
        total = len(contexts)

        async def gen_one(ctx) -> LectureDraft:
            async with sem:
                chapter_id = ctx.chapter.chapter_id
                draft_path = self._chapter_cache_path(course.course_id, snapshot_id, chapter_id)
                if draft_path.exists() and not regenerate:
                    try:
                        existing = LectureDraft.model_validate_json(draft_path.read_text(encoding="utf-8"))
                        if _can_reuse_chapter(existing, ctx):
                            return existing
                    except (OSError, ValueError):
                        pass
                prev_draft = None
                idx = next((i for i, c in enumerate(contexts) if c.chapter.chapter_id == chapter_id), None)
                if idx is not None and idx > 0:
                    prev_id = contexts[idx - 1].chapter.chapter_id
                    prev_path = self._chapter_cache_path(course.course_id, snapshot_id, prev_id)
                    if prev_path.exists():
                        try:
                            prev_draft = LectureDraft.model_validate_json(prev_path.read_text(encoding="utf-8"))
                        except (OSError, ValueError):
                            pass
                try:
                    draft = await generate_chapter_from_context_with_fallback(
                        ctx, previous_draft=prev_draft, review=review,
                    )
                    atomic_write_text(draft_path, draft.model_dump_json(indent=2))
                    return draft
                except Exception as exc:
                    failed = LectureDraft(
                        chapter_id=chapter_id,
                        title=ctx.chapter.book_title,
                        overview="本章生成失败。",
                        warnings=[str(exc)],
                        used_resource_ids=[r.revision_id for r in ctx.chapter_resources] + [r.revision_id for r in ctx.global_resources],
                    )
                    atomic_write_text(draft_path, failed.model_dump_json(indent=2))
                    failures.append(f"章节 {chapter_id} 失败：{exc}")
                    return failed

        tasks = [gen_one(c) for c in contexts]
        for coro in asyncio.as_completed(tasks):
            draft = await coro
            results.append(draft)
            done += 1
            if progress:
                progress(4 + done / total, 7, f"已生成 {done}/{total} 章", _chapter_progress_summary(draft))

        # Order results by chapter order in the plan.
        order = {c.chapter_id: i for i, c in enumerate(plan.chapters)}
        results.sort(key=lambda d: order.get(d.chapter_id, 1_000_000))

        # Stage 6: synthesise full book.
        if progress:
            progress(6, 7, "全书合成中")

        book = await synthesize_book(
            course, results, plan=plan, client=LLMClient(max_retries=2, timeout=900),
        )
        book.warnings.extend(failures)
        book.components = plan.components
        book.render_config = plan.render_config
        book.snapshot_id = snapshot_id

        book_path = self.intermediate_dir / f"coursebook-{course.course_id or snapshot_id}.json"
        atomic_write_text(book_path, book.model_dump_json(indent=2))
        atomic_write_text(config.output_dir / f"coursebook-{course.course_id or snapshot_id}.md", render_coursebook(book))

        # Stage 7: render complete.
        if progress:
            progress(7, 7, "课程教辅生成完成")
        return book


def _can_reuse_chapter(draft: LectureDraft, context) -> bool:
    expected = {r.revision_id for r in context.chapter_resources + context.global_resources}
    return (
        draft.chapter_id == context.chapter.chapter_id
        and bool(expected)
        and set(draft.used_resource_ids) == expected
        and any(section.content.strip() for section in draft.sections)
        and not any("确定性回退" in warning for warning in draft.warnings)
    )


def _chapter_progress_summary(chapter: LectureDraft, *, failed: bool = False) -> dict:
    return {
        "chapter_id": chapter.chapter_id,
        "title": chapter.title,
        "status": "failed" if failed else "done",
        "module_name": chapter.module_name,
        "chapter_role": chapter.chapter_role,
        "sections": [
            {"heading": s.heading, "chars": len(s.content), "components": len(s.components)}
            for s in chapter.sections
        ],
        "total_chars": sum(len(s.content) for s in chapter.sections),
        "components": sum(len(s.components) for s in chapter.sections),
        "learning_goals": len(chapter.learning_goals),
        "key_points": len(chapter.key_points),
        "common_mistakes": len(chapter.common_mistakes),
        "warnings": chapter.warnings[:5],
        "used_resource_ids": chapter.used_resource_ids,
    }
