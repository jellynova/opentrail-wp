import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, TestTube2, RefreshCw, Loader2, Pencil, Trash2 } from 'lucide-react'
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
import { useFiscalYears, useCreateFiscalYear, usePeriods, useCreatePeriod } from '@/hooks/useFiscalYears'
import type { User, ExternalConnector, MappingScheme } from '@/types'

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
    queryFn: () => api.get<User[]>('/v1/admin/users').then((r) => r.data),
  })

  const createUser = useMutation({
    mutationFn: (payload: object) =>
      api.post<User>('/v1/admin/users', payload).then((r) => r.data),
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
      api.patch(`/v1/admin/users/${id}`, { is_active: false }).then((r) => r.data),
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
      api.get<ExternalConnector[]>('/v1/admin/connectors').then((r) => r.data),
  })

  const createConnector = useMutation({
    mutationFn: (payload: object) =>
      api.post<ExternalConnector>('/v1/admin/connectors', payload).then((r) => r.data),
    onSuccess: () => {
      toast({ title: 'Connector created' })
      void queryClient.invalidateQueries({ queryKey: ['connectors'] })
      setCreateOpen(false)
    },
    onError: () => toast({ title: 'Error', variant: 'destructive' }),
  })

  const testConnection = useMutation({
    mutationFn: (id: number) =>
      api.post(`/v1/admin/connectors/${id}/test`).then((r) => r.data),
    onSuccess: () => toast({ title: 'Connection successful' }),
    onError: () => toast({ title: 'Connection failed', variant: 'destructive' }),
  })

  const pullCOA = useMutation({
    mutationFn: (id: number) =>
      api.post(`/v1/admin/connectors/${id}/pull-coa`).then((r) => r.data),
    onSuccess: () => toast({ title: 'COA pull started' }),
    onError: () => toast({ title: 'Pull failed', variant: 'destructive' }),
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
  const { data: periods } = usePeriods(selectedFYId)
  const createFY = useCreateFiscalYear()
  const createPeriod = useCreatePeriod(selectedFYId ?? 0)

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
                      <div key={p.id} className="flex items-center justify-between rounded-sm bg-muted/50 px-2 py-1">
                        <span className="text-xs">{p.name}</span>
                        <Badge variant={p.is_closed ? 'secondary' : 'success'} className="text-xs">
                          {p.is_closed ? 'Closed' : 'Open'}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

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
      api.get<MappingScheme[]>('/v1/admin/mapping-schemes').then((r) => r.data),
  })

  const createScheme = useMutation({
    mutationFn: (payload: object) =>
      api.post<MappingScheme>('/v1/admin/mapping-schemes', payload).then((r) => r.data),
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

const SEGMENT_KEYS = ['fund', 'department', 'program', 'project', 'object', 'sub_object']

function SegmentLabelsTab() {
  const queryClient = useQueryClient()

  const { data: labels, isLoading } = useQuery({
    queryKey: ['segment-labels'],
    queryFn: () =>
      api.get<{ segment_key: string; label: string }[]>('/v1/admin/segment-labels').then((r) => r.data),
  })

  const updateLabel = useMutation({
    mutationFn: ({ key, label }: { key: string; label: string }) =>
      api.put(`/v1/admin/segment-labels/${key}`, { label }).then((r) => r.data),
    onSuccess: () => {
      toast({ title: 'Label updated' })
      void queryClient.invalidateQueries({ queryKey: ['segment-labels'] })
    },
    onError: () => toast({ title: 'Error', variant: 'destructive' }),
  })

  const [editValues, setEditValues] = useState<Record<string, string>>({})

  if (isLoading) return <LoadingSpinner fullPage />

  const getLabel = (key: string) => {
    if (key in editValues) return editValues[key]
    return labels?.find((l) => l.segment_key === key)?.label ?? key
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Customize the display names for account segment dimensions used throughout the system.
      </p>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Segment Key</TableHead>
              <TableHead>Display Label</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {SEGMENT_KEYS.map((key) => (
              <TableRow key={key}>
                <TableCell className="font-mono text-sm text-muted-foreground">{key}</TableCell>
                <TableCell>
                  <Input
                    value={getLabel(key)}
                    onChange={(e) =>
                      setEditValues((prev) => ({ ...prev, [key]: e.target.value }))
                    }
                    className="h-8 w-48"
                  />
                </TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      updateLabel.mutate({ key, label: getLabel(key) })
                    }
                    disabled={updateLabel.isPending}
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
