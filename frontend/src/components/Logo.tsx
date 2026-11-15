/** DocSense mark: a folded cream document on a cocoa tile, with two extraction lines. */
export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="ds-tile" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#8a6a50" />
          <stop offset="1" stopColor="#5a4230" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#ds-tile)" />
      <rect
        x="0.5"
        y="0.5"
        width="31"
        height="31"
        rx="8.5"
        fill="none"
        stroke="#ffffff"
        strokeOpacity="0.12"
      />
      <path
        d="M10 8.5h8.2l4.3 4.3V23a1.5 1.5 0 0 1-1.5 1.5H10A1.5 1.5 0 0 1 8.5 23V10A1.5 1.5 0 0 1 10 8.5Z"
        fill="#fffdf9"
      />
      <path
        d="M18 8.5v3.4c0 .5.4.9.9.9h3.6"
        fill="none"
        stroke="#6b4f3a"
        strokeOpacity="0.25"
        strokeWidth="1.2"
      />
      <rect x="11.5" y="15.5" width="8" height="1.6" rx=".8" fill="#a67c5b" fillOpacity="0.8" />
      <rect x="11.5" y="18.8" width="5.5" height="1.6" rx=".8" fill="#71835e" />
    </svg>
  )
}
