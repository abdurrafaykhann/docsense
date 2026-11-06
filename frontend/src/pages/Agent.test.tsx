import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import AgentPage from './AgentPage'

afterEach(() => vi.restoreAllMocks())

const RESULT = {
  answer: 'Al-Mart: PKR 6,000; Noor Pharmacy: PKR 500.',
  charts: [
    {
      title: 'Spend by vendor',
      points: [
        { label: 'Al-Mart', value: 6000 },
        { label: 'Noor Pharmacy', value: 500 },
      ],
    },
  ],
  steps: [
    {
      type: 'query',
      input: { table: 'invoices', group_by: ['vendor_name'] },
      columns: ['vendor_name', 'spend'],
      row_count: 2,
      preview: [
        { vendor_name: 'Al-Mart', spend: 6000 },
        { vendor_name: 'Noor Pharmacy', spend: 500 },
      ],
    },
    { type: 'query', input: { table: 'invoices', select: ['vendr'] }, error: 'Unknown column' },
  ],
}

test('shows the answer, a chart, and an expandable trace with the data used', async () => {
  const bodies: unknown[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_u, init) => {
    bodies.push(JSON.parse(init?.body as string))
    return new Response(JSON.stringify(RESULT), { headers: { 'Content-Type': 'application/json' } })
  })
  render(<AgentPage workspaceId={2} />)
  await userEvent.type(screen.getByLabelText('Spending question'), 'spend per vendor?{enter}')
  expect(await screen.findByTestId('agent-answer')).toHaveTextContent('PKR 6,000')
  expect(bodies).toEqual([{ question: 'spend per vendor?' }])
  expect(screen.getByLabelText('Spend by vendor')).toHaveTextContent('Noor Pharmacy')
  const data = screen.getByRole('table', { name: 'Step 1 data' })
  expect(within(data).getByText('Al-Mart')).toBeInTheDocument()
  expect(screen.getByText('failed')).toBeInTheDocument() // the second step shows its error state
  expect(screen.getByText('Unknown column')).toBeInTheDocument()
})

test('shows a friendly error when the request fails', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 500 }))
  render(<AgentPage workspaceId={2} />)
  await userEvent.type(screen.getByLabelText('Spending question'), 'x{enter}')
  expect(await screen.findByRole('alert')).toHaveTextContent('could not answer')
})
