import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import { colorFor, hueFor, project2d, shouldFallback, webgl2Supported } from '../lib/universe'
import type { UPoint } from '../lib/universe'
import UniversePage from './UniversePage'

afterEach(() => vi.restoreAllMocks())

const P = (over: Partial<UPoint>): UPoint => ({
  id: 1,
  name: 'a.png',
  x: 0,
  y: 0,
  z: 0,
  cluster: 0,
  vendor: 'Al-Mart',
  category: 'grocery',
  total: 1180,
  date: '2025-03-01',
  status: 'done',
  ...over,
})

test('colours are stable per label, distinct across labels, grey for unclustered', () => {
  expect(hueFor('grocery')).toBe(hueFor('grocery'))
  expect(hueFor('grocery')).not.toBe(hueFor('pharmacy'))
  expect(colorFor(P({ category: 'grocery' }), 'category')).toBe(
    colorFor(P({ id: 2, category: 'grocery' }), 'category'),
  )
  expect(colorFor(P({ cluster: -1 }), 'cluster')).toBe('hsl(215 12% 55%)')
  expect(colorFor(P({ vendor: null }), 'vendor')).toBe('hsl(215 12% 55%)')
})

test('fallback triggers only on sustained low frame rate', () => {
  const smooth = Array(120).fill(16.6) // ~60 fps
  const slow = Array(120).fill(50) // 20 fps
  expect(shouldFallback(smooth)).toBe(false)
  expect(shouldFallback(slow)).toBe(true)
  expect(shouldFallback(Array(30).fill(100))).toBe(false) // not enough frames yet
  expect(shouldFallback([...slow, ...Array(90).fill(16)])).toBe(false) // recovered
  expect(webgl2Supported()).toBe(false) // jsdom has no WebGL
})

test('2D projection maps the unit ball into the padded viewport', () => {
  const [a, b] = project2d(
    [P({ x: -1, y: 1, z: -1 }), P({ id: 2, x: 1, y: -1, z: 1 })],
    800,
    520,
    20,
  )
  expect([a.cx, a.cy, a.depth]).toEqual([20, 20, 0])
  expect([b.cx, b.cy, b.depth]).toEqual([780, 500, 1])
})

const DATA = {
  points: [
    P({ id: 7, name: 'inv7.png', x: -0.5, y: 0.2 }),
    P({ id: 8, name: 'inv8.png', x: 0.6, y: -0.3, cluster: 1, vendor: 'Noor', total: null }),
  ],
  clusters: [{ id: 0, label: 'rice, sugar', n: 1, centroid: [-0.5, 0.2, 0] }],
}

test('falls back to the 2D map without WebGL2; hover previews and click opens the document', async () => {
  const calls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    calls.push(`${init?.method ?? 'GET'} ${String(input)}`)
    return new Response(JSON.stringify(init?.method === 'POST' ? { points: 2 } : DATA), {
      headers: { 'Content-Type': 'application/json' },
    })
  })
  render(<UniversePage workspaceId={5} />)
  expect(await screen.findByRole('status')).toHaveTextContent('WebGL2 is not available')
  const dots = await screen.findAllByTestId('point-2d')
  expect(dots).toHaveLength(2)
  expect(screen.getByText('rice, sugar')).toBeInTheDocument()

  await userEvent.hover(dots[0])
  expect(screen.getByText(/inv7.png · Al-Mart · PKR 1,180 · 2025-03-01/)).toBeInTheDocument()
  await userEvent.click(dots[1])
  expect(location.hash).toBe('#/documents/8')

  await userEvent.click(screen.getByRole('button', { name: 'Rebuild' }))
  await waitFor(() => expect(calls).toContain('POST /api/v1/workspaces/5/universe/rebuild/'))
})

test('shows an empty state before anything is built', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ points: [], clusters: [] }), {
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  render(<UniversePage workspaceId={5} />)
  expect(await screen.findByText(/No documents placed yet/)).toBeInTheDocument()
})
