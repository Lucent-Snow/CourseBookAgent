import { useEffect, useState } from 'react'
import { ArrowRight, FolderOpen, Plus, Search, Settings, Sparkles } from 'lucide-react'
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
  const [items, setItems] = useState<Dataset[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [setup, setSetup] = useState<{ llm: boolean } | null>(null)

  useEffect(() => {
    void fetch('/api/session')
      .then((r) => r.json())
      .then(setSession)
      .catch(() => setSession({ guest: false, cloud: false, preset: null }))
  }, [])

  async function load() {
    setLoading(true)
    try {
      setItems(await productApi.datasets())
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    void infrastructureApi
      .health()
      .then((health) => setSetup({ llm: health.llm_configured }))
      .catch(() => undefined)
  }, [])

  async function createDataset() {
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    try {
      const created = await productApi.createDataset(name)
      setShowCreate(false)
      navigate(`/datasets/${created.dataset_id}`)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setCreating(false)
    }
  }

  const filtered = items.filter((item) =>
    `${item.name} ${item.description}`.toLowerCase().includes(query.toLowerCase())
  )
  const readyTotal = items.reduce((total, item) => total + item.ready_count, 0)

  return (
    <div className="mx-auto max-w-[1180px] px-4 py-6 md:px-10 md:py-10">
      {/* Editorial Hero Banner */}
      <header className="rounded-2xl bg-[#173c40] px-7 py-8 text-white shadow-sm md:px-10 md:py-10">
        <div className="flex items-center gap-2 text-xs font-semibold tracking-wider text-[#a3d6d4] uppercase">
          <Sparkles size={14} /> Course Materials → CourseBook
        </div>
        <h1 className="mt-3 max-w-2xl text-2xl font-bold tracking-tight md:text-4xl">
          把散落的课程资料，整理成一本系统教辅
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[#d7e9e8]">
          上传课堂 PPT、讲义文档与字幕，由 AI 主编统筹规划章节架构并逐章撰写，生成结构严密、可连续阅读与复习的教辅书。
        </p>

        <div className="mt-7 flex flex-wrap items-center gap-3">
          <Button
            onClick={() => setShowCreate(true)}
            disabled={creating}
            className="bg-white font-medium text-[#173c40] hover:bg-[#e7f3f3]"
          >
            <Plus size={16} className="mr-1" /> 新建课程资料集
          </Button>
          {session?.preset && (
            <div className="inline-flex items-center">
              <DemoEntry preset={session.preset} />
            </div>
          )}
        </div>
      </header>

      {/* Model Setup Hint (Tasteful, only if not configured) */}
      {setup && !setup.llm && (
        <div className="mt-6 flex flex-col justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50/70 p-4 sm:flex-row sm:items-center">
          <p className="text-xs text-amber-900">
            <strong>未配置模型：</strong>浏览已有书稿无需配置；如需开始新的成书任务，请前往设置配置 API Key。
          </p>
          <Button
            render={<Link to="/settings" />}
            variant="outline"
            size="sm"
            className="shrink-0 border-amber-300 bg-white text-xs text-amber-900 hover:bg-amber-50"
          >
            <Settings size={13} className="mr-1" /> 配置模型
          </Button>
        </div>
      )}

      {/* Collection Search & Header */}
      <div className="mt-10 flex flex-col justify-between gap-4 border-b border-[#e2e8e8] pb-4 sm:flex-row sm:items-end">
        <div>
          <h2 className="text-xl font-bold text-[#172b2d]">课程资料库</h2>
          <p className="mt-1 text-xs text-[#718183]">
            {items.length} 个课程资料集 · {readyTotal} 份已就绪资料
          </p>
        </div>

        <label className="flex h-9 w-full items-center gap-2 rounded-lg border border-[#dfe6e6] bg-white px-3 sm:w-64">
          <Search size={15} className="text-[#91a0a1]" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索课程名称…"
            className="h-auto border-0 p-0 text-xs shadow-none focus-visible:ring-0"
          />
        </label>
      </div>

      {error && (
        <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          {error}
        </div>
      )}

      {/* Grid of Datasets */}
      <div className="mt-6">
        {loading ? (
          <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((x) => (
              <div key={x} className="h-52 animate-pulse rounded-xl bg-[#e8efef]" />
            ))}
          </div>
        ) : filtered.length > 0 ? (
          <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {filtered.map((item) => (
              <Link
                key={item.dataset_id}
                to={`/datasets/${item.dataset_id}`}
                className="group flex min-h-[220px] flex-col rounded-2xl border border-[#e2e8e8] bg-white p-6 transition-all hover:border-[#9bcacc] hover:shadow-sm"
              >
                <div className="flex items-start justify-between">
                  <span className="grid size-10 place-items-center rounded-xl bg-[#e7f3f3] text-[#147d86]">
                    <FolderOpen size={18} />
                  </span>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                      item.ready_count ? 'bg-[#edf7f1] text-[#27774a]' : 'bg-[#f4f7f7] text-[#718183]'
                    }`}
                  >
                    {item.ready_count ? `${item.ready_count} 份资料可用` : '空资料集'}
                  </span>
                </div>

                <h3 className="mt-4 line-clamp-2 text-lg font-bold tracking-tight text-[#172b2d] group-hover:text-[#147d86] transition-colors">
                  {item.name}
                </h3>

                <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-[#687a7c]">
                  {item.description || '课程资料集中在此，可随时发起教辅编撰。'}
                </p>

                <div className="mt-auto border-t border-[#f0f3f3] pt-4">
                  <div className="flex items-center justify-between text-xs font-medium text-[#147d86]">
                    <span>进入资料集并成书</span>
                    <ArrowRight size={15} className="transition-transform group-hover:translate-x-1" />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-[#cbd8d8] bg-white py-16 text-center">
            <FolderOpen size={28} className="mx-auto text-[#96a5a6]" />
            <p className="mt-3 text-sm font-medium text-[#5a6b6d]">
              {query ? '没有找到匹配的课程' : '暂无课程资料集'}
            </p>
            <p className="mt-1 text-xs text-[#8a989a]">
              新建资料集后可上传课件、讲义，或直接导入校园课程
            </p>
            {!query && (
              <Button
                className="mt-5 bg-[#147d86] text-white hover:bg-[#116a72]"
                onClick={() => setShowCreate(true)}
              >
                <Plus size={15} className="mr-1" /> 新建第一个资料集
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Modal: New Dataset */}
      {showCreate && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-4 backdrop-blur-2xs"
          onClick={() => setShowCreate(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-bold text-[#172b2d]">新建课程资料集</h2>
            <p className="mt-1.5 text-xs text-[#718183]">
              输入课程名称，创建后可直接上传课件或导入讲义资料。
            </p>
            <Input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void createDataset()
              }}
              placeholder="例如：概率论与数理统计"
              className="mt-5 text-sm"
            />
            <div className="mt-6 flex justify-end gap-2.5">
              <Button variant="outline" onClick={() => setShowCreate(false)}>
                取消
              </Button>
              <Button
                disabled={!newName.trim() || creating}
                onClick={() => void createDataset()}
                className="bg-[#147d86] text-white hover:bg-[#116a72]"
              >
                创建并进入
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
