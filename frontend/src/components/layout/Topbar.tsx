import { useAuthStore } from '@/store/auth'
import { NotificationBell } from './NotificationBell'

interface TopbarProps {
  title?: string
}

export function Topbar({ title }: TopbarProps) {
  const { user } = useAuthStore()

  return (
    <header className="flex h-14 items-center justify-between border-b bg-background px-6">
      <div className="flex items-center gap-2">
        {title && <h2 className="text-sm font-medium text-muted-foreground">{title}</h2>}
      </div>
      <div className="flex items-center gap-3">
        <NotificationBell />
        <div className="text-sm text-muted-foreground">
          {user?.department && (
            <span className="rounded bg-secondary px-2 py-0.5 text-xs">
              {user.department}
            </span>
          )}
        </div>
      </div>
    </header>
  )
}
