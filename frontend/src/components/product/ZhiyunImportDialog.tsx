import { useEffect, useMemo, useState } from 'react'
import { BookOpen, Check, FileText, IdCard, Loader2, Presentation, RefreshCw, Search } from 'lucide-react'
import { productApi } from '@/api/product'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { ZhiyunCourse, ZhiyunCourseInspection } from '@/product-types'

type SourceMode = 'mine' | 'id'
type ContentType = 'transcript' | 'courseware'

export function ZhiyunImportDialog({ datasetId, onClose, onImported }: { datasetId: string; onClose: () => void; onImported: () => void }) {
  const [mode, setMode] = useState<SourceMode>('mine')
  const [courses, setCourses] = useState<ZhiyunCourse[]>([])
  const [query, setQuery] = useState('')
  const [courseId, setCourseId] = useState('')
  const [inspection, setInspection] = useState<ZhiyunCourseInspection | null>(null)
  const [lectures, setLectures] = useState<Set<string>>(new Set())
  const [types, setTypes] = useState<Set<ContentType>>(new Set(['transcript']))
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState('')

  useEffect(() => {
    void productApi.zhiyunCourses().then(setCourses).catch((err) => setError((err as Error).message)).finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => courses.filter((course) => `${course.name} ${course.teacher ?? ''} ${course.course_id}`.toLowerCase().includes(query.toLowerCase())), [courses, query])
  async function inspect(id: string) {
    if (!id.trim()) return
    setLoading(true); setError('')
    try {
      const value = await productApi.inspectZhiyunCourse(id.trim())
      setInspection(value)
      setCourseId(value.course.course_id)
      setLectures(new Set(value.lectures.map((lecture) => lecture.lecture_id)))
    } catch (err) { setError((err as Error).message) } finally { setLoading(false) }
  }
  function toggleLecture(id: string) { setLectures((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next }) }
  function toggleType(type: ContentType) { setTypes((current) => { const next = new Set(current); if (next.has(type)) next.delete(type); else next.add(type); return next }) }
  async function submit() {
    if (!inspection || !lectures.size || !types.size) return
    setImporting(true); setError(''); setResult('')
    try {
      const response = await productApi.importZhiyun(datasetId, inspection.course.course_id, [...lectures], [...types])
      if (response.data.length) onImported()
      if (response.warnings.length) {
        setResult(`已导入 ${response.data.length} 项资料。${response.warnings.join('；')}`)
      } else {
        onClose()
      }
    } catch (err) { setError((err as Error).message) } finally { setImporting(false) }
  }

  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-3" onClick={onClose}>
    <div role="dialog" aria-modal="true" aria-label="从智云导入" className="flex max-h-[92dvh] w-full max-w-[820px] flex-col overflow-hidden rounded-lg bg-white shadow-2xl" onClick={(event) => event.stopPropagation()}>
      <header className="flex items-start justify-between border-b border-[#e3e9e9] px-6 py-5"><div><h2 className="text-lg font-semibold">从智云导入</h2><p className="mt-1 text-xs text-[#718183]">选择课程、讲次，以及要保存到资料集的内容。</p></div><Button variant="ghost" onClick={onClose}>关闭</Button></header>
      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden md:grid-cols-[280px_1fr]">
        <aside className="border-b border-[#e3e9e9] bg-[#f7f9f9] p-4 md:border-b-0 md:border-r">
          <div className="grid grid-cols-2 rounded-md bg-[#e9eeee] p-1">{([['mine','我的课程',BookOpen],['id','课程 ID',IdCard]] as const).map(([key,label,Icon]) => <button key={key} onClick={() => { setMode(key); setInspection(null); setError('') }} className={`flex h-9 items-center justify-center gap-1.5 rounded text-xs ${mode === key ? 'bg-white font-medium text-[#147d86] shadow-sm' : 'text-[#718183]'}`}><Icon size={14} />{label}</button>)}</div>
          {mode === 'mine' ? <><label className="mt-4 flex h-9 items-center gap-2 rounded-md border border-[#dbe3e3] bg-white px-3"><Search size={14} className="text-[#879596]" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索我的课程" className="min-w-0 flex-1 bg-transparent text-xs outline-none" /></label><div className="mt-3 max-h-[48dvh] space-y-1 overflow-auto">{loading ? <p className="p-3 text-xs text-[#718183]">正在读取课程…</p> : filtered.map((course) => <button key={course.course_id} onClick={() => void inspect(course.course_id)} className={`w-full rounded-md p-3 text-left ${inspection?.course.course_id === course.course_id ? 'bg-[#e2f1f1]' : 'hover:bg-white'}`}><strong className="block truncate text-xs font-medium">{course.name}</strong><span className="mt-1 block truncate text-[10px] text-[#7f8d8f]">{course.teacher || '教师未知'} · {course.term || course.course_id}</span></button>)}</div></> : <div className="mt-4"><label className="text-xs text-[#657678]">输入课程 ID</label><Input autoFocus value={courseId} onChange={(event) => setCourseId(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void inspect(courseId) }} placeholder="例如：82493" className="mt-2 bg-white" /><Button onClick={() => void inspect(courseId)} disabled={!courseId.trim() || loading} className="mt-3 w-full bg-[#147d86] text-white"><RefreshCw size={14} />加载课程</Button><p className="mt-3 text-[10px] leading-4 text-[#879596]">适合导入不在“我的课程”列表中、但当前账号有权访问的课程。</p></div>}
        </aside>
        <main className="min-h-0 overflow-auto p-5 md:p-6">{error && <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-700">{error}</div>}{result && <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">{result}</div>}{loading && inspection ? <div className="grid h-48 place-items-center text-sm text-[#718183]"><Loader2 className="animate-spin" /></div> : inspection ? <><div><p className="text-[10px] font-semibold text-[#147d86]">已选择课程</p><h3 className="mt-1 text-lg font-semibold">{inspection.course.name}</h3><p className="mt-1 text-xs text-[#718183]">{inspection.course.teacher || '教师未知'} · 课程 ID {inspection.course.course_id}</p></div><section className="mt-6"><div className="flex items-center justify-between"><h4 className="text-xs font-semibold">导入内容</h4><span className="text-[10px] text-[#819092]">可多选</span></div><div className="mt-3 grid gap-3 sm:grid-cols-2"><button onClick={() => toggleType('transcript')} className={`flex items-start gap-3 rounded-md border p-3 text-left ${types.has('transcript') ? 'border-[#147d86] bg-[#eef7f7]' : 'border-[#dfe6e6]'}`}><FileText size={17} className="mt-0.5 text-[#147d86]" /><span><strong className="block text-xs">课堂字幕</strong><small className="mt-1 block leading-4 text-[#718183]">带时间点的课堂字幕文本</small></span>{types.has('transcript') && <Check size={14} className="ml-auto text-[#147d86]" />}</button><button onClick={() => toggleType('courseware')} className={`flex items-start gap-3 rounded-md border p-3 text-left ${types.has('courseware') ? 'border-[#147d86] bg-[#eef7f7]' : 'border-[#dfe6e6]'}`}><Presentation size={17} className="mt-0.5 text-[#147d86]" /><span><strong className="block text-xs">智云课件页</strong><small className="mt-1 block leading-4 text-[#718183]">PPT 页面图片与时间点，非原始 PPTX</small></span>{types.has('courseware') && <Check size={14} className="ml-auto text-[#147d86]" />}</button></div></section><section className="mt-6"><div className="flex items-center justify-between"><h4 className="text-xs font-semibold">选择讲次</h4><button onClick={() => setLectures(lectures.size === inspection.lectures.length ? new Set() : new Set(inspection.lectures.map((item) => item.lecture_id)))} className="text-[11px] text-[#147d86]">{lectures.size === inspection.lectures.length ? '取消全选' : '全选'}</button></div><div className="mt-3 max-h-60 divide-y divide-[#edf0f0] overflow-auto rounded-md border border-[#dfe6e6]">{inspection.lectures.map((lecture) => <label key={lecture.lecture_id} className="flex cursor-pointer items-center gap-3 px-3 py-3 hover:bg-[#fafcfc]"><input type="checkbox" checked={lectures.has(lecture.lecture_id)} onChange={() => toggleLecture(lecture.lecture_id)} /><span className="grid size-7 place-items-center rounded bg-[#eef4f4] text-[10px] font-medium text-[#147d86]">{lecture.index}</span><span className="min-w-0 flex-1 truncate text-xs">{lecture.title}</span><span className="text-[10px] text-[#879596]">{lecture.duration ? `${Math.round(lecture.duration / 60)} 分钟` : ''}</span></label>)}</div></section></> : <div className="grid min-h-80 place-items-center text-center"><div><BookOpen size={28} className="mx-auto text-[#9aa7a8]" /><p className="mt-3 text-sm font-medium">选择一门课程</p><p className="mt-1 text-xs text-[#819092]">随后可以选择讲次、字幕和课件页</p></div></div>}</main>
      </div>
      <footer className="flex items-center justify-between border-t border-[#e3e9e9] px-6 py-4"><p className="text-[11px] text-[#718183]">{inspection ? `将导入 ${lectures.size} 个讲次 · ${types.size} 类内容` : '尚未选择课程'}</p><div className="flex gap-2"><Button variant="outline" onClick={onClose}>取消</Button><Button onClick={() => void submit()} disabled={!inspection || !lectures.size || !types.size || importing} className="bg-[#147d86] text-white">{importing ? <><Loader2 size={14} className="animate-spin" />正在导入</> : '导入到资料集'}</Button></div></footer>
    </div>
  </div>
}
