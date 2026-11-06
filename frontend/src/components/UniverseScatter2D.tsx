import { colorFor, project2d } from '../lib/universe'
import type { ColorBy, UCluster, UPoint } from '../lib/universe'

const W = 800
const H = 520

/** Accessible 2D fallback for slow devices / no WebGL2: same data, same interactions. */
export default function UniverseScatter2D({
  points,
  clusters,
  colorBy,
  onOpen,
  onHover,
}: {
  points: UPoint[]
  clusters: UCluster[]
  colorBy: ColorBy
  onOpen: (id: number) => void
  onHover: (p: UPoint | null) => void
}) {
  const proj = project2d(points, W, H)
  const byId = new Map(points.map((p) => [p.id, p]))
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full rounded-xl border border-slate-800 bg-slate-950"
      role="img"
      aria-label="2D document map"
    >
      {proj.map((q) => {
        const p = byId.get(q.id)!
        return (
          <circle
            key={q.id}
            data-testid="point-2d"
            cx={q.cx}
            cy={q.cy}
            r={4 + q.depth * 3}
            fill={colorFor(p, colorBy)}
            opacity={0.55 + q.depth * 0.45}
            className="cursor-pointer"
            tabIndex={0}
            aria-label={p.name}
            onMouseEnter={() => onHover(p)}
            onMouseLeave={() => onHover(null)}
            onFocus={() => onHover(p)}
            onBlur={() => onHover(null)}
            onClick={() => onOpen(p.id)}
            onKeyDown={(e) => e.key === 'Enter' && onOpen(p.id)}
          />
        )
      })}
      {clusters.map((c) => {
        const [q] = project2d(
          [
            {
              id: -1,
              name: '',
              x: c.centroid[0],
              y: c.centroid[1],
              z: c.centroid[2],
              cluster: c.id,
              vendor: null,
              category: null,
              total: null,
              date: null,
              status: '',
            },
          ],
          W,
          H,
        )
        return (
          <text
            key={c.id}
            x={q.cx}
            y={q.cy - 12}
            textAnchor="middle"
            className="fill-slate-300 text-[11px]"
          >
            {c.label || `cluster ${c.id + 1}`}
          </text>
        )
      })}
    </svg>
  )
}
