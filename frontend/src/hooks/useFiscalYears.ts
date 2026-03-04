import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { FiscalYear, Period } from '@/types'

export function useFiscalYears() {
  return useQuery({
    queryKey: ['fiscal-years'],
    queryFn: () => api.get<FiscalYear[]>('/v1/fiscal-years').then((r) => r.data),
  })
}

export function usePeriods(fiscalYearId: number | null) {
  return useQuery({
    queryKey: ['fiscal-years', fiscalYearId, 'periods'],
    queryFn: () =>
      api
        .get<Period[]>(`/v1/fiscal-years/${fiscalYearId}/periods`)
        .then((r) => r.data),
    enabled: fiscalYearId !== null,
  })
}

interface CreateFiscalYearPayload {
  label: string
  start_date: string
  end_date: string
}

export function useCreateFiscalYear() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateFiscalYearPayload) =>
      api.post<FiscalYear>('/v1/fiscal-years', payload).then((r) => r.data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['fiscal-years'] })
    },
  })
}

interface CreatePeriodPayload {
  period_number: number
  name: string
  start_date: string
  end_date: string
}

export function useCreatePeriod(fiscalYearId: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreatePeriodPayload) =>
      api
        .post<Period>(`/v1/fiscal-years/${fiscalYearId}/periods`, payload)
        .then((r) => r.data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['fiscal-years', fiscalYearId, 'periods'] })
    },
  })
}
