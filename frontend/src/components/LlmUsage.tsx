import { useEffect, useState } from 'react'
import { api } from '../api/client'

interface ProviderStats {
  requests: number
  ok: number
  rate_limited: number
  error: number
  tokens_est: number
  avg_latency_s: number
}

interface Usage {
  providers: Record<string, ProviderStats>
  totals: {
    requests: number
    cache_hits: number
    cache_hit_rate: number
    rate_limited: number
    tokens_est: number
  }
  days: {
    day: string
    providers: Record<string, { ok: number; rate_limited: number; tokens_est: number }>
  }[]
}

export default function LlmUsage() {
  const [usage, setUsage] = useState<Usage | null>(null)

  useEffect(() => {
    api<Usage>('/admin/llm-usage/').then(setUsage, () => setUsage(null))
  }, [])

  if (!usage?.totals) return null
  const t = usage.totals
  return (
    <section className="flex flex-col gap-3" aria-label="LLM usage">
      <h2 className="font-semibold">LLM usage (free-tier accounting, last 14 days)</h2>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['API requests', t.requests],
          ['Cache hit rate', `${Math.round(t.cache_hit_rate * 100)}%`],
          ['Rate-limited (429)', t.rate_limited],
          ['Tokens (est.)', t.tokens_est.toLocaleString()],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-slate-800 bg-slate-900 p-3">
            <dt className="text-xs text-slate-400">{label}</dt>
            <dd className="text-lg font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
      {Object.keys(usage.providers).length === 0 ? (
        <p className="text-sm text-slate-500">No LLM calls recorded yet.</p>
      ) : (
        <table className="w-full text-sm" aria-label="LLM usage by provider">
          <thead className="text-left text-slate-400">
            <tr>
              <th>Provider</th>
              <th>Requests</th>
              <th>OK</th>
              <th>429</th>
              <th>Errors</th>
              <th>Tokens (est.)</th>
              <th>Avg latency</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(usage.providers).map(([name, p]) => (
              <tr key={name} className="border-t border-slate-800">
                <td className="py-1">{name}</td>
                <td>{p.requests}</td>
                <td>{p.ok}</td>
                <td className={p.rate_limited ? 'text-amber-300' : ''}>{p.rate_limited}</td>
                <td className={p.error ? 'text-rose-400' : ''}>{p.error}</td>
                <td>{p.tokens_est.toLocaleString()}</td>
                <td>{p.avg_latency_s}s</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
