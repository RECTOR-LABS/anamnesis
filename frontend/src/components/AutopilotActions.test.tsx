import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { AutopilotActions } from './AutopilotActions'
import type { Alert, Watchlisted } from '../types'

// Same GYaS demo token/deployer as the other card fixtures.
const MINT = 'GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump'
const DEPLOYER = 'sF2wwqcTGvNPfBFvBw6P6c1PYuDG3S3M2sV4iF6r1qz'

/** Minimal but type-valid `Watchlisted` fixture — only presence/absence matters to this
 * component, not the field values. */
function makeWatchlisted(overrides: Partial<Watchlisted> = {}): Watchlisted {
  return { deployer: DEPLOYER, mint: MINT, edge_id: 'edge-1', ...overrides }
}

/** Minimal but type-valid `Alert` fixture — same rationale as `makeWatchlisted`. */
function makeAlert(overrides: Partial<Alert> = {}): Alert {
  return {
    id: 'alert-1',
    deployer: DEPLOYER,
    mint: MINT,
    severity: 'high',
    score: 0.85,
    rationale: 'Deployer previously rugged 3 tokens.',
    evidence: ['HOLDER_CONCENTRATION'],
    message: 'High-risk deployer relaunching.',
    status: 'pending',
    created_at: '2026-07-04T00:00:00Z',
    ...overrides,
  }
}

describe('AutopilotActions', () => {
  it('renders both tiles when watchlisted and alert are present, with the alert tile amber-iconed', () => {
    const { container } = render(
      <AutopilotActions watchlisted={makeWatchlisted()} alert={makeAlert()} />
    )

    const tiles = container.querySelectorAll('.act')
    expect(tiles).toHaveLength(2)
    expect(tiles[0]).toHaveTextContent('Deployer watchlisted')
    expect(tiles[1]).toHaveTextContent('Alert drafted')
    expect(tiles[1].querySelector('.ic')).toHaveClass('ic', 'amber')
  })

  it('renders exactly one tile when only watchlisted is present (alert null)', () => {
    const { container } = render(<AutopilotActions watchlisted={makeWatchlisted()} alert={null} />)

    const tiles = container.querySelectorAll('.act')
    expect(tiles).toHaveLength(1)
    expect(tiles[0]).toHaveTextContent('Deployer watchlisted')
    expect(container).not.toHaveTextContent('Alert drafted')
  })

  it('renders no tiles and the no-actions note when both watchlisted and alert are null', () => {
    const { container } = render(<AutopilotActions watchlisted={null} alert={null} />)

    expect(container.querySelectorAll('.act')).toHaveLength(0)
    expect(container.querySelector('.acts')).toHaveTextContent(
      'No autopilot actions — the verdict is below the action threshold.'
    )
  })
})
