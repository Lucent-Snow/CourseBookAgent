import { Badge } from '@/components/ui/badge'
import type { ChapterComponent } from '@/types'

interface ComponentConfig {
  label: string
  accent: string
  badge: string
}

const CONFIG: Record<string, ComponentConfig> = {
  worked_example: {
    label: '例题',
    accent: 'border-l-amber-500',
    badge: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  },
  tip_box: {
    label: '小贴士',
    accent: 'border-l-sky-500',
    badge: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200',
  },
  warning: {
    label: '易错警告',
    accent: 'border-l-red-500',
    badge: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
  },
  procedure: {
    label: '步骤',
    accent: 'border-l-emerald-500',
    badge: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200',
  },
  side_note: {
    label: '旁注',
    accent: 'border-l-slate-400',
    badge: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  },
}

const FALLBACK: ComponentConfig = {
  label: '补充说明',
  accent: 'border-l-slate-300',
  badge: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : String(value ?? '')
}

/**
 * 组件 body 的健壮解析：
 * - 优先取 steps 数组（V2 结构）
 * - 其次取 body 字符串
 * - 兜底处理后端曾把 steps 数组误 stringify 成 Python list 的情况
 */
function bodyLines(data: Record<string, unknown>): string[] {
  if (Array.isArray(data.steps)) {
    return data.steps.map(asString).filter((s) => s.trim().length > 0)
  }
  const body = asString(data.body).trim()
  if (!body) return []
  if (body.startsWith("['") && body.endsWith("']")) {
    return body
      .slice(2, -2)
      .split("', '")
      .map((s) => s.trim())
      .filter(Boolean)
  }
  return [body]
}

export function ComponentBlock({ component }: { component: ChapterComponent }) {
  const config = CONFIG[component.component_type] ?? FALLBACK
  const title = asString(component.data.title)
  const lines = bodyLines(component.data)
  const sourceRef = asString(component.data.source_ref)
  const whenToUse = asString(component.data.when_to_use)

  return (
    <div className={`my-3 rounded-r-md border border-l-4 bg-muted/40 p-4 ${config.accent}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className={`${config.badge} border-0 font-semibold`}>
          {config.label}
        </Badge>
        {title && <span className="text-sm font-semibold">{title}</span>}
      </div>
      {lines.length > 0 && (
        <div className="mt-2 space-y-1.5">
          {lines.map((line, i) => (
            <p key={i} className="whitespace-pre-wrap text-sm leading-relaxed">
              {line}
            </p>
          ))}
        </div>
      )}
      {whenToUse && <p className="mt-2 text-xs text-muted-foreground">适用：{whenToUse}</p>}
      {sourceRef && <p className="mt-2 text-xs text-muted-foreground">来源：{sourceRef}</p>}
    </div>
  )
}
