# LP-secured detection — multi-AMM, hybrid discovery + on-chain verification (design)

- **Date:** 2026-06-25
- **Status:** Approved — ready for implementation plan
- **Task:** Forensic polish — replace the `_lp_unverified` always-`False` default with real LP burn/lock detection (SPEC A.5 carry-over: "`lp_secured` still conservative default")
- **Scope decision:** General multi-AMM (Scope C), delivered **incrementally**. **This spec = Phase 1 (fungible-LP venues).** Phase 2 (position-NFT venues) is a separate spec.
- **Depends on:** `forensic/helius.py` (A.5 — `HeliusClient`, `build_token_profile`, the `lp_resolver` injection seam), `forensic/signals.py` (A.1 — `TokenProfile`, `assess_token_signals`), `forensic/mcp_tools.py` (A.8 — profile dict surface)
- **New runtime dependency:** DexScreener public HTTP API (**keyless** — no new access gate, unlike Qwen/ApsaraDB)

## Goal

Today `forensic/helius.py::_lp_unverified` hard-returns `False`, so `TokenProfile.lp_secured` is `False` for **every** token. The `LP_NOT_SECURED` **high**-severity signal therefore fires unconditionally — it has zero discriminating power and inflates every verdict. The field cannot tell "proven ruggable" from "couldn't determine."

Replace it with grounded, multi-venue LP-securedness detection: for a mint, discover its pools, and for each prove on-chain whether its liquidity is **burned**, **locked**, or **withdrawable** — so the signal finally discriminates. Liquidity-rug-via-LP-removal is one of the highest-frequency Solana rug vectors; this is core verdict quality, not cosmetic polish.

**Forensic honesty is the through-line:** "unknown" must never masquerade as "secured" (false safety) *or* as "not secured" (false alarm). The model carries per-pool evidence so every verdict shows its work — consistent with the `FUNDING_SOURCES` cite-or-omit discipline.

## Decisions

### D1 — Hybrid discovery: aggregator enumerates, Helius verifies

Helius has no mint→pools endpoint. A keyless aggregator (**DexScreener**, Phase 1) enumerates the pools for a mint (pool address + venue + USD liquidity); then **Helius on-chain reads are the source of truth** for securedness. The aggregator only *points* at pools — it never supplies the verdict. We deliberately do **not** trust any aggregator-computed "liquidity locked" flag: a forensic tool proves it on-chain.

