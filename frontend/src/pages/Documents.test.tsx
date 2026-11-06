import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
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
  expect(screen.getByLabelText('Extracted fields')).toHaveTextContent('3500')
  expect(screen.getByLabelText('Line items')).toHaveTextContent('Widget')
})
