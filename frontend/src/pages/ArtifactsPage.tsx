import { useEffect, useState } from 'react'
import { ArrowRight, BookOpen, Boxes } from 'lucide-react'
import { Link } from 'react-router-dom'
import { productApi } from '@/api/product'
import type { ArtifactSummary } from '@/product-types'

export function ArtifactsPage() {
  const [items, setItems] = useState<ArtifactSummary[]>([])
  const [error, setError] = useState('')
  useEffect(() => { void productApi.artifacts().then(setItems).catch((err) => setError((err as Error).message)) }, [])
 return <div className="mx-auto max-w-[1180px] px-4 py-6 md:px-10 md:py-10"><header><p className="text-xs font-semibold text-[#147d86]">ARTIFACTS</p><h1 className="mt-2 text-[28px] font-semibold">生成产物</h1><p className="mt-2 text-sm text-[#718183]">每次运行生成独立版本，可以分别阅读、检查和导出。</p></header>{error && <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}<div className="mt-7 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{items.map((item) => <Link key={item.artifact_id} to={`/artifacts/${item.artifact_id}`} className="group rounded-lg border border-[#dfe6e6] bg-white p-5 hover:border-[#9bcacc]"><div className="flex items-start justify-between"><span className="grid size-10 place-items-center rounded-md bg-[#e7f3f3] text-[#147d86]"><BookOpen size={18} /></span><span className="rounded-full bg-[#edf7f1] px-2 py-1 text-[10px] text-[#27774a]">{item.status === 'ready' ? '已完成' : '部分完成'}</span></div><h2 className="mt-5 line-clamp-2 text-[16px] font-semibold">{item.title}</h2><p className="mt-2 text-xs text-[#718183]">{item.chapter_count} 章 · 资料集 {item.dataset_name || item.dataset_id || '—'}</p><div className="mt-5 flex items-center border-t border-[#edf0f0] pt-4 font-mono text-[10px] text-[#819092]">{item.run_id}<ArrowRight size={14} className="ml-auto transition-transform group-hover:translate-x-1" /></div></Link>)}</div>{!items.length && !error && <div className="mt-7 rounded-lg border border-dashed border-[#cbd8d8] bg-white py-20 text-center"><Boxes className="mx-auto text-[#96a5a6]" /><p className="mt-3 text-sm text-[#657678]">暂无生成产物</p></div>}</div>
}
