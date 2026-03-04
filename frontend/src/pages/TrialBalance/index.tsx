import { useState, useRef } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  flexRender,
  type ColumnDef,
  type ColumnFiltersState,
} from '@tanstack/react-table'
import { Download, Upload, RefreshCw, Loader2 } from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useFiscalYears, usePeriods } from '@/hooks/useFiscalYears'
import { useTrialBalance, useImportFromCSV } from '@/hooks/useTrialBalance'
import { formatCurrency, netBalance } from '@/lib/utils'
import type { TrialBalanceEntry } from '@/types'
import { toast } from '@/hooks/useToast'

function NetBalanceCell({ debit, credit }: { debit: string; credit: string }) {
  const net = netBalance(debit, credit)
  return (
    <span className={net < 0 ? 'text-destructive' : net > 0 ? 'text-foreground' : 'text-muted-foreground'}>
      {formatCurrency(net)}
    </span>
  )
}

export function TrialBalancePage() {
  const [selectedFYId, setSelectedFYId] = useState<number | null>(null)
  const [selectedPeriodId, setSelectedPeriodId] = useState<number | null>(null)
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const [globalFilter, setGlobalFilter] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: fiscalYears, isLoading: fyLoading } = useFiscalYears()
  const { data: periods, isLoading: periodsLoading } = usePeriods(selectedFYId)
  const { data: trialBalance, isLoading: tbLoading } = useTrialBalance(selectedPeriodId)
  const importCSV = useImportFromCSV()

  const columns: ColumnDef<TrialBalanceEntry>[] = [
    {
      accessorFn: (row) => row.account?.acct_fmtd ?? row.account_id.toString(),
      id: 'account',
      header: 'Account',
      cell: ({ getValue }) => (
        <span className="font-mono text-xs">{getValue<string>()}</span>
      ),
    },
    {
      accessorFn: (row) => row.account?.description ?? '—',
      id: 'description',
      header: 'Description',
      cell: ({ getValue }) => (
        <span className="max-w-[200px] truncate block">{getValue<string>()}</span>
      ),
    },
    {
      accessorFn: (row) => row.account?.acct_type ?? '—',
      id: 'acct_type',
      header: 'Type',
      cell: ({ getValue }) => <Badge variant="outline">{getValue<string>()}</Badge>,
    },
    {
      accessorFn: (row) => row.account?.dept_code ?? '—',
      id: 'dept_code',
      header: 'Dept',
    },
    {
      accessorFn: (row) => row.account?.fund_code ?? '—',
      id: 'fund_code',
      header: 'Fund',
    },
    {
      accessorKey: 'opening_debit',
      header: 'Open Dr',
      cell: ({ getValue }) => (
        <span className="text-right block font-mono text-xs">
          {formatCurrency(getValue<string>())}
        </span>
      ),
    },
    {
      accessorKey: 'opening_credit',
      header: 'Open Cr',
      cell: ({ getValue }) => (
        <span className="text-right block font-mono text-xs">
          {formatCurrency(getValue<string>())}
        </span>
      ),
    },
    {
      accessorKey: 'period_debit',
      header: 'Period Dr',
      cell: ({ getValue }) => (
        <span className="text-right block font-mono text-xs">
          {formatCurrency(getValue<string>())}
        </span>
      ),
    },
    {
      accessorKey: 'period_credit',
      header: 'Period Cr',
      cell: ({ getValue }) => (
        <span className="text-right block font-mono text-xs">
          {formatCurrency(getValue<string>())}
        </span>
      ),
    },
    {
      accessorKey: 'ytd_debit',
      header: 'YTD Dr',
      cell: ({ getValue }) => (
        <span className="text-right block font-mono text-xs">
          {formatCurrency(getValue<string>())}
        </span>
      ),
    },
    {
      accessorKey: 'ytd_credit',
      header: 'YTD Cr',
      cell: ({ getValue }) => (
        <span className="text-right block font-mono text-xs">
          {formatCurrency(getValue<string>())}
        </span>
      ),
    },
    {
      id: 'net_balance',
      header: 'Net Balance',
      cell: ({ row }) => (
        <NetBalanceCell
          debit={row.original.ytd_debit}
          credit={row.original.ytd_credit}
        />
      ),
    },
  ]

  const table = useReactTable({
    data: trialBalance ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    onColumnFiltersChange: setColumnFilters,
    state: { columnFilters, globalFilter },
    onGlobalFilterChange: setGlobalFilter,
  })

  // Compute totals
  const totals = (trialBalance ?? []).reduce(
    (acc, row) => ({
      opening_debit: acc.opening_debit + parseFloat(row.opening_debit || '0'),
      opening_credit: acc.opening_credit + parseFloat(row.opening_credit || '0'),
      period_debit: acc.period_debit + parseFloat(row.period_debit || '0'),
      period_credit: acc.period_credit + parseFloat(row.period_credit || '0'),
      ytd_debit: acc.ytd_debit + parseFloat(row.ytd_debit || '0'),
      ytd_credit: acc.ytd_credit + parseFloat(row.ytd_credit || '0'),
    }),
    {
      opening_debit: 0,
      opening_credit: 0,
      period_debit: 0,
      period_credit: 0,
      ytd_debit: 0,
      ytd_credit: 0,
    }
  )

  const handleCSVImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !selectedPeriodId) return
    importCSV.mutate(
      { period_id: selectedPeriodId, file },
      {
        onSuccess: (data) => {
          toast({ title: 'Import successful', description: `Imported ${data.imported} records.` })
        },
        onError: () => {
          toast({ title: 'Import failed', description: 'Could not import CSV.', variant: 'destructive' })
        },
      }
    )
    // Reset input
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Trial Balance"
        description="View and import trial balance data by period"
        actions={
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={!selectedPeriodId || importCSV.isPending}
            >
              {importCSV.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Upload className="mr-2 h-4 w-4" />
              )}
              Import CSV
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={handleCSVImport}
            />
            <Button variant="outline" size="sm" disabled={!trialBalance?.length}>
              <Download className="mr-2 h-4 w-4" />
              Export Excel
            </Button>
          </div>
        }
      />

      {/* Period selector */}
      <div className="flex flex-wrap gap-3 items-end">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Fiscal Year</label>
          <Select
            value={selectedFYId?.toString() ?? ''}
            onValueChange={(v) => {
              setSelectedFYId(Number(v))
              setSelectedPeriodId(null)
            }}
          >
            <SelectTrigger className="w-48">
              <SelectValue placeholder="Select fiscal year" />
            </SelectTrigger>
            <SelectContent>
              {fyLoading ? (
                <SelectItem value="loading" disabled>Loading…</SelectItem>
              ) : (
                fiscalYears?.map((fy) => (
                  <SelectItem key={fy.id} value={fy.id.toString()}>
                    {fy.label}
                  </SelectItem>
                ))
              )}
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
            <SelectTrigger className="w-48">
              <SelectValue placeholder="Select period" />
            </SelectTrigger>
            <SelectContent>
              {periodsLoading ? (
                <SelectItem value="loading" disabled>Loading…</SelectItem>
              ) : (
                periods?.map((p) => (
                  <SelectItem key={p.id} value={p.id.toString()}>
                    {p.name}
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Search</label>
          <Input
            placeholder="Filter accounts…"
            value={globalFilter}
            onChange={(e) => setGlobalFilter(e.target.value)}
            className="w-56"
          />
        </div>
      </div>

      {/* Table */}
      {!selectedPeriodId ? (
        <div className="rounded-lg border bg-card p-12 text-center">
          <RefreshCw className="mx-auto h-8 w-8 text-muted-foreground mb-3" />
          <p className="text-sm text-muted-foreground">Select a fiscal year and period to view trial balance data</p>
        </div>
      ) : tbLoading ? (
        <LoadingSpinner fullPage />
      ) : !trialBalance?.length ? (
        <div className="rounded-lg border bg-card p-12 text-center">
          <p className="text-sm text-muted-foreground">No trial balance data for this period. Import data to get started.</p>
        </div>
      ) : (
        <div className="rounded-md border overflow-hidden">
          <div className="overflow-x-auto max-h-[60vh] overflow-y-auto">
            <Table>
              <TableHeader className="sticky top-0 bg-muted/80 backdrop-blur-sm">
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <TableHead key={header.id} className="whitespace-nowrap">
                        {header.isPlaceholder
                          ? null
                          : flexRender(header.column.columnDef.header, header.getContext())}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {table.getRowModel().rows.map((row) => {
                  const ytdNet = netBalance(row.original.ytd_debit, row.original.ytd_credit)
                  return (
                    <TableRow
                      key={row.id}
                      className={ytdNet !== 0 ? 'bg-blue-50/30' : ''}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id} className="py-2">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </TableCell>
                      ))}
                    </TableRow>
                  )
                })}
              </TableBody>
              <TableFooter>
                <TableRow className="font-semibold">
                  <TableCell colSpan={5}>Totals ({table.getRowModel().rows.length} accounts)</TableCell>
                  <TableCell className="text-right font-mono text-xs">{formatCurrency(totals.opening_debit)}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{formatCurrency(totals.opening_credit)}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{formatCurrency(totals.period_debit)}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{formatCurrency(totals.period_credit)}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{formatCurrency(totals.ytd_debit)}</TableCell>
                  <TableCell className="text-right font-mono text-xs">{formatCurrency(totals.ytd_credit)}</TableCell>
                  <TableCell>
                    <NetBalanceCell
                      debit={totals.ytd_debit.toString()}
                      credit={totals.ytd_credit.toString()}
                    />
                  </TableCell>
                </TableRow>
              </TableFooter>
            </Table>
          </div>
        </div>
      )}
    </div>
  )
}
