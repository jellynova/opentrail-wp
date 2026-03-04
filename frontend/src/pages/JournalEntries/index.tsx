import { useState } from 'react'
import { Plus, Loader2, ChevronDown, Trash2 } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useFiscalYears, usePeriods } from '@/hooks/useFiscalYears'
import { useAllJournalEntries, useJournalEntry, useCreateJournalEntry, usePostJournalEntry, useApproveJournalEntry } from '@/hooks/useJournalEntries'
import { formatDate, formatCurrency } from '@/lib/utils'
import { useAuthStore } from '@/store/auth'
import { toast } from '@/hooks/useToast'

type EntryType = 'adjusting' | 'reclassifying' | 'elimination' | 'budget_variance'

interface JournalLineForm {
  account_id: string
  debit: string
  credit: string
  description: string
  gl_reference: string
}

const entryTypeOptions: { value: EntryType; label: string }[] = [
  { value: 'adjusting', label: 'Adjusting' },
  { value: 'reclassifying', label: 'Reclassifying' },
  { value: 'elimination', label: 'Elimination' },
  { value: 'budget_variance', label: 'Budget Variance' },
]

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, 'success' | 'info' | 'secondary'> = {
    approved: 'success',
    posted: 'info',
    draft: 'secondary',
  }
  return <Badge variant={variants[status] ?? 'secondary'}>{status}</Badge>
}

