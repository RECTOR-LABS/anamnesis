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
})
