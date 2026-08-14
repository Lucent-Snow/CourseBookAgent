import type { AuthStatus, CourseBook, CourseListItem, JobState } from '@/types'

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

  generate: (courseId: string) =>
    request<JobState>('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ course_id: courseId }),
    }),

  job: (jobId: string) => request<JobState>(`/api/jobs/${jobId}`),

  book: (courseId: string) => request<CourseBook>(`/api/books/${courseId}`),

  downloadUrl: (courseId: string) => `/api/books/${courseId}/download.md`,
  jobDownloadUrl: (jobId: string) => `/api/jobs/${jobId}/download.md`,
}
