import type { Mode } from '../types'

interface ModeToggleProps {
  mode: Mode
  onChange: (m: Mode) => void
}

/** The Lite/Pro segmented control from mockup v4 (`.seg > button.on`). Controlled: the button
 * matching `mode` carries the `on` class, the other renders with no class at all (mirrors the
 * mockup markup exactly). Clicking a button reports its own mode via `onChange` — it never
 * tracks state itself. `:focus-visible` styling is handled entirely by mockup.css. */
export function ModeToggle({ mode, onChange }: ModeToggleProps) {
  return (
    <div className="seg" role="group" aria-label="View mode">
      <button
        type="button"
        className={mode === 'lite' ? 'on' : undefined}
        data-mode="lite"
        onClick={() => onChange('lite')}
      >
        Lite
      </button>
      <button
        type="button"
        className={mode === 'pro' ? 'on' : undefined}
        data-mode="pro"
        onClick={() => onChange('pro')}
      >
        Pro
      </button>
    </div>
  )
}
