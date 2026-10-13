import { BookOpen, Boxes, FolderOpen, History, Settings } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'

const navigation = [
  { to: '/datasets', label: '资料库', icon: FolderOpen },
  { to: '/runs', label: '运行', icon: History },
  { to: '/artifacts', label: '产物', icon: Boxes },
  { to: '/settings', label: '设置', icon: Settings },
]
const linkClass = ({ isActive }: { isActive: boolean }) => cn('flex items-center gap-2 rounded-md px-3 text-sm transition-colors', isActive ? 'bg-[#e6f3f3] font-medium text-[#116a72]' : 'text-[#6c7b7d] hover:bg-[#f2f5f5] hover:text-[#172426]')

export function AppShell() {
  return (
    <div className="min-h-dvh bg-[#f7f9f9] text-[#1a2b2c]">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-[232px] flex-col border-r border-[#e2e8e8] bg-white px-4 py-5 md:flex">
        <Link to="/datasets" className="flex items-center gap-3 px-3 pb-8">
          <span className="grid size-9 place-items-center rounded-xl bg-[#147d86] text-white shadow-sm shadow-[#147d86]/20">
            <BookOpen size={18} />
          </span>
          <span>
            <strong className="block text-[15px] font-semibold tracking-tight text-[#172b2d]">智课成书</strong>
            <small className="text-[11px] font-normal text-[#7b8c8e]">课程教辅工作台</small>
          </span>
        </Link>
        <nav className="space-y-1.5">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={(state) => cn(linkClass(state), 'h-10')}
            >
              <Icon size={17} />
              {label === '产物' ? '书架' : label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto border-t border-[#edf1f1] px-3 pt-4">
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2 rounded-md py-1.5 text-xs transition-colors',
                isActive ? 'font-medium text-[#147d86]' : 'text-[#859597] hover:text-[#25393b]'
              )
            }
          >
            <Settings size={14} />
            <span>环境与模型设置</span>
          </NavLink>
        </div>
      </aside>
      <header className="sticky top-0 z-30 border-b border-[#e2e8e8] bg-white md:hidden">
        <div className="flex h-14 items-center gap-2 px-4">
          <span className="grid size-8 place-items-center rounded-lg bg-[#147d86] text-white">
            <BookOpen size={16} />
          </span>
          <strong className="text-sm font-semibold text-[#172b2d]">智课成书</strong>
        </div>
        <nav className="grid grid-cols-4 gap-1 px-2 pb-2">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={(state) => cn(linkClass(state), 'h-9 justify-center px-1 text-xs')}
            >
              <Icon size={14} />
              {label === '产物' ? '书架' : label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="min-h-dvh md:ml-[232px]">
        <Outlet />
      </main>
    </div>
  )
}
