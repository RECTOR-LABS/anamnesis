import type { Funding } from '../types'
import { Card } from './Card'
import { shortAddr } from '../format'

interface FundingTrailProps {
  funding: Funding
}

const INFO = (
  <>
    Where the deployer's money came from — traced <b>hop-by-hop</b> back to the source (an
    exchange, bridge, or mixer).
  </>
)


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
