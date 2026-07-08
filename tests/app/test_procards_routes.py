"""HTTP tests for the lazy Pro-card data routes: GET /api/profile/{mint},
GET /api/deployer/{mint}, GET /api/funding/{mint}.

No engine logic is exercised here — each route only reuses an existing forensic serializer
from anamnesis.forensic.mcp_tools verbatim (token_profile_dict / deployer_token_history_dict /
trace_funding_dict). Tests stay network-free two ways:

1. app.deps.get_helius is monkeypatched (autouse) to a harmless stub. Every route still calls
   it to obtain a client to pass through, even in these tests where the serializer itself is
   also monkeypatched below — so it must never fall through to a real
   config.require("ANAMNESIS_HELIUS_API_KEY") lookup (unset in CI, and not something an
   HTTP-surface test should depend on regardless of what happens to be in the local shell env).
2. Each route's serializer is monkeypatched on the ROUTE module (`app.routes.<mod>.<name>`),
   not on `anamnesis.forensic.mcp_tools` itself: every route does `from anamnesis.forensic.
   mcp_tools import <name>`, which binds a new name in the route module's namespace, so patching
   the original mcp_tools attribute afterward would not be visible to the route.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from anamnesis.forensic.helius import HeliusError
from app import deps
from app.main import app

client = TestClient(app)

MINT = "GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump"


@pytest.fixture(autouse=True)
def _stub_helius_client(monkeypatch):
    monkeypatch.setattr(deps, "get_helius", lambda: "FAKE_HELIUS_CLIENT")


# ---------------------------------------------------------------------------
# GET /api/profile/{mint}
# ---------------------------------------------------------------------------


def test_get_profile_returns_token_profile_dict_body(monkeypatch):
    profile = {
        "mint": MINT,
        "deployer": "dep1111111111111111111111111111111111111",
        "created_at": "2026-01-01T00:00:00+00:00",
        "mint_authority": None,
        "freeze_authority": None,
        "lp": {"status": "unknown", "evidence": []},
        "top_holder_pct": 12.5,
        "holder_count": 400,
    }
    monkeypatch.setattr("app.routes.profile.token_profile_dict", lambda client, mint: profile)

    resp = client.get(f"/api/profile/{MINT}")

    assert resp.status_code == 200
    assert resp.json() == profile


def test_get_profile_never_500s_on_helius_error(monkeypatch):
    # token_profile_dict IS @_forensic_read-decorated in the real code (it already degrades
    # HeliusError internally) -- this test proves the route's OWN guard holds even if the
    # imported name is swapped for something that raises directly (e.g. under test, or if the
    # decorator is ever removed upstream), per the never-500 discipline of api/routes/price.py.
    def _raise(client, mint):
        raise HeliusError("getAsset failed: HTTP 500")

    monkeypatch.setattr("app.routes.profile.token_profile_dict", _raise)

    resp = client.get(f"/api/profile/{MINT}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["mint"] == MINT
    assert "error" in body


# ---------------------------------------------------------------------------
# GET /api/deployer/{mint}
# ---------------------------------------------------------------------------


def test_get_deployer_returns_deployer_token_history_dict_body(monkeypatch):
    history = {
        "mint": MINT,
        "deployer": "dep1111111111111111111111111111111111111",
        "created_mints": [{"mint": "child1", "created_at": "2026-01-01T00:00:00+00:00"}],
        "count": 1,
        "truncated": False,
    }
    monkeypatch.setattr(
        "app.routes.deployer.deployer_token_history_dict", lambda client, mint: history
    )

    resp = client.get(f"/api/deployer/{MINT}")

    assert resp.status_code == 200
    assert resp.json() == history


def test_get_deployer_degraded_dict_is_still_200_not_500(monkeypatch):
    # deployer_token_history_dict is @_forensic_read-decorated: on a Helius RPC failure it
    # degrades to {"error", "mint"} rather than raising. The route must pass that shape through
    # as-is (never turn a degraded dict into a 500).
    degraded = {"error": "getSignaturesForAddress failed: HTTP 429", "mint": MINT}
    monkeypatch.setattr(
        "app.routes.deployer.deployer_token_history_dict", lambda client, mint: degraded
    )

    resp = client.get(f"/api/deployer/{MINT}")

    assert resp.status_code == 200
    assert resp.json() == degraded


def test_get_deployer_unresolved_deployer_is_200_not_500(monkeypatch):
    # The realistic "miss" path (verified against helius.created_mints, which short-circuits
    # `if not deployer: return [], False`): resolve_origin cannot identify a deployer, so
    # deployer_token_history_dict returns a well-shaped dict with deployer=None and an empty
    # history -- not an {"error"} dict, and never a raise.
    unresolved = {
        "mint": MINT, "deployer": None, "created_mints": [], "count": 0, "truncated": False,
    }
    monkeypatch.setattr(
        "app.routes.deployer.deployer_token_history_dict", lambda client, mint: unresolved
    )

    resp = client.get(f"/api/deployer/{MINT}")

    assert resp.status_code == 200
    assert resp.json() == unresolved


# ---------------------------------------------------------------------------
# GET /api/funding/{mint}
# ---------------------------------------------------------------------------


def test_get_funding_returns_trace_funding_dict_body(monkeypatch):
    funding = {
        "mint": MINT,
        "deployer": "dep1111111111111111111111111111111111111",
        "funder": "cexHot1111111111111111111111111111111111",
        "source_type": "cex",
        "funded_at": "2026-01-01T00:00:00+00:00",
    }
    monkeypatch.setattr("app.routes.funding.trace_funding_dict", lambda client, mint: funding)

    resp = client.get(f"/api/funding/{MINT}")

    assert resp.status_code == 200
    assert resp.json() == funding


def test_get_funding_degraded_dict_is_still_200_not_500(monkeypatch):
    degraded = {"error": "getSignaturesForAddress failed: HTTP 429", "mint": MINT}
    monkeypatch.setattr("app.routes.funding.trace_funding_dict", lambda client, mint: degraded)

    resp = client.get(f"/api/funding/{MINT}")

    assert resp.status_code == 200
    assert resp.json() == degraded


def test_get_funding_unresolved_deployer_is_200_not_500(monkeypatch):
    # Same realistic "miss" path as deployer history (verified against helius.funder_of, which
    # short-circuits `if not deployer: return None, None`, and classify_funder(None) ==
    # "unknown"): an unresolved deployer degrades to nulls/"unknown", never a raise.
    unresolved = {
        "mint": MINT, "deployer": None, "funder": None,
        "source_type": "unknown", "funded_at": None,
    }
    monkeypatch.setattr("app.routes.funding.trace_funding_dict", lambda client, mint: unresolved)

    resp = client.get(f"/api/funding/{MINT}")

    assert resp.status_code == 200
    assert resp.json() == unresolved
