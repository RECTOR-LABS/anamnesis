import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useChatStream } from './useChatStream'
import { streamChat } from '../api'
import type { ChatEvent } from '../types'

vi.mock('../api', () => ({
  streamChat: vi.fn(),
}))

const mockedStreamChat = vi.mocked(streamChat)

describe('useChatStream', () => {
  beforeEach(() => {
    mockedStreamChat.mockReset()
  })

  it('appends a user turn + empty assistant turn, fills the assistant bubble as frames arrive, and clears streaming on done', () => {
    let onEvent!: (e: ChatEvent) => void
    let onDone!: () => void
    mockedStreamChat.mockImplementation((_message, _mint, ev, done) => {
      onEvent = ev
      onDone = done
      return Promise.resolve()
    })

    const { result } = renderHook(() => useChatStream())

    act(() => {
      result.current.send('hi', 'MINT')
    })

    expect(result.current.messages).toEqual([
      { role: 'user', content: 'hi' },
      { role: 'assistant', content: '' },
    ])
    expect(result.current.streaming).toBe(true)
    expect(mockedStreamChat).toHaveBeenCalledWith(
      'hi',
      'MINT',
      expect.any(Function),
      expect.any(Function),
      expect.any(Function),
    )

    act(() => {
      onEvent({ role: 'assistant', content: 'partial' })
    })
    expect(result.current.messages[1].content).toBe('partial')

    // qwen-agent yields cumulative content, so a second frame REPLACES rather than appends.
    act(() => {
      onEvent({ role: 'assistant', content: 'partial answer complete' })
    })
    expect(result.current.messages).toEqual([
      { role: 'user', content: 'hi' },
      { role: 'assistant', content: 'partial answer complete' },
    ])

    act(() => {
      onDone()
    })
    expect(result.current.streaming).toBe(false)
  })

  it('ignores a non-assistant event without touching the assistant bubble', () => {
    let onEvent!: (e: ChatEvent) => void
    mockedStreamChat.mockImplementation((_message, _mint, ev) => {
      onEvent = ev
      return Promise.resolve()
    })
    const { result } = renderHook(() => useChatStream())

    act(() => {
      result.current.send('hi', 'MINT')
    })
    act(() => {
      onEvent({ role: 'tool', content: 'ignored' })
    })

    expect(result.current.messages[1].content).toBe('')
  })

  it('routes onError to the error state and stops streaming', () => {
    let onError!: (msg: string) => void
    mockedStreamChat.mockImplementation((_message, _mint, _ev, _done, err) => {
      onError = err
      return Promise.resolve()
    })
    const { result } = renderHook(() => useChatStream())

    act(() => {
      result.current.send('hi', 'MINT')
    })
    act(() => {
      onError('boom')
    })

    expect(result.current.error).toBe('boom')
    expect(result.current.streaming).toBe(false)
  })

  it('ignores a whitespace-only message: no messages appended, streamChat not called', () => {
    const { result } = renderHook(() => useChatStream())

    act(() => {
      result.current.send('   ', null)
    })

    expect(result.current.messages).toEqual([])
    expect(result.current.streaming).toBe(false)
    expect(mockedStreamChat).not.toHaveBeenCalled()
  })

  it('ignores a second send while a stream is already in flight', () => {
    mockedStreamChat.mockImplementation(() => new Promise<void>(() => {})) // never settles
    const { result } = renderHook(() => useChatStream())

    act(() => {
      result.current.send('first', 'MINT')
    })
    act(() => {
      result.current.send('second', 'MINT')
    })

    expect(mockedStreamChat).toHaveBeenCalledTimes(1)
    expect(result.current.messages).toEqual([
      { role: 'user', content: 'first' },
      { role: 'assistant', content: '' },
    ])
  })

  it('accumulates the frame `tool` affordance onto the assistant turn as an ordered, consecutive-deduped trace', () => {
    let onEvent!: (e: ChatEvent) => void
    mockedStreamChat.mockImplementation((_message, _mint, ev) => {
      onEvent = ev
      return Promise.resolve()
    })
    const { result } = renderHook(() => useChatStream())
    act(() => {
      result.current.send('trace it', 'MINT')
    })

    // One tool call surfaces as two same-name frames (the about-to-call assistant frame + the
    // function-role response), both carrying `tool` — they must collapse to a single trace entry.
    act(() => {
      onEvent({ role: 'assistant', content: '', tool: 'recall' })
    })
    act(() => {
      onEvent({ role: 'tool', content: '{"rugs":3}', tool: 'recall' })
    })
    act(() => {
      onEvent({ role: 'assistant', content: '', tool: 'solana_forensics-trace_funding' })
    })
    act(() => {
      onEvent({ role: 'assistant', content: 'HIGH — 3 prior rugs', tool: 'assess_risk' })
    })

    expect(result.current.messages[1]).toEqual({
      role: 'assistant',
      content: 'HIGH — 3 prior rugs',
      tools: ['recall', 'solana_forensics-trace_funding', 'assess_risk'],
    })
  })

  it("keeps a tool frame's content out of the bubble while still recording its tool name", () => {
    let onEvent!: (e: ChatEvent) => void
    mockedStreamChat.mockImplementation((_message, _mint, ev) => {
      onEvent = ev
      return Promise.resolve()
    })
    const { result } = renderHook(() => useChatStream())
    act(() => {
      result.current.send('hi', 'MINT')
    })
    act(() => {
      onEvent({ role: 'tool', content: 'raw tool json — must not render', tool: 'recall' })
    })

    expect(result.current.messages[1].content).toBe('')
    expect(result.current.messages[1].tools).toEqual(['recall'])
  })

  it('does not shrink the bubble when a tool-boundary micro-frame follows grown content', () => {
    // Live smoke (T20) found qwen-agent RESETS the assistant message at each tool boundary: the
    // about-to-call / function-response frames straddling the boundary carry a `tool` affordance
    // and ~1-char of content. Replacing on every non-empty frame made the bubble visibly
    // shrink/regrow ("typed, deleted, reappeared"). The hook must hold the grown content through
    // those micro-frames and only advance on a longer (or genuine-new-turn) frame.
    let onEvent!: (e: ChatEvent) => void
    mockedStreamChat.mockImplementation((_message, _mint, ev) => {
      onEvent = ev
      return Promise.resolve()
    })
    const { result } = renderHook(() => useChatStream())
    act(() => {
      result.current.send('is it safe?', 'MINT')
    })

    // Turn 1 grows a real answer.
    act(() => {
      onEvent({ role: 'assistant', content: 'Recalling this deployer' })
    })
    expect(result.current.messages[1].content).toBe('Recalling this deployer')

    // Tool-boundary micro-frames: shorter, tool-bearing content. Must NOT clobber the bubble.
    act(() => {
      onEvent({ role: 'assistant', content: ' ', tool: 'recall' })
    })
    act(() => {
      onEvent({ role: 'function', content: '{"rugs":3}', tool: 'recall' })
    })
    act(() => {
      onEvent({ role: 'assistant', content: ' ', tool: 'solana_forensics-trace_funding' })
    })
    expect(result.current.messages[1].content).toBe('Recalling this deployer')

    // The final answer (longer) advances the bubble; the tool trace still records both tools.
    act(() => {
      onEvent({ role: 'assistant', content: 'HIGH — 3 prior rugs compound across sessions' })
    })
    expect(result.current.messages[1].content).toBe('HIGH — 3 prior rugs compound across sessions')
    expect(result.current.messages[1].tools).toEqual(['recall', 'solana_forensics-trace_funding'])
  })

  it('replaces the bubble when a genuine new turn arrives, even if shorter than the prior content', () => {
    // A non-tool, non-cumulative assistant frame is a new turn (not a micro-frame): even if its
    // answer is shorter than an earlier preamble, it must still land in the bubble — otherwise
    // the hook would freeze on the preamble forever.
    let onEvent!: (e: ChatEvent) => void
    mockedStreamChat.mockImplementation((_message, _mint, ev) => {
      onEvent = ev
      return Promise.resolve()
    })
    const { result } = renderHook(() => useChatStream())
    act(() => {
      result.current.send('is it safe?', 'MINT')
    })

    // A long preamble turn.
    act(() => {
      onEvent({ role: 'assistant', content: 'I will thoroughly investigate this deployer now.' })
    })
    expect(result.current.messages[1].content).toBe(
      'I will thoroughly investigate this deployer now.',
    )

    // A genuine new turn (no tool) with a SHORTER answer — must replace, not freeze.
    act(() => {
      onEvent({ role: 'assistant', content: 'HIGH risk.' })
    })
    expect(result.current.messages[1].content).toBe('HIGH risk.')
  })
})
