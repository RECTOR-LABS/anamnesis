"""JSON-able serializers for edges, verdicts, and alert drafts.

Shared by agent/tools.py and agent/actions.py so neither imports the other
(no cycle) and the dict shapes stay identical across the tool surface.
"""
from __future__ import annotations

from ..memory.alerts import AlertDraft
from ..memory.models import Edge
from ..risk import Verdict


def edge_to_dict(e: Edge) -> dict:
    return {
        "type": e.type, "src": e.src, "dst": e.dst,
        "method": e.provenance.method, "source": e.provenance.source,
        "confidence": e.provenance.confidence, "recorded_at": e.recorded_at,
        "valid_from": e.valid_from, "valid_to": e.valid_to, "superseded_at": e.superseded_at,
    }


def verdict_to_dict(v: Verdict) -> dict:
    return {
        "level": v.level, "score": round(v.score, 4), "rationale": v.rationale,
        "signals": [
            {"code": s.code, "severity": s.severity, "detail": s.detail} for s in v.cited_signals
        ],
        "remembered": [edge_to_dict(e) for e in v.remembered],
    }


def draft_to_dict(d: AlertDraft) -> dict:
    return {
        "id": d.id, "deployer": d.deployer, "mint": d.mint, "severity": d.severity,
        "score": d.score, "rationale": d.rationale, "evidence": list(d.evidence),
        "message": d.message, "status": d.status, "created_at": d.created_at,
    }
