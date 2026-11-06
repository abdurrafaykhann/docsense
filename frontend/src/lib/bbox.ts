export type BBox = [number, number, number, number] // normalised x0,y0,x1,y1 (0..1)

/** Absolute-position style (percentages) so the overlay survives any zoom or image size. */
const pc = (v: number) => `${Number((v * 100).toFixed(3))}%`

export function bboxToStyle(b: BBox) {
  return { left: pc(b[0]), top: pc(b[1]), width: pc(b[2] - b[0]), height: pc(b[3] - b[1]) }
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))

/** Convert two pointer positions (client px) inside `rect` to a normalised, ordered bbox. */
export function pointsToBbox(
  a: { x: number; y: number },
  b: { x: number; y: number },
  rect: { left: number; top: number; width: number; height: number },
): BBox {
  const nx = (x: number) => clamp01((x - rect.left) / rect.width)
  const ny = (y: number) => clamp01((y - rect.top) / rect.height)
  const [x0, x1] = [nx(a.x), nx(b.x)].sort((p, q) => p - q)
  const [y0, y1] = [ny(a.y), ny(b.y)].sort((p, q) => p - q)
  return [x0, y0, x1, y1]
}

export type Tone = 'ok' | 'warn' | 'bad' | 'reviewed'

export function toneFor(confidence: number, flags: string[], reviewed: boolean): Tone {
  if (reviewed) return 'reviewed'
  if (confidence < 0.7 || flags.length > 0) return confidence < 0.7 ? 'bad' : 'warn'
  return confidence >= 0.85 ? 'ok' : 'warn'
}

export const TONE_CLASS: Record<Tone, string> = {
  ok: 'border-emerald-400 bg-emerald-400/10',
  warn: 'border-amber-300 bg-amber-300/10',
  bad: 'border-rose-500 bg-rose-500/15 border-dashed',
  reviewed: 'border-sky-400 bg-sky-400/10',
}

export const REGION_COLOR: Record<string, string> = {
  vendor: '#e11d48',
  meta: '#2563eb',
  table: '#16a34a',
  totals: '#f59e0b',
  other: '#9333ea',
}
