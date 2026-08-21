import type {
  AuthStatus,
  BookSummary,
  CourseBook,
  CourseListItem,
  JobState,
  RunReport,
  RunSummary,
  Settings,
} from '@/types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      detail = body?.detail ?? ''
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(detail || `请求失败（${res.status}）`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<{ ok: boolean; llm_configured: boolean }>('/api/health'),

  authStatus: () => request<AuthStatus>('/api/zhiyun/auth'),

  login: (username: string, password: string, webvpn: boolean) =>
    request<AuthStatus>('/api/zhiyun/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, webvpn }),
    }),

  listCourses: async (): Promise<CourseListItem[]> => {
    const res = await request<{ data: CourseListItem[] }>('/api/courses')
    return res.data ?? []
  },

  generate: (courseId: string, regenerate = false) =>
    request<JobState>('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ course_id: courseId, regenerate }),
    }),

  job: (jobId: string) => request<JobState>(`/api/jobs/${jobId}`),

  book: (courseId: string) => request<CourseBook>(`/api/books/${courseId}`),

  downloadUrl: (courseId: string) => `/api/books/${courseId}/download.md`,
  jobDownloadUrl: (jobId: string) => `/api/jobs/${jobId}/download.md`,

  // 书架
  listBooks: async (): Promise<BookSummary[]> => {
    const res = await request<{ data: BookSummary[] }>('/api/books')
    return res.data ?? []
  },

  // 设置
  settings: () => request<Settings>('/api/settings'),
  saveLlm: (base_url: string, model: string, api_key: string) =>
    request<{ ok: boolean; configured: boolean }>('/api/settings/llm', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url, model, api_key }),
    }),
  testLlm: () =>
    request<{ ok: boolean; model: string; latency_ms: number }>('/api/settings/llm/test', {
      method: 'POST',
    }),
  clearCache: () => request<{ ok: boolean; removed: string[] }>('/api/cache', { method: 'DELETE' }),

  // V2 质量报告
  listRuns: async (): Promise<RunSummary[]> => {
    const res = await request<{ data: RunSummary[] }>('/api/runs')
    return res.data ?? []
  },
  runReport: (runId: string) => request<RunReport>(`/api/runs/${runId}/report`),
  confirmChapter: (runId: string, lectureIndex: number, note: string) =>
    request<{ ok: boolean }>(`/api/runs/${runId}/chapters/${lectureIndex}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note }),
    }),

  // 单讲重生成
  regenerateLecture: (courseId: string, index: number) =>
    request<JobState>(`/api/courses/${courseId}/lectures/${index}/regenerate`, {
      method: 'POST',
    }),
}
