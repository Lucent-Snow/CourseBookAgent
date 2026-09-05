import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { api } from '@/api/client'
import type { ChapterSummary, CourseListItem } from '@/types'

type Phase = 'idle' | '规划' | '生成' | '合成' | '完成'

interface ProgressInfo {
  phase: Phase
  current: number | null
  total: number | null
}

interface ChapterTiming {
  start: number
  end?: number
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

function fmt(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

export function WorkspacePage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [courses, setCourses] = useState<CourseListItem[]>([])
  const [courseId, setCourseId] = useState(searchParams.get('courseId') ?? '82493')
  const [forceRegen, setForceRegen] = useState(false)
  const [status, setStatus] = useState('选择课程后开始生成')
  const [error, setError] = useState('')
  const [progress, setProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const [activeJob, setActiveJob] = useState<string | null>(null)
  const [retryable, setRetryable] = useState(false)
  const [info, setInfo] = useState<ProgressInfo>({ phase: 'idle', current: null, total: null })
  const [chapters, setChapters] = useState<ChapterSummary[]>([])
  const [expanded, setExpanded] = useState<number | null>(null)
  const [startTime, setStartTime] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [chapterTimes, setChapterTimes] = useState<Record<number, ChapterTiming>>({})
  const pollTimer = useRef<number | null>(null)
  const tickRef = useRef<number | null>(null)
  const lastCurrentRef = useRef<number | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    let disposed = false
    mountedRef.current = true
    void api.listCourses().then(setCourses).catch(() => {})
    const saved = localStorage.getItem('coursebook-active-job')
    if (saved) {
      void api.job(saved).then(job => {
        if (disposed) return
        setActiveJob(job.job_id)
        setCourseId(job.course_id)
        setBusy(['queued', 'running'].includes(job.status))
        poll(job.job_id, job.course_id)
      }).catch(() => localStorage.removeItem('coursebook-active-job'))
    }
    return () => {
      disposed = true
      mountedRef.current = false
      if (pollTimer.current) window.clearTimeout(pollTimer.current)
      if (tickRef.current) window.clearInterval(tickRef.current)
    }
  }, [])

  useEffect(() => {
    if (!busy) return
    tickRef.current = window.setInterval(() => setNow(Date.now()), 1000)
    return () => {
      if (tickRef.current) window.clearInterval(tickRef.current)
    }
  }, [busy])

  function recordTiming(current: number) {
    const prev = lastCurrentRef.current
    setChapterTimes((prevTimes) => {
      const next = { ...prevTimes }
      if (prev !== null && prev !== current && next[prev] && !next[prev].end) {
        next[prev] = { ...next[prev], end: Date.now() }
      }
      if (!next[current]) next[current] = { start: Date.now() }
      return next
    })
    lastCurrentRef.current = current
  }

