import { useEffect, useState } from 'react'
import { ArrowLeft, BookOpen, Download, History } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { BookReader } from '@/components/book/BookReader'
import { Button } from '@/components/ui/button'
import { productApi } from '@/api/product'
import type { ArtifactDetail } from '@/product-types'

export function ArtifactDetailPage() {
  const { artifactId = '' } = useParams()
  const [detail, setDetail] = useState<ArtifactDetail | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    void productApi
      .artifact(artifactId)
      .then(setDetail)
      .catch((err) => setError((err as Error).message))
  }, [artifactId])

  if (!detail) {
    return <div className="p-12 text-center text-sm text-[#718183]">{error || '正在翻开书卷…'}</div>
  }

  const { artifact, book } = detail

  return (
    <div className="mx-auto max-w-[1280px] px-4 py-6 md:px-8 md:py-8">
      {/* Return Link */}
      <Link
        to="/artifacts"
        className="inline-flex items-center gap-1.5 text-xs font-medium text-[#718183] transition-colors hover:text-[#147d86]"
      >
        <ArrowLeft size={14} /> 返回书架
      </Link>

      {/* Editorial Book Masthead */}
      <header className="mt-4 flex flex-col justify-between gap-5 border-b border-[#e2e8e8] pb-6 sm:flex-row sm:items-end">
        <div>
          <div className="flex items-center gap-2 text-xs font-medium text-[#147d86]">
            <BookOpen size={14} />
            <span>课程教辅书</span>
            <span className="text-[#a4b2b4]">·</span>
            <span>{artifact.chapter_count} 个章节</span>
          </div>

          <h1 className="mt-2 text-2xl font-bold tracking-tight text-[#172b2d] sm:text-3xl">
            {artifact.title || book.title}
          </h1>

          <p className="mt-1.5 text-xs text-[#687a7c]">
            课程：{artifact.dataset_name || '自选资料'}
          </p>
        </div>

        {/* Export & Inspection Actions */}
        <div className="flex shrink-0 flex-wrap items-center gap-2.5">
          <Button
            render={<Link to={`/runs/${artifact.run_id}`} />}
            variant="outline"
            size="sm"
            className="text-xs"
          >
            <History size={13} className="mr-1" /> 编撰详情
          </Button>

          <Button
            render={<a href={`/api/runs/${artifact.run_id}/download.html`} download />}
            variant="outline"
            size="sm"
            className="border-[#147d86]/30 text-xs text-[#147d86] hover:bg-[#eef6f6]"
          >
            <Download size={13} className="mr-1" /> 纸书版 HTML
          </Button>

          <Button
            render={<a href={`/api/runs/${artifact.run_id}/download.md`} download />}
            size="sm"
            className="bg-[#147d86] text-xs text-white hover:bg-[#116a72]"
          >
            <Download size={13} className="mr-1" /> Markdown
          </Button>
        </div>
      </header>

      {/* The Reader Canvas */}
      <div className="mt-8">
        <BookReader book={book} />
      </div>
    </div>
  )
}
