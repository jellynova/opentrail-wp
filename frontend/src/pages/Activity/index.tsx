import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, Filter, Loader2, X } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import api from '@/lib/api'
import { downloadFile } from '@/lib/download'
import { apiErrorMessage, formatDateTime, humanise } from '@/lib/utils'
import { toast } from '@/hooks/useToast'
import { useAuditLogs, useRecentActivity, type AuditFilters } from '@/hooks/useActivity'
import type { User } from '@/types'

const RESOURCE_TYPES = [
  'journal_entry',
  'trial_balance',
  'trial_balance_entry',
  'budget_request',
  'budget_year',
  'budget_amendment',
  'document',
  'period',
  'fiscal_year',
  'report',
  'account',
  'mapping_scheme',
  'segment_definition',
  'connector',
  'user',
]

const ACTION_VARIANT: Record<string, 'success' | 'warning' | 'secondary' | 'info' | 'destructive'> = {
  create: 'info',
  upload: 'info',
  update: 'secondary',
  post: 'success',
  approve: 'success',
  sign_off: 'success',
  close: 'success',
  import: 'info',
  pull_coa: 'info',
  pull_trial_balance: 'info',
  pull_budget: 'info',
  delete: 'destructive',
  reject: 'destructive',
  unpost: 'warning',
  reopen: 'warning',
  sign_off_reset: 'warning',
  roll_forward: 'info',
}

export function ActivityPage() {
  const [filters, setFilters] = useState<AuditFilters>({})
  const [draft, setDraft] = useState<AuditFilters>({})
  const [limit, setLimit] = useState(100)
  const [exporting, setExporting] = useState(false)

  const { data, isLoading, isError, error } = useAuditLogs(filters, limit)
  const { data: live } = useRecentActivity()

  const { data: users } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => api.get<User[]>('/v1/users').then((r) => r.data),
  })

  const apply = () => setFilters(draft)
  const clear = () => {
    setDraft({})
    setFilters({})
  }
  const activeCount = Object.values(filters).filter((v) => v !== undefined && v !== '').length

  const exportCsv = async () => {
    setExporting(true)
    try {
      await downloadFile('/v1/audit-logs/export', 'opentrail-activity-log.csv', {
        params: { ...filters } as Record<string, unknown>,
      })
    } catch (err) {
      toast({ title: 'Export failed', description: apiErrorMessage(err), variant: 'destructive' })
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Activity Log"
        description="Every change to financial data, with who made it and when (PLAN §8.3)"
        actions={
          <Button size="sm" variant="outline" onClick={exportCsv} disabled={exporting}>
            {exporting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
            Export CSV
          </Button>
        }
      />

      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Resource</Label>
              <Select
                value={draft.resource_type ?? 'all'}
                onValueChange={(v) => setDraft({ ...draft, resource_type: v === 'all' ? undefined : v })}
              >
                <SelectTrigger className="w-48"><SelectValue placeholder="All resources" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All resources</SelectItem>
                  {RESOURCE_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>{humanise(t)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Action</Label>
              <Input
                className="w-40"
                placeholder="e.g. post"
                value={draft.action ?? ''}
                onChange={(e) => setDraft({ ...draft, action: e.target.value || undefined })}
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs">User</Label>
              <Select
                value={draft.user_id ? String(draft.user_id) : 'all'}
                onValueChange={(v) => setDraft({ ...draft, user_id: v === 'all' ? undefined : Number(v) })}
              >
                <SelectTrigger className="w-40"><SelectValue placeholder="Anyone" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Anyone</SelectItem>
                  {users?.map((u) => (
                    <SelectItem key={u.id} value={String(u.id)}>{u.username}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">From</Label>
              <Input
                type="date"
                className="w-40"
                value={draft.date_from ?? ''}
                onChange={(e) => setDraft({ ...draft, date_from: e.target.value || undefined })}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">To</Label>
              <Input
                type="date"
                className="w-40"
                value={draft.date_to ?? ''}
                onChange={(e) => setDraft({ ...draft, date_to: e.target.value || undefined })}
              />
            </div>

            <Button size="sm" onClick={apply}>
              <Filter className="mr-2 h-4 w-4" /> Apply
            </Button>
            {(activeCount > 0 || Object.keys(draft).length > 0) && (
              <Button size="sm" variant="ghost" onClick={clear}>
                <X className="mr-2 h-4 w-4" /> Clear
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {live && live.length > 0 && (
        <div className="rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Live: </span>
          {live[0].message || humanise(live[0].action)} · {live[0].username} · {formatDateTime(live[0].timestamp)}
        </div>
      )}

      {isLoading ? (
        <LoadingSpinner fullPage />
      ) : isError ? (
        <div className="rounded-lg border bg-card p-10 text-center text-sm text-muted-foreground">
          {apiErrorMessage(error, 'Could not load the activity log.')}
        </div>
      ) : !data?.items.length ? (
        <div className="rounded-lg border bg-card p-10 text-center text-sm text-muted-foreground">
          No activity matches these filters.
        </div>
      ) : (
        <div className="space-y-3">
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-44">When</TableHead>
                  <TableHead className="w-28">User</TableHead>
                  <TableHead className="w-32">Action</TableHead>
                  <TableHead className="w-40">Resource</TableHead>
                  <TableHead>Detail</TableHead>
                  <TableHead className="w-28">IP</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="text-xs text-muted-foreground">{formatDateTime(entry.timestamp)}</TableCell>
                    <TableCell className="text-sm">{entry.username ?? '—'}</TableCell>
                    <TableCell>
                      <Badge variant={ACTION_VARIANT[entry.action] ?? 'secondary'}>{humanise(entry.action)}</Badge>
                    </TableCell>
                    <TableCell className="text-sm">
                      {humanise(entry.resource_type)}
                      {entry.resource_id !== null && (
                        <span className="text-muted-foreground"> #{entry.resource_id}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{entry.description}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{entry.ip_address ?? '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              Showing {data.items.length} of the most recent matching entries
            </p>
            {data.has_more && (
              <Button size="sm" variant="outline" onClick={() => setLimit((l) => l + 100)}>
                Load more
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
