import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { EvidenceCard } from './EvidenceCard'
import type { Verdict } from '../types'

/** Truncates the way `EvidenceCard`'s module-private `shortMint` does. Duplicated here (not
 * imported — the helper is intentionally not exported) so assertions can compute the expected
 * truncated form from the fixture's mint instead of hardcoding a magic string. */
const shortMint = (m: string) => (m.length > 13 ? `${m.slice(0, 5)}…${m.slice(-6)}` : m)

/** Builds a HIGH-from-memory `Verdict` fixture — same shape/demo data as `VerdictCard.test.tsx`'s
 * `makeVerdict` (the GYaS demo token: 3 memory rugs, one medium signal). Each test overrides only
 * the field(s) it cares about. */
function makeVerdict(overrides: Partial<Verdict> = {}): Verdict {
  return {
    level: 'HIGH',
    score: 0.8511,
    mint: 'GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump',
    deployer: 'sF2wwqcTGvNPfBFvBw6P6c1PYuDG3S3M2sV4iF6r1qz',
    rationale: 'Deployer previously rugged 3 tokens; risk stands regardless of current state.',
    provenance: { first_party: 0.85, derived: null, claimed: null },
    memory_rugs: [
      { mint: '3qFSoWZ5w8n3B7pNn9BVi93BjEmFAKerVwoV3z6Fzuad', date: '2025-11-16' },
      { mint: '7wZk9cRt2LpXqYh1MnBv8sDfGjKl4oPqRstUvWxYzAbC', date: '2025-12-01' },
      { mint: 'HqNzYtR5vKmXpLd3FgWs9BnJc2VoTe6UiAy8ZrMkPqSx', date: '2026-01-10' },
    ],
    signals: [{ code: 'HOLDER_CONCENTRATION', severity: 'medium', detail: 'top holder 97.8%' }],
    acted: true,
    watchlisted: null,
    alert: null,
    ...overrides,
  }
}

describe('EvidenceCard', () => {
  it('renders a high-severity row per memory rug with the truncated mint, plus the first-party tag', () => {
    const verdict = makeVerdict({ signals: [] })
    const { container } = render(<EvidenceCard verdict={verdict} />)

    expect(container.querySelector('.tag.fp')).toHaveTextContent('first-party · scores')

    const rows = container.querySelectorAll('.row')
    expect(rows).toHaveLength(3)
    rows.forEach((row, i) => {
      expect(row.querySelector('.sev')).toHaveClass('sev', 'high')
      expect(row.querySelector('.rk')).toHaveTextContent(shortMint(verdict.memory_rugs[i].mint))
    })
  })

  it('renders a live signal as a row with its code, detail, and severity dot', () => {
    const verdict = makeVerdict({
      memory_rugs: [],
      signals: [{ code: 'LP_UNVERIFIED', severity: 'medium', detail: 'securedness unverifiable across pools' }],
    })
    const { container } = render(<EvidenceCard verdict={verdict} />)

    const row = container.querySelector('.row')
    expect(row?.querySelector('.sev')).toHaveClass('sev', 'med')
    expect(row?.querySelector('.rk')).toHaveTextContent('LP_UNVERIFIED')
    expect(row?.querySelector('.rd')).toHaveTextContent('securedness unverifiable across pools')
  })

  it('renders the holder-concentration bar with the real percentage when topHolderPct is supplied', () => {
    const verdict = makeVerdict({
      memory_rugs: [],
      signals: [{ code: 'HOLDER_CONCENTRATION', severity: 'medium', detail: 'top holder 97.8%' }],
    })
    const { container } = render(<EvidenceCard verdict={verdict} topHolderPct={97.8} />)

    const top = container.querySelector('.hbar .top') as HTMLElement
    expect(top).toBeInTheDocument()
    expect(top.style.width).toBe('97.8%')
    expect(container.querySelector('.hnote')).toHaveTextContent('others · 2.2%')
  })

  it('rounds the holder-bar top-holder percentage to one decimal place for display', () => {
    const verdict = makeVerdict({
      memory_rugs: [],
      signals: [{ code: 'HOLDER_CONCENTRATION', severity: 'medium', detail: 'top holder 97.8%' }],
    })
    const { container } = render(<EvidenceCard verdict={verdict} topHolderPct={97.7969569195} />)

    expect(container.querySelector('.hnote')).toHaveTextContent('top holder · 97.8%')
  })

  it('omits the holder bar when topHolderPct is null, still rendering the signal as a plain row', () => {
    const verdict = makeVerdict({
      memory_rugs: [],
      signals: [{ code: 'HOLDER_CONCENTRATION', severity: 'medium', detail: 'top holder 97.8%' }],
    })
    const { container } = render(<EvidenceCard verdict={verdict} topHolderPct={null} />)

    expect(container.querySelector('.hbar')).not.toBeInTheDocument()
    const row = container.querySelector('.row')
    expect(row).toBeInTheDocument()
    expect(row?.querySelector('.rk')).toHaveTextContent('HOLDER_CONCENTRATION')
  })

  it('sums memory_rugs and signals into the .meta findings count', () => {
    const verdict = makeVerdict({
      signals: [
        { code: 'HOLDER_CONCENTRATION', severity: 'medium', detail: 'top holder 97.8%' },
        { code: 'LP_UNVERIFIED', severity: 'low', detail: 'securedness unverifiable across pools' },
      ],
    })
    const { container } = render(<EvidenceCard verdict={verdict} />)

    expect(container.querySelector('.meta')).toHaveTextContent('5 findings')
  })

  it('omits the memory group header when memory_rugs is empty, without crashing, and still renders signals', () => {
    const verdict = makeVerdict({ memory_rugs: [] })
    const { container } = render(<EvidenceCard verdict={verdict} />)

    const groups = container.querySelectorAll('.ev-grp')
    expect(groups).toHaveLength(1)
    expect(groups[0]).toHaveTextContent('Live on-chain signals')
    expect(container.querySelector('.row')).toBeInTheDocument()
  })

  it('omits the live-signals group header when signals is empty, without crashing, and still renders memory rugs', () => {
    const verdict = makeVerdict({ signals: [] })
    const { container } = render(<EvidenceCard verdict={verdict} />)

    const groups = container.querySelectorAll('.ev-grp')
    expect(groups).toHaveLength(1)
    expect(groups[0]).toHaveTextContent('Deployer history')
    expect(container.querySelector('.row')).toBeInTheDocument()
  })
})
