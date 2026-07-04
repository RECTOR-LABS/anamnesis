import type { ReactNode } from 'react'
import { Tooltip } from './Tooltip'

interface CardProps {
  title: string
  meta?: ReactNode
  info?: ReactNode
  className?: string
  children: ReactNode
}

/** The card shell from mockup v4 (`.card > .card-h + .card-b`). `className` appends onto the
 * base "card" class (e.g. "anim", "pro-only" — space-separated, caller's choice) rather than
 * replacing it. `meta`/`info` use a nullish check (not truthiness) so a legitimately falsy-but-
 * real value (e.g. `meta={0}`) still renders instead of being silently dropped. */
export function Card({ title, meta, info, className, children }: CardProps) {
  const cardClass = className ? `card ${className}` : 'card'

  return (
    <div className={cardClass}>
      <div className="card-h">
        <span className="ht">
          <h3>{title}</h3>
          {info != null && <Tooltip>{info}</Tooltip>}
        </span>
        {meta != null && <span className="meta">{meta}</span>}
      </div>
      <div className="card-b">{children}</div>
    </div>
  )
}
