# A.8b — Funding-trace + Deployer-token-history Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the two forensic reads deferred from A.8 — `trace_funding` (1-hop funding-source classification) and `get_deployer_token_history` (bounded on-chain mint-creation scan) — as MCP tools, following the existing A.8 structure.

**Architecture:** Pure algorithms over an injected `HeliusClient` in `forensic/helius.py` → `@_forensic_read` dict handlers in `forensic/mcp_tools.py` → thin `@server.tool()` wrappers in `mcp/solana_forensics_mcp.py`. Both tools take a `mint` and re-resolve the deployer via the existing `resolve_origin`. Both return raw facts (no new `Signal` codes). Design: `docs/design/2026-06-25-a8b-funding-deployer-history-design.md`.

**Tech Stack:** Python 3.12, `httpx`, `mcp`/FastMCP, `pytest` + `respx`, `ruff`.

## Global Constraints

- **No `from __future__ import annotations` in `mcp/solana_forensics_mcp.py`** (FastMCP reads raw `inspect.signature` annotations; stringized ones break tool registration). `helius.py` and `mcp_tools.py` keep their existing `from __future__ import annotations`.
- **CI installs neither `qwen_agent` nor `mcp`.** Tests in `test_helius.py` / `test_mcp_tools.py` are pure-over-client and run in CI (no guard). `test_mcp_server_registration.py` keeps its module-level `pytest.importorskip("mcp")`.
- **Tools take `mint`** and re-resolve the deployer internally (uniform agent-facing contract; reuses `@_forensic_read`'s mint validation).
- **`FUNDING_SOURCES` is cite-or-omit:** only addresses attributable to a named entity on a public label source ship; everything else classifies as `"unknown"`. Never guess an address.
- **Helius key is never printed/logged**; live smoke scrubs `api-key=` from any output.
- **Raw reads, no new `Signal` codes** (signals integration is out of scope).
- TDD: red → green → `ruff` → commit. GPG-signed commits (`git commit -S`, key `BF47B9DC1FA320FA`) authored as RECTOR; **zero AI attribution**. Verify like CI before push: `.venv/bin/ruff check .` · `.venv/bin/pytest -q` · `.venv/bin/pytest -q --store=mongo`. One branch (`feat/a8b-funding-deployer-history`, already created), one PR.

## File Structure

- `src/anamnesis/forensic/helius.py` — add `FUNDING_SOURCES`, `classify_funder`, `funder_of`, `_all_instructions`, `created_mint_in_tx`, `created_mints`.
- `src/anamnesis/forensic/mcp_tools.py` — add `trace_funding_dict`, `deployer_token_history_dict` handlers.
- `mcp/solana_forensics_mcp.py` — add `trace_funding` + `get_deployer_token_history` `@server.tool()`s.
- `tests/test_helius.py` — unit tests for the new helius functions.
- `tests/test_mcp_tools.py` — unit tests for the two handlers; extend the blank-mint loop.
- `tests/test_mcp_server_registration.py` — assert the five-tool surface.
- `PLAN.md` / `SPEC.md` — toolset line reflects 5 tools.

---

### Task 1: Funding-source classification (`classify_funder`)

**Files:**
- Modify: `src/anamnesis/forensic/helius.py` (add after `LAUNCHPAD_AUTHORITIES`)
- Test: `tests/test_helius.py`

**Interfaces:**
- Produces: `FUNDING_SOURCES: dict[str, str]`; `classify_funder(address: str | None) -> str` → `"cex"|"bridge"|"mixer"|"unknown"`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_helius.py`; add `classify_funder` to the imports from `anamnesis.forensic.helius`)

```python
def test_classify_funder_categorizes_known_and_unknown(monkeypatch):
    monkeypatch.setattr(
        "anamnesis.forensic.helius.FUNDING_SOURCES",
        {"cexAddr": "cex", "bridgeAddr": "bridge", "mixerAddr": "mixer"},
    )
    assert classify_funder("cexAddr") == "cex"
    assert classify_funder("bridgeAddr") == "bridge"
    assert classify_funder("mixerAddr") == "mixer"
    assert classify_funder("randomAddr") == "unknown"
    assert classify_funder(None) == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_helius.py::test_classify_funder_categorizes_known_and_unknown -v`
Expected: FAIL — `ImportError` / `cannot import name 'classify_funder'`.

- [ ] **Step 3: Write minimal implementation** (in `helius.py`, after the `LAUNCHPAD_AUTHORITIES` block)

```python
# --- Funding-source classification (A.8b) ---------------------------------------------------
# Curated, categorized funding-source addresses (cite-or-omit). Each entry MUST resolve to the
# named entity on a public label source (e.g. solscan.io) before it is committed; an address we
# cannot attribute is omitted, so an unlabelled funder honestly classifies as "unknown" rather
# than guessed. Extend by appending entries.
FUNDING_SOURCES: dict[str, str] = {
    # "<verified-address>": "cex" | "bridge" | "mixer",  # <entity> — <source/citation>
}


def classify_funder(address: str | None) -> str:
    """Classify a funding-source ``address`` as ``"cex"``/``"bridge"``/``"mixer"`` via the curated
    ``FUNDING_SOURCES`` set, else ``"unknown"`` (also when the address is missing)."""
    if not address:
        return "unknown"
    return FUNDING_SOURCES.get(address, "unknown")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_helius.py::test_classify_funder_categorizes_known_and_unknown -v`
Expected: PASS.

- [ ] **Step 5: Curate verified addresses (cite-or-omit)**

Populate `FUNDING_SOURCES` with addresses **verified** against a public label source (solscan.io / an on-chain label provider), each commented with the entity name and citation. Omit any you cannot attribute. Target the common funders: major CEX hot wallets (`cex`), canonical bridge custody/program addresses (`bridge`), and any documented mixer/tumbler (`mixer`). If no source is available in this session, leave the set empty and surface it in the handoff — the tool is structurally complete and honestly returns `"unknown"` until populated. **Do not invent addresses.** (No code/test change; classify_funder tests use synthetic addresses.)

- [ ] **Step 6: Run ruff + commit**

```bash
.venv/bin/ruff check .
git add src/anamnesis/forensic/helius.py tests/test_helius.py
git commit -S -m "feat: A.8b classify_funder + curated funding-source set"
```

---

### Task 2: Deployer funder resolution (`funder_of`)

**Files:**
- Modify: `src/anamnesis/forensic/helius.py`
- Test: `tests/test_helius.py`

**Interfaces:**
- Consumes: `oldest_signature`, `get_transaction`, `fee_payer`, `creation_time` (existing).
- Produces: `funder_of(client: HeliusClient, deployer: str | None) -> tuple[str | None, str | None]` → `(funder, funded_at)`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_helius.py`; add `funder_of` to the imports)

