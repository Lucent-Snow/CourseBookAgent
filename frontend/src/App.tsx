import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Progress } from '@/components/ui/progress'
import { BookReader } from '@/components/book/BookReader'
import { api } from '@/api/client'
import type { AuthStatus, CourseBook, CourseListItem } from '@/types'

interface Status {
  text: string
  error: boolean
}

const DEMO_COURSE: CourseListItem = {
  course_id: '82493',
  name: '实验设计与心理统计Ⅱ',
  teacher: '',
  term: '',
}

export default function App() {
  const [courses, setCourses] = useState<CourseListItem[]>([DEMO_COURSE])
  const [courseId, setCourseId] = useState(DEMO_COURSE.course_id)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [webvpn, setWebvpn] = useState(false)
  const [auth, setAuth] = useState<AuthStatus | null>(null)
  const [book, setBook] = useState<CourseBook | null>(null)
  const [bookCourseId, setBookCourseId] = useState<string | null>(null)
  const [status, setStatus] = useState<Status>({ text: '等待开始', error: false })
  const [progress, setProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const pollTimer = useRef<number | null>(null)

  const loadBook = useCallback(async (id: string) => {
    try {
      const data = await api.book(id)
      setBook(data)
      setBookCourseId(id)
    } catch {
      // 尚无缓存成书时保持空态
    }
  }, [])

  useEffect(() => {
    void (async () => {
      try {
        const a = await api.authStatus()
        setAuth(a)
        if (a.authenticated) {
          const list = await api.listCourses()
          if (list.length) setCourses(list)
        }
      } catch {
        // 忽略认证状态探测失败
      }
      await loadBook(DEMO_COURSE.course_id)
    })()
    return () => {
      if (pollTimer.current) window.clearTimeout(pollTimer.current)
    }
  }, [loadBook])

  function onChangeCourse(id: string) {
    setCourseId(id)
    setBook(null)
    setBookCourseId(null)
    setStatus({ text: '尚未生成讲义', error: false })
    setProgress(0)
    void loadBook(id)
  }

  async function onLogin(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setStatus({ text: '正在登录智云课堂', error: false })
    try {
      const result = await api.login(username, password, webvpn)
      setAuth(result)
      setPassword('')
      setStatus({ text: `已登录：${result.username}`, error: false })
      const list = await api.listCourses()
      if (list.length) setCourses(list)
    } catch (err) {
      setStatus({ text: (err as Error).message, error: true })
    } finally {
      setBusy(false)
    }
  }

  function poll(jobId: string, genCourseId: string) {
    void (async () => {
      try {
        const job = await api.job(jobId)
        setProgress(job.progress ?? 0)
        setStatus({ text: job.message || job.step, error: job.status === 'failed' })
        if (job.status === 'completed' || job.status === 'partial') {
          await loadBook(genCourseId)
          setStatus({ text: '课程讲义已生成', error: job.status === 'partial' })
          setBusy(false)
          return
        }
        if (job.status === 'failed') {
          setBusy(false)
          return
        }
        pollTimer.current = window.setTimeout(() => poll(jobId, genCourseId), 1200)
      } catch (err) {
        setStatus({ text: (err as Error).message, error: true })
        setBusy(false)
      }
    })()
  }

  async function onGenerate() {
    setBusy(true)
    setProgress(0)
    setStatus({ text: '正在创建任务', error: false })
    try {
      const job = await api.generate(courseId)
      poll(job.job_id, courseId)
    } catch (err) {
      setStatus({ text: (err as Error).message, error: true })
      setBusy(false)
    }
  }

  const downloadUrl = bookCourseId ? api.downloadUrl(bookCourseId) : null

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="sticky top-0 z-10 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="grid size-8 place-items-center rounded bg-primary font-bold text-primary-foreground">
              课
            </div>
            <div>
              <div className="text-xs tracking-widest text-muted-foreground uppercase">
                CourseBookAgent
              </div>
              <h1 className="text-lg font-bold">智课成书</h1>
            </div>
          </div>
          <div className="hidden text-xs tracking-widest text-muted-foreground uppercase sm:block">
            字幕 · 结构 · 讲义
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="grid gap-8 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="space-y-6">
            <form onSubmit={onLogin} className="rounded-lg border p-4">
              <h2 className="mb-1 text-sm font-semibold">登录智云课堂</h2>
              <p className="mb-3 text-xs text-muted-foreground">
                {auth?.authenticated
                  ? `已登录：${auth.username}${auth.webvpn ? '（WebVPN）' : ''}`
                  : '未登录：可浏览本地缓存；刷新课程前请登录。'}
              </p>
              <label className="mb-1 block text-xs text-muted-foreground" htmlFor="username">
                学号
              </label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="学号"
                autoComplete="username"
              />
              <label className="mt-3 mb-1 block text-xs text-muted-foreground" htmlFor="password">
                密码
              </label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="密码"
                autoComplete="current-password"
              />
              <label className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={webvpn}
                  onChange={(e) => setWebvpn(e.target.checked)}
                  className="size-3.5"
                />
                校外网络，使用 WebVPN
              </label>
              <Button type="submit" disabled={busy} className="mt-4 w-full">
                登录并加载课程
              </Button>
              <p className="mt-2 text-xs text-muted-foreground">密码仅用于本次认证，不写入本项目。</p>
            </form>

            <div className="rounded-lg border p-4">
              <label className="mb-1 block text-xs text-muted-foreground" htmlFor="course">
                选择课程
              </label>
              <select
                id="course"
                value={courseId}
                onChange={(e) => onChangeCourse(e.target.value)}
                className="h-9 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                {courses.map((c) => (
                  <option key={c.course_id} value={c.course_id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <Button onClick={onGenerate} disabled={busy} className="mt-3 w-full">
                {busy ? '生成中…' : '生成全课讲义'}
              </Button>

              <div className="mt-4 space-y-2">
                <div
                  className={`rounded-md border-l-4 p-2.5 text-xs ${
                    status.error
                      ? 'border-red-500 bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-200'
                      : 'border-primary bg-muted/50'
                  }`}
                >
                  {status.text}
                </div>
                {busy && <Progress value={progress} />}
              </div>

              {downloadUrl && (
                <Button render={<a href={downloadUrl} />} variant="secondary" className="mt-4 w-full">
                  下载 Markdown
                </Button>
              )}
            </div>
          </aside>

          <section className="min-w-0">
            {book ? (
              <BookReader book={book} />
            ) : (
              <div className="flex min-h-80 items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground">
                {busy ? '正在整理字幕并生成章节，请稍候…' : '生成完成后，讲义会在这里展开。'}
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}
