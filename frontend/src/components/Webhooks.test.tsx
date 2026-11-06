import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, test, vi } from 'vitest'
import WebhooksSection from './WebhooksSection'

afterEach(() => vi.restoreAllMocks())

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

test('creates a webhook, shows the secret once, sends a test and shows the delivery result', async () => {
  let hooks: unknown[] = []
  const calls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    calls.push(`${init?.method ?? 'GET'} ${url}`)
    if (init?.method === 'POST' && url.endsWith('/webhooks/')) {
      const body = JSON.parse(init.body as string)
      const ep = { id: 4, url: body.url, events: body.events, active: true, secret: 'whsec_abc' }
      hooks = [{ ...ep, secret: undefined }]
      return json(ep, 201)
    }
    if (init?.method === 'POST' && url.endsWith('/test/'))
      return json({ id: 1, status: 'delivered' }, 202)
    if (url.endsWith('/deliveries/'))
      return json([
        { id: 1, event: 'ping', status: 'delivered', attempts: 1, response_code: 200, error: '' },
      ])
    return json(hooks)
  })
  render(<WebhooksSection workspaceId={3} />)
  await userEvent.type(
    screen.getByLabelText('Webhook URL'),
    'https://n8n.example.com/webhook/docsense',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Add webhook' }))
  expect(await screen.findByRole('status')).toHaveTextContent('whsec_abc')
  expect(await screen.findByText(/n8n.example.com/)).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: 'Send test' }))
  await waitFor(() =>
    expect(screen.getByTestId('delivery-4')).toHaveTextContent('ping delivered (HTTP 200)'),
  )
  expect(calls).toContain('POST /api/v1/workspaces/3/webhooks/4/test/')
})

test('shows the validation message when the URL is rejected (e.g. private address)', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (_u, init) =>
    init?.method === 'POST'
      ? json({ url: ['Host resolves to a non-public address (127.0.0.1)'] }, 400)
      : json([]),
  )
  render(<WebhooksSection workspaceId={3} />)
  await userEvent.type(screen.getByLabelText('Webhook URL'), 'https://localhost/h')
  await userEvent.click(screen.getByRole('button', { name: 'Add webhook' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('non-public address')
})
