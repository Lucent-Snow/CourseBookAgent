import { Badge } from '@/components/ui/badge'
import { MathText } from '@/components/math/MathText'
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

const FIELD_LABELS: Record<string, string> = {
  title: '标题',
  problem: '题目',
  problem_statement: '问题陈述',
  goal: '目标',
  key_inequality: '关键不等式',
  'δ_or_N_choice': 'δ/N 的选取',
  delta_or_N_choice: 'δ/N 的选取',
  verification_step: '验证步骤',
  common_fallacy: '常见误区',
  context: '语境',
  tip: '提示',
  why_it_works: '原理',
  mistake_pattern: '错误模式',
  why_wrong: '错误原因',
  correct_pattern: '正确写法',
  evidence_from_class: '课堂证据',
  body: '说明',
  steps: '步骤',
  conclusion: '结论',
  source_ref: '来源',
  when_to_use: '适用场景',
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : String(value ?? '')
}

function asStringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map(asString).filter((s) => s.trim().length > 0)
  }
  const raw = asString(value).trim()
  if (!raw) return []
  if (raw.startsWith('[') && raw.endsWith(']')) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) return asStringList(parsed)
    } catch {
      // fall through to a python-list-ish split below
    }
    const inner = raw.slice(1, -1).trim()
    if (inner) {
      return inner
        .split(',')
        .map((s) => s.trim().replace(/^["']|["']$/g, '').trim())
        .filter(Boolean)
    }
  }
  return [raw]
}

export function ComponentBlock({ component }: { component: ChapterComponent }) {
  const config = CONFIG[component.component_type] ?? FALLBACK
  const data = (component.data ?? {}) as Record<string, unknown>
  const title = asString(data.title)
  const sourceRef = asString(data.source_ref)
  const whenToUse = asString(data.when_to_use)
  const steps = asStringList(data.steps)
  const body = asStringList(data.body)

  const skip = new Set(['title', 'body', 'steps', 'source_ref', 'when_to_use'])
  const detailFields = Object.entries(data)
    .filter(
      ([key, value]) =>
        !skip.has(key) && value !== undefined && value !== null && asString(value).trim() !== '',
    )
    .map(([key, value]) => ({ label: FIELD_LABELS[key] ?? key, value: asString(value) }))

  return (
    <div className={`my-3 rounded-r-md border border-l-4 bg-muted/40 p-4 ${config.accent}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className={`${config.badge} border-0 font-semibold`}>
          {config.label}
        </Badge>
        {title && (
          <span className="text-sm font-semibold">
            <MathText text={title} />
          </span>
        )}
      </div>
      {steps.length > 0 && (
        <ol className="mt-2 list-decimal space-y-1.5 pl-5">
          {steps.map((line, i) => (
            <li key={i} className="text-sm leading-relaxed">
              <MathText text={line} />
            </li>
          ))}
        </ol>
      )}
      {body.length > 0 && (
        <div className="mt-2 space-y-1.5">
          {body.map((line, i) => (
            <p key={i} className="text-sm leading-relaxed whitespace-pre-wrap">
              <MathText text={line} />
            </p>
          ))}
        </div>
      )}
      {detailFields.length > 0 && (
        <dl className="mt-2 space-y-1.5">
          {detailFields.map((field, i) => (
            <div key={i} className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
              <dt className="shrink-0 text-sm font-medium text-muted-foreground">{field.label}</dt>
              <dd className="min-w-0 text-sm leading-relaxed">
                <MathText text={field.value} />
              </dd>
            </div>
          ))}
        </dl>
      )}
      {whenToUse && (
        <p className="mt-2 text-xs text-muted-foreground">
          适用：<MathText text={whenToUse} />
        </p>
      )}
      {sourceRef && <p className="mt-2 text-xs text-muted-foreground">来源：{sourceRef}</p>}
    </div>
  )
}
