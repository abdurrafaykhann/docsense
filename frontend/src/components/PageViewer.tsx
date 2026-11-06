import { useRef, useState } from 'react'
import { bboxToStyle, pointsToBbox, REGION_COLOR, TONE_CLASS } from '../lib/bbox'
import type { BBox, Tone } from '../lib/bbox'

export interface OverlayBox {
  name: string
  bbox: BBox
  tone: Tone
  selected: boolean
}

interface Props {
  src: string | null
  boxes: OverlayBox[]
  /** Layout regions drawn as coloured outlines with a class label. */
  regions?: { cls: string; bbox: BBox; score: number }[]
  /** When set, region boxes are clickable (layout editing). */
  regionEdit?: { selected: number | null; onSelect: (index: number) => void }
  onSelect: (name: string) => void
  /** When true, dragging on the image draws a replacement box. */
  drawing?: boolean
  onDraw?: (bbox: BBox) => void
}

export default function PageViewer({
  src,
  boxes,
  regions,
  regionEdit,
  onSelect,
  drawing,
  onDraw,
}: Props) {
  const wrap = useRef<HTMLDivElement>(null)
  const [drag, setDrag] = useState<{
    a: { x: number; y: number }
    b: { x: number; y: number }
  } | null>(null)

  const rect = () => wrap.current!.getBoundingClientRect()
  const live = drag ? pointsToBbox(drag.a, drag.b, rect()) : null

  return (
    <div
      ref={wrap}
      data-testid="page-viewer"
      className={`relative w-full select-none overflow-hidden rounded-lg border border-slate-800 bg-slate-900 ${drawing ? 'cursor-crosshair' : ''}`}
      onPointerDown={(e) => {
        if (!drawing) return
        setDrag({ a: { x: e.clientX, y: e.clientY }, b: { x: e.clientX, y: e.clientY } })
      }}
      onPointerMove={(e) => drag && setDrag({ ...drag, b: { x: e.clientX, y: e.clientY } })}
      onPointerUp={() => {
        if (!drag) return
        const box = pointsToBbox(drag.a, drag.b, rect())
        setDrag(null)
        if (box[2] - box[0] > 0.005 && box[3] - box[1] > 0.003) onDraw?.(box)
      }}
    >
      {src ? (
        <img src={src} alt="Document page" className="block w-full" draggable={false} />
      ) : (
        <div className="aspect-[3/4] w-full animate-pulse" />
      )}
      {regions?.map((r, i) => (
        <div
          key={`region-${i}`}
          data-testid={`region-${r.cls}`}
          data-selected={regionEdit?.selected === i}
          role={regionEdit ? 'button' : undefined}
          aria-label={regionEdit ? `region ${r.cls} ${i}` : undefined}
          onClick={(e) => {
            if (!regionEdit) return
            e.stopPropagation()
            regionEdit.onSelect(i)
          }}
          className={`absolute border-2 ${regionEdit?.selected === i ? 'border-solid ring-2 ring-white' : 'border-dotted'} ${regionEdit && !drawing ? '' : 'pointer-events-none'}`}
          style={{ ...bboxToStyle(r.bbox), borderColor: REGION_COLOR[r.cls] }}
        >
          <span
            className="absolute -top-0 left-0 px-1 text-[10px] font-semibold text-white"
            style={{ background: REGION_COLOR[r.cls] }}
          >
            {r.cls} {Math.round(r.score * 100)}%
          </span>
        </div>
      ))}
      {boxes.map((b) => (
        <button
          key={b.name}
          type="button"
          aria-label={`field ${b.name}`}
          data-tone={b.tone}
          data-selected={b.selected}
          onClick={(e) => {
            e.stopPropagation()
            onSelect(b.name)
          }}
          className={`absolute border-2 ${TONE_CLASS[b.tone]} ${b.selected ? 'ring-2 ring-white' : ''} ${drawing ? 'pointer-events-none' : ''}`}
          style={bboxToStyle(b.bbox)}
        />
      ))}
      {live && (
        <div
          className="pointer-events-none absolute border-2 border-white bg-white/10"
          style={bboxToStyle(live)}
        />
      )}
    </div>
  )
}
