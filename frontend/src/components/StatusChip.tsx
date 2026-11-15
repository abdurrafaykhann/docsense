import type { DocStatus } from '../api/documents'

const STYLE: Record<DocStatus, { chip: string; dot: string }> = {
  queued: { chip: 'bg-white/[0.06] text-slate-300 ring-white/10', dot: 'bg-slate-400' },
  processing: {
    chip: 'bg-amber-400/10 text-amber-200 ring-amber-400/25',
    dot: 'bg-amber-300 animate-pulse',
  },
  done: { chip: 'bg-emerald-400/10 text-emerald-200 ring-emerald-400/25', dot: 'bg-emerald-400' },
  needs_review: {
    chip: 'bg-orange-400/10 text-orange-200 ring-orange-400/25',
    dot: 'bg-orange-400',
  },
  failed: { chip: 'bg-rose-400/10 text-rose-200 ring-rose-400/25', dot: 'bg-rose-400' },
}

export default function StatusChip({ status }: { status: DocStatus }) {
  const s = STYLE[status]
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${s.chip}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} aria-hidden="true" />
      {status.replace('_', ' ')}
    </span>
  )
}
