import { useEffect, useState } from 'react'
import {
  BookOpen,
  Clock3,
  Layers,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { productApi } from '@/api/product'
import type { DatasetRunSummary } from '@/product-types'

function isAttention(status: string | null) {
  return status === 'failed' || status === 'partial' || status === 'interrupted'
}

function statusTone(status: string | null) {
  if (isAttention(status)) return 'bg-amber-50 text-amber-800 border border-amber-200'
  if (status === 'completed') return 'bg-[#e9f5ee] text-[#236e44]'
  if (status === 'running' || status === 'retrying') return 'bg-[#e6f3f3] text-[#147d86]'
  return 'bg-[#f1f3f3] text-[#657678]'
}

function statusLabel(status: string | null) {
  const map: Record<string, string> = {
    queued: '排队中',
    running: '正在撰写',
    retrying: '重新尝试中',
    completed: '已完稿',
    partial: '部分完成',
    failed: '生成中断',
    interrupted: '已暂停',
    cancelled: '已停止',
  }
  return map[status ?? ''] || status || '等待中'
}

export function RunsPage() {
  const [runs, setRuns] = useState<DatasetRunSummary[]>([])
  const [datasetNames, setDatasetNames] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState<'all' | 'running' | 'completed' | 'attention'>('all')

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const datasets = await productApi.datasets()
        const names = Object.fromEntries(datasets.map((dataset) => [dataset.dataset_id, dataset.name]))
        const responses = await Promise.all(
          datasets.map((dataset) => productApi.datasetRuns(dataset.dataset_id).catch(() => ({ data: [], dataset })))
        )
        const allRuns = responses.flatMap((response) => response.data ?? [])
        allRuns.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
        if (active) {
          setDatasetNames(names)
          setRuns(allRuns)
          setError('')
        }
      } catch (err) {
        if (active) setError((err as Error).message)
      } finally {
        if (active) setLoading(false)
      }
    }
    void load()
    const timer = window.setInterval(load, 5000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  const runningCount = runs.filter((r) => r.status === 'running' || r.status === 'retrying' || r.status === 'queued').length
  const completedCount = runs.filter((r) => r.artifact_available).length
  const attentionCount = runs.filter((r) => isAttention(r.status)).length

  const filteredRuns = runs.filter((r) => {
    if (filter === 'running') return r.status === 'running' || r.status === 'retrying' || r.status === 'queued'
    if (filter === 'completed') return r.artifact_available
    if (filter === 'attention') return isAttention(r.status)
    return true
  })

  return (
    <div className="mx-auto max-w-[1180px] px-4 py-6 md:px-10 md:py-10">
      <header className="flex flex-col justify-between gap-4 border-b border-[#e2e8e8] pb-6 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-semibold tracking-wider text-[#147d86] uppercase">Run Center</p>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-[#172b2d] sm:text-3xl">运行中心</h1>
          <p className="mt-2 text-sm text-[#687a7c]">
            跟踪各课程教辅的撰写进度、恢复中断任务或直接打开已完稿书卷。
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex shrink-0 items-center gap-1 rounded-xl border border-[#dfe6e6] bg-white p-1">
          {[
            { key: 'all', label: `全部 (${runs.length})` },
            { key: 'running', label: `撰写中 (${runningCount})` },
            { key: 'completed', label: `已完稿 (${completedCount})` },
            { key: 'attention', label: `需处理 (${attentionCount})` },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setFilter(item.key as typeof filter)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                filter === item.key
                  ? 'bg-[#147d86] text-white shadow-2xs'
                  : 'text-[#687a7c] hover:bg-[#f2f6f6] hover:text-[#172b2d]'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </header>

      {error && (
        <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          {error}
        </div>
      )}

      <div className="mt-6">
        {filteredRuns.length > 0 ? (
          <div className="space-y-3">
            {filteredRuns.map((run) => {
              const datasetName = datasetNames[run.dataset_id] || '课程资料'
              const isRunning = run.status === 'running' || run.status === 'retrying' || run.status === 'queued'
              return (
                <div
                  key={run.job_id}
                  className="group flex flex-col justify-between gap-4 rounded-xl border border-[#e2e8e8] bg-white p-5 transition-all hover:border-[#a4ced0] hover:shadow-xs sm:flex-row sm:items-center"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="grid size-7 place-items-center rounded-lg bg-[#eef5f5] text-[#147d86]">
                        <Layers size={14} />
                      </span>
                      <h3 className="truncate text-base font-semibold text-[#172b2d]">{datasetName}</h3>
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${statusTone(run.status)}`}>
                        {statusLabel(run.status)}
                      </span>
                    </div>

                    <p className="mt-2 line-clamp-1 text-xs text-[#526668]">
                      {run.message || '等待状态更新'}
                    </p>

                    <p className="mt-1.5 text-[11px] text-[#819294]">
                      {run.created_at ? new Date(run.created_at).toLocaleString('zh-CN') : '时间未知'}
                    </p>
                  </div>

                  {/* Progress & Actions */}
                  <div className="flex shrink-0 items-center gap-3 sm:gap-4">
                    {isRunning && (
                      <div className="w-28">
                        <div className="flex justify-between text-[11px] text-[#55696b]">
                          <span>撰写中</span>
                          <span className="font-semibold">{run.progress}%</span>
                        </div>
                        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[#e5ecec]">
                          <div
                            className="flow-progress h-full rounded-full"
                            style={{ width: `${Math.max(5, run.progress)}%` }}
                          />
                        </div>
                      </div>
                    )}

                    <Link
                      to={`/runs/${run.job_id}`}
                      className="inline-flex h-8 items-center gap-1 rounded-lg border border-[#dfe6e6] bg-white px-3 text-xs font-medium text-[#465a5c] transition-colors hover:bg-[#f6f9f9] hover:text-[#172b2d]"
                    >
                      查看过程
                    </Link>

                    {run.artifact_available && (
                      <Button
                        render={<Link to={`/artifacts/${run.job_id}`} />}
                        size="sm"
                        className="bg-[#147d86] text-white hover:bg-[#116a72]"
                      >
                        <BookOpen size={13} className="mr-1" />
                        阅读成书
                      </Button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-[#cbd8d8] bg-white py-16 text-center">
            <Clock3 size={24} className="mx-auto text-[#96a5a6]" />
            <p className="mt-3 text-sm text-[#5a6b6d]">
              {loading ? '正在读取任务…' : '暂无匹配的运行记录'}
            </p>
            {!loading && (
              <p className="mt-1 text-xs text-[#8b999a]">
                从<Link to="/datasets" className="mx-1 font-medium text-[#147d86] hover:underline">资料库</Link>选择资料，开启第一本教辅书的编撰。
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
