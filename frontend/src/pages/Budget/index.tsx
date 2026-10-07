import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowLeft, Download, Loader2, Plus, Trash2 } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  useApproveAmendment,
  useBudgetAmendments,
  useBudgetRequestAction,
  useBudgetRequests,
  useBudgetVariance,
  useBudgetYears,
  useConsolidateBudget,
  useCreateAmendment,
  useCreateBudgetRequest,
  useCreateBudgetYear,
  useSetBudgetYearStatus,
  type RequestAction,
} from '@/hooks/useBudget'
import { useAccounts } from '@/hooks/useAccounts'
import { useFiscalYears, usePeriods } from '@/hooks/useFiscalYears'
import { apiErrorMessage, formatAmount, formatCurrency, formatDate } from '@/lib/utils'
import { downloadFile } from '@/lib/download'
import { useAuthStore } from '@/store/auth'
import { toast } from '@/hooks/useToast'
import type { BudgetRequest, BudgetYear, TrafficLight } from '@/types'

const FINANCE = ['finance_admin', 'finance_officer']

const YEAR_FLOW: BudgetYear['status'][] = ['setup', 'open', 'under_review', 'approved', 'adopted']

const STATUS_LABEL: Record<BudgetYear['status'], string> = {
  setup: 'Setup',
  open: 'Open for requests',
  under_review: 'Under review',
  approved: 'Approved',
  adopted: 'Adopted',
}

function BudgetYearStatusBadge({ status }: { status: BudgetYear['status'] }) {
  const variants = {
    setup: 'secondary',
    open: 'info',
    under_review: 'warning',
    approved: 'success',
    adopted: 'success',
  } as const
  return <Badge variant={variants[status] ?? 'secondary'}>{STATUS_LABEL[status] ?? status}</Badge>
}

function RequestStatusBadge({ status }: { status: string }) {
  const variants: Record<string, 'success' | 'info' | 'warning' | 'secondary' | 'destructive'> = {
    draft: 'secondary',
    submitted: 'info',
    approved: 'success',
    modified: 'warning',
    rejected: 'destructive',
  }
  return <Badge variant={variants[status] ?? 'secondary'}>{status}</Badge>
}

const LIGHT: Record<TrafficLight, { dot: string; text: string; label: string }> = {
  green: { dot: 'bg-green-500', text: 'text-green-700', label: 'On track' },
  amber: { dot: 'bg-yellow-500', text: 'text-yellow-700', label: 'Monitor' },
  red: { dot: 'bg-red-500', text: 'text-red-700', label: 'Action required' },
}

function StatusDot({ status }: { status: TrafficLight }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`h-2 w-2 rounded-full ${LIGHT[status].dot}`} />
      <span className="text-xs">{LIGHT[status].label}</span>
    </div>
  )
}

const compactCurrency = (v: number) =>
  new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD', notation: 'compact', maximumFractionDigits: 1 }).format(v)

function onError(title: string) {
  return (err: unknown) => toast({ title, description: apiErrorMessage(err), variant: 'destructive' })
}

// ---------------------------------------------------------------------------
// Requests
// ---------------------------------------------------------------------------

