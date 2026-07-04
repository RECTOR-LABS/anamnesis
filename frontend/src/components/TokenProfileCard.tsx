import type { ReactNode } from 'react'
import type { Profile } from '../types'
import { Card } from './Card'

interface TokenProfileCardProps {
  profile: Profile
}

/** The engine's own holder-concentration warn cutoff (`HOLDER_CONCENTRATION_THRESHOLD` in
 * `anamnesis.forensic.signals`) — kept in lockstep so this card's "warn" tone agrees with the risk
 * line the backend itself draws, rather than an arbitrary UI-picked number. */
const HOLDER_CONCENTRATION_WARN_PCT = 25

const INFO = (
  <>
    This token's <b>own</b> on-chain state. Note it reads mostly clean (authorities renounced) —{' '}
    <b>memory is what flips the verdict</b>, not these signals.
  </>
)

type Tone = 'ok' | 'warn' | null

/** One `.kv .i` row: a label plus a value that's either plain (`tone === null`) or ticked/colored
 * ok|warn. Kept local (not exported) — a small helper avoids 6x markup duplication for the grid
 * below without promoting it to a shared, un-asked-for abstraction. */
function kvItem(label: string, value: ReactNode, tone: Tone) {
  return (
    <div className="i" key={label}>
      <div className="k">{label}</div>
      <div className={tone ? `v ${tone}` : 'v'}>
        {tone && <span className="tick" />}
        {value}
      </div>
    </div>
  )
}

/** `created_at` → a `"<days>d <hours>h"` age string. A missing, unparseable, or future (clock-skew)
 * timestamp all degrade to the honest `'unknown'` rather than a misleading NaN/negative age. */
function formatAge(createdAt: string | null): string {
  if (!createdAt) return 'unknown'
  const ms = Date.now() - new Date(createdAt).getTime()
  if (Number.isNaN(ms) || ms < 0) return 'unknown'
  const h = Math.floor(ms / 3_600_000)
  return `${Math.floor(h / 24)}d ${h % 24}h`
}

/** Maps `lp.status` to its display value/tone. `GET /api/profile` uses the default
 * `_lp_unanalyzed` resolver, so `status` is virtually always `"unknown"` on this route (rendered
 * "unverified") — but all three documented values are mapped here for type-complete correctness,
 * not as dead code. */
function liquidityRow(status: string): { value: string; tone: 'ok' | 'warn' } {
  if (status === 'secured') return { value: 'secured', tone: 'ok' }
  if (status === 'not_secured') return { value: 'not secured', tone: 'warn' }
  return { value: 'unverified', tone: 'warn' } // covers 'unknown' and any other value
}

function topHolderRow(pct: number | null): { value: string; tone: Tone } {
  if (pct == null) return { value: 'unknown', tone: null }
  return { value: `${pct}%`, tone: pct >= HOLDER_CONCENTRATION_WARN_PCT ? 'warn' : 'ok' }
}

/** The Token profile card — pro-only "own signals" for the flagged mint, from mockup v4 (lines
 * 241-254): a key-value grid (authorities / holders / age / liquidity / top-holder) plus a
 * conditional "memory is what flips it" note. This token typically reads mostly clean on its own —
 * memory is what drives the verdict, not these live signals; the note only fires when that clean
 * read is actually true (both authorities renounced), never asserted falsely in a forensic tool.
 * Pure presentational, driven entirely by `profile`; App lazy-loads `getProfile(mint)` in T18. */
export function TokenProfileCard({ profile }: TokenProfileCardProps) {
  if (profile.error) {
    return (
      <Card title="Token profile" meta="own signals" info={INFO} className="anim pro-only">
        <p className="clean-note">Profile unavailable — {profile.error}.</p>
      </Card>
    )
  }

  const liquidity = liquidityRow(profile.lp.status)
  const topHolder = topHolderRow(profile.top_holder_pct)
  const isClean = profile.mint_authority == null && profile.freeze_authority == null

  const rows: { label: string; value: ReactNode; tone: Tone }[] = [
    {
      label: 'mint authority',
      value: profile.mint_authority == null ? 'renounced' : 'active',
      tone: profile.mint_authority == null ? 'ok' : 'warn',
    },
    {
      label: 'freeze authority',
      value: profile.freeze_authority == null ? 'renounced' : 'active',
      tone: profile.freeze_authority == null ? 'ok' : 'warn',
    },
    { label: 'holders', value: profile.holder_count.toLocaleString('en-US'), tone: null },
    { label: 'age', value: formatAge(profile.created_at), tone: null },
    { label: 'liquidity', value: liquidity.value, tone: liquidity.tone },
    { label: 'top holder', value: topHolder.value, tone: topHolder.tone },
  ]

  return (
    <Card title="Token profile" meta="own signals" info={INFO} className="anim pro-only">
      <div className="kv">{rows.map((r) => kvItem(r.label, r.value, r.tone))}</div>
      {isClean && (
        <p className="clean-note">
          Reads <b>mostly clean</b> on its own — renounced authorities, no active mint.{' '}
          <b>Memory is what flips it to HIGH.</b>
        </p>
      )}
    </Card>
  )
}
