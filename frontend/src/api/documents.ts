import { api, ApiError, tokens } from './client'

export type DocStatus = 'queued' | 'processing' | 'needs_review' | 'done' | 'failed'

export interface DocSummary {
  id: number
  name: string
  status: DocStatus
  doc_type: string
  page_count: number
  size: number
  created_at: string
  error: string
}

export interface FieldRow {
  name: string
  value: string
  reviewed_value: string | null
  confidence: number
  flags: string[]
  page: number | null
  bbox: [number, number, number, number] | null
}

export interface Issue {
  code: string
  message: string
  fields: string[]
  severity: 'error' | 'warn'
}

export interface LineItem {
  description: string | null
  quantity: number | null
  unit_price: number | null
  amount: number | null
}

export interface Extraction {
  id: number
  version: number
  overall_confidence: number
  needs_review: boolean
  provider: string
  issues: Issue[]
  line_items: LineItem[]
  fields: FieldRow[]
}

export interface StepState {
  status: 'pending' | 'running' | 'done' | 'failed' | 'skipped'
  detail: string
}

export interface DocDetail extends DocSummary {
  progress: Record<string, StepState>
  pages: { number: number; width: number; height: number }[]
  extraction: Extraction | null
}

export const STEP_ORDER = ['load', 'cleanup', 'ocr', 'extract', 'validate', 'save']

export const listDocuments = (ws: number) => api<DocSummary[]>(`/workspaces/${ws}/documents/`)
export const getDocument = (ws: number, id: number) =>
  api<DocDetail>(`/workspaces/${ws}/documents/${id}/`)
export const reprocess = (ws: number, id: number) =>
  api<DocSummary>(`/workspaces/${ws}/documents/${id}/reprocess/`, { method: 'POST' })

export interface UploadResult {
  documents: DocSummary[]
  errors: { name: string; error: string }[]
}

export async function uploadFiles(ws: number, files: File[]): Promise<UploadResult> {
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  try {
    return await api<UploadResult>(`/workspaces/${ws}/documents/`, { method: 'POST', body: form })
  } catch (e) {
    // Nothing accepted: the API still reports per-file reasons in the body.
    const body = e instanceof ApiError ? (e.body as Partial<UploadResult> | null) : null
    if (body?.errors) return { documents: body.documents ?? [], errors: body.errors }
    throw e
  }
}

/** Page images need the Authorization header, so fetch as a blob URL. */
export async function pageImageUrl(ws: number, id: number, page: number): Promise<string> {
  const res = await fetch(`/api/v1/workspaces/${ws}/documents/${id}/pages/${page}/image/`, {
    headers: { Authorization: `Bearer ${tokens.access}` },
  })
  if (!res.ok) throw new Error('image unavailable')
  return URL.createObjectURL(await res.blob())
}

/** Live pipeline progress over WebSocket; returns a disposer. */
export function watchProgress(
  id: number,
  onEvent: (e: {
    type: string
    step?: string
    status?: string
    detail?: string
    doc_status?: DocStatus
    steps?: Record<string, StepState>
  }) => void,
): () => void {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/ws/documents/${id}/?token=${tokens.access}`)
  ws.onmessage = (m) => onEvent(JSON.parse(m.data))
  return () => ws.close()
}
