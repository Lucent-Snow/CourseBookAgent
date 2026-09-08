"""End-to-end orchestration with the new multi-resource book generation flow.

The legacy 4-layer pipeline is preserved for backward compatibility
(``generate_course``).  ``generate_course_v2`` implements the workflow
described in ``docs/WORKFLOW.md``:

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
import json
import logging
from dataclasses import asdict
from pathlib import Path

from coursebook_agent.agent.chapter import (
    _apply_statistical_guardrails,
    _collect_ranges,
    _build_transcript_links,
    generate_chapter,
    generate_chapter_v2,
    generate_chapter_v2_with_fallback,
)
from coursebook_agent.agent.describe import describe_with_cache
from coursebook_agent.agent.digest import compress_lecture, compress_lecture_from_cache
from coursebook_agent.agent.editor import (
    heuristic_book_plan,
    heuristic_book_plan_v2,
    load_plan,
    plan_book,
    plan_book_v2,
    save_plan,
)
from coursebook_agent.agent.llm import LLMClient
from coursebook_agent.agent.quality import (
    CourseProfile,
    QualityResult,
    deterministic_quality_gate,
    enforce_component_contract,
    fact_verification_gate,
    llm_quality_gate,
    load_profile,
    sanitize_examples,
    traceability_metrics,
)
from coursebook_agent.storage import atomic_write_text
from coursebook_agent.agent.synthesize import synthesize_book, synthesize_book_fallback
from coursebook_agent.config import config
from coursebook_agent.models import (
    BookPlan,
    Course,
    CourseBook,
    LectureDraft,
    ParsedResource,
    ResourceDescription,
)
from coursebook_agent.assembly.assemble import assemble_chapter_contexts
from coursebook_agent.preprocess.transcript import chunk_segments, clean_segments, apply_canonical_terms
from coursebook_agent.product.snapshot_loader import (
    load_course_resources_from_zhiyun,
    load_snapshot,
)
from coursebook_agent.renderer.markdown import render_chapter, render_coursebook
from coursebook_agent.sources.zhiyun import ZhiyunSource

logger = logging.getLogger(__name__)


class CourseBookPipeline:
    def __init__(self, source: ZhiyunSource | None = None):
        self.source = source or ZhiyunSource()
        self.intermediate_dir = config.data_dir / "intermediate"
        self.intermediate_dir.mkdir(parents=True, exist_ok=True)
        self.plans_dir = config.data_dir / "plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)

    def plan_path(self, course_id: str) -> Path:
        return self.plans_dir / f"bookplan-{course_id}.json"

    # ── Layer 1: Digest compression ──────────────────────────────────────────

    async def compress_lecture(
        self, course_id: str, lecture_index: int, *, refresh_source: bool = False
    ):
        """Compress a single lecture's transcript into a digest."""
        lectures = await asyncio.to_thread(self.source.list_lectures, course_id, refresh_source)
        if lecture_index < 1 or lecture_index > len(lectures):
            raise ValueError(f"讲次序号必须在 1-{len(lectures)} 之间")
        lecture = lectures[lecture_index - 1]
        digest_path = self.intermediate_dir / f"digest-{lecture.lecture_id}.json"

        segments = await asyncio.to_thread(self.source.get_transcript, lecture, refresh_source)
        chunks = chunk_segments(clean_segments(segments))

        # Cache chunks too
        chunks_path = self.intermediate_dir / f"chunks-{lecture.lecture_id}.json"
        atomic_write_text(chunks_path,
            json.dumps([c.model_dump() for c in chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        digest = await compress_lecture(lecture, chunks, client=LLMClient(max_retries=3, timeout=180))
        atomic_write_text(digest_path, digest.model_dump_json(indent=2))
        return digest

    async def get_digest(self, course_id: str, lecture_index: int, *, refresh_source: bool = False, refresh: bool = False):
        """Get or build a lecture digest, using cache when available."""
        lectures = await asyncio.to_thread(self.source.list_lectures, course_id, refresh_source)
        if lecture_index < 1 or lecture_index > len(lectures):
            raise ValueError(f"讲次序号必须在 1-{len(lectures)} 之间")
        lecture = lectures[lecture_index - 1]
        digest_path = self.intermediate_dir / f"digest-{lecture.lecture_id}.json"

        if digest_path.exists() and not refresh:
            from coursebook_agent.models import LectureDigest
            return LectureDigest.model_validate_json(digest_path.read_text(encoding="utf-8"))

        # Fallback: build from existing chapter draft
        chunks_path = self.intermediate_dir / f"chunks-{lecture.lecture_id}.json"
        if chunks_path.exists():
            from coursebook_agent.models import TimedChunk
            chunks = [TimedChunk.model_validate(c) for c in json.loads(chunks_path.read_text(encoding="utf-8"))]
            return compress_lecture_from_cache(lecture, chunks, digest_path)

        # Full LLM compression
        return await self.compress_lecture(course_id, lecture_index, refresh_source=refresh_source)

    # ── Layer 2: Book planning ───────────────────────────────────────────────

    async def ensure_book_plan(
        self, course_id: str, *, refresh: bool = False, refresh_source: bool = False, concurrency: int = 3
    ) -> BookPlan:
        path = self.plan_path(course_id)
        if path.exists() and not refresh:
            return load_plan(path)

        course = await asyncio.to_thread(self.source.get_course, course_id, refresh_source)
        lectures = await asyncio.to_thread(self.source.list_lectures, course_id, refresh_source)

        # Build digests for all lectures（并发，信号量限流）
        sem = asyncio.Semaphore(max(1, concurrency))

        async def digest_one(index: int):
            async with sem:
                return await self.get_digest(course_id, index, refresh_source=refresh_source, refresh=False)

        digests = await asyncio.gather(*[digest_one(i) for i in range(1, len(lectures) + 1)])

        try:
            plan = await plan_book(course, digests, client=LLMClient(max_retries=3, timeout=180))
        except Exception as exc:
            plan = heuristic_book_plan(course, digests)
            plan.warnings.append(f"LLM 规划失败，已使用启发式蓝图：{exc}")

        save_plan(plan, path)
        return plan

    # ── Layer 3: Chapter generation ──────────────────────────────────────────

    async def generate_lecture(
        self,
        course_id: str,
        lecture_index: int,
        *,
        refresh_source: bool = False,
        regenerate: bool = False,
        review: bool = True,
        use_book_plan: bool = True,
        previous_draft: LectureDraft | None = None,
        plan: BookPlan | None = None,
    ) -> LectureDraft:
        course = await asyncio.to_thread(self.source.get_course, course_id, refresh_source)
        lectures = await asyncio.to_thread(self.source.list_lectures, course_id, refresh_source)
        if lecture_index < 1 or lecture_index > len(lectures):
            raise ValueError(f"讲次序号必须在 1-{len(lectures)} 之间")
        lecture = lectures[lecture_index - 1]
        draft_path = self.intermediate_dir / f"chapter-{lecture.lecture_id}.json"

        active_plan = plan
        if use_book_plan and active_plan is None:
            try:
                active_plan = await self.ensure_book_plan(course_id, refresh=False, refresh_source=refresh_source)
            except Exception:
                active_plan = None

        # Find chapter instruction from plan（提前提取，质量门禁需要）
        instruction = None
        if active_plan:
            for ch in active_plan.chapters:
                if ch.lecture_id == lecture.lecture_id or ch.index == lecture_index:
                    instruction = ch
                    break

        # 加载课程 profile（质量门禁需要）
        profile: CourseProfile | None = None
        profile_path = Path(__file__).resolve().parent / "profiles" / f"{course_id}-v2.json"
        if profile_path.exists():
            try:
                profile = load_profile(profile_path)
            except Exception:
                pass

        # 获取字幕 chunks（无论缓存命中还是重新生成都需要，用于质量门禁）
        segments = await asyncio.to_thread(self.source.get_transcript, lecture, refresh_source)
        chunks = chunk_segments(clean_segments(segments))

        # 术语规范化（从 profile 加载别名并替换）
        profile_path_for_terms = Path(__file__).resolve().parent.parent / "profiles" / f"{course_id}-v2.json"
        chunks, term_logs = apply_canonical_terms(chunks, profile_path_for_terms)

        chunks_path = self.intermediate_dir / f"chunks-{lecture.lecture_id}.json"
        atomic_write_text(chunks_path,
            json.dumps([c.model_dump() for c in chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # ── 提取模板骨架与范例 ──────────────────────────────────────────────
        template_skeleton = _get_template_skeleton(profile, instruction)
        exemplar_sections = _get_exemplar_sections(profile, instruction)

        # ── 获取上一章草稿用于衔接上下文 ────────────────────────────────────────
        if previous_draft is None and lecture_index > 1:
            prev = lectures[lecture_index - 2]
            prev_path = self.intermediate_dir / f"chapter-{prev.lecture_id}.json"
            if prev_path.exists():
                previous_draft = LectureDraft.model_validate_json(prev_path.read_text(encoding="utf-8"))

        # ── 生成 + 质量门禁重试循环 ──────────────────────────────────────────
        max_attempts = 3
        revision_feedback: list[str] = []

        for attempt in range(max_attempts):
            # ── 获取草稿：缓存或重新生成 ──────────────────────────────────────
            if draft_path.exists() and not regenerate and attempt == 0:
                draft = _apply_statistical_guardrails(
                    LectureDraft.model_validate_json(draft_path.read_text(encoding="utf-8"))
                )
            else:
                draft = await generate_chapter(
                    lecture,
                    chunks,
                    client=LLMClient(max_retries=3, timeout=180),
                    review=review,
                    instruction=instruction,
                    plan=active_plan,
                    previous_draft=previous_draft,
                    template_skeleton=template_skeleton,
                    exemplar_sections=exemplar_sections,
                    revision_feedback=revision_feedback if revision_feedback else None,
                )

            # ── 质量门禁 ──────────────────────────────────────────────────────
            # 第一层：组件契约 + 例子清理（始终执行）
            draft = sanitize_examples(enforce_component_contract(draft))

            quality_issues: list[str] = []
            draft.quality_metrics = {"traceability": traceability_metrics(draft, chunks)}
            trace = draft.quality_metrics["traceability"]
            if trace["source_coverage"] < 1 or not draft.sections:
                quality_issues.append("部分小节没有有效字幕来源")
            draft.quality_report = {
                "deterministic": {"accepted": not quality_issues, "issues": list(quality_issues),
                                  "metrics": draft.quality_metrics},
                "semantic": {"accepted": False, "issues": [], "metrics": {"review_status": "not_run"}},
            }

            # 第二层：确定性质量检查（始终执行）
            if profile and instruction:
                det_result = deterministic_quality_gate(draft, instruction, profile, chunks)
                draft.quality_metrics.update(det_result.metrics)
                draft.quality_report["deterministic"] = asdict(det_result)
                if not det_result.accepted:
                    quality_issues.extend(det_result.issues)

            # 第三层：LLM 审校（review 模式下执行）
            if review and profile and instruction:
                try:
                    llm_result = await llm_quality_gate(draft, instruction, profile, chunks)
                    draft.quality_report["semantic"] = asdict(llm_result)
                    if not llm_result.accepted:
                        quality_issues.extend(llm_result.issues)
                except Exception as exc:
                    quality_issues.append(f"[审校] LLM 审校失败：{exc}")
                    draft.quality_report["semantic"] = {
                        "accepted": False, "issues": [str(exc)], "metrics": {"review_status": "failed"}}
            # 第四层：事实抽检（始终执行，抽样验证字幕支撑）
            fact_result: QualityResult | None = None
            try:
                fact_result = await fact_verification_gate(draft, chunks, sample_size=4)
                draft.quality_metrics["fact_check"] = fact_result.metrics
                if not fact_result.accepted:
                    quality_issues.extend(f"[事实抽检] {issue}" for issue in fact_result.issues)
            except Exception as exc:
                fact_result = QualityResult(False, [f"事实抽检异常：{exc}"], {"status": "failed"})
                draft.quality_metrics["fact_check"] = {"status": "failed"}

            draft.quality_report["fact_check"] = asdict(fact_result)

            # ── 重试判定 ──────────────────────────────────────────────────────
            if not quality_issues:
                break  # 质量通过，退出循环

            if attempt < max_attempts - 1:
                revision_feedback = quality_issues  # 反馈给下一轮生成
            else:
                # 最后一次尝试仍未通过，记录 warnings 并输出
                draft.warnings.extend(f"[质量] {issue}" for issue in quality_issues)

        # 写盘前应用统计护栏
        draft = _apply_statistical_guardrails(draft)
        evidence = [c for c in chunks if c.lecture_id == draft.lecture_id]
        draft.source_ranges = _collect_ranges(draft.sections, evidence)
        draft.transcript_links = _build_transcript_links(draft.sections, evidence)
        by_id = {c.chunk_id: c for c in evidence}
        for section in draft.sections:
            section.time_links = [by_id[cid].citation for cid in dict.fromkeys(section.source_chunk_ids) if cid in by_id]
        draft.quality_report["accepted"] = not quality_issues and draft.quality_report["semantic"]["accepted"]
        atomic_write_text(draft_path, draft.model_dump_json(indent=2))
        output_path = config.output_dir / f"lecture-{lecture.index:02d}-{lecture.lecture_id}.md"
        atomic_write_text(output_path, render_chapter(draft))
        return draft

    async def generate_single_lecture(
        self,
        course_id: str,
        lecture_index: int,
        *,
        refresh_source: bool = False,
        review: bool = True,
    ) -> CourseBook:
        """Generate one lecture without requiring the rest of the course cache.

        This is the first-generation path used by the UI.  A later full-course
        run can reuse the saved chapter and complete the book-level synthesis.
        """
        course = await asyncio.to_thread(self.source.get_course, course_id, refresh_source)
        lectures = await asyncio.to_thread(self.source.list_lectures, course_id, refresh_source)
        if lecture_index < 1 or lecture_index > len(lectures):
            raise ValueError(f"讲次序号必须在 1-{len(lectures)} 之间")
        plan = await self.ensure_book_plan(course_id, refresh=False, refresh_source=refresh_source)
        chapter = await self.generate_lecture(
            course_id,
            lecture_index,
            refresh_source=refresh_source,
            regenerate=True,
            review=review,
            plan=plan,
        )

        book_path = self.intermediate_dir / f"coursebook-{course_id}.json"
        if book_path.exists():
            book = CourseBook.model_validate_json(book_path.read_text(encoding="utf-8"))
            replaced = False
            for position, existing in enumerate(book.chapters):
                if existing.lecture_id == chapter.lecture_id or position == lecture_index - 1:
                    book.chapters[position] = chapter
                    replaced = True
                    break
            if not replaced:
                book.chapters.append(chapter)
        else:
            book = CourseBook(course=course, title=plan.book_title, chapters=[chapter])
            book.components = plan.components
            book.render_config = plan.render_config
        atomic_write_text(book_path, book.model_dump_json(indent=2))
        atomic_write_text(config.output_dir / f"coursebook-{course_id}.md", render_coursebook(book))
        return book

    # ── Layer 4: Full course generation ──────────────────────────────────────

    async def generate_course(
        self,
        course_id: str,
        *,
        refresh_source: bool = False,
        regenerate: bool = False,
        review: bool = True,
        use_book_plan: bool = True,
        synthesize: bool = True,
        progress=None,
        only_indices: list[int] | None = None,
        concurrency: int = 3,
        checkpoint_dir: Path | None = None,
    ) -> CourseBook:
        course = await asyncio.to_thread(self.source.get_course, course_id, refresh_source)
        lectures = await asyncio.to_thread(self.source.list_lectures, course_id, refresh_source)

        # Layer 2: Book plan
        if not lectures:
            raise ValueError("课程没有可生成的讲次")
        if only_indices is not None and any(i < 1 or i > len(lectures) for i in only_indices):
            raise ValueError("重试讲次超出课程范围")
        plan = None
        checkpoint_plan = checkpoint_dir / "plan.json" if checkpoint_dir else None
        if checkpoint_plan and checkpoint_plan.exists():
            plan = load_plan(checkpoint_plan)
        elif use_book_plan:
            if progress:
                progress(0, max(len(lectures), 1), "总编辑规划全书结构")
            try:
                plan = await self.ensure_book_plan(
                    course_id,
                    refresh=(regenerate and only_indices is None) or not self.plan_path(course_id).exists(),
                    refresh_source=refresh_source,
                    concurrency=concurrency,
                )
            except Exception as exc:
                if progress:
                    progress(0, max(len(lectures), 1), f"全书规划失败：{exc}")
                plan = None
        if plan and checkpoint_plan:
            atomic_write_text(checkpoint_plan, plan.model_dump_json(indent=2))
        if checkpoint_dir:
            old_manifest = checkpoint_dir / "lectures.json"
            if old_manifest.exists():
                saved = json.loads(old_manifest.read_text(encoding="utf-8"))
                if [l["lecture_id"] for l in saved] != [l.lecture_id for l in lectures]:
                    raise ValueError("课程讲次已变化，请新建生成任务")
            atomic_write_text(checkpoint_dir / "lectures.json",
                              json.dumps([l.model_dump() for l in lectures], ensure_ascii=False))

        # Layer 3: Generate chapters（并发，信号量限流）
        selected = set(only_indices or [])
        total = len(lectures)
        chapters_by_pos: dict[int, LectureDraft] = {}
        failures: list[str] = []
        done = 0
        sem = asyncio.Semaphore(max(1, concurrency))

        async def gen_one(position: int, lecture) -> None:
            nonlocal done
            summary: dict | None = None
            async with sem:
                # 加载上一章草稿用于衔接上下文
                prev_draft: LectureDraft | None = None
                if position > 1:
                    prev_lecture = lectures[position - 2]
                    prev_path = self.intermediate_dir / f"chapter-{prev_lecture.lecture_id}.json"
                    if prev_path.exists():
                        try:
                            prev_draft = LectureDraft.model_validate_json(prev_path.read_text(encoding="utf-8"))
                        except Exception:
                            pass
                try:
                    chapter = await self.generate_lecture(
                        course_id, position,
                        refresh_source=refresh_source, regenerate=regenerate,
                        review=review, use_book_plan=use_book_plan,
                        previous_draft=prev_draft, plan=plan,
                    )
                    chapters_by_pos[position] = chapter
                    if checkpoint_dir:
                        chunks_path = self.intermediate_dir / f"chunks-{lecture.lecture_id}.json"
                        if chunks_path.exists():
                            atomic_write_text(checkpoint_dir / chunks_path.name, chunks_path.read_text(encoding="utf-8"))
                        atomic_write_text(checkpoint_dir / f"chapter-{lecture.lecture_id}.json",
                                          chapter.model_dump_json(indent=2))
                    summary = _chapter_summary(position, chapter)
                except Exception as exc:
                    failed = LectureDraft(
                        lecture_id=lecture.lecture_id,
                        title=f"第 {position} 讲：{lecture.title}",
                        overview="本讲生成失败。",
                        warnings=[str(exc)],
                    )
                    chapters_by_pos[position] = failed
                    failures.append(f"第 {position} 讲失败：{exc}")
                    summary = {
                        "index": position,
                        "title": f"第 {position} 讲：{lecture.title}",
                        "status": "failed",
                        "error": str(exc),
                    }
                finally:
                    done += 1
                    if progress:
                        progress(done, total, f"生成第 {min(done + 1, total)}/{total} 章", summary)

        tasks = []
        for position, lecture in enumerate(lectures, start=1):
            if only_indices is not None and position not in selected:
                draft_path = self.intermediate_dir / f"chapter-{lecture.lecture_id}.json"
                if checkpoint_dir:
                    draft_path = checkpoint_dir / f"chapter-{lecture.lecture_id}.json"
                if draft_path.exists():
                    chapters_by_pos[position] = LectureDraft.model_validate_json(
                        draft_path.read_text(encoding="utf-8")
                    )
                    if chapters_by_pos[position].lecture_id != lecture.lecture_id:
                        raise ValueError("章节快照与课程讲次不匹配")
                else:
                    raise ValueError(f"第 {position} 讲缓存缺失，无法复用；请重新生成该讲")
                done += 1
                if progress:
                    progress(done, total, "读取已完成章节", _chapter_summary(position, chapters_by_pos[position]))
                continue
            tasks.append((position, lecture))

        if tasks:
            await asyncio.gather(*(gen_one(position, lecture) for position, lecture in tasks))

        chapters = [chapters_by_pos[p] for p in sorted(chapters_by_pos)]

        # Layer 4: Synthesize
        if progress:
            progress(len(lectures), max(len(lectures), 1), "全书合成中")

        if synthesize:
            try:
                book = await synthesize_book(course, chapters, plan=plan, client=LLMClient(max_retries=2, timeout=180))
            except Exception as exc:
                book = synthesize_book_fallback(course, chapters, plan=plan)
                book.warnings.append(f"终审合成失败，已回退：{exc}")
        else:
            book = synthesize_book_fallback(course, chapters, plan=plan)

        book.warnings.extend(failures)
        if plan:
            book.components = plan.components
            book.render_config = plan.render_config

        book_path = self.intermediate_dir / f"coursebook-{course_id}.json"
        atomic_write_text(book_path, book.model_dump_json(indent=2))
        atomic_write_text(config.output_dir / f"coursebook-{course_id}.md", render_coursebook(book))
        if progress:
            progress(len(lectures), max(len(lectures), 1), "课程教辅生成完成")
        return book


def _get_template_skeleton(profile: "CourseProfile | None", instruction) -> str:
    """从 profile 中提取当前章节类型的骨架模板。"""
    if not profile or not instruction:
        return ""
    role = instruction.chapter_role or "core"
    template = profile.chapter_templates.get(role) or profile.chapter_templates.get("core") or {}
    return str(template.get("skeleton", ""))


def _get_exemplar_sections(profile: "CourseProfile | None", instruction) -> list[dict]:
    """从 profile 中提取当前章节类型的 few-shot 范例小节。"""
    if not profile or not instruction:
        return []
    role = instruction.chapter_role or "core"
    template = profile.chapter_templates.get(role) or profile.chapter_templates.get("core") or {}
    exemplars = template.get("exemplar_sections", [])
    if isinstance(exemplars, list):
        return [ex for ex in exemplars if isinstance(ex, dict)]
    return []


def _chapter_summary(index: int, chapter: LectureDraft) -> dict:
    """一讲生成结果的真实摘要，用于前端实时展示。"""
    sections = [
        {
            "heading": s.heading,
            "chars": len(s.content),
            "components": len(s.components),
            "time_links": len(s.time_links),
        }
        for s in chapter.sections
    ]
    return {
        "index": index,
        "title": chapter.title,
        "status": "done",
        "quality_metrics": chapter.quality_metrics,
        "module_name": chapter.module_name,
        "chapter_role": chapter.chapter_role,
        "sections": sections,
        "total_chars": sum(x["chars"] for x in sections),
        "components": sum(x["components"] for x in sections),
        "learning_goals": len(chapter.learning_goals),
        "key_points": len(chapter.key_points),
        "common_mistakes": len(chapter.common_mistakes),
        "warnings": chapter.warnings[:5],
    }


# ── v2 multi-resource orchestration ─────────────────────────────────────────


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


class MultiResourceCourseBookPipeline(CourseBookPipeline):
    """Pipeline that drives the v2 multi-resource workflow.

    Backed by the legacy CourseBookPipeline for shared infra (plans_dir,
    intermediate_dir, renderer, profile loading, synthesise).  Adds the
    description/main-Agent/assemble stages.
    """

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

    async def run(
        self,
        *,
        snapshot_id: str | None = None,
        course_id: str | None = None,
        regenerate: bool = False,
        review: bool = True,
        concurrency: int = 3,
        progress=None,
        chapter_indices: list[int] | None = None,
    ) -> CourseBook:
        """Top-level entry.  Either snapshot_id or course_id must be provided.

        Returns the produced CourseBook and persists:
        - ``intermediate/descriptions/description-<rev>.json``
        - ``plans/bookplan-<snapshot_id>.json``
        - ``intermediate/chapter-<chapter_id>.json``
        - ``intermediate/coursebook-<course_id>.json``
        - ``output/coursebook-<course_id>.md``
        """
        if not snapshot_id and not course_id:
            raise ValueError("snapshot_id 或 course_id 必须提供其一")

        loaded = await asyncio.to_thread(load_snapshot, snapshot_id) if snapshot_id else None
        if loaded is None:
            assert course_id is not None
            loaded = await asyncio.to_thread(load_course_resources_from_zhiyun, course_id)
        course = loaded.course or (Course(course_id=course_id, name=f"课程 {course_id}") if course_id else Course(course_id="unknown", name="未命名课程"))
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

        plan_path = self._plan_path_for(snapshot_id) if snapshot_id else self.plan_path(course.course_id)
        if plan_path.exists() and not regenerate:
            plan = load_plan(plan_path)
        else:
            try:
                plan = await plan_book_v2(
                    course, descriptions,
                    client=LLMClient(max_retries=3, timeout=180),
                    snapshot_id=snapshot_id,
                )
            except Exception as exc:
                logger.warning("plan_book_v2 failed (%s); using heuristic v2 fallback", exc)
                plan = heuristic_book_plan_v2(course, descriptions, snapshot_id=snapshot_id)
                plan.warnings.append(f"主 Agent 不可用，已使用按资料逐章的启发式回退：{exc}")
            save_plan(plan, plan_path)

        if not plan.chapters:
            raise ValueError("主 Agent 未产出任何章节")

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
                        if existing.chapter_id == chapter_id:
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
                    draft = await generate_chapter_v2_with_fallback(
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
            course, results, plan=plan, client=LLMClient(max_retries=2, timeout=180),
        )
        book.warnings.extend(failures)
        book.components = plan.components
        book.render_config = plan.render_config
        book.snapshot_id = snapshot_id

        book_path = self.intermediate_dir / f"coursebook-{course.course_id}.json"
        atomic_write_text(book_path, book.model_dump_json(indent=2))
        atomic_write_text(config.output_dir / f"coursebook-{course.course_id}.md", render_coursebook(book))

        # Stage 7: render complete.
        if progress:
            progress(7, 7, "课程教辅生成完成")
        return book
