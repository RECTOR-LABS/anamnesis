import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import App from './App'
import { assess, getDeployer, getFunding, getGraph, getPrice, getProfile, streamChat } from './api'
import type {
  DeployerHistory as DeployerHistoryData,
  Funding,
  GraphData,
  Profile,
  PricePoint,
  Verdict,
} from './types'

vi.mock('./api', () => ({
  assess: vi.fn(),
  getGraph: vi.fn(),
  getPrice: vi.fn(),
  getProfile: vi.fn(),
  getDeployer: vi.fn(),
  getFunding: vi.fn(),
  streamChat: vi.fn(),
}))

const mockedAssess = vi.mocked(assess)
const mockedGetGraph = vi.mocked(getGraph)
const mockedGetPrice = vi.mocked(getPrice)
const mockedGetProfile = vi.mocked(getProfile)
const mockedGetDeployer = vi.mocked(getDeployer)
const mockedGetFunding = vi.mocked(getFunding)
const mockedStreamChat = vi.mocked(streamChat)

// Same GYaS demo token/deployer used across the component fixtures (VerdictCard.test.tsx et al.) —
// it's also App's own pre-filled DEMO_MINT, so the scanned mint and the returned verdict agree.
const MINT = 'GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump'
const DEPLOYER = 'sF2wwqcTGvNPfBFvBw6P6c1PYuDG3S3M2sV4iF6r1qz'

/** A HIGH-from-memory `Verdict` fixture — mirrors the demo token's shape. Each test overrides only
 * the field(s) it cares about. */
function makeVerdict(overrides: Partial<Verdict> = {}): Verdict {
  return {
    level: 'HIGH',
    score: 0.85,
    mint: MINT,
    deployer: DEPLOYER,
    rationale: 'Deployer previously rugged tokens; risk stands regardless of current state.',
    provenance: { first_party: 0.85, derived: null, claimed: null },
    memory_rugs: [{ mint: 'RUG11111111111111111111111111111111111111', date: '2025-11-16' }],
    signals: [],
    acted: true,
    watchlisted: null,
    alert: null,
    ...overrides,
  }
}

function makeGraph(): GraphData {
  return {
    nodes: [
      { id: DEPLOYER, type: 'wallet', flags: ['deployer'] },
      { id: 'RUG11111111111111111111111111111111111111', type: 'token', flags: ['rugged'] },
    ],
    edges: [{ src: DEPLOYER, dst: 'RUG11111111111111111111111111111111111111', type: 'DEPLOYED' }],
  }
}

function makePrice(): PricePoint[] {
  return [
    { t: '2026-07-01T00:00:00Z', price: 1 },
    { t: '2026-07-02T00:00:00Z', price: 2 },
  ]
}

function makeProfile(): Profile {
  return {
    mint: MINT,
    deployer: DEPLOYER,
    created_at: '2026-06-30T20:00:00Z',
    mint_authority: null,
    freeze_authority: null,
    lp: { status: 'unknown', evidence: [] },
    top_holder_pct: 97.8,
    holder_count: 12345,
  }
}

function makeDeployerHistory(): DeployerHistoryData {
  return {
    mint: MINT,
    deployer: DEPLOYER,
    created_mints: [{ mint: MINT, created_at: '2026-06-30T00:00:00Z' }],
    count: 1,
    truncated: false,
  }
}

function makeFunding(): Funding {
  return {
    mint: MINT,
    deployer: DEPLOYER,
    funder: 'Binance7iQqUvS8G2vT4Y1Kz3XwR9pNc6mEoAt5LhWjB',
    source_type: 'cex',
    funded_at: '2026-06-30T12:00:00Z',
  }
}

/** `VerdictCard`'s `useCountUp`/meter-fill both read `prefers-reduced-motion` at render time —
 * stubbing `matchMedia` to always match resolves both synchronously (copied from
 * `VerdictCard.test.tsx`'s convention), which App's tree pulls in the moment a verdict lands. */
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

  mockedAssess.mockReset().mockResolvedValue(makeVerdict())
  mockedGetGraph.mockReset().mockResolvedValue(makeGraph())
  mockedGetPrice.mockReset().mockResolvedValue(makePrice())
  mockedGetProfile.mockReset().mockResolvedValue(makeProfile())
  mockedGetDeployer.mockReset().mockResolvedValue(makeDeployerHistory())
  mockedGetFunding.mockReset().mockResolvedValue(makeFunding())
  mockedStreamChat.mockReset().mockResolvedValue(undefined)
})

