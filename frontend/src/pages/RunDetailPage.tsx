import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Compass,
  Download,
  FileText,
  Pause,
  RefreshCw,
  Sparkles,
} from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { productApi } from '@/api/product'
import type { AgentProjection, PlannedChapterSummary, RunProjection } from '@/product-types'

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    queued: '排队中',
    running: '正在撰写',
    completed: '编撰完成',
    partial: '部分完成',
    failed: '生成中断',
    retrying: '重新尝试中',
    interrupted: '已暂停',
    cancelled: '已停止',
  }
  return map[status] || status
}

function statusBadgeClass(status: string): string {
  if (status === 'completed') return 'bg-[#e9f5ee] text-[#236e44]'
  if (['failed', 'partial', 'interrupted'].includes(status)) return 'bg-amber-50 text-amber-800 border border-amber-200'
  if (status === 'running') return 'bg-[#e6f3f3] text-[#147d86]'
  return 'bg-[#f0f3f3] text-[#6d7f81]'
}

export function RunDetailPage() {
  const { runId = '' } = useParams()
  const [run, setRun] = useState<RunProjection | null>(null)
  const [error, setError] = useState('')
  const [selectedChapterId, setSelectedChapterId] = useState<string | null>(null)

  useEffect(() => {
    const refresh = () => {
      void productApi
        .run(runId)
        .then((data) => {
          setRun(data)
          // If no chapter selected, pick the running or first chapter
          setSelectedChapterId((prev) => {
            if (prev) return prev
            const running = data.agents.find((a) => a.status === 'running')
            if (running) return running.chapter_id || running.agent_id
            return null
          })
        })
        .catch((err) => setError((err as Error).message))
    }
    refresh()
    const timer = window.setInterval(refresh, 1500)
    return () => window.clearInterval(timer)
  }, [runId])

  async function action(kind: 'retry' | 'cancel') {
    try {
      const res = await fetch(`/api/runs/${runId}/${kind}`, { method: 'POST' })
      if (!res.ok) {
        const detail = await res.json().then((b) => b?.detail).catch(() => '')
        throw new Error(detail || `操作失败（${res.status}）`)
      }
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (!run) {
    return (
      <div className="mx-auto max-w-4xl p-12 text-center text-sm text-[#718183]">
        {error || '正在打开书卷…'}
      </div>
    )
  }

  const plan = run.stage.plan_summary || {}
  const displayTitle = plan.book_title || run.dataset_name || '课程精讲与复习教辅'
  const positioning = plan.book_positioning
  const modules = plan.modules || []
  const plannedChapters: PlannedChapterSummary[] = plan.planned_chapters || []
  const learningPath = plan.learning_path || []
  const globalEmphasis = plan.global_emphasis || []

  // Agents mapped by chapter id
  const agents = run.agents || []
  const agentByChapterId = new Map<string, AgentProjection>()
  agents.forEach((a) => {
    const cid = a.chapter_id || a.agent_id
    agentByChapterId.set(cid, a)
  })

  // Selected agent or planned chapter info
  const selectedAgent = selectedChapterId ? agentByChapterId.get(selectedChapterId) : null
  const selectedPlannedChapter = plannedChapters.find((c) => c.chapter_id === selectedChapterId)

  // Live narrative string
  let liveNarrative = run.message || '正在撰写…'
  if (run.status === 'completed') {
    liveNarrative = `全书已完稿，共收录 ${run.stage.chapters_total || agents.length} 个知识章节`
  } else if (['failed', 'partial', 'interrupted'].includes(run.status)) {
    liveNarrative = '生成遇到异常或中断；已写成的章节已妥善保存，可随时继续'
  }

  const totalChapters = run.stage.chapters_total || agents.length || plannedChapters.length
  const completedChapters = run.stage.chapters_succeeded || agents.filter((a) => a.status === 'succeeded').length

  return (
    <div className="mx-auto max-w-[1240px] px-4 py-6 md:px-8 md:py-8">
      {/* Return Link */}
      <Link
        to="/runs"
        className="inline-flex items-center gap-1.5 text-xs font-medium text-[#718183] transition-colors hover:text-[#147d86]"
      >
        <ArrowLeft size={14} /> 返回运行中心
      </Link>

      {/* Hero Header: Bold, Editorial, Confident */}
      <header className="mt-4 flex flex-col justify-between gap-6 border-b border-[#e2e8e8] pb-6 lg:flex-row lg:items-end">
        <div className="max-w-3xl">
          <div className="flex items-center gap-2 text-xs font-medium">
            <span className="flex items-center gap-1 text-[#147d86]">
              <BookOpen size={14} /> 课程教辅
            </span>
            <span className="text-[#a4b2b4]">·</span>
            <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${statusBadgeClass(run.status)}`}>
              {statusLabel(run.status)}
            </span>
          </div>

          <h1 className="mt-3 text-2xl font-bold tracking-tight text-[#172b2d] sm:text-3xl">
            {displayTitle}
          </h1>

          {positioning ? (
            <p className="mt-2.5 text-sm leading-relaxed text-[#54686a] italic">
              “{positioning}”
            </p>
          ) : (
            <p className="mt-2 text-sm text-[#728385]">
              基于课程资料，由 AI 主编统筹规划章节架构并逐章执笔
            </p>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex shrink-0 flex-wrap items-center gap-2.5">
          {['failed', 'partial', 'interrupted'].includes(run.status) && (
            <Button
              variant="outline"
              onClick={() => void action('retry')}
              className="border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100"
            >
              <RefreshCw size={14} className="mr-1.5" /> 恢复并继续
            </Button>
          )}

          {['queued', 'running'].includes(run.status) && (
            <Button variant="outline" onClick={() => void action('cancel')}>
              <Pause size={14} className="mr-1.5" /> 暂停
            </Button>
          )}

          {run.artifact_available && (
            <>
              <Button
                render={<a href={`/api/runs/${run.run_id}/download.html`} download />}
                variant="outline"
                className="hover:border-[#147d86] hover:text-[#147d86]"
              >
                <Download size={14} className="mr-1.5" /> 纸书 HTML
              </Button>
              <Button
                render={<Link to={`/artifacts/${run.run_id}`} />}
                className="bg-[#147d86] text-white hover:bg-[#116a72]"
              >
                <BookOpen size={14} className="mr-1.5" /> 打开书稿
              </Button>
            </>
          )}
        </div>
      </header>

      {/* Slim Progress Bar */}
      <div className="mt-4 flex items-center justify-between text-xs">
        <span className="flex items-center gap-2 text-[#687a7c]">
          {run.status === 'running' && <span className="size-2 animate-ping rounded-full bg-[#147d86]" />}
          {liveNarrative}
        </span>
        <span className="font-semibold text-[#172b2d]">
          {totalChapters > 0 ? `${completedChapters} / ${totalChapters} 章` : `${run.progress}%`}
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#e7eeee]">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            run.status === 'running' ? 'flow-progress' : 'bg-[#147d86]'
          }`}
          style={{ width: `${Math.max(2, run.progress)}%` }}
        />
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          {error}
        </div>
      )}

      {/* Main Studio Canvas: Left Outline vs Right Knowledge Showcase */}
      <div className="mt-8 grid gap-8 lg:grid-cols-[380px_1fr]">
        {/* Left Column: The Living Outline */}
        <aside className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold tracking-tight text-[#172b2d]">全书目录与进度</h2>
            <button
              type="button"
              onClick={() => setSelectedChapterId(null)}
              className={`text-xs transition-colors ${
                selectedChapterId === null ? 'font-semibold text-[#147d86]' : 'text-[#718183] hover:text-[#172b2d]'
              }`}
            >
              查看全书大纲
            </button>
          </div>

          <div className="overflow-hidden rounded-xl border border-[#e2e8e8] bg-white shadow-xs">
            {plannedChapters.length === 0 && agents.length === 0 ? (
              <div className="p-8 text-center text-xs text-[#718183]">
                <Clock3 size={20} className="mx-auto mb-2 text-[#9bb0b2]" />
                正在通读资料并规划目录结构…
              </div>
            ) : (
              <div className="divide-y divide-[#f0f3f3]">
                {/* Modules & Chapters */}
                {modules.length > 0
                  ? modules.map((mod, mIdx) => {
                      const modChapters = plannedChapters.filter(
                        (ch, idx) =>
                          ch.module_name === mod.name ||
                          mod.chapter_indices?.includes(idx + 1)
                      )
                      return (
                        <div key={mod.name || mIdx} className="p-3">
                          <p className="px-2 py-1 text-[11px] font-semibold tracking-wider text-[#819294] uppercase">
                            {mod.name}
                          </p>
                          <div className="mt-1 space-y-1">
                            {modChapters.map((ch) => {
                              const agent = agentByChapterId.get(ch.chapter_id)
                              const status = agent?.status || 'pending'
                              const isSelected = selectedChapterId === ch.chapter_id
                              return (
                                <button
                                  key={ch.chapter_id}
                                  type="button"
                                  onClick={() => setSelectedChapterId(ch.chapter_id)}
                                  className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs transition-all ${
                                    isSelected
                                      ? 'bg-[#e7f3f3] font-medium text-[#116a72]'
                                      : 'text-[#334648] hover:bg-[#f6f9f9]'
                                  }`}
                                >
                                  <span className="flex items-center gap-2 truncate">
                                    <ChapterStatusDot status={status} />
                                    <span className="truncate">{ch.title}</span>
                                  </span>
                                  <ChevronRight
                                    size={14}
                                    className={`shrink-0 transition-transform ${
                                      isSelected ? 'text-[#147d86]' : 'text-[#a4b4b5]'
                                    }`}
                                  />
                                </button>
                              )
                            })}
                          </div>
                        </div>
                      )
                    })
                  : (plannedChapters.length > 0 ? plannedChapters : agents).map((item, idx) => {
                      const cid = String(('chapter_id' in item ? item.chapter_id : item.agent_id) || `item-${idx}`)
                      const title = ('title' in item ? item.title : item.label) || `第 ${idx + 1} 章`
                      const agent = agentByChapterId.get(cid)
                      const status = agent?.status || ('status' in item ? item.status : 'pending')
                      const isSelected = selectedChapterId === cid
                      return (
                        <button
                          key={cid}
                          type="button"
                          onClick={() => setSelectedChapterId(cid)}
                          className={`flex w-full items-center justify-between px-4 py-3 text-left text-xs transition-all ${
                            isSelected
                              ? 'bg-[#e7f3f3] font-medium text-[#116a72]'
                              : 'text-[#334648] hover:bg-[#fafcfc]'
                          }`}
                        >
                          <span className="flex items-center gap-2 truncate">
                            <ChapterStatusDot status={status} />
                            <span className="truncate">{title}</span>
                          </span>
                          <ChevronRight
                            size={14}
                            className={`shrink-0 ${
                              isSelected ? 'text-[#147d86]' : 'text-[#a4b4b5]'
                            }`}
                          />
                        </button>
                      )
                    })}
              </div>
            )}
          </div>

          {/* Quick source material overview */}
          <div className="rounded-xl border border-[#e2e8e8] bg-white p-4">
            <h3 className="flex items-center gap-2 text-xs font-semibold text-[#172b2d]">
              <FileText size={14} className="text-[#147d86]" /> 输入资料概况
            </h3>
            <p className="mt-1 text-[11px] text-[#788a8c]">
              共纳入 {run.resources.length} 份课堂资料，作为各章节的内容源
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {run.resources.slice(0, 6).map((res) => (
                <span
                  key={res.revision_id}
                  className="rounded-md bg-[#f2f6f6] px-2 py-1 text-[10px] text-[#4d6163]"
                >
                  {res.title}
                </span>
              ))}
              {run.resources.length > 6 && (
                <span className="rounded-md bg-[#f2f6f6] px-2 py-1 text-[10px] text-[#788a8c]">
                  +{run.resources.length - 6} 份
                </span>
              )}
            </div>
          </div>
        </aside>

        {/* Right Column: Stage Showcase (Chapter Detail OR Book Blueprint) */}
        <main className="min-w-0">
          {selectedChapterId && (selectedAgent || selectedPlannedChapter) ? (
            /* Chapter Focus Card */
            <div className="rounded-2xl border border-[#e2e8e8] bg-white p-6 shadow-xs sm:p-8">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#f0f3f3] pb-5">
                <div>
                  <span className="text-[11px] font-medium tracking-wide text-[#147d86] uppercase">
                    {selectedAgent?.module_name || selectedPlannedChapter?.module_name || '章节审阅'}
                  </span>
                  <h2 className="mt-1 text-xl font-bold text-[#172b2d]">
                    {selectedAgent?.label || selectedPlannedChapter?.title}
                  </h2>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-medium ${statusBadgeClass(
                    selectedAgent?.status || 'pending'
                  )}`}
                >
                  {statusLabel(selectedAgent?.status || 'pending')}
                </span>
              </div>

              {/* Narrative purpose */}
              {(selectedAgent?.narrative_purpose || selectedPlannedChapter?.narrative_purpose) && (
                <div className="mt-5">
                  <h4 className="text-xs font-semibold text-[#485d5f]">本章教学目标</h4>
                  <p className="mt-1.5 text-sm leading-relaxed text-[#233537]">
                    {selectedAgent?.narrative_purpose || selectedPlannedChapter?.narrative_purpose}
                  </p>
                </div>
              )}

              {/* Section Outlines */}
              {selectedAgent?.section_headings && selectedAgent.section_headings.length > 0 ? (
                <div className="mt-6">
                  <h4 className="text-xs font-semibold text-[#485d5f]">已完成小节</h4>
                  <div className="mt-3 space-y-2">
                    {selectedAgent.section_headings.map((heading, idx) => (
                      <div
                        key={idx}
                        className="flex items-center gap-2.5 rounded-lg border border-[#edf2f2] bg-[#f9fbfb] px-3.5 py-2.5 text-xs text-[#25393b]"
                      >
                        <span className="font-mono text-[11px] font-semibold text-[#147d86]">
                          § {idx + 1}
                        </span>
                        <span>{heading}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : selectedPlannedChapter?.section_plan && selectedPlannedChapter.section_plan.length > 0 ? (
                <div className="mt-6">
                  <h4 className="text-xs font-semibold text-[#485d5f]">规划小节</h4>
                  <div className="mt-3 space-y-2">
                    {selectedPlannedChapter.section_plan.map((sec, idx) => (
                      <div
                        key={idx}
                        className="flex items-center gap-2.5 rounded-lg border border-[#edf2f2] bg-[#fafcfc] px-3.5 py-2.5 text-xs text-[#526668]"
                      >
                        <span className="font-mono text-[11px] font-semibold text-[#90a2a4]">
                          § {idx + 1}
                        </span>
                        <span>{sec}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {/* Core coverage concepts */}
              {(selectedAgent?.key_points?.length || selectedPlannedChapter?.must_cover?.length) ? (
                <div className="mt-6">
                  <h4 className="text-xs font-semibold text-[#485d5f]">核心覆盖要点</h4>
                  <div className="mt-2.5 flex flex-wrap gap-2">
                    {(selectedAgent?.key_points?.length ? selectedAgent.key_points : selectedPlannedChapter?.must_cover || []).map(
                      (point, i) => (
                        <span
                          key={i}
                          className="rounded-md border border-[#d6e7e8] bg-[#eef6f6] px-2.5 py-1 text-xs text-[#17545b]"
                        >
                          {point}
                        </span>
                      )
                    )}
                  </div>
                </div>
              ) : null}

              {/* Error prompt if failed */}
              {selectedAgent?.status === 'failed' && (
                <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-xs text-red-800">
                  <p className="font-semibold">此章节撰写中断</p>
                  <p className="mt-1 text-[11px] text-red-700/80">
                    {selectedAgent.error || '模型生成超时或返回异常，可通过顶部的“恢复并继续”重新尝试本章。'}
                  </p>
                </div>
              )}
            </div>
          ) : (
            /* The Whole Book Blueprint */
            <div className="space-y-6">
              <div className="rounded-2xl border border-[#e2e8e8] bg-white p-6 shadow-xs sm:p-8">
                <div className="flex items-center gap-2 text-xs font-semibold tracking-wide text-[#147d86]">
                  <Compass size={16} /> 全书知识架构
                </div>
                <h3 className="mt-2 text-lg font-bold text-[#172b2d]">研读脉络与学习路径</h3>
                <p className="mt-1 text-xs text-[#6e8082]">
                  由 AI 主编基于全部课程资料归纳提炼的知识主线与学习逻辑
                </p>

                {learningPath.length > 0 ? (
                  <div className="mt-6 space-y-3">
                    {learningPath.map((step, idx) => (
                      <div key={idx} className="flex items-start gap-3">
                        <span className="grid size-6 shrink-0 place-items-center rounded-full bg-[#e6f3f3] text-xs font-bold text-[#147d86]">
                          {idx + 1}
                        </span>
                        <p className="mt-0.5 text-sm leading-relaxed text-[#25393b]">{step}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-4 text-xs text-[#718183]">暂无学习路径明细</p>
                )}
              </div>

              {globalEmphasis.length > 0 && (
                <div className="rounded-2xl border border-[#b9dedf] bg-[#f2f8f8] p-6 shadow-xs sm:p-8">
                  <div className="flex items-center gap-2 text-xs font-semibold text-[#147d86]">
                    <Sparkles size={16} /> 全书贯穿原则
                  </div>
                  <h3 className="mt-2 text-lg font-bold text-[#172b2d]">核心学科方法论</h3>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    {globalEmphasis.map((quote, idx) => (
                      <div
                        key={idx}
                        className="rounded-xl border border-white/80 bg-white/70 p-4 text-xs leading-relaxed text-[#264548] shadow-2xs"
                      >
                        “{quote}”
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Finished banner if artifact ready */}
              {run.artifact_available && (
                <div className="flex flex-col justify-between gap-4 rounded-2xl bg-[#173c40] p-6 text-white sm:flex-row sm:items-center sm:p-7">
                  <div>
                    <h3 className="text-lg font-bold">教辅书已完稿，随时阅读</h3>
                    <p className="mt-1 text-xs text-[#b8d8d7]">
                      包含完整的知识章节、导读前言、课堂例题与排版，支持离线 HTML 和 Markdown 导出。
                    </p>
                  </div>
                  <Button
                    render={<Link to={`/artifacts/${run.run_id}`} />}
                    className="shrink-0 bg-white text-[#173c40] hover:bg-[#e6f3f3]"
                  >
                    <BookOpen size={14} className="mr-1.5" /> 立即开始阅读
                  </Button>
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}

function ChapterStatusDot({ status }: { status: string }) {
  if (status === 'succeeded') {
    return <CheckCircle2 size={14} className="shrink-0 text-[#27774a]" />
  }
  if (status === 'running') {
    return <span className="size-2 shrink-0 animate-ping rounded-full bg-[#147d86]" />
  }
  if (status === 'failed') {
    return <AlertTriangle size={14} className="shrink-0 text-amber-600" />
  }
  return <span className="size-2 shrink-0 rounded-full bg-[#cbd6d6]" />
}
