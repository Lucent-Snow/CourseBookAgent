import { useEffect, useState } from 'react'
import { Activity, AlertTriangle, ArrowRight, CheckCircle2, Clock3 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { productApi } from '@/api/product'
import type { RunProjection } from '@/product-types'

const statusLabel: Record<string, string> = { queued: '排队中', running: '运行中', completed: '已完成', partial: '部分完成', failed: '失败', interrupted: '已中断', cancelled: '已取消' }
export function RunsPage() {
  const [runs, setRuns] = useState<RunProjection[]>([])
  const [error, setError] = useState('')
  useEffect(() => { void productApi.runs().then(setRuns).catch((err) => setError((err as Error).message)) }, [])
  return <div className="mx-auto max-w-[1180px] px-4 py-6 md:px-10 md:py-10"><header><p className="text-xs font-semibold text-[#147d86]">RUN CENTER</p><h1 className="mt-2 text-[28px] font-semibold">运行中心</h1><p className="mt-2 text-sm text-[#718183]">查看每次生成的阶段、章节 Agent、异常与产物。</p></header>{error && <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}<section className="mt-7 overflow-hidden rounded-lg border border-[#dfe6e6] bg-white">{runs.length ? <div className="divide-y divide-[#edf0f0]">{runs.map((run) => <Link key={run.run_id} to={`/runs/${run.run_id}`} className="grid grid-cols-[1.4fr_.8fr_.8fr_.8fr_28px] items-center gap-4 px-5 py-4 hover:bg-[#fafcfc]"><div><p className="flex items-center gap-2 text-sm font-medium"><Activity size={15} className="text-[#147d86]" />课程 {run.course_id}</p><p className="mt-1 font-mono text-[10px] text-[#819092]">{run.run_id}</p></div><span className="text-xs text-[#657678]">{statusLabel[run.status] || run.status}</span><span className="text-xs text-[#657678]">{run.progress}%</span><span className={`flex items-center gap-1.5 text-xs ${run.failed_agents ? 'text-red-600' : 'text-[#27774a]'}`}>{run.failed_agents ? <AlertTriangle size={14} /> : <CheckCircle2 size={14} />}{run.failed_agents ? `${run.failed_agents} 个异常` : `${run.total_agents} 个任务`}</span><ArrowRight size={15} className="text-[#9aa7a8]" /></Link>)}</div> : <div className="py-20 text-center"><Clock3 size={25} className="mx-auto text-[#96a5a6]" /><p className="mt-3 text-sm text-[#657678]">暂无运行记录</p><p className="mt-1 text-xs text-[#8b999a]">从资料集详情页创建第一次生成</p></div>}</section></div>
}
