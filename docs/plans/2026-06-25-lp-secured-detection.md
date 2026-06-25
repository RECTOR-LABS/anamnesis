# LP-secured detection (Phase 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the always-`False` `lp_secured` default with grounded multi-AMM LP burn/lock detection so the `LP_NOT_SECURED` signal finally discriminates, with honest `unknown` and per-pool evidence.

**Architecture:** A keyless aggregator (DexScreener) enumerates a mint's pools; each pool is routed by its **on-chain owning program** (`getAccountInfo(pool).owner`) to a per-venue verifier that proves securedness on Helius (LP-mint supply + largest-holder ownership vs the incinerator and a curated locker allowlist). Results compose by conservative precedence `NOT_SECURED ⊳ UNKNOWN ⊳ SECURED` into a tri-state `LpAssessment` carrying per-pool evidence. Phase 1 covers the four fungible-LP venues (Raydium V4, Raydium CPMM, Meteora DAMM v1, PumpSwap) plus the pump.fun bonding curve; position-NFT venues report `unknown`.

**Tech Stack:** Python ≥3.12, `httpx` (already a dep), `pytest`, `ruff`. No new runtime dependency. Spec: `docs/design/2026-06-25-lp-secured-detection-design.md`.

## Global Constraints

- Python `>=3.12`; 4-space indent (match existing `src/anamnesis/` files); `ruff` clean (`.venv/bin/ruff check .`).
- New modules `forensic/pools.py` and `forensic/lp.py` MUST start with `from __future__ import annotations` (consistent with `signals.py`/`helius.py`). The FastMCP entrypoint `mcp/solana_forensics_mcp.py` MUST NOT (existing rule — breaks tool registration).
- Tests run with `.venv/bin/pytest -q`; the mongo contract suite with `.venv/bin/pytest -q --store=mongo` (unaffected here but must stay green).
- Pure model/logic stays network-free and CI-runnable; network is confined to the two HTTP clients and exercised only by live-validation (key-gated), never in CI.
- Commits: GPG-signed (`git commit -S`, key `BF47B9DC1FA320FA`) authored as RECTOR, conventional-commit subjects, **zero AI attribution**. One logical change per commit.
- Verify like CI before any push: `.venv/bin/ruff check .` · `.venv/bin/pytest -q` · `.venv/bin/pytest -q --store=mongo`.
- Secrets: `ANAMNESIS_HELIUS_API_KEY` only via env, never logged/printed; scrub it from any error string. Live-smoke export recipe: `line=$(grep -E '^(export )?ANAMNESIS_HELIUS_API_KEY=' ~/Documents/secret/.env | tail -1); export ANAMNESIS_HELIUS_API_KEY="${line#*=}"`.
- **Curated constants (cite-or-omit, mainnet-only):**
  - `INCINERATOR = "1nc1nerator11111111111111111111111111111111"`
  - `LP_LOCKERS` = `{LocpQgucEQHbqNABEYvBvwoxCPsSbG91A1QaQhQQqjn: jupiter_lock, strmRqUCoQUgGUan5YhzUZa6KqdzwX5L6FpUxfmKg5m: streamflow, LockrWmn6K5twhz3y9w1dQERbmgSaRkfnTeTKbpofwE: raydium_lock, GsSCS3vPWrtJ5Y9aEVVT65fmrex5P5RGHXdZvsdbWgfo: uncx, UNCX77nZrA3TdAxMEggqG18xxpgiNGT6iqyynPwpoxN: uncx, UNCXdvMRxvz91g3HqFmpZ5NgmL77UH4QRM4NfeL4mQB: uncx, UNCXrB8cZXnmtYM1aSo1Wx3pQaeSZYuF2jCTesXvECs: uncx}`
  - `SECURED_FRACTION_THRESHOLD = 0.95`, `DUST_LIQUIDITY_USD = 1_000.0`
  - Venue program IDs (for owner-routing): Raydium V4 `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8`, Raydium CPMM `CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C`, Meteora DAMM v1 `Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB`, PumpSwap `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`, pump.fun curve `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`.
- **Phase-1 limitation (documented, not a placeholder):** lock detection is owner-match against `LP_LOCKERS`; the locker escrow's unlock-timestamp is **not** decoded in Phase 1 — locker-custodied LP counts as secured with an evidence note `lock duration unverified`. Time-bounded/expired-lock disambiguation is Phase 2. (Burn detection is full.)

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `src/anamnesis/forensic/signals.py` (modify) | pure model: add `LpStatus`/`LpEvidence`/`LpAssessment`; migrate `TokenProfile.lp_secured`→`lp`; signal logic | 1, 9 |
| `src/anamnesis/forensic/pools.py` (create) | discovery: `DexScreenerClient`, `PoolRef`, `discover_pools` | 4 |
| `src/anamnesis/forensic/lp.py` (create) | constants, `secured_fraction`, `aggregate`, venue routing + decoders + verifiers, `LpAnalyzer` | 2, 3, 5, 6, 7, 8 |
| `src/anamnesis/forensic/helius.py` (modify) | `_lp_unanalyzed` default; `LpResolver` type; `build_token_profile` sets `lp=`; `get_account_info`/`get_token_supply` reads | 5, 9 |
| `src/anamnesis/forensic/mcp_tools.py` (modify) | surface `lp` assessment in the profile dict | 10 |
| `mcp/solana_forensics_mcp.py` (modify) | own DexScreener client; inject real `LpAnalyzer` into `get_token_profile`; close on shutdown | 10 |
| `tests/test_lp.py`, `tests/test_pools.py` (create) | unit tests for lp/pools | 2–8 |
| `tests/test_signals.py`, `test_assess.py`, `test_helius.py`, `test_mcp_tools.py`, `test_agent_tools.py` (modify) | migrate `lp_secured=`→`lp=` | 9, 10 |
| `scripts/lp_smoke.py` (create, git-ignored area) | key-gated live validation | 11 |

**Milestones (natural PR/stop points):** Tasks 1–6 + 9–10 = model + discovery + Raydium venues + migration + wiring (a complete, mergeable increment with Raydium burn/lock live and all other venues honest-`unknown`). Tasks 7–8 add PumpSwap + Meteora + pump.fun-curve decoders. Task 11 = live validation.

---

### Task 1: LP model types (additive, pure)

**Files:**
- Modify: `src/anamnesis/forensic/signals.py` (add types after imports, before `TokenProfile`)
- Test: `tests/test_lp_model.py` (create)

**Interfaces:**
- Produces: `LpStatus(SECURED|NOT_SECURED|UNKNOWN)` (str-Enum); `LpEvidence(venue:str, pool:str, lp_mint:str|None, method:str, secured:bool|None, detail:str, liquidity_usd:float|None=None, citation:str|None=None)`; `LpAssessment(status:LpStatus, evidence:list[LpEvidence]=[])`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lp_model.py
from anamnesis.forensic.signals import LpStatus, LpEvidence, LpAssessment


def test_lp_assessment_defaults_to_empty_evidence():
    a = LpAssessment(status=LpStatus.UNKNOWN)
    assert a.status is LpStatus.UNKNOWN
    assert a.evidence == []


