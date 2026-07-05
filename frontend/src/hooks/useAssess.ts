import { useCallback, useRef, useState } from 'react'
import type { Verdict } from '../types'
import { assess } from '../api'

export interface UseAssessResult {
  verdict: Verdict | null
  loading: boolean
  error: string | null
  run: (mint: string) => void
}

/** Drives `POST /api/assess` for the CommandBar's SCAN action. `verdict` is intentionally NOT
 * cleared when a new `run` starts — it stays in state across the re-run rather than resetting to
 * null (App itself renders a scanning skeleton in place of it while `loading`, per T19).
 * `error` IS cleared at the start of each run, since a fresh scan deserves a fresh chance. On a
 * FAILED scan `verdict` IS cleared, though: a forensic tool must never leave the previous token's
 * risk verdict on screen under the new token's "scan failed" banner.
 *
 * `latest` is a monotonic request id guarding against out-of-order responses: if the user fires a
 * second scan before the first one's request resolves, only the response whose id still matches
 * the CURRENT id may commit state, so a slow, superseded response can never clobber a newer
 * verdict. */
export function useAssess(): UseAssessResult {
  const [verdict, setVerdict] = useState<Verdict | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const latest = useRef(0) // monotonic request id — only the newest run may commit state

  const run = useCallback((mint: string) => {
    const id = ++latest.current
    setLoading(true)
    setError(null)
    assess(mint)
      .then((v) => {
        if (id !== latest.current) return // a newer scan superseded this one — drop the stale result
        setVerdict(v)
        setLoading(false)
      })
      .catch((e) => {
        if (id !== latest.current) return
        setVerdict(null) // drop any prior token's verdict — never show it under this scan's error
        setError(e instanceof Error ? e.message : 'assess failed')
        setLoading(false)
      })
  }, [])

  return { verdict, loading, error, run }
}
