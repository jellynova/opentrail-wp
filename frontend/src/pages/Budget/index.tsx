import { useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { Plus, Loader2 } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useBudgetYears, useBudgetRequests, useUpdateBudgetRequestStatus } from '@/hooks/useBudget'
import { formatCurrency, formatDate } from '@/lib/utils'
import { useAuthStore } from '@/store/auth'
import { toast } from '@/hooks/useToast'
import type { BudgetRequest } from '@/types'

function BudgetYearStatusBadge({ status }: { status: string }) {
  const variants: Record<string, 'success' | 'info' | 'warning' | 'secondary' | 'outline'> = {
    setup: 'secondary',
    open: 'info',
    under_review: 'warning',
    approved: 'success',
    adopted: 'success',
  }
  return (
    <Badge variant={variants[status] ?? 'secondary'}>
      {status.replace('_', ' ')}
    </Badge>
  )
}

function RequestStatusBadge({ status }: { status: string }) {
  const variants: Record<string, 'success' | 'info' | 'warning' | 'secondary' | 'destructive'> = {
    draft: 'secondary',
    submitted: 'info',
    approved: 'success',
    modified: 'warning',
    rejected: 'destructive',
  }
  return (
    <Badge variant={variants[status] ?? 'secondary'}>{status}</Badge>
  )
}

function varianceColor(pct: number): string {
  const abs = Math.abs(pct)
  if (abs < 5) return 'text-green-600'
  if (abs < 15) return 'text-yellow-600'
  return 'text-red-600'
}

function varianceDot(pct: number): string {
  const abs = Math.abs(pct)
  if (abs < 5) return 'bg-green-500'
  if (abs < 15) return 'bg-yellow-500'
  return 'bg-red-500'
}

interface BudgetActualRow {
  department: string
  budget: number
  actual: number
  variance: number
  variancePct: number
}

