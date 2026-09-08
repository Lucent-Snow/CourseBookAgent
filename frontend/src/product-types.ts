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

export interface ResourceProjection {
  revision_id: string
  resource_id: string
  title: string
  kind: string
  provider: string
  description_status: 'pending' | 'running' | 'done' | 'failed'
  description_text: string
  description_topic: string
  description_scope: string
  description_suggested_role: string
  tag_kind: 'chapter' | 'global' | 'none'
  tag_chapter_ids: string[]
}

export interface StageProjection {
  parsed: number
  parsed_total: number
  described: number
  described_total: number
  planned: boolean
  plan_summary: {
    chapter_count: number
    global_resource_count: number
    chapter_resource_count: number
    module_names: string[]
  }
  assembled: number
  assembled_total: number
  chapters_succeeded: number
  chapters_failed: number
  chapters_total: number
  synthesized: boolean
  rendered: boolean
}

export interface QualityReport {
  chapter_id: string
  title: string
  section_count: number
  source_revision_ids: string[]
  missing_source_count: number
  component_count: number
  warnings: string[]
}

export interface RunEvent {
  status: string
  step: string
  progress: number
  message: string
  at: string | null
  error_code?: string | null
  retryable?: boolean
  attempt?: number
}

export interface RunProjection {
  run_id: string
  course_id: string
  dataset_id: string
  dataset_name: string
  snapshot_id: string | null
  preset_id: string
  status: string
  phase: string
  progress: number
  message: string
  error_code: string | null
  error: string | null
  retry_count: number
  metrics: {
    request_count?: number
    successful_requests?: number
    failed_requests?: number
    retry_count?: number
    prompt_tokens?: number
    completion_tokens?: number
    total_tokens?: number
    latency_ms?: number
    models?: string[]
    estimated_cost?: number | null
    cost_currency?: string | null
    cost_configured?: boolean
  }
  created_at: string | null
  updated_at: string | null
  active_agents: number
  failed_agents: number
  total_agents: number
  agents: AgentProjection[]
  resources: ResourceProjection[]
  stage: StageProjection
  quality: QualityReport[]
  events: RunEvent[]
  artifact_available: boolean
}

export interface DatasetRunSummary {
  job_id: string
  status: string | null
  phase: string | null
  progress: number
  message: string
  course_id: string | null
  snapshot_id: string | null
  preset_id: string
  dataset_id: string
  artifact_available: boolean
  updated_at: string | null
  created_at: string | null
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
