import { STEP_ORDER } from '../api/documents'
import type { StepState } from '../api/documents'

const LABEL: Record<string, string> = {
  load: 'Load',
  cleanup: 'Clean up',
  ocr: 'OCR',
  extract: 'Extract',
  validate: 'Validate',
  save: 'Save',
}

const DOT: Record<string, string> = {
  pending: 'bg-slate-700',
  running: 'bg-amber-400 animate-pulse',
  done: 'bg-emerald-400',
  failed: 'bg-rose-500',
  skipped: 'bg-slate-500',
}

export default function Stepper({ steps }: { steps: Record<string, StepState> }) {
  return (
    <ol className="flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label="Pipeline progress">
      {STEP_ORDER.map((s) => {
        const st = steps[s]?.status ?? 'pending'
        return (
          <li
            key={s}
            className="flex items-center gap-1.5"
            data-status={st}
            title={steps[s]?.detail}
          >
            <span className={`inline-block h-2.5 w-2.5 rounded-full ${DOT[st]}`} />
            {LABEL[s]}
          </li>
        )
      })}
    </ol>
  )
}
