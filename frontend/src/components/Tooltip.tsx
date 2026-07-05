import type { ReactNode } from 'react'

interface TooltipProps {
  children: ReactNode
  label?: string
}

/** The ⓘ info popover from mockup v4 (`.info`/`.tip`). Show-on-hover/focus is pure CSS
 * (`mockup.css`) — this only renders the structure + the a11y attributes it depends on. */
export function Tooltip({ children, label = 'What is this?' }: TooltipProps) {
  return (
    <span className="info" tabIndex={0} aria-label={label}>
      i<span className="tip">{children}</span>
    </span>
  )
}
