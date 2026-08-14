import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { api } from '@/api/client'
import type { BookSummary, CourseListItem } from '@/types'

const GRADIENTS = [
  'from-[#147D86] to-[#1E9AA6]',
  'from-[#C46943] to-[#D88A5C]',
  'from-[#4F6BD8] to-[#6B82E8]',
  'from-[#7A5BB8] to-[#9B7BD8]',
  'from-[#2E8B57] to-[#4FA97A]',
]

function CourseCard({
  course,
  book,
  gradient,
}: {
  course: CourseListItem
  book?: BookSummary
  gradient: string
}) {
  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
      <div className={`bg-gradient-to-br ${gradient} px-5 py-6`}>
        <h3 className="text-lg font-bold text-white">{course.name}</h3>
        <p className="mt-1 text-xs text-white/70">
          {course.term || '本学期'}
          {book ? ` · ${book.chapters} 讲` : ''}
        </p>
      </div>
      <div className="flex flex-col gap-3 p-5">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">{course.teacher || '教师信息未提供'}</span>
          {book ? (
            <Badge className="border-0 bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200">
              已生成
            </Badge>
          ) : (
            <Badge variant="secondary" className="text-muted-foreground">
              未生成
            </Badge>
          )}
        </div>
        {book ? (
          <Button render={<Link to={`/read/${course.course_id}`} />} variant="secondary">
            继续阅读 →
          </Button>
        ) : (
          <Button render={<Link to={`/workspace?courseId=${course.course_id}`} />} variant="outline">
            生成讲义 →
          </Button>
        )}
      </div>
    </div>
  )
}

export function ShelfPage() {
  const [courses, setCourses] = useState<CourseListItem[]>([])
  const [books, setBooks] = useState<Record<string, BookSummary>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    void (async () => {
      try {
        const [cs, bs] = await Promise.all([api.listCourses(), api.listBooks()])
        setCourses(cs)
        setBooks(Object.fromEntries(bs.map((b) => [b.course_id, b])))
      } catch (err) {
        setError((err as Error).message)
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  return (
    <div>
      <div className="mb-8">
        <h2 className="text-2xl font-bold">课程书架</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          选择一门课程，自动整理成可阅读、可复习、可追溯的教辅书。
        </p>
      </div>

      {error && (
        <div className="rounded-md border-l-4 border-red-500 bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-56 animate-pulse rounded-xl bg-muted" />
          ))}
        </div>
      ) : courses.length === 0 ? (
        <div className="rounded-lg border border-dashed p-16 text-center text-sm text-muted-foreground">
          暂无可用课程，请先在「设置」中登录智云课堂。
        </div>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {courses.map((c, i) => (
            <CourseCard key={c.course_id} course={c} book={books[c.course_id]} gradient={GRADIENTS[i % GRADIENTS.length]} />
          ))}
        </div>
      )}
    </div>
  )
}
