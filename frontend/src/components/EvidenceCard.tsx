import type { Verdict } from '../types'
import { Card } from './Card'
import { SeverityDot } from './SeverityDot'
import { shortAddr } from '../format'

interface EvidenceCardProps {
  verdict: Verdict // supplies memory_rugs[] and signals[]
  topHolderPct?: number | null // the holder-concentration bar %; from Profile.top_holder_pct
}

/** The Evidence card — pro-only "receipts" behind the verdict — from mockup v4 (lines 215-227):
 * memory rugs (first-party, always HIGH) plus live on-chain signals, with a holder-concentration
 * bar rendered on the `HOLDER_CONCENTRATION` signal once `topHolderPct` is known. Pure
 * presentational, driven entirely by `verdict` plus the one prop `Verdict` itself doesn't carry
 * (`topHolderPct` comes from `Profile`) — App wires this in T18 the same way it wires
 * `VerdictCard`. Each group renders only when its list is non-empty, so a token with no memory
 * rugs (or, in principle, no live signals) never shows an empty section header. */
export function EvidenceCard({ verdict, topHolderPct }: EvidenceCardProps) {
  const findings = verdict.memory_rugs.length + verdict.signals.length

  return (
    <Card
      title="Evidence"
      meta={`${findings} findings`}
      info={
        <>
          The receipts behind the verdict: past rugs <b>recalled from memory</b> (first-party)
          plus <b>live on-chain signals</b>. Memory alone can reach HIGH; live signals alone
          cannot.
        </>
      }
      className="anim pro-only"
    >
      {verdict.memory_rugs.length > 0 && (
        <>
          <div className="ev-grp">
            Deployer history · from memory <span className="tag fp">first-party · scores</span>
          </div>
          {verdict.memory_rugs.map((rug) => (
            <div className="row" key={rug.mint}>
              <SeverityDot severity="high" />
              <span className="rk">{shortAddr(rug.mint)}</span>
              <span className="rd">rugged</span>
              <span className="rx">
                {rug.date ?? '—'} <span className="chev">›</span>
              </span>
            </div>
          ))}
        </>
      )}

      {verdict.signals.length > 0 && (
        <>
          <div className="ev-grp">
            Live on-chain signals <span className="tag">live · Helius</span>
          </div>
          {verdict.signals.map((sig, i) =>
            sig.code === 'HOLDER_CONCENTRATION' && topHolderPct != null ? (
              <div className="row" style={{ flexWrap: 'wrap' }} key={`${sig.code}-${i}`}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%' }}>
                  <SeverityDot severity={sig.severity} />
                  <span className="rk">{sig.code}</span>
                  <span className="rd">{sig.detail}</span>
                  <span className="rx">{sig.severity}</span>
                </div>
                <div style={{ width: '100%' }}>
                  <div className="hbar">
                    <i className="top" style={{ width: `${topHolderPct}%` }} />
                    <i className="rest" />
                  </div>
                  <div className="hnote">
                    <span>top holder · {topHolderPct.toFixed(1)}%</span>
                    <span>others · {(100 - topHolderPct).toFixed(1)}%</span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="row" key={`${sig.code}-${i}`}>
                <SeverityDot severity={sig.severity} />
                <span className="rk">{sig.code}</span>
                <span className="rd">{sig.detail}</span>
                <span className="rx">{sig.severity}</span>
              </div>
            )
          )}
        </>
      )}
    </Card>
  )
}
