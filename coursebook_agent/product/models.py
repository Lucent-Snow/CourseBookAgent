"""Domain models for the product workbench application layer."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ResourceKind = Literal["zhiyun_course", "transcript", "pptx", "pdf", "docx", "markdown", "text"]
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
    source_ref: str | None = None
    created_at: str
    updated_at: str
    current_revision: ResourceRevision | None = None


class ResourcePreview(BaseModel):
    revision: ResourceRevision
    text: str


class ZhiyunImportRequest(BaseModel):
    course_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")


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
