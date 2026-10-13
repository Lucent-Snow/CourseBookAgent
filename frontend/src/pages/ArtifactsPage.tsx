import { useEffect, useState } from 'react'
import { BookOpen, Boxes, Download } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { DemoEntry, type DemoPreset } from '@/components/DemoEntry'
import { productApi } from '@/api/product'
import type { ArtifactSummary } from '@/product-types'

export function ArtifactsPage() {
  const [items, setItems] = useState<ArtifactSummary[]>([])
  const [preset, setPreset] = useState<DemoPreset | null | undefined>(undefined)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    void productApi
      .artifacts()
      .then(setItems)
      .catch((err) => setError((err as Error).message))
      .finally(() => setLoading(false))

    void fetch('/api/session')
      .then((res) => res.json())
      .then((session) => setPreset(session.preset ?? null))
      .catch(() => setPreset(null))
  }, [])

  return (
    <div className="mx-auto max-w-[1180px] px-4 py-6 md:px-10 md:py-10">
      <header className="flex flex-col justify-between gap-4 border-b border-[#e2e8e8] pb-6 sm:flex-row sm:items-end">
        <div>
          <p className="text-xs font-semibold tracking-wider text-[#147d86] uppercase">Bookshelf</p>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-[#172b2d] sm:text-3xl">书架</h1>
          <p className="mt-2 text-sm text-[#687a7c]">
            汇聚所有已完稿的课程教辅书，支持沉浸式通读、导出 Markdown 与单文件纸书版。
          </p>
        </div>

        {preset !== undefined && preset !== null && (
          <div className="shrink-0">
            <DemoEntry preset={preset} />
          </div>
        )}
      </header>

      {error && (
        <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          {error}
        </div>
      )}

      <div className="mt-8">
        {loading ? (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((x) => (
              <div key={x} className="h-64 animate-pulse rounded-2xl bg-[#e8efef]" />
            ))}
          </div>
        ) : items.length > 0 ? (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <div
                key={item.artifact_id}
                className="group flex flex-col justify-between rounded-2xl border border-[#e2e8e8] bg-white p-6 shadow-xs transition-all hover:border-[#9bcacc] hover:shadow-md"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="grid size-9 place-items-center rounded-xl bg-[#eef5f5] text-[#147d86]">
                      <BookOpen size={18} />
                    </span>
                    <span className="rounded-full bg-[#edf7f1] px-2.5 py-0.5 text-[11px] font-medium text-[#27774a]">
                      {item.chapter_count} 个知识章节
                    </span>
                  </div>

                  <h3 className="mt-4 line-clamp-2 text-lg font-bold tracking-tight text-[#172b2d] group-hover:text-[#147d86] transition-colors">
                    {item.title}
                  </h3>

                  <p className="mt-2 line-clamp-1 text-xs text-[#718183]">
                    课程源：{item.dataset_name || '自选资料'}
                  </p>
                </div>

                <div className="mt-6 border-t border-[#f0f3f3] pt-4">
                  <div className="flex items-center justify-between gap-2">
                    <Button
                      render={<Link to={`/artifacts/${item.artifact_id}`} />}
                      size="sm"
                      className="bg-[#147d86] text-xs text-white hover:bg-[#116a72]"
                    >
                      阅读全书
                    </Button>
                    <a
                      href={`/api/runs/${item.run_id}/download.html`}
                      download
                      className="inline-flex items-center gap-1 text-xs font-medium text-[#65797b] transition-colors hover:text-[#147d86]"
                    >
                      <Download size={13} /> 纸书版
                    </a>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-[#cbd8d8] bg-white py-16 text-center">
            <Boxes className="mx-auto text-[#96a5a6]" size={28} />
            <p className="mt-3 text-sm font-medium text-[#5a6b6d]">书架上暂无成书</p>
            <p className="mt-1 text-xs text-[#8b999a]">
              从<Link to="/datasets" className="mx-1 font-medium text-[#147d86] hover:underline">资料库</Link>导入或上传材料，开启第一本书的编撰。
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
