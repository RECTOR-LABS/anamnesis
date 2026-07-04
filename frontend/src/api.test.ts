import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  assess,
  getDeployer,
  getFunding,
  getGraph,
  getPrice,
  getProfile,
  streamChat,
} from './api'
import type { DeployerHistory, Funding, GraphData, Profile, Verdict } from './types'

/** Stubs the global `fetch` with a mock resolving to `response` (a partial, loosely-typed
 * stand-in for the DOM `Response` — only the fields each test actually reads: `ok`, `status`,
 * `json`, or `body`). `vi.stubGlobal` takes `unknown`, so this never fights the real ambient
 * `fetch` type that `src/api.ts` itself is checked against. */
function stubFetch(response: Record<string, unknown>) {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** Builds a `ReadableStream<Uint8Array>` that yields each string in `chunks` as one separate
 * `reader.read()` result (encoded via `TextEncoder`), then closes — simulating network chunks
 * that may split an SSE frame's blank-line boundary mid-delimiter. Most fixtures below use the
 * real backend's `\r\n\r\n` framing (sse-starlette's `DEFAULT_SEPARATOR`, see `api/routes/chat.py`);
 * at least one deliberately keeps bare `\n\n` to prove `streamChat`'s CRLF normalizer is a no-op
 * passthrough for a plain-`\n`-framed producer too. */
function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk))
      }
      controller.close()
    },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('assess', () => {
  const verdict: Verdict = {
    level: 'HIGH',
    score: 0.8511,
    mint: 'GYaS',
    deployer: 'sF2ww',
    rationale: 'memory match: 1 first-party rug on this deployer',
    provenance: { first_party: 0.85, derived: null, claimed: null },
    memory_rugs: [{ mint: '3qFSo', date: '2025-11-16' }],
    signals: [{ code: 'HOLDER_CONCENTRATION', severity: 'medium', detail: 'top holder 97.8%' }],
    acted: true,
    watchlisted: { deployer: 'sF2ww', mint: 'GYaS', edge_id: 'edge1' },
    alert: null,
  }

  it('returns the parsed Verdict on a 2xx response', async () => {
    const fetchMock = stubFetch({ ok: true, json: async () => verdict })

    const result = await assess('GYaS')

    expect(result).toEqual(verdict)
    expect(fetchMock).toHaveBeenCalledWith('/api/assess', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mint: 'GYaS' }),
    })
  })

  it('throws a clear, labeled error on a non-2xx response', async () => {
    stubFetch({ ok: false, status: 500 })

    await expect(assess('GYaS')).rejects.toThrow('assess failed: 500')
  })
})

describe('getPrice', () => {
  it('unwraps the {points} envelope into a plain array', async () => {
    const points = [
      { t: '2026-01-03T00:00:00+00:00', price: 1.1 },
      { t: '2026-01-04T00:00:00+00:00', price: 1.3 },
    ]
    stubFetch({ ok: true, json: async () => ({ points }) })

    const result = await getPrice('GYaS')

    expect(result).toEqual(points)
  })

  it('propagates a labeled error on a non-2xx response', async () => {
    stubFetch({ ok: false, status: 404 })

    await expect(getPrice('GYaS')).rejects.toThrow('price failed: 404')
  })
})

describe('GET endpoints', () => {
  it('getProfile hits GET /api/profile/{mint}, URI-encoded, and returns the body verbatim', async () => {
    const profile: Profile = {
      mint: 'GYaS',
      deployer: 'dep1',
      created_at: null,
      mint_authority: null,
      freeze_authority: null,
      lp: { status: 'unknown', evidence: [] },
      top_holder_pct: 12.5,
      holder_count: 400,
    }
    const fetchMock = stubFetch({ ok: true, json: async () => profile })

    const result = await getProfile('mint/with space')

    expect(result).toEqual(profile)
    expect(fetchMock).toHaveBeenCalledWith('/api/profile/mint%2Fwith%20space', undefined)
  })

  it('getDeployer hits GET /api/deployer/{mint} and returns the body verbatim', async () => {
    const history: DeployerHistory = {
      mint: 'GYaS',
      deployer: 'dep1',
      created_mints: [{ mint: 'child1', created_at: '2026-01-01T00:00:00+00:00' }],
      count: 1,
      truncated: false,
    }
    const fetchMock = stubFetch({ ok: true, json: async () => history })

    const result = await getDeployer('GYaS')

    expect(result).toEqual(history)
    expect(fetchMock).toHaveBeenCalledWith('/api/deployer/GYaS', undefined)
  })

  it('getFunding hits GET /api/funding/{mint} and returns the body verbatim', async () => {
    const funding: Funding = {
      mint: 'GYaS',
      deployer: 'dep1',
      funder: 'cex1',
      source_type: 'cex',
      funded_at: '2026-01-01T00:00:00+00:00',
    }
    const fetchMock = stubFetch({ ok: true, json: async () => funding })

    const result = await getFunding('GYaS')

    expect(result).toEqual(funding)
    expect(fetchMock).toHaveBeenCalledWith('/api/funding/GYaS', undefined)
  })

  it('getGraph hits GET /api/graph/{deployer} and returns the body verbatim', async () => {
    const graph: GraphData = {
      nodes: [{ id: 'dep1', type: 'wallet', flags: [] }],
      edges: [],
    }
    const fetchMock = stubFetch({ ok: true, json: async () => graph })

    const result = await getGraph('dep1')

    expect(result).toEqual(graph)
    expect(fetchMock).toHaveBeenCalledWith('/api/graph/dep1', undefined)
  })
})

