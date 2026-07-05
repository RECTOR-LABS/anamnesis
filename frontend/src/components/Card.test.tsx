import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Card } from './Card'

describe('Card', () => {
  it('renders the title in an h3 and children in the .card-b body', () => {
    const { container } = render(
      <Card title="Verdict">
        <p>body content</p>
      </Card>,
    )

    expect(screen.getByRole('heading', { level: 3, name: 'Verdict' })).toBeInTheDocument()
    expect(container.querySelector('.card-b')).toContainElement(screen.getByText('body content'))
  })

  it('renders meta when given, inside .card-h', () => {
    const { container } = render(
      <Card title="Evidence" meta="5 findings">
        content
      </Card>,
    )

    expect(container.querySelector('.card-h .meta')).toHaveTextContent('5 findings')
  })

  it('omits .meta when not given', () => {
    const { container } = render(<Card title="Evidence">content</Card>)
    expect(container.querySelector('.meta')).not.toBeInTheDocument()
  })

  it('renders a tooltip trigger when info is given', () => {
    render(
      <Card title="Verdict" info="Explains the verdict">
        content
      </Card>,
    )

    expect(screen.getByLabelText('What is this?')).toBeInTheDocument()
  })

  it('omits the tooltip trigger when info is not given', () => {
    render(<Card title="Verdict">content</Card>)
    expect(screen.queryByLabelText('What is this?')).not.toBeInTheDocument()
  })

  it('appends an extra className onto the .card element (e.g. anim/pro-only)', () => {
    const { container } = render(
      <Card title="Verdict" className="anim pro-only">
        content
      </Card>,
    )

    expect(container.querySelector('.card')).toHaveClass('card', 'anim', 'pro-only')
  })

  it('renders just the base "card" class when no className is given', () => {
    const { container } = render(<Card title="Verdict">content</Card>)
    expect(container.querySelector('.card')).toHaveClass('card')
    expect(container.firstElementChild).toHaveAttribute('class', 'card')
  })
})
