import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { formatClock, withStartParam, type VideoRef } from '@/lib/time-node'

export function VideoNodePlayer({ open, chapterTitle, video, startSec, onClose }: {
  open: boolean
  chapterTitle: string
  video?: VideoRef
  startSec: number
  onClose: () => void
}) {
  const elementRef = useRef<HTMLVideoElement | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!open) return
    setFailed(false)
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  useEffect(() => {
    const element = elementRef.current
    if (!open || !element || !video?.file) return
    const seek = () => {
      try {
        element.currentTime = Number.isFinite(element.duration) && element.duration > 0
          ? Math.min(startSec, element.duration - 0.5)
          : startSec
      } catch { /* seeking is best effort */ }
      void element.play().catch(() => undefined)
    }
    if (element.readyState >= 1) seek()
    else element.addEventListener('loadedmetadata', seek, { once: true })
    return () => element.removeEventListener('loadedmetadata', seek)
  }, [open, video?.file, startSec])

  if (!open) return null
  const replay = video?.link ? withStartParam(video.link, startSec) : ''

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`${chapterTitle} 视频节点`}
      onClick={(event) => { if (event.target === event.currentTarget) onClose() }}
    >
      <div className="w-full max-w-4xl overflow-hidden rounded-xl bg-neutral-950 text-neutral-100 shadow-2xl">
        <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2.5 text-sm">
          <span className="min-w-0 flex-1 truncate">{chapterTitle} · {formatClock(startSec)}</span>
          {replay && (
            <a
              href={replay}
              target="_blank"
              rel="noreferrer"
              className="rounded-md border border-white/20 px-3 py-1 text-xs hover:bg-white/10"
            >
              回放页
            </a>
          )}
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center gap-1 rounded-md border border-white/20 px-3 py-1 text-xs hover:bg-white/10"
          >
            <X className="size-3.5" /> 关闭
          </button>
        </div>
        {video?.file ? (
          <video
            ref={elementRef}
            key={`${video.file}-${startSec}`}
            src={video.file}
            controls
            playsInline
            preload="metadata"
            className="block max-h-[75vh] w-full bg-black"
            onError={() => setFailed(true)}
          />
        ) : (
          <p className="px-5 py-9 text-center text-sm leading-7 text-neutral-300">
            本章没有可直连的视频文件，可用右上角“回放页”打开课堂回放。
          </p>
        )}
        {failed && (
          <p className="border-t border-white/10 px-4 py-3 text-xs text-amber-300">
            视频直链加载失败（可能需要在校园网内访问）。可点“回放页”兜底。
          </p>
        )}
      </div>
    </div>
  )
}
