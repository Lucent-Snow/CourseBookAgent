import { useEffect, useState } from 'react'
import { ArrowRight, BookOpen, Boxes } from 'lucide-react'
import { Link } from 'react-router-dom'
import { DemoEntry, type DemoPreset } from '@/components/DemoEntry'
import { productApi } from '@/api/product'
import type { ArtifactSummary } from '@/product-types'

export function ArtifactsPage() {
 const [items, setItems] = useState<ArtifactSummary[]>([])
 const [preset, setPreset] = useState<DemoPreset | null | undefined>(undefined)
 const [loading, setLoading] = useState(true)
 const [error, setError] = useState('')
 useEffect(() => {
  void productApi.artifacts().then(setItems).catch((err) => setError((err as Error).message)).finally(() => setLoading(false))
  void fetch('/api/session').then((res) => res.json()).then((session) => setPreset(session.preset ?? null)).catch(() => setPreset(null))
 }, [])
 return <div className="mx-auto max-w-[1180px] px-4 py-6 md:px-10 md:py-10">
  <header><p className="text-xs font-semibold text-[#147d86]">COURSE BOOKS</p><h1 className="mt-2 text-[28px] font-semibold">生成产物</h1><p className="mt-2 text-sm text-[#718183]">每次生成都会保留独立版本。选择一本教辅，阅读、检查或导出 Markdown。</p></header>
  {preset !== undefined && <div className="mt-7"><DemoEntry preset={preset} /></div>}
  {error && <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
  <div className="mt-8 flex items-end justify-between border-b border-[#dfe6e6] pb-4"><h2 className="text-lg font-semibold">全部书稿</h2><span className="text-xs text-[#718183]">{items.length} 个版本</span></div>
  <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{items.map((item) => <Link key={item.artifact_id} to={`/artifacts/${item.artifact_id}`} className="group flex min-h-56 flex-col rounded-xl border border-[#dfe6e6] bg-white p-5 transition-all hover:border-[#9bcacc] hover:shadow-[0_8px_25px_rgba(20,80,84,.08)]"><div className="flex items-start justify-between"><span className="grid size-10 place-items-center rounded-md bg-[#e7f3f3] text-[#147d86]"><BookOpen size={18} /></span><span className={`rounded-full px-2 py-1 text-[10px] font-medium ${item.status === 'ready' ? 'bg-[#edf7f1] text-[#27774a]' : 'bg-amber-50 text-amber-800'}`}>{item.status === 'ready' ? '已完成' : '部分完成'}</span></div><h3 className="mt-5 line-clamp-2 text-[17px] font-semibold">{item.title}</h3><p className="mt-2 text-xs leading-5 text-[#718183]">{item.dataset_name || item.dataset_id || '未命名资料集'} · {item.chapter_count} 章</p><div className="mt-auto flex items-center border-t border-[#edf0f0] pt-4 text-xs text-[#718183]"><span>{item.created_at ? new Date(item.created_at).toLocaleDateString('zh-CN') : '时间未知'} · 阅读书稿</span><ArrowRight size={15} className="ml-auto text-[#147d86] transition-transform group-hover:translate-x-1" /></div></Link>)}</div>
  {!items.length && !error && <div className="mt-5 rounded-xl border border-dashed border-[#cbd8d8] bg-white py-20 text-center"><Boxes className="mx-auto text-[#96a5a6]" /><p className="mt-3 text-sm text-[#657678]">{loading ? '正在加载书稿…' : '暂无生成产物'}</p>{!loading && <p className="mt-1 text-xs text-[#8b999a]">从<Link to="/datasets" className="mx-1 text-[#147d86] underline">资料集</Link>选择资料并创建第一次生成。</p>}</div>}
 </div>
}
