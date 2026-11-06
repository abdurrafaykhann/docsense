import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import LlmUsage from './LlmUsage'

afterEach(() => vi.restoreAllMocks())

const json = (b: unknown, status = 200) =>
  new Response(JSON.stringify(b), { status, headers: { 'Content-Type': 'application/json' } })

test('shows totals and per-provider request, 429 and token counts', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    json({
      totals: { requests: 4, cache_hits: 1, cache_hit_rate: 0.2, rate_limited: 1, tokens_est: 700 },
      providers: {
        groq: {
          requests: 3,
          ok: 2,
          rate_limited: 1,
          error: 0,
          tokens_est: 400,
          avg_latency_s: 1.4,
        },
        gemini: {
          requests: 1,
          ok: 1,
          rate_limited: 0,
          error: 0,
          tokens_est: 300,
          avg_latency_s: 2,
        },
      },
      days: [],
    }),
  )
  render(<LlmUsage />)
  const table = await screen.findByRole('table', { name: 'LLM usage by provider' })
  expect(table).toHaveTextContent('groq')
  expect(table).toHaveTextContent('1.4s')
  expect(screen.getByLabelText('LLM usage')).toHaveTextContent('20%')
})

test('renders nothing for non-staff (403) and an empty state when no calls were made', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(json({}, 403))
  const { container } = render(<LlmUsage />)
  await new Promise((r) => setTimeout(r, 20))
  expect(container).toBeEmptyDOMElement()

  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    json({
      totals: { requests: 0, cache_hits: 0, cache_hit_rate: 0, rate_limited: 0, tokens_est: 0 },
      providers: {},
      days: [],
    }),
  )
  render(<LlmUsage />)
  expect(await screen.findByText('No LLM calls recorded yet.')).toBeInTheDocument()
})
