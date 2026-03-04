import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import type { Account } from '@/types'

interface AccountsParams {
  fiscal_year_id?: number
  acct_type?: string
  dept_code?: string
  fund_code?: string
  is_active?: boolean
}

export function useAccounts(params?: AccountsParams) {
  return useQuery({
    queryKey: ['accounts', params],
    queryFn: () =>
      api
        .get<Account[]>('/v1/accounts', { params })
        .then((r) => r.data),
    enabled: params?.fiscal_year_id !== undefined,
  })
}

export function useAccount(id: number | null) {
  return useQuery({
    queryKey: ['accounts', id],
    queryFn: () => api.get<Account>(`/v1/accounts/${id}`).then((r) => r.data),
    enabled: id !== null,
  })
}
