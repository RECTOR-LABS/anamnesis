import { useState } from 'react'
import type { ChatMessage } from '../hooks/useChatStream'
import { Card } from './Card'
import { Markdown } from './Markdown'

interface ChatPanelProps {
  messages: ChatMessage[]
  streaming: boolean
  /** App binds the current mint; ChatPanel only ever hands back the typed text. */
  onSend: (message: string) => void
  /** Surfaces `useChatStream`'s `error` (a rejected/failed SSE stream) inside the card. */
  error?: string | null
}

/** The "Ask a follow-up" chat card (mockup v4's `.msg`/`.ask` block, pro-only). Renders the
 * conversation as alternating `.msg`/`.msg.a` bubbles and a single-line composer. Submission goes
 * through a `<form>` — the mockup used a bare `<label>`, but a form gives Enter-to-submit and the
 * send button correct, accessible semantics while reusing the same `.ask` styling. Input and send
 * are disabled while `streaming` is true, mirroring `useChatStream`'s own concurrent-send guard. */
export function ChatPanel({ messages, streaming, onSend, error }: ChatPanelProps) {
  const [input, setInput] = useState('')

  function submit() {
    const t = input.trim()
    if (!t) return
    onSend(t)
    setInput('')
  }

  return (
    <Card
      title="Ask a follow-up"
      meta="agent"
      info={
        <>
          Ask anything — including <b>"what did you know last week?"</b> The agent replays its
          memory as of any past moment (bi-temporal recall).
        </>
      }
      className="anim pro-only"
    >
      {messages
        // Render an assistant bubble once it has streamed text OR an orchestration trace: the
        // optimistic placeholder appended on send is empty until frames arrive, and hiding a
        // trace-but-no-text-yet turn would hide the live "using recall → …" trace during the tool
        // phase. A truly empty turn (errored before any frame) still stays hidden, so no stray ◈
        // avatar sits over a blank <p> next to the error note.
        .filter((m) => m.role !== 'assistant' || m.content !== '' || !!m.tools?.length)
        .map((m, i) => (
          <div className={m.role === 'assistant' ? 'msg a' : 'msg'} key={i}>
            <div className={m.role === 'assistant' ? 'av a' : 'av u'}>
              {m.role === 'assistant' ? '◈' : 'YOU'}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              {/* The qwen-agent tool trace (recall → forensic reads → assess) — makes the
                  memory-first orchestration visible instead of a black box. */}
              {m.tools && m.tools.length > 0 && (
                <div
                  className="tooltrace"
                  aria-label="tools the agent used"
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: '5px',
                    marginBottom: m.content ? '6px' : '0',
                    fontFamily: 'var(--mono)',
                    fontSize: '10px',
                  }}
                >
                  {m.tools.map((t, ti) => (
                    <span
                      key={ti}
                      style={{
                        color: 'var(--accent)',
                        background: 'var(--accent-dim)',
                        border: '1px solid var(--accent-line)',
                        borderRadius: '5px',
                        padding: '1px 6px',
                      }}
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}
              {/* The agent replies in markdown (headings, bold, lists, a /graphs link) — render it,
                  don't dump raw `###`/`**`. User turns are plain text. */}
              {m.role === 'assistant' ? <Markdown text={m.content} /> : <p>{m.content}</p>}
            </div>
          </div>
        ))}
      {error && (
        <p className="clean-note" style={{ color: 'var(--high)' }}>
          Chat error — {error}
        </p>
      )}
      <form
        className="ask"
        onSubmit={(e) => {
          e.preventDefault()
          submit()
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about funding, holders, or the cluster…"
          aria-label="Ask a follow-up"
          disabled={streaming}
        />
        <button
          type="submit"
          aria-label="Send message"
          disabled={streaming}
          style={{ all: 'unset', display: 'inline-flex', cursor: streaming ? 'default' : 'pointer' }}
        >
          <svg
            className="send"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z" />
          </svg>
        </button>
      </form>
    </Card>
  )
}
