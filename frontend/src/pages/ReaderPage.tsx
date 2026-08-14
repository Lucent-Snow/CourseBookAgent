import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { BookReader } from '@/components/book/BookReader'
import { Button } from '@/components/ui/button'
import { api } from '@/api/client'
import type { CourseBook } from '@/types'

export function ReaderPage() {
  const { courseId = '82493' } = useParams()
  const [book, setBook] = useState<CourseBook | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    setBook(null)
    setError('')
    void api
      .book(courseId)
      .then(setBook)
      .catch((err) => setError((err as Error).message))
      .finally(() => setLoading(false))
  }, [courseId])

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-1/2 animate-pulse rounded bg-muted" />
        <div className="h-64 animate-pulse rounded-lg bg-muted" />
      </div>
    )
  }

  if (error || !book) {
    return (
      <div className="mx-auto max-w-md py-16 text-center">
        <p className="text-sm text-muted-foreground">{error || '尚无已生成的讲义'}</p>
        <Button render={<Link to="/workspace" />} className="mt-4">
          去生成讲义
        </Button>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← 返回书架
        </Link>
        <Button render={<a href={api.downloadUrl(courseId)} />} variant="secondary" size="sm">
          导出 Markdown
        </Button>
      </div>
      <BookReader book={book} />
    </div>
  )
}
