import { useEffect, useState } from 'react'
import { api } from '../api/client'

interface PRF {
  precision: number
  recall: number
  f1: number
  support: number
}

interface Metrics {
  n_docs?: number
  micro?: PRF
  per_field?: Record<string, PRF>
  line_items?: PRF | null
  total_exact_match?: number | null
  review_rate?: number
  error_catch_rate?: number | null
  auto_accept_precision?: number | null
  validation_pass_rate?: number
  mean_prompt_tokens_est?: number | null
  llm_requests?: number
}

interface Run {
  id: number
  kind: string
  dataset: string
  arm: string
  n: number
  git_sha: string
  created_at: string
  config: Record<string, unknown>
  metrics: Metrics
}

const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)

export default function EvaluationPage() {
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [open, setOpen] = useState<number | null>(null)

  useEffect(() => {
    api<Run[]>('/evaluation/runs/').then(setRuns, () => setRuns([]))
  }, [])

  if (!runs) return <p className="text-slate-400">Loading…</p>
  const selected = runs.find((r) => r.id === open)
  const th = 'px-2 py-1 text-left font-medium text-slate-400'

  return (
    <section className="flex flex-col gap-5">
      <h1 className="text-xl font-semibold">Evaluation</h1>
      {runs.length === 0 && (
        <p className="text-sm text-slate-500">
          No results yet. Run <code>python -m docsense_ml.evaluate</code> then{' '}
          <code>manage.py import_eval</code>.
        </p>
      )}
      {runs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm" aria-label="Evaluation runs">
            <thead>
              <tr>
                {[
                  'Kind',
                  'Dataset',
                  'Arm',
                  'N',
                  'Micro F1',
                  'Total exact',
                  'Review rate',
                  'Errors caught',
                  'Auto-accept precision',
                ].map((h) => (
                  <th key={h} className={th}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr
                  key={r.id}
                  className={`cursor-pointer border-t border-slate-800 hover:bg-slate-900 ${open === r.id ? 'bg-slate-900' : ''}`}
                  onClick={() => setOpen(r.id === open ? null : r.id)}
                >
                  <td className="px-2 py-1.5">{r.kind}</td>
                  <td className="px-2 py-1.5">{r.dataset}</td>
                  <td className="px-2 py-1.5">{r.arm}</td>
                  <td className="px-2 py-1.5">{r.n}</td>
                  <td className="px-2 py-1.5">{pct(r.metrics.micro?.f1)}</td>
                  <td className="px-2 py-1.5">{pct(r.metrics.total_exact_match)}</td>
                  <td className="px-2 py-1.5">{pct(r.metrics.review_rate)}</td>
                  <td className="px-2 py-1.5">{pct(r.metrics.error_catch_rate)}</td>
                  <td className="px-2 py-1.5">{pct(r.metrics.auto_accept_precision)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected?.metrics.per_field && (
        <div>
          <h2 className="mb-2 font-semibold">
            Per-field — {selected.dataset} / {selected.arm}
          </h2>
          <table className="w-full max-w-xl text-sm" aria-label="Per-field metrics">
            <thead>
              <tr>
                {['Field', 'Precision', 'Recall', 'F1', 'Support'].map((h) => (
                  <th key={h} className={th}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(selected.metrics.per_field).map(([name, m]) => (
                <tr key={name} className="border-t border-slate-800">
                  <td className="px-2 py-1">{name}</td>
                  <td className="px-2 py-1">{pct(m.precision)}</td>
                  <td className="px-2 py-1">{pct(m.recall)}</td>
                  <td className="px-2 py-1">{pct(m.f1)}</td>
                  <td className="px-2 py-1">{m.support}</td>
                </tr>
              ))}
              {selected.metrics.line_items && (
                <tr className="border-t border-slate-800">
                  <td className="px-2 py-1">line_items</td>
                  <td className="px-2 py-1">{pct(selected.metrics.line_items.precision)}</td>
                  <td className="px-2 py-1">{pct(selected.metrics.line_items.recall)}</td>
                  <td className="px-2 py-1">{pct(selected.metrics.line_items.f1)}</td>
                  <td className="px-2 py-1">{selected.metrics.line_items.support}</td>
                </tr>
              )}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-slate-500">
            ~{selected.metrics.mean_prompt_tokens_est ?? '—'} prompt tokens/doc ·{' '}
            {selected.metrics.llm_requests ?? 0} LLM requests · commit {selected.git_sha}
          </p>
        </div>
      )}
    </section>
  )
}
