import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, Download, Play, Plus, Lock, LayoutTemplate } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import api from '@/lib/api'
import { formatDate } from '@/lib/utils'
import { useFiscalYears } from '@/hooks/useFiscalYears'
import type { Report } from '@/types'

const builtInTemplates = [
  { id: 'psab-fs', name: 'PSAB Financial Statements', category: 'PSAB', description: 'Statement of financial position, operations, change in net debt, and cash flows.' },
  { id: 'lgde-sched', name: 'LGDE Schedules', category: 'LGDE', description: 'Local Government Data Entry schedules for Ministry reporting.' },
  { id: 'wp-summary', name: 'Working Papers Summary', category: 'Working Papers', description: 'Consolidated working paper binder index and lead schedules.' },
  { id: 'budget-comparison', name: 'Budget vs Actual', category: 'Management', description: 'Departmental budget vs actual variance report.' },
  { id: 'tb-detail', name: 'Trial Balance Detail', category: 'Accounting', description: 'Full trial balance with account details and YTD balances.' },
  { id: 'je-listing', name: 'Journal Entry Listing', category: 'Accounting', description: 'All journal entries for the period with lines.' },
]

function GenerateDialog({
  report,
  onClose,
}: {
  report: { id: string | number; name: string } | null
  onClose: () => void
}) {
  const [selectedFYId, setSelectedFYId] = useState<string>('')
  const [format, setFormat] = useState<'pdf' | 'xlsx'>('pdf')
  const { data: fiscalYears } = useFiscalYears()

  if (!report) return null

  return (
    <Dialog open={!!report} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Generate: {report.name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <label className="text-sm font-medium">Fiscal Year</label>
            <Select value={selectedFYId} onValueChange={setSelectedFYId}>
              <SelectTrigger>
                <SelectValue placeholder="Select fiscal year" />
              </SelectTrigger>
              <SelectContent>
                {fiscalYears?.map((fy) => (
                  <SelectItem key={fy.id} value={fy.id.toString()}>{fy.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium">Export Format</label>
            <Select value={format} onValueChange={(v) => setFormat(v as 'pdf' | 'xlsx')}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="pdf">PDF</SelectItem>
                <SelectItem value="xlsx">Excel (.xlsx)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={!selectedFYId}>
            <Download className="mr-2 h-4 w-4" />
            Generate &amp; Download
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ReportsPage() {
  const [generateTarget, setGenerateTarget] = useState<{ id: string | number; name: string } | null>(null)

  const { data: savedReports, isLoading } = useQuery({
    queryKey: ['reports'],
    queryFn: () => api.get<Report[]>('/v1/reports').then((r) => r.data),
  })

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports"
        description="Generate financial statements, LGDE schedules, and working paper reports"
        actions={
          <Button size="sm">
            <Plus className="mr-2 h-4 w-4" />
            New Report
          </Button>
        }
      />

      <Tabs defaultValue="templates">
        <TabsList>
          <TabsTrigger value="templates">
            <LayoutTemplate className="mr-2 h-4 w-4" />
            Templates
          </TabsTrigger>
          <TabsTrigger value="saved">
            <FileText className="mr-2 h-4 w-4" />
            Saved Reports
          </TabsTrigger>
        </TabsList>

        {/* Built-in Templates */}
        <TabsContent value="templates" className="mt-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {builtInTemplates.map((tpl) => (
              <Card key={tpl.id} className="flex flex-col">
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-sm leading-snug">{tpl.name}</CardTitle>
                    <Badge variant="outline" className="shrink-0 text-xs">{tpl.category}</Badge>
                  </div>
                  <CardDescription className="text-xs">{tpl.description}</CardDescription>
                </CardHeader>
                <CardContent className="mt-auto pt-2 flex gap-2">
                  <Button
                    size="sm"
                    className="flex-1"
                    onClick={() => setGenerateTarget({ id: tpl.id, name: tpl.name })}
                  >
                    <Play className="mr-2 h-3 w-3" />
                    Generate
                  </Button>
                  <Button size="sm" variant="outline">
                    <Download className="h-4 w-4" />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        {/* Saved Reports */}
        <TabsContent value="saved" className="mt-4">
          {isLoading ? (
            <LoadingSpinner fullPage />
          ) : !savedReports?.length ? (
            <div className="rounded-lg border bg-card p-12 text-center">
              <FileText className="mx-auto h-8 w-8 text-muted-foreground mb-3" />
              <p className="text-sm text-muted-foreground">No saved reports yet.</p>
            </div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Fiscal Year</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {savedReports.map((report) => (
                    <TableRow key={report.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {report.is_protected && <Lock className="h-3 w-3 text-muted-foreground" />}
                          <span className="font-medium text-sm">{report.name}</span>
                        </div>
                        {report.description && (
                          <p className="text-xs text-muted-foreground mt-0.5">{report.description}</p>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{report.report_type}</Badge>
                      </TableCell>
                      <TableCell className="text-sm">
                        {report.fiscal_year_id ?? '—'}
                      </TableCell>
                      <TableCell className="text-sm">{formatDate(report.created_at)}</TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setGenerateTarget({ id: report.id, name: report.name })}
                          >
                            <Play className="mr-1 h-3 w-3" />
                            Run
                          </Button>
                          <Button size="sm" variant="ghost">
                            <Download className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>
      </Tabs>

      <GenerateDialog report={generateTarget} onClose={() => setGenerateTarget(null)} />
    </div>
  )
}
