import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, Check, Eye, File, FileText, Layers, Presentation, RefreshCw, Trash2, Upload } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { MaterialImportDialog } from '@/components/product/MaterialImportDialog'
import { productApi } from '@/api/product'
import type { DatasetDetail, DatasetRunSummary, Resource } from '@/product-types'

const iconFor = (kind: Resource['kind']) => ['pptx', 'courseware'].includes(kind) ? Presentation : kind === 'transcript' ? FileText : File
const sourceLabel = (resource: Resource) => {
 if (resource.source_type === 'xuezai') return `${resource.kind === 'xuezai_upload' ? '学在浙大课件' : '学在浙大'} · ${resource.current_revision?.metadata.module || resource.current_revision?.filename || ''}`
 if (resource.source_type === 'zhiyun') return `${resource.kind === 'courseware' ? '智云课件页' : '智云字幕'} · 第 ${String(resource.current_revision?.metadata.lecture_index ?? '-')} 讲`
 return resource.current_revision?.filename || ''
}
const formatSize = (value = 0) => value < 1024 ? `${value} B` : value < 1024 * 1024 ? `${(value / 1024).toFixed(1)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`
const formatTime = (value: string | null) => value ? new Date(value).toLocaleString() : '—'
const statusLabel = (status: string | null | undefined) => status === 'completed' ? '已完成' : status === 'partial' ? '部分完成' : status === 'failed' ? '失败' : status === 'running' ? '运行中' : status === 'queued' ? '排队' : '—'

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

 async function load() {
 try {
 const [detailData, runsData] = await Promise.all([
 productApi.dataset(datasetId),
 productApi.datasetRuns(datasetId).catch(() => ({ data: [], dataset: { dataset_id: datasetId, name: '' } })),
 ])
 setDetail(detailData)
 setRuns(runsData.data ?? [])
 } catch (err) { setError((err as Error).message) }
 }

 useEffect(() => { void load() }, [datasetId])

 async function upload(files: FileList | null) {
 if (!files?.length) return
 setBusy(true)
 setError('')
 try { for (const file of Array.from(files)) await productApi.upload(datasetId, file); await load() }
 catch (err) { setError((err as Error).message) }
 finally { setBusy(false); if (input.current) input.current.value = '' }
 }

 async function showPreview(resource: Resource) {
 const revision = resource.current_revision; if (!revision) return
 try {
 const data = await productApi.preview(revision.revision_id)
 setPreview({ title: resource.title, text: data.text })
 } catch (err) { setError((err as Error).message) }
 }

 async function deleteRun(jobId: string) {
 if (!window.confirm(`确认删除运行 ${jobId} 及其产物？此操作不可恢复。`)) return
 try {
 await productApi.deleteRun(jobId)
 await load()
 } catch (err) { setError((err as Error).message) }
 }

 if (!detail) return <div className="p-10 text-sm text-[#718183]">{error || '正在读取资料集…'}</div>
 const ready = detail.resources.filter((item) => item.current_revision?.parse_status === 'ready').length

 return (
 <div className="mx-auto max-w-[1180px] px-4 py-6 md:px-10 md:py-9">
 <Link to="/datasets" className="inline-flex items-center gap-2 text-sm text-[#718183] hover:text-[#147d86]">
 <ArrowLeft size={15} />返回资料库
 </Link>
 <header className="mt-6 flex flex-col items-start justify-between gap-4 border-b border-[#dfe6e6] pb-6 lg:flex-row">
 <div>
 <h1 className="text-[28px] font-semibold">{detail.dataset.name}</h1>
 <p className="mt-2 text-sm text-[#718183]">{detail.dataset.description || '在这里长期保存所有课程资料；生成时再选择本次使用范围。'}</p>
 </div>
 <div className="flex gap-2">
 <input ref={input} type="file" multiple accept=".pptx,.pdf,.docx,.md,.markdown,.txt" className="hidden" onChange={(e) => void upload(e.target.files)} />
 <Button variant="outline" disabled={busy} onClick={() => input.current?.click()}><Upload size={15} />上传文件</Button>
 <Button disabled={busy} onClick={() => setShowImport(true)} className="bg-[#147d86] text-white hover:bg-[#116a72]"><RefreshCw size={15} />从平台导入</Button>
 </div>
 </header>

 <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-4">
 {[[detail.resources.length, '全部资料'], [ready, '解析可用'], [detail.snapshots.length, '输入快照'], [runs.length, '生成记录']].map(([value, label]) => (
 <div key={String(label)} className="rounded-lg border border-[#dfe6e6] bg-white p-4">
 <strong className="text-2xl">{value}</strong>
 <p className="mt-1 text-xs text-[#718183]">{label}</p>
 </div>
 ))}
 </div>

 {error && <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

 <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_340px]">
 {/* ── 资料内容 ─────────────────────────────────────────────── */}
 <div className="space-y-5">
 <section className="overflow-hidden rounded-lg border border-[#dfe6e6] bg-white">
 <div className="flex items-center justify-between border-b border-[#edf0f0] px-5 py-4">
 <div>
 <h2 className="text-sm font-semibold">资料内容</h2>
 <p className="mt-1 text-xs text-[#819092]">支持 PPTX、PDF、DOCX、Markdown、TXT、智云课堂字幕与学在浙大课件</p>
 </div>
 <span className="text-xs text-[#819092]">{detail.resources.length} 项</span>
 </div>
 {detail.resources.length ? (
 <div className="divide-y divide-[#edf0f0]">
 {detail.resources.map((resource) => {
 const Icon = iconFor(resource.kind)
 const revision = resource.current_revision
 return (
 <div key={resource.resource_id} className="flex items-center gap-3 px-5 py-4">
 <span className="grid size-9 place-items-center rounded-md bg-[#eef4f4] text-[#147d86]"><Icon size={17} /></span>
 <div className="min-w-0 flex-1">
 <p className="truncate text-sm font-medium">{resource.title}</p>
 <p className="mt-1 text-[11px] text-[#819092]">{sourceLabel(resource)} · {formatSize(revision?.size_bytes)}</p>
 </div>
 <span className={revision?.parse_status === 'ready' ? 'text-[#27774a]' : 'text-red-600'}>
 {revision?.parse_status === 'ready' ? <Check size={15} /> : (revision?.parse_error || '解析失败')}
 </span>
 {revision?.parse_status === 'ready' && (
 <Button variant="ghost" size="icon-sm" title="预览资料" onClick={() => void showPreview(resource)}><Eye size={15} /></Button>
 )}
 </div>
 )
 })}
 </div>
 ) : (
 <div className="py-16 text-center text-sm text-[#718183]">上传文件或导入智云课程开始建立资料集</div>
 )}
 </section>

 {/* ── 该资料集的所有生成记录 ───────────────────────────────────── */}
 <section className="overflow-hidden rounded-lg border border-[#dfe6e6] bg-white">
 <div className="flex items-center justify-between border-b border-[#edf0f0] px-5 py-4">
 <div>
 <h2 className="text-sm font-semibold flex items-center gap-2"><Layers size={15} />本资料集的所有生成记录</h2>
 <p className="mt-1 text-xs text-[#819092]">按生成时间倒序；点击进入运行详情，或删除一条记录。</p>
 </div>
 <span className="text-xs text-[#819092]">{runs.length} 条</span>
 </div>
 {runs.length ? (
 <div className="divide-y divide-[#edf0f0]">
 {runs.map((run, idx) => (
 <div key={run.job_id} className="flex items-center gap-3 px-5 py-4">
 <span className={`inline-flex h-7 items-center rounded-full px-3 text-[10px] font-medium ${run.status === 'completed' ? 'bg-[#e9f5ee] text-[#27774a]' : run.status === 'partial' ? 'bg-amber-50 text-amber-700' : run.status === 'failed' ? 'bg-red-50 text-red-700' : 'bg-[#e6f3f3] text-[#147d86]'}`}>
 第 {runs.length - idx} 次
 </span>
 <div className="min-w-0 flex-1">
 <p className="text-sm font-medium truncate">
 第 {runs.length - idx} 次生成 · {statusLabel(run.status)} · {run.progress}%
 </p>
 <p className="mt-1 truncate text-[11px] text-[#819092]">运行 {run.job_id} · 创建于 {formatTime(run.created_at)}{run.snapshot_id && ` · 快照 ${run.snapshot_id.slice(-12)}`}{run.course_id && ` · 课程 ${run.course_id}`}</p>
 </div>
 {run.artifact_available && (
 <Link to={`/artifacts/${run.job_id}`} className="text-xs text-[#147d86] hover:underline">查看产物</Link>
 )}
 <Link to={`/runs/${run.job_id}`} className="inline-flex h-7 items-center gap-1 rounded-md border border-[#dfe6e6] bg-white px-2.5 text-xs font-medium text-[#147d86] hover:bg-[#f7f9f9]"><RefreshCw size={13} />运行详情</Link>
 <Button variant="ghost" size="icon-sm" title="删除运行" onClick={() => void deleteRun(run.job_id)}><Trash2 size={15} className="text-red-600" /></Button>
 </div>
 ))}
 </div>
 ) : (
 <div className="py-14 text-center text-sm text-[#718183]">
 该资料集还没有生成记录。
 <div className="mt-3"><Button variant="outline" size="sm" onClick={() => navigate(`/datasets/${datasetId}/configure`)}><ArrowRight size={13} />开始第一次生成</Button></div>
 </div>
 )}
 </section>
 </div>

 {/* ── sidebar ──────────────────────────────────────────────── */}
 <aside className="space-y-5">
 <div className="rounded-lg border border-[#b8dadb] bg-[#f2f9f9] p-5">
 <h2 className="text-sm font-semibold">创建一次生成</h2>
 <p className="mt-2 text-xs leading-5 text-[#657678]">下一步选择这次使用的具体资料，创建不可变输入快照，再配置课程教辅工作流。</p>
 <Button disabled={!ready} onClick={() => navigate(`/datasets/${datasetId}/configure`)} className="mt-5 w-full bg-[#147d86] text-white hover:bg-[#116a72]">选择资料并配置</Button>
 </div>
 <div className="rounded-lg border border-[#dfe6e6] bg-white p-5">
 <h2 className="text-sm font-semibold">历史输入快照</h2>
 {detail.snapshots.length ? (
 <div className="mt-3 space-y-3">
 {detail.snapshots.slice(0, 5).map((snapshot) => (
 <div key={snapshot.snapshot_id} className="rounded-md bg-[#f7f9f9] p-3">
 <p className="text-xs font-medium">{snapshot.label || '未命名快照'}</p>
 <p className="mt-1 text-[10px] text-[#819092]">{snapshot.resource_count} 项资料 · {snapshot.sha256.slice(0,8)}</p>
 </div>
 ))}
 </div>
 ) : (
 <p className="mt-3 text-xs text-[#819092]">尚未创建快照</p>
 )}
 </div>
 </aside>
 </div>

 {showImport && <MaterialImportDialog datasetId={datasetId} onClose={() => setShowImport(false)} onImported={() => { void load() }} />}
 {preview && (
 <div className="fixed inset-0 z-40 flex justify-end bg-black/25" onClick={() => setPreview(null)}>
 <div className="h-full w-[520px] overflow-auto bg-white p-7 shadow-xl" onClick={(e) => e.stopPropagation()}>
 <div className="flex items-center justify-between">
 <h2 className="text-base font-semibold">{preview.title}</h2>
 <Button variant="ghost" onClick={() => setPreview(null)}>关闭</Button>
 </div>
 <pre className="mt-6 whitespace-pre-wrap font-sans text-sm leading-7 text-[#425456]">{preview.text || '没有可预览文本'}</pre>
 </div>
 </div>
 )}
 </div>
 )
}