function BudgetVsActualChart({ data }: { data: BudgetActualRow[] }) {
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="department" tick={{ fontSize: 12 }} />
          <YAxis tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}K`} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(value: number) => formatCurrency(value)}
            labelFormatter={(label: string) => `Department: ${label}`}
          />
          <Legend />
          <Bar dataKey="budget" name="Budget" fill="hsl(221.2 83.2% 53.3%)" radius={[2, 2, 0, 0]} />
          <Bar dataKey="actual" name="Actual" fill="hsl(215.4 16.3% 46.9%)" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function BudgetRequestActions({ request }: { request: BudgetRequest }) {
  const updateStatus = useUpdateBudgetRequestStatus()
  const { hasRole } = useAuthStore()

  const canApprove = hasRole(['finance_admin', 'finance_officer'])

  if (!canApprove || request.status === 'approved' || request.status === 'rejected') return null

  return (
    <div className="flex gap-1">
      {request.status === 'submitted' && (
        <>
          <Button
            size="sm"
            variant="outline"
            className="text-green-600 border-green-300 hover:bg-green-50"
            disabled={updateStatus.isPending}
            onClick={() =>
              updateStatus.mutate(
                { id: request.id, status: 'approved', approved_amount: request.proposed_amount ?? undefined },
                {
                  onSuccess: () => toast({ title: 'Request approved' }),
                  onError: () => toast({ title: 'Error', variant: 'destructive' }),
                }
              )
            }
          >
            Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="text-red-600 border-red-300 hover:bg-red-50"
            disabled={updateStatus.isPending}
            onClick={() =>
              updateStatus.mutate(
                { id: request.id, status: 'rejected' },
                {
                  onSuccess: () => toast({ title: 'Request rejected' }),
                  onError: () => toast({ title: 'Error', variant: 'destructive' }),
                }
              )
            }
          >
            Reject
          </Button>
        </>
      )}
    </div>
  )
}

export function BudgetPage() {
  const [selectedBYId, setSelectedBYId] = useState<number | null>(null)
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [filterDept, setFilterDept] = useState<string>('all')

  const { data: budgetYears, isLoading: byLoading } = useBudgetYears()
  const { data: requests, isLoading: reqLoading } = useBudgetRequests({
    budget_year_id: selectedBYId ?? undefined,
    status: filterStatus !== 'all' ? filterStatus : undefined,
    department: filterDept !== 'all' ? filterDept : undefined,
  })

  const { hasRole } = useAuthStore()

  // Derive departments from requests for filter
  const departments = Array.from(new Set((requests ?? []).map((r) => r.department))).sort()

  // Build budget vs actual data (mock actual = proposed * 0.92 for demo)
  const budgetActualData: BudgetActualRow[] = departments.slice(0, 8).map((dept) => {
    const deptRequests = (requests ?? []).filter((r) => r.department === dept && r.status === 'approved')
    const budget = deptRequests.reduce((s, r) => s + parseFloat(r.approved_amount ?? r.proposed_amount ?? '0'), 0)
    const actual = budget * (0.88 + Math.random() * 0.2) // simulated
    const variance = actual - budget
    const variancePct = budget > 0 ? (variance / budget) * 100 : 0
    return { department: dept, budget, actual, variance, variancePct }
  })

  const visibleRequests = requests ?? []

  return (
    <div className="space-y-4">
      <PageHeader
        title="Budget"
        description="Budget requests, approvals, and budget vs actual analysis"
        actions={
          hasRole(['budget_manager', 'finance_admin', 'finance_officer']) ? (
            <Button size="sm">
              <Plus className="mr-2 h-4 w-4" />
              New Request
            </Button>
          ) : undefined
        }
      />

      <Tabs defaultValue="requests">
        <TabsList>
          <TabsTrigger value="requests">Budget Requests</TabsTrigger>
          <TabsTrigger value="vs-actual">Budget vs Actual</TabsTrigger>
          <TabsTrigger value="years">Budget Years</TabsTrigger>
        </TabsList>

        {/* Budget Requests Tab */}
        <TabsContent value="requests" className="mt-4 space-y-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Budget Year</label>
              <Select
                value={selectedBYId?.toString() ?? ''}
                onValueChange={(v) => setSelectedBYId(Number(v))}
              >
                <SelectTrigger className="w-44">
                  <SelectValue placeholder="All years" />
                </SelectTrigger>
                <SelectContent>
                  {budgetYears?.map((by) => (
                    <SelectItem key={by.id} value={by.id.toString()}>{by.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Status</label>
              <Select value={filterStatus} onValueChange={setFilterStatus}>
                <SelectTrigger className="w-36">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="submitted">Submitted</SelectItem>
                  <SelectItem value="approved">Approved</SelectItem>
                  <SelectItem value="rejected">Rejected</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {hasRole(['finance_admin', 'finance_officer']) && (
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">Department</label>
                <Select value={filterDept} onValueChange={setFilterDept}>
                  <SelectTrigger className="w-44">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Departments</SelectItem>
                    {departments.map((d) => (
                      <SelectItem key={d} value={d}>{d}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {reqLoading ? (
            <LoadingSpinner fullPage />
          ) : visibleRequests.length === 0 ? (
            <div className="rounded-lg border bg-card p-12 text-center">
              <p className="text-sm text-muted-foreground">No budget requests found.</p>
            </div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Account</TableHead>
                    <TableHead>Department</TableHead>
                    <TableHead className="text-right">Prior Yr Actual</TableHead>
                    <TableHead className="text-right">Prior Yr Budget</TableHead>
                    <TableHead className="text-right">Proposed</TableHead>
                    <TableHead className="text-right">Approved</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleRequests.map((req) => (
                    <TableRow key={req.id}>
                      <TableCell className="font-mono text-xs">
                        {req.account?.acct_fmtd ?? req.account_id}
                      </TableCell>
                      <TableCell className="text-sm">{req.department}</TableCell>
                      <TableCell className="text-right font-mono text-xs">
                        {formatCurrency(req.prior_year_actual)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs">
                        {formatCurrency(req.prior_year_budget)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs font-medium">
                        {formatCurrency(req.proposed_amount)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs">
                        {formatCurrency(req.approved_amount)}
                      </TableCell>
                      <TableCell>
                        <RequestStatusBadge status={req.status} />
                      </TableCell>
                      <TableCell>
                        <BudgetRequestActions request={req} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>

        {/* Budget vs Actual Tab */}
        <TabsContent value="vs-actual" className="mt-4 space-y-4">
          {budgetActualData.length === 0 ? (
            <div className="rounded-lg border bg-card p-12 text-center">
              <p className="text-sm text-muted-foreground">
                No approved budget requests to compare. Approve requests to see variance analysis.
              </p>
            </div>
          ) : (
            <>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Budget vs Actual by Department</CardTitle>
                </CardHeader>
                <CardContent>
                  <BudgetVsActualChart data={budgetActualData} />
                </CardContent>
              </Card>

              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Department</TableHead>
                      <TableHead className="text-right">Budget</TableHead>
                      <TableHead className="text-right">Actual</TableHead>
                      <TableHead className="text-right">Variance $</TableHead>
                      <TableHead className="text-right">Variance %</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {budgetActualData.map((row) => (
                      <TableRow key={row.department}>
                        <TableCell className="font-medium text-sm">{row.department}</TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          {formatCurrency(row.budget)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs">
                          {formatCurrency(row.actual)}
                        </TableCell>
                        <TableCell className={`text-right font-mono text-xs ${varianceColor(row.variancePct)}`}>
                          {formatCurrency(row.variance)}
                        </TableCell>
                        <TableCell className={`text-right font-mono text-xs font-semibold ${varianceColor(row.variancePct)}`}>
                          {row.variancePct.toFixed(1)}%
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1.5">
                            <div className={`h-2 w-2 rounded-full ${varianceDot(row.variancePct)}`} />
                            <span className="text-xs">
                              {Math.abs(row.variancePct) < 5
                                ? 'On track'
                                : Math.abs(row.variancePct) < 15
                                ? 'Monitor'
                                : 'Action required'}
                            </span>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          )}
        </TabsContent>

        {/* Budget Years Tab */}
        <TabsContent value="years" className="mt-4">
          {byLoading ? (
            <LoadingSpinner fullPage />
          ) : !budgetYears?.length ? (
            <div className="rounded-lg border bg-card p-12 text-center">
              <p className="text-sm text-muted-foreground">No budget years configured.</p>
            </div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Label</TableHead>
                    <TableHead>Fiscal Year ID</TableHead>
                    <TableHead>Submission Deadline</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Instructions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {budgetYears.map((by) => (
                    <TableRow key={by.id}>
                      <TableCell className="font-medium">{by.label}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{by.fiscal_year_id}</TableCell>
                      <TableCell className="text-sm">
                        {formatDate(by.submission_deadline)}
                      </TableCell>
                      <TableCell>
                        <BudgetYearStatusBadge status={by.status} />
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">
                        {by.instructions_text ?? '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}