```python
class _FunderClient:
    def __init__(self, sig, payer):
        self._sig, self._payer = sig, payer

    def oldest_signature(self, address, **_):
        return self._sig

    def get_transaction(self, signature):
        return {"blockTime": 1700000000,
                "transaction": {"message": {"accountKeys": [{"pubkey": self._payer}]}}}


def test_funder_of_returns_payer_of_earliest_tx():
    funder, funded_at = funder_of(_FunderClient("fundSig", "cexHot"), "deployerW")
    assert funder == "cexHot"
    assert funded_at == "2023-11-14T22:13:20+00:00"


def test_funder_of_none_when_self_paid_or_unresolved():
    assert funder_of(_FunderClient("sig", "deployerW"), "deployerW") == (None, None)
    assert funder_of(_FunderClient(None, "x"), "deployerW") == (None, None)
    assert funder_of(_FunderClient("sig", "x"), None) == (None, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_helius.py::test_funder_of_returns_payer_of_earliest_tx tests/test_helius.py::test_funder_of_none_when_self_paid_or_unresolved -v`
Expected: FAIL — `cannot import name 'funder_of'`.

- [ ] **Step 3: Write minimal implementation** (in `helius.py`, near `resolve_origin`)

```python
def funder_of(client: HeliusClient, deployer: str | None) -> tuple[str | None, str | None]:
    """Return ``(funder, funded_at)`` — the wallet that paid the deployer's earliest transaction.

    A fresh deploy wallet's first on-chain transaction is the transfer that seeded it, so that
    tx's fee payer is its funder. Returns ``(None, None)`` when the deployer is unknown, has no
    signatures, or its earliest tx was paid by the deployer itself (no identifiable inbound funder).
    """
    if not deployer:
        return None, None
    signature = client.oldest_signature(deployer)
    if not signature:
        return None, None
    tx = client.get_transaction(signature)
    payer = fee_payer(tx)
    if payer is None or payer == deployer:
        return None, None
    return payer, creation_time(tx)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_helius.py -k funder_of -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run ruff + commit**

```bash
.venv/bin/ruff check .
git add src/anamnesis/forensic/helius.py tests/test_helius.py
git commit -S -m "feat: A.8b funder_of — deployer's 1-hop funding wallet"
```

---

### Task 3: `trace_funding_dict` handler

**Files:**
- Modify: `src/anamnesis/forensic/mcp_tools.py`
- Test: `tests/test_mcp_tools.py`

**Interfaces:**
- Consumes: `resolve_origin`, `funder_of`, `classify_funder` (helius).
- Produces: `trace_funding_dict(client, mint) -> {"mint","deployer","funder","source_type","funded_at"}`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_mcp_tools.py`; import `trace_funding_dict`)

