"""Read-only projections over the existing generation job model."""

from __future__ import annotations

import json

from coursebook_agent.config import config
from coursebook_agent.models import JobState
from coursebook_agent.product.models import (
    AgentProjection,
    ArtifactSummary,
    QualityReport,
    ResourceProjection,
    RunEvent,
    RunProjection,
    StageProjection,
)


def _description_cache_dir() -> "Path":
    from pathlib import Path
    return Path(config.data_dir) / "intermediate" / "descriptions"


def _load_description(revision_id: str) -> dict | None:
    path = _description_cache_dir() / f"description-{revision_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _load_plan(snapshot_id: str | None, course_id: str | None) -> dict | None:
    for candidate in (
        f"bookplan-{snapshot_id}.json" if snapshot_id else None,
        f"bookplan-{course_id}.json" if course_id else None,
    ):
        if not candidate:
            continue
        plan_path = config.data_dir / "plans" / candidate
        if plan_path.exists():
            try:
                return json.loads(plan_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
    return None


def _load_chapter(snapshot_id: str | None, course_id: str | None, chapter_id: str) -> dict | None:
    for candidate in (
        f"chapter-{snapshot_id}-{chapter_id}.json" if snapshot_id else None,
        f"chapter-{course_id}-{chapter_id}.json" if course_id else None,
    ):
        if not candidate:
            continue
        path = config.data_dir / "intermediate" / candidate
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
    return None


def _phase(state: JobState) -> str:
    if state.status == "queued":
        return "queued"
    if state.status in {"failed", "partial", "interrupted"}:
        return "attention"
    if state.status == "completed":
        return "completed"
    # Prefer the per-resource transparency counters (stage field) when
    # present, falling back to message keywords otherwise.
    stage = getattr(state, "stage", None)
    if stage is not None:
        if getattr(stage, "rendered", False):
            return "completed"
        if getattr(stage, "synthesized", False):
            return "synthesize"
        total = getattr(stage, "chapters_total", 0) or 0
        done = getattr(stage, "chapters_succeeded", 0) + getattr(stage, "chapters_failed", 0)
        if total and done < total:
            return "write"
        if getattr(stage, "assembled_total", 0) and getattr(stage, "assembled", 0) < getattr(stage, "assembled_total", 0):
            return "plan"
        if getattr(stage, "planned", False):
            return "plan"
        if getattr(stage, "described_total", 0) and getattr(stage, "described", 0) < getattr(stage, "described_total", 0):
            return "describe"
    message = f"{state.step} {state.message}"
    if "解析" in message or "描述" in message:
        return "describe"
    if "规划" in message or "Tag" in message or "组装" in message:
        return "plan"
    if "合成" in message or "渲染" in message:
        return "synthesize"
    if "质量" in message or "审校" in message:
        return "quality"
    return "write"


def project_run(state: JobState) -> RunProjection:
    requested = [int(item) for item in (state.request.get("lecture_indices") or []) if str(item).isdigit()]
    requested_chapters = [str(c) for c in (state.request.get("chapter_indices") or []) if str(c)]

    summaries_by_index: dict[int, dict] = {}
    summaries_by_chapter: dict[str, dict] = {}
    for item in state.chapters:
        idx_value = item.get("index")
        if isinstance(idx_value, int) or (isinstance(idx_value, str) and idx_value.isdigit()):
            summaries_by_index[int(idx_value)] = item
        cid = item.get("chapter_id")
        if cid:
            summaries_by_chapter[str(cid)] = item

    # Read the plan cache for the canonical chapter order. The cache file is
    # written by MultiResourceCourseBookPipeline under data/plans/ with the
    # name pattern bookplan-{snapshot_id}.json or bookplan-{course_id}.json.
    canonical_chapter_ids: list[str] = []
    plan: dict | None = None
    snapshot_id = state.request.get("snapshot_id")
    course_id = state.course_id or state.request.get("course_id")
    for candidate in (
        f"bookplan-{snapshot_id}.json" if snapshot_id else None,
        f"bookplan-{course_id}.json" if course_id else None,
    ):
        if not candidate:
            continue
        plan_path = config.data_dir / "plans" / candidate
        if plan_path.exists():
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                canonical_chapter_ids = [c.get("chapter_id") for c in plan.get("chapters", []) if c.get("chapter_id")]
                if canonical_chapter_ids:
                    break
            except (OSError, ValueError):
                pass

    actual_chapters = summaries_by_chapter or {
        item.get("chapter_id"): item for item in state.chapters if item.get("chapter_id")
    }
    # If the caller-supplied lecture_indices is wildly inconsistent with the
    # actual number of chapters produced (e.g. legacy/test fixtures that
    # passed duplicated lecture_indices), trust the actual chapter records.
    if requested and len(requested) > max(len(actual_chapters), 1) * 2:
        requested = []

    # Resolve chapter title with the highest fidelity source we have:
    # chapter_cache > plan > JobState.chapters. This guards against
    # JobState.chapters being polluted by another run with overlapping
    # chapter_ids (c1, c2, ...).
    plan_chapters = plan.get("chapters", []) if plan else []
    plan_title_by_id = {
        c.get("chapter_id"): c.get("book_title") or c.get("title")
        for c in plan_chapters
        if c.get("chapter_id")
    }

    agents: list[AgentProjection] = []
    seen_keys: set[str] = set()

    def push_chapter(chapter: dict, idx: int) -> None:
        cid = str(chapter.get("chapter_id") or f"chapter-{idx}")
        if cid in seen_keys:
            return
        seen_keys.add(cid)
        cached = _load_chapter(snapshot_id, course_id, cid)
        cached_title = (cached or {}).get("title") if cached else None
        title = (
            cached_title
            or plan_title_by_id.get(cid)
            or chapter.get("title")
            or f"第 {idx} 章"
        )
        status_value = chapter.get("status")
        cached_status = (cached or {}).get("status") if cached else None
        if status_value == "failed" or cached_status == "failed":
            status = "failed"
        elif status_value in {"done", "succeeded"} or cached is not None:
            status = "succeeded"
        else:
            status = "pending"
        agents.append(AgentProjection(
            agent_id=f"{state.job_id}-{cid}",
            label=title,
            status=status,
            step="quality" if status == "succeeded" else "write",
            message=chapter.get("error") or ("章节已生成" if status == "succeeded" else "等待章节生成"),
            attempt=state.retry_count + 1,
            retryable=status == "failed",
            error=chapter.get("error"),
            output_available=status == "succeeded",
        ))

    if requested:
        for idx in requested:
            push_chapter(summaries_by_index.get(idx, {}), idx)
    elif requested_chapters:
        # chapter_indices can be either chapter_id strings ("c1") or numeric
        # chapter orderings ("1","2",...).  Resolve against summaries_by_chapter
        # first, then against summaries_by_index.
        for idx, token in enumerate(requested_chapters, start=1):
            if token in summaries_by_chapter:
                push_chapter(summaries_by_chapter[token], idx)
            elif token.isdigit() and int(token) in summaries_by_index:
                push_chapter(summaries_by_index[int(token)], idx)
            else:
                # Skip unknowns so callers that passed an inconsistent legacy
                # sequence (e.g. duplicated numbers) don't manufacture
                # phantom chapters.
                continue

    if not agents:
        # Iterate chapters in the canonical plan order when we have it so
        # the UI shows chapter 1..N by plan, not by completion time.
        if canonical_chapter_ids:
            for idx, cid in enumerate(canonical_chapter_ids, start=1):
                push_chapter(summaries_by_chapter.get(cid, {}), idx)
        else:
            for idx, chapter in enumerate(state.chapters, start=1):
                push_chapter(chapter if chapter else {}, idx)
    # The legacy callback only emits terminal chapter summaries. Keep one explicit
    # active projection so the UI does not infer execution from localized text.
    if state.status == "running" and agents and not any(agent.status == "running" for agent in agents):
        pending = next((agent for agent in agents if agent.status == "pending"), None)
        if pending:
            pending.status = "running"
            pending.message = state.message
    events = state.events
    created_at = events[0].get("at") if events else None
    updated_at = events[-1].get("at") if events else None

    # ── New transparency fields ─────────────────────────────────────────
    snapshot_id = state.request.get("snapshot_id")
    course_id = state.course_id or state.request.get("course_id")
    plan = _load_plan(snapshot_id, course_id)

    resource_tags = plan.get("resource_tags", {}) if plan else {}
    global_resource_ids = set(plan.get("global_resource_ids", []) if plan else [])
    chapter_resources = plan.get("chapter_resources", {}) if plan else {}

    # Per-resource transparency: build from cached descriptions and the
    # snapshot resource revision list.
    service = None
    try:
        from coursebook_agent.product.service import ProductService
        service = ProductService()
        snapshot_obj = service.get_snapshot(snapshot_id) if snapshot_id else None
    except Exception:
        snapshot_obj = None

    resources: list[ResourceProjection] = []
    if snapshot_obj is not None:
        for revision_id in snapshot_obj.resource_revision_ids:
            desc = _load_description(revision_id) or {}
            tags = resource_tags.get(revision_id, [])
            if "__global__" in tags or revision_id in global_resource_ids:
                kind = "global"
                tag_chapters: list[str] = []
            elif tags:
                kind = "chapter"
                tag_chapters = [t for t in tags if t != "__global__"]
            else:
                kind = "none"
                tag_chapters = []
            title = ""
            resource_id = ""
            kind_str = ""
            provider_str = ""
            if service is not None:
                try:
                    rev = service.get_revision(revision_id)
                    res = service.get_resource(rev.resource_id)
                    title = res.title or rev.filename
                    resource_id = rev.resource_id
                    kind_str = res.kind
                    provider_str = res.provider
                except Exception:
                    pass
            resources.append(ResourceProjection(
                revision_id=revision_id,
                resource_id=resource_id,
                title=title or desc.get("title") or "",
                kind=kind_str,
                provider=provider_str,
                description_status="done" if desc else "pending",
                description_text=desc.get("summary", ""),
                description_topic=desc.get("topic", ""),
                description_scope=desc.get("scope", ""),
                description_suggested_role=desc.get("suggested_role", ""),
                tag_kind=kind,
                tag_chapter_ids=tag_chapters,
            ))

    # Stage counters
    selected_run = bool(state.request.get("chapter_indices"))
    assembled_total = len(agents) if selected_run else len(plan_chapters)
    assembled_count = min(
        sum(1 for r in chapter_resources.values() if r),
        assembled_total,
    )
    stage = StageProjection(
        parsed=sum(1 for r in resources if r.description_status != "pending"),
        parsed_total=len(resources),
        described=sum(1 for r in resources if r.description_status == "done"),
        described_total=len(resources),
        planned=bool(plan_chapters),
        plan_summary={
            "chapter_count": len(plan_chapters),
            "selected_chapter_count": len(agents) if selected_run else len(plan_chapters),
            "global_resource_count": len(global_resource_ids),
            "chapter_resource_count": sum(len(v) for v in chapter_resources.values()),
            "module_names": [m.get("name") for m in (plan.get("modules") or [])] if plan else [],
        } if plan else {},
        assembled=assembled_count,
        assembled_total=assembled_total,
        chapters_succeeded=sum(1 for a in agents if a.status == "succeeded"),
        chapters_failed=sum(1 for a in agents if a.status == "failed"),
        chapters_total=len(agents),
        synthesized=bool(state.book) and state.status in {"partial", "completed"},
        rendered=bool(state.book) and state.status == "completed",
    )

    # Quality report: each chapter that has a draft on disk.
    quality: list[QualityReport] = []
    for cid in (plan_chapters and [c.get("chapter_id") for c in plan_chapters if c.get("chapter_id")] or []):
        draft = _load_chapter(snapshot_id, course_id, cid)
        if not draft:
            continue
        sections = draft.get("sections") or []
        warnings: list[str] = []
        used = set(draft.get("used_resource_ids") or [])
        missing_sources: list[str] = []
        for sec in sections:
            for ref in (sec.get("source_chunk_ids") or []):
                if ref not in used:
                    missing_sources.append(ref)
        if not sections:
            warnings.append("章节无小节正文")
        if missing_sources:
            warnings.append(f"{len(missing_sources)} 处小节引用了未在 chapter_used_resource_ids 中的来源")
        if not (draft.get("sections") and (draft.get("concepts") or draft.get("sections")[0].get("content",""))):
            warnings.append("概念与正文薄弱")
        # Pull warnings from both the legacy warnings field and from the
        # components array where the LLM was instructed to put warning_box
        # instances. The LLM sometimes serialises a dict into a string in
        # the warnings field; we try ast.literal_eval to recover it.
        import ast
        for w in draft.get("warnings") or []:
            parsed_w: object = w
            if isinstance(w, str) and w.lstrip().startswith("{"):
                try:
                    parsed_w = ast.literal_eval(w)
                except (ValueError, SyntaxError):
                    parsed_w = None
            if isinstance(parsed_w, dict):
                title = str(parsed_w.get("title") or parsed_w.get("body") or "")
                body = str(parsed_w.get("body") or "")
                if title and body and title != body:
                    warnings.append(f"{title}: {body[:120]}")
                elif title:
                    warnings.append(title)
                else:
                    warnings.append(str(w))
            elif parsed_w is None:
                warnings.append(w[:140] if isinstance(w, str) else str(w))
            else:
                warnings.append(str(parsed_w))
        for sec in sections:
            for comp in (sec.get("components") or []):
                if isinstance(comp, dict) and comp.get("component_type") == "warning":
                    title = str(comp.get("data", {}).get("title") or "")
                    body = str(comp.get("data", {}).get("body") or "")
                    if title:
                        warnings.append(f"{title}: {body[:120]}" if body else title)
        # Cap warning count to avoid front-end overload.
        quality.append(QualityReport(
            chapter_id=cid,
            title=draft.get("title",""),
            section_count=len(sections),
            source_revision_ids=draft.get("used_resource_ids") or [],
            missing_source_count=len(missing_sources),
            component_count=sum(len(s.get("components") or []) for s in sections),
            warnings=warnings[:5],
        ))

    return RunProjection(
        run_id=state.job_id,
        course_id=state.course_id,
        dataset_id=state.dataset_id or state.request.get("dataset_id", ""),
        dataset_name=state.dataset_name or state.request.get("dataset_name", ""),
        snapshot_id=state.request.get("snapshot_id"),
        preset_id=state.request.get("preset_id", "coursebook"),
        status=state.status,
        phase=_phase(state),
        progress=state.progress,
        message=state.message,
        error_code=state.error_code,
        error=state.error,
        retry_count=state.retry_count,
        metrics=state.metrics,
        created_at=created_at,
        updated_at=updated_at,
        active_agents=sum(agent.status == "running" for agent in agents),
        failed_agents=sum(agent.status == "failed" for agent in agents),
        total_agents=len(agents),
        agents=agents,
        resources=resources,
        stage=stage,
        quality=quality,
        events=[RunEvent.model_validate(event) for event in state.events[-80:]],
        artifact_available=state.book is not None,
    )


def project_artifact(state: JobState) -> ArtifactSummary | None:
    if not state.book:
        return None
    created_at = state.events[-1].get("at") if state.events else None
    return ArtifactSummary(
        artifact_id=state.job_id,
        run_id=state.job_id,
        course_id=state.course_id,
        title=state.book.title,
        status="partial" if state.status == "partial" else "ready",
        chapter_count=len(state.book.chapters),
        created_at=created_at,
    )
