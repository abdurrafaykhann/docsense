import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

afterEach(() => vi.restoreAllMocks())

test('shows API status when health check succeeds', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ status: 'ok', db: true, service: 'docsense' })),
  )
  render(<App />)
  expect(await screen.findByTestId('status')).toHaveTextContent('API: ok')
})

test('shows an error when the API is unreachable', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 500 }))
  render(<App />)
  expect(await screen.findByTestId('status')).toHaveTextContent('API unreachable')
})
