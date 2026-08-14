import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { api } from '@/api/client'
import type { CourseListItem } from '@/types'

type Phase = 'idle' | '规划' | '生成' | '合成' | '完成'

interface ProgressInfo {
  phase: Phase
  current: number | null
  total: number | null
}

function parseMessage(message: string): ProgressInfo {
  const m = message.match(/生成第 (\d+)\/(\d+) 章/)
  if (m) return { phase: '生成', current: Number(m[1]), total: Number(m[2]) }
  if (message.includes('规划')) return { phase: '规划', current: null, total: null }
  if (message.includes('合成')) return { phase: '合成', current: null, total: null }
  if (message.includes('完成')) return { phase: '完成', current: null, total: null }
  return { phase: 'idle', current: null, total: null }
}

const PHASES: Phase[] = ['规划', '生成', '合成', '完成']

export function WorkspacePage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [courses, setCourses] = useState<CourseListItem[]>([])
  const [courseId, setCourseId] = useState(searchParams.get('courseId') ?? '82493')
  const [status, setStatus] = useState('选择课程后开始生成')
  const [error, setError] = useState('')
  const [progress, setProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const [info, setInfo] = useState<ProgressInfo>({ phase: 'idle', current: null, total: null })
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
        setInfo(parseMessage(job.message || ''))
        if (job.status === 'completed' || job.status === 'partial') {
          setInfo({ phase: '完成', current: null, total: null })
          setProgress(100)
          setBusy(false)
          navigate(`/read/${genCourseId}`)
          return
        }
        if (job.status === 'failed') {
          setBusy(false)
          return
        }
        timer.current = window.setTimeout(() => poll(jobId, genCourseId), 1000)
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
    setInfo({ phase: 'idle', current: null, total: null })
    try {
      const job = await api.generate(courseId)
      poll(job.job_id, courseId)
    } catch (err) {
      setBusy(false)
      setError((err as Error).message)
    }
  }

  const phaseIndex = PHASES.indexOf(info.phase === 'idle' ? '规划' : info.phase)
  const chapters = info.total ? Array.from({ length: info.total }, (_, i) => i + 1) : []

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
        {PHASES.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <div
              className={`grid size-7 place-items-center rounded-full text-xs font-semibold ${
                i < phaseIndex
                  ? 'bg-emerald-500 text-white'
                  : i === phaseIndex
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground'
              }`}
            >
              {i < phaseIndex ? '✓' : i + 1}
            </div>
            <span className={`text-sm ${i === phaseIndex ? 'font-medium' : 'text-muted-foreground'}`}>
              {label}
            </span>
            {i < PHASES.length - 1 && <div className="mx-2 h-px w-8 bg-border" />}
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

        {busy && (
          <div className="mt-5 space-y-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{status}</span>
              <span>{progress}%</span>
            </div>
            <Progress value={progress} />

            {/* 章节级生成进度 */}
            {info.phase === '生成' && chapters.length > 0 && (
              <div className="max-h-64 space-y-1 overflow-auto rounded-md border bg-muted/30 p-2">
                {chapters.map((n) => {
                  const state =
                    info.current != null && n < info.current
                      ? 'done'
                      : n === info.current
                        ? 'active'
                        : 'pending'
                  return (
                    <div
                      key={n}
                      className={`flex items-center gap-2 rounded px-2 py-1 text-xs ${
                        state === 'active' ? 'bg-accent font-medium' : state === 'done' ? 'text-muted-foreground' : 'text-muted-foreground/60'
                      }`}
                    >
                      <span className="w-4 text-center">
                        {state === 'done' ? '✓' : state === 'active' ? '⟳' : '○'}
                      </span>
                      <span>第 {n} 讲</span>
                      {state === 'active' && <span className="text-muted-foreground">生成中…</span>}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-md border-l-4 border-red-500 bg-red-50 p-2.5 text-xs text-red-800 dark:bg-red-950/40 dark:text-red-200">
            {error}
          </div>
        )}

        {!busy && !error && (
          <div className="mt-4 rounded-md border-l-4 border-primary bg-muted/50 p-2.5 text-xs">
            {status}
          </div>
        )}

        <p className="mt-4 text-xs text-muted-foreground">
          生成约需数分钟，可关闭页面稍后回来；已生成的部分会缓存。
        </p>
      </div>
    </div>
  )
}
