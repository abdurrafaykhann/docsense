export interface UPoint {
  id: number
  name: string
  x: number
  y: number
  z: number
  cluster: number
  vendor: string | null
  category: string | null
  total: number | null
  date: string | null
  status: string
}

export interface UCluster {
  id: number
  label: string
  n: number
  centroid: [number, number, number]
}

export type ColorBy = 'cluster' | 'vendor' | 'category'

/** Stable colour for a category label (same label -> same colour across renders and sessions). */
export function hueFor(label: string): number {
  let h = 2166136261
  for (let i = 0; i < label.length; i++) h = Math.imul(h ^ label.charCodeAt(i), 16777619)
  return Math.abs(h) % 360
}

export function colorFor(p: UPoint, by: ColorBy): string {
  const key =
    by === 'cluster'
      ? p.cluster < 0
        ? 'unclustered'
        : `cluster-${p.cluster}`
      : by === 'vendor'
        ? (p.vendor ?? 'unknown')
        : (p.category ?? 'uncategorized')
  if (key === 'unclustered' || key === 'unknown') return 'hsl(215 12% 55%)'
  return `hsl(${hueFor(key)} 75% 62%)`
}

/**
 * Decide whether to drop to the 2D view: average frame rate below `minFps` over at least
 * `minFrames` consecutive frames (frame durations in milliseconds).
 */
export function shouldFallback(frameMs: number[], minFps = 30, minFrames = 90): boolean {
  if (frameMs.length < minFrames) return false
  const recent = frameMs.slice(-minFrames)
  const avg = recent.reduce((a, b) => a + b, 0) / recent.length
  return 1000 / avg < minFps
}

export function webgl2Supported(): boolean {
  try {
    return Boolean(document.createElement('canvas').getContext('webgl2'))
  } catch {
    return false
  }
}

/** Orthographic projection for the 2D fallback: x,y from the cloud, depth (z) shades the dot. */
export function project2d(
  points: UPoint[],
  width: number,
  height: number,
  pad = 24,
): { id: number; cx: number; cy: number; depth: number }[] {
  const sx = (width - 2 * pad) / 2
  const sy = (height - 2 * pad) / 2
  return points.map((p) => ({
    id: p.id,
    cx: pad + sx + p.x * sx,
    cy: pad + sy - p.y * sy,
    depth: (p.z + 1) / 2,
  }))
}
