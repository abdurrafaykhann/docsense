import { useEffect, useState } from 'react'
import { fetchHealth, type Health } from './api/health'

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    fetchHealth(ctrl.signal)
      .then(setHealth)
      .catch((e: Error) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
    return () => ctrl.abort()
  }, [])

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 p-6">
      <h1 className="text-4xl font-bold tracking-tight">DocSense</h1>
      <p className="text-slate-400">AI document intelligence for invoices and receipts.</p>
      <section
        aria-label="API status"
        className="rounded-xl border border-slate-800 bg-slate-900 p-4 text-sm"
      >
        {health && (
          <p data-testid="status">
            API: <span className="text-emerald-400">{health.status}</span> · database:{' '}
            {health.db ? 'connected' : 'down'}
          </p>
        )}
        {error && (
          <p data-testid="status" className="text-rose-400">
            API unreachable: {error}
          </p>
        )}
        {!health && !error && <p className="text-slate-500">Checking API…</p>}
      </section>
    </main>
  )
}