function NewRequestDialog({
  open,
  onClose,
  budgetYear,
}: {
  open: boolean
  onClose: () => void
  budgetYear: BudgetYear
}) {
  const { user, hasRole } = useAuthStore()
  const { data: accounts } = useAccounts({ fiscal_year_id: budgetYear.fiscal_year_id })
  const create = useCreateBudgetRequest()
  const [accountId, setAccountId] = useState('')
  const [department, setDepartment] = useState(user?.department ?? '')
  const [amount, setAmount] = useState('')
  const [justification, setJustification] = useState('')

  const save = () =>
    create.mutate(
      {
        budgetYearId: budgetYear.id,
        account_id: Number(accountId),
        department: department || undefined,
        proposed_amount: amount,
        justification_text: justification || undefined,
      },
      {
        onSuccess: () => {
          toast({ title: 'Request saved as draft', description: 'Submit it when ready for finance review.' })
          setAccountId('')
          setAmount('')
          setJustification('')
          onClose()
        },
        onError: onError('Could not save request'),
      }
    )

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>New budget request — {budgetYear.label}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Account</Label>
            <select
              aria-label="Account"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            >
              <option value="">Select account…</option>
              {accounts?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.acct_fmtd} — {a.description}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label>Department</Label>
            <Input
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              disabled={hasRole(['budget_manager']) && !!user?.department}
            />
          </div>
          <div className="space-y-1">
            <Label>Proposed amount</Label>
            <Input type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
            <p className="text-xs text-muted-foreground">
              Prior-year actual and budget are filled in automatically.
            </p>
          </div>
          <div className="space-y-1">
            <Label>Justification</Label>
            <Textarea rows={3} value={justification} onChange={(e) => setJustification(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={save} disabled={!accountId || !amount || create.isPending}>
            {create.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save draft
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ReviewDialog({
  request,
  onClose,
}: {
  request: BudgetRequest | null
  onClose: () => void
}) {
  const action = useBudgetRequestAction()
  const [amount, setAmount] = useState('')
  const [comment, setComment] = useState('')

  useEffect(() => {
    setAmount(request?.proposed_amount ?? '')
    setComment('')
  }, [request])

  if (!request) return null

  const act = (kind: RequestAction, body: Record<string, unknown>, message: string) =>
    action.mutate(
      { id: request.id, action: kind, body },
      {
        onSuccess: () => {
          toast({ title: message })
          onClose()
        },
        onError: onError('Review failed'),
      }
    )

  return (
    <Dialog open={!!request} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Review request — {request.department}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-3 gap-2">
            <div>
              <div className="text-xs text-muted-foreground">Prior-year actual</div>
              {formatCurrency(request.prior_year_actual)}
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Prior-year budget</div>
              {formatCurrency(request.prior_year_budget)}
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Proposed</div>
              <span className="font-semibold">{formatCurrency(request.proposed_amount)}</span>
            </div>
          </div>
          {request.justification_text && (
            <p className="rounded-md bg-muted/50 p-2 text-xs">{request.justification_text}</p>
          )}
          <div className="space-y-1">
            <Label>Approved amount</Label>
            <Input type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
            <p className="text-xs text-muted-foreground">Approving a different amount marks the request “modified”.</p>
          </div>
          <div className="space-y-1">
            <Label>Comment</Label>
            <Textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            disabled={!comment || action.isPending}
            onClick={() => act('return', { review_comment: comment }, 'Returned to department')}
          >
            Return for revision
          </Button>
          <Button
            variant="outline"
            className="text-red-600"
            disabled={!comment || action.isPending}
            onClick={() => act('reject', { review_comment: comment }, 'Request rejected')}
          >
            Reject
          </Button>
          <Button
            disabled={!amount || action.isPending}
            onClick={() =>
              act('approve', { approved_amount: amount, review_comment: comment || undefined }, 'Request approved')
            }
          >
            Approve
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RequestsTab({ budgetYear }: { budgetYear: BudgetYear }) {
  const { user, hasRole } = useAuthStore()
  const [filterStatus, setFilterStatus] = useState('all')
  const [filterDept, setFilterDept] = useState('all')
  const [newOpen, setNewOpen] = useState(false)
  const [reviewing, setReviewing] = useState<BudgetRequest | null>(null)
  const { data: accounts } = useAccounts({ fiscal_year_id: budgetYear.fiscal_year_id })
  const { data: requests, isLoading } = useBudgetRequests(budgetYear.id, {
    status: filterStatus !== 'all' ? filterStatus : undefined,
    department: filterDept !== 'all' ? filterDept : undefined,
  })
  const action = useBudgetRequestAction()
  const accountLabel = useMemo(() => new Map(accounts?.map((a) => [a.id, `${a.acct_fmtd} ${a.description ?? ''}`])), [accounts])
  const departments = Array.from(new Set((requests ?? []).map((r) => r.department))).sort()
  const isFinance = hasRole(FINANCE)
  const reviewOpen = budgetYear.status === 'open' || budgetYear.status === 'under_review'
  const canCreate =
    hasRole(['budget_manager', ...FINANCE]) &&
    (budgetYear.status === 'open' || (budgetYear.status === 'setup' && isFinance))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Status</label>
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="w-36">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {['all', 'draft', 'submitted', 'approved', 'modified', 'rejected'].map((s) => (
                <SelectItem key={s} value={s}>
                  {s === 'all' ? 'All' : s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {isFinance && (
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Department</label>
            <Select value={filterDept} onValueChange={setFilterDept}>
              <SelectTrigger className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All departments</SelectItem>
                {departments.map((d) => (
                  <SelectItem key={d} value={d}>
                    {d}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div className="flex-1" />
        {canCreate && (
          <Button size="sm" onClick={() => setNewOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            New request
          </Button>
        )}
      </div>

      {budgetYear.instructions_text && (
        <p className="rounded-md border bg-muted/30 p-3 text-sm">
          <span className="font-medium">Instructions: </span>
          {budgetYear.instructions_text}
          {budgetYear.submission_deadline && (
            <span className="text-muted-foreground"> — due {formatDate(budgetYear.submission_deadline)}</span>
          )}
        </p>
      )}

      {isLoading ? (
        <LoadingSpinner fullPage />
      ) : !requests?.length ? (
        <div className="rounded-lg border bg-card p-12 text-center text-sm text-muted-foreground">
          No budget requests found.
        </div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Account</TableHead>
                <TableHead>Department</TableHead>
                <TableHead className="text-right">Prior yr actual</TableHead>
                <TableHead className="text-right">Prior yr budget</TableHead>
                <TableHead className="text-right">Proposed</TableHead>
                <TableHead className="text-right">Approved</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {requests.map((req) => {
                const mine = req.submitted_by_user_id === user?.id
                return (
                  <TableRow key={req.id}>
                    <TableCell className="text-xs">
                      <span className="font-mono">{accountLabel.get(req.account_id) ?? req.account_id}</span>
                      {req.review_comment && (
                        <div className="text-muted-foreground italic">“{req.review_comment}”</div>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">{req.department}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{formatCurrency(req.prior_year_actual)}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{formatCurrency(req.prior_year_budget)}</TableCell>
                    <TableCell className="text-right font-mono text-xs font-medium">
                      {formatCurrency(req.proposed_amount)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">{formatCurrency(req.approved_amount)}</TableCell>
                    <TableCell>
                      <RequestStatusBadge status={req.status} />
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        {req.status === 'draft' && (mine || isFinance) && (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={action.isPending || budgetYear.status !== 'open'}
                              onClick={() =>
                                action.mutate(
                                  { id: req.id, action: 'submit' },
                                  { onSuccess: () => toast({ title: 'Submitted for review' }), onError: onError('Submit failed') }
                                )
                              }
                            >
                              Submit
                            </Button>
                            <Button
                              size="icon"
                              variant="ghost"
                              className="h-8 w-8"
                              aria-label="Delete request"
                              disabled={action.isPending}
                              onClick={() =>
                                action.mutate({ id: req.id, action: 'delete' }, { onError: onError('Delete failed') })
                              }
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </>
                        )}
                        {req.status === 'submitted' && isFinance && !mine && reviewOpen && (
                          <Button size="sm" variant="outline" onClick={() => setReviewing(req)}>
                            Review
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <NewRequestDialog open={newOpen} onClose={() => setNewOpen(false)} budgetYear={budgetYear} />
      <ReviewDialog request={reviewing} onClose={() => setReviewing(null)} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Budget vs actual
// ---------------------------------------------------------------------------

function VarianceTab({ budgetYear }: { budgetYear: BudgetYear }) {
  const [groupBy, setGroupBy] = useState<'department' | 'classification' | 'account'>('department')
  const [department, setDepartment] = useState<string | null>(null)
  const [periodId, setPeriodId] = useState<number | null>(null)
  const { data: periods } = usePeriods(budgetYear.fiscal_year_id)
  const params = {
    group_by: department ? 'account' : groupBy,
    department: department ?? undefined,
    period_id: periodId ?? undefined,
  }
  const { data: report, isLoading } = useBudgetVariance(budgetYear.id, params)

  const items = report?.groups
    ? report.groups.map((g) => ({ key: `${g.kind}:${g.group}`, label: g.group, drill: groupBy === 'department', ...g }))
    : (report?.rows ?? []).map((r) => ({
        key: String(r.account_id),
        label: `${r.acct_fmtd} ${r.description ?? ''}`,
        drill: false,
        ...r,
      }))
  const chartData = items
    .filter((i) => i.kind === 'expense')
    .slice(0, 12)
    .map((i) => ({ name: i.label, budget: Number(i.amended_budget), actual: Number(i.ytd_actual) }))

  const exportAs = (format: 'xlsx' | 'pdf') =>
    downloadFile(`/v1/budget-years/${budgetYear.id}/variance`, `budget_vs_actual.${format}`, {
      params: { ...params, format },
    }).catch(onError('Export failed'))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        {department ? (
          <Button variant="outline" size="sm" onClick={() => setDepartment(null)}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            All departments
          </Button>
        ) : (
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Group by</label>
            <Select value={groupBy} onValueChange={(v) => setGroupBy(v as typeof groupBy)}>
              <SelectTrigger className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="department">Department</SelectItem>
                <SelectItem value="classification">PSAB function</SelectItem>
                <SelectItem value="account">Account</SelectItem>
              </SelectContent>
            </Select>
          </div>
        )}
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Actuals through</label>
          <Select value={periodId?.toString() ?? 'ye'} onValueChange={(v) => setPeriodId(v === 'ye' ? null : Number(v))}>
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ye">Year end</SelectItem>
              {periods?.map((p) => (
                <SelectItem key={p.id} value={p.id.toString()}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {department && <h3 className="pb-2 text-sm font-semibold">{department}</h3>}
        <div className="flex-1" />
        <Button variant="outline" size="sm" onClick={() => void exportAs('xlsx')}>
          <Download className="mr-2 h-4 w-4" />
          Excel
        </Button>
        <Button variant="outline" size="sm" onClick={() => void exportAs('pdf')}>
          <Download className="mr-2 h-4 w-4" />
          PDF
        </Button>
      </div>

      {isLoading ? (
        <LoadingSpinner fullPage />
      ) : !items.length ? (
        <div className="rounded-lg border bg-card p-12 text-center text-sm text-muted-foreground">
          No budget lines yet. Consolidate approved requests or import the budget to see variance analysis.
        </div>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            Through period {report?.through_period} ({report?.percent_of_year}% of the year). Variances are
            favourable when positive: revenue above budget, or spending below budget.
          </p>
          {chartData.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Expenses — amended budget vs actual</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                      <YAxis tickFormatter={compactCurrency} tick={{ fontSize: 11 }} width={70} />
                      <Tooltip formatter={(value: number) => formatCurrency(value)} />
                      <Legend />
                      <Bar dataKey="budget" name="Budget" fill="hsl(221.2 83.2% 53.3%)" radius={[2, 2, 0, 0]} />
                      <Bar dataKey="actual" name="Actual" fill="hsl(215.4 16.3% 46.9%)" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{department || groupBy === 'account' ? 'Account' : groupBy === 'department' ? 'Department' : 'Function'}</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Original</TableHead>
                  <TableHead className="text-right">Amended</TableHead>
                  <TableHead className="text-right">Actual</TableHead>
                  <TableHead className="text-right">Variance</TableHead>
                  <TableHead className="text-right">%</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((i) => (
                  <TableRow
                    key={i.key}
                    className={i.drill ? 'cursor-pointer' : undefined}
                    onClick={i.drill ? () => setDepartment(i.label) : undefined}
                  >
                    <TableCell className="text-sm font-medium">
                      {i.label}
                      {i.drill && <span className="ml-1 text-xs text-muted-foreground">›</span>}
                    </TableCell>
                    <TableCell className="text-xs capitalize text-muted-foreground">{i.kind}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{formatAmount(i.original_budget)}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{formatAmount(i.amended_budget)}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{formatAmount(i.ytd_actual)}</TableCell>
                    <TableCell className={`text-right font-mono text-xs ${LIGHT[i.status].text}`}>
                      {formatAmount(i.variance)}
                    </TableCell>
                    <TableCell className={`text-right font-mono text-xs ${LIGHT[i.status].text}`}>
                      {i.variance_pct === null ? '—' : `${Number(i.variance_pct).toFixed(1)}%`}
                    </TableCell>
                    <TableCell>
                      <StatusDot status={i.status} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Amendments
// ---------------------------------------------------------------------------

function AmendmentsTab({ budgetYear }: { budgetYear: BudgetYear }) {
  const { hasRole } = useAuthStore()
  const { data: amendments, isLoading } = useBudgetAmendments(budgetYear.id)
  const { data: accounts } = useAccounts({ fiscal_year_id: budgetYear.fiscal_year_id })
  const create = useCreateAmendment()
  const approve = useApproveAmendment()
  const [open, setOpen] = useState(false)
  const [reference, setReference] = useState('')
  const [rationale, setRationale] = useState('')
  const [lines, setLines] = useState([{ account_id: '', amount: '' }])
  const accountLabel = new Map(accounts?.map((a) => [a.id, `${a.acct_fmtd} ${a.description ?? ''}`]))

  const save = () =>
    create.mutate(
      {
        budgetYearId: budgetYear.id,
        approval_reference: reference || undefined,
        rationale: rationale || undefined,
        lines: lines.filter((l) => l.account_id && l.amount).map((l) => ({ account_id: Number(l.account_id), amount: l.amount })),
      },
      {
        onSuccess: () => {
          toast({ title: 'Amendment drafted' })
          setOpen(false)
          setLines([{ account_id: '', amount: '' }])
          setReference('')
          setRationale('')
        },
        onError: onError('Could not create amendment'),
      }
    )

  if (budgetYear.status !== 'adopted') {
    return (
      <div className="rounded-lg border bg-card p-12 text-center text-sm text-muted-foreground">
        Amendments apply once the budget is adopted. Until then, edit budget lines directly.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {hasRole(FINANCE) && (
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            New amendment
          </Button>
        </div>
      )}
      {isLoading ? (
        <LoadingSpinner fullPage />
      ) : !amendments?.length ? (
        <div className="rounded-lg border bg-card p-12 text-center text-sm text-muted-foreground">No amendments.</div>
      ) : (
        amendments.map((a) => (
          <Card key={a.id}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base">
                Amendment {a.amendment_number}
                {a.approval_reference && <span className="ml-2 text-sm font-normal text-muted-foreground">{a.approval_reference}</span>}
              </CardTitle>
              <div className="flex items-center gap-2">
                <Badge variant={a.status === 'approved' ? 'success' : 'secondary'}>
                  {a.status}
                  {a.approved_date && ` ${formatDate(a.approved_date)}`}
                </Badge>
                {a.status === 'draft' && hasRole(['finance_admin']) && (
                  <Button
                    size="sm"
                    disabled={approve.isPending}
                    onClick={() => {
                      const ref = a.approval_reference || window.prompt('Bylaw or resolution number')
                      if (ref) approve.mutate({ id: a.id, approval_reference: ref }, { onError: onError('Approval failed') })
                    }}
                  >
                    Approve
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {a.rationale && <p className="text-muted-foreground">{a.rationale}</p>}
              <Table>
                <TableBody>
                  {a.lines.map((l) => (
                    <TableRow key={l.id}>
                      <TableCell className="font-mono text-xs">{accountLabel.get(l.account_id) ?? l.account_id}</TableCell>
                      <TableCell className="text-right font-mono text-xs">{formatAmount(l.amount, 2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        ))
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>New budget amendment</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>Approval reference (bylaw / resolution)</Label>
              <Input value={reference} onChange={(e) => setReference(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Rationale</Label>
              <Textarea rows={2} value={rationale} onChange={(e) => setRationale(e.target.value)} />
            </div>
            <Label>Changes (positive increases the budget)</Label>
            {lines.map((l, i) => (
              <div key={i} className="flex gap-2">
                <select
                  aria-label="Account"
                  value={l.account_id}
                  onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, account_id: e.target.value } : x)))}
                  className="h-9 flex-1 rounded-md border border-input bg-background px-2 text-sm"
                >
                  <option value="">Select account…</option>
                  {accounts?.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.acct_fmtd} — {a.description}
                    </option>
                  ))}
                </select>
                <Input
                  className="w-32"
                  type="number"
                  step="0.01"
                  value={l.amount}
                  onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, amount: e.target.value } : x)))}
                />
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => setLines((ls) => [...ls, { account_id: '', amount: '' }])}>
              <Plus className="mr-1 h-4 w-4" /> Add line
            </Button>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={save} disabled={create.isPending || !lines.some((l) => l.account_id && l.amount)}>
              Save draft
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Budget years
// ---------------------------------------------------------------------------

function YearControls({ budgetYear }: { budgetYear: BudgetYear }) {
  const { hasRole } = useAuthStore()
  const setStatus = useSetBudgetYearStatus()
  const consolidate = useConsolidateBudget()
  const idx = YEAR_FLOW.indexOf(budgetYear.status)
  const next = YEAR_FLOW[idx + 1]
  const prev = budgetYear.status !== 'adopted' ? YEAR_FLOW[idx - 1] : undefined

  const move = (status: BudgetYear['status']) =>
    setStatus.mutate(
      { id: budgetYear.id, status },
      { onSuccess: () => toast({ title: `Budget is now: ${STATUS_LABEL[status]}` }), onError: onError('Status change failed') }
    )

  return (
    <div className="flex flex-wrap items-center gap-2">
      <BudgetYearStatusBadge status={budgetYear.status} />
      {hasRole(['finance_admin']) && (
        <>
          {prev && (
            <Button size="sm" variant="ghost" disabled={setStatus.isPending} onClick={() => move(prev)}>
              Back to {STATUS_LABEL[prev].toLowerCase()}
            </Button>
          )}
          {(budgetYear.status === 'under_review' || budgetYear.status === 'approved') && (
            <Button
              size="sm"
              variant="outline"
              disabled={consolidate.isPending}
              onClick={() =>
                consolidate.mutate(budgetYear.id, {
                  onSuccess: (r) =>
                    toast({
                      title: `Consolidated into ${r.lines} budget lines`,
                      description: r.requests_pending_review
                        ? `${r.requests_pending_review} submitted requests are still awaiting review.`
                        : undefined,
                    }),
                  onError: onError('Consolidation failed'),
                })
              }
            >
              Consolidate requests
            </Button>
          )}
          {next && (
            <Button size="sm" disabled={setStatus.isPending} onClick={() => move(next)}>
              {next === 'adopted' ? 'Adopt budget' : `Move to ${STATUS_LABEL[next].toLowerCase()}`}
            </Button>
          )}
        </>
      )}
      <Button
        size="sm"
        variant="outline"
        onClick={() =>
          void downloadFile(`/v1/budget-years/${budgetYear.id}/council-report`, 'budget.xlsx', {
            params: { format: 'xlsx' },
          }).catch(onError('Export failed'))
        }
      >
        <Download className="mr-2 h-4 w-4" />
        Council report
      </Button>
    </div>
  )
}

function NewBudgetYearDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: fiscalYears } = useFiscalYears()
  const create = useCreateBudgetYear()
  const [fyId, setFyId] = useState('')
  const [label, setLabel] = useState('')
  const [deadline, setDeadline] = useState('')
  const [instructions, setInstructions] = useState('')
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>New budget year</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>Fiscal year</Label>
            <Select value={fyId} onValueChange={setFyId}>
              <SelectTrigger>
                <SelectValue placeholder="Select fiscal year" />
              </SelectTrigger>
              <SelectContent>
                {fiscalYears?.map((fy) => (
                  <SelectItem key={fy.id} value={fy.id.toString()}>
                    {fy.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Label</Label>
            <Input placeholder="2026 Financial Plan" value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Submission deadline</Label>
            <Input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Instructions for departments</Label>
            <Textarea rows={3} value={instructions} onChange={(e) => setInstructions(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!fyId || !label || create.isPending}
            onClick={() =>
              create.mutate(
                {
                  fiscal_year_id: Number(fyId),
                  label,
                  submission_deadline: deadline || undefined,
                  instructions_text: instructions || undefined,
                },
                { onSuccess: onClose, onError: onError('Could not create budget year') }
              )
            }
          >
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function BudgetPage() {
  const { hasRole } = useAuthStore()
  const { data: budgetYears, isLoading } = useBudgetYears()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [newYearOpen, setNewYearOpen] = useState(false)

  useEffect(() => {
    if (selectedId === null && budgetYears?.length) setSelectedId(budgetYears[0].id)
  }, [budgetYears, selectedId])

  const budgetYear = budgetYears?.find((b) => b.id === selectedId) ?? null

  return (
    <div className="space-y-4">
      <PageHeader
        title="Budget"
        description="Department requests, finance review, adoption, amendments and budget-to-actual monitoring"
        actions={
          hasRole(['finance_admin']) ? (
            <Button size="sm" variant="outline" onClick={() => setNewYearOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              New budget year
            </Button>
          ) : undefined
        }
      />

      {isLoading ? (
        <LoadingSpinner fullPage />
      ) : !budgetYears?.length ? (
        <div className="rounded-lg border bg-card p-12 text-center text-sm text-muted-foreground">
          No budget years configured.
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Select value={selectedId?.toString() ?? ''} onValueChange={(v) => setSelectedId(Number(v))}>
              <SelectTrigger className="w-56">
                <SelectValue placeholder="Budget year" />
              </SelectTrigger>
              <SelectContent>
                {budgetYears.map((by) => (
                  <SelectItem key={by.id} value={by.id.toString()}>
                    {by.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {budgetYear && <YearControls budgetYear={budgetYear} />}
          </div>

          {budgetYear && (
            <Tabs defaultValue="requests">
              <TabsList>
                <TabsTrigger value="requests">Requests</TabsTrigger>
                <TabsTrigger value="vs-actual">Budget vs actual</TabsTrigger>
                <TabsTrigger value="amendments">Amendments</TabsTrigger>
              </TabsList>
              <TabsContent value="requests" className="mt-4">
                <RequestsTab budgetYear={budgetYear} />
              </TabsContent>
              <TabsContent value="vs-actual" className="mt-4">
                <VarianceTab budgetYear={budgetYear} />
              </TabsContent>
              <TabsContent value="amendments" className="mt-4">
                <AmendmentsTab budgetYear={budgetYear} />
              </TabsContent>
            </Tabs>
          )}
        </>
      )}

      <NewBudgetYearDialog open={newYearOpen} onClose={() => setNewYearOpen(false)} />
    </div>
  )
}
