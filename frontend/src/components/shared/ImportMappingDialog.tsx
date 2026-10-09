/**
 * Caseware-style import mapping dialog.
 *
 * The app never assumes which column holds what: the user picks a file, the
 * dialog previews it raw (/imports/preview) and a dropdown above each column
 * assigns it to a canonical field (or Ignore). Mappings are remembered per
 * client per fiscal year in localStorage and pre-filled from the backend's
 * column guesses on first import.
 */
import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, Minus, Plus, Table2 } from 'lucide-react'
import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { apiErrorMessage } from '@/lib/utils'

/** A canonical field an importer accepts, shown with a friendly label. */
export interface CanonicalField {
  key: string
  label: string
  required?: boolean
}

interface PreviewColumnGuess {
  index: number
  header: string
}

interface ImportPreview {
  file_type: string
  file_name: string
  sheet_names: string[]
  selected_sheet: string | null
  total_rows: number
  rows: string[][]
  header_row: number
  column_guesses: Record<string, PreviewColumnGuess>
}

export type ColumnMap = Record<string, number>
/** Per canonical field: the assigned column index as a string, or '' when ignored. */
export type MappingState = Record<string, string>

const IGNORE = '__ignore__'

/** localStorage key: last-used mapping per import kind per fiscal year. */
export const mappingStorageKey = (importKind: string, fiscalYearId: number | null | undefined) =>
  `opentrail:import-mapping:${importKind}:${fiscalYearId ?? 'none'}`

