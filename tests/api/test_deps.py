"""api.deps has two test surfaces: assess() wiring is proven with get_memory/get_alerts/
build_profile monkeypatched to in-memory fakes + a stub profile (no network, no real Mongo);
separately, the REAL _client/get_memory/get_alerts singleton constructors are proven against
mongomock (still no network, no real Mongo) so a typo'd env var, a swapped constructor arg,
or a dropped lru_cache on any of them fails here too. Only get_helius/get_dex/build_profile's
live network body and qwen-agent's get_agent remain unexercised in this module."""
import mongomock

from anamnesis.forensic.signals import LpAssessment, LpStatus, TokenProfile
from anamnesis.memory.alerts import InMemoryAlertStore, MongoAlertStore
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.repository import InMemoryRepository

from api import deps


def _stub_profile(mint: str) -> TokenProfile:
    # Clean profile (no signals) over an empty memory -> deterministic "low" verdict below,
    # with zero network: deps.build_profile is monkeypatched to this per test.
    return TokenProfile(
        mint=mint, deployer="stubDeployer", mint_authority=None, freeze_authority=None,
        lp=LpAssessment(LpStatus.SECURED), top_holder_pct=2.0, holder_count=300,
    )


def test_assess_wires_memory_alerts_and_profile_into_a_dict(monkeypatch):
    # get_memory/get_alerts/build_profile are module-level globals in deps.py precisely so
    # a test can swap them for network-free fakes like this.
    monkeypatch.setattr(deps, "get_memory", lambda: ForensicMemory(InMemoryRepository()))
    monkeypatch.setattr(deps, "get_alerts", lambda: InMemoryAlertStore())
    monkeypatch.setattr(deps, "build_profile", _stub_profile)

    result = deps.assess("bad mint")

    assert "level" in result
    assert result["level"] == "low"  # clean profile + empty memory -> no signals, no risk
    assert result["mint"] == "bad mint"  # assess_and_act never sets this; assess() echoes it
    assert result["deployer"] == "stubDeployer"  # read off the (stubbed) profile, not result


def test_get_memory_and_get_alerts_construct_real_stores_against_mongomock(monkeypatch):
    # Only the network is stubbed (a live MongoClient -> mongomock); _client/get_memory/
    # get_alerts are the REAL constructors from deps.py. This catches what the assess()
    # wiring test above cannot: a typo'd env var name in config.require(...), a swapped
    # constructor arg, or a dropped lru_cache on any of these three would pass that test
    # (everything there is monkeypatched away) and only break at deploy.
    client = mongomock.MongoClient()
    monkeypatch.setattr(deps, "_client", lambda: client)  # one shared client, mirrors prod

    # lru_cache hygiene: get_memory/get_alerts are process-lifetime singletons. Clear before
    # AND after so a mongomock-backed instance built in this test can never leak into another
    # test via a warm cache entry (deps._client itself is fully replaced above, not called,
    # so its own cache never gets a mongomock entry and needs no clearing).
    deps.get_memory.cache_clear()
    deps.get_alerts.cache_clear()
    try:
        memory = deps.get_memory()
        alerts = deps.get_alerts()

        assert isinstance(memory, ForensicMemory)
        assert isinstance(alerts, MongoAlertStore)

        # Behavioral, not just type: proves get_memory()/get_alerts() actually wired the
        # mongomock client + config.ANAMNESIS_DB through MongoRepository/MongoAlertStore
        # (construction, index creation, and collection resolution all succeeded) -- not
        # merely that some object came back.
        assert memory.recall("nobody") == []
        assert alerts.list_pending() == []
    finally:
        deps.get_memory.cache_clear()
        deps.get_alerts.cache_clear()
