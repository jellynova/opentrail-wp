import api from './api'

/** Download a file from an authenticated API endpoint (GET or POST) and save it in the browser. */
export async function downloadFile(
  url: string,
  fallbackName: string,
  options: { method?: 'get' | 'post'; params?: Record<string, unknown>; data?: unknown } = {}
): Promise<void> {
  const response = await api.request<Blob>({
    url,
    method: options.method ?? 'get',
    params: options.params,
    data: options.data,
    responseType: 'blob',
  })
  const disposition = String(response.headers['content-disposition'] ?? '')
  const match = /filename="?([^";]+)"?/.exec(disposition)
  const href = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = href
  link.download = match?.[1] ?? fallbackName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
}
