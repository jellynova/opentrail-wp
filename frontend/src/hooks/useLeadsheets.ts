import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { AccountComment, AccountLink, LeadsheetsResponse, MappingScheme, RelatedDocument, WorkingPaper } from '@/types'

export function useLeadsheets(periodId: number | null, scheme: string) {
  return useQuery({
    queryKey: ['leadsheets', periodId, scheme],
    queryFn: () =>
      api
        .get<LeadsheetsResponse>('/v1/working-papers/leadsheets', {
          params: { period_id: periodId, scheme },
        })
        .then((r) => r.data),
    enabled: periodId !== null,
  })
}

export function useMappingSchemes() {
  return useQuery({
    queryKey: ['mapping-schemes'],
    queryFn: () => api.get<MappingScheme[]>('/v1/mapping-schemes').then((r) => r.data),
  })
}

export function useAccountLinks(documentId: number | null) {
  return useQuery({
    queryKey: ['account-links', documentId],
    queryFn: () =>
      api.get<AccountLink[]>(`/v1/working-papers/${documentId}/account-links`).then((r) => r.data),
    enabled: documentId !== null,
  })
}

/** All links for a fiscal year, fetched once so leadsheet rows can show indicators cheaply. */
export function useAllAccountLinks(fiscalYearId: number | null) {
  return useQuery({
    queryKey: ['account-links', 'by-year', fiscalYearId],
    queryFn: async () => {
      const documents = await api
        .get<WorkingPaper[]>('/v1/documents', { params: { fiscal_year_id: fiscalYearId! } })
        .then((r) => r.data)
      const links = await Promise.all(
        documents.map((d: WorkingPaper) =>
          api
            .get<AccountLink[]>(`/v1/working-papers/${d.id}/account-links`)
            .then((r) => r.data)
            .catch(() => [] as AccountLink[])
        )
      )
      return links.flat()
    },
    enabled: fiscalYearId !== null,
  })
}

/** Latest-version documents for one fiscal year (used by the link picker). */
export function useDocumentsForLinks(fiscalYearId: number | null) {
  return useQuery({
    queryKey: ['documents', { fiscal_year_id: fiscalYearId }],
    queryFn: () =>
      api
        .get<WorkingPaper[]>('/v1/documents', { params: { fiscal_year_id: fiscalYearId! } })
        .then((r) => r.data),
    enabled: fiscalYearId !== null,
  })
}

export function useLinksByAccount(accountCode: string | null, fiscalYearId?: number | null) {
  return useQuery({
    queryKey: ['account-links', 'by-account', accountCode, fiscalYearId ?? null],
    queryFn: () =>
      api
        .get<AccountLink[]>(`/v1/working-papers/by-account/${encodeURIComponent(accountCode!)}`, {
          params: fiscalYearId ? { fiscal_year_id: fiscalYearId } : undefined,
        })
        .then((r) => r.data),
    enabled: !!accountCode,
  })
}

function useLinkMutation<TVars>(fn: (vars: TVars) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of ['account-links', 'documents', 'working-papers-leadsheets']) {
        void queryClient.invalidateQueries({ queryKey: [key] })
      }
    },
  })
}

export function useAddAccountLink() {
  return useLinkMutation<{ documentId: number; account_code: string; fiscal_year_id: number }>(
    ({ documentId, ...body }) =>
      api
        .post<AccountLink>(`/v1/working-papers/${documentId}/account-links`, body)
        .then((r) => r.data)
  )
}

export function useRemoveAccountLink() {
  return useLinkMutation<{ documentId: number; linkId: number }>(
    ({ documentId, linkId }) =>
      api.delete(`/v1/working-papers/${documentId}/account-links/${linkId}`)
  )
}

// ── Document-to-document cross-references ("file linking") ─────────────────

export function useRelatedDocuments(documentId: number | null) {
  return useQuery({
    queryKey: ['related-documents', documentId],
    queryFn: () =>
      api.get<RelatedDocument[]>(`/v1/working-papers/${documentId}/related-documents`).then((r) => r.data),
    enabled: documentId !== null,
  })
}

function useRelatedDocumentMutation<TVars>(fn: (vars: TVars) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['related-documents'] }),
  })
}

export function useAddRelatedDocument() {
  return useRelatedDocumentMutation<{ documentId: number; related_document_id: number; note?: string }>(
    ({ documentId, ...body }) =>
      api.post<RelatedDocument>(`/v1/working-papers/${documentId}/related-documents`, body).then((r) => r.data)
  )
}

export function useRemoveRelatedDocument() {
  return useRelatedDocumentMutation<{ documentId: number; linkId: number }>(
    ({ documentId, linkId }) => api.delete(`/v1/working-papers/${documentId}/related-documents/${linkId}`)
  )
}

// ── Account comments ("explain a variance" without a document) ─────────────

export function useAccountComments(accountCode: string | null, fiscalYearId: number | null) {
  return useQuery({
    queryKey: ['account-comments', accountCode, fiscalYearId],
    queryFn: () =>
      api
        .get<AccountComment[]>(`/v1/working-papers/by-account/${encodeURIComponent(accountCode!)}/comments`, {
          params: { fiscal_year_id: fiscalYearId },
        })
        .then((r) => r.data),
    enabled: !!accountCode && fiscalYearId !== null,
  })
}

/** Every comment for a fiscal year, fetched once so leadsheet rows can show counts cheaply. */
export function useAllAccountComments(fiscalYearId: number | null) {
  return useQuery({
    queryKey: ['account-comments', 'by-year', fiscalYearId],
    queryFn: () =>
      api.get<AccountComment[]>('/v1/working-papers/comments', { params: { fiscal_year_id: fiscalYearId! } }).then((r) => r.data),
    enabled: fiscalYearId !== null,
  })
}

function useCommentMutation<TVars>(fn: (vars: TVars) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['account-comments'] })
      void queryClient.invalidateQueries({ queryKey: ['unsupported-material-accounts'] })
    },
  })
}

export function useAddAccountComment() {
  return useCommentMutation<{ accountCode: string; fiscal_year_id: number; text: string }>(
    ({ accountCode, ...body }) =>
      api.post<AccountComment>(`/v1/working-papers/by-account/${encodeURIComponent(accountCode)}/comments`, body)
  )
}

export function useResolveAccountComment() {
  return useCommentMutation<{ accountCode: string; commentId: number; resolved: boolean }>(
    ({ accountCode, commentId, resolved }) =>
      api.post(
        `/v1/working-papers/by-account/${encodeURIComponent(accountCode)}/comments/${commentId}/resolve`,
        null,
        { params: { resolved } }
      )
  )
}

export function useDeleteAccountComment() {
  return useCommentMutation<{ accountCode: string; commentId: number }>(
    ({ accountCode, commentId }) =>
      api.delete(`/v1/working-papers/by-account/${encodeURIComponent(accountCode)}/comments/${commentId}`)
  )
}
