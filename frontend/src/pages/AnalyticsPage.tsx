import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import BarChart from '../components/BarChart'

interface SpendRow {
  key: string
  label: string
  total: number
  count: number
}

interface Summary {
  invoices: number
  total_spend: number
  average: number
  open_flags: number
  vendors: number
}

interface FlagRow {
  id: number
  document_id: number
  document: string
  kind: string
  severity: string
  evidence: Record<string, unknown>
  resolved: boolean
}

const KIND_LABEL: Record<string, string> = {
  exact_dup: 'Exact duplicate',
  near_dup: 'Near duplicate',
  image_dup: 'Similar image',
  amount_outlier: 'Unusual amount',
  price_creep: 'Price creep',
}

export function describe(f: FlagRow): string {
  const e = f.evidence
  switch (f.kind) {
    case 'exact_dup':
    case 'near_dup':
    case 'image_dup':
      return `${String(e.reason)} (of document #${String(e.duplicate_of)})`
    case 'amount_outlier':
      return `total ${String(e.total)} vs vendor median ${String(e.vendor_median ?? '—')}${
        e.z !== undefined ? ` (robust z ${String(e.z)})` : ''
      }`
    case 'price_creep':
      return `${String(e.item)}: ${String(e.previous_median)} → ${String(e.latest)} (+${String(e.increase_pct)}%)`
    default:
      return ''
  }
}

const SEVERITY = { high: 'text-rose-400', medium: 'text-amber-300', low: 'text-slate-400' } as const

export default function AnalyticsPage({ workspaceId }: { workspaceId: number }) {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [month, setMonth] = useState<SpendRow[]>([])
  const [vendor, setVendor] = useState<SpendRow[]>([])
  const [category, setCategory] = useState<SpendRow[]>([])
  const [flags, setFlags] = useState<FlagRow[]>([])
  const [showResolved, setShowResolved] = useState(false)

  const load = useCallback(async () => {
    const base = `/workspaces/${workspaceId}/analytics`
    const spend = (g: string) => api<{ rows: SpendRow[] }>(`${base}/spend/?group_by=${g}`)
    const [s, m, v, c, f] = await Promise.all([
      api<Summary>(`${base}/summary/`),
      spend('month'),
      spend('vendor'),
      spend('category'),
      api<FlagRow[]>(`${base}/flags/`),
    ])
    setSummary(s)
    setMonth(m.rows)
    setVendor(v.rows)
    setCategory(c.rows)
    setFlags(f)
  }, [workspaceId])

  useEffect(() => {
    void load()
  }, [load])

  async function resolve(f: FlagRow) {
    await api(`/workspaces/${workspaceId}/analytics/flags/${f.id}/`, {
      method: 'PATCH',
      json: { resolved: !f.resolved },
    })
    await load()
  }

  const shown = flags.filter((f) => showResolved || !f.resolved)
  const toBars = (rows: SpendRow[]) => rows.map((r) => ({ label: r.label, value: r.total }))

  return (
    <section className="flex flex-col gap-5">
      <h1 className="text-xl font-semibold">Spending analytics</h1>
      {summary && (
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Summary">
          {[
            ['Approved invoices', summary.invoices],
            ['Total spend (PKR)', Math.round(summary.total_spend).toLocaleString()],
            ['Average invoice', Math.round(summary.average).toLocaleString()],
            ['Open flags', summary.open_flags],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-slate-800 bg-slate-900 p-3">
              <dt className="text-xs text-slate-400">{label}</dt>
              <dd className="text-lg font-semibold">{value}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <BarChart title="Spend by month" data={toBars(month)} />
        <BarChart title="Spend by vendor" data={toBars(vendor).slice(0, 10)} />
        <BarChart title="Spend by category" data={toBars(category)} />
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-semibold">Flagged items</h2>
          <label className="flex items-center gap-1.5 text-xs text-slate-400">
            <input
              type="checkbox"
              checked={showResolved}
              onChange={(e) => setShowResolved(e.target.checked)}
            />
            Show resolved
          </label>
        </div>
        <table className="w-full text-sm" aria-label="Flagged items">
          <tbody>
            {shown.length === 0 && (
              <tr>
                <td className="py-3 text-slate-500">Nothing flagged. 🎉</td>
              </tr>
            )}
            {shown.map((f) => (
              <tr key={f.id} className="border-t border-slate-800 align-top">
                <td
                  className={`py-2 pr-3 text-xs font-semibold ${SEVERITY[f.severity as keyof typeof SEVERITY] ?? ''}`}
                >
                  {f.severity}
                </td>
                <td className="py-2 pr-3">{KIND_LABEL[f.kind] ?? f.kind}</td>
                <td className="py-2 pr-3">
                  <a href={`#/documents/${f.document_id}`} className="underline">
                    {f.document}
                  </a>
                </td>
                <td className="py-2 pr-3 text-xs text-slate-400">{describe(f)}</td>
                <td className="py-2">
                  <button className="text-xs underline" onClick={() => void resolve(f)}>
                    {f.resolved ? 'Reopen' : 'Resolve'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
