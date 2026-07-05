import type { Severity } from '../types'

interface SeverityDotProps {
  severity: Severity
}

/** The severity indicator dot from mockup v4 (`.sev.high/.med/.low`). `Severity` spells out
 * "medium" (types.ts), but the CSS class is abbreviated to `.sev.med` — map accordingly. */
export function SeverityDot({ severity }: SeverityDotProps) {
  const cls = severity === 'medium' ? 'med' : severity

  return <span className={`sev ${cls}`} />
}
