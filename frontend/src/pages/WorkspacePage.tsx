import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { api } from '@/api/client'
import type { CourseListItem } from '@/types'

const STEPS = ['选课', '生成', '完成']

export function WorkspacePage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [courses, setCourses] = useState<CourseListItem[]>([])
  const [courseId, setCourseId] = useState(searchParams.get('courseId') ?? '82493')
  const [status, setStatus] = useState('选择课程后开始生成')
  const [error, setError] = useState('')
  const [progress, setProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    void api.listCourses().then(setCourses).catch(() => {})
    return () => {
      if (timer.current) window.clearTimeout(timer.current)
    }
  }, [])

  function poll(jobId: string, genCourseId: string) {
    void (async () => {
      try {
        const job = await api.job(jobId)
        setProgress(job.progress ?? 0)
        setStatus(job.message || job.step)
        setError(job.status === 'failed' ? (job.error || '生成失败') : '')
        if (job.status === 'completed' || job.status === 'partial') {
          setBusy(false)
          navigate(`/read/${genCourseId}`)
          return
        }
        if (job.status === 'failed') {
          setBusy(false)
          return
        }
        timer.current = window.setTimeout(() => poll(jobId, genCourseId), 1200)
      } catch (err) {
        setBusy(false)
        setError((err as Error).message)
      }
    })()
  }

  async function generate() {
    setBusy(true)
    setProgress(0)
    setError('')
    setStatus('正在创建任务')
    try {
      const job = await api.generate(courseId)
      poll(job.job_id, courseId)
    } catch (err) {
      setBusy(false)
      setError((err as Error).message)
    }
  }

  const activeStep = busy ? 1 : progress >= 100 ? 2 : 0

  return (
    <div className="mx-auto max-w-2xl">
      <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
        ← 返回书架
      </Link>
      <h2 className="mt-4 text-2xl font-bold">生成讲义</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        选择一门课程，系统自动获取字幕并整理成教辅书。
      </p>

      {/* 步骤条 */}
      <div className="mt-8 flex items-center gap-2">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <div
              className={`grid size-7 place-items-center rounded-full text-xs font-semibold ${
                i < activeStep
                  ? 'bg-emerald-500 text-white'
                  : i === activeStep
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground'
              }`}
            >
              {i < activeStep ? '✓' : i + 1}
            </div>
            <span className={`text-sm ${i === activeStep ? 'font-medium' : 'text-muted-foreground'}`}>
              {label}
            </span>
            {i < STEPS.length - 1 && <div className="mx-2 h-px w-10 bg-border" />}
          </div>
        ))}
      </div>

      <div className="mt-8 rounded-xl border bg-card p-6">
        <label className="mb-2 block text-xs text-muted-foreground" htmlFor="course">
          选择课程
        </label>
        <select
          id="course"
          value={courseId}
          disabled={busy}
          onChange={(e) => setCourseId(e.target.value)}
          className="h-10 w-full rounded-lg border border-input bg-transparent px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
        >
          {courses.map((c) => (
            <option key={c.course_id} value={c.course_id}>
              {c.name}
            </option>
          ))}
        </select>

        <Button onClick={generate} disabled={busy} className="mt-4 w-full">
          {busy ? '生成中…' : '生成全课讲义'}
        </Button>

        <div className="mt-4 space-y-2">
          {error ? (
            <div className="rounded-md border-l-4 border-red-500 bg-red-50 p-2.5 text-xs text-red-800 dark:bg-red-950/40 dark:text-red-200">
              {error}
            </div>
          ) : (
            <div className="rounded-md border-l-4 border-primary bg-muted/50 p-2.5 text-xs">
              {status}
            </div>
          )}
          {busy && <Progress value={progress} />}
        </div>

        <p className="mt-4 text-xs text-muted-foreground">
          生成约需数分钟，可关闭页面稍后回来；已生成的部分会缓存。
        </p>
      </div>
    </div>
  )
}
