import { AlertTriangle } from 'lucide-react'
import { cn, formatAmount } from '@/lib/utils'
import type { ReportOutput } from '@/types'

/** Renders the common tabular report shape as a financial statement. */
export function ReportView({ report }: { report: ReportOutput }) {
  const decimals = report.number_format?.decimals ?? 0
  const textCols = report.text_columns ?? []

  return (
    <div className="space-y-3">
      {!!report.warnings?.length && (
        <div className="rounded-md border border-yellow-300 bg-yellow-50 p-3 text-sm text-yellow-900">
          {report.warnings.map((w) => (
            <div key={w} className="flex gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              {w}
            </div>
          ))}
        </div>
      )}
      <div className="rounded-md border bg-white p-6 font-serif text-sm text-black">
        <div className="mb-4 text-center">
          {report.organization && <div className="font-bold uppercase">{report.organization}</div>}
          <div className="text-base font-bold">{report.title}</div>
          {report.subtitle && <div className="italic">{report.subtitle}</div>}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-black">
                {textCols.map((c) => (
                  <th key={c.key} className="px-2 py-1 text-left font-bold">
                    {c.label}
                  </th>
                ))}
                <th />
                {report.columns.map((c) => (
                  <th key={c.key} className="whitespace-nowrap px-2 py-1 text-right font-bold">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.rows.map((row, i) => {
                const u = row.style?.underline
                return (
                  <tr key={row.id ?? i} className={cn(row.style?.bold && 'font-bold', row.style?.italic && 'italic')}>
                    {textCols.map((c) => (
                      <td key={c.key} className="whitespace-nowrap px-2 py-0.5 font-mono text-xs">
                        {row.text?.[c.key] ?? ''}
                      </td>
                    ))}
                    <td className="py-0.5 pr-2" style={{ paddingLeft: `${0.5 + 1.25 * (row.level ?? 0)}rem` }}>
                      {row.label}
                    </td>
                    {report.columns.map((c) => {
                      const v = row.values?.[c.key]
                      const text =
                        v === null || v === undefined
                          ? ''
                          : c.percent
                            ? `${Number(v).toFixed(1)}%`
                            : formatAmount(v, decimals)
                      return (
                        <td
                          key={c.key}
                          className={cn(
                            'w-32 whitespace-nowrap px-2 py-0.5 text-right tabular-nums',
                            u === 'single' && text && 'border-t border-black',
                            u === 'double' && text && 'border-b-4 border-t border-double border-black'
                          )}
                        >
                          {text}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
