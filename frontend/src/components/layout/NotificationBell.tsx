import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell, Radio } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/store/auth'
import { useEventStream } from '@/hooks/useActivity'
import { toast } from '@/hooks/useToast'
import { formatRelativeTime, humanise } from '@/lib/utils'
import type { ActivityNotification } from '@/types'

/**
 * Live activity bell (PLAN §8.2). The SSE connection lives here — it is the one component
 * mounted on every page — and the stream also invalidates React Query caches, so open
 * pages refresh themselves when someone else changes data.
 */
export function NotificationBell() {
  const { notifications, connected, lastEvent, clear } = useEventStream()
  const [open, setOpen] = useState(false)
  const [seen, setSeen] = useState(0)
  const panelRef = useRef<HTMLDivElement>(null)
  const currentUser = useAuthStore((s) => s.user)

  // Announce other people's activity; your own actions are already obvious.
  useEffect(() => {
    if (!lastEvent) return
    if (currentUser && lastEvent.username === currentUser.username) return
    toast({ title: lastEvent.message || humanise(lastEvent.action) })
  }, [lastEvent, currentUser])

  useEffect(() => {
    if (open) setSeen(notifications.length)
  }, [open, notifications.length])

  useEffect(() => {
    if (!open) return
    const onClick = (event: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const unread = Math.max(0, notifications.length - seen)

  return (
    <div className="relative" ref={panelRef}>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Activity notifications"
        onClick={() => setOpen((o) => !o)}
        className="relative"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </Button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-md border bg-card shadow-lg">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">Activity</span>
              <span
                className={`flex items-center gap-1 text-[10px] ${
                  connected ? 'text-green-600' : 'text-muted-foreground'
                }`}
                title={connected ? 'Live updates connected' : 'Reconnecting…'}
              >
                <Radio className="h-3 w-3" />
                {connected ? 'live' : 'offline'}
              </span>
            </div>
            <button className="text-xs text-muted-foreground hover:text-foreground" onClick={clear}>
              Clear
            </button>
          </div>

          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="px-3 py-6 text-center text-xs text-muted-foreground">No activity yet.</p>
            ) : (
              notifications.map((n: ActivityNotification) => (
                <div key={n.id} className="border-b px-3 py-2 last:border-b-0">
                  <p className="text-xs">{n.message || humanise(n.action)}</p>
                  <p className="mt-0.5 text-[10px] text-muted-foreground">
                    {n.username ?? 'system'} · {formatRelativeTime(n.timestamp)}
                  </p>
                </div>
              ))
            )}
          </div>

          <div className="border-t px-3 py-2 text-right">
            <Link
              to="/activity"
              className="text-xs text-primary hover:underline"
              onClick={() => setOpen(false)}
            >
              View full activity log →
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}
