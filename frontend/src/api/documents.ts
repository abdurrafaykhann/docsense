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
  reviewed: boolean
  box_edited: boolean
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

export interface AuditRow {
  action: string
  detail: Record<string, unknown>
  user: string
  at: string
}

export interface LayoutRegion {
  cls: 'vendor' | 'meta' | 'table' | 'totals' | 'other'
  bbox: [number, number, number, number]
  score: number
  source: 'model' | 'human'
}

export interface DocDetail extends DocSummary {
  audit: AuditRow[]
  progress: Record<string, StepState>
  pages: {
    number: number
    width: number
    height: number
    regions: LayoutRegion[]
  }[]
  extraction: Extraction | null
}

export const STEP_ORDER = ['load', 'cleanup', 'ocr', 'layout', 'extract', 'validate', 'save']

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

const base = (ws: number, id: number) => `/workspaces/${ws}/documents/${id}`

export const patchField = (
  ws: number,
  id: number,
  name: string,
  body: { value?: string; bbox?: number[]; page?: number },
) => api<Extraction>(`${base(ws, id)}/fields/${name}/`, { method: 'PATCH', json: body })

export const putLineItems = (ws: number, id: number, line_items: LineItem[]) =>
  api<Extraction>(`${base(ws, id)}/line-items/`, { method: 'PUT', json: { line_items } })

export const approveDocument = (ws: number, id: number) =>
  api<DocSummary>(`${base(ws, id)}/approve/`, { method: 'POST' })

export const reviewQueue = (ws: number) =>
  api<{ count: number; documents: (DocSummary & { confidence: number })[] }>(
    `/workspaces/${ws}/review/queue/`,
  )

export const putRegions = (
  ws: number,
  id: number,
  page: number,
  regions: { cls: string; bbox: number[] }[],
) =>
  api<LayoutRegion[]>(`${base(ws, id)}/pages/${page}/regions/`, {
    method: 'PUT',
    json: { regions },
  })