def test_lp_status_is_json_friendly_string():
    assert LpStatus.SECURED.value == "secured"
    assert LpStatus.NOT_SECURED.value == "not_secured"


def test_lp_evidence_optional_fields_default_none():
    e = LpEvidence(venue="raydium_v4", pool="P", lp_mint="L", method="lp_mint_burned", secured=True, detail="d")
    assert e.liquidity_usd is None and e.citation is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lp_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'LpStatus'`.

- [ ] **Step 3: Add the model to `signals.py`**

Add `from enum import Enum` to the imports, then insert before `class TokenProfile`:

```python
class LpStatus(str, Enum):
    SECURED = "secured"
    NOT_SECURED = "not_secured"
    UNKNOWN = "unknown"


@dataclass
class LpEvidence:
    venue: str            # "raydium_v4" | "raydium_cpmm" | "meteora_damm_v1" | "pumpswap" | "pumpfun_curve" | "unknown"
    pool: str             # pool / pair address
    lp_mint: str | None   # resolved LP mint (None for bonding curve / unresolved)
    method: str           # lp_mint_burned | lp_locked:<locker> | bonding_curve_custody | withdrawable | position_nft_unverified | discovery_failed | verify_failed
    secured: bool | None  # True | False | None(=unknown for this pool)
    detail: str
    liquidity_usd: float | None = None
    citation: str | None = None


@dataclass
class LpAssessment:
    status: LpStatus
    evidence: list[LpEvidence] = field(default_factory=list)
```

(`field` is already imported in `signals.py`? It uses `@dataclass` only — add `from dataclasses import dataclass, field`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lp_model.py -q` → Expected: 3 passed. Then `.venv/bin/ruff check src/anamnesis/forensic/signals.py`.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/forensic/signals.py tests/test_lp_model.py
git commit -S -m "feat: LP-secured tri-state model (LpStatus/LpEvidence/LpAssessment)"
```

---

### Task 2: `secured_fraction` + curated constants (pure)

**Files:**
- Create: `src/anamnesis/forensic/lp.py`
- Test: `tests/test_lp.py` (create)

**Interfaces:**
- Consumes: nothing on-chain — operates on already-resolved holder dicts `{"owner": str|None, "amount": int|str}`.
- Produces: `INCINERATOR`, `LP_LOCKERS: dict[str,str]`, `SECURED_FRACTION_THRESHOLD`, `DUST_LIQUIDITY_USD`; `secured_fraction(holders: list[dict], supply: int) -> float`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lp.py
from anamnesis.forensic.lp import secured_fraction, INCINERATOR, LP_LOCKERS

_LOCKER = next(iter(LP_LOCKERS))  # a curated locker program id


def test_secured_fraction_counts_incinerator_and_locker_held():
    holders = [
        {"owner": INCINERATOR, "amount": "600"},
        {"owner": _LOCKER, "amount": "350"},
        {"owner": "someDeployer", "amount": "50"},
    ]
    assert secured_fraction(holders, supply=1000) == 0.95


def test_secured_fraction_zero_when_all_withdrawable():
    assert secured_fraction([{"owner": "deployer", "amount": "1000"}], 1000) == 0.0


def test_secured_fraction_zero_supply_is_zero_not_crash():
    assert secured_fraction([{"owner": INCINERATOR, "amount": "0"}], 0) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lp.py -q` → Expected: FAIL — `ModuleNotFoundError: anamnesis.forensic.lp`.

- [ ] **Step 3: Create `lp.py` with constants + `secured_fraction`**

```python
"""LP-securedness verification (Phase 1) — pure verdict logic + on-chain verifiers.

Discovery (forensic/pools.py) enumerates a mint's pools; here each pool is routed by its
owning program to a per-venue verifier that proves securedness against Helius reads, and the
results compose by conservative precedence into an LpAssessment. Burn = LP held by the
incinerator (supply unchanged) or burned out of supply; lock = LP held by a curated, cited
locker program. Aggregator output is never trusted for the verdict — only on-chain reads are.
"""
from __future__ import annotations

# Canonical Solana burn account: tokens sent here are unspendable (supply is NOT decremented).
INCINERATOR = "1nc1nerator11111111111111111111111111111111"

# Cite-or-omit, MAINNET program ids only (see design D6 for sources). owner(LP holder) ∈ keys => locked.
LP_LOCKERS: dict[str, str] = {
    "LocpQgucEQHbqNABEYvBvwoxCPsSbG91A1QaQhQQqjn": "jupiter_lock",
    "strmRqUCoQUgGUan5YhzUZa6KqdzwX5L6FpUxfmKg5m": "streamflow",
    "LockrWmn6K5twhz3y9w1dQERbmgSaRkfnTeTKbpofwE": "raydium_lock",
    "GsSCS3vPWrtJ5Y9aEVVT65fmrex5P5RGHXdZvsdbWgfo": "uncx",
    "UNCX77nZrA3TdAxMEggqG18xxpgiNGT6iqyynPwpoxN": "uncx",
    "UNCXdvMRxvz91g3HqFmpZ5NgmL77UH4QRM4NfeL4mQB": "uncx",
    "UNCXrB8cZXnmtYM1aSo1Wx3pQaeSZYuF2jCTesXvECs": "uncx",
}

SECURED_FRACTION_THRESHOLD = 0.95  # >= this fraction of current LP supply burned+locked => pool secured
DUST_LIQUIDITY_USD = 1_000.0       # pools below this are recorded but never drive the verdict (decoy guard)


def secured_fraction(holders: list[dict], supply: int) -> float:
    """Fraction of *current* LP supply that is immobilized (incinerator-held or locker-held).

    ``holders`` are top LP-token holders already annotated with their resolved owner. The
    denominator is current circulating supply, so a partial SPL-burn that leaves withdrawable
    LP correctly reads below 1.0. Returns 0.0 on zero/unknown supply.
    """
    if not supply:
        return 0.0
    secured = 0
    for h in holders:
        owner = h.get("owner")
        if owner == INCINERATOR or owner in LP_LOCKERS:
            secured += int(h.get("amount") or 0)
    return secured / supply
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lp.py -q` → Expected: 3 passed. `.venv/bin/ruff check src/anamnesis/forensic/lp.py`.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/forensic/lp.py tests/test_lp.py
git commit -S -m "feat: LP secured_fraction + curated incinerator/locker constants"
```

---

### Task 3: `aggregate` precedence (pure)

**Files:**
- Modify: `src/anamnesis/forensic/lp.py`
- Test: `tests/test_lp.py`

**Interfaces:**
- Consumes: `LpEvidence`, `LpStatus` from `signals`; `DUST_LIQUIDITY_USD`.
- Produces: `aggregate(evidence: list[LpEvidence], *, dust_usd: float = DUST_LIQUIDITY_USD) -> LpStatus`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_lp.py
from anamnesis.forensic.lp import aggregate
from anamnesis.forensic.signals import LpEvidence, LpStatus


def _ev(secured, usd, venue="raydium_v4"):
    return LpEvidence(venue=venue, pool="P", lp_mint="L", method="m", secured=secured, detail="d", liquidity_usd=usd)


def test_aggregate_empty_is_unknown():
    assert aggregate([]) is LpStatus.UNKNOWN


def test_aggregate_nondust_unsecured_dominates():
    assert aggregate([_ev(True, 50_000), _ev(False, 20_000)]) is LpStatus.NOT_SECURED


def test_aggregate_dust_unsecured_does_not_drive_verdict():
    # a $50 decoy "unsecured" pool must not override a deep secured pool
    assert aggregate([_ev(True, 80_000), _ev(False, 50)]) is LpStatus.SECURED


def test_aggregate_unknown_when_only_dust_pools():
    assert aggregate([_ev(True, 50), _ev(True, 10)]) is LpStatus.UNKNOWN


def test_aggregate_unknown_when_nondust_has_none():
    assert aggregate([_ev(True, 50_000), _ev(None, 30_000)]) is LpStatus.UNKNOWN


def test_aggregate_secured_when_all_nondust_secured():
    assert aggregate([_ev(True, 50_000), _ev(True, 30_000)]) is LpStatus.SECURED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lp.py -q` → Expected: FAIL — `ImportError: cannot import name 'aggregate'`.

