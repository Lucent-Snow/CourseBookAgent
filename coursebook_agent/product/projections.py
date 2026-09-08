"""Read-only projections over the existing generation job model."""

from __future__ import annotations

import json

from coursebook_agent.config import config
from coursebook_agent.models import JobState
from coursebook_agent.product.models import AgentProjection, ArtifactSummary, RunProjection


def _phase(state: JobState) -> str:
    if state.status == "queued":
        return "queued"
    if state.status in {"failed", "partial", "interrupted"}:
        return "attention"
    if state.status == "completed":
        return "completed"
    # Map by message keywords in the order the pipeline emits them.
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

    agents: list[AgentProjection] = []
    seen_keys: set[str] = set()

    def push_chapter(chapter: dict, idx: int) -> None:
        cid = str(chapter.get("chapter_id") or f"chapter-{idx}")
        if cid in seen_keys:
            return
        seen_keys.add(cid)
        status_value = chapter.get("status")
        if status_value == "failed":
            status = "failed"
        elif status_value in {"done", "succeeded"}:
            status = "succeeded"
        else:
            status = "pending"
        agents.append(AgentProjection(
            agent_id=f"{state.job_id}-{cid}",
            label=chapter.get("title") or f"第 {idx} 章",
            status=status,
            step="quality" if status == "succeeded" else "write",
            message=chapter.get("error") or ("章节已生成" if status == "succeeded" else "等待章节生成"),
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
    return RunProjection(
        run_id=state.job_id,
        course_id=state.course_id,
        snapshot_id=state.request.get("snapshot_id"),
        preset_id=state.request.get("preset_id", "coursebook"),
        status=state.status,
        phase=_phase(state),
        progress=state.progress,
        message=state.message,
        created_at=created_at,
        updated_at=updated_at,
        active_agents=sum(agent.status == "running" for agent in agents),
        failed_agents=sum(agent.status == "failed" for agent in agents),
        total_agents=len(agents),
        agents=agents,
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