```python
class _FundingClient:
    # mint creation tx -> deployer "depl"; deployer's earliest tx -> funder "cexHot"
    def oldest_signature(self, address, **_):
        return {"mintA": "createSig", "depl": "fundSig"}.get(address)

    def get_transaction(self, signature):
        payer = {"createSig": "depl", "fundSig": "cexHot"}[signature]
        return {"blockTime": 1700000000,
                "transaction": {"message": {"accountKeys": [{"pubkey": payer}]}}}

    def get_asset(self, mint):  # resolve_origin fallback (unused once the sig resolves)
        return {"authorities": []}


def test_trace_funding_dict_classifies_known_funder(monkeypatch):
    monkeypatch.setattr("anamnesis.forensic.helius.FUNDING_SOURCES", {"cexHot": "cex"})
    out = trace_funding_dict(_FundingClient(), "mintA")
    assert out == {"mint": "mintA", "deployer": "depl", "funder": "cexHot",
                   "source_type": "cex", "funded_at": "2023-11-14T22:13:20+00:00"}


def test_trace_funding_dict_unknown_when_self_funded():
    out = trace_funding_dict(_FakeClient(), "mintA")
    assert out == {"mint": "mintA", "deployer": "deployerW", "funder": None,
                   "source_type": "unknown", "funded_at": None}


def test_trace_funding_dict_degrades_on_rpc_error():
    assert trace_funding_dict(_DeployerRpcErrorClient(), "mintA") == {
        "error": "getSignaturesForAddress failed: 429", "mint": "mintA"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_mcp_tools.py -k trace_funding -v`
Expected: FAIL — `cannot import name 'trace_funding_dict'`.

- [ ] **Step 3: Write minimal implementation** (in `mcp_tools.py`; extend the `from .helius import (...)` block with `classify_funder`, `funder_of`, `resolve_origin` — `resolve_origin` is already imported)

