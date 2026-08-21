import type { ReactNode } from 'react'
import { Badge } from '@/components/ui/badge'
import { ComponentBlock } from './ComponentBlock'
import { sanitizeList } from '@/lib/sanitize'
import type { LectureDraft } from '@/types'

const ROLE_LABELS: Record<string, string> = {
  core: '核心方法',
  review: '复习整合',
  guest: '专题/嘉宾',
  mixed: '综合',
  admin: '课程说明',
}

function SectionHeading({ children }: { children: ReactNode }) {
  return <h3 className="mt-8 mb-3 text-base font-semibold">{children}</h3>
}

function List({ items, className = '' }: { items: string[]; className?: string }) {
  if (!items.length) return null
  return (
    <ul className={`my-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed ${className}`}>
      {items.map((item, i) => (
        <li key={i}>{item}</li>
      ))}
    </ul>
  )
}

export function ChapterView({ chapter }: { chapter: LectureDraft }) {
  const role = ROLE_LABELS[chapter.chapter_role] ?? chapter.chapter_role ?? ''

  return (
    <article className="min-w-0">
      <h2 className="text-2xl font-bold leading-snug">{chapter.title}</h2>
      {(chapter.module_name || role) && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {chapter.module_name && <Badge variant="secondary">模块：{chapter.module_name}</Badge>}
          {role && <Badge variant="outline">角色：{role}</Badge>}
        </div>
      )}

      {chapter.bridge_from_prev && (
        <>
          <SectionHeading>承上</SectionHeading>
          <p className="text-sm leading-relaxed text-muted-foreground">{chapter.bridge_from_prev}</p>
        </>
      )}

      {chapter.learning_goals.length > 0 && (
        <>
          <SectionHeading>学习目标</SectionHeading>
          <List items={chapter.learning_goals} />
        </>
      )}

      <SectionHeading>本章导读</SectionHeading>
      <p className="whitespace-pre-wrap text-sm leading-relaxed">{chapter.overview}</p>

      {chapter.key_points.length > 0 && (
        <>
          <SectionHeading>本章重点</SectionHeading>
          <List items={chapter.key_points} />
        </>
      )}

      {chapter.concepts.length > 0 && (
        <>
          <SectionHeading>核心概念</SectionHeading>
          <List items={chapter.concepts} />
        </>
      )}

      {chapter.prerequisite_concepts.length > 0 && (
        <>
          <SectionHeading>先修概念</SectionHeading>
          <List items={chapter.prerequisite_concepts} />
        </>
      )}

      {chapter.sections.map((section, i) => (
        <section key={i} className="mt-8">
          <h3 className="flex flex-wrap items-center gap-2 text-base font-semibold">
            {chapter.sections.length > 1 && <span className="text-muted-foreground">{i + 1}.</span>}
            <span>{section.heading}</span>
            {section.emphasis === 'key' && <Badge variant="secondary">重点</Badge>}
            {section.emphasis === 'review' && <Badge variant="outline">回顾</Badge>}
          </h3>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{section.content}</p>
          {section.components.map((comp, j) => (
            <ComponentBlock key={j} component={comp} />
          ))}
          {section.time_links.length > 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              字幕时间段：{section.time_links.join(' · ')}
            </p>
          )}
        </section>
      ))}

      {chapter.examples.length > 0 && (
        <>
          <SectionHeading>课堂例子与补充</SectionHeading>
          <List items={sanitizeList(chapter.examples)} />
        </>
      )}

      {chapter.common_mistakes.length > 0 && (
        <>
          <SectionHeading>易错点</SectionHeading>
          <List items={chapter.common_mistakes} />
        </>
      )}

      <SectionHeading>本章小结</SectionHeading>
      <List items={chapter.summary} />

      {chapter.bridge_to_next && (
        <>
          <SectionHeading>启下</SectionHeading>
          <p className="text-sm leading-relaxed text-muted-foreground">{chapter.bridge_to_next}</p>
        </>
      )}

      {chapter.source_ranges.length > 0 && (
        <>
          <SectionHeading>来源</SectionHeading>
          <List items={chapter.source_ranges} className="text-xs text-muted-foreground" />
        </>
      )}

      {chapter.warnings.length > 0 && (
        <>
          <SectionHeading>整理说明</SectionHeading>
          <List items={chapter.warnings} className="text-xs text-muted-foreground" />
        </>
      )}
    </article>
  )
}
