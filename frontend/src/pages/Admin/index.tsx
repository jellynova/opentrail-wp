import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, TestTube2, RefreshCw, Loader2, Pencil, Trash2, Lock, Unlock, FastForward, ShieldAlert } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import api from '@/lib/api'
import { formatDate, formatDateTime } from '@/lib/utils'
import { toast } from '@/hooks/useToast'
import { useAuthStore } from '@/store/auth'
import { apiErrorMessage, humanise } from '@/lib/utils'
import {
  useCloseFiscalYear,
  useCreateFiscalYear,
  useCreatePeriod,
  useFiscalYears,
  usePeriodClose,
  usePeriodCloseCheck,
  usePeriodCloseSnapshot,
  usePeriodReopen,
  usePeriods,
  useRollForwardFiscalYear,
} from '@/hooks/useFiscalYears'

import type { Period, User, ExternalConnector, MappingScheme } from '@/types'

// ── Users Tab ────────────────────────────────────────────────────────────────

function UserRoleBadge({ role }: { role: User['role'] }) {
  const variants: Record<User['role'], 'success' | 'info' | 'warning' | 'secondary'> = {
    finance_admin: 'success',
    finance_officer: 'info',
    budget_manager: 'warning',
    viewer: 'secondary',
  }
  return <Badge variant={variants[role]}>{role.replace(/_/g, ' ')}</Badge>
}

