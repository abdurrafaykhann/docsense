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
  map50?: number
  map50_95?: number
  per_class_ap50?: Record<string, number | null>
  hit_at_5?: number | null
  mrr?: number | null
  unanswerable_rejected_by_gate?: number | null
  hit_at_5_by_category?: Record<string, number>
  answers?: {
    judge_score_mean_1_5: number | null
    exact_fact_rate: number | null
    citation_accuracy: number | null
    abstention_accuracy: number | null
  }
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

const CLASS_NAMES = ['vendor', 'meta', 'table', 'totals', 'other']

const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)

export default function EvaluationPage() {
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [open, setOpen] = useState<number | null>(null)

  useEffect(() => {
    api<Run[]>('/evaluation/runs/').then(setRuns, () => setRuns([]))
  }, [])

  if (!runs) return <p className="text-slate-400">Loading…</p>
  const extraction = runs.filter((r) => r.kind === 'extraction')
  const layout = runs.filter((r) => r.kind === 'layout')
  const rag = runs.filter((r) => r.kind === 'rag')
  const selected = extraction.find((r) => r.id === open)
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
      {extraction.length > 0 && (
        <div className="overflow-x-auto">
          <h2 className="mb-2 font-semibold">Field extraction</h2>
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
              {extraction.map((r) => (
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
      {layout.length > 0 && (
        <div className="overflow-x-auto">
          <h2 className="mb-2 font-semibold">Layout model — mAP@50 per class</h2>
          <table className="w-full min-w-[720px] text-sm" aria-label="Layout runs">
            <thead>
              <tr>
                {['Experiment', 'Dataset', 'N', 'mAP@50', ...CLASS_NAMES].map((h) => (
                  <th key={h} className={th}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {layout.map((r) => (
                <tr key={r.id} className="border-t border-slate-800">
                  <td className="px-2 py-1.5">{r.arm}</td>
                  <td className="px-2 py-1.5">{r.dataset}</td>
                  <td className="px-2 py-1.5">{r.n}</td>
                  <td className="px-2 py-1.5">{pct(r.metrics.map50)}</td>
                  {CLASS_NAMES.map((c) => (
                    <td key={c} className="px-2 py-1.5">
                      {pct(r.metrics.per_class_ap50?.[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-slate-500">
            “—” = no ground truth for that class in the set (CORD annotates only table and totals).
          </p>
        </div>
      )}
      {rag.length > 0 && (
        <div className="overflow-x-auto">
          <h2 className="mb-2 font-semibold">Ask your documents (RAG)</h2>
          <table className="w-full min-w-[720px] text-sm" aria-label="RAG runs">
            <thead>
              <tr>
                {[
                  'Setup',
                  'Questions',
                  'Hit@5',
                  'MRR',
                  'Unanswerable rejected',
                  'Judge (1-5)',
                  'Citation acc.',
                  'Abstention acc.',
                ].map((h) => (
                  <th key={h} className={th}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rag.map((r) => (
                <tr key={r.id} className="border-t border-slate-800">
                  <td className="px-2 py-1.5">{r.arm}</td>
                  <td className="px-2 py-1.5">{r.n}</td>
                  <td className="px-2 py-1.5">{pct(r.metrics.hit_at_5)}</td>
                  <td className="px-2 py-1.5">{r.metrics.mrr ?? '—'}</td>
                  <td className="px-2 py-1.5">{pct(r.metrics.unanswerable_rejected_by_gate)}</td>
                  <td className="px-2 py-1.5">{r.metrics.answers?.judge_score_mean_1_5 ?? '—'}</td>
                  <td className="px-2 py-1.5">{pct(r.metrics.answers?.citation_accuracy)}</td>
                  <td className="px-2 py-1.5">{pct(r.metrics.answers?.abstention_accuracy)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-slate-500">
            Retrieval metrics need no LLM. Answer metrics (judge, citation, abstention) appear after
            running <code>manage.py eval_rag --answer-provider … --judge-provider …</code>.
          </p>
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
