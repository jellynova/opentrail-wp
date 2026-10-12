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
  // Prefer RFC 6266 filename* (UTF-8, for non-ASCII names) over the ASCII fallback
  const extended = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  const plain = /filename="?([^";]+)"?/.exec(disposition)
  let name = plain?.[1]
  if (extended) {
    try {
      name = decodeURIComponent(extended[1])
    } catch {
      // malformed encoding: keep the fallback
    }
  }
  const href = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = href
  link.download = name ?? fallbackName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(href)
}
