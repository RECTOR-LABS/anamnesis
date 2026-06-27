"""Alert drafts — the human-in-the-loop review queue for B.1.

A high-risk verdict auto-drafts an AlertDraft (status="pending"); it is NEVER
auto-sent. AlertStore mirrors the Repository pattern so the same contract is
proven against the in-memory fake and the Mongo store.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


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
