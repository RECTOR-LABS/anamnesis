import type { Level } from '../types'

interface RiskPillProps {
  level: Level
}

/** The verdict pill from mockup v4 (`.pill.high/.med/.low`). `Level` is upper-cased
 * ("HIGH"|"MEDIUM"|"LOW" — see types.ts), but the CSS classes are lower-case and MEDIUM is
 * abbreviated to "med" (mirrors `.sev.med` in SeverityDot) — only `.pill.high`/`.med`/`.low`
 * are defined in mockup.css, so a naive `level.toLowerCase()` for MEDIUM would emit a
 * class ("medium") with no matching rule and render unstyled. */
export function RiskPill({ level }: RiskPillProps) {
  const cls = level === 'MEDIUM' ? 'med' : level.toLowerCase()

  return (
    <span className={`pill ${cls}`}>
      <span className="pdot" />
      {level} RISK
    </span>
  )
}
