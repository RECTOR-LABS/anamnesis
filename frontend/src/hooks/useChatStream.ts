import { useCallback, useState } from 'react'
import { streamChat } from '../api'

/** UI-facing chat turn — distinct from the wire-level `ChatEvent` in `types.ts` (this is
 * accumulated conversation state, not a single SSE frame). */
export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  /** Ordered forensic/memory tools this assistant turn invoked — the qwen-agent orchestration
   * trace, projected from each frame's `tool` affordance. Consecutive duplicates collapse (one
   * tool call surfaces as two frames — the about-to-call and its response — both carrying the same
   * name). Absent until the turn calls a tool; drives ChatPanel's live "used …" trace. */
  tools?: string[]
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
          setMessages((m) => {
            // Locate the current (last) assistant turn — the one this frame belongs to.
            let ai = -1
            for (let i = m.length - 1; i >= 0; i--) {
              if (m[i].role === 'assistant') {
                ai = i
                break
              }
            }
            if (ai === -1) return m
            const cur = m[ai]
            let next = cur
            // 1) Record the tool trace (consecutive-dedup). Runs for ANY frame carrying a `tool`
            //    affordance — including the content-less assistant frame emitted while a tool is in
            //    flight and the function-role frame carrying the result — so it is NOT gated on the
            //    assistant/non-empty check below.
            if (e.tool) {
              const prev = next.tools ?? []
              if (prev[prev.length - 1] !== e.tool) {
                next = { ...next, tools: [...prev, e.tool] }
              }
            }
            // 2) Fill the bubble from a non-empty assistant text frame. qwen-agent yields the
            //    GROWING message each frame (cumulative), so REPLACE rather than append; a
            //    content-less or non-assistant frame leaves the streamed text untouched, so a tool
            //    call never blanks the bubble mid-turn.
            if (e.role === 'assistant' && e.content !== '') {
              next = { ...next, content: e.content }
            }
            if (next === cur) return m // nothing changed → same ref, React skips the re-render
            const copy = m.slice()
            copy[ai] = next
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
