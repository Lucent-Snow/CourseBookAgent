"""Stage-by-stage lab interface for prompt iteration.

Each `CourseBookPipeline.run()` stage is exposed as an idempotent
operation that returns cached output when present, runs the stage on
cache miss, and writes back to the same cache layout the pipeline uses.

Operators iterate prompts in ``coursebook_agent/agent/*.py`` between lab
runs. The cache is invalidated per stage so a `--force` rerun picks up
the new prompts.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coursebook_agent.agent.chapter import generate_chapter_from_context_with_fallback
from coursebook_agent.agent.describe import cache_path_for, describe_resource, describe_with_cache
from coursebook_agent.agent.editor import (
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
    BookPlan,
    ChapterContext,
    Course,
    CourseBook,
    LectureDraft,
    ResourceDescription,
)
from coursebook_agent.product.service import ProductService
from coursebook_agent.product.snapshot_loader import LoadedResources, load_snapshot
from coursebook_agent.storage import atomic_write_text

logger = logging.getLogger(__name__)

STAGES: tuple[str, ...] = ("describe", "plan", "assemble", "generate", "synthesize")


@dataclass
class StageStatus:
    """Snapshot of one pipeline stage's cache state."""

    stage: str
    state: str  # "empty" | "cached"
    count: int = 0
    files: list[str] = field(default_factory=list)


@dataclass
class LabRunResult:
    """What a stage run produced, with metadata for CLI / API."""

    stage: str
    state: str  # "cached" | "fresh" | "partial"
    count: int
    duration_ms: int
    payload_path: str | None = None


