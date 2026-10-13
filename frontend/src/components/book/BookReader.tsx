import { useState } from 'react'
import { BookOpen, Compass, ListOrdered, Menu } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { ChapterView } from './ChapterView'
import { readerBook } from '@/lib/book-presentation'
import { videoIndexFrom } from '@/lib/time-node'
import { MathText } from '@/components/math/MathText'
import type { CourseBook } from '@/types'

function MetaSection({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null
  return (
    <div className="mt-8">
      <h3 className="text-sm font-bold tracking-tight text-[#172b2d]">{title}</h3>
      <div className="mt-3 space-y-2">
        {items.map((item, i) => (
          <div
            key={i}
            className="rounded-xl border border-[#e8eeee] bg-[#fafcfc] p-3 text-xs leading-relaxed text-[#314547]"
          >
            <MathText text={item} />
          </div>
        ))}
      </div>
    </div>
  )
}

function FrontMatter({ book }: { book: CourseBook }) {
  const courseMeta = [book.course?.name, book.course?.teacher, book.course?.term].filter(Boolean).join(' · ')
  return (
    <div className="max-w-3xl min-w-0">
      <div className="border-b border-[#e2e8e8] pb-6">
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#147d86]">
          <BookOpen size={14} /> 课程教辅书 · 卷首
        </span>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-[#172b2d] sm:text-4xl">
          {book.title}
        </h1>
        {courseMeta && (
          <p className="mt-2 text-xs font-medium text-[#718183]">{courseMeta}</p>
        )}
      </div>

      {book.preface && (
        <div className="mt-8 rounded-2xl border border-[#dce8e8] bg-[#f9fbfb] p-6 sm:p-8">
          <h2 className="text-sm font-bold tracking-wide text-[#147d86] uppercase">编者前言</h2>
          <div className="mt-3 text-sm leading-relaxed whitespace-pre-wrap text-[#263a3c]">
            <MathText text={book.preface} />
          </div>
        </div>
      )}

      {book.knowledge_map?.length ? (
        <div className="mt-8">
          <h3 className="flex items-center gap-2 text-sm font-bold text-[#172b2d]">
            <Compass size={15} className="text-[#147d86]" /> 知识结构总览
          </h3>
          <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
            {book.knowledge_map.map((item, i) => (
              <div
                key={i}
                className="rounded-xl border border-[#e2e8e8] bg-white p-3.5 text-xs leading-relaxed text-[#35484a] shadow-2xs"
              >
                <MathText text={item} />
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {book.learning_path?.length ? (
        <div className="mt-8">
          <h3 className="flex items-center gap-2 text-sm font-bold text-[#172b2d]">
            <ListOrdered size={15} className="text-[#147d86]" /> 建议研读路径
          </h3>
          <div className="mt-3 space-y-2">
            {book.learning_path.map((item, i) => (
              <div key={i} className="flex items-start gap-3 rounded-xl border border-[#e8eeee] bg-[#fbfcfc] p-3">
                <span className="grid size-5 shrink-0 place-items-center rounded-full bg-[#e6f3f3] text-[11px] font-bold text-[#147d86]">
                  {i + 1}
                </span>
                <span className="text-xs leading-relaxed text-[#334648]">
                  <MathText text={item} />
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <MetaSection title="核心要点速记" items={book.key_point_index} />
      <MetaSection title="全课术语表" items={book.glossary} />
    </div>
  )
}

export function BookReader({
  book: originalBook,
  onRegenerate,
}: {
  book: CourseBook
  onRegenerate?: (index: number) => void
}) {
  const book = readerBook(originalBook)
  const [active, setActive] = useState(-1)
  const [tocOpen, setTocOpen] = useState(false)
  const chapter = active >= 0 ? book.chapters[active] : null
  const videoIndex = videoIndexFrom(book.render_config)

  const tocItems = [
    { label: '前言 · 知识架构', index: -1 },
    ...book.chapters.map((c, i) => ({ label: c.title, index: i })),
  ]

  const toc = (
    <nav className="space-y-1">
      {tocItems.map((item) => (
        <button
          key={item.index}
          type="button"
          onClick={() => {
            setActive(item.index)
            setTocOpen(false)
          }}
          className={`block w-full rounded-lg px-3 py-2 text-left text-xs transition-colors ${
            active === item.index
              ? 'bg-[#e7f3f3] font-semibold text-[#116a72]'
              : 'text-[#5a6c6e] hover:bg-[#f3f6f6] hover:text-[#172b2d]'
          }`}
        >
          {item.label}
        </button>
      ))}
    </nav>
  )

  return (
    <div className="grid gap-8 lg:grid-cols-[280px_minmax(0,1fr)]">
      {/* Table of Contents Column */}
      <aside className="sticky top-6 hidden h-fit max-h-[calc(100vh-6rem)] overflow-auto rounded-2xl border border-[#e2e8e8] bg-white p-4 shadow-xs lg:block">
        <p className="px-2 pb-3 text-[11px] font-bold tracking-wider text-[#829294] uppercase">
          目录
        </p>
        {toc}
      </aside>

      {/* Mobile Drawer Trigger */}
      <div className="lg:hidden">
        <Sheet open={tocOpen} onOpenChange={setTocOpen}>
          <SheetTrigger render={<Button variant="outline" size="sm" />}>
            <Menu className="mr-2 size-4" />
            查看目录
          </SheetTrigger>
          <SheetContent side="left" className="w-80 overflow-auto">
            <SheetTitle className="text-sm font-bold text-[#172b2d]">全书目录</SheetTitle>
            <div className="mt-4">{toc}</div>
          </SheetContent>
        </Sheet>
      </div>

      {/* Reader Main Stage */}
      <main className="min-w-0">
        {chapter ? (
          <div>
            {onRegenerate && (
              <div className="mb-4 flex justify-end">
                <Button variant="outline" size="sm" onClick={() => onRegenerate(active + 1)}>
                  重新生成本章
                </Button>
              </div>
            )}
            <ChapterView chapter={chapter} video={videoIndex[chapter.title]} />
          </div>
        ) : (
          <FrontMatter book={book} />
        )}
      </main>
    </div>
  )
}
