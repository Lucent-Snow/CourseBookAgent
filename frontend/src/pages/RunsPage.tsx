import { useEffect, useState } from 'react'
import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, Layers } from 'lucide-react'
import { Link } from 'react-router-dom'
import { productApi } from '@/api/product'
import type { DatasetRunSummary } from '@/product-types'

const statusLabel: Record<string, string> = {
 queued: '排队中', running: '运行中', completed: '已完成', partial: '部分完成',
 failed: '失败', interrupted: '已中断', cancelled: '已取消',
}

export function RunsPage() {
 const [runs, setRuns] = useState<DatasetRunSummary[]>([])
 const [error, setError] = useState('')

 useEffect(() => {
 async function load() {
 try {
 // Pull every dataset's runs so the centre is a complete history.
 const datasets = await (await fetch('/api/product/datasets')).json()
 const allRuns: DatasetRunSummary[] = []
 for (const ds of datasets.data ?? []) {
 const resp = await productApi.datasetRuns(ds.dataset_id).catch(() => ({ data: [], dataset: ds }))
 for (const r of resp.data ?? []) allRuns.push(r)
 }
 allRuns.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
 setRuns(allRuns)
 } catch (err) { setError((err as Error).message) }
 }
 void load()
 const timer = window.setInterval(load, 5000)
 return () => window.clearInterval(timer)
 }, [])

 return (
 <div className="mx-auto max-w-[1180px] px-4 py-6 md:px-10 md:py-10">
 <header>
 <p className="text-xs font-semibold text-[#147d86]">RUN CENTER</p>
 <h1 className="mt-2 text-[28px] font-semibold">运行中心</h1>
 <p className="mt-2 text-sm text-[#718183]">所有资料集的全部生成记录，按时间倒序。点击进入运行详情或回到资料集。</p>
 </header>
 {error && <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
 <section className="mt-7 overflow-hidden rounded-lg border border-[#dfe6e6] bg-white">
 {runs.length ? (
 <div className="divide-y divide-[#edf0f0]">
 {runs.map((run) => (
 <Link key={run.job_id} to={`/runs/${run.job_id}`} className="grid grid-cols-[1.6fr_1fr_.6fr_28px] items-center gap-4 px-5 py-4 hover:bg-[#fafcfc]">
 <div>
 <p className="flex items-center gap-2 text-sm font-medium">
 <Layers size={15} className="text-[#147d86]" />
 资料集 · {run.dataset_id.slice(-12)}
 </p>
 <p className="mt-1 text-[10px] text-[#819092] font-mono">{run.job_id}{run.snapshot_id && ` · 快照 ${run.snapshot_id.slice(-12)}`}{run.course_id && ` · 课程 ${run.course_id}`}</p>
 </div>
 <span className="text-xs text-[#657678]">
 {statusLabel[run.status ?? ''] || run.status} · {run.progress}%
 </span>
 <span className={`flex items-center gap-1.5 text-xs ${run.status === 'failed' || run.status === 'partial' ? 'text-red-600' : 'text-[#27774a]'}`}>
 {run.status === 'failed' || run.status === 'partial' ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}
 {run.artifact_available ? '产物可读' : run.status === 'running' || run.status === 'queued' ? '运行中' : '—'}
 </span>
 <ArrowRight size={15} className="text-[#9aa7a8]" />
 </Link>
 ))}
 </div>
 ) : (
 <div className="py-20 text-center">
 <Clock3 size={25} className="mx-auto text-[#96a5a6]" />
 <p className="mt-3 text-sm text-[#657678]">暂无运行记录</p>
 <p className="mt-1 text-xs text-[#8b999a]">从资料集详情页创建第一次生成</p>
 </div>
 )}
 </section>
 </div>
 )
}