// Wire types for the Anamnesis dashboard API. These mirror the FastAPI JSON contract
// (api/cards.py, api/routes/*.py) field-for-field — verified directly against that code,
// not inferred from docs. Keep this file in lockstep with the backend: any serializer change
// there should be reflected here in the same PR.

/** `Verdict.level` is normalized to upper case by `api/cards.py::verdict_card` (the engine's
 * own `anamnesis.risk.Verdict.level` is lowercase internally) so the dashboard's HIGH/MEDIUM/LOW
 * pill convention and the provenance gate agree regardless of the engine's internal casing. */
export type Level = 'HIGH' | 'MEDIUM' | 'LOW'

/** Signal severity is passed through verbatim from the engine and stays lowercase — it is a
 * distinct field from `Verdict.level` and must not be confused with it. */
export type Severity = 'high' | 'medium' | 'low'

export interface Signal {
  code: string
  severity: Severity
  detail: string
}

export interface MemoryRug {
  mint: string
  date: string | null
}

export interface Provenance {
  first_party: number | null
  derived: number | null
  claimed: number | null
}

export interface Watchlisted {
  deployer: string
  mint: string
  edge_id: string
}

/** `Alert.severity` is `verdict.level` copied verbatim onto the `AlertDraft` (see
 * `anamnesis.agent.actions.draft_alert`) — lowercase like `Signal.severity`, NOT normalized to
 * `Level` the way `Verdict.level` is. Typed as plain `string` (not `Severity`) since it is
 * sourced independently and nothing here guarantees it stays one of the three known bands. */
export interface Alert {
  id: string
  deployer: string
  mint: string
  severity: string
  score: number
  rationale: string
  evidence: string[]
  message: string
  status: string
  created_at: string
}

export interface Verdict {
  level: Level
  score: number
  mint: string
  deployer: string | null
  rationale: string | null
  provenance: Provenance
  memory_rugs: MemoryRug[]
  signals: Signal[]
  acted: boolean
  watchlisted: Watchlisted | null
  alert: Alert | null
}

export interface LpEvidence {
  venue: string
  pool: string
  lp_mint: string | null
  method: string
  /** `true`/`false` are a proven secured/withdrawable pool; `null` is unknown/unverifiable for
   * this pool (see `anamnesis.forensic.signals.LpEvidence.secured`) — a distinct third state,
   * not a stand-in for `false`. Treating `null` as "not secured" would understate risk, and
   * treating it as "secured" would hide it; callers must render it as its own state. */
  secured: boolean | null
  detail: string
  liquidity_usd: number | null
  citation: string | null
}

export interface Profile {
  mint: string
  deployer: string | null
  created_at: string | null
  mint_authority: string | null
  freeze_authority: string | null
  lp: { status: string; evidence: LpEvidence[] }
  top_holder_pct: number | null
  holder_count: number
  /** Present only on the degraded `{mint, error}` shape returned when the upstream Helius read
   * fails (`api/routes/profile.py`'s `except HeliusError` guard). On that path every other
   * field is simply absent from the payload, not null — callers must check for `error` before
   * trusting the rest of the shape. */
  error?: string
}

/** One entry in a deployer's serial-mint history. `created_at` mirrors
 * `anamnesis.forensic.helius.creation_time`, which returns `None` when a transaction's
 * `blockTime` is absent. */
export interface DeployerMint {
  mint: string
  created_at: string | null
}

export interface DeployerHistory {
  mint: string
  /** Null when `resolve_origin` cannot identify a deployer — a well-shaped miss
   * (`created_mints: []`, `count: 0`), not an error. */
  deployer: string | null
  created_mints: DeployerMint[]
  count: number
  /** True only when the bounded scan stopped on a cap (more history may exist) — never implies
   * a partial answer is complete. */
  truncated: boolean
  /** Present only on the degraded `{mint, error}` shape (a Helius RPC failure) — see `Profile.error`. */
  error?: string
}

export interface Funding {
  mint: string
  deployer: string | null
  funder: string | null
  source_type: string
  funded_at: string | null
  /** Present only on the degraded `{mint, error}` shape — see `Profile.error`. */
  error?: string
}

export interface GraphNode {
  id: string
  type: string
  flags: string[]
}

export interface GraphEdge {
  src: string
  dst: string
  type: string
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface PricePoint {
  t: string
  price: number
}

export interface ChatEvent {
  role: string
  content: string
  tool?: string
}