- [ ] **Step 3: Implement `aggregate`**

Add to `lp.py` (import the model at top: `from .signals import LpAssessment, LpEvidence, LpStatus`):

```python
def aggregate(evidence: list[LpEvidence], *, dust_usd: float = DUST_LIQUIDITY_USD) -> LpStatus:
    """Compose per-pool evidence by conservative precedence: NOT_SECURED ⊳ UNKNOWN ⊳ SECURED.

    Only non-dust pools drive the verdict (a dust 'burned' decoy can't hide a deep unsecured
    pool, and a dust unsecured pool can't flag an otherwise-secured token). With no non-dust
    pool, or any non-dust pool we couldn't determine, the honest answer is UNKNOWN.
    """
    if not evidence:
        return LpStatus.UNKNOWN
    nondust = [e for e in evidence if (e.liquidity_usd or 0.0) >= dust_usd]
    if any(e.secured is False for e in nondust):
        return LpStatus.NOT_SECURED
    if not nondust or any(e.secured is None for e in nondust):
        return LpStatus.UNKNOWN
    return LpStatus.SECURED
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lp.py -q` → Expected: all passed. `.venv/bin/ruff check src/anamnesis/forensic/lp.py`.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/forensic/lp.py tests/test_lp.py
git commit -S -m "feat: LP aggregate precedence (NOT_SECURED > UNKNOWN > SECURED, dust-weighted)"
```

---

### Task 4: DexScreener discovery (`pools.py`)

**Files:**
- Create: `src/anamnesis/forensic/pools.py`
- Test: `tests/test_pools.py` (create)

**Interfaces:**
- Produces: `AggregatorError(RuntimeError)`; `PoolRef(pool:str, dex_id:str, liquidity_usd:float|None)`; `DexScreenerClient` (context-manager, `.token_pairs(mint)->list[dict]`); `discover_pools(client, mint)->list[PoolRef]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pools.py
from anamnesis.forensic.pools import PoolRef, discover_pools


class _FakeDex:
    def __init__(self, pairs): self._pairs = pairs
    def token_pairs(self, mint): return self._pairs


def test_discover_pools_maps_pairs_to_poolrefs():
    pairs = [
        {"pairAddress": "POOL1", "dexId": "raydium", "liquidity": {"usd": 42000.0}},
        {"pairAddress": "POOL2", "dexId": "meteora", "liquidity": {"usd": None}},
    ]
    refs = discover_pools(_FakeDex(pairs), "mintA")
    assert refs == [
        PoolRef(pool="POOL1", dex_id="raydium", liquidity_usd=42000.0),
        PoolRef(pool="POOL2", dex_id="meteora", liquidity_usd=None),
    ]


def test_discover_pools_skips_pairs_without_address():
    refs = discover_pools(_FakeDex([{"dexId": "raydium"}]), "mintA")
    assert refs == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_pools.py -q` → Expected: FAIL — module missing.

- [ ] **Step 3: Implement `pools.py`**

```python
"""Pool discovery — keyless DexScreener enumeration of a mint's pools.

DexScreener returns the pool/pair address, a bare ``dexId``, and indexed USD liquidity — but
NOT the LP mint (resolved on-chain later) and not an unambiguous venue (V4/CPMM/CLMM all read
``dexId == "raydium"``). So this layer only enumerates; venue routing and securedness are
on-chain (forensic/lp.py). The interface leaves a seam for a GeckoTerminal fallback (Phase 2).
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

DEXSCREENER_BASE = "https://api.dexscreener.com"


class AggregatorError(RuntimeError):
    """DexScreener was unreachable or returned an unusable payload."""


@dataclass
class PoolRef:
    pool: str
    dex_id: str
    liquidity_usd: float | None


class DexScreenerClient:
    """Minimal keyless DexScreener client (token-pairs lookup)."""

    def __init__(self, *, timeout: float = 20.0) -> None:
        self._client = httpx.Client(timeout=timeout, base_url=DEXSCREENER_BASE)

    def __enter__(self) -> DexScreenerClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def token_pairs(self, mint: str) -> list[dict]:
        """All Solana pairs for a mint; raises AggregatorError on transport/shape failure."""
        try:
            resp = self._client.get(f"/token-pairs/v1/solana/{mint}")
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:  # ValueError = bad JSON
            raise AggregatorError(f"dexscreener token-pairs failed: {e}") from e
        if not isinstance(data, list):
            raise AggregatorError(f"dexscreener token-pairs: expected a list, got {type(data).__name__}")
        return data


def discover_pools(client: DexScreenerClient, mint: str) -> list[PoolRef]:
    """Enumerate a mint's pools as PoolRefs; pairs without an address are skipped."""
    out: list[PoolRef] = []
    for p in client.token_pairs(mint):
        addr = p.get("pairAddress")
        if not addr:
            continue
        usd = ((p.get("liquidity") or {}).get("usd"))
        out.append(PoolRef(pool=addr, dex_id=p.get("dexId") or "", liquidity_usd=usd))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_pools.py -q` → Expected: 2 passed. `.venv/bin/ruff check src/anamnesis/forensic/pools.py`.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/forensic/pools.py tests/test_pools.py
git commit -S -m "feat: DexScreener pool discovery (PoolRef enumeration)"
```

---

### Task 5: Helius account reads + owner-routing helper

**Files:**
- Modify: `src/anamnesis/forensic/helius.py` (add two RPC reads)
- Modify: `src/anamnesis/forensic/lp.py` (add `PROGRAM_TO_VENUE`, `venue_of`, `token_account_owner`, `largest_holders_with_owners`)
- Test: `tests/test_helius.py`, `tests/test_lp.py`

**Interfaces:**
- Produces (helius): `HeliusClient.get_account_info(addr, *, encoding="jsonParsed") -> dict` (returns `result.value`), `HeliusClient.get_token_supply(mint) -> int`.
- Produces (lp): `PROGRAM_TO_VENUE: dict[str,str]`; `venue_of(helius, pool) -> str` (owner-program → venue label, else `"unknown"`); `token_account_owner(helius, token_account) -> str|None`; `largest_holders_with_owners(helius, lp_mint) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_helius.py
def test_get_token_supply_reads_amount():
    class _C(_FakeClient):
        def _rpc(self, method, params):
            assert method == "getTokenSupply"
            return {"value": {"amount": "12345", "decimals": 6}}
    from anamnesis.forensic.helius import HeliusClient
    # exercise via a thin subclass that stubs _rpc
    c = _C.__new__(_C)
    assert HeliusClient.get_token_supply(c, "lpMint") == 12345
```

