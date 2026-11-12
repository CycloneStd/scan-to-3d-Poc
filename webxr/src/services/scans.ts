import { ApiRequestError, apiUrl, authenticatedFetch } from './auth'

export type ScanStatus = 'draft' | 'queued' | 'processing' | 'ready' | 'failed' | string
export type ScanAsset = {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  status: string
  created_at: string
}
export type ScanJob = {
  id: string
  scan_id: string
  status: string
  progress: number
  current_stage: string | null
  error_code: string | null
  error_message: string | null
  metrics: Record<string, unknown>
  created_at: string
  started_at: string | null
  finished_at: string | null
}
export type ScanArtifact = {
  id: string
  kind: string
  filename: string
  content_type: string
  size_bytes: number
  download_url: string | null
}
export type ScanSummary = {
  id: string
  name: string
  subject_type: string
  subject: string | null
  description: string | null
  status: ScanStatus
  created_at: string
  updated_at: string
}
export type ScanRecord = ScanSummary & {
  assets: ScanAsset[]
  jobs: ScanJob[]
  artifacts: ScanArtifact[]
}
export type ScanPayload = {
  name: string
  subject_type: string
  subject: string | null
  description: string | null
}
type UploadInit = {
  asset_id: string
  method: 'PUT'
  upload_url: string
  headers: Record<string, string>
}

function fileContentType(file: File) {
  if (file.type) return file.type
  const extension = file.name.split('.').pop()?.toLowerCase()
  const types: Record<string, string> = {
    jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
    mp4: 'video/mp4', mov: 'video/quicktime', m4v: 'video/x-m4v',
    avi: 'video/x-msvideo', mkv: 'video/x-matroska', webm: 'video/webm',
  }
  return types[extension ?? ''] ?? 'application/octet-stream'
}

async function errorMessage(response: Response) {
  const payload = await response.json().catch(() => ({})) as { detail?: unknown; message?: unknown }
  if (typeof payload.detail === 'string') return payload.detail
  if (typeof payload.message === 'string') return payload.message
  return `Request failed (${response.status}).`
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await authenticatedFetch(path, { ...init, headers })
  if (!response.ok) throw new ApiRequestError(await errorMessage(response), response.status)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

async function download(path: string) {
  const response = await authenticatedFetch(path)
  if (!response.ok) throw new ApiRequestError(await errorMessage(response), response.status)
  return response.blob()
}

export const scansApi = {
  list: (limit = 100) => requestJson<ScanRecord[]>(`/scans?limit=${limit}`),
  get: (scanId: string) => requestJson<ScanRecord>(`/scans/${encodeURIComponent(scanId)}`),
  create: (payload: ScanPayload) => requestJson<ScanSummary>('/scans', { method: 'POST', body: JSON.stringify(payload) }),
  update: (scanId: string, payload: ScanPayload) => requestJson<ScanSummary>(`/scans/${encodeURIComponent(scanId)}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  remove: (scanId: string) => requestJson<void>(`/scans/${encodeURIComponent(scanId)}`, { method: 'DELETE' }),
  async upload(scanId: string, file: File) {
    const initialized = await requestJson<UploadInit>(`/scans/${encodeURIComponent(scanId)}/uploads`, {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, content_type: fileContentType(file), size_bytes: file.size }),
    })
    const target = new URL(initialized.upload_url, apiUrl('/'))
    const apiBase = new URL(apiUrl('/'))
    const apiPrefix = apiBase.pathname.replace(/\/+$/, '')
    const localUploadPrefix = `${apiPrefix}/uploads/local/`
    const localPath = target.pathname.startsWith(localUploadPrefix)
      ? `${target.pathname.slice(apiPrefix.length)}${target.search}`
      : null
    const uploadResponse = localPath && target.origin === apiBase.origin
      ? await authenticatedFetch(localPath, { method: initialized.method, headers: initialized.headers, body: file })
      : await fetch(target, { method: initialized.method, headers: initialized.headers, body: file, credentials: 'omit', redirect: 'error' })
    if (!uploadResponse.ok) throw new ApiRequestError(`Upload failed (${uploadResponse.status}).`, uploadResponse.status)
    await requestJson(`/scans/${encodeURIComponent(scanId)}/uploads/${encodeURIComponent(initialized.asset_id)}/complete`, { method: 'POST' })
  },
  start: (scanId: string) => requestJson<ScanJob>(`/scans/${encodeURIComponent(scanId)}/jobs`, { method: 'POST' }),
  job: (jobId: string) => requestJson<ScanJob>(`/jobs/${encodeURIComponent(jobId)}`),
  artifact: (artifactId: string) => download(`/artifacts/${encodeURIComponent(artifactId)}/download`),
  sourceAsset: (assetId: string) => download(`/assets/${encodeURIComponent(assetId)}/download`),
}
