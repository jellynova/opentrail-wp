import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import { AlertTriangle, Eye, Link2, Link2Off, Loader2, MessageSquare, Search, Sheet, Target } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { DocumentPreviewDialog } from '@/components/shared/DocumentPreviewDialog'
import { RelatedDocumentsDialog } from '@/components/shared/RelatedDocumentsDialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAuthStore } from '@/store/auth'
import { apiErrorMessage, formatCurrency, formatDate } from '@/lib/utils'
import { toast } from '@/hooks/useToast'
import { useFiscalYears, usePeriods } from '@/hooks/useFiscalYears'
import {
  useAccountComments,
  useAddAccountComment,
  useAddAccountLink,
  useAllAccountComments,
  useAllAccountLinks,
  useDeleteAccountComment,
  useDocumentsForLinks,
  useLeadsheets,
  useLinksByAccount,
  useMappingSchemes,
  useRemoveAccountLink,
  useResolveAccountComment,
} from '@/hooks/useLeadsheets'
import { useMateriality, useSetMateriality, useUnsupportedMaterialAccounts } from '@/hooks/useMateriality'
import type {
  AccountLink,
  LeadsheetAccount,
  LeadsheetGroup,
  LeadsheetTotals,
  UnsupportedMaterialAccount,
  WorkingPaper,
} from '@/types'

const compactCurrency = (v: number) =>
  new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD', notation: 'compact', maximumFractionDigits: 1 }).format(v)

/** Read-only viewer for one leadsheet (a PSAB classification group). */
function LeadsheetTable({
  accounts,
  totals,
  fiscalYearId,
  linkedCounts,
  commentCounts,
  flaggedAccounts,
  canEdit,
  onManageLinks,
  onManageComments,
}: {
  accounts: LeadsheetAccount[]
  totals: LeadsheetTotals
  fiscalYearId: number | null
  linkedCounts: Map<string, number>
  commentCounts: Map<string, number>
  flaggedAccounts: Map<string, UnsupportedMaterialAccount>
  canEdit: boolean
  onManageLinks: (accountCode: string) => void
  onManageComments: (accountCode: string) => void
}) {
  const [filter, setFilter] = useState('')

  const rows = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return accounts
    return accounts.filter(
      (a) =>
        a.acct_fmtd.toLowerCase().includes(q) ||
        (a.description ?? '').toLowerCase().includes(q)
    )
  }, [accounts, filter])


  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="w-64 pl-8"
            placeholder="Filter by account code or description…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
        <span className="text-xs text-muted-foreground">
          {rows.length} of {accounts.length} accounts
        </span>
      </div>

      <div className="rounded-md border overflow-hidden">
        <div className="overflow-x-auto max-h-[60vh] overflow-y-auto">
          <Table>
            <TableHeader className="sticky top-0 bg-muted/80 backdrop-blur-sm">
              <TableRow>
                <TableHead>Account</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="text-right">Prior year</TableHead>
                <TableHead className="text-right">Unadjusted</TableHead>
                <TableHead className="text-right">AJE</TableHead>
                <TableHead className="text-right">RJE</TableHead>
                <TableHead className="text-right">Final</TableHead>
                <TableHead className="text-right">Change</TableHead>
                <TableHead className="w-28">Documents</TableHead>
                <TableHead className="w-24">Notes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((a) => {
                const linkCount = linkedCounts.get(a.acct_fmtd) ?? 0
                const commentCount = commentCounts.get(a.acct_fmtd) ?? 0
                const flag = flaggedAccounts.get(a.acct_fmtd)
                return (
                  <TableRow key={a.account_id} className={flag ? 'bg-destructive/5' : ''}>
                    <TableCell className="font-mono text-xs">
                      <span className="flex items-center gap-1">
                        {flag && (
                          <span
                            title={`Material balance (${formatCurrency(flag.final_balance)}) with no supporting document — exceeds the ${formatCurrency(flag.threshold)} threshold by ${formatCurrency(flag.excess)}`}
                          >
                            <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-destructive" />
                          </span>
                        )}
                        {a.acct_fmtd}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-[260px] truncate">{a.description ?? '—'}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{formatCurrency(a.prior_year)}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{formatCurrency(a.unadjusted)}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{formatCurrency(a.aje)}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{formatCurrency(a.rje)}</TableCell>
                    <TableCell className="text-right font-mono text-xs font-medium">{formatCurrency(a.final)}</TableCell>
                    <TableCell
                      className={`text-right font-mono text-xs ${
                        Number(a.change) < 0 ? 'text-destructive' : ''
                      }`}
                    >
                      {formatCurrency(a.change)}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <button
                          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                          onClick={() => onManageLinks(a.acct_fmtd)}
                          title={canEdit ? 'Attach or detach documents' : 'View linked documents'}
                        >
                          <Link2 className="h-3.5 w-3.5" />
                          {linkCount > 0 ? (
                            <span className="font-medium text-primary">{linkCount}</span>
                          ) : (
                            <span>—</span>
                          )}
                        </button>
                      </div>
                    </TableCell>
                    <TableCell>
                      <button
                        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                        onClick={() => onManageComments(a.acct_fmtd)}
                        title={canEdit ? 'Add or view notes explaining this account' : 'View notes'}
                      >
                        <MessageSquare className="h-3.5 w-3.5" />
                        {commentCount > 0 ? (
                          <span className="font-medium text-primary">{commentCount}</span>
                        ) : (
                          <span>—</span>
                        )}
                      </button>
                    </TableCell>
                  </TableRow>
                )
              })}
              {!rows.length && (
                <TableRow>
                  <TableCell colSpan={10} className="text-center text-sm text-muted-foreground py-8">
                    No accounts match the filter.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell colSpan={2} className="font-medium">Total</TableCell>
                <TableCell className="text-right font-mono text-xs">{formatCurrency(totals.prior_year)}</TableCell>
                <TableCell className="text-right font-mono text-xs">{formatCurrency(totals.unadjusted)}</TableCell>
                <TableCell className="text-right font-mono text-xs">{formatCurrency(totals.aje)}</TableCell>
                <TableCell className="text-right font-mono text-xs">{formatCurrency(totals.rje)}</TableCell>
                <TableCell className="text-right font-mono text-xs font-medium">{formatCurrency(totals.final)}</TableCell>
                <TableCell className="text-right font-mono text-xs">{formatCurrency(totals.change)}</TableCell>
                <TableCell />
                <TableCell />
              </TableRow>
            </TableFooter>
          </Table>
        </div>
      </div>
      {fiscalYearId === null && (
        <p className="text-xs text-muted-foreground">
          Document links are scoped to a fiscal year; select a period first.
        </p>
      )}
    </div>
  )
}

