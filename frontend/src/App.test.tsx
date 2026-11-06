import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App'
import { api, tokens } from './api/client'
import { AuthProvider } from './auth/AuthContext'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const ME = {
  user: { id: 1, email: 'a@example.com', name: 'A' },
  workspaces: [{ workspace_id: 1, name: 'Acme', slug: 'acme', role: 'owner' }],
}

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

function renderApp() {
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  )
}

test('anonymous user sees the login form and a failed login shows the error', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    json({ detail: 'No active account found with the given credentials' }, 401),
  )
  renderApp()
  await userEvent.type(screen.getByPlaceholderText('Email'), 'a@example.com')
  await userEvent.type(screen.getByPlaceholderText('Password'), 'wrong')
  await userEvent.click(screen.getByRole('button', { name: 'Log in' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('No active account')
})

test('login stores tokens, shows documents, and settings has members and keys', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    if (url.endsWith('/auth/login/')) return json({ access: 'A', refresh: 'R' })
    if (url.endsWith('/me/')) return json(ME)
    if (url.endsWith('/usage/'))
      return json({
        today: { uploads: 2, upload_bytes: 0, api_requests: 0 },
        limits: { daily_uploads: 50, max_upload_mb: 10 },
        history: {},
      })
    if (url.endsWith('/members/'))
      return json([{ id: 1, user_id: 1, email: 'a@example.com', name: 'A', role: 'owner' }])
    if (url.endsWith('/api-keys/')) return json([])
    if (url.endsWith('/documents/')) return json([])
    if (url.endsWith('/review/queue/')) return json({ count: 0, documents: [] })
    return json({}, 404)
  })
  renderApp()
  await userEvent.type(screen.getByPlaceholderText('Email'), 'a@example.com')
  await userEvent.type(screen.getByPlaceholderText('Password'), 'pw')
  await userEvent.click(screen.getByRole('button', { name: 'Log in' }))
  expect(await screen.findByText('No documents yet.')).toBeInTheDocument()
  expect(tokens.access).toBe('A')
  location.hash = '#/settings'
  expect(await screen.findByText(/Uploads: 2 \/ 50/)).toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'API keys' })).toBeInTheDocument()
})

test('api() refreshes an expired access token once and retries', async () => {
  tokens.set('old', 'R')
  const calls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    calls.push(url)
    if (url.endsWith('/auth/refresh/')) return json({ access: 'new' })
    const auth = new Headers(init?.headers).get('Authorization')
    return auth === 'Bearer new' ? json({ ok: true }) : json({ detail: 'expired' }, 401)
  })
  await waitFor(async () => expect(await api('/anything/')).toEqual({ ok: true }))
  expect(tokens.access).toBe('new')
  expect(calls.filter((c) => c.endsWith('/auth/refresh/'))).toHaveLength(1)
})