export function loadSavedMapping(importKind: string, fiscalYearId: number | null | undefined): MappingState | null {
  try {
    const raw = localStorage.getItem(mappingStorageKey(importKind, fiscalYearId))
    const parsed = raw ? (JSON.parse(raw) as MappingState) : null
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

export function saveMapping(importKind: string, fiscalYearId: number | null | undefined, mapping: MappingState) {
  try {
    localStorage.setItem(mappingStorageKey(importKind, fiscalYearId), JSON.stringify(mapping))
  } catch {
    // private mode / quota — remembering the mapping is a nicety, not a requirement
  }
}

function columnLetter(index: number): string {
  let n = index + 1
  const letters: string[] = []
  while (n > 0) {
    const rem = (n - 1) % 26
    letters.unshift(String.fromCharCode(65 + rem))
    n = Math.floor((n - 1) / 26)
  }
  return letters.join('') || '?'
}

function useImportPreview(file: File | null, sheet: string | null, enabled: boolean) {
  return useQuery<ImportPreview, Error>({
    queryKey: ['import-preview', file?.name, file?.size, file?.lastModified, sheet],
    queryFn: async () => {
      const form = new FormData()
      if (file) form.append('file', file)
      const { data } = await api.post<ImportPreview>('/v1/imports/preview', form, {
        params: sheet ? { sheet } : {},
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return data
    },
    enabled,
    retry: false,
  })
}

export interface ImportMappingDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Which importer this is — also the localStorage bucket for saved mappings. */
  importKind: 'trial-balance' | 'budget-lines' | 'tca' | 'sofi'
  fields: CanonicalField[]
  file: File | null
  fiscalYearId: number | null
  /** Extra query params (period_id, schedule_type, replace, …) for the import call. */
  importParams: Record<string, string | number | boolean | undefined>
  /** Import endpoint path, e.g. /v1/tca/lines/import */
  importPath: string
  title: string
  onImported: (result: Record<string, unknown>) => void
  /** Fires after a successful import so the host can invalidate its queries. */
  onImportSuccess?: () => void
}

/** Column dropdown: every field not already taken by another column, plus Ignore. */
function ColumnAssign({
  col, fields, mapping, onAssign,
}: {
  col: number
  fields: CanonicalField[]
  mapping: MappingState
  onAssign: (fieldKey: string, col: number | null) => void
}) {
  const owner = fields.find((f) => mapping[f.key] === String(col))
  const taken = new Set(
    Object.entries(mapping)
      .filter(([key, value]) => value !== '' && fields.some((f) => f.key === key && f.key !== owner?.key))
      .map(([, value]) => value)
  )
  return (
    <Select
      value={owner ? String(col) : IGNORE}
      onValueChange={(v) => {
        if (v === IGNORE) {
          if (owner) onAssign(owner.key, null)
        } else {
          // The user picked a field for this column; if that field was mapped
          // elsewhere it moves here, and any field it displaces is ignored.
          const field = fields.find((f) => f.key === v)
          if (field) onAssign(field.key, col)
        }
      }}
    >
      <SelectTrigger className="h-7 w-full text-left text-xs">
        <SelectValue placeholder="Ignore" />
      </SelectTrigger>
      <SelectContent className="max-h-72">
        <SelectItem value={IGNORE}>Ignore</SelectItem>
        {fields.map((f) => {
          const disabled = taken.has(String(col)) && f.key !== owner?.key
          return (
            <SelectItem key={f.key} value={f.key} disabled={disabled && f.key !== owner?.key}>
              {f.label}{f.required ? ' *' : ''}
            </SelectItem>
          )
        })}
      </SelectContent>
    </Select>
  )
}

export function ImportMappingDialog({
  open, onOpenChange, importKind, fields, file, fiscalYearId, importParams, importPath, title, onImported, onImportSuccess,
}: ImportMappingDialogProps) {
  const [sheet, setSheet] = useState<string | null>(null)
  const preview = useImportPreview(open ? file : null, sheet, open && !!file)
  const [headerRow, setHeaderRow] = useState(0)
  const [mapping, setMapping] = useState<MappingState>({})
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const rows = preview.data?.rows ?? []
  const width = useMemo(() => Math.max(0, ...rows.map((r) => r.length)), [rows])
  const maxRow = Math.max(rows.length - 1, 0)
  const headerRowIndex = Math.min(headerRow, maxRow)

  // Pre-fill: the saved per-client mapping first, then the backend's guesses.
  useEffect(() => {
    if (!preview.data) return
    setHeaderRow(preview.data.header_row)
    const saved = loadSavedMapping(importKind, fiscalYearId)
    if (saved && Object.keys(saved).length) {
      setMapping(saved)
      return
    }
    const guessed: MappingState = {}
    for (const field of fields) {
      const guess = preview.data.column_guesses[field.key]
      if (guess) guessed[field.key] = String(guess.index)
    }
    setMapping(guessed)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preview.data, importKind, fiscalYearId])

  const assign = (fieldKey: string, col: number | null) =>
    setMapping((current) => {
      const next: MappingState = { ...current, [fieldKey]: col === null ? '' : String(col) }
      if (col !== null) {
        for (const [key, value] of Object.entries(next)) {
          if (key !== fieldKey && value === String(col)) next[key] = ''
        }
      }
      return next
    })

  const mappedFields = fields.filter((f) => (mapping[f.key] ?? '') !== '')
  const missingFields = fields.filter((f) => f.required && (mapping[f.key] ?? '') === '')

  /** Live preview of the parsed result under the current mapping. */
  const parsedPreview = useMemo(() => {
    const out: Record<string, string>[] = []
    for (const row of rows.slice(headerRowIndex + 1)) {
      const parsed: Record<string, string> = {}
      for (const f of mappedFields) parsed[f.key] = (row[Number(mapping[f.key])] ?? '').trim()
      if (Object.values(parsed).some((v) => v !== '')) out.push(parsed)
    }
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, headerRowIndex, mapping, fields])

  const doImport = async () => {
    if (!file || missingFields.length) return
    setImporting(true)
    setError(null)
    const columnMap: ColumnMap = {}
    for (const f of mappedFields) columnMap[f.key] = Number(mapping[f.key])
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('column_map', JSON.stringify(columnMap))
      const { data } = await api.post(importPath, form, {
        params: { ...importParams, header_row: headerRowIndex },
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      saveMapping(importKind, fiscalYearId, mapping)
      onImportSuccess?.()
      onImported(data)
      onOpenChange(false)
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      if (detail && typeof detail === 'object' && 'message' in (detail as Record<string, unknown>)) {
        setError(String((detail as { message: string }).message))
      } else if (typeof detail === 'string') {
        setError(detail)
      } else {
        setError(apiErrorMessage(err))
      }
    } finally {
      setImporting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!importing) onOpenChange(o) }}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Table2 className="h-4 w-4" /> {title}
          </DialogTitle>
          <DialogDescription>
            Assign each column to a field — nothing is assumed from column titles. Your mapping is
            remembered for this fiscal year.
          </DialogDescription>
        </DialogHeader>

        {!file ? (
          <p className="text-sm text-muted-foreground">No file selected.</p>
        ) : preview.isLoading ? (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Reading {file.name}…
          </div>
        ) : preview.isError ? (
          <div className="space-y-3">
            <p className="text-sm text-destructive">Could not read the file: {apiErrorMessage(preview.error)}</p>
          </div>
        ) : preview.data ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-end gap-3">
              <div className="text-xs text-muted-foreground">
                {preview.data.file_name} — detected as <b>{preview.data.file_type}</b>, {preview.data.total_rows} rows
              </div>
              {preview.data.sheet_names.length > 0 && (
                <div className="space-y-1">
                  <Label className="text-xs">Sheet</Label>
                  <Select
                    value={sheet ?? preview.data.selected_sheet ?? preview.data.sheet_names[0]}
                    onValueChange={(v) => setSheet(v)}
                  >
                    <SelectTrigger className="h-8 w-48"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {preview.data.sheet_names.map((name) => (
                        <SelectItem key={name} value={name}>{name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div className="space-y-1">
                <Label className="text-xs">Header row</Label>
                <div className="flex items-center gap-1">
                  <Button type="button" variant="outline" size="icon" className="h-8 w-8" aria-label="Header row up"
                    onClick={() => setHeaderRow((r) => Math.max(0, Math.min(r - 1, maxRow)))}>
                    <Minus className="h-3 w-3" />
                  </Button>
                  <Input
                    className="h-8 w-16 text-center"
                    inputMode="numeric"
                    value={headerRow}
                    onChange={(e) => {
                      const n = Number(e.target.value)
                      setHeaderRow(Number.isNaN(n) ? 0 : Math.max(0, Math.min(n, maxRow)))
                    }}
                  />
                  <Button type="button" variant="outline" size="icon" className="h-8 w-8" aria-label="Header row down"
                    onClick={() => setHeaderRow((r) => Math.min(maxRow, r + 1))}>
                    <Plus className="h-3 w-3" />
                  </Button>
                </div>
              </div>
            </div>

            <div className="overflow-auto rounded-md border" style={{ maxHeight: '36vh' }}>
              <table className="w-full border-collapse text-xs">
                <thead className="sticky top-0 z-10 bg-muted/95 backdrop-blur-sm">
                  <tr>
                    <th className="border-b p-1" />
                    {Array.from({ length: width }, (_, col) => (
                      <th key={col} className="min-w-[9rem] border-b p-1 text-left align-top">
                        <ColumnAssign col={col} fields={fields} mapping={mapping} onAssign={assign} />
                        <div className="mt-0.5 px-1 font-mono text-[10px] text-muted-foreground">
                          {columnLetter(col)} — {(rows[headerRowIndex]?.[col] ?? '').slice(0, 24) || '(empty)'}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, rowIdx) => (
                    <tr key={rowIdx} className={rowIdx === headerRowIndex ? 'bg-muted/60 font-medium' : ''}>
                      <td className="border-b px-1 py-0.5 text-right text-[10px] text-muted-foreground">{rowIdx + 1}</td>
                      {Array.from({ length: width }, (_, col) => (
                        <td key={col} className="border-b px-1 py-0.5 font-mono">
                          {(row[col] ?? '').slice(0, 40) || '\u00a0'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="space-y-1">
              <Label className="text-xs">Preview — rows as they will be imported</Label>
              <div className="overflow-auto rounded-md border" style={{ maxHeight: '15vh' }}>
                <table className="w-full text-xs">
                  <thead className="bg-muted/60">
                    <tr>
                      {mappedFields.map((f) => (
                        <th key={f.key} className="px-2 py-1 text-left font-medium">{f.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {parsedPreview.slice(0, 8).map((row, i) => (
                      <tr key={i}>
                        {mappedFields.map((f) => (
                          <td key={f.key} className="px-2 py-0.5 font-mono">{row[f.key] ?? ''}</td>
                        ))}
                      </tr>
                    ))}
                    {!parsedPreview.length && (
                      <tr>
                        <td className="px-2 py-1 text-muted-foreground">No data rows below the selected header row.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {missingFields.length > 0 && (
              <p className="text-xs text-destructive">
                Assign {missingFields.map((f) => f.label).join(', ')} to import.
              </p>
            )}
            {error && <p className="text-xs text-destructive">{error}</p>}
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={importing}>Cancel</Button>
          <Button
            onClick={() => void doImport()}
            disabled={importing || preview.isLoading || !!preview.isError || missingFields.length > 0 || !file}
          >
            {importing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Import
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
