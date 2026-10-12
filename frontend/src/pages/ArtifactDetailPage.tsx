import { useEffect, useState } from 'react'
import { ArrowLeft, BookOpen, Download, FolderOpen, RefreshCw } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { BookReader } from '@/components/book/BookReader'
import { Button } from '@/components/ui/button'
import { productApi } from '@/api/product'
import type { ArtifactDetail } from '@/product-types'

export function ArtifactDetailPage() {
 const { artifactId = '' } = useParams()
 const [detail, setDetail] = useState<ArtifactDetail | null>(null)
 const [error, setError] = useState('')
 useEffect(() => { void productApi.artifact(artifactId).then(setDetail).catch((err) => setError((err as Error).message)) }, [artifactId])
 if (!detail) return <div className="p-10 text-sm text-[#718183]">{error || '正在加载产物…'}</div>

 const { artifact, book } = detail
 const sectionCount = book.chapters.reduce((total, chapter) => total + (chapter.sections?.length ?? 0), 0)
 return <div className="mx-auto max-w-[1280px] px-4 py-6 md:px-8 md:py-8">
  <Link to="/artifacts" className="inline-flex items-center gap-2 text-sm text-[#718183]"><ArrowLeft size={15} />返回生成产物</Link>
  <header className="mt-5 rounded-2xl border border-[#dfe6e6] bg-white p-5 md:p-7">
   <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-start">
    <div className="min-w-0"><p className="flex items-center gap-2 text-xs font-semibold text-[#147d86]"><BookOpen size={15} />课程教辅 · {artifact.status === 'ready' ? '书稿可读' : '部分书稿'}</p><h1 className="mt-3 text-2xl font-semibold leading-snug md:text-3xl">{artifact.title || book.title}</h1><p className="mt-3 text-sm text-[#52686a]">来自资料集「{artifact.dataset_name || artifact.dataset_id || '未命名资料集'}」；每次生成都对应独立的资料快照和书稿版本。</p></div>
    <div className="flex shrink-0 flex-wrap gap-2"><Button render={<Link to={`/runs/${artifact.run_id}`} />} variant="outline"><RefreshCw size={14} />查看运行过程</Button><Button render={<a href={`/api/runs/${artifact.run_id}/download.md`} />} className="bg-[#147d86] text-white"><Download size={14} />导出 Markdown</Button></div>
   </div>
   <div className="mt-6 grid gap-3 border-t border-[#edf0f0] pt-5 sm:grid-cols-3"><div><strong className="block text-xl">{artifact.chapter_count}</strong><span className="text-xs text-[#718183]">知识章节</span></div><div><strong className="block text-xl">{sectionCount}</strong><span className="text-xs text-[#718183]">章节小节</span></div><div><strong className="block text-sm">{artifact.created_at ? new Date(artifact.created_at).toLocaleDateString('zh-CN') : '—'}</strong><span className="text-xs text-[#718183]">生成日期</span></div></div>
  </header>
  <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-[#f2f7f7] px-4 py-3 text-xs leading-5 text-[#52686a]"><span>这是由课程资料整理的教辅草稿；用于学习或教学前，请核对具体事实和例题。</span><Link to={`/datasets/${artifact.dataset_id}`} className="inline-flex items-center gap-1 font-medium text-[#147d86]"><FolderOpen size={14} />查看资料集</Link></div>
  <div className="mt-8"><BookReader book={book} /></div>
  <p className="mt-10 text-[11px] text-[#819092]">书稿版本 {artifact.artifact_id} · 运行 {artifact.run_id} · 输入快照 {artifact.snapshot_id || '—'}</p>
 </div>
}
