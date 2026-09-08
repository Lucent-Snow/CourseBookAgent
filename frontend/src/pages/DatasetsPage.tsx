import { useEffect, useState } from 'react'
import { ArrowRight, FileText, FolderOpen, Plus, Search } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { productApi } from '@/api/product'
import type { Dataset } from '@/product-types'

export function DatasetsPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<Dataset[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')

  async function load() {
    setLoading(true)
    try { setItems(await productApi.datasets()) } catch (err) { setError((err as Error).message) } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])
  async function createDataset() {
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    try { const created = await productApi.createDataset(name); setShowCreate(false); navigate(`/datasets/${created.dataset_id}`) } catch (err) { setError((err as Error).message) } finally { setCreating(false) }
  }
  const filtered = items.filter((item) => `${item.name} ${item.description}`.toLowerCase().includes(query.toLowerCase()))
  return <div className="mx-auto max-w-[1180px] px-4 py-6 md:px-10 md:py-10">
    <header className="flex flex-col items-start justify-between gap-5 sm:flex-row sm:items-end"><div><p className="text-xs font-semibold text-[#147d86]">MATERIAL LIBRARY</p><h1 className="mt-2 text-[28px] font-semibold">资料库</h1><p className="mt-2 text-sm text-[#718183]">集中保存课程字幕、PPT 与文档，再按需选择本次生成所用资料。</p></div><Button onClick={() => setShowCreate(true)} disabled={creating} className="bg-[#147d86] text-white hover:bg-[#116a72]"><Plus size={16} />新建资料集</Button></header>
    <div className="mt-8 flex items-center justify-between border-b border-[#dfe6e6] pb-4"><span className="border-b-2 border-[#147d86] pb-4 text-sm font-medium text-[#147d86]">全部资料集 {items.length}</span><label className="flex h-9 w-64 items-center gap-2 rounded-md border border-[#dfe6e6] bg-white px-3"><Search size={15} className="text-[#91a0a1]" /><Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索资料集" className="h-auto border-0 p-0 shadow-none focus-visible:ring-0" /></label></div>
    {error && <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    {loading ? <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[1,2,3].map((x) => <div key={x} className="h-48 animate-pulse rounded-lg bg-[#e6ecec]" />)}</div> : filtered.length ? <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{filtered.map((item) => <Link key={item.dataset_id} to={`/datasets/${item.dataset_id}`} className="group rounded-lg border border-[#dfe6e6] bg-white p-5 hover:border-[#9bcacc] hover:shadow-[0_8px_25px_rgba(20,80,84,.08)]"><div className="flex items-start justify-between"><span className="grid size-10 place-items-center rounded-md bg-[#e7f3f3] text-[#147d86]"><FolderOpen size={19} /></span><span className="rounded-full bg-[#edf7f1] px-2 py-1 text-[10px] font-medium text-[#27774a]">{item.ready_count}/{item.resource_count} 可用</span></div><h2 className="mt-5 text-[17px] font-semibold">{item.name}</h2><p className="mt-2 min-h-10 text-sm leading-5 text-[#718183]">{item.description || '尚未添加说明'}</p><div className="mt-5 flex items-center border-t border-[#edf0f0] pt-4 text-xs text-[#7b898b]"><FileText size={14} className="mr-1.5" />{item.resource_count} 份资料<ArrowRight size={15} className="ml-auto transition-transform group-hover:translate-x-1" /></div></Link>)}</div> : <div className="mt-6 rounded-lg border border-dashed border-[#cbd8d8] bg-white py-20 text-center"><FolderOpen size={26} className="mx-auto text-[#96a5a6]" /><p className="mt-3 text-sm text-[#637476]">还没有资料集</p><p className="mt-1 text-xs text-[#8a989a]">创建后可导入智云课程或上传自己的资料</p><Button className="mt-5 bg-[#147d86] text-white" onClick={() => setShowCreate(true)}><Plus size={15} />创建第一个资料集</Button></div>}
    {showCreate && <div className="fixed inset-0 z-50 grid place-items-center bg-black/25 p-4" onClick={() => setShowCreate(false)}><div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl" onClick={(event) => event.stopPropagation()}><h2 className="text-base font-semibold">新建资料集</h2><p className="mt-2 text-xs text-[#718183]">资料集可以从空白开始，之后上传文件或导入智云课程。</p><Input autoFocus value={newName} onChange={(event) => setNewName(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void createDataset() }} placeholder="例如：应用统计学课程资料" className="mt-5" /><div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={() => setShowCreate(false)}>取消</Button><Button disabled={!newName.trim() || creating} onClick={() => void createDataset()} className="bg-[#147d86] text-white">创建资料集</Button></div></div></div>}
  </div>
}
