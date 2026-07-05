import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { SeverityDot } from './SeverityDot'

describe('SeverityDot', () => {
  it('maps "medium" to the abbreviated "sev med" class', () => {
    const { container } = render(<SeverityDot severity="medium" />)
    const dot = container.querySelector('span')

    expect(dot).toHaveClass('sev', 'med')
    expect(dot).not.toHaveClass('medium')
  })

  it('renders "sev high" for high severity', () => {
    const { container } = render(<SeverityDot severity="high" />)
    expect(container.querySelector('span')).toHaveClass('sev', 'high')
  })

  it('renders "sev low" for low severity', () => {
    const { container } = render(<SeverityDot severity="low" />)
    expect(container.querySelector('span')).toHaveClass('sev', 'low')
  })

  it('renders an empty span (no text content)', () => {
    const { container } = render(<SeverityDot severity="high" />)
    expect(container.querySelector('span')).toBeEmptyDOMElement()
  })
})
