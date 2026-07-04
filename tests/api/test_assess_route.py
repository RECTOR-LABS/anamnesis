"""HTTP surface tests for POST /api/assess and GET /api/health, via FastAPI's TestClient
(no network, no real engine, no Mongo/Helius). api.deps.assess is monkeypatched to a fixed
dict matching the REAL shape assess_and_act produces (`level` lowercase, `mint`/`deployer`
present — mirrors api/deps.py's contract, see tests/api/test_deps.py), so these tests prove
the route wires deps.assess -> verdict_card end-to-end, including the lowercase->UPPERCASE
`level` normalization that only verdict_card performs (api/cards.py)."""
from fastapi.testclient import TestClient

from api import deps
from api.main import app

client = TestClient(app)

MINT = "GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump"


def _fake_assess(mint: str) -> dict:
    # Shape returned by the real api.deps.assess: assess_and_act's verdict_to_dict(...) +
    # acted/watchlisted/alert, plus mint/deployer echoed in by deps.assess itself.
    return {
        "level": "high",
        "score": 0.8511,
        "rationale": "…",
        "signals": [
            {"code": "HOLDER_CONCENTRATION", "severity": "medium", "detail": "…"},
        ],
        "remembered": [
            {"type": "RUGGED", "dst": "3qFSo", "valid_from": "2025-11-16", "method": "first_party"},
        ],
        "acted": True,
        "watchlisted": {"deployer": "sF2ww", "mint": mint, "edge_id": "e1"},
        "alert": {"severity": "high"},
        "mint": mint,
        "deployer": "sF2ww",
    }


def test_post_assess_returns_the_verdict_card(monkeypatch):
    # api.deps.assess is patched on the module (not a `from api.deps import assess` alias
    # in the route), so this only works if the route looks it up via `deps.assess(...)`.
    monkeypatch.setattr(deps, "assess", _fake_assess)

    resp = client.post("/api/assess", json={"mint": MINT})

    assert resp.status_code == 200
    body = resp.json()
    # HIGH (not "high") proves the route ran the result through verdict_card, not a
    # pass-through of deps.assess's raw (lowercase) dict.
    assert body["level"] == "HIGH"
    assert body["mint"] == MINT
    assert body["deployer"] == "sF2ww"
    assert {r["mint"] for r in body["memory_rugs"]} == {"3qFSo"}


def test_post_assess_missing_mint_is_422():
    # No monkeypatch: a missing `mint` must fail pydantic validation before the route body
    # (and therefore deps.assess / the engine) ever runs.
    resp = client.post("/api/assess", json={})

    assert resp.status_code == 422


def test_get_health_ok():
    resp = client.get("/api/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
