import { MathText } from '@/components/math/MathText'

export function GenerationNotes({ notes }: { notes: string[] }) {
  if (!notes.length) return null
  return (
    <details className="my-5 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-amber-950">
      <summary className="cursor-pointer text-sm font-medium">待核事项与生成说明（{notes.length} 条）</summary>
      <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed">
        {notes.map((note, index) => <li key={index}><MathText text={note} /></li>)}
      </ul>
    </details>
  )
}