Confirmed by research (2026-06-25): neither DexScreener nor GeckoTerminal returns the **LP mint** — only the pool/pair address and `dexId`. Resolving pool→LP-mint on-chain (or via Raydium's own API for Raydium pools) is therefore the one hard dependency on the Helius layer.

### D2 — Phase 1 = fungible-LP venues only

Only ~half of Solana AMM venues mint a **fungible LP token** where "burned/locked LP" is even meaningful. Phase 1 ships the four that do, plus the pump.fun bonding-curve case; the rest report `unknown` until Phase 2.

| Venue | Program ID | Fungible LP mint? | Phase |
|---|---|---|---|
| Raydium AMM v4 | `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` | **yes** | **1** |
| Raydium CPMM (CP-Swap) | `CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C` | **yes** | **1** |
| Meteora DAMM v1 (Dynamic AMM) | `Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB` | **yes** | **1** |
| PumpSwap (post-graduation AMM) | `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA` | **yes** (Token-2022) | **1** |
| pump.fun bonding curve | `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` | no (no LP) | **1** (curve handler) |
| Raydium CLMM | `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` | no (position NFT) | 2 |
| Orca Whirlpools | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` | no (position NFT) | 2 |
| Meteora DLMM | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | no (bin positions) | 2 |
| Meteora DAMM v2 (cp-amm) | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | no (position NFT) | 2 |

Position-NFT venues are a *category change* (no LP mint to inspect; securedness = per-position NFT custody/lock), so they earn their own spec rather than being half-built here.

### D3 — Tri-state model + per-pool evidence

`TokenProfile.lp_secured: bool` → `TokenProfile.lp: LpAssessment`.

```python
class LpStatus(str, Enum):
    SECURED = "secured"
    NOT_SECURED = "not_secured"
    UNKNOWN = "unknown"

@dataclass
class LpEvidence:
    venue: str            # "raydium_v4" | "raydium_cpmm" | "meteora_damm_v1" | "pumpswap" | "pumpfun_curve" | ...
    pool: str             # pool / pair address
    lp_mint: str | None   # resolved LP mint (None for bonding curve / unresolved)
    method: str           # see method vocabulary below
    secured: bool | None  # True | False | None(=unknown for this pool)
    detail: str           # human-readable, cite-bearing
    liquidity_usd: float | None
    citation: str | None  # tx / account / program id backing the claim

@dataclass
class LpAssessment:
    status: LpStatus
    evidence: list[LpEvidence]
```

`method` vocabulary: `lp_mint_burned` · `lp_locked:<locker>` · `bonding_curve_custody` · `withdrawable` · `position_nft_unverified` · `discovery_failed` · `verify_failed`.

A bare bool cannot express "unknown", "mixed pools", or "show your work". This is the intended, larger blast radius (touches `TokenProfile`, `signals.py`, `mcp_tools.py`, and their tests) — it is the feature.

### D4 — Aggregation is conservative precedence, not a vote

A mint commonly has several pools with **mixed** securedness; collapsing them by majority would let a deep unsecured pool hide behind shallow secured ones. Precedence:

> **`NOT_SECURED` ⊳ `UNKNOWN` ⊳ `SECURED`**

- **any** non-dust pool with withdrawable LP **and** real liquidity → `NOT_SECURED`; the assessment surfaces *that pool* (largest-liquidity unsecured = the rug vector) in its `detail`.
- else any meaningful liquidity we could not verify (Phase-2 venue, read failure, or only dust pools) → `UNKNOWN`.
- only when **all** non-dust liquidity is proven burned/locked/curve-custodied → `SECURED`.

Tunable constants (seeded; adjustable at review): `SECURED_FRACTION_THRESHOLD = 0.95` (≥95 % of an LP mint's supply burned+locked to call that pool secured — attackers leave a sliver to retain a withdrawal path) and `DUST_LIQUIDITY_USD = 1_000` (pools below this are recorded in evidence but do not drive the verdict, defeating the dust "100 %-burned" decoy).

### D5 — pump.fun pre-graduation bonding curve ⇒ `SECURED`

A token still on the pump.fun bonding curve (`BondingCurve.complete == false`) has **no LP to pull** — liquidity is immutable program logic the deployer cannot withdraw. For the rug-via-LP-removal question this is effectively secured: `SECURED`, `method=bonding_curve_custody`, with a `detail` stating the liquidity is curve-custodied, not burned/locked. (Other pump.fun risks — deployer token dumps, sniping — remain the job of other signals; this signal answers only LP removability.) On graduation (`complete == true`) the token has migrated and is assessed via its PumpSwap/Raydium pool's LP burn instead.

### D6 — "Burned" is two distinct on-chain signatures; "locked" is cite-or-omit

**Burned** LP presents either as (a) the LP mint **supply decremented** toward 0 (a real SPL `Burn`) or (b) the LP tokens **sitting in the incinerator** `1nc1nerator11111111111111111111111111111111` (supply unchanged). Both are checked. Per-pool `secured_fraction = (incinerator-held + locker-held) / current_supply`; a `supply == 0` with live pool reserves is treated as fully burned (disambiguated against reserves so a defunct never-seeded pool is not mislabelled "secured").

**Locked** LP = the dominant LP holder is an account **owned by** a curated, *citeable* locker program (mirrors `FUNDING_SOURCES`). Seeded with confirmed Solana **mainnet** program IDs only:

```python
LP_LOCKERS: dict[str, str] = {
    "LocpQgucEQHbqNABEYvBvwoxCPsSbG91A1QaQhQQqjn": "jupiter_lock",   # lock.jup.ag (audited)
    "strmRqUCoQUgGUan5YhzUZa6KqdzwX5L6FpUxfmKg5m": "streamflow",
    "LockrWmn6K5twhz3y9w1dQERbmgSaRkfnTeTKbpofwE": "raydium_lock",   # Burn & Earn (CPMM + CLMM)
    "GsSCS3vPWrtJ5Y9aEVVT65fmrex5P5RGHXdZvsdbWgfo": "uncx",          # AMM v4 locker
    "UNCX77nZrA3TdAxMEggqG18xxpgiNGT6iqyynPwpoxN": "uncx",           # AMM v4 "smart"
    "UNCXdvMRxvz91g3HqFmpZ5NgmL77UH4QRM4NfeL4mQB": "uncx",           # CP-Swap
    "UNCXrB8cZXnmtYM1aSo1Wx3pQaeSZYuF2jCTesXvECs": "uncx",           # CLMM
}
INCINERATOR = "1nc1nerator11111111111111111111111111111111"
```

Unconfirmed lockers (Team Finance Solana, Smithii, PinkLock, …) are **omitted** until a program ID is resolved from an on-chain lock tx — never guessed. For time-bounded lockers (Jupiter Lock, Streamflow), read the escrow's unlock timestamp: a future/perpetual lock counts as locked; an **already-elapsed** lock does **not** (it is withdrawable again).

### D7 — Module layout (no import cycle; pure model stays CI-safe)

- **`forensic/signals.py`** — gains `LpStatus`, `LpEvidence`, `LpAssessment` (pure model, no I/O); `TokenProfile.lp_secured: bool` → `lp: LpAssessment`; `assess_token_signals` reads `p.lp.status`. Imports nothing from `helius`/`lp`/`pools` → stays network-free and CI-runnable.
- **`forensic/pools.py`** (new) — `DexScreenerClient` (keyless `httpx`, context-manager + timeout + `AggregatorError`, mirrors `HeliusClient`), `PoolRef`, `discover_pools(client, mint) -> list[PoolRef]`. A `Venue` mapping turns DexScreener `dexId` into our enum and drops unknown venues to a passthrough label. The discovery interface leaves a seam for a GeckoTerminal fallback later (not built in Phase 1).
- **`forensic/lp.py`** (new) — per-venue verifiers, `LpAnalyzer.assess(helius, mint) -> LpAssessment` (orchestration + D4 aggregation), and the curated constants (`INCINERATOR`, `LP_LOCKERS`, thresholds). Imports the model from `signals`, `HeliusClient` from `helius`, discovery from `pools`.
- **`forensic/helius.py`** — `build_token_profile`'s `lp_resolver` seam **stays**; its type evolves to `Callable[[HeliusClient, str], LpAssessment]`. The default `_lp_unverified` is replaced by `_lp_unanalyzed`, returning `LpAssessment(LpStatus.UNKNOWN, [])` — honest "not analyzed" instead of false-`False`. The real `LpAnalyzer` is injected by the caller (agent assembly / MCP), so `helius.py` never imports `lp.py`. Dependency graph: `helius → signals`, `pools → (httpx)`, `lp → {signals, helius, pools}` — acyclic.

### D8 — Signals: honesty over noise

- `lp.status == NOT_SECURED` → existing **`LP_NOT_SECURED` (high)**, `detail` citing the rug-vector pool.
- `lp.status == UNKNOWN` → new **`LP_UNVERIFIED` (low)** — transparent, and *never* escalates the verdict (A.4 composes on medium+ only).
- `lp.status == SECURED` → no signal.

## Components & data flow

```
LpAnalyzer.assess(helius, mint) -> LpAssessment:
  pools = discover_pools(dexscreener, mint)            # [PoolRef(venue, pool, dex_id, liquidity_usd)]
  evidence = []
  for p in pools:
    match p.venue:
      raydium_v4 | raydium_cpmm | meteora_damm_v1 | pumpswap:   # fungible-LP
        lp_mint = resolve_lp_mint(helius, p)                    # pool-account lp_mint (raw+offset) / Raydium API
        supply  = helius.get_token_supply(lp_mint)
        holders = helius.get_token_largest_accounts(lp_mint)
        frac    = secured_fraction(holders, supply, INCINERATOR, LP_LOCKERS)  # burned + (currently) locked
        secured = frac >= SECURED_FRACTION_THRESHOLD
        evidence.append(LpEvidence(..., secured, method=lp_mint_burned|lp_locked:..|withdrawable, citation=lp_mint))
      pumpfun_curve:
        complete = read_bonding_curve_complete(helius, mint)    # BondingCurve PDA(seeds=["bonding-curve", mint])
        if not complete: evidence.append(LpEvidence(..., secured=True, method=bonding_curve_custody))
        # complete == true -> the migrated pool (PumpSwap/Raydium) carries the verdict
      _ (phase-2 venue):
        evidence.append(LpEvidence(..., secured=None, method=position_nft_unverified))
  status = aggregate(evidence)                          # D4 precedence, dust-weighted by liquidity_usd
  return LpAssessment(status, evidence)

build_token_profile(client, mint, *, lp_resolver=_lp_unanalyzed):
  ...
  lp = lp_resolver(client, mint)                         # real: LpAnalyzer.assess ; tests: fake
  return TokenProfile(..., lp=lp)
```

`resolve_lp_mint` reads the pool account's `lp_mint` field — Raydium v4 `AmmInfo.lp_mint` / CPMM `PoolState.lp_mint` / Meteora DAMM v1 `Pool.lp_mint` / PumpSwap `Pool.lp_mint` (Token-2022). `jsonParsed` will not decode these custom layouts → raw `getAccountInfo` + per-venue byte offset (offsets pinned against captured fixtures in the plan), or Raydium API `lpMint` for Raydium pools. Owner-of-holder is resolved via `getAccountInfo` to classify incinerator vs locker vs withdrawable.

## Error handling (no silent failures)

- DexScreener unreachable / 429 / malformed → `AggregatorError`; analyzer degrades to `UNKNOWN` with a `discovery_failed` evidence note — never crash, never false-secure.
- Per-pool verification failure (RPC error, undecodable layout) → that pool's `secured=None`, `method=verify_failed`, error in `detail`; other pools still assessed.
- Unreadable lock unlock-ts → **conservatively not counted as locked** (don't over-claim secured).
- `supply == 0` disambiguated against pool reserves before declaring burned.
- Token-2022 LP mints (PumpSwap) queried under the Token-2022 program.
- All external calls timeout-bounded (DexScreener client mirrors `HeliusClient`'s 20 s default). The Helius key is never logged; any error string is scrubbed (existing discipline).

## Testing strategy

- **Pure** unit tests (CI-safe, no network) for `aggregate()` precedence (`NOT_SECURED ⊳ UNKNOWN ⊳ SECURED`), dust-weighting, rug-vector selection, and `secured_fraction` math (incinerator-held, supply-decrement burn, currently-vs-expired lock) — fed hand-built `LpEvidence`/holder fixtures. Mirrors `signals.py` purity.
- **Per-venue verifier** tests against **captured real** DexScreener + Helius JSON fixtures (one per Phase-1 venue) — deterministic, offline.
- **Live validation** (key-gated, like A.8b — `ANAMNESIS_HELIUS_API_KEY`): a known LP-burned mint (`SECURED`), a withdrawable/rug (`NOT_SECURED`), a pre-grad pump.fun (`SECURED`/curve), a CLMM (`UNKNOWN`). Never prints the key.
- **Migration** tests: every existing `lp_secured=...` call site (`test_assess`, `test_signals`, `test_helius`, `test_mcp_tools`, `test_agent_tools`) updated to the `lp=LpAssessment(...)` shape; the MCP profile surface asserts the evidence list is emitted.

## Out of scope (Phase 2 / future)

- Position-NFT venues (Raydium CLMM, Orca Whirlpools, Meteora DLMM, Meteora DAMM v2) — per-position NFT custody/lock; until then they report `UNKNOWN`.
- GeckoTerminal discovery fallback / cross-check (seam left in `pools.py`).
- Minting dedicated `Signal` codes beyond the two above (e.g. a distinct "LP partially secured").
- Tuning `SECURED_FRACTION_THRESHOLD` / `DUST_LIQUIDITY_USD` against a labelled corpus.

## Gotchas captured from grounding research (for the implementer)

- **Never trust cached pool LP fields** for the burn verdict — PumpSwap `Pool.lp_supply` excludes burns *by design*; Raydium SDK `lpReserve` is SDK-only; CPMM `lp_supply` can lag. Always read the **live mint** supply + largest holders.
- **CPMM baseline lock**: Raydium CPMM withholds a `lock_lp_amount` at init, so a small locked fraction exists on *every* CPMM pool — do not misread it as a deliberate creator lock.
- **LP held by AMM authority vs deployer**: resolve the *owner* of the largest LP holder before concluding "deployer can pull."
- **Venue-slug drift**: GeckoTerminal emits hyphenated slugs (`raydium-clmm`); DexScreener `dexId` is bare — normalize when the fallback lands.
- **Token-2022**: PumpSwap LP mints (and some Orca positions) are Token-2022 — wrong-program assumptions silently miss them.
- **Devnet locker IDs** (Raydium `DRay…`, various `Anchor.toml` aliases) must **not** fire — only the mainnet IDs above.

## References (grounding, 2026-06-25)

- DexScreener API: `https://docs.dexscreener.com/api/reference` (`GET /token-pairs/v1/solana/{mint}`, keyless)
- Raydium API v3: `https://api-v3.raydium.io/pools/info/mint` (`lpMint` present on Standard pools, absent on Concentrated)
- Raydium program source (`raydium-io/raydium-amm`, `raydium-cp-swap`) — `lp_mint` field; Burn & Earn locker docs
- Jupiter Lock (`jup-ag/jup-lock`), Streamflow (`docs.streamflow.finance`), UNCX Solana lockers (`docs.uncx.network`)
- Solana burn address (`1nc1nerator…`) — Backpack Learn
- pump.fun graduation / PumpSwap migration LP burn — pump-fun public IDL, SolanaFloor/Chainstack writeups
