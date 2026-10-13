import { useState } from 'react'
import { AlertTriangle, CheckCircle2, PlayCircle, Sparkles } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { ComponentBlock } from './ComponentBlock'
import { MathText } from '@/components/math/MathText'
import type { LectureDraft } from '@/types'
import { timeRangeStart, type VideoRef } from '@/lib/time-node'
import { VideoNodePlayer } from './VideoNodePlayer'

const ROLE_LABELS: Record<string, string> = {
  core: '核心主干',
  review: '复习整合',
  guest: '前沿专题',
  mixed: '综合方法',
  admin: '课程导论',
}

export function ChapterView({ chapter, video }: { chapter: LectureDraft; video?: VideoRef }) {
  const [jump, setJump] = useState<number | null>(null)
  const role = ROLE_LABELS[chapter.chapter_role] ?? chapter.chapter_role ?? ''

  return (
    <article className="max-w-3xl min-w-0">
      {/* Chapter Masthead */}
      <div className="border-b border-[#e2e8e8] pb-6">
        {(chapter.module_name || role) && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {chapter.module_name && (
              <span className="font-semibold text-[#147d86]">
                {chapter.module_name}
              </span>
            )}
            {chapter.module_name && role && <span className="text-[#b2c0c2]">·</span>}
            {role && <span className="text-[#718284]">{role}</span>}
          </div>
        )}

        <h1 className="mt-2.5 text-2xl font-bold tracking-tight text-[#172b2d] sm:text-3xl">
          {chapter.title}
        </h1>

        {/* Transition from previous chapter (No clumsy '承上' heading!) */}
        {chapter.bridge_from_prev && (
          <div className="mt-4 rounded-xl border-l-2 border-[#147d86] bg-[#f8fbfb] px-4 py-2.5 text-xs leading-relaxed text-[#4d6365] italic">
            <MathText text={chapter.bridge_from_prev} />
          </div>
        )}
      </div>

      {/* Chapter Overview & Goals */}
      {chapter.overview && (
        <div className="mt-6 text-sm leading-relaxed whitespace-pre-wrap text-[#2a3e40]">
          <MathText text={chapter.overview} />
        </div>
      )}

      {chapter.learning_goals.length > 0 && (
        <div className="mt-6 rounded-2xl border border-[#dce8e8] bg-[#f8fbfb] p-5">
          <h4 className="flex items-center gap-1.5 text-xs font-bold text-[#147d86] uppercase tracking-wide">
            <CheckCircle2 size={14} /> 本章目标
          </h4>
          <ul className="mt-3 space-y-2 text-xs leading-relaxed text-[#314648]">
            {chapter.learning_goals.map((goal, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-1 size-1.5 shrink-0 rounded-full bg-[#147d86]" />
                <span>
                  <MathText text={goal} />
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Core Concepts definitions */}
      {chapter.concepts.length > 0 && (
        <div className="mt-8">
          <h3 className="text-sm font-bold tracking-tight text-[#172b2d]">核心概念</h3>
          <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
            {chapter.concepts.map((item, i) => {
              const idx = item.indexOf('：')
              const term = idx >= 0 ? item.slice(0, idx) : item
              const def = idx >= 0 ? item.slice(idx + 1) : ''
              return (
                <div key={i} className="rounded-xl border border-[#e5ecec] bg-white p-3.5 shadow-2xs">
                  <strong className="block text-xs font-bold text-[#147d86]">
                    <MathText text={term} />
                  </strong>
                  {def && (
                    <p className="mt-1 text-xs leading-relaxed text-[#516568]">
                      <MathText text={def} />
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Main Chapter Sections */}
      <div className="mt-10 space-y-10">
        {chapter.sections.map((section, i) => (
          <section key={i} className="border-t border-[#edf1f1] pt-8 first:border-0 first:pt-0">
            <h2 className="flex flex-wrap items-center gap-2.5 text-lg font-bold tracking-tight text-[#172b2d]">
              <span className="font-mono text-[#147d86]">§ {i + 1}</span>
              <span>{section.heading}</span>
              {section.emphasis === 'key' && (
                <Badge variant="secondary" className="bg-[#eef6f6] text-[#147d86] text-[10px]">
                  核心
                </Badge>
              )}
            </h2>

            <div className="mt-3 text-sm leading-relaxed whitespace-pre-wrap text-[#263a3c]">
              <MathText text={section.content} />
            </div>

            {/* Spec Components (Worked examples, procedure, warning box) */}
            {section.components.length > 0 && (
              <div className="mt-5 space-y-4">
                {section.components.map((comp, j) => (
                  <ComponentBlock key={j} component={comp} />
                ))}
              </div>
            )}

            {/* Video Node timestamps */}
            {section.time_links.length > 0 && (
              <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
                <span className="text-[#7c8f91]">原课堂视频切片：</span>
                {section.time_links.map((link, k) => (
                  <span key={k}>
                    {video ? (
                      <button
                        type="button"
                        onClick={() => setJump(timeRangeStart(link))}
                        className="inline-flex items-center gap-1 rounded-md bg-[#eef5f5] px-2 py-0.5 text-[11px] font-medium text-[#147d86] transition-colors hover:bg-[#dceeee]"
                      >
                        <PlayCircle size={12} />
                        {link}
                      </button>
                    ) : (
                      <span className="rounded-md bg-[#f1f4f4] px-2 py-0.5 text-[11px] text-[#6b7d7f]">
                        {link}
                      </span>
                    )}
                  </span>
                ))}
              </div>
            )}
          </section>
        ))}
      </div>

      {/* Common Pitfalls / Mistakes */}
      {chapter.common_mistakes.length > 0 && (
        <div className="mt-10 rounded-2xl border border-amber-200/80 bg-amber-50/50 p-5">
          <h3 className="flex items-center gap-1.5 text-xs font-bold text-amber-900">
            <AlertTriangle size={14} className="text-amber-700" /> 易错辨析与警示
          </h3>
          <ul className="mt-3 space-y-1.5 text-xs leading-relaxed text-amber-950/90">
            {chapter.common_mistakes.map((item, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-1 size-1.5 shrink-0 rounded-full bg-amber-600" />
                <span>
                  <MathText text={item} />
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Chapter Summary */}
      {chapter.summary.length > 0 && (
        <div className="mt-8 rounded-2xl border border-[#e2e8e8] bg-[#fafcfc] p-5">
          <h3 className="flex items-center gap-1.5 text-xs font-bold text-[#147d86]">
            <Sparkles size={14} /> 本章小结
          </h3>
          <ul className="mt-3 space-y-1.5 text-xs leading-relaxed text-[#314648]">
            {chapter.summary.map((item, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-1 size-1.5 shrink-0 rounded-full bg-[#147d86]" />
                <span>
                  <MathText text={item} />
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Forward Look to next chapter (No clumsy '启下' heading!) */}
      {chapter.bridge_to_next && (
        <div className="mt-8 border-t border-[#edf1f1] pt-4 text-xs leading-relaxed text-[#617678] italic">
          <span className="font-semibold not-italic text-[#147d86]">下章前瞻：</span>
          <MathText text={chapter.bridge_to_next} />
        </div>
      )}

      {/* Embedded Video Node Player */}
      <VideoNodePlayer
        open={jump !== null}
        chapterTitle={chapter.title}
        video={video}
        startSec={jump ?? 0}
        onClose={() => setJump(null)}
      />
    </article>
  )
}
