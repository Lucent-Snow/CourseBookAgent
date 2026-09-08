import { useEffect, useState } from 'react'
import { AlertTriangle, ArrowLeft, Bot, Clock3, FileText, Layers, Pause, RefreshCw, ShieldAlert, Tag } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { api } from '@/api/client'
import { productApi } from '@/api/product'
import type { QualityReport, ResourceProjection, RunProjection, StageProjection } from '@/product-types'

const STAGE_ORDER: Array<{ key: keyof StageProjection | 'rendered'; label: string; hint: string }> = [
 { key: 'parsed', label: '1. 解析所有资料', hint: '把资料切成可引用的最小单元' },
 { key: 'described', label: '2. 生成资料说明', hint: '为主 Agent 提供每份资料的描述' },
 { key: 'planned', label: '3. 规划章节与 Tag', hint: '主 Agent 决定章节、为每份资料打 Tag' },
 { key: 'assembled', label: '4. 按 Tag 装上下文', hint: '把 chapter / global 资料装进对应章节' },
 { key: 'chapters_succeeded', label: '5. 章节 Agent 并发生成', hint: '每个章节 Agent 写一章' },
 { key: 'synthesized', label: '6. 全书合成', hint: '统一术语、前言、衔接' },
 { key: 'rendered', label: '7. 渲染并输出', hint: '输出最终 Markdown' },
]

function stageIndex(stage: StageProjection): number {
 if (!stage.parsed_total && !stage.described_total) return -1
 if (!stage.rendered) return -1
 const counts: Array<boolean> = [
 stage.parsed === stage.parsed_total && stage.parsed_total > 0,
 stage.described === stage.described_total && stage.described_total > 0,
 stage.planned,
 stage.assembled === stage.assembled_total && stage.assembled_total > 0,
 stage.chapters_succeeded + stage.chapters_failed === stage.chapters_total && stage.chapters_total > 0,
 stage.synthesized,
 stage.rendered,
 ]
 const idx = counts.findIndex((c) => !c)
 return idx === -1 ? counts.length - 1 : idx - 1
}

const agentTone = { pending: 'text-[#829092] bg-[#f1f3f3]', running: 'text-[#147d86] bg-[#e6f3f3]', succeeded: 'text-[#27774a] bg-[#e9f5ee]', failed: 'text-red-700 bg-red-50', blocked: 'text-amber-700 bg-amber-50' }

const tagTone: Record<ResourceProjection['tag_kind'], string> = {
 chapter: 'text-[#147d86] bg-[#e6f3f3] border-[#b8dadb]',
 global: 'text-[#27774a] bg-[#e9f5ee] border-[#b6d8c6]',
 none: 'text-[#6f6f6f] bg-[#f1f3f3] border-[#d8dada]',
}

function describeStatusTone(s: ResourceProjection['description_status']) {
 switch (s) {
 case 'done': return 'text-[#27774a] bg-[#e9f5ee]'
 case 'running': return 'text-[#147d86] bg-[#e6f3f3]'
 case 'failed': return 'text-red-700 bg-red-50'
 default: return 'text-[#829092] bg-[#f1f3f3]'
 }
}

