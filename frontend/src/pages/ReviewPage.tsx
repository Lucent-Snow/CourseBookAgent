import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/api/client'
import type { RunReport, RunSummary } from '@/types'

function IssueRow({ tag, tone, text }: { tag: string; tone: string; text: string }) {
  return (
    <div className={`flex gap-3 rounded-lg border p-3 ${tone}`}>
      <span className="shrink-0 rounded-full bg-white/60 px-2 py-0.5 text-xs font-semibold dark:bg-black/20">
        {tag}
      </span>
      <span className="text-sm leading-relaxed">{text}</span>
    </div>
  )
}

export function ReviewPage() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [selectedRun, setSelectedRun] = useState<string | null>(null)
  const [report, setReport] = useState<RunReport | null>(null)
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [confirmMsg, setConfirmMsg] = useState('')

  useEffect(() => {
    void api
      .listRuns()
      .then((rs) => {
        setRuns(rs)
        if (rs[0]) setSelectedRun(rs[0].run_id)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedRun) return
    setReport(null)
    setSelectedIdx(null)
    void api
      .runReport(selectedRun)
      .then((r) => {
        setReport(r)
        setSelectedIdx(r.results[0]?.index ?? null)
      })
      .catch(() => setReport(null))
  }, [selectedRun])

  const chapter = report?.results.find((r) => r.index === selectedIdx)
  const issues = [
    ...(chapter?.deterministic?.issues ?? []).map((t) => ({ text: t, kind: 'det' })),
    ...(chapter?.semantic?.issues ?? []).map((t) => ({ text: t, kind: 'sem' })),
  ]

  async function confirm() {
    if (!selectedRun || selectedIdx == null) return
    try {
      await api.confirmChapter(selectedRun, selectedIdx, '已人工对照确认')
      setConfirmMsg(`第 ${selectedIdx} 讲已标记确认`)
    } catch (err) {
      setConfirmMsg((err as Error).message)
    }
  }

  if (loading) {
    return <div className="h-64 animate-pulse rounded-lg bg-muted" />
  }

  if (runs.length === 0) {
    return (
      <div className="mx-auto max-w-md py-16 text-center">
        <p className="text-sm text-muted-foreground">尚无 V2 质量运行记录</p>
      </div>
    )
  }

  return (
    <div>
      <h2 className="text-2xl font-bold">质量报告</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        每讲生成后经过确定性门禁与 LLM 审校，未通过的内容在此标记、修订、人工确认。
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <select
          value={selectedRun ?? ''}
          onChange={(e) => setSelectedRun(e.target.value)}
          className="h-9 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none"
        >
          {runs.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {r.run_id}（{r.accepted} 通过 / {r.rejected} 拒绝）
            </option>
          ))}
        </select>
        {report && (
          <div className="flex gap-2">
            <Badge className="border-0 bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200">
              {report.accepted} 通过
            </Badge>
            <Badge className="border-0 bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
              {report.rejected} 待处理
            </Badge>
          </div>
        )}
      </div>

      {report && (
        <div className="mt-6 grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
          <aside className="overflow-hidden rounded-xl border bg-card">
            <div className="border-b px-4 py-2.5 text-sm font-semibold">章节审校</div>
            <div className="divide-y">
              {report.results.map((r) => (
                <button
                  key={r.index}
                  type="button"
                  onClick={() => setSelectedIdx(r.index)}
                  className={`flex w-full items-center justify-between px-4 py-2.5 text-left text-sm ${
                    r.index === selectedIdx ? 'bg-accent' : 'hover:bg-muted'
                  }`}
                >
                  <span>第 {r.index} 讲</span>
                  <span>{r.accepted ? '✓' : '⚠'}</span>
                </button>
              ))}
            </div>
          </aside>

          <section className="min-w-0 rounded-xl border bg-card p-5">
            {chapter ? (
              <div>
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-semibold">第 {chapter.index} 讲</h3>
                  {chapter.accepted ? (
                    <Badge className="border-0 bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200">
                      已通过
                    </Badge>
                  ) : (
                    <Badge className="border-0 bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
                      待修订
                    </Badge>
                  )}
                </div>

                <div className="mt-4 space-y-2">
                  {issues.length === 0 ? (
                    <p className="text-sm text-muted-foreground">未发现问题。</p>
                  ) : (
                    issues.map((iss, i) => (
                      <IssueRow
                        key={i}
                        tag={iss.kind === 'det' ? '结构问题' : '审校问题'}
                        tone={
                          iss.kind === 'det'
                            ? 'border-amber-200 bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200'
                            : 'border-red-200 bg-red-50 text-red-900 dark:bg-red-950/30 dark:text-red-200'
                        }
                        text={iss.text}
                      />
                    ))
                  )}
                </div>

                <div className="mt-5 flex items-center gap-3">
                  <Button onClick={confirm} disabled={chapter.accepted}>
                    标记已确认
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      void (async () => {
                        try {
                          const job = await api.regenerateLecture(report.run_id.split('-')[0] || '82493', chapter.index)
                          setConfirmMsg(`已提交重生成任务：${job.job_id}`)
                        } catch (err) {
                          setConfirmMsg((err as Error).message)
                        }
                      })()
                    }}
                  >
                    重新生成本章
                  </Button>
                </div>
                {confirmMsg && <p className="mt-3 text-xs text-muted-foreground">{confirmMsg}</p>}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">选择左侧章节查看审校详情。</p>
            )}
          </section>
        </div>
      )}
    </div>
  )
}
