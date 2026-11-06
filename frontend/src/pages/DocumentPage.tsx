import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  approveDocument,
  getDocument,
  pageImageUrl,
  patchField,
  putLineItems,
  reprocess,
  reviewQueue,
  watchProgress,
} from '../api/documents'
import type { DocDetail, Extraction, LineItem } from '../api/documents'
import PageViewer from '../components/PageViewer'
import StatusChip from '../components/StatusChip'
import Stepper from '../components/Stepper'
import { toneFor } from '../lib/bbox'
import type { BBox } from '../lib/bbox'

const pct = (c: number) => `${Math.round(c * 100)}%`
const tone = (c: number) =>
  c >= 0.85 ? 'text-emerald-400' : c >= 0.7 ? 'text-amber-300' : 'text-rose-400'
const input =
  'w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm outline-none focus:border-indigo-400'

export default function DocumentPage({ workspaceId, id }: { workspaceId: number; id: number }) {
  const [doc, setDoc] = useState<DocDetail | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [drawing, setDrawing] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
        if ((e.step === 'save' && e.status === 'done') || e.status === 'failed') void load()
      }
    })
  }, [id, load])

  const hasPages = (doc?.pages.length ?? 0) > 0
  useEffect(() => {
    if (!hasPages) return
    let url: string | null = null
    pageImageUrl(workspaceId, id, 1).then(
      (u) => {
        url = u
        setImageUrl(u)
      },
      () => setImageUrl(null),
    )
    return () => {
      if (url) URL.revokeObjectURL(url)
    }
  }, [hasPages, workspaceId, id, doc?.extraction?.version])

  const ext = doc?.extraction ?? null
  const setExt = (e: Extraction) => setDoc((d) => (d ? { ...d, extraction: e } : d))
  const canEdit = doc != null && doc.status !== 'processing' && doc.status !== 'queued'

  const boxes = useMemo(
    () =>
      (ext?.fields ?? [])
        .filter((f) => f.bbox && f.page === 1)
        .map((f) => ({
          name: f.name,
          bbox: f.bbox as BBox,
          tone: toneFor(f.confidence, f.flags, f.reviewed),
          selected: f.name === selected,
        })),
    [ext, selected],
  )

  async function saveField(name: string, value: string, current: string) {
    if (value === current) return
    try {
      setExt(await patchField(workspaceId, id, name, { value }))
      setError(null)
    } catch {
      setError(`Could not save ${name}`)
    }
  }

  async function saveBox(bbox: BBox) {
    if (!selected) return
    setDrawing(false)
    setExt(await patchField(workspaceId, id, selected, { bbox, page: 1 }))
  }

  async function saveItems(items: LineItem[]) {
    setExt(await putLineItems(workspaceId, id, items))
  }

  async function approve() {
    await approveDocument(workspaceId, id)
    const q = await reviewQueue(workspaceId)
    const next = q.documents.find((d) => d.id !== id)
    location.hash = next ? `#/documents/${next.id}` : '#/documents'
  }

  if (!doc) return <p className="text-slate-400">Loading…</p>

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
        <div className="flex gap-2">
          <button
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
            onClick={async () => {
              await reprocess(workspaceId, id)
              await load()
            }}
          >
            Reprocess
          </button>
          {ext && canEdit && (
            <button
              className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500"
              onClick={() => void approve()}
            >
              Approve
            </button>
          )}
        </div>
      </header>

      <Stepper steps={doc.progress} />
      {(doc.error || error) && (
        <p role="alert" className="text-sm text-rose-400">
          {doc.error || error}
        </p>
      )}

      {ext && (
        <div className="grid gap-5 lg:grid-cols-2">
          <PageViewer
            src={imageUrl}
            boxes={boxes}
            onSelect={setSelected}
            drawing={drawing}
            onDraw={(b) => void saveBox(b)}
          />

          <div className="flex flex-col gap-4">
            <p className="text-sm text-slate-400">
              Overall confidence{' '}
              <strong className={tone(ext.overall_confidence)}>
                {pct(ext.overall_confidence)}
              </strong>{' '}
              · {ext.provider || 'n/a'} · v{ext.version}
            </p>

            {ext.issues.length > 0 ? (
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
            ) : (
              <p className="text-sm text-emerald-400">All validation rules pass.</p>
            )}

            <table className="w-full text-sm" aria-label="Extracted fields">
              <tbody>
                {ext.fields
                  .filter((f) => f.name !== 'line_items')
                  .map((f) => {
                    const current = f.reviewed_value ?? f.value
                    return (
                      <tr
                        key={`${f.name}:${current}`}
                        className={`border-b border-slate-800 ${selected === f.name ? 'bg-slate-800/60' : ''}`}
                      >
                        <td className="w-28 py-1.5 pr-2 text-slate-400">{f.name}</td>
                        <td className="py-1.5 pr-2">
                          <input
                            aria-label={f.name}
                            className={input}
                            defaultValue={current}
                            disabled={!canEdit}
                            onFocus={() => setSelected(f.name)}
                            onBlur={(e) => void saveField(f.name, e.target.value, current)}
                          />
                        </td>
                        <td className={`w-12 py-1.5 pr-2 ${tone(f.confidence)}`}>
                          {f.reviewed ? '✓' : pct(f.confidence)}
                        </td>
                        <td className="py-1.5 text-xs text-slate-500">
                          {f.flags.join(', ')}
                          {selected === f.name && canEdit && (
                            <button
                              className="ml-2 underline"
                              onClick={() => setDrawing((d) => !d)}
                              aria-pressed={drawing}
                            >
                              {drawing ? 'Cancel' : 'Redraw box'}
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
              </tbody>
            </table>

            <LineItemsEditor
              key={JSON.stringify(ext.line_items)}
              items={ext.line_items}
              disabled={!canEdit}
              onSave={(items) => void saveItems(items)}
            />

            {doc.audit.length > 0 && (
              <details className="text-xs text-slate-400">
                <summary>Audit trail ({doc.audit.length})</summary>
                <ul className="mt-1 space-y-0.5">
                  {doc.audit.map((a, k) => (
                    <li key={k}>
                      {a.user} · {a.action} {JSON.stringify(a.detail)}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        </div>
      )}
    </article>
  )
}

function LineItemsEditor({
  items,
  disabled,
  onSave,
}: {
  items: LineItem[]
  disabled: boolean
  onSave: (items: LineItem[]) => void
}) {
  const [rows, setRows] = useState(items)
  const num = (v: string) => (v.trim() === '' ? null : Number(v.replace(/,/g, '')))
  const cell = (i: number, key: keyof LineItem, v: string) => {
    const next = rows.map((r, k) =>
      k === i ? { ...r, [key]: key === 'description' ? v : num(v) } : r,
    )
    setRows(next)
    return next
  }
  return (
    <table className="w-full text-sm" aria-label="Line items">
      <thead className="text-left text-slate-400">
        <tr>
          <th>Item</th>
          <th className="w-16">Qty</th>
          <th className="w-24">Unit price</th>
          <th className="w-24">Amount</th>
          <th className="w-6" />
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-b border-slate-800">
            {(['description', 'quantity', 'unit_price', 'amount'] as const).map((k) => (
              <td key={k} className="py-1 pr-1">
                <input
                  aria-label={`${k} ${i + 1}`}
                  className={input}
                  disabled={disabled}
                  defaultValue={r[k] ?? ''}
                  onBlur={(e) => {
                    if (String(r[k] ?? '') !== e.target.value) onSave(cell(i, k, e.target.value))
                  }}
                />
              </td>
            ))}
            <td>
              <button
                aria-label={`remove row ${i + 1}`}
                disabled={disabled}
                className="text-rose-400"
                onClick={() => onSave(rows.filter((_, k) => k !== i))}
              >
                ×
              </button>
            </td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <td colSpan={5} className="pt-2">
            <button
              disabled={disabled}
              className="text-xs underline"
              onClick={() =>
                onSave([
                  ...rows,
                  { description: '', quantity: null, unit_price: null, amount: null },
                ])
              }
            >
              + Add row
            </button>
          </td>
        </tr>
      </tfoot>
    </table>
  )
}
