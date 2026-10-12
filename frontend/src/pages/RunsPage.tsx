import { useEffect, useState } from 'react'
import { AlertTriangle, ArrowRight, BookOpen, CheckCircle2, Clock3, Layers } from 'lucide-react'
import { Link } from 'react-router-dom'
import { productApi } from '@/api/product'
import type { DatasetRunSummary } from '@/product-types'

const statusLabel: Record<string, string> = {
 queued: '排队中', running: '运行中', retrying: '重试中', completed: '已完成', partial: '部分完成',
 failed: '失败', interrupted: '已中断', cancelled: '已取消',
}

function isAttention(status: string | null) {
 return status === 'failed' || status === 'partial' || status === 'interrupted'
}

function statusTone(status: string | null) {
 if (isAttention(status)) return 'bg-red-50 text-red-700'
 if (status === 'completed') return 'bg-[#e9f5ee] text-[#27774a]'
 if (status === 'running' || status === 'retrying') return 'bg-[#e6f3f3] text-[#147d86]'
 return 'bg-[#f1f3f3] text-[#657678]'
}

export function RunsPage() {
 const [runs, setRuns] = useState<DatasetRunSummary[]>([])
 const [datasetNames, setDatasetNames] = useState<Record<string, string>>({})
 const [loading, setLoading] = useState(true)
 const [error, setError] = useState('')

 useEffect(() => {
  let active = true
  async function load() {
   try {
    const datasets = await productApi.datasets()
    const names = Object.fromEntries(datasets.map((dataset) => [dataset.dataset_id, dataset.name]))
    const responses = await Promise.all(datasets.map((dataset) => productApi.datasetRuns(dataset.dataset_id).catch(() => ({ data: [], dataset }))))
    const allRuns = responses.flatMap((response) => response.data ?? [])
    allRuns.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
    if (active) { setDatasetNames(names); setRuns(allRuns); setError('') }
   } catch (err) { if (active) setError((err as Error).message) }
   finally { if (active) setLoading(false) }
  }
  void load()
  const timer = window.setInterval(load, 5000)
  return () => { active = false; window.clearInterval(timer) }
 }, [])

 const running = runs.filter((run) => run.status === 'running' || run.status === 'retrying' || run.status === 'queued').length
 const attention = runs.filter((run) => isAttention(run.status)).length
 const readable = runs.filter((run) => run.artifact_available).length

 return <div className="mx-auto max-w-[1180px] px-4 py-6 md:px-10 md:py-10">
  <header><p className="text-xs font-semibold text-[#147d86]">RUN CENTER</p><h1 className="mt-2 text-[28px] font-semibold">运行中心</h1><p className="mt-2 text-sm text-[#718183]">看清每一次生成走到哪里、是否需要处理，以及成品是否已可阅读。</p></header>
  <section aria-label="运行概览" className="mt-7 grid gap-3 sm:grid-cols-3">
   {[
    { icon: Clock3, label: '正在进行', value: running, hint: '排队、运行与重试中的任务', tone: 'text-[#147d86]' },
    { icon: AlertTriangle, label: '需要处理', value: attention, hint: '失败、中断或部分完成', tone: 'text-red-700' },
    { icon: BookOpen, label: '产物可读', value: readable, hint: '可进入成品页查看', tone: 'text-[#27774a]' },
   ].map(({ icon: Icon, label, value, hint, tone }) => <div key={label} className="rounded-xl border border-[#dfe6e6] bg-white p-5"><div className={`flex items-center gap-2 text-xs font-medium ${tone}`}><Icon size={16} />{label}</div><strong className="mt-3 block text-3xl text-[#172426]">{loading ? '—' : value}</strong><p className="mt-1 text-xs text-[#718183]">{hint}</p></div>)}
  </section>
  {error && <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
  <section className="mt-7 overflow-hidden rounded-xl border border-[#dfe6e6] bg-white">
   <div className="flex items-center justify-between border-b border-[#edf0f0] px-5 py-4"><h2 className="text-sm font-semibold">生成记录</h2><span className="text-xs text-[#718183]">{runs.length} 次 · 按创建时间倒序</span></div>
   {runs.length ? <div className="divide-y divide-[#edf0f0]">{runs.map((run) => <Link key={run.job_id} to={`/runs/${run.job_id}`} className="group flex flex-col gap-4 px-5 py-5 hover:bg-[#fafcfc] sm:flex-row sm:items-center sm:justify-between">
    <div className="min-w-0 flex-1"><p className="flex items-center gap-2 text-sm font-semibold"><Layers size={16} className="shrink-0 text-[#147d86]" /><span className="truncate">{datasetNames[run.dataset_id] || `资料集 ${run.dataset_id.slice(-12)}`}</span></p><p className="mt-2 line-clamp-1 text-xs text-[#657678]">{run.message || '等待状态更新'}</p><p className="mt-2 text-[11px] text-[#819092]">{run.created_at ? new Date(run.created_at).toLocaleString('zh-CN') : '时间未知'} · 运行 {run.job_id.slice(-12)}{run.snapshot_id && ` · 快照 ${run.snapshot_id.slice(-8)}`}</p></div>
    <div className="flex items-center gap-4 sm:gap-5"><div className="min-w-32"><div className="flex items-center justify-between gap-2"><span className={`rounded-full px-2 py-1 text-[11px] font-medium ${statusTone(run.status)}`}>{statusLabel[run.status ?? ''] || run.status || '等待中'}</span><span className="text-xs font-semibold text-[#334547]">{run.progress}%</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#e7eeee]"><div className="h-full rounded-full bg-[#147d86]" style={{ width: `${Math.max(0, Math.min(100, run.progress))}%` }} /></div></div><span className={`flex min-w-20 items-center gap-1 text-xs ${run.artifact_available ? 'text-[#27774a]' : isAttention(run.status) ? 'text-red-700' : 'text-[#718183]'}`}>{run.artifact_available ? <CheckCircle2 size={14} /> : isAttention(run.status) ? <AlertTriangle size={14} /> : <Clock3 size={14} />}{run.artifact_available ? '产物可读' : isAttention(run.status) ? '待处理' : '暂无产物'}</span><ArrowRight size={16} className="text-[#9aa7a8] transition-transform group-hover:translate-x-1" /></div>
   </Link>)}</div> : <div className="py-20 text-center"><Clock3 size={25} className="mx-auto text-[#96a5a6]" /><p className="mt-3 text-sm text-[#657678]">{loading ? '正在加载运行记录…' : '暂无运行记录'}</p>{!loading && <p className="mt-1 text-xs text-[#8b999a]">从<Link to="/datasets" className="mx-1 text-[#147d86] underline">资料集</Link>选择资料，开启第一次生成。</p>}</div>}
  </section>
 </div>
}
