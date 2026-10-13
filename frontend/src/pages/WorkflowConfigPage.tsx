import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, Check, ChevronRight, FileText, Play, Sparkles } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { productApi } from '@/api/product'
import type { DatasetDetail, WorkflowPreset } from '@/product-types'

export function WorkflowConfigPage() {
  const { datasetId = '' } = useParams()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<DatasetDetail | null>(null)
  const [preset, setPreset] = useState<WorkflowPreset | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [concurrency, setConcurrency] = useState(3)
  const [review, setReview] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    void Promise.all([productApi.dataset(datasetId), productApi.presets()])
      .then(([data, presets]) => {
        setDetail(data)
        setPreset(presets[0] ?? null)
        setSelected(
          new Set(
            data.resources
              .filter((item) => item.current_revision?.parse_status === 'ready')
              .map((item) => item.current_revision!.revision_id)
          )
        )
      })
      .catch((err) => setError((err as Error).message))
  }, [datasetId])

  const readyResources = useMemo(
    () => detail?.resources.filter((item) => item.current_revision?.parse_status === 'ready') ?? [],
    [detail]
  )

  function toggle(id: string) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function start() {
    if (!detail || !selected.size) return
    setBusy(true)
    setError('')
    try {
      const snapshot = await productApi.createSnapshot(
        datasetId,
        [...selected],
        `${detail.dataset.name} · ${new Date().toLocaleString()}`
      )
      const selectedResources = readyResources.filter((item) =>
        selected.has(item.current_revision!.revision_id)
      )
      const course = selectedResources.find((item) => item.source_type === 'zhiyun')
        ?.current_revision?.metadata.course_id

      const job = await productApi.startRun(
        course ? String(course) : '',
        snapshot.snapshot_id,
        concurrency,
        review
      )
      navigate(`/runs/${job.job_id}`)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!detail || !preset) {
    return <div className="p-12 text-center text-sm text-[#718183]">{error || '正在配置编撰工作流…'}</div>
  }

  const allSelected =
    readyResources.length > 0 &&
    readyResources.every((item) => selected.has(item.current_revision!.revision_id))

  return (
    <div className="min-h-dvh bg-[#f7f9f9]">
      <header className="flex h-16 items-center justify-between border-b border-[#e2e8e8] bg-white px-6 md:px-8">
        <Link
          to={`/datasets/${datasetId}`}
          className="flex items-center gap-1.5 text-xs font-medium text-[#718183] transition-colors hover:text-[#147d86]"
        >
          <ArrowLeft size={14} /> 返回资料台
        </Link>
        <span className="text-xs font-semibold text-[#172b2d]">成书配置</span>
        <Button
          onClick={() => void start()}
          disabled={busy || !selected.size}
          className="bg-[#147d86] text-xs font-semibold text-white hover:bg-[#116a72]"
        >
          {busy ? '正在启动…' : '开始编撰'}
          <ChevronRight size={14} className="ml-1" />
        </Button>
      </header>

      <div className="mx-auto grid max-w-[1240px] grid-cols-1 gap-8 px-4 py-8 lg:grid-cols-[1fr_360px] lg:px-8">
        <main>
          <div className="border-b border-[#e2e8e8] pb-5">
            <h1 className="text-2xl font-bold tracking-tight text-[#172b2d]">选择本次编撰所用资料</h1>
            <p className="mt-1.5 text-xs text-[#718183]">
              勾选纳入全书的课件与字幕；AI 主编将统筹规划知识主题与章节大纲。
            </p>
          </div>

          {error && (
            <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
              {error}
            </div>
          )}

          <div className="mt-6 overflow-hidden rounded-2xl border border-[#e2e8e8] bg-white shadow-xs">
            <div className="flex h-12 items-center justify-between border-b border-[#f0f3f3] px-5">
              <label className="flex cursor-pointer items-center gap-2.5 text-xs font-semibold text-[#172b2d]">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={() =>
                    setSelected(
                      allSelected
                        ? new Set()
                        : new Set(readyResources.map((item) => item.current_revision!.revision_id))
                    )
                  }
                  className="rounded text-[#147d86] focus:ring-[#147d86]"
                />
                全选可用资料
              </label>
              <span className="text-xs text-[#718183]">
                已选 {selected.size} / {readyResources.length} 份
              </span>
            </div>

            <div className="divide-y divide-[#f0f3f3]">
              {readyResources.map((resource) => {
                const isSelected = selected.has(resource.current_revision!.revision_id)
                return (
                  <label
                    key={resource.resource_id}
                    className={`flex cursor-pointer items-center gap-3.5 px-5 py-4 transition-colors ${
                      isSelected ? 'bg-[#fafcfc]' : 'hover:bg-[#fafcfc]'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggle(resource.current_revision!.revision_id)}
                      className="rounded text-[#147d86] focus:ring-[#147d86]"
                    />
                    <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#eef5f5] text-[#147d86]">
                      <FileText size={16} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <strong className="block truncate text-sm font-semibold text-[#172b2d]">
                        {resource.title}
                      </strong>
                      <span className="mt-0.5 block text-xs text-[#7c8f91]">
                        {resource.source_type === 'zhiyun'
                          ? `课堂字幕 · 第 ${String(resource.current_revision?.metadata.lecture_index)} 讲`
                          : `${resource.kind.toUpperCase()} · ${resource.current_revision?.text_chars?.toLocaleString()} 字`}
                      </span>
                    </div>
                    <Check
                      size={16}
                      className={isSelected ? 'text-[#147d86]' : 'text-transparent'}
                    />
                  </label>
                )
              })}
            </div>
          </div>
        </main>

        {/* Right Settings Sidebar */}
        <aside className="space-y-5">
          <div className="rounded-2xl border border-[#d6e7e8] bg-[#f4f9f9] p-6 shadow-xs">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-[#147d86]">
              <Sparkles size={14} /> 课程教辅流水线
            </span>
            <h3 className="mt-2 text-base font-bold text-[#172b2d]">全书规划与分章撰写</h3>
            <p className="mt-1 text-xs leading-relaxed text-[#596d6f]">
              主 Agent 通读所有资料并规划全书大纲与主题章节，按知识点装配上下文后由分章 Agent 撰写成稿。
            </p>
          </div>

          <div className="rounded-2xl border border-[#e2e8e8] bg-white p-6 shadow-xs">
            <h3 className="text-sm font-bold text-[#172b2d]">生成参数</h3>

            <div className="mt-4">
              <label className="block text-xs font-medium text-[#657678]">
                章节并行撰写数
              </label>
              <div className="mt-2 flex gap-2">
                {[1, 2, 3, 4].map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setConcurrency(value)}
                    className={`size-9 rounded-xl border text-xs font-semibold transition-colors ${
                      concurrency === value
                        ? 'border-[#147d86] bg-[#e6f3f3] text-[#147d86]'
                        : 'border-[#dfe6e6] text-[#4d5f61] hover:bg-[#f6f9f9]'
                    }`}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>

            <label className="mt-5 flex cursor-pointer items-center justify-between text-xs">
              <div>
                <span className="block font-semibold text-[#172b2d]">启用语义质量审校</span>
                <span className="mt-0.5 block text-[#819294]">
                  自动扫描知识覆盖与概念规范
                </span>
              </div>
              <input
                type="checkbox"
                checked={review}
                onChange={(e) => setReview(e.target.checked)}
                className="rounded text-[#147d86] focus:ring-[#147d86]"
              />
            </label>
          </div>

          <Button
            onClick={() => void start()}
            disabled={busy || !selected.size}
            className="w-full bg-[#147d86] py-5 text-sm font-semibold text-white shadow-sm hover:bg-[#116a72]"
          >
            <Play size={15} className="mr-1.5 fill-current" />
            {busy ? '正在启动…' : '开始编撰教辅书'}
          </Button>
        </aside>
      </div>
    </div>
  )
}
