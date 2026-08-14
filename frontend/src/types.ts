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

export interface JobState {
  job_id: string
  status: string
  step: string
  progress: number
  message: string
  error: string | null
  book: CourseBook | null
}
