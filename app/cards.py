"""Pure serializers: engine verdict/result -> card-shaped JSON for the dashboard.
No network, no engine mutation — composes over assess_and_act's dict output,
memory.cluster's ClusterGraph, and DexScreener's raw pair dicts."""
from __future__ import annotations

from datetime import datetime, timedelta

from anamnesis.memory.cluster import ClusterGraph


def _rugs(remembered: list[dict]) -> list[dict]:
    # First-party RUGGED edges only (the provenance-trust distinction the UI labels on), DEDUPED
    # by dst: the memory graph deliberately lets independent first-party edges to the SAME rugged
    # mint coexist as corroboration (memory.graph._supersedes), but the card shows and counts
    # DISTINCT tokens — matching the score, which keys trust-weighted risk on dst — so a
    # corroborated rug is one entry, not an inflated count with a duplicate React key downstream.
    seen: set[str] = set()
    rugs: list[dict] = []
    for e in remembered:
        if e.get("type") != "RUGGED" or e.get("method") != "first_party":
            continue
        dst = e["dst"]
        if dst in seen:
            continue
        seen.add(dst)
        rugs.append({"mint": dst, "date": e.get("valid_from")})
    return rugs


def verdict_card(result: dict, mint: str, deployer: str | None) -> dict:
    """Reshape an assess_and_act result dict (verdict_to_dict + acted/watchlisted/alert)
    into card-shaped JSON for the dashboard. `mint`/`deployer` are threaded in from the
    caller (the request mint and profile.deployer) since neither is reliably present on
    `result` itself: `mint` is never in it, and `deployer` only appears nested inside
    `watchlisted`, which is None below HIGH.

    The engine's `Verdict.level` is lowercase ("low"|"medium"|"high" — see
    anamnesis.risk.Verdict / compose_verdict, passed through verbatim by verdict_to_dict).
    Normalized to upper case here so the dashboard's display convention (HIGH/MEDIUM/LOW
    pills) and the provenance gate below agree regardless of the engine's internal casing.
    """
    raw_level = result.get("level")
    level = raw_level.upper() if isinstance(raw_level, str) else raw_level
    score = float(result.get("score", 0.0))
    return {
        "level": level,
        "score": score,
        "mint": mint,
        "deployer": deployer,
        "rationale": result.get("rationale"),
        "provenance": {
            "first_party": round(score, 2) if level in ("HIGH", "MEDIUM") else None,
            "derived": None,   # capped-MEDIUM tier, context in UI only
            "claimed": None,   # context only, never scores
        },
        "memory_rugs": _rugs(result.get("remembered", [])),
        "signals": result.get("signals", []),
        "acted": result.get("acted", False),
        "watchlisted": result.get("watchlisted"),
        "alert": result.get("alert"),
    }


def graph_dict(cluster: ClusterGraph) -> dict:
    """Reshape a `recall_cluster` result (anamnesis.memory.cluster.ClusterGraph) into the
    dashboard's graph contract: `{nodes:[{id,type,flags}], edges:[{src,dst,type}]}`. Pure
    field renaming only (`kind`->`type` on nodes, `rel`->`type` on edges) — no filtering or
    truncation logic of its own; `recall_cluster` already bounds/truncates the walk."""
    return {
        "nodes": [{"id": n.id, "type": n.kind, "flags": list(n.flags)} for n in cluster.nodes],
        "edges": [{"src": e.src, "dst": e.dst, "type": e.rel} for e in cluster.edges],
    }


def _liq_usd(pair: dict) -> float:
    """Liquidity accessor for the top-liquidity `max(...)` selection in `price_points`. A
    non-dict `liquidity` (off-spec upstream data — `DexScreenerClient.token_pairs` validates
    only that the top-level payload is a list, never per-pair field shapes) must contribute
    0 to the comparison rather than raising `AttributeError` on `.get`."""
    liq = pair.get("liquidity")
    return (liq.get("usd") or 0) if isinstance(liq, dict) else 0


def price_points(pairs: list[dict], now: datetime) -> list[dict]:
    """Reconstruct a minimal price sparkline from DexScreener's `priceChange` percent
    buckets (h24/h6/h1/m5) on the top-liquidity pair — an honest approximation, not a real
    time series: the existing DexScreenerClient (anamnesis.forensic.pools) has no history
    endpoint, only current price plus these rolling-window percent changes. `now` is
    injected (never `datetime.now()` internally) so this stays deterministic and
    unit-testable without freezing the clock.

    Each bucket's implied past price is `price_now / (1 + pct/100)`; a bucket reporting
    exactly -100% (or less, which DexScreener should never emit but a malformed payload
    might) is skipped rather than dividing by zero/negative. Points are emitted oldest to
    newest and the current price is always appended last, so the series stays monotonic in
    time even when some buckets are missing.

    Total on any `list[dict]` input — never raises. `GET /api/price/{mint}` calls this
    outside its `except AggregatorError` guard, so a malformed-but-list-of-dicts upstream
    payload (e.g. a truthy non-dict `priceChange` or `liquidity`) must degrade to a partial
    or empty series, not a 500.
    """
    pairs = [p for p in pairs if isinstance(p, dict)]  # drop off-spec non-dict elements up front:
    if not pairs:                                      # token_pairs validates only the top-level
        return []                                      # list, so `_liq_usd`/`.get` below stay safe
    pair = max(pairs, key=_liq_usd)
    try:
        price_now = float(pair.get("priceUsd"))
    except (TypeError, ValueError):
        return []
    pc = pair.get("priceChange")
    if not isinstance(pc, dict):
        pc = {}
    points = []
    for key, mins in (("h24", 1440), ("h6", 360), ("h1", 60), ("m5", 5)):  # oldest -> newest
        ch = pc.get(key)
        if not isinstance(ch, (int, float)) or isinstance(ch, bool):  # None/str/list/dict/bool ->
            continue                                                  # skip (never 1 + str/100 TypeError)
        denom = 1 + ch / 100
        if denom <= 0:  # guard: <= -100% would divide by zero/negative
            continue
        t = (now - timedelta(minutes=mins)).isoformat()
        points.append({"t": t, "price": price_now / denom})
    points.append({"t": now.isoformat(), "price": price_now})  # always end at current
    return points
