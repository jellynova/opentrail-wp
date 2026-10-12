import { useEffect, useState } from 'react'
import { Download, File, FileSpreadsheet, FileText, Image as ImageIcon } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import api from '@/lib/api'
import { downloadFile } from '@/lib/download'
import { apiErrorMessage } from '@/lib/utils'
import type { WorkingPaper } from '@/types'

function FileTypeIcon({ type }: { type: WorkingPaper['file_type'] }) {
  switch (type) {
    case 'pdf': return <FileText className="h-8 w-8 text-red-500" />
    case 'xlsx': return <FileSpreadsheet className="h-8 w-8 text-green-600" />
    case 'docx': return <FileText className="h-8 w-8 text-blue-600" />
    case 'img': return <ImageIcon className="h-8 w-8 text-purple-500" />
    default: return <File className="h-8 w-8 text-muted-foreground" />
  }
}

/**
 * Inline preview for a working paper (the "web based" leadsheet/document viewing the
 * user asked for): PDFs and images render directly in the browser, not just a download
 * link. A plain <iframe src>/<img src> can't carry the Bearer token, so the file is
 * fetched through the authenticated API client and shown from a blob URL.
 */
function InlineFilePreview({ document: doc }: { document: WorkingPaper }) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let objectUrl: string | null = null
    let cancelled = false
    setUrl(null)
    setError(null)
    api
      .get<Blob>(`/v1/documents/${doc.id}/view`, { responseType: 'blob' })
      .then((r) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(r.data)
        setUrl(objectUrl)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(apiErrorMessage(err))
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [doc.id])

  if (error) return <p className="py-8 text-center text-sm text-destructive">Could not load preview: {error}</p>
  if (!url) return <LoadingSpinner />
  if (doc.file_type === 'img') {
    return <img src={url} alt={doc.display_name} className="mx-auto max-h-[70vh] rounded border object-contain" />
  }
  return <iframe src={url} className="h-[70vh] w-full rounded border" title={doc.display_name} />
}

/** Document viewer dialog: inline preview for pdf/img, download-only fallback otherwise. */
export function DocumentPreviewDialog({
  document,
  onClose,
}: {
  document: WorkingPaper | null
  onClose: () => void
}) {
  if (!document) return null
  const canPreviewInline = document.file_type === 'pdf' || document.file_type === 'img'
  return (
    <Dialog open={!!document} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle>{document.display_name}</DialogTitle>
        </DialogHeader>
        {canPreviewInline ? (
          <InlineFilePreview document={document} />
        ) : (
          <div className="flex flex-col items-center gap-4 py-8 text-muted-foreground">
            <FileTypeIcon type={document.file_type} />
            <p className="text-sm">No inline preview available for {document.file_type} files.</p>
            <Button
              variant="outline"
              onClick={() => void downloadFile(`/v1/documents/${document.id}/download`, document.display_name)}
            >
              <Download className="mr-2 h-4 w-4" /> Download
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
