import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryBand } from './MemoryBand'

describe('MemoryBand', () => {
  it('renders 3 stat tiles', () => {
    const { container } = render(<MemoryBand />)
    expect(container.querySelectorAll('.band > .stat')).toHaveLength(3)
  })

  it('renders the memory-vs-cold-analysis ratio', () => {
    render(<MemoryBand />)
    expect(screen.getByText('99,313×')).toBeInTheDocument()
  })

  it('renders 3 session dots: 2 medium (.d.m) and 1 high (.d.h)', () => {
    const { container } = render(<MemoryBand />)

    expect(container.querySelectorAll('.dots .d')).toHaveLength(3)
    expect(container.querySelectorAll('.dots .d.m')).toHaveLength(2)
    expect(container.querySelectorAll('.dots .d.h')).toHaveLength(1)
  })

  it('renders the MED -> HIGH verdict sharpening', () => {
    const { container } = render(<MemoryBand />)
    const secondStat = container.querySelectorAll('.stat')[1]

    expect(secondStat.querySelector('.sv')).toHaveTextContent('MED → HIGH')
  })

  it('renders the "6 edges" compounding count', () => {
    render(<MemoryBand />)
    expect(screen.getByText('6 edges')).toBeInTheDocument()
  })

  it('renders 6 sparkline bars in each of the two sparkline stats', () => {
    const { container } = render(<MemoryBand />)
    const sparks = container.querySelectorAll('.spark')

    expect(sparks).toHaveLength(2)
    for (const spark of sparks) {
      expect(spark.querySelectorAll('i')).toHaveLength(6)
    }
  })

  it('renders the recall copy with regular spaces standing in for the mockup nbsp', () => {
    const { container } = render(<MemoryBand />)
    const firstStat = container.querySelectorAll('.stat')[0]

    expect(firstStat.querySelector('.ss')).toHaveTextContent(
      'recall in 2.7 ms vs 268 s re-deriving on-chain',
    )
  })
})
