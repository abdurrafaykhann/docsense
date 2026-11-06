import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import EvaluationPage from './EvaluationPage'

afterEach(() => vi.restoreAllMocks())

test('lists runs and shows per-field metrics when a row is opened', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify([
        {
          id: 1,
          kind: 'extraction',
          dataset: 'cord',
          arm: 'regex',
          n: 100,
          git_sha: 'abc',
          created_at: '',
          config: {},
          metrics: {
            micro: { precision: 0.5, recall: 0.4, f1: 0.444, support: 10 },
            per_field: { total: { precision: 0.9, recall: 0.8, f1: 0.847, support: 100 } },
            total_exact_match: 0.8,
            review_rate: 0.3,
            error_catch_rate: 0.75,
            auto_accept_precision: 0.9,
          },
        },
      ]),
      { headers: { 'Content-Type': 'application/json' } },
    ),
  )
  render(<EvaluationPage />)
  const table = await screen.findByRole('table', { name: 'Evaluation runs' })
  expect(table).toHaveTextContent('44.4%')
  expect(table).toHaveTextContent('80.0%')
  await userEvent.click(screen.getByText('regex'))
  expect(screen.getByRole('table', { name: 'Per-field metrics' })).toHaveTextContent('84.7%')
})

test('empty state explains how to produce results', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response('[]', { headers: { 'Content-Type': 'application/json' } }),
  )
  render(<EvaluationPage />)
  expect(await screen.findByText(/No results yet/)).toBeInTheDocument()
})

test('layout runs show per-class AP50 with dashes where a class has no ground truth', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify([
        {
          id: 5,
          kind: 'layout',
          dataset: 'cord-real-test',
          arm: 'exp-c: full aug',
          n: 65,
          git_sha: 'abc',
          created_at: '',
          config: {},
          metrics: {
            map50: 0.61,
            per_class_ap50: { vendor: null, meta: null, table: 0.72, totals: 0.5, other: null },
          },
        },
      ]),
      { headers: { 'Content-Type': 'application/json' } },
    ),
  )
  render(<EvaluationPage />)
  const table = await screen.findByRole('table', { name: 'Layout runs' })
  expect(table).toHaveTextContent('exp-c: full aug')
  expect(table).toHaveTextContent('61.0%')
  expect(table).toHaveTextContent('72.0%')
  expect(table.querySelectorAll('tbody td')[4]).toHaveTextContent('—')
})