export function RunDetailPage() {
 const { runId = '' } = useParams()
 const [run, setRun] = useState<RunProjection | null>(null)
 const [error, setError] = useState('')

 useEffect(() => {
 const refresh = () => { void productApi.run(runId).then(setRun).catch((err) => setError((err as Error).message)) }
 refresh()
 const timer = window.setInterval(refresh, 1200)
 return () => window.clearInterval(timer)
 }, [runId])

 async function action(kind: 'retry' | 'cancel') { try { if (kind === 'retry') await api.retryJob(runId); else await api.cancelJob(runId); } catch (err) { setError((err as Error).message) } }

 if (!run) return <div className="p-10 text-sm text-[#718183]">{error || '正在读取运行状态…'}</div>

 const stage = run.stage
 const currentStageIdx = stageIndex(stage)

 return (
 <div className="mx-auto max-w-[1180px] px-4 py-6 md:px-10 md:py-8">
 <header className="flex items-start justify-between gap-4">
 <div>
 <Link to="/runs" className="inline-flex items-center gap-2 text-sm text-[#718183]"><ArrowLeft size={15} />返回运行中心</Link>
 <h1 className="mt-5 text-[25px] font-semibold">{run.dataset_name || '资料集生成'}</h1>
 <p className="mt-2 font-mono text-xs text-[#819092]">运行 {run.run_id}{run.snapshot_id && ` · 输入快照 ${run.snapshot_id.slice(-12)}`}{run.course_id && ` · 课程 ${run.course_id}`}</p>
 <p className="mt-2 font-mono text-xs text-[#819092]">{run.run_id}{run.snapshot_id && ` · 输入快照 ${run.snapshot_id}`}</p>
 </div>
 <div className="flex gap-2">
 {['failed','partial','interrupted'].includes(run.status) && <Button variant="outline" onClick={() => void action('retry')}><RefreshCw size={14} />恢复或重试</Button>}
 {['queued','running'].includes(run.status) && <Button variant="outline" onClick={() => void action('cancel')}><Pause size={14} />停止运行</Button>}
 {run.artifact_available && <Button render={<Link to={`/artifacts/${run.run_id}`} />} className="bg-[#147d86] text-white">查看产物</Button>}
 </div>
 </header>

 {error && <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

 <div className="mt-7 grid gap-5 lg:grid-cols-[1fr_340px]">
 <main className="space-y-5">
 {/* ── 当前阶段 step indicator ─────────────────────────────── */}
 <section className="rounded-lg border border-[#dfe6e6] bg-white p-5">
 <div className="flex items-center justify-between">
 <div>
 <h2 className="text-base font-semibold">{run.message || '运行准备中'}</h2>
 <p className="mt-1 text-xs text-[#718183]">当前阶段：{STAGE_ORDER[Math.max(currentStageIdx, 0)]?.label ?? '排队'}</p>
 </div>
 <strong className="text-2xl text-[#147d86]">{run.progress}%</strong>
 </div>
 <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#e7eeee]">
 <div className="h-full rounded-full bg-[#147d86] transition-all" style={{ width: `${run.progress}%` }} />
 </div>
 <ol className="mt-4 grid grid-cols-7 gap-2">
 {STAGE_ORDER.map((s, i) => {
 const done = i < currentStageIdx
 const active = i === currentStageIdx
 return (
 <li key={String(s.key)} className={`rounded-md px-2 py-2 text-[10px] ${done ? 'bg-[#e9f5ee] text-[#27774a]' : active ? 'bg-[#e6f3f3] text-[#147d86] border border-[#b8dadb]' : 'bg-[#f7f9f9] text-[#a6b3b4]'}`}>
 <p className="truncate font-medium">{s.label}</p>
 <p className="mt-1 truncate text-[9px] opacity-80">{s.hint}</p>
 </li>
 )
 })}
 </ol>
 <div className="mt-4 grid grid-cols-3 gap-3 text-[11px] text-[#718183]">
 <span>已解析 {stage.parsed}/{stage.parsed_total} 份</span>
 <span>已描述 {stage.described}/{stage.described_total} 份</span>
 <span>{stage.planned ? `已规划 ${stage.plan_summary.chapter_count} 章` : '尚未规划'}</span>
 <span>已组装 {stage.assembled}/{stage.assembled_total} 章上下文</span>
 <span>章节 {stage.chapters_succeeded}/{stage.chapters_total} succeeded</span>
 <span>{stage.chapters_failed} 失败</span>
 </div>
 </section>

 {/* ── Per-resource transparency ─────────────────────────────── */}
 <section className="rounded-lg border border-[#dfe6e6] bg-white p-5">
 <div className="flex items-center justify-between">
 <h2 className="text-base font-semibold flex items-center gap-2"><FileText size={16} />资料与描述</h2>
 <span className="text-xs text-[#718183]">{run.resources.length} 份</span>
 </div>
 <p className="mt-1 text-xs text-[#718183]">每份资料的描述生成状态、与章节 Tag 的关联。</p>
 <div className="mt-4 divide-y divide-[#edf0f0]">
 {run.resources.length === 0 && <div className="py-10 text-center text-sm text-[#718183]">尚未解析任何资料</div>}
 {run.resources.map((r) => (
 <div key={r.revision_id} className="grid grid-cols-[1fr_120px_220px] gap-4 py-3">
 <div>
 <p className="text-sm font-medium truncate">{r.title || r.revision_id}</p>
 <p className="mt-1 text-[10px] text-[#819092]">{r.kind}/{r.provider} · rev={r.revision_id.slice(-8)}</p>
 {r.description_text && <p className="mt-2 text-xs leading-5 text-[#657678]">{r.description_text}</p>}
 {r.description_topic && <p className="mt-1 text-[10px] text-[#879496]">主题：{r.description_topic} · 范围：{r.description_scope} · 角色：{r.description_suggested_role}</p>}
 </div>
 <span className={`inline-flex h-7 items-center justify-center rounded-full px-3 text-[10px] ${describeStatusTone(r.description_status)}`}>{r.description_status}</span>
 <div>
 <span className={`inline-flex h-7 items-center gap-1 rounded-md border px-2 text-[10px] ${tagTone[r.tag_kind]}`}>
 <Tag size={11} />{r.tag_kind === 'chapter' ? `章节 (${r.tag_chapter_ids.join(', ')})` : r.tag_kind === 'global' ? '全局资料' : '未参与本次生成'}
 </span>
 </div>
 </div>
 ))}
 </div>
 </section>

 {/* Per-chapter agents — gated until assemble step */}
 {run.progress >= 28 && (
 <section className="rounded-lg border border-[#dfe6e6] bg-white p-5">
 <h2 className="text-base font-semibold flex items-center gap-2"><Layers size={16} />章节 Agent</h2>
 <p className="mt-1 text-xs text-[#718183]">结构化任务状态</p>
 <div className="mt-4 divide-y divide-[#edf0f0]">
 {run.agents.length === 0 && <div className="py-10 text-center text-sm text-[#718183]">任务将在装上下文后出现</div>}
 {run.agents.map((agent) => (
 <div key={agent.agent_id} className="flex items-center gap-3 py-3">
 <span className="grid size-9 place-items-center rounded-md bg-[#eef4f4] text-[#147d86]"><Bot size={16} /></span>
 <div className="min-w-0 flex-1">
 <p className="text-sm font-medium truncate">{agent.label}</p>
 <p className="mt-1 truncate text-[11px] text-[#718183]">{agent.message}</p>
 </div>
 <span className={`rounded-full px-2 py-1 text-[10px] font-medium ${agentTone[agent.status]}`}>{agent.status}</span>
 </div>
 ))}
 </div>
 </section>
 )}

 {/* Quality report */}
 {run.quality.length > 0 && (
 <section className="rounded-lg border border-[#dfe6e6] bg-white p-5">
 <h2 className="text-base font-semibold flex items-center gap-2"><ShieldAlert size={16} />质量检测</h2>
 <p className="mt-1 text-xs text-[#718183]">{run.quality.length} 章质量扫描 · {run.quality.filter((q) => q.warnings.length > 0).length} 章有警告</p>
 <div className="mt-4 divide-y divide-[#edf0f0]">
 {run.quality.map((q: QualityReport) => (
 <div key={q.chapter_id} className="py-3">
 <div className="flex items-center gap-3">
 <p className="text-sm font-medium truncate">{q.title || q.chapter_id}</p>
 <span className={`rounded-full px-2 py-0.5 text-[10px] ${q.warnings.length === 0 ? 'bg-[#e9f5ee] text-[#27774a]' : 'bg-amber-50 text-amber-700'}`}>{q.warnings.length === 0 ? '通过' : `${q.warnings.length} 警告`}</span>
 </div>
 <p className="mt-1 text-[11px] text-[#718183]">{q.section_count} 个小节 · {q.component_count} 个组件 · 来源 {q.source_revision_ids.length} 处（未在范围内 {q.missing_source_count}）</p>
 {q.warnings.length > 0 && (
 <ul className="mt-2 space-y-1 text-[11px] text-amber-700">
 {q.warnings.map((w, i) => <li key={i}>· {w}</li>)}
 </ul>
 )}
 </div>
 ))}
 </div>
 </section>
 )}
 </main>

 <aside className="space-y-5">
 <section className="rounded-lg border border-[#dfe6e6] bg-white p-5">
 <h2 className="text-sm font-semibold">运行信息</h2>
 <dl className="mt-4 space-y-3 text-xs">
 {[
 ['状态', run.status],
 ['工作流', run.preset_id],
 ...(run.course_id ? [['课程 ID', run.course_id]] : []),
 ['更新时间', run.updated_at ? new Date(run.updated_at).toLocaleString() : '—'],
 ['资料集 ID', run.dataset_id.slice(-12)],
 ['运行 ID', run.run_id],
].map(([label, value]) => (
 <div key={String(label)} className="flex justify-between gap-4">
 <dt className="text-[#718183]">{label}</dt>
 <dd className="text-right font-mono text-[11px]">{value}</dd>
 </div>
 ))}
 </dl>
 </section>

 {run.failed_agents > 0 && (
 <section className="rounded-lg border border-red-200 bg-red-50 p-5">
 <div className="flex items-center gap-2 text-sm font-semibold text-red-700"><AlertTriangle size={16} />存在失败任务</div>
 <p className="mt-2 text-xs leading-5 text-red-700/80">当前后端支持复用检查点，只重新生成失败或未完成章节。</p>
 <Button variant="outline" className="mt-4 border-red-300 bg-white text-red-700" onClick={() => void action('retry')}><RefreshCw size={14} />重试失败任务</Button>
 </section>
 )}

 <section className="rounded-lg bg-[#eef6f6] p-4 text-xs leading-5 text-[#657678]">
 <Clock3 size={15} className="mb-2 text-[#147d86]" />
 当前版本展示章节级 Agent。更细的实时步骤和中间草稿将在生成核心提供结构化回调后自动扩展。
 </section>
 </aside>
 </div>
 </div>
 )
}