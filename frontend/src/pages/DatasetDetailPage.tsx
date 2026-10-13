import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ArrowLeft,
  BookOpen,
  Check,
  Eye,
  File,
  FileText,
  FolderOpen,
  Play,
  Presentation,
  RefreshCw,
  Upload,
} from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { MaterialImportDialog } from '@/components/product/MaterialImportDialog'
import { productApi } from '@/api/product'
import type { DatasetDetail, DatasetRunSummary, Resource } from '@/product-types'

const iconFor = (kind: Resource['kind']) =>
  ['pptx', 'courseware'].includes(kind) ? Presentation : kind === 'transcript' ? FileText : File

const kindLabel = (kind: Resource['kind']) => {
  if (kind === 'transcript') return '课堂字幕'
  if (kind === 'pptx') return 'PPT 课件'
  if (kind === 'pdf') return 'PDF 讲义'
  if (kind === 'docx') return 'Word 文档'
  if (kind === 'courseware') return '智云板书'
  return '文本资料'
}

const formatChars = (chars = 0) =>
  chars >= 10000 ? `${(chars / 10000).toFixed(1)} 万字` : chars >= 1000 ? `${(chars / 1000).toFixed(1)} 千字` : `${chars} 字`

export function DatasetDetailPage() {
  const { datasetId = '' } = useParams()
  const navigate = useNavigate()
  const input = useRef<HTMLInputElement>(null)
  const [detail, setDetail] = useState<DatasetDetail | null>(null)
  const [runs, setRuns] = useState<DatasetRunSummary[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState<{ title: string; text: string } | null>(null)
  const [showImport, setShowImport] = useState(false)

  const load = useCallback(async () => {
    try {
      const [detailData, runsData] = await Promise.all([
        productApi.dataset(datasetId),
        productApi.datasetRuns(datasetId).catch(() => ({ data: [], dataset: { dataset_id: datasetId, name: '' } })),
      ])
      setDetail(detailData)
      setRuns(runsData.data ?? [])
    } catch (err) {
      setError((err as Error).message)
    }
  }, [datasetId])

  useEffect(() => {
    void load()
  }, [load])

  async function upload(files: FileList | null) {
    if (!files?.length) return
    setBusy(true)
    setError('')
    try {
      for (const file of Array.from(files)) await productApi.upload(datasetId, file)
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  async function showPreview(resource: Resource) {
    const revision = resource.current_revision
    if (!revision) return
    try {
      const data = await productApi.preview(revision.revision_id)
      setPreview({ title: resource.title, text: data.text })
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (!detail) {
    return <div className="p-12 text-center text-sm text-[#718183]">{error || '正在读取资料集…'}</div>
  }

  const readyResources = detail.resources.filter((item) => item.current_revision?.parse_status === 'ready')
  const completedRuns = runs.filter((r) => r.artifact_available)

  return (
    <div className="mx-auto max-w-[1240px] px-4 py-6 md:px-8 md:py-8">
      {/* Return Link */}
      <Link
        to="/datasets"
        className="inline-flex items-center gap-1.5 text-xs font-medium text-[#718183] transition-colors hover:text-[#147d86]"
      >
        <ArrowLeft size={14} /> 返回资料库
      </Link>

      {/* Main Asymmetrical Canvas */}
      <div className="mt-5 grid gap-8 lg:grid-cols-[360px_1fr]">
        {/* Left Column: Course Control Studio */}
        <aside className="space-y-5">
          <div className="rounded-2xl border border-[#e2e8e8] bg-white p-6 shadow-xs">
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#147d86]">
              <FolderOpen size={14} /> 课程资料台
            </span>
            <h1 className="mt-2 text-2xl font-bold tracking-tight text-[#172b2d]">
              {detail.dataset.name}
            </h1>
            <p className="mt-2 text-xs leading-relaxed text-[#687a7c]">
              {detail.dataset.description || '在这里长期汇聚课程资料；随时选择资料并发起教辅书编撰。'}
            </p>

            {/* Big Action: Start Generating */}
            <div className="mt-6 border-t border-[#f0f3f3] pt-5">
              <Button
                disabled={readyResources.length === 0}
                onClick={() => navigate(`/datasets/${datasetId}/configure`)}
                className="w-full bg-[#147d86] py-5 text-sm font-semibold text-white hover:bg-[#116a72]"
              >
                <Play size={15} className="mr-1.5 fill-current" />
                配置并开始编撰
              </Button>
              <p className="mt-2 text-center text-[11px] text-[#819294]">
                {readyResources.length > 0
                  ? `当前已就绪 ${readyResources.length} 份材料`
                  : '请先添加课件或字幕材料'}
              </p>
            </div>

            {/* Quick Upload Buttons */}
            <div className="mt-5 grid grid-cols-2 gap-2 border-t border-[#f0f3f3] pt-4">
              <input
                ref={input}
                type="file"
                multiple
                accept=".pptx,.pdf,.docx,.md,.markdown,.txt"
                className="hidden"
                onChange={(e) => void upload(e.target.files)}
              />
              <Button
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => input.current?.click()}
                className="text-xs"
              >
                <Upload size={13} className="mr-1" /> 上传文件
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => setShowImport(true)}
                className="text-xs"
              >
                <RefreshCw size={13} className="mr-1" /> 平台导入
              </Button>
            </div>
          </div>

          {/* If there's an existing finished book */}
          {completedRuns.length > 0 && (
            <div className="rounded-2xl bg-[#173c40] p-6 text-white shadow-xs">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-[#a3d6d4]">
                <BookOpen size={14} /> 最新完稿
              </div>
              <h3 className="mt-2 text-base font-bold">已成书稿可立即阅读</h3>
              <p className="mt-1 text-xs leading-relaxed text-[#cde3e2]">
                最近一次编撰已完成，包含完整的知识体系与分章正文。
              </p>
              <div className="mt-4 flex gap-2">
                <Button
                  render={<Link to={`/artifacts/${completedRuns[0].job_id}`} />}
                  size="sm"
                  className="bg-white text-xs font-medium text-[#173c40] hover:bg-[#e6f3f3]"
                >
                  打开书稿
                </Button>
                <Button
                  render={<Link to={`/runs/${completedRuns[0].job_id}`} />}
                  size="sm"
                  variant="outline"
                  className="border-white/30 text-xs text-white hover:bg-white/10"
                >
                  编撰过程
                </Button>
              </div>
            </div>
          )}
        </aside>

        {/* Right Column: Material Gallery */}
        <main className="min-w-0 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-[#172b2d]">课程收录资料</h2>
            <span className="text-xs text-[#718183]">
              {readyResources.length} 份可用 · 共 {detail.resources.length} 项
            </span>
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
              {error}
            </div>
          )}

          <div className="overflow-hidden rounded-2xl border border-[#e2e8e8] bg-white shadow-xs">
            {detail.resources.length === 0 ? (
              <div className="p-16 text-center text-xs text-[#718183]">
                <FileText size={24} className="mx-auto mb-2 text-[#9bb0b2]" />
                暂未添加任何课件或字幕。点击左侧上传文件开始。
              </div>
            ) : (
              <div className="divide-y divide-[#f0f3f3]">
                {detail.resources.map((resource) => {
                  const Icon = iconFor(resource.kind)
                  const rev = resource.current_revision
                  const isReady = rev?.parse_status === 'ready'
                  return (
                    <div
                      key={resource.resource_id}
                      className="flex items-center justify-between gap-4 p-5 transition-colors hover:bg-[#fafcfc]"
                    >
                      <div className="flex items-center gap-3.5 min-w-0">
                        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-[#eef5f5] text-[#147d86]">
                          <Icon size={18} />
                        </span>
                        <div className="min-w-0">
                          <h4 className="truncate text-sm font-semibold text-[#172b2d]">
                            {resource.title}
                          </h4>
                          <p className="mt-1 flex items-center gap-2 text-xs text-[#7c8d90]">
                            <span>{kindLabel(resource.kind)}</span>
                            {rev?.text_chars ? (
                              <>
                                <span>·</span>
                                <span>{formatChars(rev.text_chars)}</span>
                              </>
                            ) : null}
                          </p>
                        </div>
                      </div>

                      <div className="flex shrink-0 items-center gap-3">
                        {isReady ? (
                          <span className="flex items-center gap-1 text-xs font-medium text-[#27774a]">
                            <Check size={14} /> 已解析
                          </span>
                        ) : (
                          <span className="text-xs text-red-600">
                            {rev?.parse_error || '解析中'}
                          </span>
                        )}

                        {isReady && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => void showPreview(resource)}
                            className="text-xs text-[#147d86] hover:bg-[#eef5f5]"
                          >
                            <Eye size={14} className="mr-1" /> 预览
                          </Button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </main>
      </div>

      {showImport && (
        <MaterialImportDialog
          datasetId={datasetId}
          onClose={() => setShowImport(false)}
          onImported={() => {
            void load()
          }}
        />
      )}

      {/* Preview Drawer */}
      {preview && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-2xs"
          onClick={() => setPreview(null)}
        >
          <div
            className="flex h-full w-full max-w-xl flex-col bg-white p-8 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[#edf0f0] pb-4">
              <h3 className="truncate text-base font-bold text-[#172b2d]">{preview.title}</h3>
              <Button variant="ghost" size="sm" onClick={() => setPreview(null)}>
                关闭
              </Button>
            </div>
            <div className="mt-4 flex-1 overflow-auto pr-2">
              <pre className="whitespace-pre-wrap font-sans text-xs leading-relaxed text-[#35484a]">
                {preview.text || '没有可读取的文本内容'}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
