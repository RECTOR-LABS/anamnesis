import type { Mode } from '../types'
import { ModeToggle } from './ModeToggle'

interface CommandBarProps {
  mint: string
  onMintChange: (v: string) => void
  onScan: () => void
  scanning?: boolean
  mode: Mode
  onModeChange: (m: Mode) => void
}

/** The top command bar from mockup v4 (`.bar` — brand + mint search + SCAN + Lite/Pro toggle +
 * memory-live status). `mint`/`onMintChange` make the input controlled; pressing Enter in the
 * input and clicking SCAN both fire `onScan`. `.scanline` (the CSS sweep animation) renders only
 * while `scanning` is true — this component holds no state of its own, the caller drives it. */
export function CommandBar({
  mint,
  onMintChange,
  onScan,
  scanning = false,
  mode,
  onModeChange,
}: CommandBarProps) {
  return (
    <div className="bar anim">
      <div className="brand">
        <div className="mark">◈</div>
        <b>ANAMNESIS</b>
      </div>
      <label className="search">
        {scanning && <span className="scanline" />}
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4.3-4.3" />
        </svg>
        <input
          spellCheck={false}
          aria-label="Token mint address"
          value={mint}
          onChange={(e) => onMintChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onScan()
          }}
        />
      </label>
      <button type="button" className="scan" onClick={onScan}>
        SCAN
      </button>
      <ModeToggle mode={mode} onChange={onModeChange} />
      <div className="whoami">
        <span className="dot-ok" />
        memory&nbsp;live
      </div>
    </div>
  )
}
