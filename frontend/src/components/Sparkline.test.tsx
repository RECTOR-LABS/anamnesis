import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { Sparkline } from './Sparkline'
import type { PricePoint } from '../types'

/** Builds a `PricePoint[]` fixture from a list of prices, one point per minute starting at a
 * fixed timestamp. Only `price` varies per test — `t` is a throwaway distinct value. */
function makePoints(prices: number[]): PricePoint[] {
  return prices.map((price, i) => ({ t: `2026-07-04T00:${String(i).padStart(2, '0')}:00Z`, price }))
}

describe('Sparkline', () => {
  it('renders one polyline with a coordinate pair per point for a 5-point series', () => {
    const points = makePoints([1, 2, 3, 2, 4])
    const { container } = render(<Sparkline points={points} />)

    const polylines = container.querySelectorAll('polyline')
    expect(polylines).toHaveLength(1)

    const coords = polylines[0].getAttribute('points')?.split(' ')
    expect(coords).toHaveLength(5)
  })

  it('renders a "no recent price activity" note for an empty points array', () => {
    const { container } = render(<Sparkline points={[]} />)
    expect(container.querySelector('svg')).not.toBeInTheDocument()
    expect(container.querySelector('.clean-note')).toHaveTextContent('no recent price activity')
  })

  it('renders a "no recent price activity" note for a single point (cannot draw a line from fewer than 2 points)', () => {
    const { container } = render(<Sparkline points={makePoints([5])} />)
    expect(container.querySelector('svg')).not.toBeInTheDocument()
    expect(container.querySelector('.clean-note')).toHaveTextContent('no recent price activity')
  })

  it('renders a centered flat line with no NaN when all prices are equal', () => {
    const points = makePoints([5, 5, 5])
    const { container } = render(<Sparkline points={points} />)

    const polyline = container.querySelector('polyline')
    expect(polyline).toBeInTheDocument()

    const pointsAttr = polyline?.getAttribute('points') ?? ''
    expect(pointsAttr).not.toContain('NaN')

    const ys = pointsAttr.split(' ').map((pair) => pair.split(',')[1])
    ys.forEach((y) => expect(y).toBe('14.00'))
  })
})
