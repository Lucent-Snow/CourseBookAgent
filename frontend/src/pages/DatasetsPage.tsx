import { useEffect, useState } from 'react'
import { ArrowRight, BookOpen, FileText, FolderOpen, Plus, Search, Settings, Sparkles } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { infrastructureApi } from '@/api/infrastructure'
import { productApi } from '@/api/product'
import { DemoEntry, type DemoPreset } from '@/components/DemoEntry'
import type { Dataset } from '@/product-types'

export function DatasetsPage() {
  const navigate = useNavigate()
  const [session, setSession] = useState<{ guest: boolean; cloud: boolean; preset: DemoPreset | null } | null>(null)
  useEffect(() => { void fetch('/api/session').then((r) => r.json()).then(setSession).catch(() => setSession({ guest: false, cloud: false, preset: null })) }, [])
  const [items, setItems] = useState<Dataset[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [setup, setSetup] = useState<{ llm: boolean; zhiyun: boolean; xuezai: boolean } | null>(null)

  async function load() {
    setLoading(true)
    try { setItems(await productApi.datasets()) } catch (err) { setError((err as Error).message) } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [])
  useEffect(() => {
    void Promise.all([infrastructureApi.health(), productApi.providerAuth()]).then(([health, providers]) => {
      setSetup({
        llm: health.llm_configured,
        zhiyun: providers.zhiyun.authenticated,
        xuezai: providers.xue_zai_zju.authenticated,
      })
    }).catch(() => undefined)
  }, [])
  async function createDataset() {
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    try { const created = await productApi.createDataset(name); setShowCreate(false); navigate(`/datasets/${created.dataset_id}`) } catch (err) { setError((err as Error).message) } finally { setCreating(false) }
  }
  const filtered = items.filter((item) => `${item.name} ${item.description}`.toLowerCase().includes(query.toLowerCase()))
  const readyTotal = items.reduce((total, item) => total + item.ready_count, 0)
  return <div className="mx-auto max-w-[1180px] px-4 py-6 md:px-10 md:py-10">
    <header className="rounded-2xl bg-[#173c40] px-6 py-7 text-white md:px-9 md:py-9">
      <p className="text-xs font-semibold tracking-[.18em] text-[#a3d6d4]">COURSE MATERIALS → COURSE BOOK</p>
      <h1 className="mt-3 max-w-[680px] text-3xl font-semibold leading-tight md:text-4xl">把散落的课程资料，整理成一本可阅读的教辅</h1>
      <p className="mt-4 max-w-[650px] text-sm leading-6 text-[#d7e9e8]">上传课堂字幕、PPTX、PDF、DOCX、Markdown 或 TXT；系统按知识主题规划章节、分章撰写，最后生成可阅读、可导出的书稿。</p>
      <div className="mt-6 flex flex-wrap items-center gap-3"><Button onClick={() => setShowCreate(true)} disabled={creating} className="bg-white text-[#17494d] hover:bg-[#e7f3f3]"><Plus size={16} />从自己的资料开始</Button><span className="text-xs text-[#b9d8d7]">上传是主路径 · 校园平台导入可选</span></div>
    </header>
    <section aria-label="使用步骤" className="mt-5 grid gap-3 md:grid-cols-3">
      {[
        { icon: FolderOpen, title: '01 建立资料集', text: '上传文件，或导入智云、学在浙大的课程资料。' },
        { icon: Sparkles, title: '02 选择资料并生成', text: '锁定本次资料版本，查看主题规划与章节进度。' },
        { icon: BookOpen, title: '03 阅读与导出', text: '阅读教辅草稿，检查后下载 Markdown。' },
      ].map(({ icon: Icon, title, text }) => <div key={title} className="rounded-xl border border-[#dfe6e6] bg-white p-4"><Icon size={18} className="text-[#147d86]" /><h2 className="mt-3 text-sm font-semibold">{title}</h2><p className="mt-1 text-xs leading-5 text-[#718183]">{text}</p></div>)}
    </section>
    {session?.guest && <p className="mt-5 text-xs text-[#718183]">当前为独立游客空间，资料仅在此浏览器中可访问。清除浏览器 Cookie 后无法找回。</p>}
    {session?.cloud && <p className="mt-2 text-xs text-[#718183]">上传和阅读不会调用模型。生成需配置自己的模型；较慢的模型可能超时，已完成的步骤会保留。</p>}
    {session && <div className="mt-6"><DemoEntry preset={session.preset} /></div>}
    <div className="mt-9 flex flex-col justify-between gap-3 border-b border-[#dfe6e6] pb-4 sm:flex-row sm:items-end"><div><h2 className="text-lg font-semibold">我的资料集</h2><p className="mt-1 text-xs text-[#718183]">{items.length} 个资料集 · {readyTotal} 份已就绪资料</p></div><label className="flex h-9 w-full items-center gap-2 rounded-md border border-[#dfe6e6] bg-white px-3 sm:w-64"><Search size={15} className="text-[#91a0a1]" /><Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索资料集" className="h-auto border-0 p-0 shadow-none focus-visible:ring-0" /></label></div>
    {error && <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    {setup && !setup.llm && <div className="mt-5 flex flex-col items-start justify-between gap-3 rounded-md border border-amber-200 bg-amber-50 p-4 sm:flex-row sm:items-center"><div><p className="text-sm font-medium text-amber-900">重新生成前请配置模型</p><p className="mt-1 text-xs leading-5 text-amber-800">已有成品可直接阅读；上传资料不需要校内账号。模型配置仅用于自己的生成任务。</p></div><Button render={<Link to="/settings" />} variant="outline" size="sm" className="shrink-0 border-amber-300 bg-white text-amber-900"><Settings size={14} />去系统设置</Button></div>}
    {loading ? <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[1,2,3].map((x) => <div key={x} className="h-56 animate-pulse rounded-lg bg-[#e6ecec]" />)}</div> : filtered.length ? <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{filtered.map((item) => <Link key={item.dataset_id} to={`/datasets/${item.dataset_id}`} className="group flex min-h-64 flex-col rounded-xl border border-[#dfe6e6] bg-white p-5 transition-all hover:border-[#9bcacc] hover:shadow-[0_8px_25px_rgba(20,80,84,.08)]"><div className="flex items-start justify-between"><span className="grid size-10 place-items-center rounded-md bg-[#e7f3f3] text-[#147d86]"><FolderOpen size={19} /></span><span className={`rounded-full px-2 py-1 text-[10px] font-medium ${item.ready_count ? 'bg-[#edf7f1] text-[#27774a]' : 'bg-amber-50 text-amber-800'}`}>{item.ready_count ? `${item.ready_count} 份可用` : '等待添加资料'}</span></div><h3 className="mt-5 line-clamp-2 text-[17px] font-semibold">{item.name}</h3><p className="mt-2 line-clamp-2 min-h-10 text-sm leading-5 text-[#718183]">{item.description || '课程资料会集中保存在这里，供后续生成使用。'}</p><div className="mt-auto pt-5"><div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#718183]"><span><FileText size={13} className="mr-1 inline" />共 {item.resource_count} 份资料</span><span>更新于 {item.updated_at ? new Date(item.updated_at).toLocaleDateString('zh-CN') : '—'}</span></div><div className="mt-4 flex items-center justify-between border-t border-[#edf0f0] pt-4 text-sm font-medium text-[#147d86]"><span>{item.ready_count ? '查看资料并选择生成' : '进入并添加资料'}</span><ArrowRight size={16} className="transition-transform group-hover:translate-x-1" /></div></div></Link>)}</div> : <div className="mt-6 rounded-lg border border-dashed border-[#cbd8d8] bg-white py-20 text-center"><FolderOpen size={26} className="mx-auto text-[#96a5a6]" /><p className="mt-3 text-sm text-[#637476]">{query ? '没有匹配的资料集' : '还没有资料集'}</p><p className="mt-1 text-xs text-[#8a989a]">{query ? '试试其他关键词' : '创建后可上传自己的资料，也可导入校园课程'}</p>{!query && <Button className="mt-5 bg-[#147d86] text-white" onClick={() => setShowCreate(true)}><Plus size={15} />创建第一个资料集</Button>}</div>}
    {showCreate && <div className="fixed inset-0 z-50 grid place-items-center bg-black/25 p-4" onClick={() => setShowCreate(false)}><div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl" onClick={(event) => event.stopPropagation()}><h2 className="text-base font-semibold">新建资料集</h2><p className="mt-2 text-xs text-[#718183]">资料集可以从空白开始，之后上传文件或导入智云课程。</p><Input autoFocus value={newName} onChange={(event) => setNewName(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void createDataset() }} placeholder="例如：应用统计学课程资料" className="mt-5" /><div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={() => setShowCreate(false)}>取消</Button><Button disabled={!newName.trim() || creating} onClick={() => void createDataset()} className="bg-[#147d86] text-white">创建资料集</Button></div></div></div>}
  </div>
}
