import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { TcaLine, TcaLineInput, TcaRollForwardResult, TcaScheduleReport } from '@/types'

export type TcaLayout = 'continuity' | 'summary'

const key = (fiscalYearId: number | null) => ['tca', fiscalYearId]

export function useTcaLines(fiscalYearId: number | null) {
  return useQuery({
    queryKey: [...key(fiscalYearId), 'lines'],
    queryFn: () =>
      api.get<TcaLine[]>('/v1/tca/lines', { params: { fiscal_year_id: fiscalYearId } }).then((r) => r.data),
    enabled: fiscalYearId !== null,
  })
}

export function useTcaSchedule(fiscalYearId: number | null, layout: TcaLayout) {
  return useQuery({
    queryKey: [...key(fiscalYearId), 'schedule', layout],
    queryFn: () =>
      api
        .get<TcaScheduleReport>('/v1/tca/schedule', {
          params: { fiscal_year_id: fiscalYearId, layout },
        })
        .then((r) => r.data),
    enabled: fiscalYearId !== null,
  })
}

export function useSaveTcaLines(fiscalYearId: number | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (lines: TcaLineInput[]) =>
      api
        .put<{ lines_saved: number; totals: Record<string, string> }>('/v1/tca/lines', { lines }, {
          params: { fiscal_year_id: fiscalYearId },
        })
        .then((r) => r.data),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: key(fiscalYearId) }),
  })
}

export function useImportTca(fiscalYearId: number | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ file, replace }: { file: File; replace: boolean }) => {
      const form = new FormData()
      form.append('file', file)
      return api
        .post<{ records_imported: number; errors: string[] }>('/v1/tca/lines/import', form, {
          params: { fiscal_year_id: fiscalYearId, replace },
        })
        .then((r) => r.data)
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: key(fiscalYearId) }),
  })
}

export function useRollForwardTca(fiscalYearId: number | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api
        .post<TcaRollForwardResult>('/v1/tca/lines/roll-forward', null, {
          params: { fiscal_year_id: fiscalYearId },
        })
        .then((r) => r.data),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: key(fiscalYearId) }),
  })
}
