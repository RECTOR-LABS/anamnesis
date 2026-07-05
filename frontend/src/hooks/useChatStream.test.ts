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
})
