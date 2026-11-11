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
      className="rounded-lg border border-indigo-500/40 bg-indigo-950/40 px-3 py-2 text-xs text-indigo-100"
    >
      <strong>Public demo, read-only.</strong> Browse the sample data, ask questions and run the
      spending agent. Uploads, edits and retraining run in the full local setup (see the GitHub
      README).
      {withLogin && (
        <>
          {' '}
          Log in with <code className="text-white">demo@docsense.dev</code> /{' '}
          <code className="text-white">docsense-demo-2025</code>.
        </>
      )}
    </p>
  )
}
