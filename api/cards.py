"""Pure serializers: engine verdict/result -> card-shaped JSON for the dashboard.
No network, no engine mutation — composes over assess_and_act's dict output and
memory.cluster's ClusterGraph."""
from __future__ import annotations

from anamnesis.memory.cluster import ClusterGraph


def _rugs(remembered: list[dict]) -> list[dict]:
    return [{"mint": e["dst"], "date": e.get("valid_from")}
            for e in remembered if e.get("type") == "RUGGED" and e.get("method") == "first_party"]


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
