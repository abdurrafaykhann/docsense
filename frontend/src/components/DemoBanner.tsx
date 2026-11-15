import { useEffect, useState } from 'react'

/** The public demo account (sample data only; also documented in the README). */
export const DEMO_EMAIL = 'demo@docsense.dev'
export const DEMO_PASSWORD = 'docsense-demo-2025'

/** True when the server runs as the public read-only demo (no uploads, edits or retraining). */
export function useDemoMode(): boolean {
  const [demo, setDemo] = useState(false)
  useEffect(() => {
    fetch('/api/v1/health/')
      .then((r) => (r.ok ? r.json() : null))
      .then((h) => setDemo(Boolean(h?.demo_readonly)))
      .catch(() => setDemo(false))
  }, [])
  return demo
}

export default function DemoBanner({
  withLogin = false,
  onUseDemo,
}: {
  withLogin?: boolean
  onUseDemo?: () => void
}) {
  const demo = useDemoMode()
  if (!demo) return null
  return (
    <div
      role="note"
      className="flex gap-2.5 rounded-xl border border-line bg-beige px-3.5 py-2.5 text-xs leading-relaxed text-slate-300"
    >
      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-olive shadow-[0_0_0_3px_rgba(113,131,94,0.18)]" />
      <div className="flex min-w-0 flex-col gap-2">
        <p>
          <strong className="font-semibold text-espresso">Public demo, read-only.</strong> Browse
          the sample data, ask questions and run the spending agent. Uploads, edits and retraining
          run in the full local setup (see the GitHub README).
        </p>
        {withLogin && (
          <>
            {/* Each value sits alone, with no punctuation after it, so a copy-paste is exact. */}
            <dl className="grid grid-cols-[auto_1fr] items-baseline gap-x-2 gap-y-1">
              <dt>Email</dt>
              <dd>
                <code className="font-medium text-cocoa select-all">{DEMO_EMAIL}</code>
              </dd>
              <dt>Password</dt>
              <dd>
                <code className="font-medium text-cocoa select-all">{DEMO_PASSWORD}</code>
              </dd>
            </dl>
            {onUseDemo && (
              <button
                type="button"
                onClick={onUseDemo}
                className="w-fit rounded-lg border border-line bg-cream px-3 py-1.5 font-medium text-espresso hover:border-caramel"
              >
                Use the demo account
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}
