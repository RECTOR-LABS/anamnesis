import { useEffect, useState } from 'react'
import type { Verdict } from '../types'
import { Card } from './Card'
import { RiskPill } from './RiskPill'
import { SeverityDot } from './SeverityDot'
import { prefersReducedMotion, useCountUp } from '../hooks/useCountUp'

interface VerdictCardProps {
  verdict: Verdict
}

/** The hero verdict card from mockup v4 (`.verdict` — stripe + pill/score + meter + mint +
 * provenance tiers + memory flag + Lite one-liner). Unlike the mockup (which hardcodes score
 * 0.85/HIGH for the demo), every number and class here tracks `verdict`: the count-up, the meter
 * fill, and the stripe color all animate toward the *actual* score/level, never a fixed value.
 * `.pro-only`/`.lite-only` show/hide stays pure CSS — gated by `.mode-lite`/`.mode-pro` on the
 * ancestor `.wrap` that App controls — this component always emits both blocks. */
export function VerdictCard({ verdict }: VerdictCardProps) {
  const countUp = useCountUp(verdict.score)
  const [reducedMotion] = useState(prefersReducedMotion)
  const fillTarget = verdict.score * 100
  const [fillPct, setFillPct] = useState(() => (reducedMotion ? fillTarget : 0))

  // Flips the meter's inline width from 0 to the real score right after mount so the CSS
  // `transition` on `.meter i` (mockup.css) animates the fill — mirrors the mockup's
  // `@keyframes fill` timing but tracks the actual score instead of a hardcoded 85%. Under
  // reduced motion `fillPct` already starts at `fillTarget` and `.meter i{transition:none}`
  // (mockup.css) makes this a no-op repaint rather than an animated jump.
  useEffect(() => {
    setFillPct(fillTarget)
  }, [fillTarget])

  const hasMemoryRugs = verdict.memory_rugs.length > 0
  const firstParty = verdict.provenance.first_party

  return (
    <Card
      title="Verdict"
      meta="assess_risk · recall"
      info="The final risk call and score. Driven by what the agent remembers about the deployer — not just this token's current on-chain state."
      className="anim"
    >
      <div className="verdict">
        <div className={`stripe stripe-${verdict.level.toLowerCase()}`}>
          <i />
        </div>
        <div className="vmain">
          <div className="vtop">
            <RiskPill level={verdict.level} />
            <div className="vscore">
              <div className="n tnum">{countUp.toFixed(2)}</div>
              <div className="l">risk score</div>
            </div>
          </div>
          <div className="meter">
            <i style={{ width: `${fillPct.toFixed(1)}%` }} />
          </div>
          <div className="mint">
            <span className="k">mint</span>
            {verdict.mint}
          </div>

          <div className="prov pro-only">
            <div className={`ptier${firstParty != null ? ' fp' : ''}`}>
              <div className="pt">first-party</div>
              <div className="pv tnum">{firstParty != null ? firstParty.toFixed(2) : '—'}</div>
              <div className="pn">{verdict.memory_rugs.length} rugs · scores</div>
            </div>
            <div className="ptier">
              <div className="pt">derived</div>
              <div className="pv">—</div>
              <div className="pn">capped MEDIUM</div>
            </div>
            <div className="ptier">
              <div className="pt">claimed</div>
              <div className="pv">—</div>
              <div className="pn">context only</div>
            </div>
          </div>

          {hasMemoryRugs && (
            <div className="flag">
              <span className="b">⚡</span>
              <p>
                Flagged <b>from memory</b> — its deployer{' '}
                <b>rugged {verdict.memory_rugs.length} token(s) before</b>. Risk stands regardless
                of current on-chain state.
              </p>
            </div>
          )}

          <div className="lite-ev lite-only">
            {hasMemoryRugs && (
              <span>
                <SeverityDot severity="high" />
                {verdict.memory_rugs.length} prior rug(s) recalled from memory
              </span>
            )}
            {verdict.signals.slice(0, 2).map((s) => (
              <span key={s.code}>
                <SeverityDot severity={s.severity} />
                {s.detail}
              </span>
            ))}
          </div>
        </div>
      </div>
    </Card>
  )
}
