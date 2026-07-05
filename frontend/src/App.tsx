import { useEffect, useLayoutEffect, useState } from 'react'
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
import { shortAddr } from './format'

// Pre-filled so SCAN works out-of-box for the demo.
const DEMO_MINT = 'GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump'

// Client-side mint-format guard (T19). The engine never emits a `level:"N/A"` verdict — a garbage
// mint still returns a real LOW verdict, and a malformed one errors — so "invalid input" has no
// server-side signal to key off. Base58 + Solana pubkey length is the only mechanism that actually
// catches it before wasting a round-trip on something that was never a mint to begin with.
const MINT_RE = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/
const isValidMint = (m: string) => MINT_RE.test(m.trim())

/** A content-free placeholder for a verdict-gated card, shown in both grid columns while a scan
 * is in flight. Local to App (no separate file) — same rationale as the module-private helpers
 * above: nothing else needs it yet. */
function SkeletonCard() {
  return (
    <div className="card skel-card" aria-hidden="true">
      <div className="skel-bar" style={{ height: 14, width: '40%', marginBottom: 12 }} />
      <div className="skel-bar" style={{ height: 44, marginBottom: 10 }} />
      <div className="skel-bar" style={{ height: 14, width: '70%' }} />
    </div>
  )
}

/** The dashboard root — composes the full mockup v4 layout from the primitives/cards/hooks built
 * in prior tasks, wired to the live `api.ts` client. `mode` is pure presentation: it only ever
 * flips `.wrap`'s CSS class (`mode-lite`/`mode-pro`); it never gates JSX, since `.pro-only`
 * sections must always be in the DOM for `mockup.css`'s `.mode-lite .pro-only{display:none}` rule
 * to hide them. Every card except `ChatPanel` (always on, itself `pro-only`-gated by CSS) is
 * gated on `verdict` — plus its own lazy datum where one exists — so nothing renders pre-scan. */
export default function App() {
  const [mint, setMint] = useState(DEMO_MINT)
  const [mode, setMode] = useState<Mode>('lite')
  const [formatError, setFormatError] = useState<string | null>(null)
  const { verdict, loading, error, run } = useAssess()
  const chat = useChatStream()

  // Client-side gate in front of `run`: a malformed mint never reaches the API — it just shows an
  // amber format hint. Reused by the Retry button, so Retry re-validates rather than blindly
  // replaying whatever the last request was.
  const onScan = () => {
    if (!isValidMint(mint)) {
      setFormatError(
        'That doesn’t look like a Solana mint address — check the format (base58, 32–44 characters).',
      )
      return
    }
    setFormatError(null)
    run(mint)
  }

  // Lazy per-token reads, fired once a verdict lands. `price` is nullable: null means "not loaded
  // yet / failed" (Sparkline renders nothing), distinct from [] which means "loaded, genuinely no
  // series" (Sparkline's honest "no recent price activity" note) — so a still-loading or errored
  // price never shows as a false dead-token claim.
  const [graph, setGraph] = useState<GraphData | null>(null)
  const [price, setPrice] = useState<PricePoint[] | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [deployerHist, setDeployerHist] = useState<DeployerHistoryData | null>(null)
  const [funding, setFunding] = useState<Funding | null>(null)

  // Clear the previous token's lazy reads SYNCHRONOUSLY (pre-paint) the instant a new verdict lands,
  // so a re-scan never paints even one frame of the old token's price/profile/graph/funding under
  // the new verdict (forensic correctness). A passive useEffect clears only AFTER that stale frame
  // is painted — hence useLayoutEffect here, useEffect for the async fetch below.
  useLayoutEffect(() => {
    setGraph(null)
    setPrice(null)
    setProfile(null)
    setDeployerHist(null)
    setFunding(null)
  }, [verdict])

  useEffect(() => {
    if (!verdict) return
    let alive = true
    const m = verdict.mint
    getPrice(m)
      .then((p) => alive && setPrice(p))
      .catch(() => alive && setPrice(null))
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
        onScan={onScan}
        scanning={loading}
        mode={mode}
        onModeChange={setMode}
      />
      <div className="ctx">
        <span>
          <b>token</b>&nbsp; {shortAddr(mint)}
        </span>
        <span className="sep">/</span>
        <span>
          <b>model</b>&nbsp; qwen-max · DashScope
        </span>
      </div>
      <MemoryBand />
      {formatError && (
        <p className="clean-note" style={{ color: 'var(--med)' }}>
          {formatError}
        </p>
      )}
      {error && !loading && !formatError && (
        <p className="clean-note" style={{ color: 'var(--high)' }}>
          Scan failed — {error}{' '}
          <button type="button" className="scan" style={{ marginLeft: 8 }} onClick={onScan}>
            Retry
          </button>
        </p>
      )}
      {!verdict && !loading && !error && !formatError && (
        <p className="clean-note">Paste a token mint and press SCAN to begin.</p>
      )}
      <div className="grid">
        <div className="col">
          {loading ? (
            <>
              <SkeletonCard />
              <SkeletonCard />
            </>
          ) : (
            <>
              {verdict && <VerdictCard verdict={verdict} />}
              {verdict && <Sparkline points={price} />}
              {verdict && (
                <EvidenceCard verdict={verdict} topHolderPct={profile?.top_holder_pct ?? null} />
              )}
              {verdict && deployerHist && (
                <DeployerHistory
                  history={deployerHist}
                  memoryRugs={verdict.memory_rugs}
                  watchlisted={verdict.watchlisted != null}
                />
              )}
            </>
          )}
        </div>
        <div className="col">
          {loading ? (
            <>
              <SkeletonCard />
              <SkeletonCard />
            </>
          ) : (
            <>
              {verdict && profile && <TokenProfileCard profile={profile} />}
              {verdict && graph && <ClusterGraph graph={graph} />}
              {verdict && funding && <FundingTrail funding={funding} />}
              {verdict && <AutopilotActions watchlisted={verdict.watchlisted} alert={verdict.alert} />}
            </>
          )}
          <ChatPanel
            messages={chat.messages}
            streaming={chat.streaming}
            onSend={(msg) => chat.send(msg, verdict?.mint ?? mint)}
            error={chat.error}
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
