import { useMemo, useState } from 'react'
import { Link2, Link2Off, Loader2, Search, Sheet } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
import { apiErrorMessage, formatCurrency } from '@/lib/utils'
import { toast } from '@/hooks/useToast'
import { useFiscalYears, usePeriods } from '@/hooks/useFiscalYears'
import {
  useAddAccountLink,
  useAllAccountLinks,
  useDocumentsForLinks,
  useLeadsheets,
  useLinksByAccount,
  useMappingSchemes,
  useRemoveAccountLink,
} from '@/hooks/useLeadsheets'
import type { AccountLink, LeadsheetAccount, LeadsheetTotals, WorkingPaper } from '@/types'

/** Read-only viewer for one leadsheet (a PSAB classification group). */
function LeadsheetTable({
  accounts,
  totals,
  fiscalYearId,
  linkedCounts,
  canEdit,
  onManageLinks,
}: {
  accounts: LeadsheetAccount[]
  totals: LeadsheetTotals
  fiscalYearId: number | null
  linkedCounts: Map<string, number>
  canEdit: boolean
  onManageLinks: (accountCode: string) => void
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
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((a) => {
                const linkCount = linkedCounts.get(a.acct_fmtd) ?? 0
                return (
                  <TableRow key={a.account_id}>
                    <TableCell className="font-mono text-xs">{a.acct_fmtd}</TableCell>
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
                  </TableRow>
                )
              })}
              {!rows.length && (
                <TableRow>
                  <TableCell colSpan={9} className="text-center text-sm text-muted-foreground py-8">
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

/** Attach / detach working papers for one account code. */
function LinkPickerDialog({
  accountCode,
  fiscalYearId,
  onClose,
}: {
  accountCode: string | null
  fiscalYearId: number | null
  onClose: () => void
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

  const { data: fiscalYears, isLoading: fyLoading } = useFiscalYears()
  const { data: periods, isLoading: periodsLoading } = usePeriods(selectedFYId)
  const { data: schemes } = useMappingSchemes()
  const { data: result, isLoading } = useLeadsheets(selectedPeriodId, scheme)
  const { data: allLinks } = useAllAccountLinks(selectedFYId)

  // account code -> number of linked documents, for the per-row indicators
  const linkedCounts = useMemo(() => {
    const m = new Map<string, number>()
    for (const l of allLinks ?? []) m.set(l.account_code, (m.get(l.account_code) ?? 0) + 1)
    return m
  }, [allLinks])

  const currentSheet = result?.leadsheets.find((g) => g.classification === selectedSheet) ?? null
  const period = periods?.find((p) => p.id === selectedPeriodId) ?? null
  const fy = fiscalYears?.find((f) => f.id === selectedFYId) ?? null

  return (
    <div className="space-y-4">
      <PageHeader
        title="Leadsheets"
        description="Working trial balance grouped by mapping classification, with prior-year comparatives. Read-only."
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
                  canEdit={canEdit}
                  onManageLinks={setLinkAccountCode}
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

      <LinkPickerDialog
        accountCode={linkAccountCode}
        fiscalYearId={selectedFYId}
        onClose={() => setLinkAccountCode(null)}
      />
    </div>
  )
}
