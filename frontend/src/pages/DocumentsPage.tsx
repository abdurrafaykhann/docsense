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

  return (
    <section className="flex flex-col gap-4">
      <label
        className="flex cursor-pointer flex-col items-center gap-1 rounded-xl border-2 border-dashed border-slate-700 p-8 text-center text-sm text-slate-400 hover:border-indigo-400"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          void onFiles(e.dataTransfer.files)
        }}
      >
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
          className="rounded-xl border border-orange-900 bg-orange-950/40 p-3 text-sm text-orange-200"
        >
          {queue.count} document{queue.count > 1 ? 's' : ''} need review — review the least
          confident first →
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
              className="flex items-center justify-between p-3 hover:bg-slate-800"
            >
              <span className="truncate">{d.name}</span>
              <StatusChip status={d.status} />
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}
