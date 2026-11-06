import { useCallback, useEffect, useState } from 'react'
import { ApiError, api } from '../api/client'

interface Endpoint {
  id: number
  url: string
  events: string[]
  active: boolean
  secret?: string
}

interface Delivery {
  id: number
  event: string
  status: string
  attempts: number
  response_code: number | null
  error: string
}

const EVENTS = ['document.processed', 'document.flagged']

export default function WebhooksSection({ workspaceId }: { workspaceId: number }) {
  const [hooks, setHooks] = useState<Endpoint[]>([])
  const [url, setUrl] = useState('')
  const [events, setEvents] = useState<string[]>(EVENTS)
  const [secret, setSecret] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [log, setLog] = useState<Record<number, Delivery[]>>({})

  const base = `/workspaces/${workspaceId}/webhooks/`
  const load = useCallback(async () => {
    try {
      setHooks(await api<Endpoint[]>(base))
    } catch {
      setHooks([])
    }
  }, [base])

  useEffect(() => {
    void load()
  }, [load])

  async function create() {
    setError(null)
    try {
      const ep = await api<Endpoint>(base, { method: 'POST', json: { url, events } })
      setSecret(ep.secret ?? null)
      setUrl('')
      await load()
    } catch (e) {
      const body = e instanceof ApiError ? (e.body as Record<string, unknown> | null) : null
      setError(body ? Object.values(body).flat().join(' ') : 'Could not create webhook')
    }
  }

  async function test(id: number) {
    await api(`${base}${id}/test/`, { method: 'POST' })
    setLog({ ...log, [id]: await api<Delivery[]>(`${base}${id}/deliveries/`) })
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-4" aria-label="Webhooks">
      <h2 className="mb-2 font-semibold">Webhooks</h2>
      <p className="mb-3 text-xs text-slate-400">
        Signed POSTs (HMAC-SHA256) when a document is processed or flagged. Used by the n8n
        workflow.
      </p>
      {secret && (
        <p
          role="status"
          className="mb-3 break-all rounded bg-emerald-950 p-2 text-sm text-emerald-300"
        >
          Signing secret, copy now: <code>{secret}</code>
        </p>
      )}
      <ul className="mb-3 text-sm">
        {hooks.map((h) => (
          <li key={h.id} className="py-1">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate">
                {h.url}{' '}
                <span className="text-xs text-slate-500">({h.events.join(', ') || 'all'})</span>
              </span>
              <span className="flex gap-3 text-xs">
                <button className="underline" onClick={() => void test(h.id)}>
                  Send test
                </button>
                <button
                  className="text-rose-400 underline"
                  onClick={async () => {
                    await api(`${base}${h.id}/`, { method: 'DELETE' })
                    await load()
                  }}
                >
                  Delete
                </button>
              </span>
            </div>
            {log[h.id]?.[0] && (
              <p className="text-xs text-slate-400" data-testid={`delivery-${h.id}`}>
                Last delivery: {log[h.id][0].event} {log[h.id][0].status}
                {log[h.id][0].response_code ? ` (HTTP ${log[h.id][0].response_code})` : ''}
                {log[h.id][0].error ? ` — ${log[h.id][0].error}` : ''}
              </p>
            )}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-2">
        <input
          aria-label="Webhook URL"
          placeholder="https://your-n8n.example.com/webhook/docsense"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="min-w-64 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
        />
        {EVENTS.map((ev) => (
          <label key={ev} className="flex items-center gap-1 text-xs">
            <input
              type="checkbox"
              checked={events.includes(ev)}
              onChange={(e) =>
                setEvents(e.target.checked ? [...events, ev] : events.filter((x) => x !== ev))
              }
            />
            {ev}
          </label>
        ))}
        <button
          onClick={() => void create()}
          className="rounded-lg bg-indigo-500 px-3 py-2 text-sm font-medium"
        >
          Add webhook
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-rose-400">
          {error}
        </p>
      )}
    </section>
  )
}
