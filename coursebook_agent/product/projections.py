"""Read-only projections over the existing generation job model."""

from __future__ import annotations

from coursebook_agent.models import JobState
from coursebook_agent.product.models import AgentProjection, ArtifactSummary, RunProjection


def _phase(state: JobState) -> str:
    if state.status == "queued":
        return "queued"
    if state.status in {"failed", "partial", "interrupted"}:
        return "attention"
    if state.status == "completed":
        return "completed"
    message = f"{state.step} {state.message}"
    if "规划" in message or "压缩" in message or "字幕" in message:
        return "prepare"
    if "合成" in message:
        return "synthesize"
    if "质量" in message or "审校" in message:
        return "quality"
    return "write"


def project_run(state: JobState) -> RunProjection:
    requested = [int(item) for item in state.request.get("lecture_indices", []) if str(item).isdigit()]
    summaries = {int(item["index"]): item for item in state.chapters if str(item.get("index", "")).isdigit()}
    indices = requested or sorted(summaries)
    agents: list[AgentProjection] = []
    for index in indices:
        chapter = summaries.get(index)
        status = "pending"
        if chapter:
            status = "failed" if chapter.get("status") == "failed" else "succeeded"
        agents.append(AgentProjection(
            agent_id=f"{state.job_id}-chapter-{index}",
            label=chapter.get("title", f"第 {index} 讲") if chapter else f"第 {index} 讲",
            status=status,
            step="quality" if chapter and chapter.get("status") == "done" else "write",
            message=chapter.get("error") or ("章节已生成" if chapter else "等待章节生成") if chapter else "等待章节生成",
            retryable=status == "failed",
            error=chapter.get("error") if chapter else None,
            output_available=bool(chapter and chapter.get("status") == "done"),
        ))
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
