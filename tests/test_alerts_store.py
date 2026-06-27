from anamnesis.memory.alerts import AlertDraft, InMemoryAlertStore


def _draft(deployer="dep", mint="mintZ", created="2026-06-27", did=None):
    return AlertDraft(
        id=did or f"alert:{deployer}->{mint}@{created}",
        deployer=deployer, mint=mint, severity="high", score=0.72,
        rationale="deployer has remembered prior rug history",
        evidence=["memory: RUGGED dep->t1 (method=first_party)"],
        message="[HIGH] rug-risk on mint mintZ", status="pending", created_at=created,
    )


def test_add_list_get():
    store = InMemoryAlertStore()
    d = store.add_draft(_draft())
    assert store.list_pending() == [d]
    assert store.get(d.id) == d


def test_add_draft_idempotent_per_deployer_mint_pending():
    store = InMemoryAlertStore()
    first = store.add_draft(_draft(created="2026-06-27"))
    again = store.add_draft(_draft(created="2026-06-28", did="alert:dep->mintZ@2026-06-28"))
    assert again == first                      # same (deployer,mint) pending -> existing returned
    assert len(store.list_pending()) == 1