// ── Materiality ──────────────────────────────────────────────────────────────

/** Set/view a fiscal year's materiality, used to flag leadsheet accounts with no support. */
function MaterialityDialog({
  open,
  fiscalYearId,
  onClose,
}: {
  open: boolean
  fiscalYearId: number | null
  onClose: () => void
}) {
  const canEdit = useAuthStore((s) => s.hasRole(['finance_admin', 'finance_officer']))
  const { data: materiality, isError, error } = useMateriality(fiscalYearId)
  const notSetYet = isError && (error as { response?: { status?: number } })?.response?.status === 404
  const setMateriality = useSetMateriality()

  const [overall, setOverall] = useState('')
  const [performance, setPerformance] = useState('')
  const [basis, setBasis] = useState('')
  const [rationale, setRationale] = useState('')

  useEffect(() => {
    if (materiality) {
      setOverall(materiality.overall_materiality)
      setPerformance(materiality.performance_materiality ?? '')
      setBasis(materiality.basis ?? '')
      setRationale(materiality.rationale ?? '')
    } else if (notSetYet) {
      setOverall('')
      setPerformance('')
      setBasis('')
      setRationale('')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [materiality?.id, fiscalYearId])

  if (!fiscalYearId) return null

  const save = () => {
    if (!overall.trim()) return
    setMateriality.mutate(
      {
        fiscalYearId,
        overall_materiality: overall.trim(),
        performance_materiality: performance.trim() || null,
        basis: basis.trim() || null,
        rationale: rationale.trim() || null,
      },
      {
        onSuccess: () => {
          toast({ title: 'Materiality saved' })
          onClose()
        },
        onError: (err) => toast({ title: 'Could not save materiality', description: apiErrorMessage(err), variant: 'destructive' }),
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Materiality</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          The threshold above which a leadsheet balance matters enough that it should have a supporting
          document attached. Accounts over this threshold with none are flagged on the leadsheet.
        </p>
        <div className="space-y-3 py-2">
          <div className="space-y-1">
            <Label>Overall materiality ($)</Label>
            <Input value={overall} onChange={(e) => setOverall(e.target.value)} disabled={!canEdit} placeholder="e.g. 50000" />
          </div>
          <div className="space-y-1">
            <Label>Performance materiality ($, optional)</Label>
            <Input
              value={performance}
              onChange={(e) => setPerformance(e.target.value)}
              disabled={!canEdit}
              placeholder="Typically 50–75% of overall; used for flagging when set"
            />
          </div>
          <div className="space-y-1">
            <Label>Basis (optional)</Label>
            <Input value={basis} onChange={(e) => setBasis(e.target.value)} disabled={!canEdit} placeholder="e.g. 2% of total revenue" />
          </div>
          <div className="space-y-1">
            <Label>Rationale (optional)</Label>
            <Input value={rationale} onChange={(e) => setRationale(e.target.value)} disabled={!canEdit} />
          </div>
          {materiality && (
            <p className="text-xs text-muted-foreground">
              Last set by {materiality.set_by_username ?? 'unknown'}.
            </p>
          )}
          {!canEdit && (
            <p className="text-xs text-muted-foreground">Only a finance officer or admin can change this.</p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
          {canEdit && (
            <Button disabled={!overall.trim() || setMateriality.isPending} onClick={save}>
              {setMateriality.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Account comments ("explain a variance" without a document) ──────────────

function CommentsDialog({
  accountCode,
  fiscalYearId,
  onClose,
}: {
  accountCode: string | null
  fiscalYearId: number | null
  onClose: () => void
}) {
  const canEdit = useAuthStore((s) => s.hasRole(['finance_admin', 'finance_officer']))
  const currentUserId = useAuthStore((s) => s.user?.id)
  const { data: comments, isLoading } = useAccountComments(accountCode, fiscalYearId)
  const addComment = useAddAccountComment()
  const resolveComment = useResolveAccountComment()
  const deleteComment = useDeleteAccountComment()
  const [text, setText] = useState('')

  if (!accountCode) return null

  const submit = () => {
    if (!text.trim() || !fiscalYearId) return
    addComment.mutate(
      { accountCode, fiscal_year_id: fiscalYearId, text: text.trim() },
      {
        onSuccess: () => setText(''),
        onError: (err) => toast({ title: 'Could not add note', description: apiErrorMessage(err), variant: 'destructive' }),
      }
    )
  }

  return (
    <Dialog open={!!accountCode} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>
            Notes on account <span className="font-mono">{accountCode}</span>
          </DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground">
          Explain a variance directly, without attaching a document. Counts the same as a linked document for
          materiality flagging.
        </p>
        {isLoading ? (
          <LoadingSpinner />
        ) : (
          <div className="max-h-[40vh] space-y-1 overflow-y-auto">
            {!comments?.length && (
              <p className="py-4 text-center text-xs text-muted-foreground">No notes yet.</p>
            )}
            {comments?.map((c) => (
              <div key={c.id} className="flex items-start justify-between gap-2 rounded-sm bg-muted/50 px-2 py-1.5">
                <div className="min-w-0">
                  <p className={`text-xs ${c.is_resolved ? 'text-muted-foreground line-through' : ''}`}>{c.text}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {c.created_by_username ?? 'unknown'} · {formatDate(c.created_at)}
                    {c.is_resolved && c.resolved_by_username && ` · resolved by ${c.resolved_by_username}`}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    className="text-[10px] text-primary hover:underline"
                    onClick={() =>
                      resolveComment.mutate({ accountCode, commentId: c.id, resolved: !c.is_resolved })
                    }
                  >
                    {c.is_resolved ? 'reopen' : 'resolve'}
                  </button>
                  {(c.created_by_user_id === currentUserId || canEdit) && (
                    <button
                      className="text-[10px] text-destructive hover:underline"
                      onClick={() => deleteComment.mutate({ accountCode, commentId: c.id })}
                    >
                      delete
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        {canEdit && (
          <div className="flex gap-2">
            <Input
              placeholder="e.g. Variance is the Q3 grant reimbursement, timing only…"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submit()}
            />
            <Button size="sm" disabled={!text.trim() || addComment.isPending} onClick={submit}>
              {addComment.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Add
            </Button>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Data visualization ("beyond CaseWare") ────────────────────────────────────

/**
 * Audit risk map: every account plotted by balance size (x) vs. document support count
 * (y); red = material and unsupported, amber = material with partial support, slate =
 * below materiality. Gives a one-glance view of where audit risk is concentrated,
 * something CaseWare's materiality worksheets don't visualize at all.
 */
function AuditRiskMap({
  groups,
  linkedCounts,
  threshold,
}: {
  groups: LeadsheetGroup[]
  linkedCounts: Map<string, number>
  threshold: number | null
}) {
  const points = useMemo(() => {
    const seen = new Map<string, { acct_fmtd: string; description: string | null; balance: number; docs: number }>()
    for (const g of groups) {
      for (const a of g.accounts) {
        if (seen.has(a.acct_fmtd)) continue
        const balance = Math.abs(Number(a.final))
        if (balance === 0) continue
        seen.set(a.acct_fmtd, {
          acct_fmtd: a.acct_fmtd,
          description: a.description,
          balance,
          docs: linkedCounts.get(a.acct_fmtd) ?? 0,
        })
      }
    }
    return Array.from(seen.values())
  }, [groups, linkedCounts])

  if (!points.length) return null

  const colorOf = (p: { balance: number; docs: number }) => {
    if (threshold === null || p.balance < threshold) return '#94a3b8' // slate — below materiality
    return p.docs === 0 ? '#dc2626' : '#f59e0b' // red: material & unsupported; amber: material, partially supported
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Audit risk map</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-2 text-xs text-muted-foreground">
          Balance size vs. document support. <span className="text-destructive font-medium">Red</span> = material
          balance, zero supporting documents. <span className="font-medium" style={{ color: '#f59e0b' }}>Amber</span> =
          material but only partially supported.
        </p>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="balance"
                name="Balance"
                tickFormatter={compactCurrency}
                tick={{ fontSize: 11 }}
                label={{ value: 'Final balance', position: 'insideBottom', offset: -5, fontSize: 11 }}
              />
              <YAxis
                type="number"
                dataKey="docs"
                name="Documents"
                allowDecimals={false}
                tick={{ fontSize: 11 }}
                width={40}
                label={{ value: 'Linked docs', angle: -90, position: 'insideLeft', fontSize: 11 }}
              />
              <ZAxis range={[60, 60]} />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const p = payload[0].payload as { acct_fmtd: string; description: string | null; balance: number; docs: number }
                  return (
                    <div className="rounded-md border bg-card px-2 py-1 text-xs shadow-sm">
                      <p className="font-medium">{p.acct_fmtd} — {p.description ?? '—'}</p>
                      <p>Balance: {formatCurrency(String(p.balance))}</p>
                      <p>Linked documents: {p.docs}</p>
                    </div>
                  )
                }}
              />
              <Scatter data={points} fill="#94a3b8">
                {points.map((p) => (
                  <Cell key={p.acct_fmtd} fill={colorOf(p)} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}

/** Prior-year vs. final balance, totalled per leadsheet classification. */
function LeadsheetYoyChart({ groups }: { groups: LeadsheetGroup[] }) {
  const data = useMemo(
    () =>
      groups
        .map((g) => ({
          name: g.classification.length > 18 ? `${g.classification.slice(0, 17)}…` : g.classification,
          fullName: g.classification,
          prior: Number(g.totals.prior_year),
          final: Number(g.totals.final),
        }))
        .filter((d) => d.prior !== 0 || d.final !== 0),
    [groups]
  )

  if (!data.length) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Year-over-year by leadsheet</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={50} />
              <YAxis tickFormatter={compactCurrency} tick={{ fontSize: 11 }} width={70} />
              <Tooltip
                formatter={(value: number) => formatCurrency(String(value))}
                labelFormatter={(_, payload) => (payload?.[0]?.payload as { fullName?: string })?.fullName ?? ''}
              />
              <Legend />
              <Bar dataKey="prior" name="Prior year" fill="#94a3b8" />
              <Bar dataKey="final" name="Current year" fill="#2563eb" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}

/** Attach / detach working papers for one account code. */
function LinkPickerDialog({
  accountCode,
  fiscalYearId,
  onClose,
  onPreview,
  onManageRelated,
}: {
  accountCode: string | null
  fiscalYearId: number | null
  onClose: () => void
  onPreview: (doc: WorkingPaper) => void
  onManageRelated: (doc: WorkingPaper) => void
}) {
  const canEdit = useAuthStore((s) => s.hasRole(['finance_admin', 'finance_officer']))
  const { data: documents } = useDocumentsForLinks(fiscalYearId)
  const { data: links, isLoading } = useLinksByAccount(accountCode, fiscalYearId)
  const addLink = useAddAccountLink()
  const removeLink = useRemoveAccountLink()

  const toggle = (doc: WorkingPaper, link?: AccountLink) => {
    if (!fiscalYearId) return
    if (link) {
      removeLink.mutate(
        { documentId: link.working_paper_id, linkId: link.id },
        {
          onSuccess: () => toast({ title: `Unlinked from ${accountCode}` }),
          onError: (err) =>
            toast({ title: 'Could not remove link', description: apiErrorMessage(err), variant: 'destructive' }),
        }
      )
    } else {
      addLink.mutate(
        { documentId: doc.id, account_code: accountCode!, fiscal_year_id: fiscalYearId },
        {
          onSuccess: () => toast({ title: `Linked to ${accountCode}` }),
          onError: (err) =>
            toast({ title: 'Could not link document', description: apiErrorMessage(err), variant: 'destructive' }),
        }
      )
    }
  }

  return (
    <Dialog open={!!accountCode} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            Documents linked to account <span className="font-mono">{accountCode}</span>
          </DialogTitle>
        </DialogHeader>
        {isLoading ? (
          <LoadingSpinner />
        ) : (
          <div className="max-h-[50vh] overflow-y-auto rounded-md border divide-y">
            {(documents ?? []).map((doc) => {
              const link = (links ?? []).find((l) => l.working_paper_id === doc.id)
              return (
                <div key={doc.id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{doc.display_name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {doc.folder_path}
                      {link?.created_by_username ? ` · linked by ${link.created_by_username}` : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    {(doc.file_type === 'pdf' || doc.file_type === 'img') && (
                      <Button size="sm" variant="ghost" onClick={() => onPreview(doc)} title="View">
                        <Eye className="h-4 w-4" />
                      </Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={() => onManageRelated(doc)} title="Related documents">
                      <Link2 className="h-4 w-4" />
                    </Button>
                    {canEdit ? (
                      link ? (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={removeLink.isPending}
                          onClick={() => toggle(doc, link)}
                        >
                          {removeLink.isPending ? (
                            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                          ) : (
                            <Link2Off className="mr-1 h-3.5 w-3.5" />
                          )}
                          Detach
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={addLink.isPending || !fiscalYearId}
                          onClick={() => toggle(doc)}
                        >
                          {addLink.isPending ? (
                            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                          ) : (
                            <Link2 className="mr-1 h-3.5 w-3.5" />
                          )}
                          Attach
                        </Button>
                      )
                    ) : link ? (
                      <Badge variant="success">linked</Badge>
                    ) : (
                      <Badge variant="secondary">—</Badge>
                    )}
                  </div>
                </div>
              )
            })}
            {!documents?.length && (
              <p className="px-3 py-6 text-center text-sm text-muted-foreground">
                No documents for this fiscal year. Upload documents first.
              </p>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function LeadsheetsPage() {
  const canEdit = useAuthStore((s) => s.hasRole(['finance_admin', 'finance_officer']))
  const [selectedFYId, setSelectedFYId] = useState<number | null>(null)
  const [selectedPeriodId, setSelectedPeriodId] = useState<number | null>(null)
  const [scheme, setScheme] = useState('PSAB')
  const [selectedSheet, setSelectedSheet] = useState<string | null>(null)
  const [linkAccountCode, setLinkAccountCode] = useState<string | null>(null)
  const [previewPaper, setPreviewPaper] = useState<WorkingPaper | null>(null)
  const [relatedPaper, setRelatedPaper] = useState<WorkingPaper | null>(null)
  const [materialityOpen, setMaterialityOpen] = useState(false)
  const [commentsAccountCode, setCommentsAccountCode] = useState<string | null>(null)

  const { data: fiscalYears, isLoading: fyLoading } = useFiscalYears()
  const { data: periods, isLoading: periodsLoading } = usePeriods(selectedFYId)
  const { data: schemes } = useMappingSchemes()
  const { data: result, isLoading } = useLeadsheets(selectedPeriodId, scheme)
  const { data: allLinks } = useAllAccountLinks(selectedFYId)
  const { data: allDocuments } = useDocumentsForLinks(selectedFYId)
  const { data: materiality } = useMateriality(selectedFYId)
  const { data: unsupported } = useUnsupportedMaterialAccounts(selectedFYId, selectedPeriodId, scheme)
  const { data: allComments } = useAllAccountComments(selectedFYId)

  // account code -> number of linked documents, for the per-row indicators
  const linkedCounts = useMemo(() => {
    const m = new Map<string, number>()
    for (const l of allLinks ?? []) m.set(l.account_code, (m.get(l.account_code) ?? 0) + 1)
    return m
  }, [allLinks])

  // account code -> number of notes, for the per-row indicators
  const commentCounts = useMemo(() => {
    const m = new Map<string, number>()
    for (const c of allComments ?? []) m.set(c.account_code, (m.get(c.account_code) ?? 0) + 1)
    return m
  }, [allComments])

  // account code -> flag detail, for material balances with no supporting document
  const flaggedAccounts = useMemo(() => {
    const m = new Map<string, UnsupportedMaterialAccount>()
    for (const a of unsupported?.accounts ?? []) m.set(a.acct_fmtd, a)
    return m
  }, [unsupported])

  const currentSheet = result?.leadsheets.find((g) => g.classification === selectedSheet) ?? null
  const period = periods?.find((p) => p.id === selectedPeriodId) ?? null
  const fy = fiscalYears?.find((f) => f.id === selectedFYId) ?? null

  return (
    <div className="space-y-4">
      <PageHeader
        title="Leadsheets"
        description="Working trial balance grouped by mapping classification, with prior-year comparatives. Read-only."
        actions={
          <Button variant="outline" size="sm" onClick={() => setMaterialityOpen(true)} disabled={!selectedFYId}>
            <Target className="mr-2 h-4 w-4" />
            Materiality{materiality ? `: ${formatCurrency(materiality.flagging_threshold)}` : ''}
          </Button>
        }
      />

      <div className="flex flex-wrap gap-3 items-end">
        <div className="space-y-1">
          <Label>Fiscal Year</Label>
          <Select
            value={selectedFYId?.toString() ?? ''}
            onValueChange={(v) => {
              setSelectedFYId(Number(v))
              setSelectedPeriodId(null)
              setSelectedSheet(null)
            }}
          >
            <SelectTrigger className="w-48">
              <SelectValue placeholder="Select fiscal year" />
            </SelectTrigger>
            <SelectContent>
              {fyLoading ? (
                <SelectItem value="loading" disabled>Loading…</SelectItem>
              ) : (
                fiscalYears?.map((f) => (
                  <SelectItem key={f.id} value={f.id.toString()}>{f.label}</SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label>Period</Label>
          <Select
            value={selectedPeriodId?.toString() ?? ''}
            onValueChange={(v) => {
              setSelectedPeriodId(Number(v))
              setSelectedSheet(null)
            }}
            disabled={!selectedFYId}
          >
            <SelectTrigger className="w-48">
              <SelectValue placeholder="Select period" />
            </SelectTrigger>
            <SelectContent>
              {periodsLoading ? (
                <SelectItem value="loading" disabled>Loading…</SelectItem>
              ) : (
                periods?.map((p) => (
                  <SelectItem key={p.id} value={p.id.toString()}>{p.name}</SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label>Mapping scheme</Label>
          <Select value={scheme} onValueChange={(v) => { setScheme(v); setSelectedSheet(null) }}>
            <SelectTrigger className="w-44">
              <SelectValue placeholder="Scheme" />
            </SelectTrigger>
            <SelectContent>
              {(schemes ?? []).map((s) => (
                <SelectItem key={s.id} value={s.name}>{s.name}</SelectItem>
              ))}
              {!schemes?.some((s) => s.name === 'PSAB') && (
                <SelectItem value="PSAB">PSAB</SelectItem>
              )}
            </SelectContent>
          </Select>
        </div>
      </div>

      {!selectedPeriodId ? (
        <div className="rounded-lg border bg-card p-12 text-center">
          <Sheet className="mx-auto h-8 w-8 text-muted-foreground mb-3" />
          <p className="text-sm text-muted-foreground">
            Select a fiscal year and period to view its leadsheets.
          </p>
        </div>
      ) : isLoading ? (
        <LoadingSpinner fullPage />
      ) : !result?.leadsheets.length ? (
        <div className="rounded-lg border bg-card p-12 text-center">
          <p className="text-sm text-muted-foreground">
            No leadsheet data for this period and scheme. Import trial balance data first.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-[280px_1fr]">
          {/* Sheet list */}
          <div className="self-start rounded-lg border bg-card p-2 space-y-0.5">
            <p className="px-2 py-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {result.leadsheets.length} lead sheets
            </p>
            {result.leadsheets.map((g) => (
              <button
                key={g.classification}
                className={`flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
                  selectedSheet === g.classification
                    ? 'bg-primary/10 font-medium text-primary'
                    : 'hover:bg-muted'
                }`}
                onClick={() => setSelectedSheet(g.classification)}
              >
                <span className="truncate">{g.classification}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{g.accounts.length}</span>
              </button>
            ))}
          </div>

          {/* Selected sheet */}
          <div className="space-y-2">
            {currentSheet ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-lg font-semibold">{currentSheet.classification}</h2>
                  {fy && period && (
                    <Badge variant="outline">
                      {fy.label} · {period.name} · scheme {scheme}
                    </Badge>
                  )}
                </div>
                <LeadsheetTable
                  accounts={currentSheet.accounts}
                  totals={currentSheet.totals}
                  fiscalYearId={selectedFYId}
                  linkedCounts={linkedCounts}
                  commentCounts={commentCounts}
                  flaggedAccounts={flaggedAccounts}
                  canEdit={canEdit}
                  onManageLinks={setLinkAccountCode}
                  onManageComments={setCommentsAccountCode}
                />
              </>
            ) : (
              <div className="rounded-lg border bg-card p-12 text-center">
                <p className="text-sm text-muted-foreground">Select a lead sheet on the left to view its accounts.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Insights: materiality coverage + year-over-year, across all leadsheets for the period */}
      {result && result.leadsheets.length > 0 && (
        <div className="space-y-3">
          {materiality && (
            <div
              className={`rounded-md border px-4 py-2 text-sm ${
                flaggedAccounts.size > 0 ? 'border-destructive/40 bg-destructive/5' : 'border-muted bg-muted/30'
              }`}
            >
              {flaggedAccounts.size > 0 ? (
                <span className="flex items-center gap-2 text-destructive">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <span>
                    <strong>{flaggedAccounts.size}</strong> account{flaggedAccounts.size === 1 ? '' : 's'} with a
                    balance over {formatCurrency(materiality.flagging_threshold)} and no supporting document.
                  </span>
                </span>
              ) : (
                <span className="text-muted-foreground">
                  No material accounts are missing supporting documents right now.
                </span>
              )}
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            <AuditRiskMap
              groups={result.leadsheets}
              linkedCounts={linkedCounts}
              threshold={materiality ? Number(materiality.flagging_threshold) : null}
            />
            <LeadsheetYoyChart groups={result.leadsheets} />
          </div>
        </div>
      )}

      <LinkPickerDialog
        accountCode={linkAccountCode}
        fiscalYearId={selectedFYId}
        onClose={() => setLinkAccountCode(null)}
        onPreview={setPreviewPaper}
        onManageRelated={setRelatedPaper}
      />
      <DocumentPreviewDialog document={previewPaper} onClose={() => setPreviewPaper(null)} />
      <RelatedDocumentsDialog
        document={relatedPaper}
        allDocuments={allDocuments ?? []}
        onClose={() => setRelatedPaper(null)}
      />
      <MaterialityDialog
        open={materialityOpen}
        fiscalYearId={selectedFYId}
        onClose={() => setMaterialityOpen(false)}
      />
      <CommentsDialog
        accountCode={commentsAccountCode}
        fiscalYearId={selectedFYId}
        onClose={() => setCommentsAccountCode(null)}
      />
    </div>
  )
}
