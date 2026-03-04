import { Bell } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/store/auth'

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
        <Button variant="ghost" size="icon" aria-label="Notifications">
          <Bell className="h-4 w-4" />
        </Button>
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
