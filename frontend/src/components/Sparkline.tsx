import type { PricePoint } from '../types'

interface SparklineProps {
  points: PricePoint[] | null
}

/** A tiny price polyline rendered under the verdict — not in mockup v4 (a sanctioned scope
 * addition per the T16 brief), so it has no mockup markup and no CSS class: styled entirely with
 * inline SVG attributes to keep the "no new CSS" constraint intact. Pure presentational, driven
 * entirely by `points`; App wires in `GET /api/price`'s `PricePoint[]` in T18. `null` means the
 * price hasn't loaded (or the read failed) — render nothing, NOT the "no activity" note, so a
 * pending/errored fetch is never mistaken for a genuinely dead token. */
export function Sparkline({ points }: SparklineProps) {
  if (points == null) {
    return null
  }
  if (points.length < 2) {
    // Can't draw a line from fewer than 2 points — a dead token with no price series is itself a
    // signal, so render a subtle, honest note instead of silently rendering nothing.
    return (
      <div className="clean-note" style={{ fontSize: 11, marginTop: 4 }}>
        no recent price activity
      </div>
    )
  }

  const prices = points.map((p) => p.price)
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  // Normalize into a 2..26 band (2px padding so the stroke isn't clipped). A flat series
  // (max === min) would otherwise divide by zero — render it as a centered flat line instead.
  const y = (price: number) => (max === min ? 14 : 26 - ((price - min) / (max - min)) * 24)

  const coords = points.map((p, i) => ({ x: (i / (points.length - 1)) * 100, y: y(p.price) }))

  return (
    <svg
      viewBox="0 0 100 28"
      preserveAspectRatio="none"
      width="100%"
      height={28}
      role="img"
      aria-label="Recent price trend"
      style={{ display: 'block' }}
    >
      <polyline
        points={coords.map((c) => `${c.x.toFixed(2)},${c.y.toFixed(2)}`).join(' ')}
        fill="none"
        stroke="var(--accent)"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