```python
# append to tests/test_lp.py
from anamnesis.forensic.lp import PROGRAM_TO_VENUE, venue_of, largest_holders_with_owners


class _AcctClient:
    """Fake Helius exposing get_account_info / get_token_largest_accounts for routing tests."""
    def __init__(self, owner_by_addr, largest=None):
        self._owner = owner_by_addr
        self._largest = largest or []
    def get_account_info(self, addr, *, encoding="jsonParsed"):
        return {"owner": self._owner.get(addr)}
    def get_token_largest_accounts(self, mint):
        return self._largest


def test_venue_of_routes_by_owning_program():
    ray_v4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    c = _AcctClient({"POOL": ray_v4})
    assert venue_of(c, "POOL") == "raydium_v4"


def test_venue_of_unknown_program_is_unknown():
    c = _AcctClient({"POOL": "SomeOtherProgram1111111111111111111111111111"})
    assert venue_of(c, "POOL") == "unknown"


def test_largest_holders_with_owners_resolves_each_owner():
    # largest accounts are TOKEN accounts; owner is resolved via get_account_info(parsed)
    c = _AcctClient(
        owner_by_addr={"TA1": "incin", "TA2": "deployer"},
        largest=[{"address": "TA1", "amount": "600"}, {"address": "TA2", "amount": "400"}],
    )
    # patch parsed-owner extraction: get_account_info returns jsonParsed shape here
    c.get_account_info = lambda addr, **_: {"data": {"parsed": {"info": {"owner": {"TA1": "incin", "TA2": "deployer"}[addr]}}}}
    holders = largest_holders_with_owners(c, "lpMint")
    assert holders == [{"owner": "incin", "amount": "600"}, {"owner": "deployer", "amount": "400"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_helius.py::test_get_token_supply_reads_amount tests/test_lp.py -q`
Expected: FAIL — `get_token_supply` / `venue_of` / `largest_holders_with_owners` undefined.

- [ ] **Step 3a: Add reads to `helius.py`**

Add to `class HeliusClient`:

```python
    def get_account_info(self, address: str, *, encoding: str = "jsonParsed") -> dict:
        """Account info for an address — returns ``result.value`` ({} when the account is null)."""
        result = self._rpc("getAccountInfo", [address, {"encoding": encoding}])
        return (result or {}).get("value") or {}

    def get_token_supply(self, mint: str) -> int:
        """Current total supply of a mint (raw base units)."""
        result = self._rpc("getTokenSupply", [mint])
        return int(((result or {}).get("value") or {}).get("amount") or 0)
```

- [ ] **Step 3b: Add routing helpers to `lp.py`**

```python
# program id -> venue label (owner-routing; the grounded alternative to ambiguous aggregator dexIds)
PROGRAM_TO_VENUE: dict[str, str] = {
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "raydium_v4",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "raydium_cpmm",
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": "meteora_damm_v1",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "pumpswap",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pumpfun_curve",
}
FUNGIBLE_LP_VENUES = frozenset({"raydium_v4", "raydium_cpmm", "meteora_damm_v1", "pumpswap"})


def venue_of(helius, pool: str) -> str:
    """Classify a pool by its owning program (on-chain), else 'unknown'."""
    owner = helius.get_account_info(pool).get("owner")
    return PROGRAM_TO_VENUE.get(owner, "unknown")


def token_account_owner(helius, token_account: str) -> str | None:
    """The wallet/program that owns an SPL token account (jsonParsed ``info.owner``)."""
    info = helius.get_account_info(token_account)
    parsed = ((info.get("data") or {}).get("parsed") or {}) if isinstance(info.get("data"), dict) else {}
    return (parsed.get("info") or {}).get("owner")


def largest_holders_with_owners(helius, lp_mint: str) -> list[dict]:
    """Top LP-token holders annotated with their resolved owner (for secured_fraction)."""
    out: list[dict] = []
    for acc in helius.get_token_largest_accounts(lp_mint):
        out.append({"owner": token_account_owner(helius, acc.get("address")), "amount": acc.get("amount")})
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_helius.py tests/test_lp.py -q` → Expected: passed. `.venv/bin/ruff check src/anamnesis/forensic/`.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/forensic/helius.py src/anamnesis/forensic/lp.py tests/test_helius.py tests/test_lp.py
git commit -S -m "feat: Helius account/supply reads + owner-program venue routing"
```

---

### Task 6: Raydium V4/CPMM verifier (LP-mint decode + burn/lock)

**Files:**
- Modify: `src/anamnesis/forensic/lp.py`
- Test: `tests/test_lp.py`

**Interfaces:**
- Consumes: `secured_fraction`, `largest_holders_with_owners`, `LpEvidence`, `PoolRef`.
- Produces: `_pubkey_at(data_b64: str, offset: int) -> str` (base64 account data → base58 pubkey at byte offset); `RAYDIUM_V4_LP_MINT_OFFSET`/`RAYDIUM_CPMM_LP_MINT_OFFSET` (int, **pinned in Step 3 against a captured fixture**); `verify_fungible(helius, pool: PoolRef, venue: str, lp_mint_offset: int) -> LpEvidence`.

> **Offset-pinning (not a placeholder — a fixture-validated reverse-engineering step).** Raydium pool accounts are custom layouts `jsonParsed` will not decode. The LP-mint is a 32-byte `Pubkey` at a fixed offset in the pool struct (`AmmInfo.lp_mint` for V4; `PoolState.lp_mint`, after the 8-byte Anchor discriminator, for CPMM — sources in design References). Step 3 derives the offset from the struct field order and **pins it with a decode-test against a real captured account** whose LP mint is independently known (from `https://api-v3.raydium.io/pools/info/ids?ids=<pool>` → `lpMint.address`). The capture command and the assert are part of the task.

- [ ] **Step 1: Capture a real fixture + write the failing decode test**

Capture (run once, save output into the test as a constant):
```bash
line=$(grep -E '^(export )?ANAMNESIS_HELIUS_API_KEY=' ~/Documents/secret/.env | tail -1); export ANAMNESIS_HELIUS_API_KEY="${line#*=}"
# pick a known Raydium V4 pool (e.g. SOL-USDC 58oQ...) ; get its base64 account data and known lpMint:
.venv/bin/python -c "import os,httpx;u=f'https://mainnet.helius-rpc.com/?api-key={os.environ[\"ANAMNESIS_HELIUS_API_KEY\"]}';\
import json;print(json.dumps(httpx.post(u,json={'jsonrpc':'2.0','id':1,'method':'getAccountInfo','params':['<POOL>',{'encoding':'base64'}]}).json()['result']['value']['data'][0]))"
.venv/bin/python -c "import httpx;print(httpx.get('https://api-v3.raydium.io/pools/info/ids?ids=<POOL>').json()['data'][0]['lpMint']['address'])"
```

