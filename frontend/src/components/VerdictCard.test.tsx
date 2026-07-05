import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { VerdictCard } from './VerdictCard'
import type { Verdict } from '../types'

/** Builds a HIGH-from-memory `Verdict` fixture — mirrors the GYaS demo token from the design
 * plan (3 memory rugs, a first-party score, one medium signal). Each test overrides only the
 * field(s) it cares about. */
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
    watchlisted: {
      deployer: 'sF2wwqcTGvNPfBFvBw6P6c1PYuDG3S3M2sV4iF6r1qz',
      mint: 'GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump',
      edge_id: 'edge-1',
    },
    alert: {
      id: 'alert-1',
      deployer: 'sF2wwqcTGvNPfBFvBw6P6c1PYuDG3S3M2sV4iF6r1qz',
      mint: 'GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump',
      severity: 'HIGH',
      score: 0.8511,
      rationale: 'Deployer previously rugged 3 tokens.',
      evidence: ['HOLDER_CONCENTRATION'],
      message: 'Watchlisted sF2ww… — 3 prior rugs on record.',
      status: 'open',
      created_at: '2026-07-04T00:00:00Z',
    },
    ...overrides,
  }
}

/** `useCountUp` and the meter fill both read `prefers-reduced-motion` at render time — stubbing
 * `matchMedia` to always match resolves both the count-up and the fill animation to their final
 * values synchronously (no reliance on real `requestAnimationFrame` timing), so assertions below
 * never race a 1.1s animation. */
beforeEach(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: true,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
})

describe('VerdictCard', () => {
  it('renders the RiskPill for the verdict level and the mint address', () => {
    const verdict = makeVerdict()
    const { container } = render(<VerdictCard verdict={verdict} />)

    const pill = container.querySelector('.pill')
    expect(pill).toHaveClass('pill', 'high')
    expect(pill).toHaveTextContent('HIGH RISK')
    expect(screen.getByText(verdict.mint)).toBeInTheDocument()
  })

  it('settles the score count-up at verdict.score.toFixed(2)', () => {
    const verdict = makeVerdict({ score: 0.8511 })
    const { container } = render(<VerdictCard verdict={verdict} />)

    expect(container.querySelector('.vscore .n')).toHaveTextContent('0.85')
  })

  it('shows the first-party provenance tier with the fp class when non-null', () => {
    const verdict = makeVerdict({ provenance: { first_party: 0.85, derived: null, claimed: null } })
    const { container } = render(<VerdictCard verdict={verdict} />)

    const tier = container.querySelector('.ptier')
    expect(tier).toHaveClass('fp')
    expect(tier).toHaveTextContent('0.85')
  })

  it('shows a dash and omits the fp class when first_party is null', () => {
    const verdict = makeVerdict({ provenance: { first_party: null, derived: null, claimed: null } })
    const { container } = render(<VerdictCard verdict={verdict} />)

    const tier = container.querySelector('.ptier')
    expect(tier).not.toHaveClass('fp')
    expect(tier).toHaveTextContent('—')
  })

  it('renders the memory flag when memory_rugs is non-empty', () => {
    const verdict = makeVerdict()
    const { container } = render(<VerdictCard verdict={verdict} />)

    const flag = container.querySelector('.flag')
    expect(flag).toBeInTheDocument()
    expect(flag).toHaveTextContent('rugged 3 token(s) before')
  })

  it('omits the memory flag when memory_rugs is empty', () => {
    const verdict = makeVerdict({ memory_rugs: [] })
    const { container } = render(<VerdictCard verdict={verdict} />)

    expect(container.querySelector('.flag')).not.toBeInTheDocument()
  })

  it('renders the lite-ev one-liner with a rug-count line and a signal detail', () => {
    const verdict = makeVerdict()
    const { container } = render(<VerdictCard verdict={verdict} />)

    const liteEv = container.querySelector('.lite-ev')
    expect(liteEv).toHaveTextContent('3 prior rug(s) recalled from memory')
    expect(liteEv).toHaveTextContent('top holder 97.8%')
  })

  it('reflects the score in the meter fill width', () => {
    const verdict = makeVerdict({ score: 0.85 })
    const { container } = render(<VerdictCard verdict={verdict} />)

    const fill = container.querySelector('.meter i') as HTMLElement
    expect(fill.style.width).toContain('85')
  })
})
