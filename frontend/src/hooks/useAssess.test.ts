import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useAssess } from './useAssess'
import { assess } from '../api'
import type { Verdict } from '../types'

vi.mock('../api', () => ({
  assess: vi.fn(),
}))

const mockedAssess = vi.mocked(assess)

/** Minimal-but-complete `Verdict` fixture — mirrors VerdictCard.test.tsx's factory convention;
 * each test overrides only the field(s) it cares about. */
function makeVerdict(overrides: Partial<Verdict> = {}): Verdict {
  return {
    level: 'LOW',
    score: 0,
    mint: 'MINT',
    deployer: null,
    rationale: null,
    provenance: { first_party: null, derived: null, claimed: null },
    memory_rugs: [],
    signals: [],
    acted: false,
    watchlisted: null,
    alert: null,
    ...overrides,
  }
}

describe('useAssess', () => {
  beforeEach(() => {
    mockedAssess.mockReset()
  })

  it('starts with a null verdict, not loading, no error', () => {
    const { result } = renderHook(() => useAssess())

    expect(result.current.verdict).toBeNull()
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('sets loading while in flight, then commits the verdict on success', async () => {
    let resolve!: (v: Verdict) => void
    mockedAssess.mockReturnValue(
      new Promise<Verdict>((r) => {
        resolve = r
      }),
    )
    const { result } = renderHook(() => useAssess())

    act(() => {
      result.current.run('MINT1')
    })
    expect(result.current.loading).toBe(true)

    await act(async () => {
      resolve(makeVerdict({ mint: 'MINT1' }))
      await Promise.resolve()
    })

    expect(result.current.loading).toBe(false)
    expect(result.current.verdict?.mint).toBe('MINT1')
  })

  it('on rejection sets the error message, clears loading, and clears the prior verdict', async () => {
    mockedAssess.mockResolvedValueOnce(makeVerdict({ mint: 'MINT_OK' }))
    const { result } = renderHook(() => useAssess())

    await act(async () => {
      result.current.run('MINT_OK')
      await Promise.resolve()
    })
    expect(result.current.verdict?.mint).toBe('MINT_OK')

    mockedAssess.mockRejectedValueOnce(new Error('network down'))
    await act(async () => {
      result.current.run('MINT_FAIL')
      await Promise.resolve()
    })

    expect(result.current.error).toBe('network down')
    expect(result.current.loading).toBe(false)
    expect(result.current.verdict).toBe(null) // never leave the prior token's verdict under a failure
  })

  it('race guard: an older run resolving after a newer one does not clobber the newer verdict', async () => {
    let resolveA!: (v: Verdict) => void
    let resolveB!: (v: Verdict) => void
    mockedAssess
      .mockImplementationOnce(
        () =>
          new Promise<Verdict>((r) => {
            resolveA = r
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise<Verdict>((r) => {
            resolveB = r
          }),
      )

    const { result } = renderHook(() => useAssess())

    act(() => {
      result.current.run('MINT_A')
    })
    act(() => {
      result.current.run('MINT_B')
    })

    await act(async () => {
      resolveB(makeVerdict({ mint: 'MINT_B' }))
      await Promise.resolve()
    })
    expect(result.current.verdict?.mint).toBe('MINT_B')

    await act(async () => {
      resolveA(makeVerdict({ mint: 'MINT_A' }))
      await Promise.resolve()
    })
    expect(result.current.verdict?.mint).toBe('MINT_B')
    expect(result.current.loading).toBe(false)
  })
})