describe('App', () => {
  it('runs a scan and renders the live verdict', async () => {
    render(<App />)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'SCAN' }))
    })

    const pill = await screen.findByText('HIGH RISK')
    expect(pill).toHaveClass('pill', 'high')
    expect(screen.getByText(MINT)).toBeInTheDocument()
  })

  it('populates the lazy Pro cards once their reads resolve', async () => {
    const { container } = render(<App />)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'SCAN' }))
    })

    // TokenProfileCard: both authorities render "renounced" once `getProfile` resolves.
    expect((await screen.findAllByText('renounced')).length).toBeGreaterThan(0)
    // ClusterGraph: one .gnode per node once `getGraph` resolves (fired off verdict.deployer).
    expect(container.querySelectorAll('.gnode').length).toBeGreaterThan(0)
  })

  it('toggles Lite/Pro mode via the CommandBar toggle', () => {
    const { container } = render(<App />)

    expect(container.querySelector('.wrap')).toHaveClass('wrap', 'mode-lite')

    fireEvent.click(screen.getByRole('button', { name: 'Pro' }))

    expect(container.querySelector('.wrap')).toHaveClass('wrap', 'mode-pro')
  })

  it('shows a scan-failed message and no verdict card when assess rejects', async () => {
    mockedAssess.mockRejectedValueOnce(new Error('network down'))
    const { container } = render(<App />)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'SCAN' }))
    })

    expect(await screen.findByText(/Scan failed/)).toHaveTextContent('Scan failed — network down')
    expect(container.querySelector('.verdict')).not.toBeInTheDocument()
  })

  it('shows the pre-scan hint and no verdict card before any scan', () => {
    const { container } = render(<App />)

    expect(screen.getByText(/Paste a token mint and press SCAN/)).toBeInTheDocument()
    expect(container.querySelector('.verdict')).not.toBeInTheDocument()
  })

  it('shows an invalid-mint message and does not call assess for a malformed mint', async () => {
    render(<App />)

    fireEvent.change(screen.getByLabelText('Token mint address'), { target: { value: 'not-a-mint' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'SCAN' }))
    })

    expect(screen.getByText(/look like a Solana mint address/)).toBeInTheDocument()
    expect(mockedAssess).not.toHaveBeenCalled()
  })

  it('still scans a valid 44-char base58 mint (guards against an over-eager validator)', async () => {
    render(<App />)

    fireEvent.change(screen.getByLabelText('Token mint address'), { target: { value: MINT } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'SCAN' }))
    })

    expect(mockedAssess).toHaveBeenCalledWith(MINT)
  })

  it('shows skeleton cards in both columns while a scan is in flight, chat unaffected', async () => {
    mockedAssess.mockReturnValueOnce(new Promise(() => {})) // never resolves — stays in `loading`
    const { container } = render(<App />)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'SCAN' }))
    })

    expect(container.querySelectorAll('.skel-card').length).toBe(4) // 2 columns × 2 SkeletonCards
    expect(container.querySelector('.verdict')).not.toBeInTheDocument()
    // ChatPanel renders regardless of the scan being in flight.
    expect(screen.getByLabelText('Ask a follow-up')).toBeInTheDocument()
  })

  it('retries the scan through the Retry button after a failed scan', async () => {
    mockedAssess.mockRejectedValueOnce(new Error('network down'))
    render(<App />)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'SCAN' }))
    })

    expect(await screen.findByText(/Scan failed/)).toHaveTextContent('Scan failed — network down')
    expect(mockedAssess).toHaveBeenCalledTimes(1)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    })

    expect(mockedAssess).toHaveBeenCalledTimes(2)
  })

  it('suppresses the stale scan-failed banner once a format error takes over', async () => {
    mockedAssess.mockRejectedValueOnce(new Error('network down'))
    render(<App />)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'SCAN' }))
    })
    expect(await screen.findByText(/Scan failed/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Token mint address'), { target: { value: 'not-a-mint' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'SCAN' }))
    })

    expect(screen.getByText(/look like a Solana mint address/)).toBeInTheDocument()
    expect(screen.queryByText(/Scan failed/)).not.toBeInTheDocument()
  })
})
