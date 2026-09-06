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
  const [actionMessage, setActionMessage] = useState('')

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
        <div className="flex items-center gap-2">
          <Button render={<Link to={`/workspace?courseId=${courseId}`} />} variant="outline" size="sm">
            生成工作台
          </Button>
          <Button render={<a href={api.downloadUrl(courseId)} />} variant="secondary" size="sm">
            导出 Markdown
          </Button>
        </div>
      </div>
      {actionMessage && <p className="mb-4 rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">{actionMessage}</p>}
      <BookReader book={book} onRegenerate={(index) => {
        setActionMessage(`正在提交第 ${index} 讲的重新生成任务…`)
        void api.regenerateLecture(courseId, index)
          .then(() => setActionMessage(`第 ${index} 讲已提交，请到生成工作台查看进度。`))
          .catch((err) => setActionMessage(`提交失败：${(err as Error).message}`))
      }} />
    </div>
  )
}
