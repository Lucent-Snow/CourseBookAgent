import { ArrowRight, BookOpen, FolderOpen } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export interface DemoPreset {
  job_id: string
  dataset_id: string
}

export function DemoEntry({ preset }: { preset: DemoPreset | null }) {
  return <section aria-label="比赛演示示例" className="rounded-2xl border border-[#a9d4d1] bg-[linear-gradient(120deg,#e8f5f3,#f8fbfa_65%)] p-5 md:p-7">
    <div className="flex flex-col justify-between gap-5 md:flex-row md:items-center">
      <div className="max-w-[630px]">
        <p className="text-xs font-semibold tracking-wide text-[#147d86]">可直接体验的比赛示例</p>
        <h2 className="mt-2 text-xl font-semibold text-[#172426]">《概率论与数理统计》教辅</h2>
        <p className="mt-2 text-sm leading-6 text-[#52686a]">{preset ? '由三份真实课堂资料生成的九章教辅预设。先阅读成品，再查看它所用的资料集；阅读示例不需要配置模型。' : '公开演示站内有获准展示的示例资料与九章教辅；本地工作台不自动复制这些资料。阅读示例不需要配置模型。'}</p>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        {preset ? <><Button render={<Link to={`/artifacts/${preset.job_id}`} />} className="bg-[#147d86] text-white hover:bg-[#116a72]"><BookOpen size={15} />阅读示例<ArrowRight size={15} /></Button><Button render={<Link to={`/datasets/${preset.dataset_id}`} />} variant="outline" className="border-[#a9d4d1] bg-white text-[#276469]"><FolderOpen size={15} />查看示例资料</Button></> : <Button render={<a href="https://coursebook-demo.vercel.app/datasets" target="_blank" rel="noopener noreferrer" />} className="bg-[#147d86] text-white hover:bg-[#116a72]"><BookOpen size={15} />打开公开示例<ArrowRight size={15} /></Button>}
      </div>
    </div>
  </section>
}
