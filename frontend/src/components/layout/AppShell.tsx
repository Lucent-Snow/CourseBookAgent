import { Link, NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'

const navClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'rounded-md px-3 py-1.5 text-sm transition-colors',
    isActive
      ? 'bg-accent font-medium text-accent-foreground'
      : 'text-muted-foreground hover:text-foreground',
  )

export function AppShell() {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="sticky top-0 z-10 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <Link to="/" className="flex items-center gap-3">
            <div className="grid size-8 place-items-center rounded bg-primary font-bold text-primary-foreground">
              课
            </div>
            <div>
              <div className="text-[11px] leading-tight tracking-widest text-muted-foreground uppercase">
                CourseBookAgent
              </div>
              <h1 className="text-base font-bold leading-tight">智课成书</h1>
            </div>
          </Link>
          <nav className="flex items-center gap-1">
            <NavLink to="/" className={navClass} end>
              书架
            </NavLink>
            <NavLink to="/review" className={navClass}>
              质量报告
            </NavLink>
            <NavLink to="/settings" className={navClass}>
              设置
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}