function EntryDetailPanel({ entryId, onClose }: { entryId: number; onClose: () => void }) {
  const { data: entry, isLoading } = useJournalEntry(entryId)
  const postMutation = usePostJournalEntry()
  const approveMutation = useApproveJournalEntry()
  const { hasRole } = useAuthStore()

  if (isLoading) return <LoadingSpinner fullPage />
  if (!entry) return null

  const totalDebit = entry.lines?.reduce((s, l) => s + parseFloat(l.debit || '0'), 0) ?? 0
  const totalCredit = entry.lines?.reduce((s, l) => s + parseFloat(l.credit || '0'), 0) ?? 0
  const isBalanced = Math.abs(totalDebit - totalCredit) < 0.005

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div><span className="text-muted-foreground">Reference:</span> {entry.reference ?? '—'}</div>
        <div><span className="text-muted-foreground">Date:</span> {formatDate(entry.entry_date)}</div>
        <div><span className="text-muted-foreground">Type:</span> {entry.entry_type}</div>
        <div><span className="text-muted-foreground">Status:</span> <StatusBadge status={entry.status} /></div>
        {entry.description && (
          <div className="col-span-2"><span className="text-muted-foreground">Description:</span> {entry.description}</div>
        )}
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Account</TableHead>
            <TableHead>Description</TableHead>
            <TableHead className="text-right">Debit</TableHead>
            <TableHead className="text-right">Credit</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {entry.lines?.map((line) => (
            <TableRow key={line.id}>
              <TableCell className="font-mono text-xs">
                {line.account?.acct_fmtd ?? line.account_id}
              </TableCell>
              <TableCell className="text-xs">{line.description ?? '—'}</TableCell>
              <TableCell className="text-right font-mono text-xs">{formatCurrency(line.debit)}</TableCell>
              <TableCell className="text-right font-mono text-xs">{formatCurrency(line.credit)}</TableCell>
            </TableRow>
          ))}
          <TableRow className="font-semibold border-t-2">
            <TableCell colSpan={2}>Total</TableCell>
            <TableCell className="text-right font-mono text-xs">{formatCurrency(totalDebit)}</TableCell>
            <TableCell className="text-right font-mono text-xs">{formatCurrency(totalCredit)}</TableCell>
          </TableRow>
        </TableBody>
      </Table>

      {!isBalanced && (
        <p className="text-xs text-destructive">
          Warning: Entry is not balanced. Difference: {formatCurrency(Math.abs(totalDebit - totalCredit))}
        </p>
      )}

      <div className="flex gap-2 justify-end">
        {entry.status === 'draft' && hasRole(['finance_admin', 'finance_officer']) && (
          <Button
            size="sm"
            onClick={() => {
              postMutation.mutate(entry.id, {
                onSuccess: () => {
                  toast({ title: 'Entry posted' })
                  onClose()
                },
              })
            }}
            disabled={postMutation.isPending}
          >
            {postMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Post Entry
          </Button>
        )}
        {entry.status === 'posted' && hasRole(['finance_admin']) && (
          <Button
            size="sm"
            variant="default"
            onClick={() => {
              approveMutation.mutate(entry.id, {
                onSuccess: () => {
                  toast({ title: 'Entry approved' })
                  onClose()
                },
              })
            }}
            disabled={approveMutation.isPending}
          >
            {approveMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Approve
          </Button>
        )}
      </div>
    </div>
  )
}

function NewEntryDialog({
  open,
  onClose,
  periodId,
}: {
  open: boolean
  onClose: () => void
  periodId: number | null
}) {
  const [entryDate, setEntryDate] = useState(new Date().toISOString().slice(0, 10))
  const [reference, setReference] = useState('')
  const [description, setDescription] = useState('')
  const [entryType, setEntryType] = useState<EntryType>('adjusting')
  const [lines, setLines] = useState<JournalLineForm[]>([
    { account_id: '', debit: '', credit: '', description: '', gl_reference: '' },
    { account_id: '', debit: '', credit: '', description: '', gl_reference: '' },
  ])

  const createMutation = useCreateJournalEntry()

  const totalDebit = lines.reduce((s, l) => s + parseFloat(l.debit || '0'), 0)
  const totalCredit = lines.reduce((s, l) => s + parseFloat(l.credit || '0'), 0)
  const isBalanced = Math.abs(totalDebit - totalCredit) < 0.005

  const addLine = () =>
    setLines((prev) => [
      ...prev,
      { account_id: '', debit: '', credit: '', description: '', gl_reference: '' },
    ])

  const removeLine = (index: number) =>
    setLines((prev) => prev.filter((_, i) => i !== index))

  const updateLine = (index: number, field: keyof JournalLineForm, value: string) =>
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, [field]: value } : l)))

  const handleSave = (postAfter: boolean) => {
    if (!periodId) return
    const validLines = lines.filter((l) => l.account_id)
    if (validLines.length < 2) {
      toast({ title: 'Validation error', description: 'At least 2 lines are required.', variant: 'destructive' })
      return
    }
    createMutation.mutate(
      {
        period_id: periodId,
        entry_date: entryDate,
        reference: reference || undefined,
        description: description || undefined,
        entry_type: entryType,
        lines: validLines.map((l) => ({
          account_id: parseInt(l.account_id),
          debit: l.debit || '0',
          credit: l.credit || '0',
          description: l.description || undefined,
          gl_reference: l.gl_reference || undefined,
        })),
      },
      {
        onSuccess: () => {
          toast({ title: postAfter ? 'Entry created and posted' : 'Entry saved as draft' })
          onClose()
        },
        onError: () => {
          toast({ title: 'Error', description: 'Could not save entry.', variant: 'destructive' })
        },
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New Journal Entry</DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label>Entry Date</Label>
            <Input type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Entry Type</Label>
            <Select value={entryType} onValueChange={(v) => setEntryType(v as EntryType)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {entryTypeOptions.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Reference</Label>
            <Input placeholder="e.g. AJE-001" value={reference} onChange={(e) => setReference(e.target.value)} />
          </div>
          <div className="space-y-1 col-span-2">
            <Label>Description</Label>
            <Textarea
              placeholder="Entry description…"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
        </div>

        {/* Lines */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium">Journal Lines</h3>
            <Button type="button" variant="outline" size="sm" onClick={addLine}>
              <Plus className="mr-1 h-4 w-4" /> Add Line
            </Button>
          </div>

          <div className="rounded-md border overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Account ID</th>
                  <th className="px-3 py-2 text-left font-medium">Description</th>
                  <th className="px-3 py-2 text-right font-medium">Debit</th>
                  <th className="px-3 py-2 text-right font-medium">Credit</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line, i) => (
                  <tr key={i} className="border-t">
                    <td className="px-2 py-1">
                      <Input
                        placeholder="Account ID"
                        value={line.account_id}
                        onChange={(e) => updateLine(i, 'account_id', e.target.value)}
                        className="h-8 w-28"
                        type="number"
                      />
                    </td>
                    <td className="px-2 py-1">
                      <Input
                        placeholder="Description"
                        value={line.description}
                        onChange={(e) => updateLine(i, 'description', e.target.value)}
                        className="h-8"
                      />
                    </td>
                    <td className="px-2 py-1">
                      <Input
                        placeholder="0.00"
                        value={line.debit}
                        onChange={(e) => updateLine(i, 'debit', e.target.value)}
                        className="h-8 w-28 text-right"
                        type="number"
                        min="0"
                        step="0.01"
                      />
                    </td>
                    <td className="px-2 py-1">
                      <Input
                        placeholder="0.00"
                        value={line.credit}
                        onChange={(e) => updateLine(i, 'credit', e.target.value)}
                        className="h-8 w-28 text-right"
                        type="number"
                        min="0"
                        step="0.01"
                      />
                    </td>
                    <td className="px-2 py-1">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground"
                        onClick={() => removeLine(i)}
                        disabled={lines.length <= 2}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="border-t bg-muted/30">
                <tr>
                  <td colSpan={2} className="px-3 py-1 text-right text-xs font-medium text-muted-foreground">
                    Totals
                  </td>
                  <td className="px-3 py-1 text-right font-mono text-xs font-semibold">
                    {formatCurrency(totalDebit)}
                  </td>
                  <td className="px-3 py-1 text-right font-mono text-xs font-semibold">
                    {formatCurrency(totalCredit)}
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>

          {!isBalanced && totalDebit + totalCredit > 0 && (
            <p className="text-xs text-destructive">
              Entry is not balanced. Difference: {formatCurrency(Math.abs(totalDebit - totalCredit))}
            </p>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            variant="secondary"
            onClick={() => handleSave(false)}
            disabled={createMutation.isPending || !isBalanced}
          >
            {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save Draft
          </Button>
          <Button
            onClick={() => handleSave(true)}
            disabled={createMutation.isPending || !isBalanced}
          >
            {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save &amp; Post
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function JournalEntriesPage() {
  const [selectedFYId, setSelectedFYId] = useState<number | null>(null)
  const [selectedPeriodId, setSelectedPeriodId] = useState<number | null>(null)
  const [filterType, setFilterType] = useState<string>('all')
  const [filterStatus, setFilterStatus] = useState<string>('all')
  const [newEntryOpen, setNewEntryOpen] = useState(false)
  const [selectedEntryId, setSelectedEntryId] = useState<number | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const { data: fiscalYears } = useFiscalYears()
  const { data: periods } = usePeriods(selectedFYId)
  const { data: entries, isLoading } = useAllJournalEntries({
    period_id: selectedPeriodId ?? undefined,
    entry_type: filterType !== 'all' ? filterType : undefined,
    status: filterStatus !== 'all' ? filterStatus : undefined,
  })

  const filteredEntries = entries ?? []

  return (
    <div className="space-y-4">
      <PageHeader
        title="Journal Entries"
        description="Create and manage adjusting, reclassifying, and other journal entries"
        actions={
          <Button size="sm" onClick={() => setNewEntryOpen(true)} disabled={!selectedPeriodId}>
            <Plus className="mr-2 h-4 w-4" />
            New Entry
          </Button>
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-end">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Fiscal Year</label>
          <Select
            value={selectedFYId?.toString() ?? ''}
            onValueChange={(v) => { setSelectedFYId(Number(v)); setSelectedPeriodId(null) }}
          >
            <SelectTrigger className="w-44">
              <SelectValue placeholder="All years" />
            </SelectTrigger>
            <SelectContent>
              {fiscalYears?.map((fy) => (
                <SelectItem key={fy.id} value={fy.id.toString()}>{fy.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Period</label>
          <Select
            value={selectedPeriodId?.toString() ?? ''}
            onValueChange={(v) => setSelectedPeriodId(Number(v))}
            disabled={!selectedFYId}
          >
            <SelectTrigger className="w-44">
              <SelectValue placeholder="All periods" />
            </SelectTrigger>
            <SelectContent>
              {periods?.map((p) => (
                <SelectItem key={p.id} value={p.id.toString()}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Entry Type</label>
          <Select value={filterType} onValueChange={setFilterType}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              {entryTypeOptions.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
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
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="draft">Draft</SelectItem>
              <SelectItem value="posted">Posted</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Entries table */}
      {isLoading ? (
        <LoadingSpinner fullPage />
      ) : filteredEntries.length === 0 ? (
        <div className="rounded-lg border bg-card p-12 text-center">
          <p className="text-sm text-muted-foreground">No journal entries found.</p>
        </div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Reference</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Status</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredEntries.map((entry) => (
                <TableRow
                  key={entry.id}
                  className="cursor-pointer"
                  onClick={() => { setSelectedEntryId(entry.id); setDetailOpen(true) }}
                >
                  <TableCell className="font-mono text-xs">
                    {entry.reference ?? `#${entry.id}`}
                  </TableCell>
                  <TableCell>{formatDate(entry.entry_date)}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{entry.entry_type}</Badge>
                  </TableCell>
                  <TableCell className="max-w-[200px] truncate text-sm text-muted-foreground">
                    {entry.description ?? '—'}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={entry.status} />
                  </TableCell>
                  <TableCell>
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* New Entry Dialog */}
      <NewEntryDialog
        open={newEntryOpen}
        onClose={() => setNewEntryOpen(false)}
        periodId={selectedPeriodId}
      />

      {/* Detail Dialog */}
      <Dialog open={detailOpen} onOpenChange={(o) => !o && setDetailOpen(false)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Journal Entry Detail</DialogTitle>
          </DialogHeader>
          {selectedEntryId && (
            <EntryDetailPanel
              entryId={selectedEntryId}
              onClose={() => setDetailOpen(false)}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

