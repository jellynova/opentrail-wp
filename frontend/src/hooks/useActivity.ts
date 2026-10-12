import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import { useAuthStore } from '@/store/auth'
import type { ActivityNotification, AuditLogEntry, AuditLogPage } from '@/types'

export interface AuditFilters {
  resource_type?: string
  action?: string
  user_id?: number
  date_from?: string
  date_to?: string
}

export function useAuditLogs(filters: AuditFilters, limit = 100) {
  return useQuery({
    queryKey: ['audit-logs', filters, limit],
    queryFn: () =>
      api
        .get<AuditLogPage>('/v1/audit-logs', { params: { ...filters, limit } })
        .then((r) => r.data),
  })
}

/** Recent activity recorded before this page loaded (so the bell is not empty on arrival). */
export function useRecentActivity() {
  return useQuery({
    queryKey: ['activity-recent'],
    queryFn: () => api.get<ActivityNotification[]>('/v1/events/recent', { params: { limit: 25 } }).then((r) => r.data),
    staleTime: 30_000,
  })
}

const MAX_NOTIFICATIONS = 50

/**
 * Live notifications over SSE (PLAN §8.2).
 *
 * `EventSource` cannot set an Authorization header, so the access token goes in the query
 * string. Query caches for the affected resources are refreshed as events arrive, which
 * keeps other users' changes visible without polling.
 */
export function useEventStream() {
  const token = useAuthStore((s) => s.accessToken)
  const queryClient = useQueryClient()
  const [notifications, setNotifications] = useState<ActivityNotification[]>([])
  const [connected, setConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState<ActivityNotification | null>(null)

  const sourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!token) return
    const base = import.meta.env.VITE_API_BASE_URL || '/api'
    const source = new EventSource(`${base}/v1/events/stream?token=${encodeURIComponent(token)}`)
    sourceRef.current = source

    source.addEventListener('ready', (event) => {
      setConnected(true)
      try {
        const payload = JSON.parse((event as MessageEvent).data) as { recent: ActivityNotification[] }
        setNotifications((payload.recent ?? []).slice().reverse().slice(0, MAX_NOTIFICATIONS))
      } catch {
        /* a malformed ready frame is not worth breaking the stream over */
      }
    })

    source.addEventListener('notification', (event) => {
      try {
        const notification = JSON.parse((event as MessageEvent).data) as ActivityNotification
        setLastEvent(notification)
        setNotifications((current) => [notification, ...current].slice(0, MAX_NOTIFICATIONS))
        const key = notification.resource_type
        const cacheKey = INVALIDATION_KEYS[key]
        if (cacheKey) void queryClient.invalidateQueries({ queryKey: [cacheKey] })
      } catch {
        /* ignore malformed frames */
      }
    })

    source.onerror = () => setConnected(false)

    return () => {
      source.close()
      sourceRef.current = null
      setConnected(false)
    }
  }, [token, queryClient])

  return { notifications, connected, lastEvent, clear: () => setNotifications([]) }
}

/** Audit resource types mapped onto the React Query cache key to refresh on a live event. */
const INVALIDATION_KEYS: Record<string, string> = {
  journal_entry: 'journal-entries',
  trial_balance_entry: 'trial-balance',
  trial_balance: 'trial-balance',
  budget_request: 'budget-requests',
  budget_year: 'budget-years',
  budget_amendment: 'budget-amendments',
  document: 'documents',
  period: 'fiscal-years',
  fiscal_year: 'fiscal-years',
  report: 'reports',
  account: 'accounts',
  user: 'admin-users',
  connector: 'connectors',
}

/** Row type re-exported for the activity table. */
export type { AuditLogEntry }
