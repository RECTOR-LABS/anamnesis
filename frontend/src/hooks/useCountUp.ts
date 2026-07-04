import { useEffect, useState } from 'react'

const DEFAULT_DURATION = 1100
const DEFAULT_DELAY = 250

/** Reads the OS-level reduced-motion preference at call time — a plain read, not a live
 * subscription, since nothing here needs to react to the setting changing mid-session. A missing
 * `matchMedia` (SSR, or a test environment that hasn't stubbed it) reads as "motion is fine"
 * rather than throwing, since a reduced-motion opt-in should never be assumed. Shared by
 * `useCountUp` below and by `VerdictCard`'s meter-fill animation, so both honor the same signal
 * without duplicating the check. */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Animates a number from 0 up to `target` with the cubic ease-out mockup v4's inline count-up
 * script uses (`e = 1 - (1-t)^3`), starting `delay`ms after mount and running for `duration`ms
 * (defaults 250/1100ms — the mockup's exact timing). Honors `prefers-reduced-motion` by returning
 * `target` immediately with no frame ever scheduled, and falls back the same way when
 * `requestAnimationFrame` isn't available (SSR, or an environment that hasn't polyfilled it) —
 * both cases read as "show the real number, skip the show" rather than a crash or a value stuck
 * at 0. */
export function useCountUp(target: number, opts?: { duration?: number; delay?: number }): number {
  const duration = opts?.duration ?? DEFAULT_DURATION
  const delay = opts?.delay ?? DEFAULT_DELAY
  const skipAnimation =
    prefersReducedMotion() ||
    typeof window === 'undefined' ||
    typeof window.requestAnimationFrame !== 'function'
  const [value, setValue] = useState(() => (skipAnimation ? target : 0))

  useEffect(() => {
    if (skipAnimation) {
      setValue(target)
      return
    }

    let cancelled = false
    let rafId: number | undefined
    let start: number | null = null

    const tick = (now: number) => {
      if (cancelled) return
      if (start === null) start = now
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      setValue(target * eased)
      if (t < 1) {
        rafId = window.requestAnimationFrame(tick)
      }
    }

    const timeoutId = window.setTimeout(() => {
      if (!cancelled) {
        rafId = window.requestAnimationFrame(tick)
      }
    }, delay)

    return () => {
      cancelled = true
      window.clearTimeout(timeoutId)
      if (rafId !== undefined) {
        window.cancelAnimationFrame(rafId)
      }
    }
  }, [target, duration, delay, skipAnimation])

  return value
}
