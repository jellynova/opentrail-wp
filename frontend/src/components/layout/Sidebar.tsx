import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Table2,
  PenLine,
  FileText,
  BarChart3,
  Folder,
  Settings,
  LogOut,
  ChevronRight,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/store/auth'
import { Button } from '@/components/ui/button'
import { useFiscalYears } from '@/hooks/useFiscalYears'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/trial-balance', icon: Table2, label: 'Trial Balance' },
  { to: '/journal-entries', icon: PenLine, label: 'Journal Entries' },
  { to: '/reports', icon: FileText, label: 'Reports' },
  { to: '/budget', icon: BarChart3, label: 'Budget' },
  { to: '/documents', icon: Folder, label: 'Documents' },
]

const adminItem = { to: '/admin', icon: Settings, label: 'Admin' }

export function Sidebar() {
  const { user, clearAuth, hasRole } = useAuthStore()
  const { data: fiscalYears } = useFiscalYears()

  const currentFiscalYear = fiscalYears?.find((fy) => fy.status === 'open')

  const handleLogout = () => {
    clearAuth()
    window.location.href = '/login'
  }

  return (
    <aside className="flex h-full w-60 flex-col bg-slate-900 text-slate-100">
      {/* Logo */}
      <div className="flex items-center gap-2 px-6 py-5 border-b border-slate-700">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary">
          <ChevronRight className="h-5 w-5 text-white" />
        </div>
        <div>
          <p className="text-sm font-bold leading-none">OpenTrail WP</p>
          <p className="text-xs text-slate-400 mt-0.5">BC Municipal Finance</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
              )
            }
          >
            <item.icon className="h-4 w-4 shrink-0" />
            {item.label}
          </NavLink>
        ))}

        {hasRole(['finance_admin']) && (
          <NavLink
            to={adminItem.to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
              )
            }
          >
            <adminItem.icon className="h-4 w-4 shrink-0" />
            {adminItem.label}
          </NavLink>
        )}
      </nav>

      {/* Fiscal year indicator */}
      {currentFiscalYear && (
        <div className="mx-3 mb-2 rounded-md bg-slate-800 px-3 py-2">
          <p className="text-xs text-slate-400">Current Fiscal Year</p>
          <p className="text-sm font-medium text-slate-100">{currentFiscalYear.label}</p>
          <span className="inline-flex items-center rounded-full bg-green-900 px-2 py-0.5 text-xs text-green-300 mt-1">
            Open
          </span>
        </div>
      )}

      {/* User info + logout */}
      <div className="border-t border-slate-700 p-3">
        <div className="flex items-center gap-3 px-3 py-2 rounded-md">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-600 text-xs font-semibold text-slate-100 shrink-0">
            {user?.username?.slice(0, 1).toUpperCase() ?? 'U'}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-100 truncate">{user?.username}</p>
            <p className="text-xs text-slate-400 truncate capitalize">
              {user?.role?.replace(/_/g, ' ')}
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="mt-1 w-full justify-start gap-2 text-slate-400 hover:text-slate-100 hover:bg-slate-800"
          onClick={handleLogout}
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </div>
    </aside>
  )
}
