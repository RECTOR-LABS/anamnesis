import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { DeployerHistory } from './DeployerHistory'
import type { DeployerHistory as DeployerHistoryData, MemoryRug } from '../types'

/** Truncates the way `DeployerHistory`'s module-private `shortAddr` does. Duplicated here (not
 * imported — the helper is intentionally not exported) so assertions can compute the expected
 * truncated form from the fixture's address instead of hardcoding a magic string. Same form as
 * `EvidenceCard.test.tsx`'s `shortMint` dup. */
const shortAddr = (a: string) => (a.length > 13 ? `${a.slice(0, 5)}…${a.slice(-6)}` : a)

// Same GYaS demo token/deployer as VerdictCard.test.tsx / EvidenceCard.test.tsx / TokenProfileCard.test.tsx.
const MINT = 'GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump'
const DEPLOYER = 'sF2wwqcTGvNPfBFvBw6P6c1PYuDG3S3M2sV4iF6r1qz'

const RUG_MINTS = [
  '3qFSoWZ5w8n3B7pNn9BVi93BjEmFAKerVwoV3z6Fzuad',
  '7wZk9cRt2LpXqYh1MnBv8sDfGjKl4oPqRstUvWxYzAbC',
  'HqNzYtR5vKmXpLd3FgWs9BnJc2VoTe6UiAy8ZrMkPqSx',
]

/** Builds a well-formed `DeployerHistory` fixture — an empty (no prior launches) baseline. Each
 * test overrides only the field(s) it cares about. */
function makeHistory(overrides: Partial<DeployerHistoryData> = {}): DeployerHistoryData {
  return {
    mint: MINT,
    deployer: DEPLOYER,
    created_mints: [],
    count: 0,
    truncated: false,
    ...overrides,
  }
}

function makeMemoryRugs(mints: string[]): MemoryRug[] {
  return mints.map((mint, i) => ({ mint, date: `2025-11-${10 + i}` }))
}

describe('DeployerHistory', () => {
  it('renders exactly 3 rug tiles (glyph "R") for created_mints that are in memoryRugs', () => {
    const memoryRugs = makeMemoryRugs(RUG_MINTS)
    const history = makeHistory({
      created_mints: RUG_MINTS.map((mint) => ({ mint, created_at: '2025-11-01T00:00:00Z' })),
      count: 3,
    })
    const { container } = render(<DeployerHistory history={history} memoryRugs={memoryRugs} />)

    const rugTiles = container.querySelectorAll('.m.rug')
    expect(rugTiles).toHaveLength(3)
    rugTiles.forEach((tile) => expect(tile).toHaveTextContent('R'))
  })

  it('renders the this-token tile as .m.new ("◈") and an unrelated launch as .m.dead ("·")', () => {
    const history = makeHistory({
      created_mints: [
        { mint: MINT, created_at: '2026-06-30T00:00:00Z' },
        { mint: 'Dead11111111111111111111111111111111111111', created_at: '2025-01-01T00:00:00Z' },
      ],
      count: 2,
    })
    const { container } = render(<DeployerHistory history={history} memoryRugs={[]} />)

    const newTiles = container.querySelectorAll('.m.new')
    expect(newTiles).toHaveLength(1)
    expect(newTiles[0]).toHaveTextContent('◈')

    const deadTiles = container.querySelectorAll('.m.dead')
    expect(deadTiles).toHaveLength(1)
    expect(deadTiles[0]).toHaveTextContent('·')
  })

  it('classifies the this-token tile as .m.new even when history.mint is also in memoryRugs', () => {
    const history = makeHistory({
      created_mints: [{ mint: MINT, created_at: '2026-06-30T00:00:00Z' }],
      count: 1,
    })
    const memoryRugs: MemoryRug[] = [{ mint: MINT, date: '2025-01-01' }]
    const { container } = render(<DeployerHistory history={history} memoryRugs={memoryRugs} />)

    expect(container.querySelectorAll('.m.new')).toHaveLength(1)
    expect(container.querySelectorAll('.m.rug')).toHaveLength(0)
  })

  it('shows count as deployed, memoryRugs.length as known rugs (with .bad), and 0 as alive', () => {
    const memoryRugs = makeMemoryRugs(RUG_MINTS)
    // count (13) intentionally exceeds created_mints.length (2) — the truncated-scan case — so
    // the "deployed" stat must read from `history.count`, not `created_mints.length`.
    const history = makeHistory({
      created_mints: [
        { mint: 'Dead11111111111111111111111111111111111111', created_at: '2025-01-01T00:00:00Z' },
        { mint: 'Dead22222222222222222222222222222222222222', created_at: '2025-02-01T00:00:00Z' },
      ],
      count: 13,
      truncated: true,
    })
    const { container } = render(<DeployerHistory history={history} memoryRugs={memoryRugs} />)

    const nums = container.querySelectorAll('.stat2 .n')
    expect(nums[0]).toHaveTextContent('13')
    expect(nums[1]).toHaveTextContent('3')
    expect(nums[1]).toHaveClass('n', 'bad')
    expect(nums[2]).toHaveTextContent('0')
  })

  it('renders the truncated deployer address in .addr', () => {
    const history = makeHistory({ deployer: DEPLOYER })
    const { container } = render(<DeployerHistory history={history} memoryRugs={[]} />)

    expect(container.querySelector('.addr')).toHaveTextContent(shortAddr(DEPLOYER))
  })

  it('renders "unknown" in .addr when deployer is null', () => {
    const history = makeHistory({ deployer: null })
    const { container } = render(<DeployerHistory history={history} memoryRugs={[]} />)

    expect(container.querySelector('.addr')).toHaveTextContent('unknown')
  })

  it('shows "watchlisted" in .meta when watchlisted is true', () => {
    const history = makeHistory()
    const { container } = render(<DeployerHistory history={history} memoryRugs={[]} watchlisted />)

    expect(container.querySelector('.meta')).toHaveTextContent('watchlisted')
  })

  it('shows "deployer" in .meta when watchlisted is false (the default)', () => {
    const history = makeHistory()
    const { container } = render(<DeployerHistory history={history} memoryRugs={[]} />)

    expect(container.querySelector('.meta')).toHaveTextContent('deployer')
  })

  it('renders the no-prior-launches note and no tiles when created_mints is empty', () => {
    const history = makeHistory({ created_mints: [], count: 0 })
    const { container } = render(<DeployerHistory history={history} memoryRugs={[]} />)

    expect(container.querySelector('.clean-note')).toHaveTextContent(
      'No prior launches on record for this deployer.'
    )
    expect(container.querySelectorAll('.m')).toHaveLength(0)
    expect(container.querySelector('.mints')).not.toBeInTheDocument()
  })

  it('degrades to an unavailable message and renders no tile strip when history.error is present', () => {
    const history = { mint: MINT, error: 'Helius RPC failed' } as DeployerHistoryData
    const { container } = render(<DeployerHistory history={history} memoryRugs={[]} />)

    expect(container.querySelector('.clean-note')).toHaveTextContent(
      'Deployer history unavailable — Helius RPC failed.'
    )
    expect(container.querySelector('.mints')).not.toBeInTheDocument()
  })
})