describe('streamChat', () => {
  it('parses data frames and a terminal done frame, buffering a frame split across the CRLF boundary', async () => {
    // Real sse-starlette framing uses "\r\n" as its line separator (DEFAULT_SEPARATOR), so a
    // genuine frame boundary on the wire is "\r\n\r\n" (CR LF CR LF), not bare "\n\n". This test
    // additionally splits that four-byte boundary mid-delimiter — chunk one ends on the lone
    // leading "\r", chunk two opens with the remaining "\n\r\n" — to prove reassembly survives a
    // CRLF split across a network chunk boundary, not just a bare-"\n\n" split.
    const chunks = [
      'data: {"role":"assistant","content":"Hello"}\r',
      '\n\r\ndata: {"role":"assistant","content":"there"}\r\n\r\nevent: done\r\ndata: \r\n\r\n',
    ]
    stubFetch({ ok: true, body: streamOf(chunks) })

    const onEvent = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    await streamChat('hi', null, onEvent, onDone, onError)

    expect(onEvent).toHaveBeenCalledTimes(2)
    expect(onEvent).toHaveBeenNthCalledWith(1, { role: 'assistant', content: 'Hello' })
    expect(onEvent).toHaveBeenNthCalledWith(2, { role: 'assistant', content: 'there' })
    expect(onDone).toHaveBeenCalledTimes(1)
    expect(onError).not.toHaveBeenCalled()
  })

  it('routes an event: error frame to onError with the parsed message', async () => {
    stubFetch({ ok: true, body: streamOf(['event: error\r\ndata: {"message":"boom"}\r\n\r\n']) })

    const onEvent = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    await streamChat('hi', null, onEvent, onDone, onError)

    expect(onError).toHaveBeenCalledWith('boom')
    expect(onEvent).not.toHaveBeenCalled()
    expect(onDone).not.toHaveBeenCalled()
  })

  it('reports a clear error when the initial response is not ok', async () => {
    stubFetch({ ok: false, status: 500, body: null })

    const onEvent = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    await streamChat('hi', null, onEvent, onDone, onError)

    expect(onError).toHaveBeenCalledWith('chat failed: 500')
    expect(onEvent).not.toHaveBeenCalled()
    expect(onDone).not.toHaveBeenCalled()
  })

  it('parses a data line with no leading space the same as one with a leading space (bare "\\n" framing)', async () => {
    // Deliberately kept bare-"\n"-framed (not "\r\n") — the one fixture in this suite proving the
    // CRLF normalizer is a transparent no-op for a plain "\n\n"-framed producer, not only for the
    // real "\r\n\r\n"-framed backend exercised everywhere else in this block.
    const chunk = 'data:{"role":"assistant","content":"no space"}\n\nevent: done\ndata: \n\n'
    stubFetch({ ok: true, body: streamOf([chunk]) })

    const onEvent = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    await streamChat('hi', null, onEvent, onDone, onError)

    expect(onEvent).toHaveBeenCalledWith({ role: 'assistant', content: 'no space' })
    expect(onDone).toHaveBeenCalledTimes(1)
  })

  it('reports an error when an event payload is malformed JSON', async () => {
    stubFetch({ ok: true, body: streamOf(['data: {not valid json\r\n\r\n']) })

    const onEvent = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    await streamChat('hi', null, onEvent, onDone, onError)

    expect(onError).toHaveBeenCalledWith('chat stream failed: malformed event')
    expect(onDone).not.toHaveBeenCalled()
  })

  it('reports an error if the stream ends without a terminal done/error frame', async () => {
    stubFetch({
      ok: true,
      body: streamOf(['data: {"role":"assistant","content":"partial"}\r\n\r\n']),
    })

    const onEvent = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    await streamChat('hi', null, onEvent, onDone, onError)

    expect(onEvent).toHaveBeenCalledWith({ role: 'assistant', content: 'partial' })
    expect(onDone).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledWith('chat stream ended unexpectedly')
  })

  it('reports an error when the read stream fails mid-transport (dropped connection)', async () => {
    const body = new ReadableStream<Uint8Array>({
      pull() {
        throw new Error('simulated network drop')
      },
    })
    stubFetch({ ok: true, body })

    const onEvent = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    await streamChat('hi', null, onEvent, onDone, onError)

    expect(onError).toHaveBeenCalledWith('chat stream failed: connection lost')
    expect(onDone).not.toHaveBeenCalled()
    expect(onEvent).not.toHaveBeenCalled()
  })

  it('propagates a bug in the caller-supplied onEvent callback instead of misreporting it as a stream failure', async () => {
    // A well-formed frame with a broken consumer callback must surface as a real rejection
    // (a caller bug), not get mislabeled as "malformed event" or "connection lost" — those
    // messages are reserved for genuine payload/transport failures.
    stubFetch({
      ok: true,
      body: streamOf(['data: {"role":"assistant","content":"hi"}\r\n\r\n']),
    })

    const onEvent = vi.fn(() => {
      throw new Error('boom from a consumer render bug')
    })
    const onDone = vi.fn()
    const onError = vi.fn()

    await expect(streamChat('hi', null, onEvent, onDone, onError)).rejects.toThrow(
      'boom from a consumer render bug',
    )
    expect(onError).not.toHaveBeenCalled()
  })
})
