import type { CourseBook } from '@/types'

export type ResourceKind = 'zhiyun_course' | 'transcript' | 'courseware' | 'xuezai_upload' | 'pptx' | 'pdf' | 'docx' | 'markdown' | 'text'
export type Provider = 'zhiyun' | 'xue_zai_zju'

export interface ProviderCourse {
  course_id: string
  name: string
  teacher: string | null
  term: string | null
}

export interface ProviderInspection {
  provider: Provider
  course: ProviderCourse
  lectures: ZhiyunLecture[]
  uploads: Array<{
    upload_id: number
    reference_id: number
    filename: string
    size: number
    module: string
  }>
  content_types: Array<{ key: string; name: string; description: string }>
}

export interface ProviderAuthStatus {
  zhiyun: { authenticated: boolean; username: string }
  xue_zai_zju: { authenticated: boolean; username: string }
}

export interface ZhiyunCourse {
  course_id: string
  name: string
  teacher: string | null
  term: string | null
}

export interface ZhiyunLecture {
  lecture_id: string
  course_id: string
  title: string
  index: number
  duration: number | null
  lecturer_name: string | null
}
export type ParseStatus = 'pending' | 'parsing' | 'ready' | 'failed'

export interface Dataset {
  dataset_id: string
  name: string
  description: string
  created_at: string
  updated_at: string
  resource_count: number
  ready_count: number
}

export interface ResourceRevision {
  revision_id: string
  resource_id: string
  version: number
  filename: string
  mime_type: string
  size_bytes: number
  sha256: string
  parse_status: ParseStatus
  parse_error: string | null
  text_chars: number
  page_count: number | null
  metadata: Record<string, unknown>
  created_at: string
}

export interface Resource {
  resource_id: string
  dataset_id: string
  kind: ResourceKind
  title: string
  source_type: string
  provider: Provider
  source_ref: string | null
  created_at: string
  updated_at: string
  current_revision: ResourceRevision | null
}

export interface InputSnapshot {
  snapshot_id: string
  dataset_id: string
  label: string
  resource_revision_ids: string[]
  resource_count: number
  sha256: string
  created_at: string
}

export interface DatasetDetail {
  dataset: Dataset
  resources: Resource[]
  snapshots: InputSnapshot[]
}

export interface WorkflowStep {
  key: string
  name: string
  description: string
  agent_role: string
  parallel: boolean
}

export interface WorkflowPreset {
  preset_id: string
  name: string
  description: string
  supported_resource_kinds: ResourceKind[]
  steps: WorkflowStep[]
  default_config: Record<string, unknown>
  output_kind: string
}

export interface AgentProjection {
  agent_id: string
  role: string
  label: string
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'blocked'
  step: string
  message: string
  attempt: number
  started_at: string | null
  finished_at: string | null
  retryable: boolean
  error: string | null
  output_available: boolean
}

export interface RunProjection {
  run_id: string
  course_id: string
  snapshot_id: string | null
  preset_id: string
  status: string
  phase: string
  progress: number
  message: string
  created_at: string | null
  updated_at: string | null
  active_agents: number
  failed_agents: number
  total_agents: number
  agents: AgentProjection[]
  artifact_available: boolean
}

export interface ArtifactSummary {
  artifact_id: string
  run_id: string
  course_id: string
  title: string
  kind: string
  status: 'ready' | 'partial'
  chapter_count: number
  created_at: string | null
}

export interface ArtifactDetail {
  artifact: ArtifactSummary
  book: CourseBook
}
