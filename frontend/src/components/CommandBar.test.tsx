import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { CommandBar } from './CommandBar'

/** Renders `<CommandBar>` with sane controlled-prop defaults (empty mint, Lite mode, no-op
 * handlers), letting each test override just the prop(s) it cares about. */
function renderCommandBar(overrides: Partial<ComponentProps<typeof CommandBar>> = {}) {
  return render(
    <CommandBar
      mint=""
      onMintChange={vi.fn()}
      onScan={vi.fn()}
      mode="lite"
      onModeChange={vi.fn()}
      {...overrides}
    />,
  )
}

describe('CommandBar', () => {
  it('calls onMintChange with the typed value', () => {
    const onMintChange = vi.fn()
    renderCommandBar({ onMintChange })

    fireEvent.change(screen.getByLabelText('Token mint address'), { target: { value: 'GYaS' } })

    expect(onMintChange).toHaveBeenCalledWith('GYaS')
  })

  it('calls onScan when the SCAN button is clicked', () => {
    const onScan = vi.fn()
    renderCommandBar({ onScan, mint: 'GYaS' })

    fireEvent.click(screen.getByText('SCAN'))

    expect(onScan).toHaveBeenCalledTimes(1)
  })

  it('calls onScan when Enter is pressed in the input', () => {
    const onScan = vi.fn()
    renderCommandBar({ onScan, mint: 'GYaS' })

    fireEvent.keyDown(screen.getByLabelText('Token mint address'), { key: 'Enter' })

    expect(onScan).toHaveBeenCalledTimes(1)
  })

  it('does not call onScan for a non-Enter key', () => {
    const onScan = vi.fn()
    renderCommandBar({ onScan })

    fireEvent.keyDown(screen.getByLabelText('Token mint address'), { key: 'a' })

    expect(onScan).not.toHaveBeenCalled()
  })

  it('renders the .scanline sweep when scanning is true', () => {
    const { container } = renderCommandBar({ scanning: true })
    expect(container.querySelector('.scanline')).toBeInTheDocument()
  })

  it('omits .scanline when scanning is explicitly false', () => {
    const { container } = renderCommandBar({ scanning: false })
    expect(container.querySelector('.scanline')).not.toBeInTheDocument()
  })

  it('omits .scanline when scanning is not passed at all', () => {
    const { container } = renderCommandBar()
    expect(container.querySelector('.scanline')).not.toBeInTheDocument()
  })

  it('embeds the ModeToggle reflecting the current mode', () => {
    renderCommandBar({ mode: 'pro' })

    expect(screen.getByText('Pro')).toHaveClass('on')
    expect(screen.getByText('Lite')).not.toHaveClass('on')
  })

  it('calls onModeChange when a mode button is clicked', () => {
    const onModeChange = vi.fn()
    renderCommandBar({ mode: 'lite', onModeChange })

    fireEvent.click(screen.getByText('Pro'))

    expect(onModeChange).toHaveBeenCalledWith('pro')
  })
})
