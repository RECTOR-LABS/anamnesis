import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { FundingTrail } from './FundingTrail'
import type { Funding } from '../types'

/** Truncates the way `FundingTrail`'s module-private `shortAddr` does. Duplicated here (not
 * imported — the helper is intentionally not exported) so assertions can compute the expected
 * truncated form from the fixture's address instead of hardcoding a magic string. Same form as
 * `DeployerHistory.test.tsx`'s `shortAddr` dup. */
const shortAddr = (a: string) => (a.length > 13 ? `${a.slice(0, 5)}…${a.slice(-6)}` : a)

// Same GYaS demo token/deployer as VerdictCard.test.tsx / EvidenceCard.test.tsx / DeployerHistory.test.tsx.
const MINT = 'GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump'
const DEPLOYER = 'sF2wwqcTGvNPfBFvBw6P6c1PYuDG3S3M2sV4iF6r1qz'
const FUNDER = 'Binance7iQqUvS8G2vT4Y1Kz3XwR9pNc6mEoAt5LhWjB'

/** Builds a well-formed `Funding` fixture — a CEX-sourced 1-hop trace. Each test overrides only
 * the field(s) it cares about. */
function makeFunding(overrides: Partial<Funding> = {}): Funding {
  return {
    mint: MINT,
    deployer: DEPLOYER,
    funder: FUNDER,
    source_type: 'cex',
    funded_at: '2026-06-30T12:00:00Z',
    ...overrides,
  }
}

describe('FundingTrail', () => {
  it('renders 3 trail nodes: upper-cased origin, truncated funder, and high-colored truncated deployer', () => {
    const funding = makeFunding({ source_type: 'cex' })
    const { container } = render(<FundingTrail funding={funding} />)

    const nodes = container.querySelectorAll('.tnode')
    expect(nodes).toHaveLength(3)

    expect(nodes[0].querySelector('.tt')).toHaveTextContent('CEX')
    expect(nodes[0].querySelector('.ts')).toHaveTextContent('origin')

    expect(nodes[1].querySelector('.tt')).toHaveTextContent(shortAddr(FUNDER))
    expect(nodes[1].querySelector('.ts')).toHaveTextContent('funder')

    const deployerTt = nodes[2].querySelector('.tt') as HTMLElement
    expect(deployerTt).toHaveTextContent(shortAddr(DEPLOYER))
    expect(deployerTt.style.color).toBe('var(--high)')
    expect(nodes[2].querySelector('.ts')).toHaveTextContent('deployer')
  })

  it('renders "unknown" in the funder node when funder is null', () => {
    const funding = makeFunding({ funder: null })
    const { container } = render(<FundingTrail funding={funding} />)

    const nodes = container.querySelectorAll('.tnode')
    expect(nodes[1].querySelector('.tt')).toHaveTextContent('unknown')
  })

  it('degrades to an unavailable message and renders no trail when funding.error is present', () => {
    const funding = { mint: MINT, error: 'Helius RPC failed' } as Funding
    const { container } = render(<FundingTrail funding={funding} />)

    expect(container.querySelector('.clean-note')).toHaveTextContent(
      'Funding trail unavailable — Helius RPC failed.'
    )
    expect(container.querySelector('.trail')).not.toBeInTheDocument()
  })
})
