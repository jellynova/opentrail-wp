import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type {
  BudgetAmendment,
  BudgetRequest,
  BudgetVarianceReport,
  BudgetYear,
} from '@/types'

export function useBudgetYears() {
  return useQuery({
    queryKey: ['budget-years'],
    queryFn: () => api.get<BudgetYear[]>('/v1/budget-years').then((r) => r.data),
  })
}

export function useBudgetRequests(
  budgetYearId: number | null,
  params?: { department?: string; status?: string }
) {
  return useQuery({
    queryKey: ['budget-requests', budgetYearId, params],
    queryFn: () =>
      api
        .get<BudgetRequest[]>(`/v1/budget-years/${budgetYearId}/requests`, { params })
        .then((r) => r.data),
    enabled: budgetYearId !== null,
  })
}

export function useBudgetVariance(
  budgetYearId: number | null,
  params: { group_by: string; department?: string; period_id?: number }
) {
  return useQuery({
    queryKey: ['budget-variance', budgetYearId, params],
    queryFn: () =>
      api
        .get<BudgetVarianceReport>(`/v1/budget-years/${budgetYearId}/variance`, { params })
        .then((r) => r.data),
    enabled: budgetYearId !== null,
  })
}

export function useBudgetAmendments(budgetYearId: number | null) {
  return useQuery({
    queryKey: ['budget-amendments', budgetYearId],
    queryFn: () =>
      api.get<BudgetAmendment[]>(`/v1/budget-years/${budgetYearId}/amendments`).then((r) => r.data),
    enabled: budgetYearId !== null,
  })
}

/** Generic mutation that invalidates all budget queries on success. */
function useBudgetMutation<TVars, TResult = unknown>(fn: (vars: TVars) => Promise<TResult>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of ['budget-years', 'budget-requests', 'budget-variance', 'budget-amendments']) {
        void queryClient.invalidateQueries({ queryKey: [key] })
      }
    },
  })
}

export interface CreateBudgetRequestPayload {
  budgetYearId: number
  account_id: number
  department?: string
  proposed_amount: string
  justification_text?: string
}

export function useCreateBudgetRequest() {
  return useBudgetMutation(({ budgetYearId, ...payload }: CreateBudgetRequestPayload) =>
    api.post<BudgetRequest>(`/v1/budget-years/${budgetYearId}/requests`, payload).then((r) => r.data)
  )
}

export type RequestAction = 'submit' | 'approve' | 'reject' | 'return' | 'delete'

export function useBudgetRequestAction() {
  return useBudgetMutation(
    ({ id, action, body }: { id: number; action: RequestAction; body?: Record<string, unknown> }) =>
      action === 'delete'
        ? api.delete(`/v1/budget-requests/${id}`).then(() => null)
        : api.post<BudgetRequest>(`/v1/budget-requests/${id}/${action}`, body ?? {}).then((r) => r.data)
  )
}

export function useCreateBudgetYear() {
  return useBudgetMutation(
    (payload: { fiscal_year_id: number; label: string; submission_deadline?: string; instructions_text?: string }) =>
      api.post<BudgetYear>('/v1/budget-years', payload).then((r) => r.data)
  )
}

export function useSetBudgetYearStatus() {
  return useBudgetMutation(({ id, status }: { id: number; status: BudgetYear['status'] }) =>
    api.put<BudgetYear>(`/v1/budget-years/${id}`, { status }).then((r) => r.data)
  )
}

export function useConsolidateBudget() {
  return useBudgetMutation((budgetYearId: number) =>
    api
      .post<{ lines: number; requests_pending_review: number }>(`/v1/budget-years/${budgetYearId}/consolidate`)
      .then((r) => r.data)
  )
}

export function useCreateAmendment() {
  return useBudgetMutation(
    ({
      budgetYearId,
      ...payload
    }: {
      budgetYearId: number
      approval_reference?: string
      rationale?: string
      lines: { account_id: number; amount: string; description?: string }[]
    }) => api.post<BudgetAmendment>(`/v1/budget-years/${budgetYearId}/amendments`, payload).then((r) => r.data)
  )
}

export function useApproveAmendment() {
  return useBudgetMutation(({ id, approval_reference }: { id: number; approval_reference?: string }) =>
    api.post<BudgetAmendment>(`/v1/budget-amendments/${id}/approve`, { approval_reference }).then((r) => r.data)
  )
}