```python
@_forensic_read
def trace_funding_dict(client: HeliusClient, mint: str) -> dict:
    """The deployer's 1-hop funding source: the wallet that funded the deployer and its category
    (cex/bridge/mixer/unknown). funder is null when no inbound funder is identifiable."""
    deployer, _ = resolve_origin(client, mint)
    funder, funded_at = funder_of(client, deployer)
    return {
        "mint": mint,
        "deployer": deployer,
        "funder": funder,
        "source_type": classify_funder(funder),
        "funded_at": funded_at,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_mcp_tools.py -k trace_funding -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run ruff + commit**

```bash
.venv/bin/ruff check .
git add src/anamnesis/forensic/mcp_tools.py tests/test_mcp_tools.py
git commit -S -m "feat: A.8b trace_funding_dict handler"
```

---

### Task 4: Mint-creation detection + bounded scan (`created_mints`)

**Files:**
- Modify: `src/anamnesis/forensic/helius.py`
- Test: `tests/test_helius.py`

**Interfaces:**
- Consumes: `get_signatures_for_address`, `get_transaction`, `creation_time` (existing).
- Produces: `created_mint_in_tx(tx: dict) -> str | None`; `created_mints(client, deployer, *, max_sigs=1000, max_results=50) -> tuple[list[dict], bool]`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_helius.py`; import `created_mint_in_tx`, `created_mints`)

```python
def test_created_mint_in_tx_detects_top_level_and_inner():
    top = {"transaction": {"message": {"instructions": [
        {"parsed": {"type": "initializeMint", "info": {"mint": "mintTop"}}}]}}}
    assert created_mint_in_tx(top) == "mintTop"
    inner = {"transaction": {"message": {"instructions": []}},
             "meta": {"innerInstructions": [{"instructions": [
                 {"parsed": {"type": "initializeMint2", "info": {"mint": "mintInner"}}}]}]}}
    assert created_mint_in_tx(inner) == "mintInner"


def test_created_mint_in_tx_none_when_no_mint_init():
    tx = {"transaction": {"message": {"instructions": [
        {"parsed": {"type": "transfer", "info": {"lamports": 1}}}]}}}
    assert created_mint_in_tx(tx) is None
    assert created_mint_in_tx({}) is None


class _HistoryClient:
    def __init__(self, sigs, creating):
        self._sigs, self._creating = sigs, creating

    def get_signatures_for_address(self, address, *, before=None, limit=1000):
        return [] if before else [{"signature": s} for s in self._sigs]

    def get_transaction(self, signature):
        mint = self._creating.get(signature)
        ix = [{"parsed": {"type": "initializeMint", "info": {"mint": mint}}}] if mint else []
        return {"blockTime": 1700000000, "transaction": {"message": {"instructions": ix}}}


def test_created_mints_collects_creations_only():
    client = _HistoryClient(["s1", "s2", "s3"], {"s1": "mintA", "s3": "mintC"})
    mints, truncated = created_mints(client, "deployerW")
    assert [m["mint"] for m in mints] == ["mintA", "mintC"]
    assert truncated is False


def test_created_mints_truncates_on_result_cap():
    client = _HistoryClient(["s1", "s2", "s3"], {"s1": "m1", "s2": "m2", "s3": "m3"})
    mints, truncated = created_mints(client, "deployerW", max_results=2)
    assert [m["mint"] for m in mints] == ["m1", "m2"]
    assert truncated is True


def test_created_mints_truncates_on_signature_cap():
    client = _HistoryClient(["s1", "s2", "s3"], {"s3": "m3"})
    mints, truncated = created_mints(client, "deployerW", max_sigs=2)
    assert mints == []
    assert truncated is True


def test_created_mints_empty_for_unknown_deployer():
    assert created_mints(_HistoryClient([], {}), None) == ([], False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_helius.py -k "created_mint" -v`
Expected: FAIL — `cannot import name 'created_mint_in_tx'`.

- [ ] **Step 3: Write minimal implementation** (in `helius.py`, near `resolve_origin`)

