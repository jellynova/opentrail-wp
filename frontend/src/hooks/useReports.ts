import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { Report, ReportOutput } from '@/types'

export function useReports() {
  return useQuery({
    queryKey: ['reports'],
    queryFn: () => api.get<Report[]>('/v1/reports').then((r) => r.data),
  })
}

export function useGenerateReport() {
  return useMutation({
    mutationFn: ({ id, fiscal_year_id, period_id }: { id: number; fiscal_year_id: number; period_id?: number }) =>
      api
        .post<{ data: ReportOutput }>(`/v1/reports/${id}/generate`, { fiscal_year_id, period_id })
        .then((r) => r.data.data),
  })
}

export function usePreviewReport() {
  return useMutation({
    mutationFn: (body: { definition: unknown; fiscal_year_id: number; period_id?: number }) =>
      api.post<ReportOutput>('/v1/reports/preview', body).then((r) => r.data),
  })
}

export function useValidateDefinition() {
  return useMutation({
    mutationFn: (definition: unknown) =>
      api.post<{ valid: boolean; problems: string[] }>('/v1/reports/validate', { definition }).then((r) => r.data),
  })
}

function useReportsMutation<TVars, TResult>(fn: (vars: TVars) => Promise<TResult>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['reports'] }),
  })
}

export function useCloneReport() {
  return useReportsMutation((id: number) => api.post<Report>(`/v1/reports/${id}/clone`).then((r) => r.data))
}

export function useRevertReport() {
  return useReportsMutation((id: number) => api.post<Report>(`/v1/reports/${id}/revert`).then((r) => r.data))
}

export function useDeleteReport() {
  return useReportsMutation((id: number) => api.delete(`/v1/reports/${id}`).then(() => null))
}

export function useSaveReport() {
  return useReportsMutation(
    ({ id, ...body }: { id?: number; name: string; report_type: string; definition: unknown; description?: string }) =>
      (id ? api.put<Report>(`/v1/reports/${id}`, body) : api.post<Report>('/v1/reports', body)).then((r) => r.data)
  )
}

export type SofiScheduleType = 'supplier_payment' | 'employee_remuneration' | 'guarantee_indemnity'

export function useSofiSchedule(type: SofiScheduleType, fiscalYearId: number | null) {
  return useQuery({
    queryKey: ['sofi', type, fiscalYearId],
    queryFn: () =>
      api
        .get<ReportOutput>(`/v1/sofi/schedules/${type}`, { params: { fiscal_year_id: fiscalYearId } })
        .then((r) => r.data),
    enabled: fiscalYearId !== null,
  })
}

export function useImportSofi() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ type, fiscalYearId, file }: { type: SofiScheduleType; fiscalYearId: number; file: File }) => {
      const form = new FormData()
      form.append('file', file)
      return api
        .post<{ records_imported: number; errors: string[] }>('/v1/sofi/entries/import', form, {
          params: { fiscal_year_id: fiscalYearId, schedule_type: type },
        })
        .then((r) => r.data)
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['sofi'] }),
  })
}
