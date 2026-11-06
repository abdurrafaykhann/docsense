export interface Bar {
  label: string
  value: number
}

const fmt = new Intl.NumberFormat('en-PK', { maximumFractionDigits: 0 })

/** Dependency-free accessible bar chart (horizontal bars, labels left, values right). */
export default function BarChart({
  data,
  title,
  unit = 'PKR',
}: {
  data: Bar[]
  title: string
  unit?: string
}) {
  const max = Math.max(...data.map((d) => d.value), 1)
  return (
    <figure className="rounded-xl border border-slate-800 bg-slate-900 p-4" aria-label={title}>
      <figcaption className="mb-3 text-sm font-semibold">{title}</figcaption>
      {data.length === 0 ? (
        <p className="text-sm text-slate-500">No data yet.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {data.map((d) => (
            <li key={d.label} className="grid grid-cols-[8rem_1fr_6rem] items-center gap-2 text-xs">
              <span className="truncate text-slate-300" title={d.label}>
                {d.label}
              </span>
              <span className="h-3 rounded bg-slate-800">
                <span
                  data-testid="bar"
                  className="block h-3 rounded bg-indigo-500"
                  style={{ width: `${Math.max(2, (d.value / max) * 100)}%` }}
                />
              </span>
              <span className="text-right tabular-nums text-slate-300">
                {unit ? `${unit} ` : ''}
                {fmt.format(d.value)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </figure>
  )
}
