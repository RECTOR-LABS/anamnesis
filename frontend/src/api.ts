// Typed HTTP client for the Anamnesis dashboard API. Same-origin base URL `/api` — Vite proxies
// it to `localhost:8000` in dev (see vite.config.ts), nginx proxies it to uvicorn in prod.
import type {
  ChatEvent,
  DeployerHistory,
  Funding,
  GraphData,
  Profile,
  PricePoint,
  Verdict,
} from './types'

const BASE_URL = '/api'

/** Shared GET/POST-JSON helper: throws a clear, labeled error on any non-2xx response so
 * callers can render an error state instead of working with a partial/undefined body. */
async function requestJson<T>(url: string, label: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    throw new Error(`${label} failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export function assess(mint: string): Promise<Verdict> {
  return requestJson<Verdict>(`${BASE_URL}/assess`, 'assess', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mint }),
  })
}

export function getProfile(mint: string): Promise<Profile> {
  return requestJson<Profile>(`${BASE_URL}/profile/${encodeURIComponent(mint)}`, 'profile')
}

export function getDeployer(mint: string): Promise<DeployerHistory> {
  return requestJson<DeployerHistory>(`${BASE_URL}/deployer/${encodeURIComponent(mint)}`, 'deployer')
}

export function getFunding(mint: string): Promise<Funding> {
  return requestJson<Funding>(`${BASE_URL}/funding/${encodeURIComponent(mint)}`, 'funding')
}

export function getGraph(deployer: string): Promise<GraphData> {
  return requestJson<GraphData>(`${BASE_URL}/graph/${encodeURIComponent(deployer)}`, 'graph')
}

/** Unwraps the `{points: [...]}` envelope `GET /api/price/{mint}` returns (see
 * `api/routes/price.py`) so callers work with the sparkline array directly. */
export async function getPrice(mint: string): Promise<PricePoint[]> {
  const body = await requestJson<{ points: PricePoint[] }>(
    `${BASE_URL}/price/${encodeURIComponent(mint)}`,
    'price',
  )
  return body.points
}

/** One SSE frame, parsed from raw `event:`/`data:` lines. `event` is `null` for a plain
 * `data:`-only frame (qwen-agent per-chunk yields carry no `event` key — see api/routes/chat.py). */
interface SseFrame {
  event: string | null
  data: string
}

/** Parses one SSE frame's lines (already split from the stream on a blank-line boundary, no
 * trailing `\n\n`). Per the SSE spec, exactly one leading space after the `data:`/`event:`
 * colon is part of the field delimiter and is stripped — anything past that first space is the
 * literal value, so this must not `.trimStart()`, which would also eat meaningful content on a
 * malformed/non-JSON payload. Multiple `data:` lines within one frame are joined with `\n`,
 * matching the SSE multi-line data reconstruction rule. */
function parseSseFrame(frame: string): SseFrame {
  let event: string | null = null
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      let value = line.slice('data:'.length)
      if (value.startsWith(' ')) {
        value = value.slice(1)
      }
      dataLines.push(value)
    }
  }
  return { event, data: dataLines.join('\n') }
}

/** `event: error` frames always carry a `{"message": "..."}` JSON body on the wire (see
 * `api/routes/chat.py::_stream_chat`'s fixed, generic failure message) — the fallback below is
 * defense-in-depth only, in case a proxy or future backend change ever emits a malformed one. */
function parseErrorMessage(data: string): string {
  try {
    const parsed = JSON.parse(data) as { message?: string }
    return parsed.message ?? 'chat stream failed'
  } catch {
    return 'chat stream failed'
  }
}

/** Streams `POST /api/chat` over Server-Sent Events. `EventSource` cannot send a POST body, so
 * this drives `fetch`'s `ReadableStream` directly and parses SSE frames by hand: frames are
 * separated by a blank line, which may land split across chunk boundaries, so incoming bytes are
 * buffered and only complete frames are ever parsed out of it. The backend (`sse-starlette`,
 * driving `api/routes/chat.py`) frames on `\r\n` — its `DEFAULT_SEPARATOR` — so real frames end
 * in `\r\n\r\n`, not bare `\n\n`; every decoded chunk is normalized (CRLF/lone-CR to LF, the full
 * set of line endings the SSE spec permits) before the `\n\n` boundary search below, so parsing
 * works against the real backend as well as any bare-`\n`-framed producer.
 *
 * Every transport/protocol failure (network failure, non-2xx, a dropped connection mid-stream, a
 * malformed event payload, or the stream ending without a terminal event) resolves through
 * `onError` rather than rejecting, so callers can drive the happy path with `onEvent`/`onDone`
 * alone. The one thing this does NOT swallow: if `onEvent`/`onDone`/`onError` themselves throw
 * (a bug in the caller's own callback), that propagates as a normal rejection — attributing it
 * to a transport/parse failure here would send a caller chasing the wrong subsystem. */
export async function streamChat(
  message: string,
  mint: string | null,
  onEvent: (e: ChatEvent) => void,
  onDone: () => void,
  onError: (msg: string) => void,
): Promise<void> {
  let res: Response
  try {
    res = await fetch(`${BASE_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, mint }),
    })
  } catch {
    onError('chat failed: network error')
    return
  }
  if (!res.ok || !res.body) {
    onError(`chat failed: ${res.status}`)
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  try {
    for (;;) {
      // A dropped connection rejects this read (not just resolves done:true) — caught
      // narrowly here so a transport failure maps to its own message, distinct from a
      // malformed-payload failure below.
      let step: ReadableStreamReadResult<Uint8Array>
      try {
        step = await reader.read()
      } catch {
        onError('chat stream failed: connection lost')
        return
      }
      if (step.done) break
      // sse-starlette frames on "\r\n" (see the docstring above), not bare "\n" — normalize
      // CRLF/lone-CR to LF immediately, before any boundary search, so the "\n\n" frame split
      // and per-line parsing below work regardless of which line ending this chunk carries.
      buf += decoder.decode(step.value, { stream: true }).replace(/\r\n|\r/g, '\n')

      let idx: number
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const frame = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        if (frame.trim() === '') {
          continue // keep-alive / comment-only frame — nothing to project onto the wire
        }

        const { event, data } = parseSseFrame(frame)

        if (event === 'done') {
          onDone()
          return
        }
        if (event === 'error') {
          onError(parseErrorMessage(data))
          return
        }
        if (data !== '') {
          let parsed: ChatEvent
          try {
            parsed = JSON.parse(data) as ChatEvent
          } catch {
            onError('chat stream failed: malformed event')
            return
          }
          onEvent(parsed)
        }
      }
    }
    // The stream has ended. `decoder.decode(..., { stream: true })` above withholds the tail
    // bytes of a multi-byte UTF-8 character if it's split across the last physical chunk rather
    // than emitting it — this final no-arg flush finalizes any such pending bytes into `buf`
    // instead of silently dropping them.
    buf += decoder.decode()
  } finally {
    await reader.cancel().catch(() => {})
  }

  // The reader closed naturally without ever emitting a terminal `done`/`error` frame — the
  // backend contract (api/routes/chat.py) always sends one, so this is an anomaly (a dropped
  // connection or proxy timeout), not a valid silent success.
  onError('chat stream ended unexpectedly')
}
