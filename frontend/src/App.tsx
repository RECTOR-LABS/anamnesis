import { useEffect, useState } from 'react'
import type {
  DeployerHistory as DeployerHistoryData,
  Funding,
  GraphData,
  Mode,
  Profile,
  PricePoint,
} from './types'
import { getDeployer, getFunding, getGraph, getPrice, getProfile } from './api'
import { useAssess } from './hooks/useAssess'
import { useChatStream } from './hooks/useChatStream'
import { CommandBar } from './components/CommandBar'
import { MemoryBand } from './components/MemoryBand'
import { VerdictCard } from './components/VerdictCard'
import { Sparkline } from './components/Sparkline'
import { EvidenceCard } from './components/EvidenceCard'
import { DeployerHistory } from './components/DeployerHistory'
import { TokenProfileCard } from './components/TokenProfileCard'
import { ClusterGraph } from './components/ClusterGraph'
import { FundingTrail } from './components/FundingTrail'
import { AutopilotActions } from './components/AutopilotActions'
import { ChatPanel } from './components/ChatPanel'

// Pre-filled so SCAN works out-of-box for the demo.
const DEMO_MINT = 'GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump'

/** Truncates a mint/pubkey to the mockup's `3qFSo…KY3pump` form. Kept local (not a shared util) —
 * same rationale as `EvidenceCard`/`DeployerHistory`'s own module-private copies: a second call
 * site doesn't yet justify promoting a 1-line pure fn to a shared helper. */
const shortMint = (m: string) => (m.length > 13 ? `${m.slice(0, 5)}…${m.slice(-6)}` : m)

/** The dashboard root — composes the full mockup v4 layout from the primitives/cards/hooks built
 * in prior tasks, wired to the live `api.ts` client. `mode` is pure presentation: it only ever
 * flips `.wrap`'s CSS class (`mode-lite`/`mode-pro`); it never gates JSX, since `.pro-only`
 * sections must always be in the DOM for `mockup.css`'s `.mode-lite .pro-only{display:none}` rule
 * to hide them. Every card except `ChatPanel` (always on, itself `pro-only`-gated by CSS) is
 * gated on `verdict` — plus its own lazy datum where one exists — so nothing renders pre-scan. */
export default function App() {
  const [mint, setMint] = useState(DEMO_MINT)
  const [mode, setMode] = useState<Mode>('lite')
  const { verdict, loading, error, run } = useAssess()
  const chat = useChatStream()

  // Lazy per-token reads, fired once a verdict lands. Cleared at the top of the effect so NO card
  // ever shows a stale cross-token read (forensic correctness — matches the engine's
  // fresh-per-request stance). `alive` guards every setter so a superseded effect instance (a
  // second scan landing before the first token's reads finish) can never commit into the newer
  // token's cards.
  const [graph, setGraph] = useState<GraphData | null>(null)
  const [price, setPrice] = useState<PricePoint[]>([])
  const [profile, setProfile] = useState<Profile | null>(null)
  const [deployerHist, setDeployerHist] = useState<DeployerHistoryData | null>(null)
  const [funding, setFunding] = useState<Funding | null>(null)

  useEffect(() => {
    if (!verdict) return
    let alive = true
    setGraph(null)
    setPrice([])
    setProfile(null)
    setDeployerHist(null)
    setFunding(null)

    const m = verdict.mint
    getPrice(m)
      .then((p) => alive && setPrice(p))
      .catch(() => alive && setPrice([]))
    getProfile(m)
      .then((p) => alive && setProfile(p))
      .catch(() => alive && setProfile(null))
    getDeployer(m)
      .then((d) => alive && setDeployerHist(d))
      .catch(() => alive && setDeployerHist(null))
    getFunding(m)
      .then((f) => alive && setFunding(f))
      .catch(() => alive && setFunding(null))
    if (verdict.deployer) {
      getGraph(verdict.deployer)
        .then((g) => alive && setGraph(g))
        .catch(() => alive && setGraph(null))
    }

    return () => {
      alive = false
    }
  }, [verdict])

  return (
    <div className={`wrap mode-${mode}`}>
      <CommandBar
        mint={mint}
        onMintChange={setMint}
        onScan={() => run(mint)}
        scanning={loading}
        mode={mode}
        onModeChange={setMode}
      />
      <div className="ctx">
        <span>
          <b>token</b>&nbsp; {shortMint(mint)}
        </span>
        <span className="sep">/</span>
        <span>
          <b>model</b>&nbsp; qwen-max · DashScope
        </span>
      </div>
      <MemoryBand />
      {/* MINIMAL states only — the polished scanning/invalid/error states are T19. Just don't
          look broken. */}
      {error && (
        <div className="ctx" style={{ color: 'var(--high)' }}>
          Scan failed — {error}
        </div>
      )}
      {!verdict && !loading && !error && (
        <div className="ctx">Paste a token mint and press SCAN to begin.</div>
      )}
      <div className="grid">
        <div className="col">
          {verdict && <VerdictCard verdict={verdict} />}
          {verdict && <Sparkline points={price} />}
          {verdict && <EvidenceCard verdict={verdict} topHolderPct={profile?.top_holder_pct ?? null} />}
          {verdict && deployerHist && (
            <DeployerHistory
              history={deployerHist}
              memoryRugs={verdict.memory_rugs}
              watchlisted={verdict.watchlisted != null}
            />
          )}
        </div>
        <div className="col">
          {verdict && profile && <TokenProfileCard profile={profile} />}
          {verdict && graph && <ClusterGraph graph={graph} />}
          {verdict && funding && <FundingTrail funding={funding} />}
          {verdict && <AutopilotActions watchlisted={verdict.watchlisted} alert={verdict.alert} />}
          <ChatPanel
            messages={chat.messages}
            streaming={chat.streaming}
            onSend={(msg) => chat.send(msg, verdict?.mint ?? mint)}
          />
        </div>
      </div>
      <div className="foot">
        <span className="dot-ok" /> Anamnesis · forensic pre-trade intelligence · memory compounds
        every scan
      </div>
    </div>
  )
}