```python
_MINT_INIT_TYPES = frozenset({"initializeMint", "initializeMint2"})


def _all_instructions(tx: dict) -> list[dict]:
    """Every parsed instruction in a jsonParsed tx — top-level plus inner (CPI) instructions."""
    message = ((tx or {}).get("transaction") or {}).get("message") or {}
    top = message.get("instructions") or []
    inner = [
        ix
        for group in (((tx or {}).get("meta") or {}).get("innerInstructions") or [])
        for ix in (group.get("instructions") or [])
    ]
    return [*top, *inner]


def created_mint_in_tx(tx: dict) -> str | None:
    """The mint address initialized in ``tx`` (top-level or inner CPI), else ``None``.

    Detects SPL Token and Token-2022 ``initializeMint``/``initializeMint2`` via the jsonParsed
    instruction ``type`` (the RPC emits it for both token programs), reading ``info.mint``.
    """
    for ix in _all_instructions(tx):
        parsed = ix.get("parsed") if isinstance(ix, dict) else None
        if isinstance(parsed, dict) and parsed.get("type") in _MINT_INIT_TYPES:
            mint = (parsed.get("info") or {}).get("mint")
            if mint:
                return mint
    return None


def created_mints(
    client: HeliusClient, deployer: str | None, *, max_sigs: int = 1000, max_results: int = 50
) -> tuple[list[dict], bool]:
    """Scan the deployer's signatures (newest first) for mint-creation txs.

    Returns ``([{"mint", "created_at"}, ...], truncated)``: the mints this wallet initialized,
    capped at ``max_results`` results and ``max_sigs`` signatures scanned. ``truncated`` is True
    only when the scan stopped on a cap (more history may exist), so a partial answer is never
    mistaken for a complete one. Bounded to avoid the unbounded pagination that hangs
    ``resolve_origin`` on high-activity wallets.
    """
    if not deployer:
        return [], False
    out: list[dict] = []
    before: str | None = None
    scanned = 0
    while scanned < max_sigs:
        page = client.get_signatures_for_address(deployer, before=before, limit=1000)
        if not page:
            return out, False  # exhausted the deployer's history
        for entry in page:
            if scanned >= max_sigs:
                return out, True  # signature budget spent; more history may exist
            scanned += 1
            sig = entry.get("signature")
            if not sig:
                continue
            tx = client.get_transaction(sig)
            mint = created_mint_in_tx(tx)
            if mint:
                out.append({"mint": mint, "created_at": creation_time(tx)})
                if len(out) >= max_results:
                    return out, True  # result budget spent
        if len(page) < 1000:
            return out, False  # short final page — history exhausted
        before = page[-1].get("signature")
        if not before:
            return out, False
    return out, True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_helius.py -k "created_mint" -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run ruff + commit**

```bash
.venv/bin/ruff check .
git add src/anamnesis/forensic/helius.py tests/test_helius.py
git commit -S -m "feat: A.8b created_mints — bounded deployer mint-creation scan"
```

---

### Task 5: `deployer_token_history_dict` handler

**Files:**
- Modify: `src/anamnesis/forensic/mcp_tools.py`
- Test: `tests/test_mcp_tools.py`

**Interfaces:**
- Consumes: `resolve_origin`, `created_mints` (helius).
- Produces: `deployer_token_history_dict(client, mint) -> {"mint","deployer","created_mints","count","truncated"}`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_mcp_tools.py`; import `deployer_token_history_dict`)

