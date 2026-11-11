import { useCallback, useEffect, useState } from 'react'
import { activateModel, getModels, rollbackModel, startRetrain } from '../api/admin'
import type { AdminModels, ModelRow } from '../api/admin'
import { ApiError } from '../api/client'
import { useDemoMode } from '../components/DemoBanner'
import LlmUsage from '../components/LlmUsage'

/** The server's own message for a failed action (it explains what to do). */
function messageOf(e: unknown): string {
  if (e instanceof ApiError) {
    const b = e.body as Record<string, unknown> | null
    if (b && typeof b.detail === 'string') return b.detail
    if (b && b.epochs) return String(b.epochs)
    return `Request failed (${e.status}).`
  }
  return 'Could not reach the server. Try again.'
}

const pct = (v: number) => `${(v * 100).toFixed(1)}%`
const card = 'rounded-xl border border-slate-800 bg-slate-900 p-4'

function Deltas({ m }: { m: ModelRow }) {
  const d = m.metrics.deltas
  if (!d) return <span className="text-slate-500">—</span>
  return (
    <ul className="text-xs">
      {Object.entries(d).map(([set, v]) => (
        <li key={set} className={v > 0 ? 'text-emerald-400' : v < 0 ? 'text-rose-400' : ''}>
          {set}: {m.metrics.previous?.[set] ? pct(m.metrics.previous[set].map50) : '?'} →{' '}
          {m.metrics.new?.[set] ? pct(m.metrics.new[set].map50) : '?'} ({v >= 0 ? '+' : ''}
          {(v * 100).toFixed(1)} pts)
        </li>
      ))}
    </ul>
  )
}

export default function AdminPage() {
  const [data, setData] = useState<AdminModels | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [epochs, setEpochs] = useState(5)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const demo = useDemoMode()

  const load = useCallback(async () => {
    try {
      setData(await getModels())
    } catch (e) {
      setError(
        e instanceof ApiError && (e.status === 401 || e.status === 403)
          ? 'Admin access required.'
          : messageOf(e),
      )
    }
  }, [])

  // Every action reports its outcome; a refusal from the server is shown, not swallowed.
  const act = async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true)
    setNotice(null)
    try {
      await fn()
      setNotice(done)
      await load()
    } catch (e) {
      setNotice(messageOf(e))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void load()
  }, [load])

  const running = data?.jobs.some((j) => j.status === 'queued' || j.status === 'running') ?? false
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => void load(), 3000)
    return () => clearInterval(t)
  }, [running, load])

  if (error)
    return (
      <p role="alert" className="text-rose-400">
        {error}
      </p>
    )
  if (!data) return <p className="text-slate-400">Loading…</p>

  return (
    <section className="flex flex-col gap-5">
      <h1 className="text-xl font-semibold">Model registry &amp; retraining</h1>
      <div className={card}>
        <p className="text-sm text-slate-300">
          Approved documents so far: <strong>{data.feedback.samples}</strong> (
          {data.feedback.corrected} with human corrections). Retraining fine-tunes the current
          layout model on them and compares old vs new before anything is activated.
        </p>
        <div className="mt-3 flex items-center gap-2">
          <label className="text-sm">
            Epochs{' '}
            <input
              type="number"
              min={1}
              max={50}
              value={epochs}
              onChange={(e) => setEpochs(Number(e.target.value))}
              className="w-16 rounded border border-slate-700 bg-slate-950 px-2 py-1"
            />
          </label>
          <button
            disabled={running || busy || demo || data.feedback.samples === 0}
            title={
              data.feedback.samples === 0 ? 'Approve some reviewed documents first' : undefined
            }
            className="rounded-lg bg-indigo-500 px-3 py-1.5 text-sm font-medium disabled:opacity-50"
            onClick={() => act(() => startRetrain(epochs), 'Retraining started.')}
          >
            {running ? 'Training…' : 'Retrain on approved documents'}
          </button>
          <button
            disabled={busy || demo || !data.models.some((m) => m.is_active)}
            title={
              data.models.some((m) => m.is_active) ? undefined : 'No retrained model is active'
            }
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm disabled:opacity-50"
            onClick={() => act(() => rollbackModel(), 'Rolled back to the previous model.')}
          >
            Roll back
          </button>
        </div>
        {demo && (
          <p className="mt-2 text-xs text-slate-400">
            Retraining is switched off in the public demo; it runs in the full local setup.
          </p>
        )}
        {notice && (
          <p role="status" className="mt-2 text-xs text-amber-300">
            {notice}
          </p>
        )}
        {data.jobs[0] && (
          <p className="mt-2 text-xs text-slate-400" data-testid="latest-job">
            Latest job #{data.jobs[0].id}: {data.jobs[0].status}
            {data.jobs[0].status === 'failed' && ` — ${data.jobs[0].log}`}
          </p>
        )}
      </div>

      <table className="w-full text-sm" aria-label="Models">
        <thead className="text-left text-slate-400">
          <tr>
            <th className="py-1">Model</th>
            <th>Trained on</th>
            <th>Change vs parent (mAP@50)</th>
            <th>Safe?</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {data.models.length === 0 && (
            <tr>
              <td colSpan={5} className="py-3 text-slate-500">
                No retrained models yet. The default weights are in use.
              </td>
            </tr>
          )}
          {data.models.map((m) => (
            <tr key={m.id} className="border-t border-slate-800 align-top">
              <td className="py-2">
                {m.name}
                {m.is_active && (
                  <span className="ml-2 rounded-full bg-emerald-900 px-2 py-0.5 text-xs text-emerald-200">
                    active
                  </span>
                )}
              </td>
              <td>{m.n_feedback} docs</td>
              <td>
                <Deltas m={m} />
              </td>
              <td>{m.metrics.recommend_activate ? '✓ recommended' : '—'}</td>
              <td>
                {!m.is_active && (
                  <button
                    disabled={busy || demo}
                    className="rounded border border-slate-700 px-2 py-1 text-xs disabled:opacity-50"
                    onClick={() => act(() => activateModel(m.id), `Activated ${m.name}.`)}
                  >
                    Activate
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <LlmUsage />
      {demo && (
        <p className="text-xs text-slate-500">
          On the hosted demo each serverless instance keeps its own short-lived log, so these counts
          reset often. Run DocSense locally to see full usage history.
        </p>
      )}
    </section>
  )
}
