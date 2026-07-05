import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { RiskPill } from './RiskPill'

describe('RiskPill', () => {
  it('renders HIGH as "pill high" with the HIGH RISK label', () => {
    const { container } = render(<RiskPill level="HIGH" />)
    const pill = container.querySelector('.pill')

    expect(pill).toHaveClass('pill', 'high')
    expect(pill).toHaveTextContent('HIGH RISK')
  })

  it('renders MEDIUM as the abbreviated "pill med" with the MEDIUM RISK label', () => {
    const { container } = render(<RiskPill level="MEDIUM" />)
    const pill = container.querySelector('.pill')

    expect(pill).toHaveClass('pill', 'med')
    expect(pill).not.toHaveClass('medium')
    expect(pill).toHaveTextContent('MEDIUM RISK')
  })

  it('renders LOW as "pill low" with the LOW RISK label', () => {
    const { container } = render(<RiskPill level="LOW" />)
    const pill = container.querySelector('.pill')

    expect(pill).toHaveClass('pill', 'low')
    expect(pill).toHaveTextContent('LOW RISK')
  })

  it('renders the .pdot severity indicator inside the pill', () => {
    const { container } = render(<RiskPill level="HIGH" />)
    expect(container.querySelector('.pill > .pdot')).toBeInTheDocument()
  })
})
