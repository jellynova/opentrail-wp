import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CheckCircle2,
  ChevronRight,
  Download,
  Eye,
  File,
  FileSpreadsheet,
  FileText,
  Folder,
  FolderOpen,
  History,
  Image as ImageIcon,
  Loader2,
  MessageSquare,
  Pencil,
  RotateCcw,
  ShieldCheck,
  Trash2,
  Upload,
} from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import api from '@/lib/api'
import { downloadFile } from '@/lib/download'
import { apiErrorMessage, formatDateTime, formatFileSize, formatRelativeTime } from '@/lib/utils'
import { toast } from '@/hooks/useToast'
import { useAuthStore } from '@/store/auth'
import { useFiscalYears } from '@/hooks/useFiscalYears'
import {
  useAddAnnotation,
  useDeleteAnnotation,
  useDeleteDocument,
  useDocumentAnnotations,
  useDocumentFolders,
  useDocuments,
  useDocumentVersions,
  useResolveAnnotation,
  useSignOffDocument,
  useUpdateDocument,
  useUploadDocument,
  useUploadNewVersion,
} from '@/hooks/useDocuments'
import { useAllAccountLinks } from '@/hooks/useLeadsheets'
import type { AccountLink, FolderNode, SignOffState, WPAnnotation, WorkingPaper } from '@/types'

function FileTypeIcon({ type }: { type: WorkingPaper['file_type'] }) {
  switch (type) {
    case 'pdf': return <FileText className="h-4 w-4 text-red-500" />
    case 'xlsx': return <FileSpreadsheet className="h-4 w-4 text-green-600" />
    case 'docx': return <FileText className="h-4 w-4 text-blue-600" />
    case 'img': return <ImageIcon className="h-4 w-4 text-purple-500" />
    default: return <File className="h-4 w-4 text-muted-foreground" />
  }
}

const STATE_META: Record<SignOffState, { label: string; variant: 'success' | 'info' | 'warning' | 'secondary' }> = {
  approved: { label: 'Reviewed', variant: 'success' },
  prepared: { label: 'Prepared', variant: 'info' },
  reapproval_required: { label: 'Re-review needed', variant: 'warning' },
  draft: { label: 'Draft', variant: 'secondary' },
}

function SignOffBadge({ state }: { state: SignOffState }) {
  const meta = STATE_META[state] ?? STATE_META.draft
  return <Badge variant={meta.variant}>{meta.label}</Badge>
}

