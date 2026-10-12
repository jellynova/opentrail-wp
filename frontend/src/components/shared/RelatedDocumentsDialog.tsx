import { useState } from 'react'
import { Link2, Link2Off } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { apiErrorMessage } from '@/lib/utils'
import { toast } from '@/hooks/useToast'
import { useAuthStore } from '@/store/auth'
import { useAddRelatedDocument, useRelatedDocuments, useRemoveRelatedDocument } from '@/hooks/useLeadsheets'
import type { WorkingPaper } from '@/types'

/**
 * Cross-reference one document to another ("file linking") — view existing links, detach
 * them, or pick a new document to link. Shared by the Documents page and the Leadsheets
 * document picker so "related documents" work the same way from either entry point.
 */
export function RelatedDocumentsDialog({
  document,
  allDocuments,
  onClose,
}: {
  document: WorkingPaper | null
  allDocuments: WorkingPaper[]
  onClose: () => void
}) {
  const canEdit = useAuthStore((s) => s.hasRole(['finance_admin', 'finance_officer']))
  const { data: links, isLoading } = useRelatedDocuments(document?.id ?? null)
  const addLink = useAddRelatedDocument()
  const removeLink = useRemoveRelatedDocument()
  const [pickerOpen, setPickerOpen] = useState(false)

  if (!document) return null
  const linkedIds = new Set((links ?? []).map((l) => l.related_document_id))
  const candidates = allDocuments.filter((d) => d.id !== document.id && !linkedIds.has(d.id))

  return (
    <Dialog open={!!document} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Documents related to {document.display_name}</DialogTitle>
        </DialogHeader>
        {isLoading ? (
          <LoadingSpinner />
        ) : (
          <div className="max-h-[50vh] space-y-1 overflow-y-auto">
            {!links?.length && (
              <p className="py-6 text-center text-sm text-muted-foreground">
                No related documents yet. Cross-link this one to another working paper it supports or ties to.
              </p>
            )}
            {(links ?? []).map((l) => (
              <div key={l.id} className="flex items-center justify-between gap-3 rounded-sm bg-muted/50 px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{l.related_document_display_name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {l.related_document_folder_path}
                    {l.note ? ` · ${l.note}` : ''}
                    {l.created_by_username ? ` · linked by ${l.created_by_username}` : ''}
                  </p>
                </div>
                {canEdit && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={removeLink.isPending}
                    onClick={() =>
                      removeLink.mutate(
                        { documentId: document.id, linkId: l.id },
                        {
                          onSuccess: () => toast({ title: 'Removed related document' }),
                          onError: (err) =>
                            toast({ title: 'Could not remove link', description: apiErrorMessage(err), variant: 'destructive' }),
                        }
                      )
                    }
                  >
                    <Link2Off className="mr-1 h-3.5 w-3.5" /> Remove
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
        {canEdit && (
          <>
            {pickerOpen ? (
              <div className="max-h-[30vh] space-y-1 overflow-y-auto rounded-md border p-2">
                {!candidates.length ? (
                  <p className="px-1 py-2 text-xs text-muted-foreground">No other documents available to link.</p>
                ) : (
                  candidates.map((d) => (
                    <button
                      key={d.id}
                      className="flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-left text-sm hover:bg-muted"
                      disabled={addLink.isPending}
                      onClick={() =>
                        addLink.mutate(
                          { documentId: document.id, related_document_id: d.id },
                          {
                            onSuccess: () => {
                              toast({ title: `Linked to ${d.display_name}` })
                              setPickerOpen(false)
                            },
                            onError: (err) =>
                              toast({ title: 'Could not link document', description: apiErrorMessage(err), variant: 'destructive' }),
                          }
                        )
                      }
                    >
                      <span className="truncate">{d.display_name}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">{d.folder_path}</span>
                    </button>
                  ))
                )}
              </div>
            ) : (
              <Button size="sm" variant="outline" onClick={() => setPickerOpen(true)}>
                <Link2 className="mr-2 h-4 w-4" /> Link another document
              </Button>
            )}
          </>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