```python
# append to tests/test_lp.py
from anamnesis.forensic.lp import _pubkey_at, RAYDIUM_V4_LP_MINT_OFFSET

_RAY_V4_DATA_B64 = "<captured base64 from the command above>"
_RAY_V4_KNOWN_LP_MINT = "<known lpMint from Raydium API>"


def test_pubkey_at_decodes_known_raydium_v4_lp_mint():
    assert _pubkey_at(_RAY_V4_DATA_B64, RAYDIUM_V4_LP_MINT_OFFSET) == _RAY_V4_KNOWN_LP_MINT
```

Also write the venue-verifier test with fakes (no network):
```python
def test_verify_fungible_burned_is_secured():
    from anamnesis.forensic.lp import verify_fungible, INCINERATOR
    from anamnesis.forensic.pools import PoolRef

    class _C:
        def get_account_info(self, addr, *, encoding="jsonParsed"):
            return {"data": [_RAY_V4_DATA_B64, "base64"]} if addr == "POOL" else {"data": {"parsed": {"info": {"owner": INCINERATOR}}}}
        def get_token_supply(self, mint): return 1000
        def get_token_largest_accounts(self, mint): return [{"address": "TA", "amount": "1000"}]

    ev = verify_fungible(_C(), PoolRef("POOL", "raydium", 50_000.0), "raydium_v4", RAYDIUM_V4_LP_MINT_OFFSET)
    assert ev.secured is True and ev.method == "lp_mint_burned" and ev.lp_mint == _RAY_V4_KNOWN_LP_MINT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_lp.py -q` → Expected: FAIL — `_pubkey_at` / `verify_fungible` undefined.

- [ ] **Step 3: Implement decoder + verifier (pin the offset)**

```python
import base64
import base58  # NOTE: add `base58` to pyproject dependencies in this step (see Step 3b)

from .pools import PoolRef


def _pubkey_at(data_b64: str, offset: int) -> str:
    """Decode the base58 pubkey of the 32 bytes at ``offset`` in base64 account data."""
    raw = base64.b64decode(data_b64)
    return base58.b58encode(raw[offset:offset + 32]).decode()


# Pinned against captured fixtures (Step 1). AmmInfo.lp_mint / PoolState.lp_mint (post 8-byte discriminator).
RAYDIUM_V4_LP_MINT_OFFSET = 0    # <- set to the value proven by test_pubkey_at_decodes_known_raydium_v4_lp_mint
RAYDIUM_CPMM_LP_MINT_OFFSET = 0  # <- set likewise from a captured CPMM pool


def _classify(frac: float, locker_owner: str | None) -> tuple[bool, str]:
    if locker_owner:
        return True, f"lp_locked:{LP_LOCKERS.get(locker_owner, 'locker')}"
    if frac >= SECURED_FRACTION_THRESHOLD:
        return True, "lp_mint_burned"
    return False, "withdrawable"


def verify_fungible(helius, pool: PoolRef, venue: str, lp_mint_offset: int) -> LpEvidence:
    """Resolve a fungible pool's LP mint on-chain, then prove burned/locked vs withdrawable."""
    acct = helius.get_account_info(pool.pool, encoding="base64")
    data = acct.get("data")
    data_b64 = data[0] if isinstance(data, list) and data else None
    if not data_b64:
        return LpEvidence(venue, pool.pool, None, "verify_failed", None,
                          "pool account had no decodable data", pool.liquidity_usd)
    lp_mint = _pubkey_at(data_b64, lp_mint_offset)
    supply = helius.get_token_supply(lp_mint)
    holders = largest_holders_with_owners(helius, lp_mint)
    frac = secured_fraction(holders, supply)
    locker_owner = next((h["owner"] for h in holders if h.get("owner") in LP_LOCKERS), None)
    secured, method = _classify(frac, locker_owner)
    note = " (lock duration unverified — Phase 1)" if method.startswith("lp_locked") else ""
    detail = (f"{venue} LP {'secured' if secured else 'withdrawable'}: "
              f"{frac:.0%} of supply burned/locked via {method}{note}.")
    return LpEvidence(venue, pool.pool, lp_mint, method, secured, detail, pool.liquidity_usd, citation=lp_mint)
```

- [ ] **Step 3b: Add the `base58` dependency**

`base58` decodes pubkeys with zero transitive weight. Add to `pyproject.toml` `dependencies`: `"base58>=2.1"`, then `.venv/bin/pip install -e .` (or `uv sync`). Confirm `import base58` works.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_lp.py -q` → Expected: passed (after the offset constant is set to the proven value). `.venv/bin/ruff check src/anamnesis/forensic/lp.py`.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/forensic/lp.py tests/test_lp.py pyproject.toml uv.lock
git commit -S -m "feat: Raydium V4/CPMM LP-mint decode + burn/lock verifier"
```

---

### Task 7: PumpSwap + Meteora DAMM v1 verifiers (offset-pinned)

**Files:**
- Modify: `src/anamnesis/forensic/lp.py`
- Test: `tests/test_lp.py`

**Interfaces:**
- Produces: `PUMPSWAP_LP_MINT_OFFSET`, `METEORA_DAMM_V1_LP_MINT_OFFSET` (int, pinned against fixtures). Both reuse `verify_fungible`.

