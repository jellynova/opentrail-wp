import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Folder,
  FolderOpen,
  FileText,
  FileSpreadsheet,
  File,
  Image,
  Upload,
  Download,
  Eye,
  Loader2,
} from 'lucide-react'
import { PageHeader } from '@/components/shared/PageHeader'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import api from '@/lib/api'
import { formatDate, formatFileSize, formatDateTime } from '@/lib/utils'
import { toast } from '@/hooks/useToast'
import type { WorkingPaper } from '@/types'

const FOLDER_TREE = [
  { path: '/permanent', label: 'Permanent File', icon: Folder },
  { path: '/statements', label: 'Financial Statements', icon: Folder },
  { path: '/budget', label: 'Budget Working Papers', icon: Folder },
  { path: '/current', label: 'Current Year', icon: Folder, children: [
    { path: '/current/2024', label: '2024', icon: Folder },
    { path: '/current/2025', label: '2025', icon: Folder },
  ]},
]

function FileTypeIcon({ type }: { type: WorkingPaper['file_type'] }) {
  switch (type) {
    case 'pdf': return <FileText className="h-4 w-4 text-red-500" />
    case 'xlsx': return <FileSpreadsheet className="h-4 w-4 text-green-600" />
    case 'docx': return <FileText className="h-4 w-4 text-blue-600" />
    case 'img': return <Image className="h-4 w-4 text-purple-500" />
    default: return <File className="h-4 w-4 text-muted-foreground" />
  }
}

function FolderNode({
  node,
  selected,
  onSelect,
}: {
  node: typeof FOLDER_TREE[0]
  selected: string
  onSelect: (path: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const hasChildren = 'children' in node && node.children && node.children.length > 0
  const isSelected = selected === node.path

  return (
    <div>
      <button
        onClick={() => {
          onSelect(node.path)
          if (hasChildren) setExpanded((e) => !e)
        }}
        className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-left transition-colors ${
          isSelected
            ? 'bg-primary/10 text-primary font-medium'
            : 'text-foreground hover:bg-muted'
        }`}
      >
        {expanded && hasChildren ? (
          <FolderOpen className="h-4 w-4 shrink-0" />
        ) : (
          <Folder className="h-4 w-4 shrink-0" />
        )}
        {node.label}
      </button>
      {hasChildren && expanded && (
        <div className="ml-4 mt-0.5 space-y-0.5">
          {(node as { children: typeof FOLDER_TREE }).children.map((child) => (
            <FolderNode key={child.path} node={child} selected={selected} onSelect={onSelect} />
          ))}
        </div>
      )}
    </div>
  )
}

function PreviewDialog({
  paper,
  onClose,
}: {
  paper: WorkingPaper | null
  onClose: () => void
}) {
  if (!paper) return null

  return (
    <Dialog open={!!paper} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle>{paper.display_name}</DialogTitle>
        </DialogHeader>
        {paper.file_type === 'pdf' ? (
          <iframe
            src={`/api/v1/documents/${paper.id}/download`}
            className="w-full h-[70vh] rounded border"
            title={paper.display_name}
          />
        ) : (
          <div className="flex flex-col items-center gap-4 py-8 text-muted-foreground">
            <FileTypeIcon type={paper.file_type} />
            <p className="text-sm">Preview not available for {paper.file_type} files.</p>
            <Button asChild variant="outline">
              <a href={`/api/v1/documents/${paper.id}/download`} download>
                <Download className="mr-2 h-4 w-4" />
                Download
              </a>
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export function DocumentsPage() {
  const [selectedFolder, setSelectedFolder] = useState('/permanent')
  const [previewPaper, setPreviewPaper] = useState<WorkingPaper | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const { data: documents, isLoading } = useQuery({
    queryKey: ['documents', selectedFolder],
    queryFn: () =>
      api
        .get<WorkingPaper[]>('/v1/documents', { params: { folder_path: selectedFolder } })
        .then((r) => r.data),
  })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('folder_path', selectedFolder)
      formData.append('display_name', file.name)
      return api
        .post<WorkingPaper>('/v1/documents/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        .then((r) => r.data)
    },
    onSuccess: () => {
      toast({ title: 'File uploaded successfully' })
      void queryClient.invalidateQueries({ queryKey: ['documents', selectedFolder] })
    },
    onError: () => {
      toast({ title: 'Upload failed', variant: 'destructive' })
    },
  })

  const handleFileSelect = (files: FileList | null) => {
    if (!files) return
    Array.from(files).forEach((f) => uploadMutation.mutate(f))
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    handleFileSelect(e.dataTransfer.files)
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Documents"
        description="Working papers, financial statements, and supporting documents"
        actions={
          <Button size="sm" onClick={() => fileInputRef.current?.click()} disabled={uploadMutation.isPending}>
            {uploadMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Upload className="mr-2 h-4 w-4" />
            )}
            Upload
          </Button>
        }
      />

      <div className="flex gap-4">
        {/* Folder tree */}
        <div className="w-52 shrink-0 rounded-lg border bg-card p-3 space-y-0.5 self-start">
          <p className="px-2 pb-1 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Folders
          </p>
          {FOLDER_TREE.map((node) => (
            <FolderNode key={node.path} node={node} selected={selectedFolder} onSelect={setSelectedFolder} />
          ))}
        </div>

        {/* File list + drop zone */}
        <div className="flex-1 space-y-3">
          {/* Drop zone */}
          <div
            className={`rounded-lg border-2 border-dashed p-4 text-center transition-colors ${
              isDragging ? 'border-primary bg-primary/5' : 'border-muted'
            }`}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
          >
            <Upload className="mx-auto h-5 w-5 text-muted-foreground mb-1" />
            <p className="text-xs text-muted-foreground">
              Drag &amp; drop files here, or{' '}
              <button
                className="text-primary hover:underline"
                onClick={() => fileInputRef.current?.click()}
              >
                browse
              </button>
            </p>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              multiple
              onChange={(e) => handleFileSelect(e.target.files)}
            />
          </div>

          {/* File table */}
          {isLoading ? (
            <LoadingSpinner fullPage />
          ) : !documents?.length ? (
            <div className="rounded-lg border bg-card p-10 text-center">
              <Folder className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
              <p className="text-sm text-muted-foreground">No files in this folder.</p>
            </div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Size</TableHead>
                    <TableHead>Version</TableHead>
                    <TableHead>Uploaded</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {documents.map((doc) => (
                    <TableRow key={doc.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <FileTypeIcon type={doc.file_type} />
                          <div>
                            <p className="text-sm font-medium">{doc.display_name}</p>
                            {doc.description && (
                              <p className="text-xs text-muted-foreground">{doc.description}</p>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{doc.file_type.toUpperCase()}</Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {formatFileSize(doc.file_size)}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        v{doc.version_number}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDateTime(doc.uploaded_at)}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          {doc.file_type === 'pdf' && (
                            <Button
                              size="icon"
                              variant="ghost"
                              className="h-8 w-8"
                              onClick={() => setPreviewPaper(doc)}
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          )}
                          <Button size="icon" variant="ghost" className="h-8 w-8" asChild>
                            <a href={`/api/v1/documents/${doc.id}/download`} download>
                              <Download className="h-4 w-4" />
                            </a>
                          </Button>
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

      <PreviewDialog paper={previewPaper} onClose={() => setPreviewPaper(null)} />
    </div>
  )
}
