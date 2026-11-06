import type { DocStatus } from '../api/documents'

const STYLE: Record<DocStatus, string> = {
  queued: 'bg-slate-700 text-slate-200',
  processing: 'bg-amber-900 text-amber-200',
  done: 'bg-emerald-900 text-emerald-200',
  needs_review: 'bg-orange-900 text-orange-200',
  failed: 'bg-rose-900 text-rose-200',
}

export default function StatusChip({ status }: { status: DocStatus }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs ${STYLE[status]}`}>
      {status.replace('_', ' ')}
    </span>
  )
}
