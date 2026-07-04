import type { Funding } from '../types'
import { Card } from './Card'

interface FundingTrailProps {
  funding: Funding
}

const INFO = (
  <>
    Where the deployer's money came from — traced <b>hop-by-hop</b> back to the source (an
    exchange, bridge, or mixer).
  </>
)

/** Truncates an address to the mockup's `sF2ww…dZkMvv` form. Kept local to this file: same form
 * as `DeployerHistory`'s module-private `shortAddr` — cross-file coupling for a 1-line pure fn
 * isn't worth it across independently-built SDD tasks. */
const shortAddr = (a: string) => (a.length > 13 ? `${a.slice(0, 5)}…${a.slice(-6)}` : a)

/** The Funding trail card — pro-only, from mockup v4 (lines 280-287): a 3-node trace (origin →
 * funder → deployer) showing where the deployer's launch capital came from. The engine traces
 * exactly one hop (source_type → funder → deployer), so the trail is fixed at 3 nodes rather than
 * a variable-length chain. Pure presentational, driven entirely by `funding`; App lazy-loads
 * `getFunding(mint)` in T18. */
export function FundingTrail({ funding }: FundingTrailProps) {
  if (funding.error) {
    return (
      <Card title="Funding trail" meta="trace_funding" info={INFO} className="anim pro-only">
        <p className="clean-note">Funding trail unavailable — {funding.error}.</p>
      </Card>
    )
  }

  return (
    <Card title="Funding trail" meta="trace_funding" info={INFO} className="anim pro-only">
      <div className="trail">
        <div className="tnode">
          <div className="tt">{funding.source_type.toUpperCase()}</div>
          <div className="ts">origin</div>
        </div>
        <span className="tarrow">→</span>
        <div className="tnode">
          <div className="tt">{funding.funder ? shortAddr(funding.funder) : 'unknown'}</div>
          <div className="ts">funder</div>
        </div>
        <span className="tarrow">→</span>
        <div className="tnode" style={{ borderColor: 'var(--high-line)' }}>
          <div className="tt" style={{ color: 'var(--high)' }}>
            {funding.deployer ? shortAddr(funding.deployer) : 'unknown'}
          </div>
          <div className="ts">deployer</div>
        </div>
      </div>
    </Card>
  )
}
