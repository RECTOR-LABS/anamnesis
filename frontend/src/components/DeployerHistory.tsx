import type { DeployerHistory as DeployerHistoryData, MemoryRug } from '../types'
import { Card } from './Card'

interface DeployerHistoryProps {
  history: DeployerHistoryData // GET /api/deployer/{mint} shape
  memoryRugs: MemoryRug[] // Verdict.memory_rugs — identifies which launches are known rugs
  watchlisted?: boolean // Verdict.watchlisted != null — drives the header meta (default false)
}

const INFO = (
  <>
    Every token this wallet has launched. The <b>pattern</b> — many launched, nearly all dead or
    rugged — is what memory captures across sessions.
  </>
)

/** Liveness isn't derivable from the deployer-history read; forensically we treat unconfirmed
 * launches as not-alive → a conservative floor, not a live count. (Handoff: DeployerHistory
 * 'alive'≈0.) */
const ALIVE_COUNT = 0

/** Truncates an address to the mockup's `sF2ww…dZkMvv` form. Kept local to this file: T13's
 * `shortMint` is the identical form, but cross-file coupling for a 1-line pure fn isn't worth it
 * across independently-built SDD tasks — the final review will decide whether to extract a
 * shared `formatAddr`. */
const shortAddr = (a: string) => (a.length > 13 ? `${a.slice(0, 5)}…${a.slice(-6)}` : a)

/** The Deployer history card — pro-only serial-launch pattern, from mockup v4 (lines 229-237): a
 * tile strip of every token this wallet has launched (this-token / known-rug / presumed-dead)
 * plus deployed/known-rugs/alive stats. The narrative point: memory captures that this wallet
 * launches token after token, nearly all dead or rugged. Pure presentational, driven entirely by
 * `history` and `memoryRugs`; App lazy-loads `getDeployer(mint)` in T18 and passes both plus
 * `watchlisted` from `Verdict.watchlisted != null`. */
export function DeployerHistory({
  history,
  memoryRugs,
  watchlisted = false,
}: DeployerHistoryProps) {
  if (history.error) {
    return (
      <Card title="Deployer history" meta="deployer" info={INFO} className="anim pro-only">
        <p className="clean-note">Deployer history unavailable — {history.error}.</p>
      </Card>
    )
  }

  const rugSet = new Set(memoryRugs.map((r) => r.mint))

  // Precedence: this-token (the assessed mint) first, then a known rug from memory, else
  // presumed dead — so the current token always reads as itself even if memory also flags it.
  function classifyMint(mint: string): { cls: 'new' | 'rug' | 'dead'; glyph: string } {
    if (mint === history.mint) return { cls: 'new', glyph: '◈' }
    if (rugSet.has(mint)) return { cls: 'rug', glyph: 'R' }
    return { cls: 'dead', glyph: '·' }
  }

  return (
    <Card
      title={`Deployer · ${history.count}-token history`}
      meta={watchlisted ? <span style={{ color: 'var(--high)' }}>watchlisted</span> : 'deployer'}
      info={INFO}
      className="anim pro-only"
    >
      <div className="thead">
        <span className="addr">{history.deployer ? shortAddr(history.deployer) : 'unknown'}</span>
        <div className="stat2">
          <div>
            <div className="n tnum">{history.count}</div>
            <div className="l">deployed</div>
          </div>
          <div>
            <div className="n bad tnum">{memoryRugs.length}</div>
            <div className="l">known rugs</div>
          </div>
          <div>
            <div className="n tnum">{ALIVE_COUNT}</div>
            <div className="l">alive</div>
          </div>
        </div>
      </div>

      {history.created_mints.length > 0 ? (
        <>
          <div className="mints">
            {history.created_mints.map((cm, i) => {
              const { cls, glyph } = classifyMint(cm.mint)
              return (
                <span className={`m ${cls}`} key={`${cm.mint}-${i}`} title={cm.mint}>
                  {glyph}
                </span>
              )
            })}
          </div>
          {history.truncated && (
            <div className="mlegend" style={{ marginBottom: 10 }}>
              bounded scan — more launches may exist
            </div>
          )}
          <div className="mlegend">
            <span>
              <i
                className="lg"
                style={{ background: 'var(--high-bg)', border: '1px solid var(--high-line)' }}
              />
              rugged (memory)
            </span>
            <span>
              <i
                className="lg"
                style={{ background: 'var(--inset)', border: '1px solid var(--line)' }}
              />
              dead / zero-liq
            </span>
            <span>
              <i
                className="lg"
                style={{ background: 'var(--med-bg)', border: '1px solid var(--med-line)' }}
              />
              this token
            </span>
          </div>
        </>
      ) : (
        <p className="clean-note">No prior launches on record for this deployer.</p>
      )}
    </Card>
  )
}
