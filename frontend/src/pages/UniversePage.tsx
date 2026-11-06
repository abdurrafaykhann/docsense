import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import UniverseScatter2D from '../components/UniverseScatter2D'
import { parseHashQuery } from '../hooks/useHashRoute'
import { webgl2Supported } from '../lib/universe'
import type { ColorBy, UCluster, UPoint } from '../lib/universe'

// three.js is large: load it only when the 3D view is actually shown
const UniverseScene3D = lazy(() => import('../components/UniverseScene3D'))

export default function UniversePage({ workspaceId }: { workspaceId: number }) {
  const [points, setPoints] = useState<UPoint[]>([])
  const [clusters, setClusters] = useState<UCluster[]>([])
  const [colorBy, setColorBy] = useState<ColorBy>('cluster')
  const [hover, setHover] = useState<UPoint | null>(null)
  const [mode, setMode] = useState<'3d' | '2d'>(() => (webgl2Supported() ? '3d' : '2d'))
  const [notice, setNotice] = useState<string | null>(() =>
    webgl2Supported() ? null : 'WebGL2 is not available on this device: showing the 2D map.',
  )
  const [busy, setBusy] = useState(false)
  // #/universe?force3d=1 keeps the 3D view even on a slow machine (debugging / demos)
  const force3d = parseHashQuery(location.hash).get('force3d') === '1'

  const load = useCallback(async () => {
    const d = await api<{ points: UPoint[]; clusters: UCluster[] }>(
      `/workspaces/${workspaceId}/universe/points/`,
    )
    setPoints(d.points)
    setClusters(d.clusters)
  }, [workspaceId])

  useEffect(() => {
    void load()
  }, [load])

  async function rebuild() {
    setBusy(true)
    try {
      await api(`/workspaces/${workspaceId}/universe/rebuild/`, { method: 'POST' })
      await load()
    } finally {
      setBusy(false)
    }
  }

  const open = (id: number) => {
    location.hash = `#/documents/${id}`
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Document universe</h1>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label>
            Colour by{' '}
            <select
              aria-label="Colour by"
              value={colorBy}
              onChange={(e) => setColorBy(e.target.value as ColorBy)}
              className="rounded border border-slate-700 bg-slate-900 px-2 py-1"
            >
              <option value="cluster">cluster</option>
              <option value="vendor">vendor</option>
              <option value="category">category</option>
            </select>
          </label>
          {webgl2Supported() && (
            <button
              className="rounded border border-slate-700 px-2 py-1"
              onClick={() => {
                setMode(mode === '3d' ? '2d' : '3d')
                setNotice(null)
              }}
            >
              {mode === '3d' ? 'Switch to 2D' : 'Switch to 3D'}
            </button>
          )}
          <button
            disabled={busy}
            className="rounded bg-indigo-500 px-3 py-1 font-medium disabled:opacity-50"
            onClick={() => void rebuild()}
          >
            {busy ? 'Rebuilding…' : 'Rebuild'}
          </button>
        </div>
      </div>
      {notice && (
        <p role="status" className="text-xs text-amber-300">
          {notice}
        </p>
      )}
      {points.length === 0 ? (
        <p className="text-sm text-slate-500">
          No documents placed yet. Process some documents, then press Rebuild.
        </p>
      ) : (
        <div className="relative h-[520px]">
          {mode === '3d' ? (
            <Suspense fallback={<p className="text-slate-400">Loading 3D scene…</p>}>
              <UniverseScene3D
                points={points}
                clusters={clusters}
                colorBy={colorBy}
                onOpen={open}
                onHover={setHover}
                onSlow={() => {
                  if (force3d) return
                  setMode('2d')
                  setNotice('Frame rate was low, so we switched to the lighter 2D map.')
                }}
              />
            </Suspense>
          ) : (
            <UniverseScatter2D
              points={points}
              clusters={clusters}
              colorBy={colorBy}
              onOpen={open}
              onHover={setHover}
            />
          )}
        </div>
      )}
      <p className="min-h-5 text-xs text-slate-400" aria-live="polite">
        {hover
          ? `${hover.name} · ${hover.vendor ?? 'unreviewed'}${hover.total != null ? ` · PKR ${hover.total.toLocaleString()}` : ''}${hover.date ? ` · ${hover.date}` : ''}`
          : 'Hover a dot to preview a document, click to open it.'}
      </p>
    </section>
  )
}
