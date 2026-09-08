import { useEffect, useState } from 'react'
import { ArrowLeft, Download, RefreshCw } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { BookReader } from '@/components/book/BookReader'
import { Button } from '@/components/ui/button'
import { api } from '@/api/client'
import { productApi } from '@/api/product'
import type { ArtifactDetail } from '@/product-types'

export function ArtifactDetailPage() {
  const { artifactId = '' } = useParams()
  const [detail, setDetail] = useState<ArtifactDetail | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { void productApi.artifact(artifactId).then(setDetail).catch((err) => setError((err as Error).message)) }, [artifactId])
  if (!detail) return <div className="p-10 text-sm text-[#718183]">{error || '正在加载产物…'}</div>
  return <div className="px-8 py-7"><header className="mb-6 flex items-center justify-between"><div><Link to="/artifacts" className="inline-flex items-center gap-2 text-sm text-[#718183]"><ArrowLeft size={15} />返回生成产物</Link><p className="mt-2 font-mono text-[10px] text-[#8a989a]">产物 {detail.artifact.artifact_id} · 运行 {detail.artifact.run_id}</p><p className="mt-2 text-xs text-[#718183]">资料集：{detail.artifact.dataset_name || detail.artifact.dataset_id || '—'} · 快照：{detail.artifact.snapshot_id || '—'}</p></div><div className="flex gap-2"><Button render={<Link to={`/runs/${detail.artifact.run_id}`} />} variant="outline"><RefreshCw size={14} />查看运行</Button><Button render={<a href={api.jobDownloadUrl(detail.artifact.run_id)} />} className="bg-[#147d86] text-white"><Download size={14} />导出 Markdown</Button></div></header><BookReader book={detail.book} /></div>
}
