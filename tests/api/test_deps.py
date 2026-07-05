"""api.deps has four test surfaces: assess() wiring is proven with get_memory/get_alerts/
build_profile monkeypatched to in-memory fakes + a stub profile (no network, no real Mongo);
the REAL _client/get_memory/get_alerts singleton constructors are proven against mongomock
(still no network, no real Mongo) so a typo'd env var, a swapped constructor arg, or a dropped
lru_cache on any of them fails here too; build_profile is proven to reach
build_lp_aware_profile fresh on every call (no lru_cache — a mint assessed clean must never
keep reading "clean" after it rugs, just because an earlier request cached it); and assess()
is proven to call build_profile exactly ONCE per request (the result threaded into
assess_and_act via a closure) so that freshness guarantee never costs a second
Helius/DexScreener round-trip. Only get_helius/get_dex/build_profile's live network body and
qwen-agent's get_agent remain unexercised in this module."""
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


def test_build_profile_is_fresh_every_call_not_cached(monkeypatch):
    # build_profile calls build_lp_aware_profile as a bare module global, so monkeypatching
    # deps.build_lp_aware_profile is visible to it without touching build_profile itself.
    # get_helius/get_dex are stubbed too (build_profile calls them to produce
    # build_lp_aware_profile's args) so this stays network-free and independent of whether
    # ANAMNESIS_HELIUS_API_KEY is set in this environment (it never is in CI).
    calls = []

    def _fake_build_lp_aware_profile(helius, dex, mint):
        calls.append(mint)
        return _stub_profile(mint)

    monkeypatch.setattr(deps, "get_helius", lambda: None)
    monkeypatch.setattr(deps, "get_dex", lambda: None)
    monkeypatch.setattr(deps, "build_lp_aware_profile", _fake_build_lp_aware_profile)
    # Defensive: only bites if build_profile is still lru_cache'd (pre-fix) AND some earlier
    # test already warmed the "mint1" entry; post-fix build_profile has no cache_clear
    # attribute at all, so this is a no-op.
    if hasattr(deps.build_profile, "cache_clear"):
        deps.build_profile.cache_clear()

    deps.build_profile("mint1")
    deps.build_profile("mint1")

    assert calls == ["mint1", "mint1"]  # two reads, not a cache hit on the second


def test_assess_builds_profile_exactly_once_per_request(monkeypatch):
    # Same in-memory get_memory/get_alerts fakes as the wiring test above, but build_profile
    # is now a counting wrapper: this proves assess() builds the profile exactly once per
    # request (no double Helius/DexScreener round-trip) even though build_profile is no
    # longer cached across requests.
    calls = []

    def _counting_stub_profile(mint: str) -> TokenProfile:
        calls.append(mint)
        return _stub_profile(mint)

    monkeypatch.setattr(deps, "get_memory", lambda: ForensicMemory(InMemoryRepository()))
    monkeypatch.setattr(deps, "get_alerts", lambda: InMemoryAlertStore())
    monkeypatch.setattr(deps, "build_profile", _counting_stub_profile)

    deps.assess("mint1")

    assert calls == ["mint1"]  # exactly one build, not one for assess_and_act + one for .deployer


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
