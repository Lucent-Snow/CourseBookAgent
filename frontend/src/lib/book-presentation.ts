import type { CourseBook } from '@/types'
const internalKeys = new Set(['warnings', 'quality_notes', 'continuity_notes', 'source_index', 'source_ranges', 'source_ref', 'source_labels', 'source_revision_ids', 'source_chunk_ids', 'transcript_links', 'context_fingerprint', 'quality_metrics', 'evidence_from_class'])
export function readerText(text: string): string {
  const plain = text.replace(/[（(](?:来源|出自原资料|据口述重写)[^）)]*[）)]|\[(?:来源|据口述重写)[^\]]*\]/g, '').replace(/据口述(?:重写|重建)?|来源与核对状态/g, '').replace(/[、，]([）)])/g, '$1').replace('编写上我们坚持三条原则', '编写上注重术语统一与完整验算').replace(/(?:来源|出自)\s*rev_[a-z0-9]+[^。\n]*/g, '')
  return (plain.match(/[^。！？\n]+[。！？\n]*|[。！？\n]+/g) ?? []).filter(part => !/待核(?:查|实|对)?|须核对|需核对|(?:须|需|需要|应)[^。！？\n]{0,16}(?:原课件|原资料)[^。！？\n]{0,8}核对|出自原资料|无法确认|不能确认|不确定[:：]|原课件此处有图/.test(part)).join('').trim()
}
function project(value: unknown, key = ''): unknown {
  if (internalKeys.has(key) || /来源|核对状态|^source_|^evidence_/.test(key)) return Array.isArray(value) ? [] : ''
  if (typeof value === 'string') return readerText(value)
  if (Array.isArray(value)) return value.map(item => project(item)).filter(item => item !== '')
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([name, item]) => [name, project(item, name)]))
  return value
}
export function readerBook(book: CourseBook): CourseBook { return project(book) as CourseBook }
