"""Alert drafts — the human-in-the-loop review queue for B.1.

A high-risk verdict auto-drafts an AlertDraft (status="pending"); it is NEVER
auto-sent. AlertStore mirrors the Repository pattern so the same contract is
proven against the in-memory fake and the Mongo store.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AlertDraft:
    id: str
    deployer: str
    mint: str
    severity: str          # = verdict.level ("low" | "medium" | "high")
    score: float
    rationale: str
    evidence: list[str]    # human-readable lines from cited signals + remembered edges
    message: str           # fully rendered, human-readable alert text
    status: str            # "pending" (never auto-"sent")
    created_at: str


class AlertStore(Protocol):
    def add_draft(self, draft: AlertDraft) -> AlertDraft: ...

    def list_pending(self) -> list[AlertDraft]: ...

    def get(self, draft_id: str) -> AlertDraft | None: ...


class InMemoryAlertStore:
    """Test fake. `add_draft` is idempotent per (deployer, mint) among pending drafts:
    re-drafting an already-pending pair returns the existing draft (no alert spam)."""

    def __init__(self) -> None:
        self._by_id: dict[str, AlertDraft] = {}

    def add_draft(self, draft: AlertDraft) -> AlertDraft:
        for d in self._by_id.values():
            if d.status == "pending" and d.deployer == draft.deployer and d.mint == draft.mint:
                return d
        self._by_id[draft.id] = draft
        return draft

    def list_pending(self) -> list[AlertDraft]:
        pending = [d for d in self._by_id.values() if d.status == "pending"]
        return sorted(pending, key=lambda d: (d.created_at, d.id))

    def get(self, draft_id: str) -> AlertDraft | None:
        return self._by_id.get(draft_id)


ALERTS_COLLECTION = "alert_drafts"


def _draft_to_doc(d: AlertDraft) -> dict[str, Any]:
    return {
        "id": d.id, "deployer": d.deployer, "mint": d.mint, "severity": d.severity,
        "score": d.score, "rationale": d.rationale, "evidence": list(d.evidence),
        "message": d.message, "status": d.status, "created_at": d.created_at,
    }


def _draft_from_doc(doc: dict[str, Any]) -> AlertDraft:
    return AlertDraft(
        id=doc["id"], deployer=doc["deployer"], mint=doc["mint"], severity=doc["severity"],
        score=doc["score"], rationale=doc["rationale"], evidence=list(doc["evidence"]),
        message=doc["message"], status=doc["status"], created_at=doc["created_at"],
    )


class MongoAlertStore:
    """`AlertStore` over a MongoDB / ApsaraDB `alert_drafts` collection. Same idempotency
    contract as InMemoryAlertStore: one pending draft per (deployer, mint)."""

    def __init__(self, client: Any, db_name: str) -> None:
        self._col = client[db_name][ALERTS_COLLECTION]
        self._col.create_index("id", unique=True)
        self._col.create_index([("deployer", 1), ("mint", 1), ("status", 1)])

    def add_draft(self, draft: AlertDraft) -> AlertDraft:
        existing = self._col.find_one(
            {"deployer": draft.deployer, "mint": draft.mint, "status": "pending"}
        )
        if existing is not None:
            return _draft_from_doc(existing)
        self._col.replace_one({"id": draft.id}, _draft_to_doc(draft), upsert=True)
        return draft

    def list_pending(self) -> list[AlertDraft]:
        docs = self._col.find({"status": "pending"}).sort([("created_at", 1), ("id", 1)])
        return [_draft_from_doc(d) for d in docs]

    def get(self, draft_id: str) -> AlertDraft | None:
        doc = self._col.find_one({"id": draft_id})
        return _draft_from_doc(doc) if doc is not None else None
