import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { TokenProfileCard } from './TokenProfileCard'
import type { Profile } from '../types'

/** Builds a "mostly clean" `Profile` fixture — same demo mint/deployer as `VerdictCard.test.tsx` /
 * `EvidenceCard.test.tsx` (the GYaS token), with both authorities renounced, liquidity unverified,
 * and a 97.8% top holder — the same numbers mockup v4's own Token profile card hardcodes. Each
 * test overrides only the field(s) it cares about. */
function makeProfile(overrides: Partial<Profile> = {}): Profile {
  return {
    mint: 'GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump',
    deployer: 'sF2wwqcTGvNPfBFvBw6P6c1PYuDG3S3M2sV4iF6r1qz',
    created_at: '2026-06-30T20:00:00Z',
    mint_authority: null,
    freeze_authority: null,
    lp: { status: 'unknown', evidence: [] },
    top_holder_pct: 97.8,
    holder_count: 12345,
    ...overrides,
  }
}

// Fixed row order the component contracts to (mint authority, freeze authority, holders, age,
// liquidity, top holder) — indexing `.kv .i` by position disambiguates rows that share a tone
// class (e.g. two `.v.ok` rows when both authorities are renounced).
const ROW = { mintAuth: 0, freezeAuth: 1, holders: 2, age: 3, liquidity: 4, topHolder: 5 }

describe('TokenProfileCard', () => {
  it('renders the mint-authority row as renounced with an ok tone and tick when mint_authority is null', () => {
    const profile = makeProfile({ mint_authority: null })
    const { container } = render(<TokenProfileCard profile={profile} />)

    const value = container.querySelectorAll('.kv .i')[ROW.mintAuth].querySelector('.v')
    expect(value).toHaveClass('v', 'ok')
    expect(value?.querySelector('.tick')).toBeInTheDocument()
    expect(value).toHaveTextContent('renounced')
  })

  it('renders the mint-authority row as active with a warn tone when mint_authority is a live address', () => {
    const profile = makeProfile({ mint_authority: 'C6qWnvzZ3fBXNMs6pBcE2wSJKQ48CvVzuidZ9jyeqE9Y' })
    const { container } = render(<TokenProfileCard profile={profile} />)

    const value = container.querySelectorAll('.kv .i')[ROW.mintAuth].querySelector('.v')
    expect(value).toHaveClass('v', 'warn')
    expect(value).toHaveTextContent('active')
  })

  it('maps lp.status "unknown" to "unverified" with a warn tone', () => {
    const profile = makeProfile({ lp: { status: 'unknown', evidence: [] } })
    const { container } = render(<TokenProfileCard profile={profile} />)

    const value = container.querySelectorAll('.kv .i')[ROW.liquidity].querySelector('.v')
    expect(value).toHaveClass('v', 'warn')
    expect(value).toHaveTextContent('unverified')
  })

  it('maps lp.status "secured" to "secured" with an ok tone', () => {
    const profile = makeProfile({ lp: { status: 'secured', evidence: [] } })
    const { container } = render(<TokenProfileCard profile={profile} />)

    const value = container.querySelectorAll('.kv .i')[ROW.liquidity].querySelector('.v')
    expect(value).toHaveClass('v', 'ok')
    expect(value).toHaveTextContent('secured')
  })

  it('renders a high top_holder_pct as a warn percentage', () => {
    const profile = makeProfile({ top_holder_pct: 97.8 })
    const { container } = render(<TokenProfileCard profile={profile} />)

    const value = container.querySelectorAll('.kv .i')[ROW.topHolder].querySelector('.v')
    expect(value).toHaveClass('v', 'warn')
    expect(value).toHaveTextContent('97.8%')
  })

  it('renders a low top_holder_pct as an ok percentage', () => {
    const profile = makeProfile({ top_holder_pct: 4 })
    const { container } = render(<TokenProfileCard profile={profile} />)

    const value = container.querySelectorAll('.kv .i')[ROW.topHolder].querySelector('.v')
    expect(value).toHaveClass('v', 'ok')
    expect(value).toHaveTextContent('4%')
  })

  it('renders a null top_holder_pct as unknown with no tone', () => {
    const profile = makeProfile({ top_holder_pct: null })
    const { container } = render(<TokenProfileCard profile={profile} />)

    const value = container.querySelectorAll('.kv .i')[ROW.topHolder].querySelector('.v')
    expect(value).not.toHaveClass('ok')
    expect(value).not.toHaveClass('warn')
    expect(value).toHaveTextContent('unknown')
  })

  it('formats holder_count with thousands separators (the no-supply-field substitute)', () => {
    const profile = makeProfile({ holder_count: 12345 })
    const { container } = render(<TokenProfileCard profile={profile} />)

    const value = container.querySelectorAll('.kv .i')[ROW.holders].querySelector('.v')
    expect(value).toHaveTextContent('12,345')
  })

  it('formats a null created_at as unknown age', () => {
    const profile = makeProfile({ created_at: null })
    const { container } = render(<TokenProfileCard profile={profile} />)

    const value = container.querySelectorAll('.kv .i')[ROW.age].querySelector('.v')
    expect(value).toHaveTextContent('unknown')
  })

  it('formats a real created_at as "Nd Nh" against a fixed clock', () => {
    const now = new Date('2026-07-04T00:00:00Z').getTime()
    const spy = vi.spyOn(Date, 'now').mockReturnValue(now)
    try {
      const createdAt = new Date(now - (3 * 24 + 4) * 3_600_000).toISOString() // 3d4h earlier
      const profile = makeProfile({ created_at: createdAt })
      const { container } = render(<TokenProfileCard profile={profile} />)

      const value = container.querySelectorAll('.kv .i')[ROW.age].querySelector('.v')
      expect(value).toHaveTextContent('3d 4h')
    } finally {
      spy.mockRestore()
    }
  })

  it('renders the memory-flips-it note when both authorities are renounced', () => {
    const profile = makeProfile({ mint_authority: null, freeze_authority: null })
    const { container } = render(<TokenProfileCard profile={profile} />)

    expect(container.querySelector('.clean-note')).toHaveTextContent(
      'Memory is what flips it to HIGH.'
    )
  })

  it('omits the memory-flips-it note when mint_authority is not renounced', () => {
    const profile = makeProfile({
      mint_authority: 'C6qWnvzZ3fBXNMs6pBcE2wSJKQ48CvVzuidZ9jyeqE9Y',
      freeze_authority: null,
    })
    const { container } = render(<TokenProfileCard profile={profile} />)

    expect(container.querySelector('.clean-note')).not.toBeInTheDocument()
  })

  it('degrades to an unavailable message and renders no kv grid when profile.error is present', () => {
    const profile = { mint: 'X', error: 'profile unavailable' } as Profile
    const { container } = render(<TokenProfileCard profile={profile} />)

    expect(container.querySelector('.clean-note')).toHaveTextContent(
      'Profile unavailable — profile unavailable.'
    )
    expect(container.querySelector('.kv')).not.toBeInTheDocument()
  })
})