function FolderNodeView({
  node,
  selected,
  onSelect,
  depth = 0,
}: {
  node: FolderNode
  selected: string
  onSelect: (path: string) => void
  depth?: number
}) {
  const [expanded, setExpanded] = useState(depth === 0)
  const hasChildren = node.children.length > 0
  const isSelected = selected === node.path

  return (
    <div>
      <button
        onClick={() => {
          onSelect(node.path)
          if (hasChildren) setExpanded((e) => !e)
        }}
        className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-left transition-colors ${
          isSelected ? 'bg-primary/10 text-primary font-medium' : 'text-foreground hover:bg-muted'
        }`}
      >
        {hasChildren ? (
          <ChevronRight className={`h-3 w-3 shrink-0 transition-transform ${expanded ? 'rotate-90' : ''}`} />
        ) : (
          <span className="w-3 shrink-0" />
        )}
        {expanded && hasChildren ? (
          <FolderOpen className="h-4 w-4 shrink-0" />
        ) : (
          <Folder className="h-4 w-4 shrink-0" />
        )}
        <span className="flex-1 truncate">{node.label}</span>
        {node.document_count > 0 && (
          <span className="text-xs text-muted-foreground">{node.document_count}</span>
        )}
        {node.unsigned_count > 0 && (
          <span className="rounded-full bg-amber-100 px-1.5 text-[10px] text-amber-700">
            {node.unsigned_count}
          </span>
        )}
      </button>
      {hasChildren && expanded && (
        <div className="ml-3 mt-0.5 space-y-0.5 border-l pl-1">
          {node.children.map((child) => (
            <FolderNodeView key={child.path} node={child} selected={selected} onSelect={onSelect} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

/** Inline PDF viewer. An <iframe src> can't send the Bearer token, so fetch the file
 * through the API client and show it from a blob URL. */
function PdfPreview({ paper }: { paper: WorkingPaper }) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let objectUrl: string | null = null
    let cancelled = false
    setUrl(null)
    setError(null)
    api
      .get<Blob>(`/v1/documents/${paper.id}/download`, { responseType: 'blob' })
      .then((r) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(new Blob([r.data], { type: 'application/pdf' }))
        setUrl(objectUrl)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(apiErrorMessage(err))
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [paper.id])

  if (error) return <p className="py-8 text-center text-sm text-destructive">Could not load preview: {error}</p>
  if (!url) return <LoadingSpinner />
  return <iframe src={url} className="w-full h-[70vh] rounded border" title={paper.display_name} />
}

function PreviewDialog({ paper, onClose }: { paper: WorkingPaper | null; onClose: () => void }) {
  if (!paper) return null
  return (
    <Dialog open={!!paper} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle>{paper.display_name}</DialogTitle>
        </DialogHeader>
        {paper.file_type === 'pdf' ? (
          <PdfPreview paper={paper} />
        ) : (
          <div className="flex flex-col items-center gap-4 py-8 text-muted-foreground">
            <FileTypeIcon type={paper.file_type} />
            <p className="text-sm">Preview not available for {paper.file_type} files.</p>
            <Button
              variant="outline"
              onClick={() => void downloadFile(`/v1/documents/${paper.id}/download`, paper.display_name)}
            >
              <Download className="mr-2 h-4 w-4" /> Download
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** Review panel: sign-off actions, comments and version history for one document. */
function DocumentDialog({
  document,
  onClose,
}: {
  document: WorkingPaper | null
  onClose: () => void
}) {
  const user = useAuthStore((s) => s.user)
  const [comment, setComment] = useState('')
  const [signOffNote, setSignOffNote] = useState('')

  const { data: versions } = useDocumentVersions(document?.id ?? null)
  const { data: annotations } = useDocumentAnnotations(document?.id ?? null, true)
  const addAnnotation = useAddAnnotation()
  const resolveAnnotation = useResolveAnnotation()
  const deleteAnnotation = useDeleteAnnotation()
  const signOff = useSignOffDocument()
  const uploadVersion = useUploadNewVersion()
  const versionInput = useRef<HTMLInputElement>(null)

  const canPrepare = user?.role === 'finance_admin' || user?.role === 'finance_officer'
  const canReview = user?.role === 'finance_admin'

  if (!document) return null

  const runSignOff = (level: 'preparer' | 'reviewer' | 'reset') => {
    signOff.mutate(
      { documentId: document.id, level, note: signOffNote || undefined },
      {
        onSuccess: (result) => {
          toast({ title: result.message })
          setSignOffNote('')
          onClose()
        },
        onError: (err) => toast({ title: 'Sign-off failed', description: apiErrorMessage(err), variant: 'destructive' }),
      }
    )
  }

  return (
    <Dialog open={!!document} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {document.display_name}
            <SignOffBadge state={document.sign_off_state} />
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 text-sm">
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-muted-foreground">
            <span>Folder: <span className="text-foreground">{document.folder_path}</span></span>
            <span>Version: <span className="text-foreground">{document.version_number} of {document.version_count}</span></span>
            <span>Uploaded by: <span className="text-foreground">{document.uploaded_by_username ?? '—'}</span></span>
            <span>Uploaded: <span className="text-foreground">{formatDateTime(document.uploaded_at)}</span></span>
            <span>
              Preparer:{' '}
              <span className="text-foreground">
                {document.preparer_signed_off_by_username
                  ? `${document.preparer_signed_off_by_username} · ${formatDateTime(document.preparer_signed_off_at)}`
                  : 'not signed off'}
              </span>
            </span>
            <span>
              Reviewer:{' '}
              <span className="text-foreground">
                {document.reviewer_signed_off_by_username
                  ? `${document.reviewer_signed_off_by_username} · ${formatDateTime(document.reviewer_signed_off_at)}`
                  : 'not reviewed'}
              </span>
            </span>
          </div>

          {document.requires_reapproval && (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              This working paper changed after it was reviewed, so it needs approval again.
            </div>
          )}

          {/* Sign-off */}
          <div className="rounded-md border p-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Sign-off (PLAN §7.2)
            </p>
            <Input
              className="mb-2"
              placeholder="Optional note for the sign-off…"
              value={signOffNote}
              onChange={(e) => setSignOffNote(e.target.value)}
            />
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={!canPrepare || signOff.isPending || document.reviewer_signed_off_at !== null}
                onClick={() => runSignOff('preparer')}
              >
                <ShieldCheck className="mr-2 h-4 w-4" /> Mark prepared
              </Button>
              <Button
                size="sm"
                disabled={!canReview || signOff.isPending || document.preparer_signed_off_at === null}
                onClick={() => runSignOff('reviewer')}
              >
                <CheckCircle2 className="mr-2 h-4 w-4" /> Approve (reviewer)
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-destructive hover:text-destructive"
                disabled={!canReview || signOff.isPending}
                onClick={() => runSignOff('reset')}
              >
                <RotateCcw className="mr-2 h-4 w-4" /> Withdraw sign-off
              </Button>
            </div>
            {!canReview && (
              <p className="mt-2 text-xs text-muted-foreground">
                Reviewer approval is a finance director (finance_admin) action, and cannot be given by the preparer.
              </p>
            )}
          </div>

          {/* Versions */}
          <div className="rounded-md border p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <History className="mr-1 inline h-3 w-3" /> Version history
              </p>
              {canPrepare && (
                <>
                  <input
                    ref={versionInput}
                    type="file"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (!file) return
                      uploadVersion.mutate(
                        { documentId: document.id, file },
                        {
                          onSuccess: () => toast({ title: 'New version uploaded — review required again' }),
                          onError: (err) =>
                            toast({ title: 'Upload failed', description: apiErrorMessage(err), variant: 'destructive' }),
                        }
                      )
                      e.target.value = ''
                    }}
                  />
                  <Button size="sm" variant="outline" onClick={() => versionInput.current?.click()} disabled={uploadVersion.isPending}>
                    {uploadVersion.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Upload className="mr-2 h-4 w-4" />
                    )}
                    Upload new version
                  </Button>
                </>
              )}
            </div>
            <div className="space-y-1">
              {versions?.map((v) => (
                <div key={v.id} className="flex items-center justify-between rounded-sm bg-muted/50 px-2 py-1 text-xs">
                  <span>
                    v{v.version_number} · {v.uploaded_by_username} · {formatDateTime(v.uploaded_at)}
                    {v.superseded_at && <span className="ml-2 text-muted-foreground">(superseded)</span>}
                  </span>
                  <span className="flex items-center gap-2">
                    <SignOffBadge state={v.sign_off_state} />
                    <button
                      className="text-primary hover:underline"
                      onClick={() => void downloadFile(`/v1/documents/${v.id}/download`, v.display_name)}
                    >
                      download
                    </button>
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Comments */}
          <div className="rounded-md border p-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <MessageSquare className="mr-1 inline h-3 w-3" /> Review notes
            </p>
            <div className="mb-2 space-y-1">
              {!annotations?.length ? (
                <p className="text-xs text-muted-foreground">No notes yet.</p>
              ) : (
                annotations.map((a: WPAnnotation) => (
                  <div key={a.id} className="flex items-start justify-between gap-2 rounded-sm bg-muted/50 px-2 py-1">
                    <div className="min-w-0">
                      <p className={`text-xs ${a.is_resolved ? 'text-muted-foreground line-through' : ''}`}>{a.text}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {a.username} · {formatRelativeTime(a.created_at)}
                        {a.is_resolved && a.resolved_by_username && ` · resolved by ${a.resolved_by_username}`}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <button
                        className="text-[10px] text-primary hover:underline"
                        onClick={() =>
                          resolveAnnotation.mutate({
                            documentId: document.id,
                            annotationId: a.id,
                            resolved: !a.is_resolved,
                          })
                        }
                      >
                        {a.is_resolved ? 'reopen' : 'resolve'}
                      </button>
                      {(a.user_id === user?.id || user?.role === 'finance_admin') && (
                        <button
                          className="text-[10px] text-destructive hover:underline"
                          onClick={() => deleteAnnotation.mutate({ documentId: document.id, annotationId: a.id })}
                        >
                          delete
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
            <div className="flex gap-2">
              <Textarea
                className="min-h-9"
                rows={1}
                placeholder="Add a review note…"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
              <Button
                size="sm"
                disabled={!comment.trim() || addAnnotation.isPending}
                onClick={() =>
                  addAnnotation.mutate(
                    { documentId: document.id, text: comment.trim() },
                    {
                      onSuccess: () => setComment(''),
                      onError: (err) =>
                        toast({ title: 'Could not add note', description: apiErrorMessage(err), variant: 'destructive' }),
                    }
                  )
                }
              >
                Add
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function DocumentsPage() {
  const user = useAuthStore((s) => s.user)
  const canEdit = user?.role === 'finance_admin' || user?.role === 'finance_officer'

  const [selectedFolder, setSelectedFolder] = useState('/current')
  const [fiscalYearFilter, setFiscalYearFilter] = useState<number | null>(null)
  const [accountFilter, setAccountFilter] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadFiscalYear, setUploadFiscalYear] = useState<number | null>(null)
  const [uploadDescription, setUploadDescription] = useState('')
  const [previewPaper, setPreviewPaper] = useState<WorkingPaper | null>(null)
  const [reviewPaper, setReviewPaper] = useState<WorkingPaper | null>(null)
  const [editPaper, setEditPaper] = useState<WorkingPaper | null>(null)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: fiscalYears } = useFiscalYears()
  const { data: folders, isLoading: foldersLoading } = useDocumentFolders(fiscalYearFilter)
  const { data: documents, isLoading } = useDocuments({
    folder_path: selectedFolder,
    fiscal_year_id: fiscalYearFilter,
  })
  // Leadsheet account codes linked to each document in the current filter.
  const { data: allLinks } = useAllAccountLinks(fiscalYearFilter)

  const linksByDocument = useMemo(() => {
    const m = new Map<number, AccountLink[]>()
    for (const l of allLinks ?? []) {
      const list = m.get(l.working_paper_id) ?? []
      list.push(l)
      m.set(l.working_paper_id, list)
    }
    return m
  }, [allLinks])

  const visibleDocuments = useMemo(() => {
    const q = accountFilter.trim().toLowerCase()
    if (!q) return documents ?? []
    return (documents ?? []).filter((d) =>
      (linksByDocument.get(d.id) ?? []).some((l) => l.account_code.toLowerCase().includes(q))
    )
  }, [documents, linksByDocument, accountFilter])

  const upload = useUploadDocument()
  const updateDocument = useUpdateDocument()
  const deleteDocument = useDeleteDocument()

  const openFiscalYear = useMemo(
    () => fiscalYears?.find((fy) => fy.status === 'open') ?? fiscalYears?.[0],
    [fiscalYears]
  )

  const uploadFiles = (files: FileList | null) => {
    if (!files?.length) return
    const fiscalYearId = uploadFiscalYear ?? openFiscalYear?.id
    if (!fiscalYearId) {
      toast({ title: 'Create a fiscal year before uploading documents', variant: 'destructive' })
      return
    }
    Array.from(files).forEach((file) =>
      upload.mutate(
        { file, fiscalYearId, folderPath: selectedFolder, description: uploadDescription || undefined },
        {
          onSuccess: () => toast({ title: `${file.name} uploaded` }),
          onError: (err) =>
            toast({ title: `Upload failed: ${file.name}`, description: apiErrorMessage(err), variant: 'destructive' }),
        }
      )
    )
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    uploadFiles(e.dataTransfer.files)
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Documents"
        description="Working papers, financial statements and supporting documents, with preparer and reviewer sign-off"
        actions={
          <Button size="sm" onClick={() => setUploadOpen(true)} disabled={upload.isPending || !canEdit}>
            {upload.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Upload className="mr-2 h-4 w-4" />
            )}
            Upload
          </Button>
        }
      />

      <div className="flex flex-col gap-4 md:flex-row">
        {/* Folder tree */}
        <div className="w-full shrink-0 space-y-0.5 self-start rounded-lg border bg-card p-3 md:w-60">
          <div className="flex items-center justify-between px-2 pb-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Binder</p>
          </div>
          {foldersLoading ? (
            <LoadingSpinner />
          ) : (
            folders?.map((node) => (
              <FolderNodeView key={node.path} node={node} selected={selectedFolder} onSelect={setSelectedFolder} />
            ))
          )}
        </div>

        {/* File list */}
        <div className="flex-1 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">{selectedFolder}</p>
            <div className="flex items-center gap-2">
              <Input
                className="h-8 w-44 text-xs"
                placeholder="Filter by linked account…"
                value={accountFilter}
                onChange={(e) => setAccountFilter(e.target.value)}
              />
              <select
                className="rounded-md border bg-background px-2 py-1 text-xs"
                value={fiscalYearFilter ?? ''}
                onChange={(e) => setFiscalYearFilter(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">All fiscal years</option>
                {fiscalYears?.map((fy) => (
                  <option key={fy.id} value={fy.id}>{fy.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div
            className={`rounded-lg border-2 border-dashed p-4 text-center transition-colors ${
              isDragging ? 'border-primary bg-primary/5' : 'border-muted'
            }`}
            onDragOver={(e) => {
              e.preventDefault()
              setIsDragging(true)
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
          >
            <Upload className="mx-auto mb-1 h-5 w-5 text-muted-foreground" />
            <p className="text-xs text-muted-foreground">
              Drag &amp; drop files here, or{' '}
              <button className="text-primary hover:underline" onClick={() => setUploadOpen(true)}>
                choose a folder and upload
              </button>
            </p>
          </div>

          {isLoading ? (
            <LoadingSpinner fullPage />
          ) : !documents?.length ? (
            <div className="rounded-lg border bg-card p-10 text-center">
              <Folder className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">No documents in this folder.</p>
            </div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead className="w-24">Type</TableHead>
                    <TableHead className="w-24">Size</TableHead>
                    <TableHead className="w-20">Version</TableHead>
                    <TableHead className="w-32">Sign-off</TableHead>
                    <TableHead className="w-40">Linked accounts</TableHead>
                    <TableHead className="w-40">Uploaded</TableHead>
                    <TableHead className="w-40"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleDocuments.map((doc) => (
                    <TableRow key={doc.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <FileTypeIcon type={doc.file_type} />
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium">{doc.display_name}</p>
                            {doc.description && (
                              <p className="truncate text-xs text-muted-foreground">{doc.description}</p>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{doc.file_type.toUpperCase()}</Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">{formatFileSize(doc.file_size)}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        v{doc.version_number}
                        {doc.version_count > 1 && <span className="text-xs"> / {doc.version_count}</span>}
                      </TableCell>
                      <TableCell>
                        <SignOffBadge state={doc.sign_off_state} />
                      </TableCell>
                      <TableCell>
                        {(linksByDocument.get(doc.id) ?? []).length ? (
                          <div className="flex flex-wrap gap-1">
                            {(linksByDocument.get(doc.id) ?? []).map((l) => (
                              <Badge key={l.id} variant="outline" className="font-mono text-[10px]">
                                {l.account_code}
                              </Badge>
                            ))}
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {doc.uploaded_by_username} · {formatDateTime(doc.uploaded_at)}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button size="sm" variant="ghost" onClick={() => setReviewPaper(doc)} title="Review">
                            <MessageSquare className="h-4 w-4" />
                          </Button>
                          {doc.file_type === 'pdf' && (
                            <Button size="sm" variant="ghost" onClick={() => setPreviewPaper(doc)} title="Preview">
                              <Eye className="h-4 w-4" />
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="ghost"
                            title="Download"
                            onClick={() => void downloadFile(`/v1/documents/${doc.id}/download`, doc.display_name)}
                          >
                            <Download className="h-4 w-4" />
                          </Button>
                          {canEdit && (
                            <Button
                              size="sm"
                              variant="ghost"
                              title="Edit details"
                              onClick={() => {
                                setEditPaper(doc)
                                setEditName(doc.display_name)
                                setEditDescription(doc.description ?? '')
                              }}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                          )}
                          {canEdit && (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-destructive hover:text-destructive"
                              title="Delete"
                              onClick={() => {
                                if (!confirm(`Delete ${doc.display_name} and all of its versions?`)) return
                                deleteDocument.mutate(doc.id, {
                                  onSuccess: () => toast({ title: 'Document deleted' }),
                                  onError: (err) =>
                                    toast({
                                      title: 'Could not delete',
                                      description: apiErrorMessage(err),
                                      variant: 'destructive',
                                    }),
                                })
                              }}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </div>

      {/* Upload dialog: picks the fiscal year and folder explicitly */}
      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload documents</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label>Fiscal year</Label>
              <select
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                value={uploadFiscalYear ?? openFiscalYear?.id ?? ''}
                onChange={(e) => setUploadFiscalYear(Number(e.target.value))}
              >
                {fiscalYears?.map((fy) => (
                  <option key={fy.id} value={fy.id}>{fy.label} ({fy.status})</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label>Folder</Label>
              <p className="rounded-md border bg-muted px-3 py-2 text-sm">{selectedFolder}</p>
              <p className="text-xs text-muted-foreground">Change the folder from the binder tree on the left.</p>
            </div>
            <div className="space-y-1">
              <Label>Description (optional)</Label>
              <Input value={uploadDescription} onChange={(e) => setUploadDescription(e.target.value)} />
            </div>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="block w-full text-sm"
              onChange={(e) => {
                uploadFiles(e.target.files)
                setUploadOpen(false)
                setUploadDescription('')
              }}
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setUploadOpen(false)}>Cancel</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit metadata */}
      <Dialog open={!!editPaper} onOpenChange={(o) => !o && setEditPaper(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit document</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label>Name</Label>
              <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Description</Label>
              <Textarea value={editDescription} onChange={(e) => setEditDescription(e.target.value)} />
            </div>
            {editPaper && (editPaper.preparer_signed_off_at || editPaper.reviewer_signed_off_at) && (
              <p className="text-xs text-amber-700">
                This document has been signed off. Saving will withdraw the sign-off and require re-approval.
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditPaper(null)}>Cancel</Button>
            <Button
              disabled={updateDocument.isPending || !editName.trim()}
              onClick={() => {
                if (!editPaper) return
                updateDocument.mutate(
                  { documentId: editPaper.id, display_name: editName.trim(), description: editDescription },
                  {
                    onSuccess: () => {
                      toast({ title: 'Document updated' })
                      setEditPaper(null)
                    },
                    onError: (err) =>
                      toast({ title: 'Update failed', description: apiErrorMessage(err), variant: 'destructive' }),
                  }
                )
              }}
            >
              {updateDocument.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PreviewDialog paper={previewPaper} onClose={() => setPreviewPaper(null)} />
      <DocumentDialog document={reviewPaper} onClose={() => setReviewPaper(null)} />
    </div>
  )
}
