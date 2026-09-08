"""Domain models for the product workbench application layer."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ResourceKind = Literal["zhiyun_course", "transcript", "courseware", "xuezai_upload", "pptx", "pdf", "docx", "markdown", "text"]
Provider = Literal["zhiyun", "xue_zai_zju"]
ParseStatus = Literal["pending", "parsing", "ready", "failed"]


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class Dataset(BaseModel):
    dataset_id: str
    name: str
    description: str = ""
    created_at: str
    updated_at: str
    resource_count: int = 0
    ready_count: int = 0


class ResourceRevision(BaseModel):
    revision_id: str
    resource_id: str
    version: int
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    parse_status: ParseStatus
    parse_error: str | None = None
    text_chars: int = 0
    page_count: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class Resource(BaseModel):
    resource_id: str
    dataset_id: str
    kind: ResourceKind
    title: str
    source_type: str
    provider: Provider = "zhiyun"
    source_ref: str | None = None
    created_at: str
    updated_at: str
    current_revision: ResourceRevision | None = None


class ResourcePreview(BaseModel):
    revision: ResourceRevision
    text: str


class ZhiyunImportRequest(BaseModel):
    course_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    lecture_ids: list[str] = Field(default_factory=list)
    content_types: list[Literal["transcript", "courseware"]] = Field(default_factory=lambda: ["transcript"])
    refresh: bool = False


class XueZaiImportRequest(BaseModel):
    course_id: int = Field(ge=1)
    upload_ids: list[int] = Field(default_factory=list)
    refresh: bool = False


class ProviderCourseSummary(BaseModel):
    course_id: str
    name: str
    teacher: str | None = None
    term: str | None = None


class ProviderInspection(BaseModel):
    provider: Provider
    course: ProviderCourseSummary
    lectures: list[dict[str, Any]] = Field(default_factory=list)
    uploads: list[dict[str, Any]] = Field(default_factory=list)
    content_types: list[dict[str, str]] = Field(default_factory=list)


class SnapshotCreate(BaseModel):
    resource_revision_ids: list[str] = Field(min_length=1)
    label: str = Field(default="", max_length=120)


class InputSnapshot(BaseModel):
    snapshot_id: str
    dataset_id: str
    label: str
    resource_revision_ids: list[str]
    resource_count: int
    sha256: str
    created_at: str


class WorkflowStep(BaseModel):
    key: str
    name: str
    description: str
    agent_role: str
    parallel: bool = False


class WorkflowPreset(BaseModel):
    preset_id: str
    name: str
    description: str
    supported_resource_kinds: list[ResourceKind]
    steps: list[WorkflowStep]
    default_config: dict[str, Any]
    output_kind: str


class AgentProjection(BaseModel):
    agent_id: str
    role: str = "chapter_writer"
    label: str
    status: Literal["pending", "running", "succeeded", "failed", "blocked"]
    step: str
    message: str
    attempt: int = 1
    started_at: str | None = None
    finished_at: str | None = None
    retryable: bool = False
    error: str | None = None
    output_available: bool = False


class ResourceProjection(BaseModel):
    """One row of the per-resource transparency table."""
    revision_id: str
    resource_id: str
    title: str
    kind: str
    provider: str
    # Description stage
    description_status: Literal["pending", "running", "done", "failed"] = "pending"
    description_text: str = ""
    description_topic: str = ""
    description_scope: str = ""
    description_suggested_role: str = ""
    # Tag stage (chapter tags as list of chapter_id; "__global__" if global;
    # [] if no tag)
    tag_kind: Literal["chapter", "global", "none"] = "none"
    tag_chapter_ids: list[str] = Field(default_factory=list)


class StageProjection(BaseModel):
    """Run-level stage counters so the front-end can render a step indicator."""
    parsed: int = 0
    parsed_total: int = 0
    described: int = 0
    described_total: int = 0
    planned: bool = False
    plan_summary: dict = Field(default_factory=dict)
    assembled: int = 0
    assembled_total: int = 0
    chapters_succeeded: int = 0
    chapters_failed: int = 0
    chapters_total: int = 0
    synthesized: bool = False
    rendered: bool = False


class QualityReport(BaseModel):
    chapter_id: str
    title: str
    section_count: int
    source_revision_ids: list[str]
    missing_source_count: int
    component_count: int
    warnings: list[str] = Field(default_factory=list)


class RunEvent(BaseModel):
    """A persisted state transition shown in the run activity timeline."""
    status: str = ""
    step: str = ""
    progress: int = 0
    message: str = ""
    at: str | None = None
    error_code: str | None = None
    retryable: bool = False
    attempt: int = 1


class RunProjection(BaseModel):
    run_id: str
    course_id: str = ""
    dataset_id: str = ""
    dataset_name: str = ""
    snapshot_id: str | None = None
    preset_id: str = "coursebook"
    status: str
    phase: str
    progress: int
    message: str
    error_code: str | None = None
    error: str | None = None
    retry_count: int = 0
    metrics: dict = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None
    active_agents: int = 0
    failed_agents: int = 0
    total_agents: int = 0
    agents: list[AgentProjection] = Field(default_factory=list)
    resources: list[ResourceProjection] = Field(default_factory=list)
    stage: StageProjection = Field(default_factory=StageProjection)
    quality: list[QualityReport] = Field(default_factory=list)
    events: list[RunEvent] = Field(default_factory=list)
    artifact_available: bool = False


class ArtifactSummary(BaseModel):
    artifact_id: str
    run_id: str
    course_id: str
    dataset_id: str = ""
    dataset_name: str = ""
    snapshot_id: str | None = None
    title: str
    kind: str = "coursebook"
    status: Literal["ready", "partial"]
    chapter_count: int
    created_at: str | None = None
