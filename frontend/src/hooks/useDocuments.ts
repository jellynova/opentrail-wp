import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from '@/lib/api'
import type { FolderNode, WPAnnotation, WorkingPaper } from '@/types'

function invalidateDocuments(queryClient: ReturnType<typeof useQueryClient>) {
  for (const key of ['documents', 'document-versions', 'document-annotations', 'document-folders']) {
    void queryClient.invalidateQueries({ queryKey: [key] })
  }
}

export function useDocumentFolders(fiscalYearId?: number | null) {
  return useQuery({
    queryKey: ['document-folders', fiscalYearId ?? null],
    queryFn: () =>
      api
        .get<FolderNode[]>('/v1/documents/folders', {
          params: fiscalYearId ? { fiscal_year_id: fiscalYearId } : undefined,
        })
        .then((r) => r.data),
  })
}

export function useDocuments(params: { folder_path?: string; fiscal_year_id?: number | null }) {
  return useQuery({
    queryKey: ['documents', params],
    queryFn: () =>
      api
        .get<WorkingPaper[]>('/v1/documents', {
          params: {
            ...(params.folder_path ? { folder_path: params.folder_path } : {}),
            ...(params.fiscal_year_id ? { fiscal_year_id: params.fiscal_year_id } : {}),
          },
        })
        .then((r) => r.data),
  })
}

export function useDocumentVersions(documentId: number | null) {
  return useQuery({
    queryKey: ['document-versions', documentId],
    queryFn: () => api.get<WorkingPaper[]>(`/v1/documents/${documentId}/versions`).then((r) => r.data),
    enabled: documentId !== null,
  })
}

export function useDocumentAnnotations(documentId: number | null, includeResolved = true) {
  return useQuery({
    queryKey: ['document-annotations', documentId, includeResolved],
    queryFn: () =>
      api
        .get<WPAnnotation[]>(`/v1/documents/${documentId}/annotations`, {
          params: { include_resolved: includeResolved },
        })
        .then((r) => r.data),
    enabled: documentId !== null,
  })
}

export function useUploadDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      file,
      fiscalYearId,
      folderPath,
      description,
    }: {
      file: File
      fiscalYearId: number
      folderPath: string
      description?: string
    }) => {
      const form = new FormData()
      form.append('file', file)
      form.append('fiscal_year_id', String(fiscalYearId))
      form.append('folder_path', folderPath)
      form.append('display_name', file.name)
      if (description) form.append('description', description)
      return api
        .post<WorkingPaper>('/v1/documents/upload', form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        .then((r) => r.data)
    },
    onSuccess: () => invalidateDocuments(queryClient),
  })
}

export function useUploadNewVersion() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ documentId, file }: { documentId: number; file: File }) => {
      const form = new FormData()
      form.append('file', file)
      return api
        .post<WorkingPaper>(`/v1/documents/${documentId}/versions`, form, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        .then((r) => r.data)
    },
    onSuccess: () => invalidateDocuments(queryClient),
  })
}

export function useUpdateDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      documentId,
      ...payload
    }: {
      documentId: number
      display_name?: string
      description?: string
      folder_path?: string
    }) => api.put<WorkingPaper>(`/v1/documents/${documentId}`, payload).then((r) => r.data),
    onSuccess: () => invalidateDocuments(queryClient),
  })
}

export function useDeleteDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (documentId: number) => api.delete(`/v1/documents/${documentId}`).then(() => null),
    onSuccess: () => invalidateDocuments(queryClient),
  })
}

export type SignOffLevel = 'preparer' | 'reviewer' | 'reset'

export function useSignOffDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ documentId, level, note }: { documentId: number; level: SignOffLevel; note?: string }) =>
      api
        .post<{ message: string; sign_off_state: string }>(
          `/v1/documents/${documentId}/sign-off/${level}`,
          note ? { note } : undefined
        )
        .then((r) => r.data),
    onSuccess: () => invalidateDocuments(queryClient),
  })
}

export function useAddAnnotation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ documentId, text }: { documentId: number; text: string }) =>
      api.post<WPAnnotation>(`/v1/documents/${documentId}/annotations`, { text }).then((r) => r.data),
    onSuccess: () => invalidateDocuments(queryClient),
  })
}

export function useResolveAnnotation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ documentId, annotationId, resolved }: { documentId: number; annotationId: number; resolved: boolean }) =>
      api
        .post<WPAnnotation>(`/v1/documents/${documentId}/annotations/${annotationId}/resolve`, undefined, {
          params: { resolved },
        })
        .then((r) => r.data),
    onSuccess: () => invalidateDocuments(queryClient),
  })
}

export function useDeleteAnnotation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ documentId, annotationId }: { documentId: number; annotationId: number }) =>
      api.delete(`/v1/documents/${documentId}/annotations/${annotationId}`).then(() => null),
    onSuccess: () => invalidateDocuments(queryClient),
  })
}
