import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Tooltip } from './Tooltip'

describe('Tooltip', () => {
  it('renders the info trigger with the default aria-label and tabIndex 0', () => {
    render(<Tooltip>help text</Tooltip>)

    const trigger = screen.getByLabelText('What is this?')
    expect(trigger).toHaveClass('info')
    expect(trigger).toHaveAttribute('tabindex', '0')
  })

  it('supports a custom label overriding the default', () => {
    render(<Tooltip label="Custom label">help text</Tooltip>)

    expect(screen.getByLabelText('Custom label')).toBeInTheDocument()
    expect(screen.queryByLabelText('What is this?')).not.toBeInTheDocument()
  })

  it('renders children, including bold markup, inside the .tip popover', () => {
    render(
      <Tooltip>
        plain text and <b>bold text</b>
      </Tooltip>,
    )

    const trigger = screen.getByLabelText('What is this?')
    const tip = trigger.querySelector('.tip')
    expect(tip).toHaveTextContent('plain text and bold text')
    expect(tip?.querySelector('b')).toHaveTextContent('bold text')
  })
})
