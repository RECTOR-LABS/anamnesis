import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ChatPanel } from './ChatPanel'
import type { ChatMessage } from '../hooks/useChatStream'

/** Renders `<ChatPanel>` with sane controlled-prop defaults (no messages, not streaming, a no-op
 * handler), letting each test override just the prop(s) it cares about — mirrors the
 * `renderCommandBar` helper convention in `CommandBar.test.tsx`. */
function renderChatPanel(overrides: Partial<ComponentProps<typeof ChatPanel>> = {}) {
  return render(<ChatPanel messages={[]} streaming={false} onSend={vi.fn()} {...overrides} />)
}

describe('ChatPanel', () => {
  it('renders a user bubble and an assistant bubble from the message list', () => {
    const messages: ChatMessage[] = [
      { role: 'user', content: 'is this a rug?' },
      { role: 'assistant', content: 'checking memory now' },
    ]
    const { container } = renderChatPanel({ messages })

    const bubbles = container.querySelectorAll('.msg')
    expect(bubbles).toHaveLength(2)

    expect(bubbles[0]).not.toHaveClass('a')
    expect(bubbles[0]).toHaveTextContent('YOU')
    expect(bubbles[0]).toHaveTextContent('is this a rug?')

    expect(bubbles[1]).toHaveClass('msg', 'a')
    expect(bubbles[1]).toHaveTextContent('◈')
    expect(bubbles[1]).toHaveTextContent('checking memory now')
  })

  it('renders no bubbles when messages is empty', () => {
    const { container } = renderChatPanel()
    expect(container.querySelectorAll('.msg')).toHaveLength(0)
  })

  it('submits the trimmed input via onSend and clears the field', () => {
    const onSend = vi.fn()
    renderChatPanel({ onSend })

    const input = screen.getByLabelText('Ask a follow-up') as HTMLInputElement
    fireEvent.change(input, { target: { value: '  what did you know last week?  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))

    expect(onSend).toHaveBeenCalledWith('what did you know last week?')
    expect(input.value).toBe('')
  })

  it('does not call onSend for an empty or whitespace-only input', () => {
    const onSend = vi.fn()
    renderChatPanel({ onSend })

    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    expect(onSend).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Ask a follow-up'), { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    expect(onSend).not.toHaveBeenCalled()
  })

  it('disables the input and send button while streaming', () => {
    renderChatPanel({ streaming: true })

    expect(screen.getByLabelText('Ask a follow-up')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled()
  })

  it('renders a chat-error message when error is set', () => {
    renderChatPanel({ error: 'boom' })
    expect(screen.getByText('Chat error — boom')).toBeInTheDocument()
  })

  it("renders the assistant turn's tool trace as chips", () => {
    const messages: ChatMessage[] = [
      { role: 'user', content: 'is this a rug?' },
      {
        role: 'assistant',
        content: 'HIGH — 3 prior rugs',
        tools: ['recall', 'solana_forensics-trace_funding'],
      },
    ]
    const { container } = renderChatPanel({ messages })
    const trace = container.querySelector('.tooltrace')
    expect(trace).toBeInTheDocument()
    expect(trace).toHaveTextContent('recall')
    expect(trace).toHaveTextContent('solana_forensics-trace_funding')
  })

  it('renders an assistant turn with tools but no text yet, so the trace shows live during the tool phase', () => {
    const messages: ChatMessage[] = [
      { role: 'user', content: 'go' },
      { role: 'assistant', content: '', tools: ['recall'] },
    ]
    const { container } = renderChatPanel({ messages })
    expect(container.querySelectorAll('.msg.a')).toHaveLength(1)
    expect(container.querySelector('.tooltrace')).toHaveTextContent('recall')
  })

  it('still hides a truly empty assistant bubble (no content and no tools)', () => {
    const messages: ChatMessage[] = [
      { role: 'user', content: 'go' },
      { role: 'assistant', content: '' },
    ]
    const { container } = renderChatPanel({ messages })
    expect(container.querySelectorAll('.msg.a')).toHaveLength(0)
  })

  it('renders the assistant reply as formatted markdown, not raw ### / ** text', () => {
    const messages: ChatMessage[] = [
      { role: 'user', content: 'is this a rug?' },
      {
        role: 'assistant',
        content: '### Verdict\n- **Deployer** rugged 3 tokens. See [the graph](/graphs/x.html).',
      },
    ]
    const { container } = renderChatPanel({ messages })
    expect(container.querySelector('.msg.a .md-h')).toHaveTextContent('Verdict')
    expect(container.querySelector('.msg.a strong')).toHaveTextContent('Deployer')
    expect(container.querySelector('.msg.a a')).toHaveAttribute('href', '/graphs/x.html')
    const bubble = container.querySelector('.msg.a')?.textContent ?? ''
    expect(bubble).not.toContain('###')
    expect(bubble).not.toContain('**')
  })

  it('keeps a user turn as plain text (no markdown parsing)', () => {
    const messages: ChatMessage[] = [{ role: 'user', content: '**not bold**' }]
    const { container } = renderChatPanel({ messages })
    expect(container.querySelector('.msg strong')).toBeNull()
    expect(container.querySelector('.msg')?.textContent).toContain('**not bold**')
  })
})
