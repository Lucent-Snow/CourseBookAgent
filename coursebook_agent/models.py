"""Core domain models for the subtitle-only coursebook workflow."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── 课程与讲次 ──────────────────────────────────────────────────────────────

class Course(BaseModel):
    course_id: str
    name: str
    teacher: str | None = None
    term: str | None = None


class Lecture(BaseModel):
    lecture_id: str
    course_id: str
    title: str
    index: int
    date: str | None = None
    duration: int | None = None
    lecturer_name: str | None = None


class TranscriptSegment(BaseModel):
    lecture_id: str
    index: int
    start_sec: int
    end_sec: int
    text: str


class TimedChunk(BaseModel):
    """A readable, source-addressable unit sent to the model."""

    chunk_id: str
    lecture_id: str
    start_sec: int
    end_sec: int
    text: str
    source_segment_indices: list[int] = Field(default_factory=list)

    @property
    def citation(self) -> str:
        return f"字幕 {format_timestamp(self.start_sec)}–{format_timestamp(self.end_sec)}"


# ── 第1层：压缩摘要（给主编看的） ─────────────────────────────────────────

class KnowledgePoint(BaseModel):
    """A single knowledge point extracted from a lecture, for the smart editor."""

    name: str  # e.g. "α错误"
    description: str  # dense, one-liner for editor
    category: str = ""  # concept | formula | example | procedure | fact
    chunk_refs: list[str] = Field(default_factory=list)  # which chunks contain this
    time_refs: list[str] = Field(default_factory=list)  # e.g. ["05:30-12:40"]
    sufficiency: str = "sufficient"  # sufficient | partial | insufficient — 字幕对该知识点的支撑程度
    sufficiency_note: str = ""  # 充分性评估说明，如"只有口头描述，缺少具体数值"


class LectureDigest(BaseModel):
    """Dense knowledge-point map of one lecture, targeted at a smart editor.

    The editor understands what "假设检验" means. It just needs to know:
    "this lecture teaches it via X, Y, Z, with examples A and B."
    """

    lecture_id: str
    index: int
    raw_title: str
    teacher_flow: str  # 2-4 sentences: how the teacher structured this lecture
    knowledge_points: list[KnowledgePoint] = Field(default_factory=list)
    key_examples: list[str] = Field(default_factory=list)  # brief refs with time
    administrative_content: list[str] = Field(default_factory=list)  # announcements, etc.
    transitions: list[str] = Field(default_factory=list)  # what the teacher said connecting topics
    duration_estimate: str = ""  # e.g. "01:45:00"
    chunk_count: int = 0
    total_chars: int = 0
    asr_quality_notes: list[str] = Field(default_factory=list)


# ── 第2层：主编统筹 ────────────────────────────────────────────────────────

class ComponentSpec(BaseModel):
    """A reusable UI/content component the editor defines for the book."""

    name: str  # e.g. "tip_box", "worked_example", "warning", "side_note"
    description: str  # what it looks like and when to use
    fields: list[str]  # e.g. ["title", "body", "source_ref"]
    usage_instruction: str  # how chapter writers should use it
    example: str = ""  # a sample instance


class ChapterInstruction(BaseModel):
    """The editor's writing instruction for one chapter."""

    lecture_id: str
    index: int
    book_title: str
    module_name: str
    chapter_role: str = "core"  # core | review | guest | admin | mixed
    narrative_purpose: str = ""
    learning_goals: list[str] = Field(default_factory=list)
    must_cover: list[str] = Field(default_factory=list)
    de_emphasize: list[str] = Field(default_factory=list)
    prerequisite_concepts: list[str] = Field(default_factory=list)
    bridge_from_prev: str = ""
    bridge_to_next: str = ""
    canonical_terms: list[str] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    section_plan: list[str] = Field(default_factory=list)
    component_usage: list[str] = Field(default_factory=list)  # which components to use and how
    depth_guidance: str = ""  # "this chapter needs step-by-step" vs "high-level overview"
    must_verify: list[str] = Field(default_factory=list)  # 字幕支撑不足的知识点，写作者须谨慎处理


class BookPlan(BaseModel):
    """The editor's complete plan for the book."""

    course_id: str
    book_title: str
    audience: str = ""
    book_positioning: str = ""
    learning_path: list[str] = Field(default_factory=list)
    modules: list[dict] = Field(default_factory=list)
    global_emphasis: list[str] = Field(default_factory=list)
    canonical_glossary: list[str] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)
    # Component system
    components: list[ComponentSpec] = Field(default_factory=list)
    # Per-chapter instructions
    chapters: list[ChapterInstruction] = Field(default_factory=list)
    # Shared system prompt for chapter writers
    writer_system_prompt: str = ""
    # Rendering hints
    render_config: dict = Field(default_factory=dict)  # e.g. {"pdf_omit_timestamps": True}
    warnings: list[str] = Field(default_factory=list)


# ── 第3层：章节产物 ────────────────────────────────────────────────────────

class ChapterComponent(BaseModel):
    """An instance of a component within a chapter."""

    component_type: str  # matches ComponentSpec.name
    data: dict = Field(default_factory=dict)  # e.g. {"title": "...", "body": "...", "source_ref": "c005@05:30"}


class ChapterSection(BaseModel):
    heading: str
    content: str
    source_chunk_ids: list[str] = Field(default_factory=list)
    emphasis: str = "normal"  # normal | key | review
    components: list[ChapterComponent] = Field(default_factory=list)
    time_links: list[str] = Field(default_factory=list)  # e.g. ["05:30-12:40 → c005"]


class LectureDraft(BaseModel):
    quality_metrics: dict = Field(default_factory=dict)
    quality_report: dict = Field(default_factory=dict)
    lecture_id: str
    title: str
    overview: str
    concepts: list[str] = Field(default_factory=list)
    sections: list[ChapterSection] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)
    source_ranges: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Book-aware fields
    chapter_role: str = "core"
    learning_goals: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    bridge_from_prev: str = ""
    bridge_to_next: str = ""
    prerequisite_concepts: list[str] = Field(default_factory=list)
    module_name: str = ""
    # Chapter-level components (tips, sidebars, etc.)
    chapter_components: list[ChapterComponent] = Field(default_factory=list)
    # Source links for web reader
    transcript_links: list[dict] = Field(default_factory=list)  # [{"label": "c005", "start": 330, "end": 760}]


# ── 第4层：全书产物 ────────────────────────────────────────────────────────

class CourseBook(BaseModel):
    course: Course
    title: str
    chapters: list[LectureDraft] = Field(default_factory=list)
    glossary: list[str] = Field(default_factory=list)
    source_index: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Book-level editorial layer
    preface: str = ""
    how_to_use: list[str] = Field(default_factory=list)
    knowledge_map: list[str] = Field(default_factory=list)
    learning_path: list[str] = Field(default_factory=list)
    key_point_index: list[str] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)
    quality_notes: list[str] = Field(default_factory=list)
    # Component specs carried to renderer
    components: list[ComponentSpec] = Field(default_factory=list)
    render_config: dict = Field(default_factory=dict)


class JobState(BaseModel):
    error_code: str | None = None
    request: dict = Field(default_factory=dict)
    events: list[dict] = Field(default_factory=list)
    job_id: str
    course_id: str = ""
    status: str
    step: str
    progress: int = 0
    message: str = ""
    error: str | None = None
    book: CourseBook | None = None
    chapters: list[dict] = Field(default_factory=list)  # 每讲生成摘要，实时更新


def format_timestamp(seconds: int | float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
