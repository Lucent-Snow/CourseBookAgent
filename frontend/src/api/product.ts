import type { JobState } from '@/types'
import type {
  ArtifactDetail,
  ArtifactSummary,
  Dataset,
  DatasetDetail,
  InputSnapshot,
  Resource,
  RunProjection,
  WorkflowPreset,
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
  importZhiyun: async (datasetId: string, courseId: string) =>
    (await request<{ data: Resource[] }>(`/api/product/datasets/${datasetId}/imports/zhiyun`, json({ course_id: courseId }))).data,
  preview: (revisionId: string) => request<{ revision: Resource['current_revision']; text: string }>(`/api/product/resource-revisions/${revisionId}/preview`),
  createSnapshot: (datasetId: string, revisionIds: string[], label = '') =>
    request<InputSnapshot>(`/api/product/datasets/${datasetId}/snapshots`, json({ resource_revision_ids: revisionIds, label })),
  presets: async () => (await request<{ data: WorkflowPreset[] }>('/api/product/workflow-presets')).data,
  runs: async () => (await request<{ data: RunProjection[] }>('/api/product/runs')).data,
  run: (runId: string) => request<RunProjection>(`/api/product/runs/${runId}`),
  artifacts: async () => (await request<{ data: ArtifactSummary[] }>('/api/product/artifacts')).data,
  artifact: (artifactId: string) => request<ArtifactDetail>(`/api/product/artifacts/${artifactId}`),
  startRun: (courseId: string, snapshotId: string, lectureIndices: number[], concurrency: number, review: boolean) =>
    request<JobState>('/api/generate', json({
      course_id: courseId,
      snapshot_id: snapshotId,
      preset_id: 'coursebook',
      lecture_indices: lectureIndices,
      concurrency,
      review,
    })),
}
