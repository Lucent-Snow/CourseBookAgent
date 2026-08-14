"""End-to-end orchestration with four-layer book generation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from coursebook_agent.agent.chapter import _apply_statistical_guardrails, generate_chapter
from coursebook_agent.agent.digest import compress_lecture, compress_lecture_from_cache
from coursebook_agent.agent.editor import load_plan, plan_book, save_plan, heuristic_book_plan
from coursebook_agent.agent.llm import LLMClient
from coursebook_agent.agent.quality import (
    CourseProfile,
    deterministic_quality_gate,
    enforce_component_contract,
    llm_quality_gate,
    load_profile,
    sanitize_examples,
)
from coursebook_agent.agent.synthesize import synthesize_book, synthesize_book_fallback
from coursebook_agent.config import config
from coursebook_agent.models import BookPlan, CourseBook, LectureDraft
from coursebook_agent.preprocess.transcript import chunk_segments, clean_segments
from coursebook_agent.renderer.markdown import render_chapter, render_coursebook
from coursebook_agent.sources.zhiyun import ZhiyunSource


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
        chunks_path.write_text(
            json.dumps([c.model_dump() for c in chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        digest = await compress_lecture(lecture, chunks, client=LLMClient(max_retries=3, timeout=180))
        digest_path.write_text(digest.model_dump_json(indent=2), encoding="utf-8")
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
        profile_path = Path(__file__).resolve().parent.parent / "profiles" / f"{course_id}-v2.json"
        if profile_path.exists():
            try:
                profile = load_profile(profile_path)
            except Exception:
                pass

        # 获取字幕 chunks（无论缓存命中还是重新生成都需要，用于质量门禁）
        segments = await asyncio.to_thread(self.source.get_transcript, lecture, refresh_source)
        chunks = chunk_segments(clean_segments(segments))
        chunks_path = self.intermediate_dir / f"chunks-{lecture.lecture_id}.json"
        chunks_path.write_text(
            json.dumps([c.model_dump() for c in chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # ── 获取草稿：缓存或重新生成 ──────────────────────────────────────────
        if draft_path.exists() and not regenerate:
            draft = _apply_statistical_guardrails(
                LectureDraft.model_validate_json(draft_path.read_text(encoding="utf-8"))
            )
        else:
            # Get previous draft for bridge context
            if previous_draft is None and lecture_index > 1:
                prev = lectures[lecture_index - 2]
                prev_path = self.intermediate_dir / f"chapter-{prev.lecture_id}.json"
                if prev_path.exists():
                    previous_draft = LectureDraft.model_validate_json(prev_path.read_text(encoding="utf-8"))

            draft = await generate_chapter(
                lecture,
                chunks,
                client=LLMClient(max_retries=3, timeout=180),
                review=review,
                instruction=instruction,
                plan=active_plan,
                previous_draft=previous_draft,
                template_skeleton=_get_template_skeleton(profile, instruction),
            )

        # ── 质量门禁 ──────────────────────────────────────────────────────
        # 第一层：组件契约 + 例子清理（始终执行）
        draft = sanitize_examples(enforce_component_contract(draft))

        # 第二层：确定性质量检查（始终执行）
        if profile and instruction:
            det_result = deterministic_quality_gate(draft, instruction, profile, chunks)
            if not det_result.accepted:
                draft.warnings.extend(f"[质量] {issue}" for issue in det_result.issues)

        # 第三层：LLM 审校（review 模式下执行）
        if review and profile and instruction:
            try:
                llm_result = await llm_quality_gate(draft, instruction, profile, chunks)
                if not llm_result.accepted:
                    draft.warnings.extend(f"[审校] {issue}" for issue in llm_result.issues)
            except Exception as exc:
                draft.warnings.append(f"[审校] LLM 审校失败：{exc}")

        # 写盘前应用统计护栏
        draft = _apply_statistical_guardrails(draft)
        draft_path.write_text(draft.model_dump_json(indent=2), encoding="utf-8")
        output_path = config.output_dir / f"lecture-{lecture.index:02d}-{lecture.lecture_id}.md"
        output_path.write_text(render_chapter(draft), encoding="utf-8")
        return draft

    # ── Layer 4: Full course generation ──────────────────────────────────────

    async def generate_course(
        self,
        course_id: str,
        *,
        refresh_source: bool = False,
        regenerate: bool = False,
        review: bool = False,
        use_book_plan: bool = True,
        synthesize: bool = True,
        progress=None,
        only_indices: list[int] | None = None,
        concurrency: int = 3,
    ) -> CourseBook:
        course = await asyncio.to_thread(self.source.get_course, course_id, refresh_source)
        lectures = await asyncio.to_thread(self.source.list_lectures, course_id, refresh_source)

        # Layer 2: Book plan
        plan = None
        if use_book_plan:
            if progress:
                progress(0, max(len(lectures), 1), "总编辑规划全书结构")
            try:
                plan = await self.ensure_book_plan(
                    course_id,
                    refresh=regenerate or not self.plan_path(course_id).exists(),
                    refresh_source=refresh_source,
                    concurrency=concurrency,
                )
            except Exception as exc:
                if progress:
                    progress(0, max(len(lectures), 1), f"全书规划失败：{exc}")
                plan = None

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
                try:
                    chapter = await self.generate_lecture(
                        course_id, position,
                        refresh_source=refresh_source, regenerate=regenerate,
                        review=review, use_book_plan=use_book_plan,
                        previous_draft=None, plan=plan,
                    )
                    chapters_by_pos[position] = chapter
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
            if selected and position not in selected:
                draft_path = self.intermediate_dir / f"chapter-{lecture.lecture_id}.json"
                if draft_path.exists():
                    chapters_by_pos[position] = LectureDraft.model_validate_json(
                        draft_path.read_text(encoding="utf-8")
                    )
                else:
                    chapters_by_pos[position] = LectureDraft(
                        lecture_id=lecture.lecture_id,
                        title=f"第 {position} 讲：{lecture.title}",
                        overview="本章尚未生成。",
                    )
                done += 1
                continue
            tasks.append(gen_one(position, lecture))

        if tasks:
            await asyncio.gather(*tasks)

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
        book_path.write_text(book.model_dump_json(indent=2), encoding="utf-8")
        (config.output_dir / f"coursebook-{course_id}.md").write_text(render_coursebook(book), encoding="utf-8")
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
