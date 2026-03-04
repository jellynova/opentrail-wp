import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { BudgetYear, BudgetRequest } from '@/types'

export function useBudgetYears() {
  return useQuery({
    queryKey: ['budget-years'],
    queryFn: () => api.get<BudgetYear[]>('/v1/budget/years').then((r) => r.data),
  })
}

export function useBudgetRequests(params?: {
  budget_year_id?: number
  department?: string
  status?: string
}) {
  return useQuery({
    queryKey: ['budget-requests', params],
    queryFn: () =>
      api
        .get<BudgetRequest[]>('/v1/budget/requests', { params })
        .then((r) => r.data),
  })
}

interface CreateBudgetRequestPayload {
  budget_year_id: number
  account_id: number
  department: string
  prior_year_actual?: string
  prior_year_budget?: string
  proposed_amount: string
  justification_text?: string
}

export function useCreateBudgetRequest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateBudgetRequestPayload) =>
      api.post<BudgetRequest>('/v1/budget/requests', payload).then((r) => r.data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['budget-requests'] })
    },
  })
}

interface UpdateBudgetRequestStatusPayload {
  id: number
  status: 'submitted' | 'approved' | 'modified' | 'rejected'
  approved_amount?: string
}

export function useUpdateBudgetRequestStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: UpdateBudgetRequestStatusPayload) =>
      api
        .patch<BudgetRequest>(`/v1/budget/requests/${id}/status`, payload)
        .then((r) => r.data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['budget-requests'] })
    },
  })
}