```python
class _DeployerHistoryClient(_FakeClient):
    # mint creation -> deployer "depl"; deployer history page -> one creating tx (h1)
    def oldest_signature(self, address, **_):
        return {"mintA": "createSig", "depl": "h1"}.get(address, "createSig")

    def get_signatures_for_address(self, address, *, before=None, limit=1000):
        return [] if before else [{"signature": "h1"}, {"signature": "h2"}]

    def get_transaction(self, signature):
        if signature == "createSig":
            return {"blockTime": 1700000000,
                    "transaction": {"message": {"accountKeys": [{"pubkey": "depl"}]}}}
        mint = {"h1": "childMintA"}.get(signature)
        ix = [{"parsed": {"type": "initializeMint", "info": {"mint": mint}}}] if mint else []
        return {"blockTime": 1700000000, "transaction": {"message": {"instructions": ix}}}


def test_deployer_token_history_dict_lists_created_mints():
    out = deployer_token_history_dict(_DeployerHistoryClient(), "mintA")
    assert out == {
        "mint": "mintA",
        "deployer": "depl",
        "created_mints": [{"mint": "childMintA", "created_at": "2023-11-14T22:13:20+00:00"}],
        "count": 1,
        "truncated": False,
    }


def test_deployer_token_history_dict_degrades_on_rpc_error():
    assert deployer_token_history_dict(_DeployerRpcErrorClient(), "mintA") == {
        "error": "getSignaturesForAddress failed: 429", "mint": "mintA"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_mcp_tools.py -k deployer_token_history -v`
Expected: FAIL — `cannot import name 'deployer_token_history_dict'`.

- [ ] **Step 3: Write minimal implementation** (in `mcp_tools.py`; add `created_mints` to the helius import)

```python
@_forensic_read
def deployer_token_history_dict(client: HeliusClient, mint: str) -> dict:
    """Other token mints the deployer has created (a live serial-deployer scan), with a
    ``truncated`` flag when the bounded scan stopped on a cap."""
    deployer, _ = resolve_origin(client, mint)
    mints, truncated = created_mints(client, deployer)
    return {
        "mint": mint,
        "deployer": deployer,
        "created_mints": mints,
        "count": len(mints),
        "truncated": truncated,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_mcp_tools.py -k deployer_token_history -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Extend the blank-mint boundary test** (in `tests/test_mcp_tools.py`, update `test_blank_mint_is_rejected_at_the_boundary` to cover the two new handlers)

```python
def test_blank_mint_is_rejected_at_the_boundary():
    handlers = (token_profile_dict, deployer_dict, holders_dict,
                trace_funding_dict, deployer_token_history_dict)
    for handler in handlers:
        out = handler(_FakeClient(), "   ")
        assert "error" in out and out["mint"] == "   "
    assert "error" in token_profile_dict(_FakeClient(), "")
```

- [ ] **Step 6: Run the file + ruff + commit**

```bash
.venv/bin/pytest tests/test_mcp_tools.py -q
.venv/bin/ruff check .
git add src/anamnesis/forensic/mcp_tools.py tests/test_mcp_tools.py
git commit -S -m "feat: A.8b deployer_token_history_dict handler"
```

---

### Task 6: Register both tools on the MCP server

**Files:**
- Modify: `mcp/solana_forensics_mcp.py`
- Test: `tests/test_mcp_server_registration.py:test_three_forensic_tools_register`

**Interfaces:**
- Consumes: `trace_funding_dict`, `deployer_token_history_dict`, `_helius()`.
- Produces: MCP tools `trace_funding`, `get_deployer_token_history` (5-tool surface).

- [ ] **Step 1: Update the registration test (failing)** — rename to reflect five tools and assert the full set

```python
def test_three_forensic_tools_register():
    server = _load_server()
    # Assert via the public async list_tools() (Tool objects), not the private _tool_manager.
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"get_token_profile", "get_deployer", "get_holders",
                     "trace_funding", "get_deployer_token_history"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_mcp_server_registration.py::test_three_forensic_tools_register -v`
Expected: FAIL — set inequality (only the original three register).

- [ ] **Step 3: Register the two tools** (in `mcp/solana_forensics_mcp.py`; extend the `from anamnesis.forensic.mcp_tools import (...)` block with `deployer_token_history_dict`, `trace_funding_dict`, and add after `get_holders`)

```python
@server.tool()
def trace_funding(mint: str) -> dict:
    """Classify how the mint's deployer was funded: the 1-hop funding wallet and whether it is a
    known CEX, bridge, or mixer (else unknown). Mixer funding is a strong rug signal."""
    return trace_funding_dict(_helius(), mint)


