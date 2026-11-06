import { useCallback, useEffect, useState } from 'react'
import { activateModel, getModels, rollbackModel, startRetrain } from '../api/admin'
import type { AdminModels, ModelRow } from '../api/admin'

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

  const load = useCallback(async () => {
    try {
      setData(await getModels())
    } catch {
      setError('Admin access required.')
    }
  }, [])

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
            disabled={running}
            className="rounded-lg bg-indigo-500 px-3 py-1.5 text-sm font-medium disabled:opacity-50"
            onClick={async () => {
              await startRetrain(epochs)
              await load()
            }}
          >
            {running ? 'Training…' : 'Retrain on approved documents'}
          </button>
          <button
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm"
            onClick={async () => {
              await rollbackModel()
              await load()
            }}
          >
            Roll back
          </button>
        </div>
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
                    className="rounded border border-slate-700 px-2 py-1 text-xs"
                    onClick={async () => {
                      await activateModel(m.id)
                      await load()
                    }}
                  >
                    Activate
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