> Same fixture-pinned method as Task 6. `Pool.lp_mint` lives in the PumpSwap Anchor IDL (`pump-fun/pump-public-docs` → `pump_amm.json`) and the Meteora DAMM v1 `Pool` struct (MeteoraAg dynamic-amm). Capture one real pool per venue, derive the offset from the IDL field order (8-byte discriminator + preceding fields), and pin with a decode-test against the known LP mint (read it from the pool's own IDL-parsed account via an explorer, or from the pool creation tx).

- [ ] **Step 1: Capture fixtures + failing decode tests**

For each venue, capture a real pool's base64 data (same `getAccountInfo` command as Task 6 Step 1) and its known LP mint, then:

```python
# append to tests/test_lp.py
from anamnesis.forensic.lp import _pubkey_at, PUMPSWAP_LP_MINT_OFFSET, METEORA_DAMM_V1_LP_MINT_OFFSET

_PUMPSWAP_DATA_B64 = "<captured>"; _PUMPSWAP_KNOWN_LP_MINT = "<known>"
_METEORA_DATA_B64 = "<captured>"; _METEORA_KNOWN_LP_MINT = "<known>"


def test_decode_pumpswap_lp_mint():
    assert _pubkey_at(_PUMPSWAP_DATA_B64, PUMPSWAP_LP_MINT_OFFSET) == _PUMPSWAP_KNOWN_LP_MINT


def test_decode_meteora_damm_v1_lp_mint():
    assert _pubkey_at(_METEORA_DATA_B64, METEORA_DAMM_V1_LP_MINT_OFFSET) == _METEORA_KNOWN_LP_MINT
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/pytest tests/test_lp.py -q` → Expected: FAIL — offsets undefined.

- [ ] **Step 3: Pin the offsets**

```python
PUMPSWAP_LP_MINT_OFFSET = 0        # <- proven by test_decode_pumpswap_lp_mint (pump_amm.json Pool.lp_mint)
METEORA_DAMM_V1_LP_MINT_OFFSET = 0 # <- proven by test_decode_meteora_damm_v1_lp_mint (dynamic-amm Pool.lp_mint)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_lp.py -q` → Expected: passed. `.venv/bin/ruff check src/anamnesis/forensic/lp.py`.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/forensic/lp.py tests/test_lp.py
git commit -S -m "feat: PumpSwap + Meteora DAMM v1 LP-mint decode offsets"
```

---

### Task 8: pump.fun bonding-curve handler (offset-pinned)

**Files:**
- Modify: `src/anamnesis/forensic/lp.py`
- Test: `tests/test_lp.py`

**Interfaces:**
- Produces: `BONDING_CURVE_COMPLETE_OFFSET` (int, pinned); `verify_pumpfun_curve(helius, pool: PoolRef) -> LpEvidence`.

> A pre-graduation pump.fun token's DexScreener `pairAddress` is the bonding-curve account (verify in Step 1; if it is not, derive the PDA from seeds `["bonding-curve", mint]` under the pump.fun program). The `complete: bool` flag sits in the `BondingCurve` struct (`pump-fun/pump-public-docs` IDL). `complete == false` ⇒ `SECURED` (`bonding_curve_custody`); `complete == true` ⇒ the migrated PumpSwap/Raydium pool carries the verdict, so emit nothing here.

- [ ] **Step 1: Capture a pre-grad curve fixture + failing test**

```python
# append to tests/test_lp.py
from anamnesis.forensic.lp import verify_pumpfun_curve
from anamnesis.forensic.pools import PoolRef

_CURVE_DATA_B64_INCOMPLETE = "<captured base64 of a pre-grad bonding curve account>"


def test_pumpfun_pre_graduation_is_secured_by_custody():
    class _C:
        def get_account_info(self, addr, *, encoding="jsonParsed"):
            return {"data": [_CURVE_DATA_B64_INCOMPLETE, "base64"]}
    ev = verify_pumpfun_curve(_C(), PoolRef("CURVE", "pumpfun", 5_000.0))
    assert ev.secured is True and ev.method == "bonding_curve_custody"
```

- [ ] **Step 2: Run to verify fail** — `.venv/bin/pytest tests/test_lp.py -q` → FAIL.

- [ ] **Step 3: Implement**

```python
BONDING_CURVE_COMPLETE_OFFSET = 0  # <- byte index of the `complete` bool in BondingCurve (pin via fixture)


def verify_pumpfun_curve(helius, pool: PoolRef) -> LpEvidence:
    """Pre-graduation pump.fun: liquidity is curve-custodied (deployer cannot withdraw) => SECURED.
    Graduated curves return None-secured here; their migrated pool carries the verdict."""
    acct = helius.get_account_info(pool.pool, encoding="base64")
    data = acct.get("data")
    data_b64 = data[0] if isinstance(data, list) and data else None
    if not data_b64:
        return LpEvidence("pumpfun_curve", pool.pool, None, "verify_failed", None,
                          "bonding-curve account had no data", pool.liquidity_usd)
    raw = base64.b64decode(data_b64)
    complete = bool(raw[BONDING_CURVE_COMPLETE_OFFSET])
    if complete:
        return LpEvidence("pumpfun_curve", pool.pool, None, "bonding_curve_custody", None,
                          "pump.fun curve complete (graduated); migrated pool carries the verdict.",
                          pool.liquidity_usd)
    return LpEvidence("pumpfun_curve", pool.pool, None, "bonding_curve_custody", True,
                      "liquidity in pump.fun bonding curve; program-custodied, deployer cannot "
                      "withdraw (not burned/locked).", pool.liquidity_usd)
```

- [ ] **Step 4: Run to verify pass** — `.venv/bin/pytest tests/test_lp.py -q` → passed. `.venv/bin/ruff check`.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/forensic/lp.py tests/test_lp.py
git commit -S -m "feat: pump.fun bonding-curve custody handler (pre-grad => secured)"
```

---

### Task 9: `LpAnalyzer` orchestration + model migration (atomic)

**Files:**
- Modify: `src/anamnesis/forensic/lp.py` (add `LpAnalyzer`)
- Modify: `src/anamnesis/forensic/signals.py` (`TokenProfile.lp_secured`→`lp`; `assess_token_signals`)
- Modify: `src/anamnesis/forensic/helius.py` (`_lp_unanalyzed`, `LpResolver`, `build_token_profile`)
- Modify: `tests/test_signals.py`, `tests/test_assess.py`, `tests/test_helius.py`, `tests/test_agent_tools.py`
- Test: `tests/test_lp.py`

**Interfaces:**
- Consumes: `discover_pools`, `verify_fungible`, `verify_pumpfun_curve`, `venue_of`, `aggregate`, the offset constants.
- Produces: `LpAnalyzer(dex)` with `.assess(helius, mint) -> LpAssessment`; `helius._lp_unanalyzed(client, mint) -> LpAssessment`; `LpResolver = Callable[[HeliusClient, str], LpAssessment]`.

- [ ] **Step 1: Write failing analyzer test**

```python
# append to tests/test_lp.py
from anamnesis.forensic.lp import LpAnalyzer
from anamnesis.forensic.signals import LpStatus


def test_analyzer_routes_and_aggregates():
    pairs = [{"pairAddress": "POOL", "dexId": "raydium", "liquidity": {"usd": 50_000.0}}]

    class _Dex:
        def token_pairs(self, mint): return pairs

    ray_v4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

    class _Helius:
        def get_account_info(self, addr, *, encoding="jsonParsed"):
            if addr == "POOL" and encoding == "jsonParsed":
                return {"owner": ray_v4}
            if addr == "POOL":  # base64 data fetch
                return {"data": [_RAY_V4_DATA_B64, "base64"]}
            return {"data": {"parsed": {"info": {"owner": INCINERATOR}}}}
        def get_token_supply(self, mint): return 1000
        def get_token_largest_accounts(self, mint): return [{"address": "TA", "amount": "1000"}]

    a = LpAnalyzer(_Dex())
    out = a.assess(_Helius(), "mintA")
    assert out.status is LpStatus.SECURED
    assert out.evidence and out.evidence[0].venue == "raydium_v4"


def test_analyzer_discovery_failure_is_unknown():
    class _Dex:
        def token_pairs(self, mint):
            from anamnesis.forensic.pools import AggregatorError
            raise AggregatorError("down")
    out = LpAnalyzer(_Dex()).assess(object(), "mintA")
    assert out.status is LpStatus.UNKNOWN and out.evidence[0].method == "discovery_failed"
```

- [ ] **Step 2: Run to verify fail** — FAIL (`LpAnalyzer` undefined).

- [ ] **Step 3a: Implement `LpAnalyzer` in `lp.py`**

```python
import httpx

from .helius import HeliusError
from .pools import AggregatorError, DexScreenerClient, PoolRef, discover_pools

_VERIFY_DEGRADE_ON = (HeliusError, httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, IndexError)
_VENUE_OFFSETS = {
    "raydium_v4": RAYDIUM_V4_LP_MINT_OFFSET,
    "raydium_cpmm": RAYDIUM_CPMM_LP_MINT_OFFSET,
    "meteora_damm_v1": METEORA_DAMM_V1_LP_MINT_OFFSET,
    "pumpswap": PUMPSWAP_LP_MINT_OFFSET,
}


class LpAnalyzer:
    """Discover a mint's pools and prove per-pool securedness on-chain into an LpAssessment."""

    def __init__(self, dex: DexScreenerClient) -> None:
        self._dex = dex

    def assess(self, helius, mint: str) -> LpAssessment:
        try:
            pools = discover_pools(self._dex, mint)
        except AggregatorError as e:
            return LpAssessment(LpStatus.UNKNOWN, [LpEvidence(
                "unknown", "", None, "discovery_failed", None, f"pool discovery failed: {e}")])
        evidence = [self._verify(helius, mint, p) for p in pools]
        return LpAssessment(aggregate(evidence), evidence)

    def _verify(self, helius, mint: str, pool: PoolRef) -> LpEvidence:
        try:
            venue = venue_of(helius, pool.pool)
            if venue in FUNGIBLE_LP_VENUES:
                return verify_fungible(helius, pool, venue, _VENUE_OFFSETS[venue])
            if venue == "pumpfun_curve":
                return verify_pumpfun_curve(helius, pool)
            return LpEvidence(venue, pool.pool, None, "position_nft_unverified", None,
                              "position-NFT or unrecognised venue; LP burn/lock not applicable (Phase 2).",
                              pool.liquidity_usd)
        except _VERIFY_DEGRADE_ON as e:
            return LpEvidence("unknown", pool.pool, None, "verify_failed", None,
                              f"pool verification failed: {e}", pool.liquidity_usd)
```

- [ ] **Step 3b: Migrate `signals.py`**

Replace `lp_secured: bool  # liquidity burned or locked` in `TokenProfile` with `lp: LpAssessment`. Replace the `if not p.lp_secured:` block in `assess_token_signals` with:

```python
    if p.lp.status == LpStatus.NOT_SECURED:
        out.append(Signal("LP_NOT_SECURED", "high", _rug_vector_detail(p.lp.evidence)))
    elif p.lp.status == LpStatus.UNKNOWN:
        out.append(Signal("LP_UNVERIFIED", "low",
                          "Liquidity securedness could not be verified across the mint's pools."))
```

Add the helper above `assess_token_signals`:

```python
def _rug_vector_detail(evidence: list[LpEvidence]) -> str:
    unsecured = [e for e in evidence if e.secured is False]
    if not unsecured:
        return "Liquidity is neither burned nor locked; deployer can pull liquidity."
    worst = max(unsecured, key=lambda e: e.liquidity_usd or 0.0)
    usd = f"~${worst.liquidity_usd:,.0f}" if worst.liquidity_usd else "unknown size"
    return (f"Liquidity withdrawable on {worst.venue} pool {worst.pool} ({usd}); "
            "deployer can pull liquidity.")
```

- [ ] **Step 3c: Migrate `helius.py`**

Replace `_lp_unverified` and `LpResolver`:

```python
from .signals import LpAssessment, LpStatus, TokenProfile  # extend the existing import

LpResolver = Callable[[HeliusClient, str], LpAssessment]


def _lp_unanalyzed(client: HeliusClient, mint: str) -> LpAssessment:
    """Default resolver: liquidity not analyzed -> honest UNKNOWN (never a false 'not secured')."""
    return LpAssessment(LpStatus.UNKNOWN, [])
```

In `build_token_profile`, change the default to `lp_resolver: LpResolver = _lp_unanalyzed` and set `lp=lp_resolver(client, mint)` (replacing `lp_secured=lp_resolver(client, mint)`). Update its docstring line about the default.

- [ ] **Step 3d: Migrate the existing tests**

- `tests/test_signals.py`: `import` add `LpStatus, LpAssessment`; replace every `lp_secured=True` with `lp=LpAssessment(LpStatus.SECURED)` and `lp_secured=False` with `lp=LpAssessment(LpStatus.NOT_SECURED, [LpEvidence("raydium_v4","P","L","withdrawable",False,"d",50_000.0)])`. Keep the `LP_NOT_SECURED` assertion in `test_active_authorities_and_unsecured_lp_flag_high`.
- `tests/test_assess.py`: in `_profile`, `lp_secured=True`→`lp=LpAssessment(LpStatus.SECURED)`; in `test_live_high_signals...`, `lp_secured=False`→`lp=LpAssessment(LpStatus.NOT_SECURED, [LpEvidence("raydium_v4","P","L","withdrawable",False,"d",50_000.0)])`.
- `tests/test_helius.py`: `test_build_token_profile_assembles_all_fields` → `assert profile.lp.status is LpStatus.UNKNOWN` (the honest default). `test_build_token_profile_uses_injected_lp_resolver` → `lp_resolver=lambda c, m: LpAssessment(LpStatus.SECURED)`; `assert profile.lp.status is LpStatus.SECURED`. Add the imports.
- `tests/test_agent_tools.py`: both `lp_secured=True` → `lp=LpAssessment(LpStatus.SECURED)`; add imports.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -q` and `.venv/bin/pytest -q --store=mongo`
Expected: all green (the new analyzer tests + migrated call sites). `.venv/bin/ruff check .`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -S -m "feat: LpAnalyzer orchestration + migrate TokenProfile.lp_secured -> lp (tri-state)"
```

---

### Task 10: MCP surface + entrypoint wiring

**Files:**
- Modify: `src/anamnesis/forensic/mcp_tools.py` (`token_profile_dict` surfaces `lp`; accepts injectable resolver)
- Modify: `mcp/solana_forensics_mcp.py` (own a `DexScreenerClient`; inject the real `LpAnalyzer`; close on shutdown)
- Modify: `tests/test_mcp_tools.py`

**Interfaces:**
- Consumes: `_lp_unanalyzed`, `LpAnalyzer`, `DexScreenerClient`.
- Produces: `token_profile_dict(client, mint, *, lp_resolver=_lp_unanalyzed)` returning a dict whose `lp` key is `{status, evidence:[...]}`.

- [ ] **Step 1: Write failing test**

```python
# tests/test_mcp_tools.py — update test_token_profile_dict_serializes_all_fields
from anamnesis.forensic.signals import LpAssessment, LpStatus, LpEvidence


def test_token_profile_dict_serializes_lp_assessment():
    resolver = lambda c, m: LpAssessment(LpStatus.SECURED, [
        LpEvidence("raydium_v4", "POOL", "LPMINT", "lp_mint_burned", True, "burned", 50_000.0, "LPMINT")])
    out = token_profile_dict(_FakeClient(), "mintA", lp_resolver=resolver)
    assert out["mint"] == "mintA"
    assert out["lp"]["status"] == "secured"
    assert out["lp"]["evidence"][0] == {
        "venue": "raydium_v4", "pool": "POOL", "lp_mint": "LPMINT", "method": "lp_mint_burned",
        "secured": True, "detail": "burned", "liquidity_usd": 50_000.0, "citation": "LPMINT"}
    assert "lp_secured" not in out
```

- [ ] **Step 2: Run to verify fail** — FAIL (`lp_resolver` kwarg / `lp` key absent).

- [ ] **Step 3a: Update `mcp_tools.py`**

Import `_lp_unanalyzed` from `.helius`. Change the handler:

```python
@_forensic_read
def token_profile_dict(client: HeliusClient, mint: str, *, lp_resolver=_lp_unanalyzed) -> dict:
    """Full forensic profile for a mint (authorities, liquidity, holders, deployer, created_at)."""
    p = build_token_profile(client, mint, lp_resolver=lp_resolver)
    return {
        "mint": p.mint,
        "deployer": p.deployer,
        "created_at": p.created_at,
        "mint_authority": p.mint_authority,
        "freeze_authority": p.freeze_authority,
        "lp": {
            "status": p.lp.status.value,
            "evidence": [
                {"venue": e.venue, "pool": e.pool, "lp_mint": e.lp_mint, "method": e.method,
                 "secured": e.secured, "detail": e.detail, "liquidity_usd": e.liquidity_usd,
                 "citation": e.citation}
                for e in p.lp.evidence
            ],
        },
        "top_holder_pct": p.top_holder_pct,
        "holder_count": p.holder_count,
    }
```

- [ ] **Step 3b: Wire the real analyzer in the entrypoint**

In `mcp/solana_forensics_mcp.py` add a DexScreener singleton + analyzer and inject it, closing both clients on shutdown:

```python
from anamnesis.forensic.lp import LpAnalyzer
from anamnesis.forensic.pools import DexScreenerClient

_dex: DexScreenerClient | None = None


def _dexscreener() -> DexScreenerClient:
    global _dex
    if _dex is None:
        _dex = DexScreenerClient()
    return _dex


# get_token_profile injects the real analyzer (DexScreener discovery + on-chain verification):
@server.tool()
def get_token_profile(mint: str) -> dict:
    """Full forensic profile for a token mint: authorities (null == renounced), liquidity
    (per-pool LP burn/lock evidence), holder concentration, deployer, and creation time."""
    return token_profile_dict(_helius(), mint, lp_resolver=LpAnalyzer(_dexscreener()).assess)
```

Update `main()` to close the DexScreener client too:

```python
def main() -> None:
    with _helius():
        try:
            server.run()
        finally:
            _dexscreener().close()
```

- [ ] **Step 4: Run suite** — `.venv/bin/pytest -q` → green. `.venv/bin/ruff check .`. Sanity-import the entrypoint: `.venv/bin/python -c "import importlib.util,sys; sys.argv=['x']; spec=importlib.util.spec_from_file_location('m','mcp/solana_forensics_mcp.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); print('ok')"` (no key needed for import).

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/forensic/mcp_tools.py mcp/solana_forensics_mcp.py tests/test_mcp_tools.py
git commit -S -m "feat: surface LP assessment in MCP profile + wire LpAnalyzer into entrypoint"
```

---

### Task 11: Live validation (key-gated smoke)

**Files:**
- Create: `scripts/lp_smoke.py` (manual, not a CI test)

**Interfaces:** Consumes the full stack against mainnet; prints per-pool evidence; never prints the key.

- [ ] **Step 1: Write the smoke script**

```python
"""Manual live validation of LP-secured detection (key-gated). NEVER prints the Helius key.

Usage:
  line=$(grep -E '^(export )?ANAMNESIS_HELIUS_API_KEY=' ~/Documents/secret/.env | tail -1)
  export ANAMNESIS_HELIUS_API_KEY="${line#*=}"
  .venv/bin/python scripts/lp_smoke.py <mint> [<mint> ...]
"""
import sys

from anamnesis import config
from anamnesis.forensic.helius import HeliusClient
from anamnesis.forensic.lp import LpAnalyzer
from anamnesis.forensic.pools import DexScreenerClient


def main(mints: list[str]) -> None:
    key = config.require("ANAMNESIS_HELIUS_API_KEY")
    with HeliusClient(key) as helius, DexScreenerClient() as dex:
        analyzer = LpAnalyzer(dex)
        for mint in mints:
            a = analyzer.assess(helius, mint)
            print(f"\n{mint} -> {a.status.value}")
            for e in a.evidence:
                usd = f"${e.liquidity_usd:,.0f}" if e.liquidity_usd else "n/a"
                print(f"  [{e.venue}] {e.method} secured={e.secured} liq={usd} :: {e.detail}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: lp_smoke.py <mint> [<mint> ...]")
    main(sys.argv[1:])
```

- [ ] **Step 2: Run against representative mints**

Export the key (recipe above), then run against: a known LP-burned token (expect `secured`), a pre-graduation pump.fun mint (expect `secured`/`bonding_curve_custody`), a known rug/withdrawable token (expect `not_secured` naming the rug-vector pool), and a Raydium-CLMM-only token (expect `unknown`/`position_nft_unverified`). Confirm the key never appears in output.

- [ ] **Step 3: Record results + commit the script**

```bash
git add scripts/lp_smoke.py
git commit -S -m "test: key-gated live-validation smoke for LP-secured detection"
```

---

## Self-Review

**Spec coverage:**
- D1 hybrid discovery → Tasks 4 (DexScreener) + 5–8 (on-chain verify). ✓
- D2 Phase-1 venues → Tasks 6 (Raydium V4/CPMM), 7 (PumpSwap/Meteora), 8 (pump.fun curve); position-NFT → `position_nft_unverified` in Task 9 `_verify`. ✓
- D3 model → Task 1; migration → Task 9. ✓
- D4 precedence + dust → Task 3; constants in Global Constraints. ✓
- D5 pre-grad curve = SECURED → Task 8. ✓
- D6 burned (incinerator + supply) + lock allowlist → Tasks 2, 6; unlock-ts deferral documented as Phase-1 limitation. ✓
- D7 module layout/no-cycle → File Structure + Tasks 1/2/4/9 imports. ✓
- D8 signals → Task 9 (`LP_NOT_SECURED` high, `LP_UNVERIFIED` low). ✓
- Error handling → Task 4 (`AggregatorError`), Task 9 (`_verify` degrade + discovery_failed). ✓
- Testing → pure tests Tasks 1–3, fixture decode Tasks 6–8, live Task 11, migration Task 9. ✓

**Placeholder scan:** the only deferred literals are the byte-offset constants (Tasks 6–8), which are *fixture-pinned* via their decode-tests — a TDD reverse-engineering step with a concrete capture command and a known-value assert, not vague hand-waving. All other steps carry complete code.

**Type consistency:** `LpAssessment(status, evidence)`, `LpEvidence(venue, pool, lp_mint, method, secured, detail, liquidity_usd, citation)`, `PoolRef(pool, dex_id, liquidity_usd)`, `LpResolver = Callable[[HeliusClient, str], LpAssessment]`, `LpAnalyzer(dex).assess(helius, mint)` are used identically across Tasks 1–11. `secured_fraction(holders, supply)` and `aggregate(evidence, *, dust_usd)` signatures match their call sites.

**Open implementation risks (flag at execution):** (1) the four LP-mint offsets + the bonding-curve `complete` offset must pin against live fixtures — if any layout has changed, the decode-test catches it. (2) Whether DexScreener's pre-grad pump.fun `pairAddress` equals the bonding-curve account is verified in Task 8 Step 1; the PDA-derivation fallback is noted there.
