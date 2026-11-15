import { useEffect, useState } from 'react'

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

export default function DemoBanner({ withLogin = false }: { withLogin?: boolean }) {
  const demo = useDemoMode()
  if (!demo) return null
  return (
    <p
      role="note"
      className="flex gap-2.5 rounded-xl border border-line bg-beige px-3.5 py-2.5 text-xs leading-relaxed text-slate-300"
    >
      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-olive shadow-[0_0_0_3px_rgba(113,131,94,0.18)]" />
      <span>
        <strong className="font-semibold text-espresso">Public demo, read-only.</strong> Browse the
        sample data, ask questions and run the spending agent. Uploads, edits and retraining run in
        the full local setup (see the GitHub README).
        {withLogin && (
          <>
            {' '}
            Log in with <code className="font-medium text-cocoa">demo@docsense.dev</code> /{' '}
            <code className="font-medium text-cocoa">docsense-demo-2025</code>.
          </>
        )}
      </span>
    </p>
  )
}
