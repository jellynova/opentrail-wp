import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Toaster } from '@/components/ui/toaster'

export function AppShell() {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar — fixed width on desktop */}
      <Sidebar />

      {/* Main content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>

      <Toaster />
    </div>
  )
}
