import { useState } from 'react'
import { Menu } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { ChapterView } from './ChapterView'
import { MathText } from '@/components/math/MathText'
import type { CourseBook } from '@/types'

function MetaList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null
  return (
    <div className="mt-8">
      <h3 className="mb-3 text-base font-semibold">{title}</h3>
      <ul className="my-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed">
        {items.map((item, i) => (
          <li key={i}>
            <MathText text={item} />
          </li>
        ))}
      </ul>
    </div>
  )
}

function FrontMatter({ book }: { book: CourseBook }) {
  const courseMeta = [book.course?.name, book.course?.teacher, book.course?.term].filter(Boolean).join(' · ')
  return (
    <div className="min-w-0">
      <h2 className="text-2xl font-bold leading-snug">{book.title}</h2>
      {courseMeta && (
        <p className="mt-2 text-sm text-muted-foreground">{courseMeta}</p>
      )}

      {book.preface && (
        <div className="mt-8">
          <h3 className="mb-3 text-base font-semibold">前言</h3>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            <MathText text={book.preface} />
          </p>
        </div>
      )}

      <MetaList title="如何使用本书" items={book.how_to_use} />
      <MetaList title="知识地图" items={book.knowledge_map} />
      <MetaList title="学习路径" items={book.learning_path} />
      <MetaList title="要点速记" items={book.key_point_index} />
      <MetaList title="连贯性阅读提示" items={book.continuity_notes} />
      <MetaList title="全课术语表" items={book.glossary} />
      <MetaList title="来源索引" items={book.source_index} />
    </div>
  )
}

export function BookReader({ book, onRegenerate }: { book: CourseBook; onRegenerate?: (index: number) => void }) {
  const [active, setActive] = useState(-1)
  const chapter = active >= 0 ? book.chapters[active] : null

  const tocItems = [
    { label: '前言 · 知识地图', index: -1 },
    ...book.chapters.map((c, i) => ({ label: c.title, index: i })),
  ]

  const toc = (
    <nav className="space-y-1">
      {tocItems.map((item) => (
        <button
          key={item.index}
          type="button"
          onClick={() => setActive(item.index)}
          className={`block w-full rounded-md px-3 py-2 text-left text-sm leading-snug transition-colors ${
            active === item.index
              ? 'bg-accent font-medium text-accent-foreground'
              : 'text-muted-foreground hover:bg-muted hover:text-foreground'
          }`}
        >
          {item.label}
        </button>
      ))}
    </nav>
  )

  return (
    <div className="grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="sticky top-6 hidden h-fit max-h-[calc(100vh-6rem)] overflow-auto rounded-lg border p-3 lg:block">
        <p className="px-3 pb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          目录
        </p>
        {toc}
      </aside>

      <div className="lg:hidden">
        <Sheet>
          <SheetTrigger render={<Button variant="outline" size="sm" />}>
            <Menu className="mr-2 size-4" />
            目录
          </SheetTrigger>
          <SheetContent side="left" className="w-72 overflow-auto">
            <SheetTitle>目录</SheetTitle>
            <div className="mt-4">{toc}</div>
          </SheetContent>
        </Sheet>
      </div>

      <main className="min-w-0">
        {chapter ? (
          <>
            {onRegenerate && (
              <div className="mb-4 flex justify-end">
                <Button variant="outline" size="sm" onClick={() => onRegenerate(active + 1)}>
                  重新生成本讲
                </Button>
              </div>
            )}
            <ChapterView chapter={chapter} />
          </>
        ) : (
          <FrontMatter book={book} />
        )}
      </main>
    </div>
  )
}
