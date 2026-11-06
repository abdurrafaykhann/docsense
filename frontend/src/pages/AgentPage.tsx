import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api/client'
import BarChart from '../components/BarChart'

interface Step {
  type: string
  input: Record<string, unknown>
  columns?: string[]
  row_count?: number
  preview?: Record<string, unknown>[]
  error?: string
}

interface Chart {
  title: string
  points: { label: string; value: number }[]
}

interface AgentResult {
  answer: string
  steps: Step[]
  charts: Chart[]
}

const STEP_LABEL: Record<string, string> = {
  query: 'Queried your invoices',
  chart: 'Built a chart',
  price_changes: 'Compared unit prices over time',
  search: 'Searched document text',
}

function StepView({ step, index }: { step: Step; index: number }) {
  const cols = step.columns ?? []
  return (
    <details className="rounded-lg border border-slate-800 bg-slate-900 p-3 text-sm">
      <summary className="cursor-pointer">
        <span className="text-slate-400">Step {index + 1}.</span>{' '}
        {STEP_LABEL[step.type] ?? step.type}
        {step.error ? (
          <span className="ml-2 text-rose-400">failed</span>
        ) : (
          <span className="ml-2 text-slate-500">{step.row_count ?? 0} rows</span>
        )}
      </summary>
      <pre className="mt-2 overflow-x-auto rounded bg-slate-950 p-2 text-xs text-slate-300">
        {JSON.stringify(step.input, null, 1)}
      </pre>
      {step.error && <p className="mt-2 text-rose-400">{step.error}</p>}
      {cols.length > 0 && step.preview && (
        <table className="mt-2 w-full text-xs" aria-label={`Step ${index + 1} data`}>
          <thead className="text-left text-slate-400">
            <tr>
              {cols.map((c) => (
                <th key={c} className="pr-3">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {step.preview.map((r, i) => (
              <tr key={i} className="border-t border-slate-800">
                {cols.map((c) => (
                  <td key={c} className="pr-3 py-1">
                    {String(r[c] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </details>
  )
}

export default function AgentPage({ workspaceId }: { workspaceId: number }) {
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<AgentResult | null>(null)
  const [asked, setAsked] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const q = question.trim()
    if (!q) return
    setBusy(true)
    setError(null)
    setAsked(q)
    setResult(null)
    try {
      setResult(
        await api<AgentResult>(`/workspaces/${workspaceId}/agent/ask/`, {
          method: 'POST',
          json: { question: q },
        }),
      )
    } catch {
      setError('The assistant could not answer. Try rephrasing.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Spending assistant</h1>
      <form onSubmit={submit} className="flex gap-2">
        <input
          aria-label="Spending question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="How much did we spend with each vendor last quarter?"
          className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm outline-none focus:border-indigo-400"
        />
        <button
          disabled={busy}
          className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          {busy ? 'Analysing…' : 'Ask'}
        </button>
      </form>
      {error && (
        <p role="alert" className="text-sm text-rose-400">
          {error}
        </p>
      )}
      {result && (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-slate-400">“{asked}”</p>
          <div
            className="rounded-xl border border-slate-700 bg-slate-900 p-4"
            data-testid="agent-answer"
          >
            {result.answer}
          </div>
          {result.charts.map((c, i) => (
            <BarChart key={i} title={c.title} data={c.points} />
          ))}
          <h2 className="text-sm font-semibold text-slate-300">How I got this</h2>
          {result.steps.map((s, i) => (
            <StepView key={i} step={s} index={i} />
          ))}
        </div>
      )}
    </section>
  )
}
