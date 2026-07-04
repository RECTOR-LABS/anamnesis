import { useCallback, useState } from 'react'
import { streamChat } from '../api'

/** UI-facing chat turn — distinct from the wire-level `ChatEvent` in `types.ts` (this is
 * accumulated conversation state, not a single SSE frame). */
export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface UseChatStreamResult {
  messages: ChatMessage[]
  streaming: boolean
  error: string | null
  send: (message: string, mint: string | null) => void
}

/** Drives `ChatPanel`'s "Ask a follow-up" conversation over `streamChat`'s SSE frames. `send`
 * appends a user turn plus an empty assistant turn the moment it fires, then fills that same
 * assistant bubble in place as frames arrive — empty/whitespace-only messages and a second `send`
 * while one is already in flight are both silently ignored.
 *
 * qwen-agent yields the GROWING assistant message on each frame (cumulative content), not a
 * delta — so every `onEvent` REPLACES the last assistant bubble's content with the latest frame
 * rather than appending to it. (Assumption to re-confirm at live smoke / T20; unit-tested here
 * against a mocked `streamChat`.) */
export function useChatStream(): UseChatStreamResult {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const send = useCallback(
    (message: string, mint: string | null) => {
      if (!message.trim() || streaming) return // ignore empties + concurrent sends
      setError(null)
      setStreaming(true)
      // append the user turn + an empty assistant turn we fill as frames arrive
      setMessages((m) => [...m, { role: 'user', content: message }, { role: 'assistant', content: '' }])

      streamChat(
        message,
        mint,
        (e) => {
          if (e.role !== 'assistant') return
          setMessages((m) => {
            const copy = m.slice()
            for (let i = copy.length - 1; i >= 0; i--) {
              if (copy[i].role === 'assistant') {
                copy[i] = { ...copy[i], content: e.content }
                break
              }
            }
            return copy
          })
        },
        () => setStreaming(false),
        (msg) => {
          setError(msg)
          setStreaming(false)
        },
      )
    },
    [streaming],
  )

  return { messages, streaming, error, send }
}
