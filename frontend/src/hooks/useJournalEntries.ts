import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { JournalEntry } from '@/types'

export function useJournalEntries(periodId: number | null) {
  return useQuery({
    queryKey: ['journal-entries', periodId],
    queryFn: () =>
      api
        .get<JournalEntry[]>('/v1/journal-entries', {
          params: { period_id: periodId },
        })
        .then((r) => r.data),
    enabled: periodId !== null,
  })
}

export function useAllJournalEntries(params?: {
  period_id?: number
  entry_type?: string
  status?: string
  limit?: number
}) {
  return useQuery({
    queryKey: ['journal-entries', params],
    queryFn: () =>
      api
        .get<JournalEntry[]>('/v1/journal-entries', { params })
        .then((r) => r.data),
  })
}

export function useJournalEntry(id: number | null) {
  return useQuery({
    queryKey: ['journal-entries', 'detail', id],
    queryFn: () =>
      api.get<JournalEntry>(`/v1/journal-entries/${id}`).then((r) => r.data),
    enabled: id !== null,
  })
}

interface CreateJournalEntryPayload {
  period_id: number
  entry_date: string
  reference?: string
  description?: string
  entry_type: 'adjusting' | 'reclassifying' | 'elimination' | 'budget_variance'
  lines: {
    account_id: number
    debit: string
    credit: string
    description?: string
    gl_reference?: string
  }[]
}

export function useCreateJournalEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateJournalEntryPayload) =>
      api
        .post<JournalEntry>('/v1/journal-entries', payload)
        .then((r) => r.data),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ['journal-entries', variables.period_id],
      })
      void queryClient.invalidateQueries({ queryKey: ['journal-entries'] })
    },
  })
}

export function usePostJournalEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      api
        .post<JournalEntry>(`/v1/journal-entries/${id}/post`)
        .then((r) => r.data),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ['journal-entries'] })
      void queryClient.invalidateQueries({
        queryKey: ['journal-entries', 'detail', data.id],
      })
    },
  })
}

export function useApproveJournalEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      api
        .post<JournalEntry>(`/v1/journal-entries/${id}/approve`)
        .then((r) => r.data),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ['journal-entries'] })
      void queryClient.invalidateQueries({
        queryKey: ['journal-entries', 'detail', data.id],
      })
    },
  })
}
