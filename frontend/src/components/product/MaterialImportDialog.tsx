import { useEffect, useMemo, useState } from 'react'
import { BookOpen, Check, FileText, GraduationCap, IdCard, Loader2, Presentation, RefreshCw, Search } from 'lucide-react'
import { productApi } from '@/api/product'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { Provider, ProviderInspection, ZhiyunLecture } from '@/product-types'

type SourceMode = 'mine' | 'id'

interface CourseSummary {
  course_id: string
  name: string
  teacher: string | null
  term: string | null
}

const PROVIDERS: Array<{ key: Provider; name: string; icon: typeof BookOpen }> = [
  { key: 'zhiyun', name: '智云课堂', icon: BookOpen },
  { key: 'xue_zai_zju', name: '学在浙大', icon: GraduationCap },
]

export function MaterialImportDialog({ datasetId, onClose, onImported }: { datasetId: string; onClose: () => void; onImported: () => void }) {
  const [provider, setProvider] = useState<Provider>('zhiyun')
  const [mode, setMode] = useState<SourceMode>('mine')
  const [courses, setCourses] = useState<CourseSummary[]>([])
  const [query, setQuery] = useState('')
  const [courseId, setCourseId] = useState('')
  const [inspection, setInspection] = useState<ProviderInspection | null>(null)
  const [lectureSelection, setLectureSelection] = useState<Set<string>>(new Set())
  const [uploadSelection, setUploadSelection] = useState<Set<number>>(new Set())
  const [types, setTypes] = useState<Set<string>>(new Set(['transcript']))
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState('')

  useEffect(() => {
    setCourses([])
    setInspection(null)
    setLectureSelection(new Set())
    setUploadSelection(new Set())
    setTypes(new Set(provider === 'xue_zai_zju' ? ['xuezai_upload'] : ['transcript']))
    setError('')
    setResult('')
    setLoading(true)
    const loader = provider === 'xue_zai_zju' ? productApi.xuezaiCourses() : productApi.zhiyunCourses()
    loader.then((items) => setCourses(items as CourseSummary[])).catch((err) => setError((err as Error).message)).finally(() => setLoading(false))
  }, [provider])

  const filtered = useMemo(() => courses.filter((course) => `${course.name} ${course.teacher ?? ''} ${course.course_id}`.toLowerCase().includes(query.toLowerCase())), [courses, query])

  async function inspect(id: string) {
    if (!id.trim()) return
    setLoading(true); setError('')
    try {
      const value = provider === 'xue_zai_zju' ? await productApi.inspectXuezaiCourse(Number(id)) : await productApi.inspectZhiyunCourse(id.trim())
      setInspection(value)
      setCourseId(value.course.course_id)
      setLectureSelection(new Set(value.lectures.map((lecture: ZhiyunLecture) => lecture.lecture_id)))
      setUploadSelection(new Set(value.uploads.map((upload) => upload.upload_id)))
    } catch (err) { setError((err as Error).message) } finally { setLoading(false) }
  }

  function toggleLecture(id: string) { setLectureSelection((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next }) }
  function toggleUpload(id: number) { setUploadSelection((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next }) }
  function toggleType(type: string) { setTypes((current) => { const next = new Set(current); if (next.has(type)) next.delete(type); else next.add(type); return next }) }

  async function submit() {
    if (!inspection) return
    setImporting(true); setError(''); setResult('')
    try {
      let response: { data: ReturnType<typeof Object>[]; warnings: string[] }
      if (provider === 'xue_zai_zju') {
        response = await productApi.importXuezai(datasetId, Number(inspection.course.course_id), [...uploadSelection])
      } else {
        response = await productApi.importZhiyun(datasetId, inspection.course.course_id, [...lectureSelection], [...types] as Array<'transcript' | 'courseware'>)
      }
      if (response.data.length) onImported()
      if (response.warnings.length) {
        setResult(`已导入 ${response.data.length} 项资料。${response.warnings.join('；')}`)
      } else {
        onClose()
      }
    } catch (err) { setError((err as Error).message) } finally { setImporting(false) }
  }

  const importable = provider === 'xue_zai_zju' ? uploadSelection.size > 0 : lectureSelection.size > 0 && types.size > 0

  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-3" onClick={onClose}>
    <div role="dialog" aria-modal="true" aria-label="导入资料" className="flex max-h-[92dvh] w-full max-w-[820px] flex-col overflow-hidden rounded-lg bg-white shadow-2xl" onClick={(event) => event.stopPropagation()}>
      <header className="flex items-start justify-between border-b border-[#e3e9e9] px-6 py-5"><div><h2 className="text-lg font-semibold">导入资料</h2><p className="mt-1 text-xs text-[#718183]">选择资料提供商、课程以及要保存到资料集的内容。</p></div><Button variant="ghost" onClick={onClose}>关闭</Button></header>
      <div className="border-b border-[#e3e9e9] bg-[#f7f9f9] px-6 py-3"><div className="grid grid-cols-2 gap-1 rounded-md bg-[#e9eeee] p-1">{PROVIDERS.map(({ key, name, icon: Icon }) => <button key={key} onClick={() => setProvider(key)} className={`flex h-9 items-center justify-center gap-1.5 rounded text-xs ${provider === key ? 'bg-white font-medium text-[#147d86] shadow-sm' : 'text-[#718183]'}`}><Icon size={14} />{name}</button>)}</div></div>
      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden md:grid-cols-[280px_1fr]">
        <aside className="border-b border-[#e3e9e9] bg-[#f7f9f9] p-4 md:border-b-0 md:border-r">
          <div className="grid grid-cols-2 rounded-md bg-[#e9eeee] p-1">{([['mine','我的课程',BookOpen],['id','课程 ID',IdCard]] as const).map(([key,label,Icon]) => <button key={key} onClick={() => { setMode(key); setInspection(null); setError('') }} className={`flex h-9 items-center justify-center gap-1.5 rounded text-xs ${mode === key ? 'bg-white font-medium text-[#147d86] shadow-sm' : 'text-[#718183]'}`}><Icon size={14} />{label}</button>)}</div>
          {mode === 'mine' ? <>{provider === 'zhiyun' && <p className="mt-3 text-[10px] leading-4 text-[#879596]">课程来自智云课堂账号“我的课程”。</p>}{provider === 'xue_zai_zju' && <p className="mt-3 text-[10px] leading-4 text-[#879596]">课程来自学在浙大账号“我的课程”。</p>}<label className="mt-4 flex h-9 items-center gap-2 rounded-md border border-[#dbe3e3] bg-white px-3"><Search size={14} className="text-[#879596]" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索课程" className="min-w-0 flex-1 bg-transparent text-xs outline-none" /></label><div className="mt-3 max-h-[44dvh] space-y-1 overflow-auto">{loading ? <p className="p-3 text-xs text-[#718183]">正在读取课程…</p> : filtered.map((course) => <button key={course.course_id} onClick={() => void inspect(String(course.course_id))} className={`w-full rounded-md p-3 text-left ${inspection?.course.course_id === course.course_id ? 'bg-[#e2f1f1]' : 'hover:bg-white'}`}><strong className="block truncate text-xs font-medium">{course.name}</strong><span className="mt-1 block truncate text-[10px] text-[#7f8d8f]">{course.teacher || '教师未知'} · {course.term || course.course_id}</span></button>)}</div></> : <div className="mt-4"><label className="text-xs text-[#657678]">输入课程 ID</label><Input autoFocus value={courseId} onChange={(event) => setCourseId(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void inspect(courseId) }} placeholder={provider === 'zhiyun' ? '例如：82493' : '例如：12345'} className="mt-2 bg-white" /><Button onClick={() => void inspect(courseId)} disabled={!courseId.trim() || loading} className="mt-3 w-full bg-[#147d86] text-white"><RefreshCw size={14} />加载课程</Button><p className="mt-3 text-[10px] leading-4 text-[#879596]">适合导入不在“我的课程”列表中、但当前账号有权访问的课程。</p></div>}
        </aside>
        <main className="min-h-0 overflow-auto p-5 md:p-6">{error && <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-700">{error}</div>}{result && <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">{result}</div>}{loading && inspection ? <div className="grid h-48 place-items-center text-sm text-[#718183]"><Loader2 className="animate-spin" /></div> : inspection ? <><div><p className="text-[10px] font-semibold text-[#147d86]">已选择课程</p><h3 className="mt-1 text-lg font-semibold">{inspection.course.name}</h3><p className="mt-1 text-xs text-[#718183]">{inspection.course.teacher || '教师未知'} · 课程 ID {inspection.course.course_id}</p></div>{inspection.content_types.length > 0 && <section className="mt-6"><div className="flex items-center justify-between"><h4 className="text-xs font-semibold">导入内容</h4><span className="text-[10px] text-[#819092]">{provider === 'xue_zai_zju' ? '课件将直接下载为原始文件' : '可多选'}</span></div><div className="mt-3 grid gap-3 sm:grid-cols-2">{inspection.content_types.map((option) => { const selected = types.has(option.key); const Icon = option.key === 'courseware' || option.key === 'xuezai_upload' ? Presentation : FileText; return <button key={option.key} onClick={() => provider === 'xue_zai_zju' ? setTypes(new Set([option.key])) : toggleType(option.key)} className={`flex items-start gap-3 rounded-md border p-3 text-left ${selected ? 'border-[#147d86] bg-[#eef7f7]' : 'border-[#dfe6e6]'}`}><Icon size={17} className="mt-0.5 text-[#147d86]" /><span><strong className="block text-xs">{option.name}</strong><small className="mt-1 block leading-4 text-[#718183]">{option.description}</small></span>{selected && <Check size={14} className="ml-auto text-[#147d86]" />}</button> })}</div></section>}{provider === 'xue_zai_zju' ? <section className="mt-6"><div className="flex items-center justify-between"><h4 className="text-xs font-semibold">选择课件</h4><button onClick={() => setUploadSelection(uploadSelection.size === inspection.uploads.length ? new Set() : new Set(inspection.uploads.map((item) => item.upload_id)))} className="text-[11px] text-[#147d86]">{uploadSelection.size === inspection.uploads.length ? '取消全选' : '全选'}</button></div><div className="mt-3 max-h-60 divide-y divide-[#edf0f0] overflow-auto rounded-md border border-[#dfe6e6]">{inspection.uploads.length ? inspection.uploads.map((upload) => <label key={upload.upload_id} className="flex cursor-pointer items-center gap-3 px-3 py-3 hover:bg-[#fafcfc]"><input type="checkbox" checked={uploadSelection.has(upload.upload_id)} onChange={() => toggleUpload(upload.upload_id)} /><div className="min-w-0 flex-1"><p className="truncate text-xs">{upload.filename}</p><p className="mt-1 text-[10px] text-[#879596]">{upload.module || '课件'} · {(upload.size / 1024).toFixed(1)} KB</p></div></label>) : <p className="px-3 py-6 text-center text-xs text-[#718183]">这门课程暂无可下载课件</p>}</div></section> : <section className="mt-6"><div className="flex items-center justify-between"><h4 className="text-xs font-semibold">选择讲次</h4><button onClick={() => setLectureSelection(lectureSelection.size === inspection.lectures.length ? new Set() : new Set(inspection.lectures.map((lecture: ZhiyunLecture) => lecture.lecture_id)))} className="text-[11px] text-[#147d86]">{lectureSelection.size === inspection.lectures.length ? '取消全选' : '全选'}</button></div><div className="mt-3 max-h-60 divide-y divide-[#edf0f0] overflow-auto rounded-md border border-[#dfe6e6]">{inspection.lectures.map((lecture: ZhiyunLecture) => <label key={lecture.lecture_id} className="flex cursor-pointer items-center gap-3 px-3 py-3 hover:bg-[#fafcfc]"><input type="checkbox" checked={lectureSelection.has(lecture.lecture_id)} onChange={() => toggleLecture(lecture.lecture_id)} /><span className="grid size-7 place-items-center rounded bg-[#eef4f4] text-[10px] font-medium text-[#147d86]">{lecture.index}</span><span className="min-w-0 flex-1 truncate text-xs">{lecture.title}</span><span className="text-[10px] text-[#879596]">{lecture.duration ? `${Math.round(lecture.duration / 60)} 分钟` : ''}</span></label>)}</div></section>}</> : <div className="grid min-h-80 place-items-center text-center"><div><BookOpen size={28} className="mx-auto text-[#9aa7a8]" /><p className="mt-3 text-sm font-medium">选择一门课程</p><p className="mt-1 text-xs text-[#819092]">随后可以选择讲次、字幕和课件页</p></div></div>}</main>
      </div>
      <footer className="flex items-center justify-between border-t border-[#e3e9e9] px-6 py-4"><p className="text-[11px] text-[#718183]">{inspection ? (provider === 'xue_zai_zju' ? `将导入 ${uploadSelection.size} 个课件文件` : `将导入 ${lectureSelection.size} 个讲次 · ${types.size} 类内容`) : '尚未选择课程'}</p><div className="flex gap-2"><Button variant="outline" onClick={onClose}>取消</Button><Button onClick={() => void submit()} disabled={!importable || importing} className="bg-[#147d86] text-white">{importing ? <><Loader2 size={14} className="animate-spin" />正在导入</> : '导入到资料集'}</Button></div></footer>
    </div>
  </div>
}