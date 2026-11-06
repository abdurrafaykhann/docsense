import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import BarChart from '../components/BarChart'
import AnalyticsPage, { describe as describeFlag } from './AnalyticsPage'

const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })

afterEach(() => vi.restoreAllMocks())

test('bar chart scales bars to the largest value and shows an empty state', () => {
  const { rerender } = render(
    <BarChart
      title="Spend"
      data={[
        { label: 'A', value: 100 },
        { label: 'B', value: 50 },
      ]}
    />,
  )
  const bars = screen.getAllByTestId('bar')
  expect(bars[0]).toHaveStyle({ width: '100%' })
  expect(bars[1]).toHaveStyle({ width: '50%' })
  expect(screen.getByText('PKR 100')).toBeInTheDocument()
  rerender(<BarChart title="Spend" data={[]} />)
  expect(screen.getByText('No data yet.')).toBeInTheDocument()
})

test('flag descriptions explain the evidence', () => {
  const base = { id: 1, document_id: 2, document: 'd.png', severity: 'high', resolved: false }
  expect(
    describeFlag({
      ...base,
      kind: 'price_creep',
      evidence: { item: 'oil', previous_median: 520, latest: 700, increase_pct: 34.6 },
    }),
  ).toBe('oil: 520 → 700 (+34.6%)')
  expect(
    describeFlag({
      ...base,
      kind: 'exact_dup',
      evidence: { reason: 'same vendor and invoice number', duplicate_of: 5 },
    }),
  ).toContain('document #5')
})

test('analytics page renders summary, charts and lets the user resolve a flag', async () => {
  const flag = {
    id: 9,
    document_id: 4,
    document: 'inv4.png',
    kind: 'near_dup',
    severity: 'medium',
    resolved: false,
    evidence: { reason: 'same vendor, amount and close dates', duplicate_of: 3 },
  }
  const patches: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    if (init?.method === 'PATCH') {
      patches.push(url)
      return json({ ...flag, resolved: true })
    }
    if (url.includes('/summary/'))
      return json({ invoices: 9, total_spend: 10500, average: 1166, open_flags: 1, vendors: 2 })
    if (url.includes('group_by=month'))
      return json({ rows: [{ key: '2025-01', label: 'Jan 2025', total: 1770, count: 2 }] })
    if (url.includes('group_by=vendor'))
      return json({ rows: [{ key: '1', label: 'Al-Mart', total: 9000, count: 8 }] })
    if (url.includes('group_by=category'))
      return json({ rows: [{ key: 'grocery', label: 'grocery', total: 9000, count: 8 }] })
    if (url.includes('/flags/'))
      return json(patches.length ? [{ ...flag, resolved: true }] : [flag])
    return json({})
  })
  render(<AnalyticsPage workspaceId={3} />)
  expect(await screen.findByText('Jan 2025')).toBeInTheDocument()
  expect(screen.getByLabelText('Summary')).toHaveTextContent('10,500')
  expect(screen.getByLabelText('Spend by vendor')).toHaveTextContent('Al-Mart')
  const table = screen.getByRole('table', { name: 'Flagged items' })
  expect(within(table).getByText('Near duplicate')).toBeInTheDocument()
  await userEvent.click(within(table).getByRole('button', { name: 'Resolve' }))
  await waitFor(() => expect(patches).toEqual(['/api/v1/workspaces/3/analytics/flags/9/']))
  await waitFor(() => expect(screen.getByText('Nothing flagged. 🎉')).toBeInTheDocument())
})
