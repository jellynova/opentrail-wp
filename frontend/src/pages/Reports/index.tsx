import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Copy,
  Download,
  FileArchive,
  FileText,
  Lock,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Save,
  Trash2,
  Upload,
} from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { ReportView } from '@/components/shared/ReportView'
import { ImportMappingDialog, type CanonicalField } from '@/components/shared/ImportMappingDialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useFiscalYears, usePeriods } from '@/hooks/useFiscalYears'
import {
  useCloneReport,
  useDeleteReport,
  useGenerateReport,
  usePreviewReport,
  useReports,
  useRevertReport,
  useSaveReport,
  useSofiSchedule,
  useValidateDefinition,
  type SofiScheduleType,
} from '@/hooks/useReports'
import { useRollForwardTca, useSaveTcaLines, useTcaLines, useTcaSchedule, type TcaLayout } from '@/hooks/useTca'
import { apiErrorMessage, cn, formatAmount } from '@/lib/utils'
import { downloadFile } from '@/lib/download'
import { useAuthStore } from '@/store/auth'
import { toast } from '@/hooks/useToast'
import type { Report, ReportOutput, TcaLine, TcaLineInput } from '@/types'

const FINANCE = ['finance_admin', 'finance_officer']

const BLANK_DEFINITION = {
  version: 2,
  title: 'New report',
  subtitle: 'For the year ended {period_end}',
  scheme: 'PSAB',
  columns: [
    { key: 'cy', label: '{fiscal_year}', source: 'actual' },
    { key: 'py', label: '{prior_fiscal_year}', source: 'actual', year_offset: -1 },
  ],
  rows: [
    {
      id: 'rev',
      type: 'section',
      label: 'Revenue',
      total_label: 'Total revenue',
      children: [{ type: 'accounts', label: 'Revenue', classifications: ['revenue*'], sign: -1, show_detail: true }],
    },
  ],
}

function onError(title: string) {
  return (err: unknown) => toast({ title, description: apiErrorMessage(err), variant: 'destructive' })
}