function UsersTab() {
  const [createOpen, setCreateOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<User['role']>('viewer')
  const [department, setDepartment] = useState('')
  const [password, setPassword] = useState('')

  const queryClient = useQueryClient()

  const { data: users, isLoading } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => api.get<User[]>('/v1/users').then((r) => r.data),
  })

  const createUser = useMutation({
    mutationFn: (payload: object) =>
      api.post<User>('/v1/users', payload).then((r) => r.data),
    onSuccess: () => {
      toast({ title: 'User created' })
      void queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      setCreateOpen(false)
      setUsername(''); setEmail(''); setRole('viewer'); setDepartment(''); setPassword('')
    },
    onError: () => toast({ title: 'Error creating user', variant: 'destructive' }),
  })

  const deactivateUser = useMutation({
    mutationFn: (id: number) =>
      api.put(`/v1/users/${id}`, { is_active: false }).then((r) => r.data),
    onSuccess: () => {
      toast({ title: 'User deactivated' })
      void queryClient.invalidateQueries({ queryKey: ['admin-users'] })
    },
  })

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" /> Add User
        </Button>
      </div>

      {isLoading ? (
        <LoadingSpinner fullPage />
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Username</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Department</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users?.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-medium">{u.username}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{u.email}</TableCell>
                  <TableCell><UserRoleBadge role={u.role} /></TableCell>
                  <TableCell className="text-sm">{u.department ?? '—'}</TableCell>
                  <TableCell>
                    <Badge variant={u.is_active ? 'success' : 'secondary'}>
                      {u.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDate(u.created_at)}
                  </TableCell>
                  <TableCell>
                    {u.is_active && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-destructive hover:text-destructive"
                        onClick={() => deactivateUser.mutate(u.id)}
                        disabled={deactivateUser.isPending}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={(o) => !o && setCreateOpen(false)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Create User</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Username</Label>
                <Input value={username} onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>Email</Label>
                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>Role</Label>
                <Select value={role} onValueChange={(v) => setRole(v as User['role'])}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="finance_admin">Finance Admin</SelectItem>
                    <SelectItem value="finance_officer">Finance Officer</SelectItem>
                    <SelectItem value="budget_manager">Budget Manager</SelectItem>
                    <SelectItem value="viewer">Viewer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Department</Label>
                <Input value={department} onChange={(e) => setDepartment(e.target.value)} />
              </div>
              <div className="space-y-1 col-span-2">
                <Label>Password</Label>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button
              onClick={() =>
                createUser.mutate({ username, email, role, department: department || null, password })
              }
              disabled={createUser.isPending || !username || !email || !password}
            >
              {createUser.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Connectors Tab ───────────────────────────────────────────────────────────

function ConnectorsTab() {
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState('')
  const [systemType, setSystemType] = useState<ExternalConnector['system_type']>('amais')
  const [host, setHost] = useState('')
  const [port, setPort] = useState('')
  const [dbName, setDbName] = useState('')
  const [dbUsername, setDbUsername] = useState('')
  const [dbPassword, setDbPassword] = useState('')
  const [schemaName, setSchemaName] = useState('')

  const queryClient = useQueryClient()

  const { data: connectors, isLoading } = useQuery({
    queryKey: ['connectors'],
    queryFn: () =>
      api.get<ExternalConnector[]>('/v1/connectors').then((r) => r.data),
  })

  const createConnector = useMutation({
    mutationFn: (payload: object) =>
      api.post<ExternalConnector>('/v1/connectors', payload).then((r) => r.data),
    onSuccess: () => {
      toast({ title: 'Connector created' })
      void queryClient.invalidateQueries({ queryKey: ['connectors'] })
      setCreateOpen(false)
    },
    onError: () => toast({ title: 'Error', variant: 'destructive' }),
  })

  const testConnection = useMutation({
    mutationFn: (id: number) =>
      api.post(`/v1/connectors/${id}/test`).then((r) => r.data),
    onSuccess: () => toast({ title: 'Connection successful' }),
    onError: () => toast({ title: 'Connection failed', variant: 'destructive' }),
  })

  const pullCOA = useMutation({
    mutationFn: (id: number) => {
      const year = window.prompt('ERP fiscal year to import (e.g. 2025)', String(new Date().getFullYear()))
      if (!year) return Promise.resolve(null)
      return api
        .post<{ records_created: number; records_updated: number; errors: string[] }>(
          `/v1/connectors/${id}/pull/coa`,
          { fiscal_year: Number(year) }
        )
        .then((r) => r.data)
    },
    onSuccess: (r) =>
      r &&
      toast({
        title: 'Chart of accounts imported',
        description: `${r.records_created} new, ${r.records_updated} updated${r.errors.length ? `, ${r.errors.length} errors` : ''}`,
      }),
    onError: (err) => toast({ title: 'Pull failed', description: apiErrorMessage(err), variant: 'destructive' }),
  })

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" /> Add Connector
        </Button>
      </div>

      {isLoading ? (
        <LoadingSpinner fullPage />
      ) : !connectors?.length ? (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="text-sm text-muted-foreground">No connectors configured.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {connectors.map((conn) => (
            <Card key={conn.id}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">{conn.name}</CardTitle>
                  <Badge variant={conn.is_active ? 'success' : 'secondary'}>
                    {conn.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="text-xs text-muted-foreground space-y-0.5">
                  <p><span className="font-medium">Type:</span> {conn.system_type}</p>
                  {conn.host && <p><span className="font-medium">Host:</span> {conn.host}:{conn.port}</p>}
                  {conn.database_name && <p><span className="font-medium">DB:</span> {conn.database_name}</p>}
                  {conn.last_tested_at && (
                    <p><span className="font-medium">Last tested:</span> {formatDateTime(conn.last_tested_at)}</p>
                  )}
                  {conn.last_pull_at && (
                    <p><span className="font-medium">Last pull:</span> {formatDateTime(conn.last_pull_at)}</p>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => testConnection.mutate(conn.id)}
                    disabled={testConnection.isPending}
                  >
                    <TestTube2 className="mr-1 h-4 w-4" />
                    Test
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => pullCOA.mutate(conn.id)}
                    disabled={pullCOA.isPending}
                  >
                    <RefreshCw className="mr-1 h-4 w-4" />
                    Pull COA
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={(o) => !o && setCreateOpen(false)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add Connector</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1 col-span-2">
                <Label>Name</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="AMAIS Production" />
              </div>
              <div className="space-y-1 col-span-2">
                <Label>System Type</Label>
                <Select value={systemType} onValueChange={(v) => setSystemType(v as ExternalConnector['system_type'])}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="amais">AMAIS</SelectItem>
                    <SelectItem value="vadim">Vadim</SelectItem>
                    <SelectItem value="mssql">MS SQL Server</SelectItem>
                    <SelectItem value="postgres">PostgreSQL</SelectItem>
                    <SelectItem value="mysql">MySQL</SelectItem>
                    <SelectItem value="sqlite">SQLite</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Host</Label>
                <Input value={host} onChange={(e) => setHost(e.target.value)} placeholder="db.example.com" />
              </div>
              <div className="space-y-1">
                <Label>Port</Label>
                <Input value={port} onChange={(e) => setPort(e.target.value)} placeholder="1433" type="number" />
              </div>
              <div className="space-y-1">
                <Label>Database</Label>
                <Input value={dbName} onChange={(e) => setDbName(e.target.value)} placeholder="AMAIS_DB" />
              </div>
              <div className="space-y-1">
                <Label>Schema</Label>
                <Input value={schemaName} onChange={(e) => setSchemaName(e.target.value)} placeholder="dbo" />
              </div>
              <div className="space-y-1">
                <Label>Username</Label>
                <Input value={dbUsername} onChange={(e) => setDbUsername(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>Password</Label>
                <Input type="password" value={dbPassword} onChange={(e) => setDbPassword(e.target.value)} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button
              onClick={() =>
                createConnector.mutate({
                  name,
                  system_type: systemType,
                  host: host || null,
                  port: port ? parseInt(port) : null,
                  database_name: dbName || null,
                  username: dbUsername || null,
                  password: dbPassword || null,
                  schema_name: schemaName || null,
                })
              }
              disabled={createConnector.isPending || !name}
            >
              {createConnector.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Fiscal Years Tab ─────────────────────────────────────────────────────────

/** Close / reopen one period, showing the pre-close checks first (PLAN §7.3). */
function PeriodRow({
  period,
  onChanged,
}: {
  period: Period
  onChanged: () => void
}) {
  const user = useAuthStore((s) => s.user)
  const isAdmin = user?.role === 'finance_admin'
  const [checkOpen, setCheckOpen] = useState(false)
  const [reason, setReason] = useState('')

  const { data: check, isLoading } = usePeriodCloseCheck(checkOpen ? period.id : null)
  const { data: snapshot } = usePeriodCloseSnapshot(period.id, period.is_closed && checkOpen)
  const close = usePeriodClose(period.id)
  const reopen = usePeriodReopen(period.id)

  const runClose = (force: boolean) =>
    close.mutate(
      { force },
      {
        onSuccess: () => {
          toast({ title: `${period.name} closed` })
          setCheckOpen(false)
          onChanged()
        },
        onError: (err) =>
          toast({ title: 'Could not close the period', description: apiErrorMessage(err), variant: 'destructive' }),
      }
    )

  const runReopen = () =>
    reopen.mutate(
      { reason: reason || undefined },
      {
        onSuccess: () => {
          toast({ title: `${period.name} reopened` })
          setCheckOpen(false)
          setReason('')
          onChanged()
        },
        onError: (err) =>
          toast({ title: 'Could not reopen the period', description: apiErrorMessage(err), variant: 'destructive' }),
      }
    )

  return (
    <div className="rounded-sm bg-muted/50 px-2 py-1">
      <div className="flex items-center justify-between">
        <span className="text-xs">{period.name}</span>
        <div className="flex items-center gap-1">
          <Badge variant={period.is_closed ? 'secondary' : 'success'} className="text-xs">
            {period.is_closed ? 'Closed' : 'Open'}
          </Badge>
          <Button
            size="sm"
            variant="ghost"
            className="h-6 px-1"
            title={period.is_closed ? 'Period close details / reopen' : 'Close this period'}
            onClick={(e) => {
              // Without this the click bubbles to the fiscal-year card, which collapses
              // the period list and would unmount this dialog.
              e.stopPropagation()
              setCheckOpen(true)
            }}
          >
            {period.is_closed ? <Unlock className="h-3 w-3" /> : <Lock className="h-3 w-3" />}
          </Button>
        </div>
      </div>

      <Dialog open={checkOpen} onOpenChange={(o) => !o && setCheckOpen(false)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {period.is_closed ? `Reopen ${period.name}` : `Close ${period.name}`}
            </DialogTitle>
          </DialogHeader>

          {period.is_closed ? (
            <div className="space-y-3 py-2 text-sm">
              {snapshot ? (
                <div className="space-y-1 text-xs text-muted-foreground">
                  <p>
                    Closed by <span className="text-foreground">{snapshot.closed_by_username}</span> on{' '}
                    {formatDateTime(snapshot.closed_at)}
                  </p>
                  <p>
                    {snapshot.account_count} accounts · {snapshot.journal_entry_count} posted journal entries ·{' '}
                    {snapshot.is_balanced ? 'balanced' : 'NOT balanced'}
                  </p>
                  {snapshot.overrides && <p className="text-amber-700">{snapshot.overrides}</p>}
                  {snapshot.reopened_at && (
                    <p className="text-amber-700">Reopened {formatDateTime(snapshot.reopened_at)}</p>
                  )}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">Loading the close snapshot…</p>
              )}
              <div className="space-y-1">
                <Label className="text-xs">Reason for reopening</Label>
                <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. late invoice" />
              </div>
              {!isAdmin && (
                <p className="text-xs text-muted-foreground">Only a finance_admin can reopen a closed period.</p>
              )}
            </div>
          ) : isLoading ? (
            <LoadingSpinner fullPage />
          ) : (
            <div className="space-y-3 py-2 text-sm">
              {check?.ready ? (
                <p className="text-green-700">
                  All journal entries are posted and the year's working papers are signed off.
                </p>
              ) : (
                <div className="space-y-2">
                  {check?.unposted_journal_entries.length ? (
                    <div>
                      <p className="text-xs font-medium text-destructive">Journal entries not posted</p>
                      <ul className="ml-4 list-disc text-xs text-muted-foreground">
                        {check.unposted_journal_entries.map((e) => (
                          <li key={e.id}>
                            {e.reference ?? `#${e.id}`} ({humanise(e.entry_type)}, {e.status})
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {check?.unsigned_documents.length ? (
                    <div>
                      <p className="text-xs font-medium text-amber-700">Working papers not signed off</p>
                      <ul className="ml-4 list-disc text-xs text-muted-foreground">
                        {check.unsigned_documents.map((d) => (
                          <li key={d.document_id}>
                            {d.display_name} ({humanise(d.state)})
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              )}
              <p className="text-xs text-muted-foreground">
                Closing snapshots the closing balance of every account so the period is frozen for audit.
              </p>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setCheckOpen(false)}>Cancel</Button>
            {period.is_closed ? (
              <Button onClick={runReopen} disabled={!isAdmin || reopen.isPending}>
                {reopen.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Reopen period
              </Button>
            ) : (
              <>
                {check && !check.ready && isAdmin && (
                  <Button
                    variant="outline"
                    className="text-amber-700"
                    onClick={() => runClose(true)}
                    disabled={close.isPending}
                    title="Close without the working-paper sign-offs (finance_admin only)"
                  >
                    <ShieldAlert className="mr-2 h-4 w-4" /> Force close
                  </Button>
                )}
                <Button onClick={() => runClose(false)} disabled={close.isPending || !check?.ready}>
                  {close.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Close period
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function FiscalYearsTab() {
  const [createFYOpen, setCreateFYOpen] = useState(false)
  const [label, setLabel] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [selectedFYId, setSelectedFYId] = useState<number | null>(null)
  const [createPeriodOpen, setCreatePeriodOpen] = useState(false)
  const [periodName, setPeriodName] = useState('')
  const [periodNumber, setPeriodNumber] = useState('')
  const [periodStart, setPeriodStart] = useState('')
  const [periodEnd, setPeriodEnd] = useState('')

  const { data: fiscalYears, isLoading } = useFiscalYears()
  const { data: periods, refetch: refetchPeriods } = usePeriods(selectedFYId)
  const createFY = useCreateFiscalYear()
  const createPeriod = useCreatePeriod(selectedFYId ?? 0)
  const closeYear = useCloseFiscalYear()
  const rollForward = useRollForwardFiscalYear()
  const [rollForwardFor, setRollForwardFor] = useState<number | null>(null)
  const [rollForwardLabel, setRollForwardLabel] = useState('')

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCreateFYOpen(true)}>
          <Plus className="mr-2 h-4 w-4" /> New Fiscal Year
        </Button>
      </div>

      {isLoading ? (
        <LoadingSpinner fullPage />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {fiscalYears?.map((fy) => (
            <Card
              key={fy.id}
              className={`cursor-pointer transition-colors ${selectedFYId === fy.id ? 'border-primary' : ''}`}
              onClick={() => setSelectedFYId(fy.id === selectedFYId ? null : fy.id)}
            >
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm">{fy.label}</CardTitle>
                  <Badge
                    variant={fy.status === 'open' ? 'success' : fy.status === 'locked' ? 'warning' : 'secondary'}
                  >
                    {fy.status}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">
                  {formatDate(fy.start_date)} – {formatDate(fy.end_date)}
                </p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {fy.status === 'open' && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-6 text-xs"
                      disabled={closeYear.isPending}
                      onClick={(e) => {
                        e.stopPropagation()
                        if (!confirm(`Close ${fy.label}? Every period is closed and snapshotted in order.`)) return
                        closeYear.mutate(
                          { fiscalYearId: fy.id },
                          {
                            onSuccess: () => {
                              toast({ title: `Fiscal year ${fy.label} closed` })
                              setSelectedFYId(fy.id)
                            },
                            onError: (err) =>
                              toast({
                                title: 'Could not close the fiscal year',
                                description: apiErrorMessage(err),
                                variant: 'destructive',
                              }),
                          }
                        )
                      }}
                    >
                      <Lock className="mr-1 h-3 w-3" /> Close year
                    </Button>
                  )}
                  {fy.status === 'closed' && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-6 text-xs"
                      onClick={(e) => {
                        e.stopPropagation()
                        setRollForwardFor(fy.id)
                        setRollForwardLabel(String(Number(fy.label) + 1 || ''))
                      }}
                    >
                      <FastForward className="mr-1 h-3 w-3" /> Roll forward
                    </Button>
                  )}
                </div>
                {selectedFYId === fy.id && periods && (
                  <div className="mt-3 space-y-1">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium">Periods ({periods.length})</p>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 text-xs"
                        onClick={(e) => { e.stopPropagation(); setCreatePeriodOpen(true) }}
                      >
                        <Plus className="mr-1 h-3 w-3" /> Add
                      </Button>
                    </div>
                    {periods.map((p) => (
                      <PeriodRow key={p.id} period={p} onChanged={() => void refetchPeriods()} />
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Roll forward dialog */}
      <Dialog open={rollForwardFor !== null} onOpenChange={(o) => !o && setRollForwardFor(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Roll forward fiscal year</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2 text-sm">
            <p className="text-xs text-muted-foreground">
              Creates the next fiscal year with 12 periods, copies the chart of accounts, ERP mappings and mapping
              classifications, and posts each account&apos;s closing balance as the new opening balance.
            </p>
            <div className="space-y-1">
              <Label>New fiscal year label</Label>
              <Input
                value={rollForwardLabel}
                onChange={(e) => setRollForwardLabel(e.target.value)}
                placeholder="e.g. 2026"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRollForwardFor(null)}>Cancel</Button>
            <Button
              disabled={rollForward.isPending}
              onClick={() =>
                rollForward.mutate(
                  { fiscalYearId: rollForwardFor as number, label: rollForwardLabel || undefined },
                  {
                    onSuccess: (result) => {
                      toast({
                        title: `Fiscal year ${result.fiscal_year.label} created`,
                        description: `${result.accounts_copied} accounts, ${result.opening_balances_posted} opening balances (${result.balanced ? 'balanced' : 'out of balance'})`,
                      })
                      setRollForwardFor(null)
                      setSelectedFYId(result.fiscal_year.id)
                    },
                    onError: (err) =>
                      toast({
                        title: 'Roll forward failed',
                        description: apiErrorMessage(err),
                        variant: 'destructive',
                      }),
                  }
                )
              }
            >
              {rollForward.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Roll forward
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create FY Dialog */}
      <Dialog open={createFYOpen} onOpenChange={(o) => !o && setCreateFYOpen(false)}>
        <DialogContent>
          <DialogHeader><DialogTitle>New Fiscal Year</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label>Label</Label>
              <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="2025-26" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Start Date</Label>
                <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>End Date</Label>
                <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateFYOpen(false)}>Cancel</Button>
            <Button
              onClick={() =>
                createFY.mutate(
                  { label, start_date: startDate, end_date: endDate },
                  {
                    onSuccess: () => {
                      toast({ title: 'Fiscal year created' })
                      setCreateFYOpen(false)
                      setLabel(''); setStartDate(''); setEndDate('')
                    },
                    onError: () => toast({ title: 'Error', variant: 'destructive' }),
                  }
                )
              }
              disabled={createFY.isPending || !label || !startDate || !endDate}
            >
              {createFY.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Period Dialog */}
      <Dialog open={createPeriodOpen} onOpenChange={(o) => !o && setCreatePeriodOpen(false)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add Period</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Period #</Label>
                <Input
                  type="number"
                  value={periodNumber}
                  onChange={(e) => setPeriodNumber(e.target.value)}
                  placeholder="1"
                />
              </div>
              <div className="space-y-1">
                <Label>Name</Label>
                <Input
                  value={periodName}
                  onChange={(e) => setPeriodName(e.target.value)}
                  placeholder="April 2025"
                />
              </div>
              <div className="space-y-1">
                <Label>Start Date</Label>
                <Input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>End Date</Label>
                <Input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreatePeriodOpen(false)}>Cancel</Button>
            <Button
              disabled={createPeriod.isPending || !periodName || !periodNumber || !selectedFYId}
              onClick={() =>
                createPeriod.mutate(
                  {
                    period_number: parseInt(periodNumber),
                    name: periodName,
                    start_date: periodStart,
                    end_date: periodEnd,
                  },
                  {
                    onSuccess: () => {
                      toast({ title: 'Period created' })
                      setCreatePeriodOpen(false)
                      setPeriodName(''); setPeriodNumber(''); setPeriodStart(''); setPeriodEnd('')
                    },
                    onError: () => toast({ title: 'Error', variant: 'destructive' }),
                  }
                )
              }
            >
              {createPeriod.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Add Period
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Mapping Schemes Tab ──────────────────────────────────────────────────────

function MappingSchemesTab() {
  const [createOpen, setCreateOpen] = useState(false)
  const [schemeName, setSchemeName] = useState('')
  const [schemeDesc, setSchemeDesc] = useState('')
  const queryClient = useQueryClient()

  const { data: schemes, isLoading } = useQuery({
    queryKey: ['mapping-schemes'],
    queryFn: () =>
      api.get<MappingScheme[]>('/v1/mapping-schemes').then((r) => r.data),
  })

  const createScheme = useMutation({
    mutationFn: (payload: object) =>
      api.post<MappingScheme>('/v1/mapping-schemes', payload).then((r) => r.data),
    onSuccess: () => {
      toast({ title: 'Scheme created' })
      void queryClient.invalidateQueries({ queryKey: ['mapping-schemes'] })
      setCreateOpen(false)
      setSchemeName(''); setSchemeDesc('')
    },
    onError: () => toast({ title: 'Error', variant: 'destructive' }),
  })

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" /> New Scheme
        </Button>
      </div>

      {isLoading ? (
        <LoadingSpinner fullPage />
      ) : !schemes?.length ? (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="text-sm text-muted-foreground">No mapping schemes.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Status</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {schemes.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">{s.name}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{s.description ?? '—'}</TableCell>
                  <TableCell>
                    <Badge variant={s.is_active ? 'success' : 'secondary'}>
                      {s.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Button size="icon" variant="ghost" className="h-8 w-8">
                      <Pencil className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={(o) => !o && setCreateOpen(false)}>
        <DialogContent>
          <DialogHeader><DialogTitle>New Mapping Scheme</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label>Name</Label>
              <Input
                value={schemeName}
                onChange={(e) => setSchemeName(e.target.value)}
                placeholder="e.g. PSAB 2025"
              />
            </div>
            <div className="space-y-1">
              <Label>Description</Label>
              <Input
                value={schemeDesc}
                onChange={(e) => setSchemeDesc(e.target.value)}
                placeholder="Optional description"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancel</Button>
            <Button
              onClick={() =>
                createScheme.mutate({ name: schemeName, description: schemeDesc || null, is_active: true })
              }
              disabled={createScheme.isPending || !schemeName}
            >
              {createScheme.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ── Segment Labels Tab ───────────────────────────────────────────────────────

interface SegmentDefinition {
  id: number
  segment_number: number
  label: string
  description: string | null
  is_active: boolean
}

function SegmentLabelsTab() {
  const queryClient = useQueryClient()

  const { data: segments, isLoading } = useQuery({
    queryKey: ['segment-definitions'],
    queryFn: () => api.get<SegmentDefinition[]>('/v1/segment-definitions').then((r) => r.data),
  })

  const update = useMutation({
    mutationFn: ({ id, ...body }: { id: number; label?: string; is_active?: boolean }) =>
      api.put(`/v1/segment-definitions/${id}`, body).then((r) => r.data),
    onSuccess: () => {
      toast({ title: 'Segment updated' })
      void queryClient.invalidateQueries({ queryKey: ['segment-definitions'] })
    },
    onError: (err) => toast({ title: 'Error', description: apiErrorMessage(err), variant: 'destructive' }),
  })

  const [editValues, setEditValues] = useState<Record<number, string>>({})

  if (isLoading) return <LoadingSpinner fullPage />

  if (!segments?.length) {
    return (
      <p className="text-sm text-muted-foreground">
        Segment definitions are created when the chart of accounts is imported from the ERP connector. Import the
        COA, then label the segments in use here (e.g. Fund, Department, GL Account) and mark unused ones inactive.
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Label the ERP account segments (gl-acc1…gl-acc10). Labels drive column headings and report filters.
      </p>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Segment</TableHead>
              <TableHead>Label</TableHead>
              <TableHead>In use</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {[...segments]
              .sort((a, b) => a.segment_number - b.segment_number)
              .map((seg) => (
                <TableRow key={seg.id}>
                  <TableCell className="font-mono text-sm text-muted-foreground">seg{seg.segment_number}</TableCell>
                  <TableCell>
                    <Input
                      value={editValues[seg.id] ?? seg.label}
                      onChange={(e) => setEditValues((prev) => ({ ...prev, [seg.id]: e.target.value }))}
                      className="h-8 w-48"
                    />
                  </TableCell>
                  <TableCell>
                    <input
                      type="checkbox"
                      aria-label={`Segment ${seg.segment_number} in use`}
                      checked={seg.is_active}
                      onChange={(e) => update.mutate({ id: seg.id, is_active: e.target.checked })}
                    />
                  </TableCell>
                  <TableCell>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => update.mutate({ id: seg.id, label: editValues[seg.id] ?? seg.label })}
                      disabled={update.isPending}
                    >
                      Save
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

// ── Main Admin Page ──────────────────────────────────────────────────────────

export function AdminPage() {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Administration"
        description="Manage users, connectors, fiscal years, and system configuration"
      />

      <Tabs defaultValue="users">
        <TabsList className="flex-wrap h-auto gap-1">
          <TabsTrigger value="users">Users</TabsTrigger>
          <TabsTrigger value="connectors">Connectors</TabsTrigger>
          <TabsTrigger value="fiscal-years">Fiscal Years</TabsTrigger>
          <TabsTrigger value="mapping">Mapping Schemes</TabsTrigger>
          <TabsTrigger value="segments">Segment Labels</TabsTrigger>
        </TabsList>

        <TabsContent value="users" className="mt-4"><UsersTab /></TabsContent>
        <TabsContent value="connectors" className="mt-4"><ConnectorsTab /></TabsContent>
        <TabsContent value="fiscal-years" className="mt-4"><FiscalYearsTab /></TabsContent>
        <TabsContent value="mapping" className="mt-4"><MappingSchemesTab /></TabsContent>
        <TabsContent value="segments" className="mt-4"><SegmentLabelsTab /></TabsContent>
      </Tabs>
    </div>
  )
}
