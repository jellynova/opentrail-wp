import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { TrialBalanceEntry } from '@/types'

export function useTrialBalance(periodId: number | null) {
  return useQuery({
    queryKey: ['trial-balance', periodId],
    queryFn: () =>
      api
        .get<TrialBalanceEntry[]>('/v1/trial-balance', {
          params: { period_id: periodId },
        })
        .then((r) => r.data),
    enabled: periodId !== null,
  })
}

/** What both import endpoints return (backend `ImportResult`). */
export interface ImportResult {
  records_imported: number
  records_updated: number
  errors: string[]
}

interface ImportFromCSVPayload {
  period_id: number
  fiscal_year_id: number
  file: File
}

export function useImportFromCSV() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ period_id, fiscal_year_id, file }: ImportFromCSVPayload) => {
      const formData = new FormData()
      formData.append('file', file)
      // period_id and fiscal_year_id are query parameters, not form fields.
      return api
        .post<ImportResult>('/v1/trial-balance/import/csv', formData, {
          params: { period_id, fiscal_year_id },
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        .then((r) => r.data)
    },
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ['trial-balance', variables.period_id] })
    },
  })
}
