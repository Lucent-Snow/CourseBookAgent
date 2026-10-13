export type VideoRef = { file?: string; link?: string }
export type VideoIndex = Record<string, VideoRef>

/** Seconds at the start of a subtitle time range like "01:09:01-01:12:28". */
export function timeRangeStart(label: string): number {
  const match = label.match(/(\d{1,2}:)?\d{1,2}:\d{2}/)
  if (!match) return 0
  const parts = match[0].split(':').map(Number)
  return parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : parts[0] * 60 + parts[1]
}

export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  const mm = String(minutes).padStart(2, '0')
  const ss = String(secs).padStart(2, '0')
  return hours ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`
}

/** Append the zhiyun replay time parameter (kept inside the hash route). */
export function withStartParam(link: string, seconds: number): string {
  if (!link) return ''
  if (link.includes('{ts}')) return link.replace('{ts}', String(seconds))
  return `${link}${link.includes('?') ? '&' : '?'}ts=${seconds}`
}

export function videoIndexFrom(renderConfig: Record<string, unknown> | undefined): VideoIndex {
  const raw = renderConfig?.video_index
  return raw && typeof raw === 'object' ? (raw as VideoIndex) : {}
}
