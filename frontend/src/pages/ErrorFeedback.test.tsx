import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import { ApiError, errorMessage } from '../api/client'
import AnalyticsPage from './AnalyticsPage'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const READONLY = {
  detail: 'This public demo is read-only.',
  demo_readonly: true,
}

afterEach(() => vi.restoreAllMocks())

test('errorMessage prefers the server detail and skips internal flags', () => {
  expect(errorMessage(new ApiError(403, READONLY))).toBe('This public demo is read-only.')
  expect(errorMessage(new ApiError(400, { url: ['Enter a valid URL.'], ok: false }))).toBe(
    'Enter a valid URL.',
  )
  expect(errorMessage(new ApiError(500, null), 'Could not save.')).toBe(
    'Could not save. (error 500)',
  )
  expect(errorMessage(new TypeError('Failed to fetch'))).toMatch(/Could not reach the server/)
})

test('a refused flag update is shown on the analytics page, not swallowed', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (init?.method === 'PATCH') return json(READONLY, 403)
    if (url.includes('/summary/'))
      return json({ invoices: 1, total_spend: 10, average: 10, open_flags: 1, vendors: 1 })
    if (url.includes('/spend/')) return json({ group_by: 'month', rows: [] })
    if (url.includes('/flags/'))
      return json([
        {
          id: 7,
          document_id: 1,
          document: 'a.jpg',
          kind: 'duplicate',
          severity: 'high',
          score: 1,
          details: { of: 2 },
          resolved: false,
        },
      ])
    return json({})
  })
  render(<AnalyticsPage workspaceId={1} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Resolve' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('This public demo is read-only.')
})
