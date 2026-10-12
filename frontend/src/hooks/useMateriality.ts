import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { Materiality, UnsupportedMaterialAccountsResponse } from '@/types'

/** Current materiality for a fiscal year. 404 (not yet set) is a normal, expected state,
 * not a transient failure -- callers should check isError/error status, not retry. */
export function useMateriality(fiscalYearId: number | null) {
  return useQuery({
    queryKey: ['materiality', fiscalYearId],
    queryFn: () => api.get<Materiality>(`/v1/materiality/${fiscalYearId}`).then((r) => r.data),
    enabled: fiscalYearId !== null,
    retry: false,
  })
}

export interface MaterialityInput {
  fiscalYearId: number
  overall_materiality: string
  performance_materiality?: string | null
  trivial_threshold?: string | null
  basis?: string | null
  rationale?: string | null
}

export function useSetMateriality() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ fiscalYearId, ...body }: MaterialityInput) =>
      api.put<Materiality>(`/v1/materiality/${fiscalYearId}`, body).then((r) => r.data),
    onSuccess: (_, vars) => {
      void queryClient.invalidateQueries({ queryKey: ['materiality', vars.fiscalYearId] })
      void queryClient.invalidateQueries({ queryKey: ['unsupported-material-accounts'] })
    },
  })
}

export function useUnsupportedMaterialAccounts(
  fiscalYearId: number | null,
  periodId: number | null,
  scheme: string
) {
  return useQuery({
    queryKey: ['unsupported-material-accounts', fiscalYearId, periodId, scheme],
    queryFn: () =>
      api
        .get<UnsupportedMaterialAccountsResponse>(`/v1/materiality/${fiscalYearId}/unsupported-accounts`, {
          params: { period_id: periodId, scheme },
        })
        .then((r) => r.data),
    enabled: fiscalYearId !== null && periodId !== null,
  })
}
