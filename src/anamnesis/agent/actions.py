"""The 'acts' layer — watchlist + alert drafting triggered off a verdict.

Pure over injected memory + alert stores (CI-testable without qwen-agent). The
pure verdict pipeline (assess.py) is unchanged; this module performs the writes.
"""
from __future__ import annotations

from collections.abc import Callable

from ..assess import assess_risk
from ..forensic.signals import TokenProfile
from ..memory.alerts import AlertDraft, AlertStore
from ..memory.graph import ForensicMemory
from ..memory.models import Edge, Provenance, make_edge
from ..risk import HIGH_THRESHOLD, Verdict
from .serialize import draft_to_dict, verdict_to_dict


def watchlist_add(
    memory: ForensicMemory, deployer: str, mint: str, score: float, now: str
) -> Edge:
    """Record the deployer on the watchlist (a WATCHLISTED edge, deployer -> triggering mint).

    Provenance is `derived` (this is inferred from the verdict, not a first-party on-chain
    observation) — and WATCHLISTED is not a scored type, so a watchlist entry is recall-able
    but can never inflate a future verdict (no feedback loop).
    """
    edge = make_edge(
        "WATCHLISTED", deployer, mint,
        valid_from=now, recorded_at=now,
        provenance=Provenance(
            source="assess_risk", method="derived", confidence=min(1.0, max(0.0, score))
        ),
    )
    memory.remember([edge], now=now)
    return edge


def _evidence_lines(verdict: Verdict) -> list[str]:
    lines = [f"signal: {s.code} ({s.severity}) — {s.detail}" for s in verdict.cited_signals]
    lines += [
        f"memory: {e.type} {e.src}->{e.dst} (method={e.provenance.method})"
        for e in verdict.remembered
    ]
    return lines


def _render_message(deployer: str, mint: str, verdict: Verdict) -> str:
    head = (
        f"[{verdict.level.upper()}] rug-risk on mint {mint} "
        f"(deployer {deployer}, score {verdict.score:.2f})"
    )
    ev = _evidence_lines(verdict)
    if ev:
        return head + "\n" + verdict.rationale + "\nEvidence:\n" + "\n".join(
            f"  - {x}" for x in ev
        )
    return head + "\n" + verdict.rationale


def draft_alert(
    alerts: AlertStore, verdict: Verdict, deployer: str, mint: str, now: str
) -> AlertDraft:
    """Render a pending alert draft from a verdict and persist it (idempotent per
    (deployer, mint) — the store returns the existing pending draft for a repeat pair).
    Drafts are never auto-sent: a human reviews `list_pending_alerts` and decides."""
    draft = AlertDraft(
        id=f"alert:{deployer}->{mint}@{now}",
        deployer=deployer, mint=mint, severity=verdict.level, score=round(verdict.score, 4),
        rationale=verdict.rationale, evidence=_evidence_lines(verdict),
        message=_render_message(deployer, mint, verdict), status="pending", created_at=now,
    )
    return alerts.add_draft(draft)


def assess_and_act(
    memory: ForensicMemory,
    alerts: AlertStore,
    build_profile: Callable[[str], TokenProfile],
    mint: str,
    now: str,
    *,
    as_of: str | None = None,
) -> dict:
    """Assess a mint, and if the verdict is HIGH, auto-watchlist its deployer and draft a
    pending alert. The verdict (the valuable read) is ALWAYS returned; a failed write
    degrades to acted=False + an `error` note rather than discarding the investigation."""
    profile = build_profile(mint)
    verdict = assess_risk(profile, memory, as_of=as_of)
    result = verdict_to_dict(verdict)
    result["acted"] = False
    result["watchlisted"] = None
    result["alert"] = None
    if verdict.score >= HIGH_THRESHOLD and profile.deployer:
        try:
            edge = watchlist_add(memory, profile.deployer, mint, verdict.score, now)
            draft = draft_alert(alerts, verdict, profile.deployer, mint, now)
            result["acted"] = True
            result["watchlisted"] = {
                "deployer": profile.deployer, "mint": mint, "edge_id": edge.id
            }
            result["alert"] = draft_to_dict(draft)
        except Exception as exc:  # keep the verdict; surface only the failure type
            result["error"] = f"act failed: {type(exc).__name__}"
    return result


def list_pending_alerts(alerts: AlertStore) -> dict:
    """The human-in-the-loop review surface: every pending (un-sent) alert draft."""
    pending = alerts.list_pending()
    return {"pending": [draft_to_dict(d) for d in pending], "count": len(pending)}


def watchlist_mint(
    memory: ForensicMemory, build_profile: Callable[[str], TokenProfile], mint: str, now: str
) -> dict:
    """Explicit watchlist: assess the mint and force-watchlist its deployer (no threshold),
    carrying the derived risk score. A no-op with a note when the deployer is unresolved."""
    profile = build_profile(mint)
    if not profile.deployer:
        return {"watchlisted": None, "note": "deployer unresolved; nothing to watchlist"}
    verdict = assess_risk(profile, memory)
    edge = watchlist_add(memory, profile.deployer, mint, verdict.score, now)
    return {"watchlisted": {"deployer": profile.deployer, "mint": mint, "edge_id": edge.id}}


def draft_for_mint(
    memory: ForensicMemory,
    alerts: AlertStore,
    build_profile: Callable[[str], TokenProfile],
    mint: str,
    now: str,
) -> dict:
    """Explicit draft: assess the mint and draft a pending alert regardless of threshold.
    A no-op with a note when the deployer is unresolved."""
    profile = build_profile(mint)
    if not profile.deployer:
        return {"alert": None, "note": "deployer unresolved; cannot draft"}
    verdict = assess_risk(profile, memory)
    draft = draft_alert(alerts, verdict, profile.deployer, mint, now)
    return {"alert": draft_to_dict(draft)}
