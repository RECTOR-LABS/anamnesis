import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { Markdown } from './Markdown'

describe('Markdown', () => {
  it('renders **bold** as <strong>, not literal asterisks', () => {
    const { container } = render(<Markdown text="**Deployer Wallet**: sF2ww" />)
    expect(container.querySelector('strong')).toHaveTextContent('Deployer Wallet')
    expect(container.textContent).not.toContain('**')
  })

  it('renders ### as a heading block, not literal hashes', () => {
    const { container } = render(<Markdown text="### Deployer Information" />)
    expect(container.querySelector('.md-h')).toHaveTextContent('Deployer Information')
    expect(container.textContent).not.toContain('###')
  })

  it('renders "- " lines as a <ul> of <li>', () => {
    const { container } = render(<Markdown text={'- one\n- two'} />)
    const items = container.querySelectorAll('ul li')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('one')
    expect(items[1]).toHaveTextContent('two')
  })

  it('renders numbered lines as an <ol>', () => {
    const { container } = render(<Markdown text={'1. first\n2. second'} />)
    expect(container.querySelectorAll('ol li')).toHaveLength(2)
  })

  it('renders [text](url) as a link opening in a new tab', () => {
    const { container } = render(<Markdown text="see [the graph](/graphs/cluster_x.html)" />)
    const a = container.querySelector('a')
    expect(a).toHaveAttribute('href', '/graphs/cluster_x.html')
    expect(a).toHaveAttribute('target', '_blank')
    expect(a?.getAttribute('rel') ?? '').toContain('noopener')
    expect(a).toHaveTextContent('the graph')
  })

  it('refuses a javascript: link — renders the text, no anchor, no scheme leak', () => {
    const { container } = render(<Markdown text="[click](javascript:alert(1))" />)
    expect(container.querySelector('a')).toBeNull()
    expect(container.textContent).toContain('click')
    expect(container.innerHTML.toLowerCase()).not.toContain('javascript:')
  })

  it('renders `code` as <code>', () => {
    const { container } = render(<Markdown text="wallet `sF2ww`" />)
    expect(container.querySelector('code')).toHaveTextContent('sF2ww')
  })

  it('does not execute raw HTML — escapes it to text (no injected element)', () => {
    const { container } = render(<Markdown text={'<img src=x onerror="alert(1)">'} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toContain('<img')
  })

  it('splits blocks: paragraph + heading + list + paragraph', () => {
    const md = 'Intro line.\n\n### Section\n- a\n- b\n\nOutro line.'
    const { container } = render(<Markdown text={md} />)
    expect(container.querySelectorAll('.md-h')).toHaveLength(1)
    expect(container.querySelectorAll('ul li')).toHaveLength(2)
    expect(container.querySelectorAll('p')).toHaveLength(2)
  })

  it('renders nothing for empty text', () => {
    const { container } = render(<Markdown text="" />)
    expect(container.textContent).toBe('')
  })
})
