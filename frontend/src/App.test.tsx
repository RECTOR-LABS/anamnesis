import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import App from './App'

describe('App', () => {
  it('mounts without crashing and renders the dashboard shell', () => {
    const { container } = render(<App />)

    expect(container.querySelector('.wrap')).toBeInTheDocument()
    expect(screen.getByText(/Anamnesis — dashboard shell/i)).toBeInTheDocument()
  })
})
