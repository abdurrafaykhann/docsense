import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { Extraction } from '../api/documents'
import DocumentPage from './DocumentPage'
import DocumentsPage from './DocumentsPage'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

class FakeWS {
  static last: FakeWS
  onmessage: ((m: { data: string }) => void) | null = null
  url: string
  constructor(url: string) {
    this.url = url
    FakeWS.last = this
  }
  close() {}
  emit(o: unknown) {
    this.onmessage?.({ data: JSON.stringify(o) })
  }
}

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('WebSocket', FakeWS)
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test('upload posts files and shows rejection messages', async () => {
  const calls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    calls.push(`${init?.method ?? 'GET'} ${String(input)}`)
    if (init?.method === 'POST')
      return json({ documents: [], errors: [{ name: 'x.exe', error: 'Unsupported type' }] }, 400)
    if (String(input).endsWith('/review/queue/')) return json({ count: 0, documents: [] })
    return json([])
  })
  render(<DocumentsPage workspaceId={7} />)
  const file = new File(['x'], 'x.exe', { type: 'application/x-msdownload' })
  await userEvent.upload(screen.getByLabelText('Upload documents'), file, { applyAccept: false })
  expect(await screen.findByRole('alert')).toHaveTextContent('x.exe: Unsupported type')
  expect(calls).toContain('POST /api/v1/workspaces/7/documents/')
})

test('document page shows live step progress from the websocket, then fields and issues', async () => {
  const base = {
    id: 3,
    name: 'inv.png',
    status: 'processing',
    doc_type: 'invoice',
    page_count: 0,
    size: 1,
    created_at: '',
    error: '',
    pages: [],
    extraction: null,
    audit: [],
    progress: { load: { status: 'running', detail: '' } },
  }
  const done = {
    ...base,
    status: 'needs_review',
    progress: Object.fromEntries(
      ['load', 'cleanup', 'ocr', 'extract', 'validate', 'save'].map((s) => [
        s,
        { status: 'done', detail: '' },
      ]),
    ),
    extraction: {
      id: 1,
      version: 1,
      overall_confidence: 0.62,
      needs_review: true,
      provider: 'groq',
      issues: [
        {
          code: 'total_mismatch',
          message: 'Total 3500 != subtotal + tax (3540)',
          fields: ['total'],
          severity: 'error',
        },
      ],
      line_items: [{ description: 'Widget', quantity: 2, unit_price: 500, amount: 1000 }],
      fields: [
        {
          name: 'total',
          value: '3500',
          reviewed_value: null,
          confidence: 0.3,
          flags: ['total_mismatch'],
          page: 1,
          bbox: [0, 0, 1, 1],
        },
      ],
    },
  }
  let phase = 0
  vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(phase++ === 0 ? base : done))
  render(<DocumentPage workspaceId={1} id={3} />)
  expect(await screen.findByText('inv.png')).toBeInTheDocument()
  FakeWS.last.emit({
    type: 'progress',
    step: 'ocr',
    status: 'running',
    detail: '',
    doc_status: 'processing',
  })
  await waitFor(() =>
    expect(
      screen.getByLabelText('Pipeline progress').querySelector('[data-status="running"]'),
    ).not.toBeNull(),
  )
  FakeWS.last.emit({
    type: 'progress',
    step: 'save',
    status: 'done',
    detail: '',
    doc_status: 'needs_review',
  })
  expect(await screen.findByLabelText('Validation issues')).toHaveTextContent('Total 3500')
  expect(screen.getByLabelText('total')).toHaveValue('3500')
  expect(screen.getByLabelText('description 1')).toHaveValue('Widget')
})

const REVIEW_DOC = {
  id: 9,
  name: 'r.png',
  status: 'needs_review',
  doc_type: 'invoice',
  page_count: 1,
  size: 1,
  created_at: '',
  error: '',
  audit: [],
  progress: Object.fromEntries(
    ['load', 'cleanup', 'ocr', 'extract', 'validate', 'save'].map((s) => [
      s,
      { status: 'done', detail: '' },
    ]),
  ),
  pages: [{ number: 1, width: 100, height: 200 }],
  extraction: {
    id: 1,
    version: 1,
    overall_confidence: 0.6,
    needs_review: true,
    provider: 'fake',
    issues: [
      { code: 'total_mismatch', message: 'Total mismatch', fields: ['total'], severity: 'error' },
    ],
    line_items: [],
    fields: [
      {
        name: 'total',
        value: '3500',
        reviewed_value: null,
        confidence: 0.3,
        flags: ['total_mismatch'],
        page: 1,
        bbox: [0.1, 0.8, 0.5, 0.85],
        reviewed: false,
        box_edited: false,
      },
      {
        name: 'vendor_name',
        value: 'ACME',
        reviewed_value: null,
        confidence: 0.95,
        flags: [],
        page: 1,
        bbox: [0.1, 0.1, 0.5, 0.15],
        reviewed: false,
        box_edited: false,
      },
    ],
  },
}

test('review: boxes are toned by confidence, editing a field PATCHes it, approve goes to next doc', async () => {
  vi.stubGlobal(
    'URL',
    Object.assign(URL, { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} }),
  )
  const requests: { method: string; url: string; body?: string }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    requests.push({ method: init?.method ?? 'GET', url, body: init?.body as string })
    if (url.endsWith('/image/')) return new Response('img', { status: 200 })
    if (url.endsWith('/review/queue/'))
      return json({ count: 1, documents: [{ ...REVIEW_DOC, id: 12, confidence: 0.5 }] })
    if (init?.method === 'PATCH') {
      const ext = structuredClone(REVIEW_DOC.extraction) as unknown as Extraction
      ext.fields[0] = { ...ext.fields[0], reviewed_value: '3540', reviewed: true }
      ext.issues = []
      return json(ext)
    }
    if (url.endsWith('/approve/')) return json({ ...REVIEW_DOC, status: 'done' })
    return json(REVIEW_DOC)
  })
  render(<DocumentPage workspaceId={1} id={9} />)
  expect(await screen.findByLabelText('field total')).toHaveAttribute('data-tone', 'bad')
  expect(screen.getByLabelText('field vendor_name')).toHaveAttribute('data-tone', 'ok')

  const total = screen.getByLabelText('total')
  await userEvent.clear(total)
  await userEvent.type(total, '3540')
  await userEvent.tab()

  await waitFor(() => expect(screen.getByText('All validation rules pass.')).toBeInTheDocument())
  const patch = requests.find((r) => r.method === 'PATCH')!
  expect(patch.url).toContain('/documents/9/fields/total/')
  expect(JSON.parse(patch.body!)).toEqual({ value: '3540' })
  expect(screen.getByLabelText('field total')).toHaveAttribute('data-tone', 'reviewed')

  await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
  await waitFor(() => expect(location.hash).toBe('#/documents/12'))
})
