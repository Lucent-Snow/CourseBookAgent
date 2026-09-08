import type { JobState } from '@/types'
import type {
  ArtifactDetail,
  ArtifactSummary,
  Dataset,
  DatasetDetail,
  DatasetRunSummary,
  InputSnapshot,
  ProviderAuthStatus,
  ProviderInspection,
  Resource,
  RunProjection,
  WorkflowPreset,
  ZhiyunCourse,
} from '@/product-types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `请求失败（${response.status}）`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const productApi = {
  datasets: async () => (await request<{ data: Dataset[] }>('/api/product/datasets')).data,
  createDataset: (name: string, description = '') => request<Dataset>('/api/product/datasets', json({ name, description })),
  dataset: (datasetId: string) => request<DatasetDetail>(`/api/product/datasets/${datasetId}`),
  deleteDataset: (datasetId: string) => request<void>(`/api/product/datasets/${datasetId}`, { method: 'DELETE' }),
  upload: async (datasetId: string, file: File) => {
    const data = new FormData()
    data.append('file', file)
    return request<Resource>(`/api/product/datasets/${datasetId}/resources`, { method: 'POST', body: data })
  },
  zhiyunCourses: async () => (await request<{ data: ZhiyunCourse[] }>('/api/product/imports/zhiyun/courses')).data,
  inspectZhiyunCourse: (courseId: string) => request<ProviderInspection>(`/api/product/imports/zhiyun/courses/${courseId}`),
  importZhiyun: (datasetId: string, courseId: string, lectureIds: string[], contentTypes: Array<'transcript' | 'courseware'>) =>
    request<{ data: Resource[]; warnings: string[] }>(`/api/product/datasets/${datasetId}/imports/zhiyun`, json({ course_id: courseId, lecture_ids: lectureIds, content_types: contentTypes })),
  xuezaiCourses: async () => (await request<{ data: Array<{ course_id: number; name: string; teacher: string | null; term: string | null }> }>('/api/product/imports/xuezai/courses')).data,
  inspectXuezaiCourse: (courseId: number) => request<ProviderInspection>(`/api/product/imports/xuezai/courses/${courseId}`),
  importXuezai: (datasetId: string, courseId: number, uploadIds: number[]) =>
    request<{ data: Resource[]; warnings: string[] }>(`/api/product/datasets/${datasetId}/imports/xuezai`, json({ course_id: courseId, upload_ids: uploadIds })),
  providerAuth: () => request<ProviderAuthStatus>('/api/product/auth/providers'),
  unifiedLogin: (username: string, password: string, webvpn: boolean) =>
    request<{ providers: ProviderAuthStatus; username: string; warnings?: string[] }>(
      '/api/product/auth/login',
      json({ username, password, webvpn }),
    ),
  preview: (revisionId: string) => request<{ revision: Resource['current_revision']; text: string }>(`/api/product/resource-revisions/${revisionId}/preview`),
  createSnapshot: (datasetId: string, revisionIds: string[], label = '') =>
    request<InputSnapshot>(`/api/product/datasets/${datasetId}/snapshots`, json({ resource_revision_ids: revisionIds, label })),
  presets: async () => (await request<{ data: WorkflowPreset[] }>('/api/product/workflow-presets')).data,
  runs: async () => (await request<{ data: RunProjection[] }>('/api/product/runs')).data,
  run: (runId: string) => request<RunProjection>(`/api/product/runs/${runId}`),
  datasetRuns: (datasetId: string) => request<{ data: DatasetRunSummary[]; dataset: { dataset_id: string; name: string } }>(`/api/product/datasets/${datasetId}/runs`),
  deleteRun: (runId: string) => request<void>(`/api/product/runs/${runId}`, { method: 'DELETE' }),
  artifacts: async () => (await request<{ data: ArtifactSummary[] }>('/api/product/artifacts')).data,
  artifact: (artifactId: string) => request<ArtifactDetail>(`/api/product/artifacts/${artifactId}`),
  startRun: (courseId: string, snapshotId: string, lectureIndices: number[], concurrency: number, review: boolean) => {
    const payload: Record<string, unknown> = {
      snapshot_id: snapshotId,
      regenerate: false,
      review,
      concurrency,
      chapter_indices: lectureIndices,
    }
    if (courseId) payload.course_id = courseId
    return request<JobState>('/api/generate/v2', json(payload))
  },
}