/** Fiscal year + optional period picker shared by the tabs. */
function PeriodPicker({
  fiscalYearId,
  periodId,
  onChange,
  requirePeriod = false,
}: {
  fiscalYearId: number | null
  periodId: number | null
  onChange: (fy: number | null, period: number | null) => void
  requirePeriod?: boolean
}) {
  const { data: fiscalYears } = useFiscalYears()
  const { data: periods } = usePeriods(fiscalYearId)
  return (
    <div className="flex flex-wrap gap-3">
      <div className="space-y-1">
        <label className="text-xs font-medium text-muted-foreground">Fiscal year</label>
        <Select value={fiscalYearId?.toString() ?? ''} onValueChange={(v) => onChange(Number(v), null)}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Select year" />
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
        <label className="text-xs font-medium text-muted-foreground">Through period</label>
        <Select
          value={periodId?.toString() ?? (requirePeriod ? '' : 'ye')}
          onValueChange={(v) => onChange(fiscalYearId, v === 'ye' ? null : Number(v))}
          disabled={!fiscalYearId}
        >
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Select period" />
          </SelectTrigger>
          <SelectContent>
            {!requirePeriod && <SelectItem value="ye">Year end</SelectItem>}
            {periods?.map((p) => (
              <SelectItem key={p.id} value={p.id.toString()}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Statements & saved reports
// ---------------------------------------------------------------------------

function ReportCard({ report, onOpen, onEdit }: { report: Report; onOpen: () => void; onEdit: () => void }) {
  const { hasRole } = useAuthStore()
  const clone = useCloneReport()
  const remove = useDeleteReport()
  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-start justify-between gap-2 text-sm">
          <span>{report.name}</span>
          {report.is_protected && <Lock className="h-4 w-4 shrink-0 text-muted-foreground" aria-label="Protected template" />}
        </CardTitle>
        {report.description && <CardDescription className="text-xs">{report.description}</CardDescription>}
      </CardHeader>
      <CardContent className="mt-auto flex flex-wrap gap-2">
        <Button size="sm" onClick={onOpen}>
          <Play className="mr-1 h-3 w-3" /> Open
        </Button>
        {hasRole(FINANCE) && (
          <Button
            size="sm"
            variant="outline"
            disabled={clone.isPending}
            onClick={() =>
              clone.mutate(report.id, {
                onSuccess: (c) => toast({ title: `Created “${c.name}”`, description: 'Edit it under Saved reports.' }),
                onError: onError('Clone failed'),
              })
            }
          >
            <Copy className="mr-1 h-3 w-3" /> {report.is_protected ? 'Customize' : 'Duplicate'}
          </Button>
        )}
        {!report.is_protected && hasRole(FINANCE) && (
          <>
            <Button size="sm" variant="outline" onClick={onEdit}>
              Edit
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8"
              aria-label="Delete report"
              onClick={() => {
                if (window.confirm(`Delete “${report.name}”?`)) remove.mutate(report.id, { onError: onError('Delete failed') })
              }}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function ReportRunner({ report, onBack }: { report: Report; onBack: () => void }) {
  const [fy, setFy] = useState<number | null>(null)
  const [period, setPeriod] = useState<number | null>(null)
  const generate = useGenerateReport()
  const body = { fiscal_year_id: fy ?? 0, period_id: period ?? undefined }

  const exportAs = (fmt: 'pdf' | 'excel') =>
    downloadFile(`/v1/reports/${report.id}/export/${fmt}`, `${report.name}.${fmt === 'pdf' ? 'pdf' : 'xlsx'}`, {
      method: 'post',
      data: body,
    }).catch(onError('Export failed'))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Button variant="outline" size="sm" onClick={onBack}>
          ← All reports
        </Button>
        <PeriodPicker fiscalYearId={fy} periodId={period} onChange={(f, p) => { setFy(f); setPeriod(p) }} />
        <Button
          size="sm"
          disabled={!fy || generate.isPending}
          onClick={() => generate.mutate({ id: report.id, ...body }, { onError: onError('Could not generate report') })}
        >
          <Play className="mr-2 h-4 w-4" /> Generate
        </Button>
        <Button size="sm" variant="outline" disabled={!fy} onClick={() => void exportAs('pdf')}>
          <Download className="mr-2 h-4 w-4" /> PDF
        </Button>
        <Button size="sm" variant="outline" disabled={!fy} onClick={() => void exportAs('excel')}>
          <Download className="mr-2 h-4 w-4" /> Excel
        </Button>
      </div>
      <h2 className="text-lg font-semibold">{report.name}</h2>
      {generate.isPending ? <LoadingSpinner fullPage /> : generate.data && <ReportView report={generate.data} />}
    </div>
  )
}

function ReportEditor({ report, onBack }: { report: Report | null; onBack: () => void }) {
  const [name, setName] = useState(report?.name ?? 'New report')
  const [text, setText] = useState(JSON.stringify(report?.definition ?? BLANK_DEFINITION, null, 2))
  const [fy, setFy] = useState<number | null>(null)
  const [period, setPeriod] = useState<number | null>(null)
  const [problems, setProblems] = useState<string[]>([])
  const [preview, setPreview] = useState<ReportOutput | null>(null)
  const validate = useValidateDefinition()
  const previewMutation = usePreviewReport()
  const save = useSaveReport()
  const revert = useRevertReport()

  const parsed = useMemo(() => {
    try {
      return { definition: JSON.parse(text) as Record<string, unknown>, error: null }
    } catch (e) {
      return { definition: null, error: (e as Error).message }
    }
  }, [text])

  const check = (then?: (definition: Record<string, unknown>) => void) => {
    if (!parsed.definition) return setProblems([`Invalid JSON: ${parsed.error}`])
    validate.mutate(parsed.definition, {
      onSuccess: (r) => {
        setProblems(r.problems)
        if (r.valid && then) then(parsed.definition!)
      },
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <Button variant="outline" size="sm" onClick={onBack}>
          ← All reports
        </Button>
        <div className="space-y-1">
          <Label>Name</Label>
          <Input className="w-80" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <Button
          size="sm"
          disabled={save.isPending}
          onClick={() =>
            check((definition) =>
              save.mutate(
                {
                  id: report?.id,
                  name,
                  report_type: String(definition.report_type ?? report?.report_type ?? 'custom'),
                  definition,
                },
                { onSuccess: () => toast({ title: 'Report saved' }), onError: onError('Save failed') }
              )
            )
          }
        >
          <Save className="mr-2 h-4 w-4" /> Save
        </Button>
        {!!report?.definition?.source_template_key && (
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              window.confirm('Replace this report with the current standard layout?') &&
              revert.mutate(report.id, {
                onSuccess: (r) => {
                  setText(JSON.stringify(r.definition, null, 2))
                  toast({ title: 'Reverted to the standard layout' })
                },
                onError: onError('Revert failed'),
              })
            }
          >
            <RotateCcw className="mr-2 h-4 w-4" /> Revert to standard
          </Button>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>Definition (JSON)</Label>
            <Button size="sm" variant="ghost" onClick={() => check()}>
              Validate
            </Button>
          </div>
          <Textarea
            className="h-[60vh] font-mono text-xs"
            spellCheck={false}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          {problems.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-xs text-destructive">
              {problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          ) : (
            validate.data?.valid && <p className="text-xs text-green-700">Definition is valid.</p>
          )}
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer">Row and column reference</summary>
            <div className="mt-2 space-y-1">
              <p><b>section / group</b>: label, children, total_label. <b>accounts</b>: classifications (e.g. "revenue.taxation", "liabilities*"), accounts (code globs like "6-1*"), sign (-1 for credit lines), measure (closing | opening | movement), show_detail.</p>
              <p><b>formula</b>: formula over row ids ("fa - li"; functions abs, min, max, round, pct). <b>manual</b>: values per column. <b>text</b>: label with tokens {'{fiscal_year}'}, {'{period_end}'}, {'{organization}'}, {'{row:ID:COL}'}.</p>
              <p><b>columns</b>: source actual (year_offset), budget (budget_version original | amended) or formula ("cy - bud").</p>
            </div>
          </details>
        </div>
        <div className="space-y-2">
          <div className="flex flex-wrap items-end gap-3">
            <PeriodPicker fiscalYearId={fy} periodId={period} onChange={(f, p) => { setFy(f); setPeriod(p) }} />
            <Button
              size="sm"
              variant="outline"
              disabled={!fy || previewMutation.isPending}
              onClick={() =>
                check((definition) =>
                  previewMutation.mutate(
                    { definition, fiscal_year_id: fy!, period_id: period ?? undefined },
                    { onSuccess: setPreview, onError: onError('Preview failed') }
                  )
                )
              }
            >
              <Play className="mr-2 h-4 w-4" /> Preview
            </Button>
          </div>
          {preview ? (
            <ReportView report={preview} />
          ) : (
            <div className="rounded-md border p-12 text-center text-sm text-muted-foreground">
              Choose a fiscal year and preview to see the report.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function StatementsTab() {
  const { hasRole } = useAuthStore()
  const { data: reports, isLoading } = useReports()
  const [running, setRunning] = useState<Report | null>(null)
  const [editing, setEditing] = useState<Report | 'new' | null>(null)

  if (running) return <ReportRunner report={running} onBack={() => setRunning(null)} />
  if (editing) return <ReportEditor report={editing === 'new' ? null : editing} onBack={() => setEditing(null)} />
  if (isLoading) return <LoadingSpinner fullPage />

  // conventional statement order, then anything else alphabetically
  const ORDER = ['sfp', 'so', 'scnfa', 'scf', 'notes']
  const rank = (r: Report) => {
    const i = ORDER.indexOf(r.report_type.split('_').slice(1).join('_'))
    return i === -1 ? ORDER.length : i
  }
  const sorted = [...(reports ?? [])].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name))
  const groups: { title: string; items: Report[] }[] = [
    { title: 'PSAB financial statements', items: sorted.filter((r) => r.is_template && r.report_type.startsWith('psab')) },
    { title: 'LGDE / SOFI statements', items: sorted.filter((r) => r.is_template && r.report_type.startsWith('lgde')) },
    { title: 'Saved reports', items: sorted.filter((r) => !r.is_template) },
  ]

  return (
    <div className="space-y-6">
      {hasRole(FINANCE) && (
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setEditing('new')}>
            <Plus className="mr-2 h-4 w-4" /> New report
          </Button>
        </div>
      )}
      {groups.map((g) => (
        <section key={g.title} className="space-y-2">
          <h3 className="text-sm font-semibold">
            {g.title} <Badge variant="secondary">{g.items.length}</Badge>
          </h3>
          {g.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {g.title === 'Saved reports'
                ? 'Customize a built-in statement or create a new report to see it here.'
                : 'No templates installed.'}
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {g.items.map((r) => (
                <ReportCard key={r.id} report={r} onOpen={() => setRunning(r)} onEdit={() => setEditing(r)} />
              ))}
            </div>
          )}
        </section>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Working papers
// ---------------------------------------------------------------------------

const WORKING_PAPERS = [
  { key: 'trial-balance', name: 'Working trial balance', description: 'Opening → unadjusted → AJEs → RJEs → final, per account.' },
  { key: 'leadsheets', name: 'Leadsheets', description: 'Working trial balance grouped by PSAB classification, with prior year.' },
  { key: 'aje', name: 'Adjusting entries schedule', description: 'All posted adjusting journal entries for the year.' },
  { key: 'rje', name: 'Reclassification schedule', description: 'All posted reclassifying entries for the year.' },
] as const

function WorkingPapersTab() {
  const [fy, setFy] = useState<number | null>(null)
  const [period, setPeriod] = useState<number | null>(null)

  const download = (key: (typeof WORKING_PAPERS)[number]['key'], format: 'xlsx' | 'pdf') => {
    const isSchedule = key === 'aje' || key === 'rje'
    const url = `/v1/working-papers/${isSchedule ? 'je-schedule' : key}`
    const params = isSchedule
      ? { fiscal_year_id: fy, entry_type: key === 'aje' ? 'adjusting' : 'reclassifying', format }
      : { period_id: period, format }
    void downloadFile(url, `${key}.${format}`, { params }).catch(onError('Export failed'))
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <PeriodPicker fiscalYearId={fy} periodId={period} onChange={(f, p) => { setFy(f); setPeriod(p) }} requirePeriod />
        <Button
          size="sm"
          disabled={!period}
          onClick={() =>
            void downloadFile('/v1/working-papers/package', 'working_papers.zip', { params: { period_id: period } }).catch(
              onError('Package failed')
            )
          }
        >
          <FileArchive className="mr-2 h-4 w-4" /> Download package (ZIP)
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {WORKING_PAPERS.map((wp) => {
          const ready = wp.key === 'aje' || wp.key === 'rje' ? !!fy : !!period
          return (
            <Card key={wp.key}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <FileText className="h-4 w-4" /> {wp.name}
                </CardTitle>
                <CardDescription className="text-xs">{wp.description}</CardDescription>
              </CardHeader>
              <CardContent className="flex gap-2">
                <Button size="sm" variant="outline" disabled={!ready} onClick={() => download(wp.key, 'xlsx')}>
                  <Download className="mr-1 h-3 w-3" /> Excel
                </Button>
                <Button size="sm" variant="outline" disabled={!ready} onClick={() => download(wp.key, 'pdf')}>
                  <Download className="mr-1 h-3 w-3" /> PDF
                </Button>
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SOFI schedules
// ---------------------------------------------------------------------------

const SOFI: { type: SofiScheduleType; name: string; hint: string }[] = [
  { type: 'supplier_payment', name: 'Supplier payments', hint: 'Columns: Supplier (or Vendor Name), Amount — CSV, Excel, QuickBooks or Sage export' },
  { type: 'employee_remuneration', name: 'Employee remuneration & expenses', hint: 'Columns: Employee, Position, Remuneration, Expenses, Elected (Y/N) — CSV, Excel, QuickBooks or Sage export' },
  { type: 'guarantee_indemnity', name: 'Guarantees & indemnities', hint: 'Columns: Agreement, Amount, Description — CSV, Excel, QuickBooks or Sage export' },
]

const SOFI_FIELDS: CanonicalField[] = [
  { key: 'name', label: 'Name (supplier / employee / agreement)', required: true },
  { key: 'amount', label: 'Amount' },
  { key: 'expenses', label: 'Expenses' },
  { key: 'position', label: 'Position' },
  { key: 'description', label: 'Description' },
  { key: 'is_elected_official', label: 'Elected official (Y/N)' },
]

function SofiSchedule({ type, hint, fiscalYearId }: { type: SofiScheduleType; hint: string; fiscalYearId: number }) {
  const { hasRole } = useAuthStore()
  const { data, isLoading } = useSofiSchedule(type, fiscalYearId)
  const [mappingOpen, setMappingOpen] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const queryClient = useQueryClient()

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {hasRole(FINANCE) && (
          <label className="inline-flex cursor-pointer items-center rounded-md border px-3 py-1.5 text-sm hover:bg-muted">
            <Upload className="mr-2 h-4 w-4" /> Import file (replaces year)
            <input
              type="file"
              accept=".csv,.xlsx,.xls,.txt,.iif"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                e.target.value = ''
                if (file) {
                  setImportFile(file)
                  setMappingOpen(true)
                }
              }}
            />
          </label>
        )}
        <span className="text-xs text-muted-foreground">{hint}</span>
        <div className="flex-1" />
        {(['xlsx', 'pdf'] as const).map((format) => (
          <Button
            key={format}
            size="sm"
            variant="outline"
            onClick={() =>
              void downloadFile(`/v1/sofi/schedules/${type}`, `${type}.${format}`, {
                params: { fiscal_year_id: fiscalYearId, format },
              }).catch(onError('Export failed'))
            }
          >
            <Download className="mr-1 h-3 w-3" /> {format === 'xlsx' ? 'Excel' : 'PDF'}
          </Button>
        ))}
      </div>
      {isLoading ? <LoadingSpinner fullPage /> : data && <ReportView report={data} />}

      <ImportMappingDialog
        open={mappingOpen}
        onOpenChange={(open) => { if (!open) { setMappingOpen(false); setImportFile(null) } }}
        importKind="sofi"
        fields={SOFI_FIELDS}
        file={importFile}
        fiscalYearId={fiscalYearId}
        importParams={{ fiscal_year_id: fiscalYearId, schedule_type: type, replace: true }}
        importPath="/v1/sofi/entries/import"
        title="Import SOFI schedule"
        onImportSuccess={() => void queryClient.invalidateQueries({ queryKey: ['sofi'] })}
        onImported={(result) => {
          const r = result as { records_imported?: number; errors?: string[] }
          if ((r.records_imported ?? 0) === 0) {
            toast({
              title: 'Could not read the file',
              description: r.errors?.length ? r.errors.slice(0, 3).join('; ') : 'No rows were recognised — check the header row and mapping.',
              variant: 'destructive',
            })
          } else {
            toast({
              title: `Imported ${r.records_imported} rows`,
              description: r.errors?.length ? r.errors.slice(0, 3).join('; ') : undefined,
              variant: r.errors?.length ? 'destructive' : undefined,
            })
          }
        }}
      />
    </div>
  )
}

function SofiTab() {
  const { data: fiscalYears } = useFiscalYears()
  const [fy, setFy] = useState<number | null>(null)
  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <label className="text-xs font-medium text-muted-foreground">Fiscal year</label>
        <Select value={fy?.toString() ?? ''} onValueChange={(v) => setFy(Number(v))}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Select year" />
          </SelectTrigger>
          <SelectContent>
            {fiscalYears?.map((y) => (
              <SelectItem key={y.id} value={y.id.toString()}>
                {y.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {fy && (
        <Tabs defaultValue="supplier_payment">
          <TabsList>
            {SOFI.map((s) => (
              <TabsTrigger key={s.type} value={s.type}>
                {s.name}
              </TabsTrigger>
            ))}
          </TabsList>
          {SOFI.map((s) => (
            <TabsContent key={s.type} value={s.type} className="mt-4">
              <SofiSchedule type={s.type} hint={s.hint} fiscalYearId={fy} />
            </TabsContent>
          ))}
        </Tabs>
      )}
    </div>
  )
}

const TCA_FIELDS = [
  { key: 'cost_opening', label: 'Cost — opening' },
  { key: 'cost_additions', label: 'Additions' },
  { key: 'cost_disposals', label: 'Disposals' },
  { key: 'amort_opening', label: 'Accum. amort. — opening' },
  { key: 'amort_expense', label: 'Amortization' },
  { key: 'amort_disposals', label: 'Amort. disposals' },
] as const

const TCA_MAPPING_FIELDS: CanonicalField[] = [
  { key: 'asset_class', label: 'Asset class', required: true },
  { key: 'cost_opening', label: 'Cost — opening' },
  { key: 'cost_additions', label: 'Additions' },
  { key: 'cost_disposals', label: 'Disposals' },
  { key: 'amort_opening', label: 'Accum. amort. — opening' },
  { key: 'amort_expense', label: 'Amortization' },
  { key: 'amort_disposals', label: 'Amort. disposals' },
  { key: 'notes', label: 'Notes' },
]

const EMPTY_TCA_LINE: TcaLineInput = {
  asset_class: '',
  cost_opening: '0',
  cost_additions: '0',
  cost_disposals: '0',
  amort_opening: '0',
  amort_expense: '0',
  amort_disposals: '0',
}

/** Manual entry for the continuity schedule (CSV import is the usual path). */
function TcaEditor({
  fiscalYearId,
  lines,
  onClose,
}: {
  fiscalYearId: number
  lines: TcaLine[]
  onClose: () => void
}) {
  const [rows, setRows] = useState<TcaLineInput[]>(
    lines.length
      ? lines.map((l) => ({
          asset_class: l.asset_class,
          cost_opening: l.cost_opening,
          cost_additions: l.cost_additions,
          cost_disposals: l.cost_disposals,
          amort_opening: l.amort_opening,
          amort_expense: l.amort_expense,
          amort_disposals: l.amort_disposals,
        }))
      : [{ ...EMPTY_TCA_LINE }]
  )
  const save = useSaveTcaLines(fiscalYearId)

  const update = (index: number, patch: Partial<TcaLineInput>) =>
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)))

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        One row per asset class. Closing cost, closing accumulated amortization and net book value are
        calculated. Negative additions/disposals are allowed; use the Disposals columns for retirements.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="py-1 pr-2">Asset class</th>
              {TCA_FIELDS.map((f) => (
                <th key={f.key} className="py-1 pr-2 text-right">
                  {f.label}
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-b last:border-0">
                <td className="py-1 pr-2">
                  <Input
                    className="h-8 min-w-40"
                    value={row.asset_class}
                    placeholder="Buildings"
                    onChange={(e) => update(index, { asset_class: e.target.value })}
                  />
                </td>
                {TCA_FIELDS.map((f) => (
                  <td key={f.key} className="py-1 pr-2">
                    <Input
                      className="h-8 w-28 text-right"
                      inputMode="decimal"
                      value={row[f.key]}
                      onChange={(e) => update(index, { [f.key]: e.target.value })}
                    />
                  </td>
                ))}
                <td>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8"
                    title="Remove row"
                    onClick={() => setRows((current) => current.filter((_, i) => i !== index))}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={() => setRows((current) => [...current, { ...EMPTY_TCA_LINE }])}>
          <Plus className="mr-1 h-4 w-4" /> Add asset class
        </Button>
        <div className="flex-1" />
        <Button variant="ghost" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button
          size="sm"
          disabled={save.isPending}
          onClick={() => {
            const cleaned = rows.filter((r) => r.asset_class.trim())
            if (cleaned.length !== rows.length) {
              toast({ title: 'Every row needs an asset class', variant: 'destructive' })
              return
            }
            save.mutate(cleaned, {
              onSuccess: (r) => {
                toast({ title: `Saved ${r.lines_saved} asset classes` })
                onClose()
              },
              onError: onError('Could not save the schedule'),
            })
          }}
        >
          <Save className="mr-1 h-4 w-4" /> Save schedule
        </Button>
      </div>
    </div>
  )
}

function TcaTab() {
  const { hasRole } = useAuthStore()
  const { data: fiscalYears } = useFiscalYears()
  const [fy, setFy] = useState<number | null>(null)
  const [layout, setLayout] = useState<TcaLayout>('continuity')
  const [editing, setEditing] = useState(false)
  const [mappingOpen, setMappingOpen] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const { data: lines } = useTcaLines(fy)
  const { data: schedule, isLoading } = useTcaSchedule(fy, layout)
  const rollForward = useRollForwardTca(fy)
  const queryClient = useQueryClient()
  const year = fiscalYears?.find((y) => y.id === fy)
  const readOnly = year?.status === 'locked'
  const rec = schedule?.reconciliation

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Fiscal year</label>
          <Select value={fy?.toString() ?? ''} onValueChange={(v) => setFy(Number(v))}>
            <SelectTrigger className="w-40">
              <SelectValue placeholder="Select year" />
            </SelectTrigger>
            <SelectContent>
              {fiscalYears?.map((y) => (
                <SelectItem key={y.id} value={y.id.toString()}>
                  {y.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Layout</label>
          <Select value={layout} onValueChange={(v) => setLayout(v as TcaLayout)}>
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="continuity">Cost &amp; amortization continuity</SelectItem>
              <SelectItem value="summary">Closing figures only</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {hasRole(FINANCE) && fy && !readOnly && (
          <>
            <label className="inline-flex cursor-pointer items-center rounded-md border px-3 py-2 text-sm hover:bg-muted">
              <Upload className="mr-2 h-4 w-4" /> Import file (replaces year)
              <input
                type="file"
                accept=".csv,.xlsx,.xls,.txt,.iif"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  e.target.value = ''
                  if (file) {
                    setImportFile(file)
                    setMappingOpen(true)
                  }
                }}
              />
            </label>
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              <Pencil className="mr-1 h-4 w-4" /> Edit schedule
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={rollForward.isPending}
              onClick={() =>
                rollForward.mutate(undefined, {
                  onSuccess: (r) =>
                    toast({
                      title: r.applied
                        ? `Carried ${r.prior_year} closing balances into this year`
                        : 'Nothing carried forward',
                      description: r.warnings.length ? r.warnings.join('; ') : undefined,
                      variant: r.warnings.length ? 'destructive' : undefined,
                    }),
                  onError: onError('Roll forward failed'),
                })
              }
            >
              <RotateCcw className="mr-1 h-4 w-4" /> Carry forward openings
            </Button>
          </>
        )}
        <div className="flex-1" />
        {fy &&
          (['xlsx', 'pdf'] as const).map((format) => (
            <Button
              key={format}
              size="sm"
              variant="outline"
              onClick={() =>
                void downloadFile(`/v1/tca/schedule`, `TCA_${year?.label ?? ''}.${format}`, {
                  params: { fiscal_year_id: fy, layout, format },
                }).catch(onError('Export failed'))
              }
            >
              <Download className="mr-1 h-3 w-3" /> {format === 'xlsx' ? 'Excel' : 'PDF'}
            </Button>
          ))}
      </div>

      {fy && rec?.available && (
        <div
          className={cn(
            'rounded-md border p-3 text-sm',
            rec.agrees
              ? 'border-green-300 bg-green-50 text-green-900'
              : 'border-yellow-300 bg-yellow-50 text-yellow-900'
          )}
        >
          {rec.agrees ? (
            <span>
              Ties to the GL: cost {formatAmount(Number(rec.gl_cost))}, accumulated amortization{' '}
              {formatAmount(Number(rec.gl_accumulated_amortization))}.
            </span>
          ) : (
            <span className="flex gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                Does not agree with the GL accounts classified as TCA cost / accumulated amortization:
                cost differs by {formatAmount(Number(rec.cost_difference))}, accumulated amortization by{' '}
                {formatAmount(Number(rec.amortization_difference))}. The schedule total may include assets
                under construction, or the GL may carry an adjustment not yet in the register.
              </span>
            </span>
          )}
        </div>
      )}
      {fy && rec && !rec.available && (
        <p className="text-xs text-muted-foreground">
          No accounts are classified as TCA cost / accumulated amortization in the PSAB scheme, so the
          schedule cannot be reconciled to the GL yet.
        </p>
      )}

      {!fy ? (
        <p className="text-sm text-muted-foreground">Select a fiscal year to view its schedule.</p>
      ) : isLoading ? (
        <LoadingSpinner fullPage />
      ) : schedule && schedule.line_count === 0 ? (
        <div className="rounded-lg border bg-card p-10 text-center">
          <p className="text-sm text-muted-foreground">
            No tangible capital asset schedule for this year yet. Import the asset register as CSV, or add
            the asset classes manually.
          </p>
        </div>
      ) : (
        schedule && <ReportView report={schedule} />
      )}

      {editing && fy && (
        <Dialog open onOpenChange={(open) => !open && setEditing(false)}>
          <DialogContent className="max-w-5xl">
            <DialogHeader>
              <DialogTitle>Tangible capital asset schedule — {year?.label}</DialogTitle>
            </DialogHeader>
            <TcaEditor fiscalYearId={fy} lines={lines ?? []} onClose={() => setEditing(false)} />
          </DialogContent>
        </Dialog>
      )}

      <ImportMappingDialog
        open={mappingOpen}
        onOpenChange={(open) => { if (!open) { setMappingOpen(false); setImportFile(null) } }}
        importKind="tca"
        fields={TCA_MAPPING_FIELDS}
        file={importFile}
        fiscalYearId={fy}
        importParams={{ fiscal_year_id: fy ?? undefined, replace: true }}
        importPath="/v1/tca/lines/import"
        title="Import tangible capital asset schedule"
        onImportSuccess={() => {
          void queryClient.invalidateQueries({ queryKey: ['tca', fy] })
        }}
        onImported={(result) => {
          const r = result as { records_imported?: number; errors?: string[] }
          if ((r.records_imported ?? 0) === 0) {
            toast({
              title: 'Could not read the file',
              description: r.errors?.length ? r.errors.slice(0, 3).join('; ') : 'No asset classes were recognised — check the header row and mapping.',
              variant: 'destructive',
            })
          } else {
            toast({
              title: `Imported ${r.records_imported} asset classes`,
              description: r.errors?.length ? r.errors.slice(0, 3).join('; ') : undefined,
              variant: r.errors?.length ? 'destructive' : undefined,
            })
          }
        }}
      />
    </div>
  )
}

export function ReportsPage() {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Reports"
        description="PSAB and LGDE financial statements, custom reports, working papers, SOFI schedules and the tangible capital asset schedule"
      />
      <Tabs defaultValue="statements">
        <TabsList>
          <TabsTrigger value="statements">Statements &amp; reports</TabsTrigger>
          <TabsTrigger value="working-papers">Working papers</TabsTrigger>
          <TabsTrigger value="sofi">SOFI schedules</TabsTrigger>
          <TabsTrigger value="tca">Tangible capital assets</TabsTrigger>
        </TabsList>
        <TabsContent value="statements" className="mt-4">
          <StatementsTab />
        </TabsContent>
        <TabsContent value="working-papers" className="mt-4">
          <WorkingPapersTab />
        </TabsContent>
        <TabsContent value="sofi" className="mt-4">
          <SofiTab />
        </TabsContent>
        <TabsContent value="tca" className="mt-4">
          <TcaTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
