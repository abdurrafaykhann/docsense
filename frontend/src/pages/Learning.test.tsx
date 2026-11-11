import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import AdminPage from './AdminPage'
import DocumentPage from './DocumentPage'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

class FakeWS {
  onmessage: ((m: { data: string }) => void) | null = null
  close() {}
}

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('WebSocket', FakeWS)
  vi.stubGlobal(
    'URL',
    Object.assign(URL, { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} }),
  )
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

const steps = Object.fromEntries(
  ['load', 'cleanup', 'ocr', 'layout', 'extract', 'validate', 'save'].map((s) => [
    s,
    { status: 'done', detail: '' },
  ]),
)

const DOC = {
  id: 4,
  name: 'r.png',
  status: 'needs_review',
  doc_type: 'invoice',
  page_count: 1,
  size: 1,
  created_at: '',
  error: '',
  audit: [],
  progress: steps,
  pages: [
    {
      number: 1,
      width: 100,
      height: 200,
      regions: [
        { cls: 'table', bbox: [0.05, 0.3, 0.95, 0.6], score: 0.9, source: 'model' },
        { cls: 'totals', bbox: [0.5, 0.65, 0.95, 0.8], score: 0.7, source: 'model' },
      ],
    },
  ],
  extraction: {
    id: 1,
    version: 1,
    overall_confidence: 0.9,
    needs_review: true,
    provider: 'fake',
    issues: [],
    line_items: [],
    fields: [],
  },
}

test('layout editor: delete a region, draw a new one, save sends the full list', async () => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    left: 0,
    top: 0,
    width: 100,
    height: 200,
    right: 100,
    bottom: 200,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  })
  const puts: unknown[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.endsWith('/image/')) return new Response('img')
    if (init?.method === 'PUT') {
      puts.push(JSON.parse(init.body as string))
      return json([])
    }
    return json(DOC)
  })
  render(<DocumentPage workspaceId={1} id={4} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Edit layout' }))
  expect(screen.getByLabelText('Layout editor')).toBeInTheDocument()

  // select + delete the totals region
  await userEvent.click(screen.getByLabelText('region totals 1'))
  await userEvent.click(screen.getByRole('button', { name: 'Delete selected' }))
  expect(screen.queryByTestId('region-totals')).toBeNull()

  // draw a new 'vendor' region by dragging on the page
  await userEvent.selectOptions(screen.getByLabelText('New region class'), 'vendor')
  const viewer = screen.getByTestId('page-viewer')
  fireEvent.pointerDown(viewer, { clientX: 10, clientY: 10 })
  fireEvent.pointerMove(viewer, { clientX: 90, clientY: 50 })
  fireEvent.pointerUp(viewer)
  expect(screen.getByTestId('region-vendor')).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: 'Save layout' }))
  await waitFor(() => expect(puts).toHaveLength(1))
  const sent = (puts[0] as { regions: { cls: string; bbox: number[] }[] }).regions
  expect(sent.map((r) => r.cls)).toEqual(['table', 'vendor'])
  expect(sent[1].bbox).toEqual([0.1, 0.05, 0.9, 0.25])
})

const MODELS = {
  feedback: { samples: 12, corrected: 7 },
  jobs: [{ id: 3, status: 'done', epochs: 5, log: '', result: null }],
  models: [
    {
      id: 2,
      name: 'layout-20250101-j3',
      is_active: false,
      created_at: '',
      n_feedback: 12,
      notes: '',
      parent: 'layout-base',
      metrics: {
        previous: { 'synthetic-hard': { map50: 0.5, per_class_ap50: {} } },
        new: { 'synthetic-hard': { map50: 0.58, per_class_ap50: {} } },
        deltas: { 'synthetic-hard': 0.08 },
        recommend_activate: true,
      },
    },
  ],
}

test('admin page shows the old-vs-new comparison and activates a model', async () => {
  const calls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    calls.push(`${init?.method ?? 'GET'} ${url}`)
    if (url.includes('/llm-usage/')) return json({}, 403)
    return json(url.includes('/activate/') ? { ...MODELS.models[0], is_active: true } : MODELS)
  })
  render(<AdminPage />)
  const table = await screen.findByRole('table', { name: 'Models' })
  expect(table).toHaveTextContent('50.0% → 58.0% (+8.0 pts)')
  expect(table).toHaveTextContent('✓ recommended')
  expect(screen.getByText(/Approved documents so far/)).toHaveTextContent('12')
  await userEvent.click(screen.getByRole('button', { name: 'Activate' }))
  expect(calls).toContain('POST /api/v1/admin/models/2/activate/')
})

test('admin page shows an error for non-staff users', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(json({ detail: 'forbidden' }, 403))
  render(<AdminPage />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Admin access required')
})

test('a refused admin action shows the server message instead of failing silently', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (url.includes('/llm-usage/')) return json({}, 403)
    if (url.includes('/retrain/') && init?.method === 'POST')
      return json({ detail: 'A retraining job is already running.' }, 400)
    return json(MODELS)
  })
  render(<AdminPage />)
  await userEvent.click(await screen.findByRole('button', { name: /Retrain on approved/ }))
  expect(await screen.findByRole('status')).toHaveTextContent(
    'A retraining job is already running.',
  )
})

test('in the public demo the admin actions are disabled and explained', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.includes('/health/')) return json({ status: 'ok', demo_readonly: true })
    if (url.includes('/llm-usage/')) return json({}, 403)
    return json(MODELS)
  })
  render(<AdminPage />)
  expect(await screen.findByText(/switched off in the public demo/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Retrain on approved/ })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Activate' })).toBeDisabled()
})

test('roll back is disabled when no retrained model is active', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) =>
    String(input).includes('/llm-usage/') ? json({}, 403) : json(MODELS),
  )
  render(<AdminPage />)
  expect(await screen.findByRole('button', { name: 'Roll back' })).toBeDisabled()
})
