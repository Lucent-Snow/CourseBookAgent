// 与后端 coursebook_agent/models.py 对应的数据类型（snake_case 保持一致）。

export interface Course {
  course_id: string
  name: string
  teacher: string | null
  term: string | null
}

export interface ChapterComponent {
  component_type: string
  data: Record<string, unknown>
}

export interface ChapterSection {
  heading: string
  content: string
  source_chunk_ids: string[]
  emphasis: 'normal' | 'key' | 'review'
  components: ChapterComponent[]
  time_links: string[]
}

export interface TranscriptLink {
  label: string
  start: number
  end: number
}

export interface LectureDraft {
  quality_metrics?: { traceability?: TraceabilityMetrics }
  lecture_id: string
  title: string
  overview: string
  concepts: string[]
  sections: ChapterSection[]
  examples: string[]
  summary: string[]
  source_ranges: string[]
  warnings: string[]
  chapter_role: string
  learning_goals: string[]
  key_points: string[]
  common_mistakes: string[]
  bridge_from_prev: string
  bridge_to_next: string
  prerequisite_concepts: string[]
  module_name: string
  chapter_components: ChapterComponent[]
  transcript_links: TranscriptLink[]
}

export interface ComponentSpec {
  name: string
  description: string
  fields: string[]
  usage_instruction: string
  example: string
}

export interface CourseBook {
  course: Course
  title: string
  chapters: LectureDraft[]
  glossary: string[]
  source_index: string[]
  warnings: string[]
  preface: string
  how_to_use: string[]
  knowledge_map: string[]
  learning_path: string[]
  key_point_index: string[]
  continuity_notes: string[]
  quality_notes: string[]
  components: ComponentSpec[]
  render_config: Record<string, unknown>
}

export interface CourseListItem {
  course_id: string
  name: string
  teacher: string | null
  term: string | null
}

export interface AuthStatus {
  authenticated: boolean
  username: string
  webvpn: boolean
}

export interface ChapterSummarySection {
  heading: string
  chars: number
  components: number
  time_links: number
}

export interface ChapterSummary {
  index: number
  title: string
  status: 'done' | 'failed'
  module_name?: string
  chapter_role?: string
  sections?: ChapterSummarySection[]
  total_chars?: number
  components?: number
  learning_goals?: number
  key_points?: number
  common_mistakes?: number
  warnings?: string[]
  error?: string
}

export interface JobState {
  course_id: string
  job_id: string
  status: string
  step: string
  progress: number
  message: string
  error: string | null
  book: CourseBook | null
  chapters: ChapterSummary[]
}

export interface LLMSettings {
  base_url: string
  model: string
  api_key_set: boolean
  configured: boolean
}

export interface DataStats {
  cache_bytes: number
  course_count: number
}

export interface Settings {
  llm: LLMSettings
  zhiyun: AuthStatus
  data: DataStats
}

export interface RunSummary {
  run_id: string
  course_id: string
  accepted: number
  rejected: number
  indices: number[]
}

export interface RunChapterResult {
  confirmation?: { confirmed: boolean; note: string; at: string } | null
  index: number
  lecture_id: string
  accepted: boolean
  corrections: number
  attempt?: number
  deterministic?: { accepted: boolean; issues: string[]; metrics?: { traceability?: TraceabilityMetrics } }
  semantic?: { accepted: boolean; issues: string[]; metrics?: { review_status: string } }
}

export interface RunReport {
  course_id?: string
  run_id: string
  profile_version: string
  indices: number[]
  accepted: number
  rejected: number
  results: RunChapterResult[]
}

export interface LectureListItem {
  lecture_id: string
  course_id: string
  title: string
  index: number
  date?: string | null
  duration?: number | null
}

export interface TraceabilityMetrics {
  source_coverage: number
  sections_without_sources: number
  valid_referenced_chunks: number
  invalid_referenced_chunks: number
}

export interface BookSummary {
  course_id: string
  title: string
  chapters: number
}
