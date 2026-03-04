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

interface ImportFromConnectorPayload {
  connector_id: number
  period_id: number
  fiscal_year_id: number
}

export function useImportFromConnector() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ImportFromConnectorPayload) =>
      api
        .post<{ imported: number }>('/v1/trial-balance/import/connector', payload)
        .then((r) => r.data),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ['trial-balance', variables.period_id] })
    },
  })
}

interface ImportFromCSVPayload {
  period_id: number
  file: File
}

export function useImportFromCSV() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ period_id, file }: ImportFromCSVPayload) => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('period_id', period_id.toString())
      return api
        .post<{ imported: number }>('/v1/trial-balance/import/csv', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        .then((r) => r.data)
    },
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ['trial-balance', variables.period_id] })
    },
  })
}
