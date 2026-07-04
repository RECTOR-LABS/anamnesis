import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ModeToggle } from './ModeToggle'

describe('ModeToggle', () => {
  it('marks Lite "on" and Pro not-on when mode is "lite"', () => {
    render(<ModeToggle mode="lite" onChange={vi.fn()} />)

    expect(screen.getByText('Lite')).toHaveClass('on')
    expect(screen.getByText('Pro')).not.toHaveClass('on')
  })

  it('marks Pro "on" and Lite not-on when mode is "pro"', () => {
    render(<ModeToggle mode="pro" onChange={vi.fn()} />)

    expect(screen.getByText('Pro')).toHaveClass('on')
    expect(screen.getByText('Lite')).not.toHaveClass('on')
  })

  it('calls onChange with "pro" when the Pro button is clicked', () => {
    const onChange = vi.fn()
    render(<ModeToggle mode="lite" onChange={onChange} />)

    fireEvent.click(screen.getByText('Pro'))

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('pro')
  })

  it('calls onChange with "lite" when the Lite button is clicked', () => {
    const onChange = vi.fn()
    render(<ModeToggle mode="pro" onChange={onChange} />)

    fireEvent.click(screen.getByText('Lite'))

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith('lite')
  })

  it('exposes an accessible "View mode" group', () => {
    render(<ModeToggle mode="lite" onChange={vi.fn()} />)
    expect(screen.getByRole('group', { name: 'View mode' })).toBeInTheDocument()
  })
})
