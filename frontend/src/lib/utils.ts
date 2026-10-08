import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num)) return '—'
  return new Intl.NumberFormat('en-CA', {
    style: 'currency',
    currency: 'CAD',
    minimumFractionDigits: 2,
  }).format(num)
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  // Date-only values (2025-01-01) are calendar dates, not instants: parsing them as UTC
  // midnight renders the previous day anywhere west of UTC — including BC.
  const value = /^\d{4}-\d{2}-\d{2}$/.test(dateStr) ? `${dateStr}T00:00:00` : dateStr
  const date = new Date(value)
  if (isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('en-CA')
}

export function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('en-CA')
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function netBalance(debit: string, credit: string): number {
  return parseFloat(debit || '0') - parseFloat(credit || '0')
}

/** Human-readable message from an API error (FastAPI `detail` string, list or validation errors). */
export function apiErrorMessage(error: unknown, fallback = 'Something went wrong.'): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === 'string' ? d : (d as { msg?: string })?.msg ?? JSON.stringify(d)))
      .join('; ')
  }
  return fallback
}

/** Accounting format: thousands separators, negatives in parentheses, no currency symbol. */
export function formatAmount(value: string | number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || value === '') return ''
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num)) return ''
  if (Math.abs(num) < 0.5 * Math.pow(10, -decimals)) return '-'
  const s = new Intl.NumberFormat('en-CA', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(Math.abs(num))
  return num < 0 ? `(${s})` : s
}

/** "3 min ago" style formatting for activity feeds. */
export function formatRelativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  const then = new Date(dateStr).getTime()
  if (isNaN(then)) return '—'
  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days} d ago`
  return formatDate(dateStr)
}

/** Title-case a snake_case action or resource name for display. */
export function humanise(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
