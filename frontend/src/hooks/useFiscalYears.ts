import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { FiscalYear, FiscalYearReopenResult, Period, PeriodClose, PreCloseCheck, RollForwardResult } from '@/types'

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


// ── Period close and roll forward (PLAN §7.3) ───────────────────────────────

function usePeriodMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['fiscal-years'] })
      void queryClient.invalidateQueries({ queryKey: ['trial-balance'] })
    },
  })
}

export function usePeriodCloseCheck(periodId: number | null) {
  return useQuery({
    queryKey: ['period-close-check', periodId],
    queryFn: () => api.get<PreCloseCheck>(`/v1/periods/${periodId}/close-check`).then((r) => r.data),
    enabled: periodId !== null,
  })
}

export function usePeriodClose(periodId: number | null) {
  return usePeriodMutation(
    ({ notes, force }: { notes?: string; force?: boolean }) =>
      api.post<PeriodClose>(`/v1/periods/${periodId}/close`, { notes, force }).then((r) => r.data)
  )
}

export function usePeriodReopen(periodId: number | null) {
  return usePeriodMutation(
    ({ reason, periodId: overrideId }: { reason?: string; periodId?: number }) =>
      api
        .post<Period>(`/v1/periods/${overrideId ?? periodId}/reopen`, { reason })
        .then((r) => r.data)
  )
}

export function useCloseFiscalYear() {
  return usePeriodMutation(
    ({ fiscalYearId, force }: { fiscalYearId: number; force?: boolean }) =>
      api.post<FiscalYear>(`/v1/fiscal-years/${fiscalYearId}/close`, { force }).then((r) => r.data)
  )
}

export function useRollForwardFiscalYear() {
  return usePeriodMutation(
    ({ fiscalYearId, label }: { fiscalYearId: number; label?: string }) =>
      api
        .post<RollForwardResult>(`/v1/fiscal-years/${fiscalYearId}/roll-forward`, { label })
        .then((r) => r.data)
  )
}

export function usePeriodCloseSnapshot(periodId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ['period-close', periodId],
    queryFn: () => api.get<PeriodClose>(`/v1/periods/${periodId}/close`).then((r) => r.data),
    enabled: periodId !== null && enabled,
  })
}

// ── Fiscal-year reopen (finance_admin only, audited) ─────────────────────────

export function useReopenFiscalYear() {
  return usePeriodMutation(
    ({ fiscalYearId, reason, force }: { fiscalYearId: number; reason: string; force?: boolean }) =>
      api
        .post<FiscalYearReopenResult>(`/v1/fiscal-years/${fiscalYearId}/reopen`, { reason, force })
        .then((r) => r.data)
  )
}
