import { type ReactNode } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

// 匹配显式数学定界符与常见裸 LaTeX（\frac{...}{...}、\sqrt{...}、\sin 等）。
const MATH_RE =
  /\\\[(.*?)\\\]|\$\$(.*?)\$\$|\\\((.*?)\\\)|\$([^$\n]+?)\$|(\\[a-zA-Z]+(?:\{[^{}]*\})*)/gs

function render(latex: string, display: boolean): string {
  try {
    return katex.renderToString(latex, { displayMode: display, throwOnError: false })
  } catch {
    return latex
  }
}

export function mathify(text: string): ReactNode[] {
  if (!text) return []
  const nodes: ReactNode[] = []
  const re = new RegExp(MATH_RE.source, 'gs')
  let last = 0
  let key = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    let display = false
    let latex = ''
    if (m[1] != null) {
      display = true
      latex = m[1]
    } else if (m[2] != null) {
      display = true
      latex = m[2]
    } else if (m[3] != null) {
      latex = m[3]
    } else if (m[4] != null) {
      latex = m[4]
    } else if (m[5] != null) {
      latex = m[5]
    }
    if (latex.trim()) {
      nodes.push(
        <span
          key={key++}
          className={display ? 'block my-2 text-center' : 'inline-block'}
          dangerouslySetInnerHTML={{ __html: render(latex.trim(), display) }}
        />,
      )
    }
    last = re.lastIndex
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

export function MathText({ text, className }: { text: string; className?: string }) {
  return <span className={className}>{mathify(text)}</span>
}
