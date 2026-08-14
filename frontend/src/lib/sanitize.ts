// 清理旧产物里残留的机器痕迹（Python dict 字符串、列表 repr 等）。
// 新生成的数据已经由后端 quality.py 清理，这里是对历史缓存数据的兜底。

export function sanitizeExample(item: string): string {
  const s = (item ?? '').trim()
  if (!s) return ''
  if (s.startsWith('{') && s.endsWith('}')) {
    const keyMatch =
      s.match(/'example'\s*:\s*'((?:[^'\\]|\\.)*)'/i) ??
      s.match(/'description'\s*:\s*'((?:[^'\\]|\\.)*)'/i) ??
      s.match(/'body'\s*:\s*'((?:[^'\\]|\\.)*)'/i) ??
      s.match(/'title'\s*:\s*'((?:[^'\\]|\\.)*)'/i)
    if (keyMatch) return keyMatch[1]
  }
  return s
}

export function sanitizeList(items: string[]): string[] {
  return items.map(sanitizeExample).filter((s) => s.length > 0)
}