@server.tool()
def get_deployer_token_history(mint: str) -> dict:
    """Other token mints the deployer has created — a live on-chain scan that surfaces serial
    deployers. Bounded; the `truncated` flag marks a partial scan."""
    return deployer_token_history_dict(_helius(), mint)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_mcp_server_registration.py -v`
Expected: PASS (all tests; five tools register).

- [ ] **Step 5: Run ruff + commit**

```bash
.venv/bin/ruff check .
git add mcp/solana_forensics_mcp.py tests/test_mcp_server_registration.py
git commit -S -m "feat: A.8b register trace_funding + get_deployer_token_history tools"
```

---

### Task 7: Verify, reconcile docs, live-smoke, PR

**Files:**
- Modify: `PLAN.md`, `SPEC.md` (toolset references)

- [ ] **Step 1: Full CI-parity verification**

Run:
```bash
.venv/bin/ruff check .
.venv/bin/pytest -q
.venv/bin/pytest -q --store=mongo
```
Expected: ruff clean; both suites pass (previous count + the new A.8b tests).

- [ ] **Step 2: Reconcile living docs** — in `PLAN.md` and `SPEC.md`, update the MCP-toolset line from "3 reads" to the five-tool surface (e.g. `MCP forensic toolset ✓ (A.8: 3 reads; A.8b: +trace_funding +get_deployer_token_history)`). Grep first: `grep -rn "trace_funding\|3 reads\|toolset" PLAN.md SPEC.md`.

```bash
git add PLAN.md SPEC.md
git commit -S -m "docs: A.8b — reflect 5-tool forensic surface in PLAN/SPEC"
```

- [ ] **Step 3: Live smoke (key-gated; never print the key)** — export the key per the handoff recipe, then exercise both tools against a **bounded** pump.fun mint (discover one via the pump.fun program's recent sigs; depth-guard < 1000 sigs). Confirm `trace_funding` returns a plausible `funder`/`source_type` and `get_deployer_token_history` returns `created_mints` with `truncated` set honestly. This is a manual gate, not a committed test (live on-chain data is flaky). Scrub `api-key=` from any output.

- [ ] **Step 4: Push + open PR**

```bash
git push -u origin feat/a8b-funding-deployer-history
gh pr create --base main --title "feat: A.8b — trace_funding + get_deployer_token_history" --body-file <(...)
```
Body: the two new forensic tools, the 1-hop + bounded-scan designs, the cite-or-omit address set, test counts, and `ruff`/`pytest`/`--store=mongo` results. **No AI attribution.** Merge with `--merge --delete-branch` after CI green.

---

## Self-Review

**Spec coverage:** D1 (both tools, one PR) → all tasks; D2 (1-hop funder) → Task 2/3; D3 (bounded mint scan, no DAS) → Task 4/5; D4 (curated in-code address set) → Task 1; D5 (raw reads, no Signals) → handlers return facts; D6 (input=mint, re-resolve) → Task 3/5. Error/bounds → `@_forensic_read` (handler tests) + `truncated`/`max_sigs` (Task 4). Testing → every task. Out-of-scope items excluded. ✓

**Placeholder scan:** No "TBD/TODO". The only non-code step is Task 1 Step 5 (address curation) — deliberately a verify-against-source data step with the cite-or-omit rule, not a code placeholder; the function + tests are complete without it. ✓

**Type consistency:** `funder_of -> tuple[str|None, str|None]` consumed by `trace_funding_dict`; `created_mints -> tuple[list[dict], bool]` consumed by `deployer_token_history_dict`; `created_mint_in_tx -> str|None` consumed by `created_mints`; `classify_funder(str|None) -> str` consumed by `trace_funding_dict`. Handler dict keys match the design's data shapes. ✓
