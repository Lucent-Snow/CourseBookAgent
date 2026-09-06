import { useState } from 'react'
import { Menu } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { ChapterView } from './ChapterView'
import type { CourseBook } from '@/types'

function FrontMatter({ book }: { book: CourseBook }) {
  return (
    <div className="min-w-0">
      <h2 className="text-2xl font-bold leading-snug">{book.title}</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        {book.course.name}
        {book.course.teacher ? ` · ${book.course.teacher}` : ''}
        {book.course.term ? ` · ${book.course.term}` : ''}
      </p>

      {book.preface && (
        <div className="mt-8">
          <h3 className="mb-3 text-base font-semibold">前言</h3>
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{book.preface}</p>
        </div>
      )}

      {book.how_to_use.length > 0 && (
        <div className="mt-8">
          <h3 className="mb-3 text-base font-semibold">如何使用本书</h3>
          <ul className="my-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed">
            {book.how_to_use.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {book.knowledge_map.length > 0 && (
        <div className="mt-8">
          <h3 className="mb-3 text-base font-semibold">知识地图</h3>
          <ul className="my-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed">
            {book.knowledge_map.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {book.learning_path.length > 0 && (
        <div className="mt-8">
          <h3 className="mb-3 text-base font-semibold">学习路径</h3>
          <ul className="my-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed">
            {book.learning_path.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}
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
        ) : <FrontMatter book={book} />}
      </main>
    </div>
  )
}
