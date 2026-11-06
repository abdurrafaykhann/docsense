import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'

function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const b = e.body as Record<string, unknown> | null
    if (b) return Object.values(b).flat().join(' ')
    return `Request failed (${e.status})`
  }
  return 'Something went wrong'
}

export default function LoginPage() {
  const { login, signup } = useAuth()
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [workspace, setWorkspace] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (mode === 'login') await login(email, password)
      else await signup(email, password, name, workspace)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const input =
    'w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-indigo-400'

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-6">
      <h1 className="text-3xl font-bold">DocSense</h1>
      <form onSubmit={submit} className="flex flex-col gap-3" aria-label={mode}>
        {mode === 'signup' && (
          <>
            <input
              className={input}
              placeholder="Your name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <input
              className={input}
              placeholder="Workspace name"
              value={workspace}
              onChange={(e) => setWorkspace(e.target.value)}
            />
          </>
        )}
        <input
          className={input}
          type="email"
          placeholder="Email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          className={input}
          type="password"
          placeholder="Password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && (
          <p role="alert" className="text-sm text-rose-400">
            {error}
          </p>
        )}
        <button
          disabled={busy}
          className="rounded-lg bg-indigo-500 px-3 py-2 font-medium hover:bg-indigo-400 disabled:opacity-50"
        >
          {mode === 'login' ? 'Log in' : 'Create account'}
        </button>
      </form>
      <button
        type="button"
        className="text-sm text-slate-400 underline"
        onClick={() => setMode(mode === 'login' ? 'signup' : 'login')}
      >
        {mode === 'login' ? 'Need an account? Sign up' : 'Have an account? Log in'}
      </button>
    </main>
  )
}
