import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { citationHref } from '../api/chat'
import { parseHash, parseHashQuery } from '../hooks/useHashRoute'
import AskPage from './AskPage'
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

test('hash helpers split path and query', () => {
  expect(parseHash('#/documents/4?page=2&hl=0.1,0.2,0.5,0.3')).toEqual(['documents', '4'])
  expect(parseHashQuery('#/documents/4?page=2&hl=0.1,0.2,0.5,0.3').get('page')).toBe('2')
  expect(parseHashQuery('#/ask').get('page')).toBeNull()
})

test('citation links point at the page and the highlighted box', () => {
  expect(
    citationHref({
      document_id: 7,
      document: 'policy.pdf',
      page: 2,
      bbox: [0.1, 0.2, 0.9, 0.3],
      kind: 'text',
      quote: '',
    }),
  ).toBe('#/documents/7?page=2&hl=0.1,0.2,0.9,0.3')
})

test('grounded answers show citation chips; unanswerable ones are flagged and uncited', async () => {
  const replies = [
    {
      conversation_id: 1,
      answer: 'The warranty is 24 months.',
      grounded: true,
      retrieved: 3,
      citations: [
        {
          document_id: 7,
          document: 'policy.pdf',
          page: 2,
          bbox: [0.1, 0.2, 0.9, 0.3],
          kind: 'text',
          quote: 'warranty 24 months',
        },
      ],
    },
    {
      conversation_id: 1,
      answer: "I couldn't find that in your documents.",
      grounded: false,
      retrieved: 0,
      citations: [],
    },
  ]
  const bodies: unknown[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_u, init) => {
    bodies.push(JSON.parse(init?.body as string))
    return json(replies.shift())
  })
  render(<AskPage workspaceId={1} />)
  const input = screen.getByLabelText('Question')
  await userEvent.type(input, 'Warranty period?{enter}')
  const chip = await screen.findByRole('link', { name: 'policy.pdf · p.2' })
  expect(chip).toHaveAttribute('href', '#/documents/7?page=2&hl=0.1,0.2,0.9,0.3')

  await userEvent.type(input, 'Who won in 1992?{enter}')
  await waitFor(() => expect(document.querySelectorAll('[data-grounded]')).toHaveLength(2))
  const answers = document.querySelectorAll('[data-grounded]')
  expect(answers[1]).toHaveAttribute('data-grounded', 'false')
  expect(answers[1].querySelector('a')).toBeNull()
  // the second question continues the same conversation
  expect((bodies[1] as { conversation_id: number }).conversation_id).toBe(1)
})

test('opening a citation shows the right page tab image and the highlight box', async () => {
  const doc = {
    id: 7,
    name: 'policy.pdf',
    status: 'done',
    doc_type: 'invoice',
    page_count: 2,
    size: 1,
    created_at: '',
    error: '',
    audit: [],
    extraction: {
      id: 1,
      version: 1,
      overall_confidence: 1,
      needs_review: false,
      provider: 'x',
      issues: [],
      line_items: [],
      fields: [],
    },
    progress: {},
    pages: [
      { number: 1, width: 10, height: 10, regions: [] },
      { number: 2, width: 10, height: 10, regions: [] },
    ],
  }
  const urls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    urls.push(String(input))
    return String(input).endsWith('/image/') ? new Response('img') : json(doc)
  })
  render(<DocumentPage workspaceId={1} id={7} initialPage={2} highlight={[0.1, 0.2, 0.9, 0.3]} />)
  const hl = await screen.findByTestId('citation-highlight')
  expect(hl).toHaveStyle({ left: '10%', top: '20%', width: '80%', height: '10%' })
  expect(screen.getByRole('tab', { name: 'Page 2' })).toHaveAttribute('aria-selected', 'true')
  await waitFor(() => expect(urls.some((u) => u.endsWith('/pages/2/image/'))).toBe(true))
  await userEvent.click(screen.getByRole('tab', { name: 'Page 1' }))
  await waitFor(() => expect(urls.some((u) => u.endsWith('/pages/1/image/'))).toBe(true))
})