class LabService:
    """Idempotent per-stage operator for the multi-resource pipeline."""

    def __init__(self, snapshot_id: str, course_id: str | None = None) -> None:
        if not snapshot_id:
            raise ValueError("snapshot_id 必填")
        self.snapshot_id = snapshot_id
        self.course_id = course_id
        self.intermediate_dir = config.data_dir / "intermediate"
        self.intermediate_dir.mkdir(parents=True, exist_ok=True)
        self.plans_dir = config.data_dir / "plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self.descriptions_dir = self.intermediate_dir / "descriptions"
        self.descriptions_dir.mkdir(parents=True, exist_ok=True)

    # ── Path helpers ────────────────────────────────────────────────────────

    def description_path(self, revision_id: str) -> Path:
        return cache_path_for(self.descriptions_dir, revision_id)

    def plan_path(self) -> Path:
        return self.plans_dir / f"bookplan-{self.snapshot_id}.json"

    def chapter_path(self, course_id: str, chapter_id: str) -> Path:
        if self.snapshot_id:
            return self.intermediate_dir / f"chapter-{self.snapshot_id}-{chapter_id}.json"
        return self.intermediate_dir / f"chapter-{course_id}-{chapter_id}.json"

    def coursebook_path(self, course_id: str) -> Path:
        key = course_id or self.snapshot_id
        return self.intermediate_dir / f"coursebook-{key}.json"

    # ── Loading ────────────────────────────────────────────────────────────

    def load(self) -> LoadedResources:
        return load_snapshot(self.snapshot_id)

    def dataset_name(self) -> str:
        snapshot = ProductService().get_snapshot(self.snapshot_id)
        return snapshot.dataset_name or snapshot.name or "未命名资料集"

    # ── Status ─────────────────────────────────────────────────────────────

    def status(self) -> dict[str, StageStatus]:
        """Return a per-stage status snapshot. Pure read, no LLM."""
        loaded = self.load()
        descriptions = [self._read_description(r.revision_id) for r in loaded.resources]
        plan = self._read_plan()
        chapter_ids = (
            [c.chapter_id for c in plan.chapters]
            if plan is not None
            else self._infer_chapter_ids_from_cache(loaded)
        )
        chapters = [self._read_chapter(course_id_for_path(loaded), cid) for cid in chapter_ids]
        book = self._read_coursebook(loaded)

        return {
            "describe": StageStatus(
                stage="describe",
                state="cached" if all(descriptions) else "empty",
                count=sum(1 for d in descriptions if d is not None),
                files=[r.revision_id for r, d in zip(loaded.resources, descriptions) if d is not None],
            ),
            "plan": StageStatus(
                stage="plan",
                state="cached" if plan is not None else "empty",
                count=1 if plan is not None else 0,
                files=[str(self.plan_path())] if plan is not None else [],
            ),
            "assemble": StageStatus(
                stage="assemble",
                state="cached" if plan is not None else "empty",
                count=len(plan.chapters) if plan is not None else 0,
            ),
            "generate": StageStatus(
                stage="generate",
                state="cached" if any(chapters) else "empty",
                count=sum(1 for c in chapters if c is not None),
                files=[cid for cid, c in zip(chapter_ids, chapters) if c is not None],
            ),
            "synthesize": StageStatus(
                stage="synthesize",
                state="cached" if book is not None else "empty",
                count=1 if book is not None else 0,
                files=[str(self.coursebook_path(course_id_for_path(loaded)))] if book is not None else [],
            ),
        }

    # ── describe ───────────────────────────────────────────────────────────

    async def run_describe(
        self,
        *,
        force: bool = False,
        revision_id: str | None = None,
        client: LLMClient | None = None,
    ) -> list[ResourceDescription]:
        loaded = self.load()
        if revision_id is not None:
            target = next((r for r in loaded.resources if r.revision_id == revision_id), None)
            if target is None:
                raise ValueError(f"snapshot {self.snapshot_id} 不包含 {revision_id}")
            targets = [target]
        else:
            targets = loaded.resources

        if force:
            if revision_id is not None:
                self.clear_descriptions(revision_id)
            else:
                self.clear_descriptions()

        llm = client or LLMClient(max_retries=3, timeout=180)
        sem = asyncio.Semaphore(4)

        async def one(p: Any) -> ResourceDescription:
            async with sem:
                # describe_with_cache has its own cache; force was handled above
                # by deleting the relevant files.
                return await describe_with_cache(p, cache_dir=self.descriptions_dir, client=llm)

        return list(await asyncio.gather(*[one(p) for p in targets]))

    def clear_descriptions(self, revision_id: str | None = None) -> int:
        if revision_id is not None:
            path = self.description_path(revision_id)
            if path.exists():
                path.unlink()
                return 1
            return 0
        removed = 0
        for p in self.descriptions_dir.glob("description-*.json"):
            p.unlink()
            removed += 1
        return removed

    def list_descriptions(self) -> list[ResourceDescription]:
        loaded = self.load()
        return [d for d in (self._read_description(r.revision_id) for r in loaded.resources) if d is not None]

    # ── plan ───────────────────────────────────────────────────────────────

    async def run_plan(
        self,
        *,
        force: bool = False,
        client: LLMClient | None = None,
    ) -> BookPlan:
        loaded = self.load()
        path = self.plan_path()
        if not force and path.exists():
            try:
                return load_plan(path)
            except (OSError, ValueError):
                pass

        descriptions = self.list_descriptions()
        if not descriptions:
            raise RuntimeError("plan 之前必须先跑 describe：当前 snapshot 没有可用 description")

        course = self._resolve_course(loaded)
        llm = client or LLMClient(max_retries=3, timeout=180)
        try:
            plan = await plan_book_from_descriptions(
                course, descriptions, client=llm, snapshot_id=self.snapshot_id,
            )
        except Exception as exc:
            logger.warning("plan_book_from_descriptions failed (%s); using heuristic fallback", exc)
            plan = heuristic_plan_by_topic(course, descriptions, snapshot_id=self.snapshot_id)
            plan.warnings.append(f"主 Agent 不可用，已使用按资料逐章的启发式回退：{exc}")
        save_plan(plan, path)
        return plan

    def clear_plan(self) -> int:
        path = self.plan_path()
        if path.exists():
            path.unlink()
            return 1
        return 0

    def _read_plan(self) -> BookPlan | None:
        path = self.plan_path()
        if not path.exists():
            return None
        try:
            return load_plan(path)
        except (OSError, ValueError):
            return None

    # ── assemble ───────────────────────────────────────────────────────────

    async def run_assemble(self, *, force: bool = False) -> list[ChapterContext]:
        """assemble 是纯函数：plan + parsed → ChapterContext[]。force 也会重算。"""
        loaded = self.load()
        plan = self._read_plan()
        if plan is None:
            raise RuntimeError("assemble 之前必须先跑 plan")
        return assemble_chapter_contexts(plan, loaded.resources, course=self._resolve_course(loaded), snapshot_id=self.snapshot_id)

    # ── generate ───────────────────────────────────────────────────────────

    async def run_generate(
        self,
        *,
        chapter_id: str,
        force: bool = False,
        review: bool = True,
        client: LLMClient | None = None,
    ) -> LectureDraft:
        loaded = self.load()
        course = self._resolve_course(loaded)
        course_id = course.course_id or self.snapshot_id

        plan = self._read_plan()
        if plan is None:
            raise RuntimeError("generate 之前必须先跑 plan")

        contexts = assemble_chapter_contexts(
            plan, loaded.resources, course=course, snapshot_id=self.snapshot_id,
        )
        order = {c.chapter.chapter_id: c for c in contexts}
        ctx = order.get(chapter_id)
        if ctx is None:
            raise ValueError(f"chapter_id {chapter_id} 不在 plan 中")

        cache_path = self.chapter_path(course_id, chapter_id)
        if not force and cache_path.exists():
            try:
                cached = LectureDraft.model_validate_json(cache_path.read_text(encoding="utf-8"))
                if cached.chapter_id == chapter_id:
                    return cached
            except (OSError, ValueError):
                pass

        # Find previous draft in plan order for bridge.
        plan_chapter_ids = [c.chapter_id for c in plan.chapters]
        prev_draft = None
        if chapter_id in plan_chapter_ids:
            idx = plan_chapter_ids.index(chapter_id)
            if idx > 0:
                prev_id = plan_chapter_ids[idx - 1]
                prev_path = self.chapter_path(course_id, prev_id)
                if prev_path.exists():
                    try:
                        prev_draft = LectureDraft.model_validate_json(prev_path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        pass

        draft = await generate_chapter_from_context_with_fallback(
            ctx, previous_draft=prev_draft, review=review, client=client,
        )
        atomic_write_text(cache_path, draft.model_dump_json(indent=2))
        return draft

    def list_chapters(self) -> list[LectureDraft]:
        plan = self._read_plan()
        if plan is not None:
            ids = [c.chapter_id for c in plan.chapters]
        else:
            ids = self._infer_chapter_ids_from_cache(self.load())
        loaded = self.load()
        cid = course_id_for_path(loaded)
        out: list[LectureDraft] = []
        for chap_id in ids:
            draft = self._read_chapter(cid, chap_id)
            if draft is not None:
                out.append(draft)
        return out

    def clear_chapter(self, chapter_id: str) -> int:
        loaded = self.load()
        cid = course_id_for_path(loaded)
        path = self.chapter_path(cid, chapter_id)
        if path.exists():
            path.unlink()
            return 1
        return 0

    def clear_chapters(self) -> int:
        loaded = self.load()
        cid = course_id_for_path(loaded)
        removed = 0
        for p in self.intermediate_dir.glob(f"chapter-{self.snapshot_id}-*.json"):
            p.unlink()
            removed += 1
        for p in self.intermediate_dir.glob(f"chapter-{cid}-*.json"):
            p.unlink()
            removed += 1
        return removed

    # ── synthesize ─────────────────────────────────────────────────────────

    async def run_synthesize(self, *, force: bool = False) -> CourseBook:
        loaded = self.load()
        course = self._resolve_course(loaded)
        course_id = course.course_id or self.snapshot_id

        plan = self._read_plan()
        chapters = self.list_chapters()
        if plan is None:
            raise RuntimeError("synthesize 之前必须先跑 plan")
        if not chapters:
            raise RuntimeError("synthesize 之前必须先跑 generate")

        cache_path = self.coursebook_path(course_id)
        if not force and cache_path.exists():
            try:
                cached = CourseBook.model_validate_json(cache_path.read_text(encoding="utf-8"))
                if len(cached.chapters) == len(chapters):
                    return cached
            except (OSError, ValueError):
                pass

        llm = LLMClient(max_retries=2, timeout=180)
        book = await synthesize_book(course, chapters, plan=plan, client=llm)
        book.components = plan.components
        book.render_config = plan.render_config
        book.snapshot_id = self.snapshot_id
        atomic_write_text(cache_path, book.model_dump_json(indent=2))
        return book

    # ── Internal reads ─────────────────────────────────────────────────────

    def _read_description(self, revision_id: str) -> ResourceDescription | None:
        path = self.description_path(revision_id)
        if not path.exists():
            return None
        try:
            return ResourceDescription.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _read_chapter(self, course_id: str, chapter_id: str) -> LectureDraft | None:
        path = self.chapter_path(course_id, chapter_id)
        if not path.exists():
            return None
        try:
            return LectureDraft.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _read_coursebook(self, loaded: LoadedResources) -> CourseBook | None:
        cid = course_id_for_path(loaded)
        path = self.coursebook_path(cid)
        if not path.exists():
            return None
        try:
            return CourseBook.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _infer_chapter_ids_from_cache(self, loaded: LoadedResources) -> list[str]:
        cid = course_id_for_path(loaded)
        prefix = f"chapter-{self.snapshot_id}-"
        out: list[str] = []
        for p in self.intermediate_dir.glob(f"{prefix}*.json"):
            out.append(p.stem[len(prefix):])
        if out:
            return sorted(out)
        prefix = f"chapter-{cid}-"
        for p in self.intermediate_dir.glob(f"{prefix}*.json"):
            out.append(p.stem[len(prefix):])
        return sorted(out)

    def _resolve_course(self, loaded: LoadedResources) -> Course:
        if loaded.course is not None:
            return loaded.course
        return Course(course_id=self.course_id or "", name=self.dataset_name())


def course_id_for_path(loaded: LoadedResources) -> str:
    return loaded.course.course_id if loaded.course and loaded.course.course_id else ""
