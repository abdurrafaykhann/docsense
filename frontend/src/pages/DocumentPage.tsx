import { useCallback, useEffect, useState } from 'react'
import { getDocument, reprocess, watchProgress } from '../api/documents'
import type { DocDetail } from '../api/documents'
import Stepper from '../components/Stepper'
import StatusChip from '../components/StatusChip'

const pct = (c: number) => `${Math.round(c * 100)}%`
const tone = (c: number) =>
  c >= 0.85 ? 'text-emerald-400' : c >= 0.7 ? 'text-amber-300' : 'text-rose-400'

export default function DocumentPage({ workspaceId, id }: { workspaceId: number; id: number }) {
  const [doc, setDoc] = useState<DocDetail | null>(null)

  const load = useCallback(
    async () => setDoc(await getDocument(workspaceId, id)),
    [workspaceId, id],
  )

  useEffect(() => {
    void load()
    return watchProgress(id, (e) => {
      if (e.type === 'snapshot' && e.steps) {
        setDoc((d) => (d ? { ...d, progress: e.steps! } : d))
      } else if (e.type === 'progress' && e.step) {
        setDoc((d) =>
          d
            ? {
                ...d,
                status: e.doc_status ?? d.status,
                progress: {
                  ...d.progress,
                  [e.step!]: { status: e.status as never, detail: e.detail ?? '' },
                },
              }
            : d,
        )
        if (e.step === 'save' && e.status === 'done') void load()
        if (e.status === 'failed') void load()
      }
    })
  }, [id, load])

  if (!doc) return <p className="text-slate-400">Loading…</p>
  const ext = doc.extraction

  return (
    <article className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <a href="#/documents" className="text-sm text-slate-400 underline">
            ← Documents
          </a>
          <h1 className="text-xl font-semibold">{doc.name}</h1>
          <StatusChip status={doc.status} />
        </div>
        <button
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
          onClick={async () => {
            await reprocess(workspaceId, id)
            await load()
          }}
        >
          Reprocess
        </button>
      </header>

      <Stepper steps={doc.progress} />
      {doc.error && (
        <p role="alert" className="text-sm text-rose-400">
          {doc.error}
        </p>
      )}

      {ext && (
        <>
          <p className="text-sm text-slate-400">
            Overall confidence{' '}
            <strong className={tone(ext.overall_confidence)}>{pct(ext.overall_confidence)}</strong>{' '}
            · extracted with {ext.provider || 'n/a'} · version {ext.version}
          </p>

          {ext.issues.length > 0 && (
            <ul
              className="rounded-xl border border-orange-900 bg-orange-950/40 p-3 text-sm"
              aria-label="Validation issues"
            >
              {ext.issues.map((i, k) => (
                <li key={k}>
                  <span className={i.severity === 'error' ? 'text-rose-400' : 'text-amber-300'}>
                    {i.severity}
                  </span>{' '}
                  {i.message}
                </li>
              ))}
            </ul>
          )}

          <table className="w-full max-w-2xl text-sm" aria-label="Extracted fields">
            <tbody>
              {ext.fields
                .filter((f) => f.name !== 'line_items')
                .map((f) => (
                  <tr key={f.name} className="border-b border-slate-800">
                    <td className="py-1.5 pr-4 text-slate-400">{f.name}</td>
                    <td className="py-1.5 pr-4">{f.reviewed_value ?? (f.value || '—')}</td>
                    <td className={`py-1.5 pr-4 ${tone(f.confidence)}`}>{pct(f.confidence)}</td>
                    <td className="py-1.5 text-xs text-slate-500">{f.flags.join(', ')}</td>
                  </tr>
                ))}
            </tbody>
          </table>

          {ext.line_items.length > 0 && (
            <table className="w-full max-w-2xl text-sm" aria-label="Line items">
              <thead className="text-left text-slate-400">
                <tr>
                  <th>Item</th>
                  <th>Qty</th>
                  <th>Unit price</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                {ext.line_items.map((li, k) => (
                  <tr key={k} className="border-b border-slate-800">
                    <td>{li.description}</td>
                    <td>{li.quantity}</td>
                    <td>{li.unit_price}</td>
                    <td>{li.amount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </article>
  )
}
