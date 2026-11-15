import { useCallback, useEffect, useRef, useState } from 'react'
import { listDocuments, reviewQueue, uploadFiles } from '../api/documents'
import type { DocSummary } from '../api/documents'
import StatusChip from '../components/StatusChip'

export default function DocumentsPage({ workspaceId }: { workspaceId: number }) {
  const [docs, setDocs] = useState<DocSummary[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [queue, setQueue] = useState<{ count: number; first?: number }>({ count: 0 })
  const input = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async () => {
    setDocs(await listDocuments(workspaceId))
    const q = await reviewQueue(workspaceId)
    setQueue({ count: q.count, first: q.documents[0]?.id })
  }, [workspaceId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Poll while anything is still in flight (the detail page uses the WebSocket for live steps).
  const inFlight = docs.some((d) => d.status === 'queued' || d.status === 'processing')
  useEffect(() => {
    if (!inFlight) return
    const t = setInterval(() => void refresh(), 2000)
    return () => clearInterval(t)
  }, [inFlight, refresh])

  async function onFiles(files: FileList | null) {
    if (!files?.length) return
    setBusy(true)
    setMessage(null)
    try {
      const res = await uploadFiles(workspaceId, Array.from(files))
      if (res.errors.length) setMessage(res.errors.map((e) => `${e.name}: ${e.error}`).join('; '))
    } catch (e) {
      setMessage('Upload failed')
      console.error(e)
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
      await refresh()
    }
  }

  const done = docs.filter((d) => d.status === 'done').length
  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Documents</h1>
          <p className="mt-1 text-sm text-slate-400">
            Every invoice and receipt in this workspace, with its extraction status.
          </p>
        </div>
        {docs.length > 0 && (
          <p className="font-mono text-xs text-slate-500">
            {docs.length} documents · {done} done
          </p>
        )}
      </header>
      <label
        className="group flex cursor-pointer flex-col items-center gap-1.5 rounded-2xl border border-dashed border-white/15 bg-white/[0.02] p-8 text-center text-sm text-slate-400 hover:border-indigo-400/70 hover:bg-indigo-500/[0.04]"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          void onFiles(e.dataTransfer.files)
        }}
      >
        <span
          aria-hidden="true"
          className="mb-1 flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/15 text-lg text-indigo-300 ring-1 ring-indigo-400/25 group-hover:bg-indigo-500/25"
        >
          ↑
        </span>
        <span className="text-base text-slate-200">
          {busy ? 'Uploading…' : 'Drop invoices or receipts here, or click to choose'}
        </span>
        <span>PDF, PNG, JPG, WEBP</span>
        <input
          ref={input}
          type="file"
          multiple
          accept="application/pdf,image/png,image/jpeg,image/webp"
          capture="environment"
          className="hidden"
          aria-label="Upload documents"
          onChange={(e) => void onFiles(e.target.files)}
        />
      </label>
      {queue.count > 0 && (
        <a
          href={`#/documents/${queue.first}`}
          className="flex items-center gap-3 rounded-xl border border-orange-400/20 bg-orange-400/[0.07] px-4 py-3 text-sm text-orange-100 hover:bg-orange-400/[0.11]"
        >
          <span className="h-2 w-2 shrink-0 rounded-full bg-orange-400 shadow-[0_0_10px_#fb923c]" />
          <span>
            {queue.count} document{queue.count > 1 ? 's' : ''} need review — review the least
            confident first →
          </span>
        </a>
      )}
      {message && (
        <p role="alert" className="text-sm text-rose-400">
          {message}
        </p>
      )}
      <ul className="divide-y divide-slate-800 rounded-xl border border-slate-800 bg-slate-900">
        {docs.length === 0 && <li className="p-4 text-sm text-slate-500">No documents yet.</li>}
        {docs.map((d) => (
          <li key={d.id}>
            <a
              href={`#/documents/${d.id}`}
              className="group flex items-center gap-3 px-4 py-3 hover:bg-white/[0.04]"
            >
              <span
                aria-hidden="true"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/[0.05] font-mono text-[10px] text-slate-400 ring-1 ring-white/[0.08]"
              >
                {d.name.split('.').pop()?.slice(0, 4).toUpperCase() || 'DOC'}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-slate-100">{d.name}</span>
                <span className="block font-mono text-[11px] text-slate-500">
                  {d.created_at ? new Date(d.created_at).toLocaleDateString() : ''}
                  {d.size ? ` · ${Math.max(1, Math.round(d.size / 1024))} KB` : ''}
                </span>
              </span>
              <StatusChip status={d.status} />
              <span aria-hidden="true" className="text-slate-600 group-hover:text-slate-300">
                ›
              </span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}