  function poll(jobId: string, genCourseId: string) {
    void (async () => {
      try {
        const job = await api.job(jobId)
        if (!mountedRef.current) return
        setProgress(job.progress ?? 0)
        setStatus(job.message || job.step)
        setError(job.status === 'failed' ? (job.error || '生成失败') : '')
        setChapters(job.chapters ?? [])
        setRetryable(['failed', 'partial', 'interrupted'].includes(job.status))
        const parsed = parseMessage(job.message || '')
        setInfo(parsed)
        if (parsed.phase === '生成' && parsed.current) recordTiming(parsed.current)

        if (job.status === 'completed') {
          if (localStorage.getItem('coursebook-active-job') === jobId) {
            localStorage.removeItem('coursebook-active-job')
          }
          setInfo({ phase: '完成', current: null, total: null })
          setProgress(100)
          setBusy(false)
          navigate(`/read/${genCourseId}`)
          return
        }
        if (['failed', 'partial', 'interrupted'].includes(job.status)) {
          setBusy(false)
          return
        }
        pollTimer.current = window.setTimeout(() => poll(jobId, genCourseId), 800)
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
    setChapters([])
    setExpanded(null)
    setStartTime(Date.now())
    setNow(Date.now())
    setChapterTimes({})
    lastCurrentRef.current = null
    try {
      const job = await api.generate(courseId, forceRegen)
      setActiveJob(job.job_id)
      setRetryable(false)
      localStorage.setItem('coursebook-active-job', job.job_id)
      poll(job.job_id, courseId)
    } catch (err) {
      setBusy(false)
      setError((err as Error).message)
    }
  }

  async function retry() {
    if (!activeJob) return
    setBusy(true)
    setError('')
    try {
      const job = await api.retryJob(activeJob)
      setRetryable(false)
      poll(job.job_id, job.course_id)
    } catch (err) {
      setBusy(false)
      setError((err as Error).message)
    }
  }

  const elapsedSec = startTime ? Math.floor((now - startTime) / 1000) : 0
  const doneTimings = Object.values(chapterTimes).filter((t) => t.end)
  const doneCount = doneTimings.length
  const totalDoneSec = doneTimings.reduce((s, t) => s + ((t.end! - t.start) / 1000), 0)
  const avgSec = doneCount > 0 ? totalDoneSec / doneCount : 0
  const remainCount = Math.max(0, (info.total ?? 0) - chapters.length)
  const etaSec = avgSec > 0 ? avgSec * remainCount : 0

  const phaseIndex = PHASES.indexOf(info.phase === 'idle' ? '规划' : info.phase)
  const totalSlots = info.total ?? 0
  const slots = totalSlots > 0 ? Array.from({ length: totalSlots }, (_, i) => i + 1) : []

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
              className={`grid size-7 place-items-center rounded-full text-xs font-semibold transition-colors ${
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

        <label className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={forceRegen}
            onChange={(e) => setForceRegen(e.target.checked)}
            className="size-3.5"
          />
          强制重新生成（忽略缓存，可观察完整生成过程）
        </label>

        <Button onClick={generate} disabled={busy} className="mt-3 w-full">
          {busy ? '生成中…' : '生成全课讲义'}
        </Button>
        {retryable && (
          <Button onClick={retry} disabled={busy} variant="outline" className="mt-3 w-full">
            恢复任务（复用已完成章节）
          </Button>
        )}
        {busy && activeJob && (
          <Button variant="outline" className="mt-3 w-full" onClick={() => {
            void api.cancelJob(activeJob).catch(err => setError((err as Error).message))
          }}>
            停止生成并保留进度
          </Button>
        )}

        {busy && (
          <div className="mt-6 space-y-4">
            {/* 进度 */}
            <div>
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">{status}</span>
                <span className="font-semibold tabular-nums">{progress}%</span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className="flow-progress h-full rounded-full transition-all duration-700"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            {/* 时间统计 */}
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-lg border bg-card py-3">
                <div className="text-xl font-bold tabular-nums">{fmt(elapsedSec)}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">已用时间</div>
              </div>
              <div className="rounded-lg border bg-card py-3">
                <div className="text-xl font-bold tabular-nums">{etaSec > 0 ? `~${fmt(etaSec)}` : '—'}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">预计剩余</div>
              </div>
              <div className="rounded-lg border bg-card py-3">
                <div className="text-xl font-bold tabular-nums">{avgSec > 0 ? `${Math.round(avgSec)}s` : '—'}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">平均每讲</div>
              </div>
            </div>

            {/* 章节真实数据 */}
            <div className="max-h-96 space-y-1 overflow-auto rounded-lg border bg-muted/30 p-2">
              {slots.map((n) => {
                const chapter = chapters.find((c) => c.index === n)
                const isActive = info.current === n
                const isExpanded = expanded === n
                const timing = chapterTimes[n]
                const durSec = chapter && timing?.end ? (timing.end - timing.start) / 1000 : isActive && timing ? (now - timing.start) / 1000 : 0
                return (
                  <div key={n}>
                    <button
                      type="button"
                      onClick={() => setExpanded(isExpanded ? null : n)}
                      className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors ${
                        isActive ? 'bg-accent font-medium' : chapter ? 'hover:bg-muted' : 'text-muted-foreground/60'
                      }`}
                    >
                      <span className={`w-4 shrink-0 text-center ${isActive ? 'soft-pulse' : ''}`}>
                        {chapter?.status === 'failed' ? '✗' : chapter ? '✓' : isActive ? '⟳' : '○'}
                      </span>
                      <span className="truncate">{chapter ? chapter.title : isActive ? `第 ${n} 讲 · 生成中` : `第 ${n} 讲`}</span>
                      <span className="ml-auto shrink-0 tabular-nums text-muted-foreground">
                        {chapter?.status === 'failed'
                          ? '失败'
                          : chapter
                            ? `${chapter.total_chars ?? 0}字 · ${chapter.components ?? 0}组件 · ${durSec > 0 ? Math.round(durSec) + 's' : ''}`
                            : isActive && durSec > 0
                              ? `${Math.round(durSec)}s`
                              : ''}
                      </span>
                    </button>

                    {/* 展开详情 */}
                    {isExpanded && chapter && (
                      <div className="ml-6 space-y-1 rounded bg-background/60 p-2">
                        {chapter.status === 'failed' ? (
                          <p className="text-xs text-red-600 dark:text-red-400">{chapter.error}</p>
                        ) : (
                          <>
                            {chapter.module_name && (
                              <p className="text-xs text-muted-foreground">
                                模块：{chapter.module_name} · 角色：{chapter.chapter_role}
                              </p>
                            )}
                            <div className="mt-1 space-y-0.5">
                              {chapter.sections?.map((s, i) => (
                                <div key={i} className="flex items-center justify-between text-xs text-muted-foreground">
                                  <span className="truncate">
                                    {i + 1}. {s.heading}
                                  </span>
                                  <span className="ml-2 shrink-0 tabular-nums">
                                    {s.chars}字 · {s.components}组件 · {s.time_links}来源
                                  </span>
                                </div>
                              ))}
                            </div>
                            <p className="mt-1 text-xs text-muted-foreground">
                              目标 {chapter.learning_goals} · 重点 {chapter.key_points} · 易错 {chapter.common_mistakes}
                            </p>
                            {chapter.warnings && chapter.warnings.length > 0 && (
                              <div className="mt-1 space-y-0.5">
                                {chapter.warnings.map((w, i) => (
                                  <p key={i} className="text-xs text-amber-600 dark:text-amber-400">⚠ {w}</p>
                                ))}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
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
