# A.8b — Funding-trace + deployer-token-history reads (design)

- **Date:** 2026-06-25
- **Status:** Approved — ready for implementation plan
- **Task:** PLAN.md A.8b (the two forensic algorithms deferred from A.8)
- **Depends on:** `forensic/helius.py` (A.5 — `resolve_origin`, `oldest_signature`, `get_transaction`, `get_signatures_for_address`, `fee_payer`, `creation_time`), `forensic/mcp_tools.py` (A.8 — `@_forensic_read`), `mcp/solana_forensics_mcp.py` (A.8), `agent/agent.py` (A.9)

## Goal

Add the two forensic reads explicitly deferred from A.8 (see `2026-06-24-a8-mcp-server.md` §D2): they are **new forensic algorithms**, not thin wrappers. They were blocked on live Helius (gate #3), which is now open and the read layer is mainnet-validated.

- **`trace_funding`** — classify the *source* that funded the mint's deployer (CEX / bridge / mixer / unknown). A mixer-funded deployer is a strong pre-trade rug signal; a CEX-hot-wallet funder is KYC-traceable.
- **`get_deployer_token_history`** — the **live** list of *other* mints the deployer has created, surfacing serial deployers. Complements the bi-temporal memory store (which holds rug history Anamnesis has *observed*) with an on-chain ground-truth scan.

Both follow the A.8 structure unchanged: algorithm in `helius.py` (pure over an injected `HeliusClient`, fake-client unit tests, CI-runnable) → `@_forensic_read` dict handler in `mcp_tools.py` → thin `@server.tool()` in the MCP entrypoint → auto-namespaced `solana_forensics-*` to the agent.

## Decisions

### D1 — Scope: both tools, one PR

Both ship together (independent algorithms, tested separately), matching the prior design's bundling. Neither is on the compounding-memory demo's critical path, so this is forensic-depth work, not a demo blocker.

### D2 — `trace_funding`: 1-hop direct funder

Classify the sender of the deployer's **earliest inbound SOL transfer** — a fresh deploy wallet's first on-chain appearance is the funding that seeded it. One hop only: bounded, fast (pre-trade-friendly), deterministic, and testable. Multi-hop laundering traversal (graph walk, cycle handling, many RPC calls) is explicitly out of scope and noted as a future extension; no premature depth parameter (YAGNI).

If the earliest tx is not a simple inbound transfer (or the deployer is unresolved), `funder` is `None` and `source_type` is `"unknown"` — the tool never guesses.

### D3 — `get_deployer_token_history`: bounded on-chain mint-creation scan

Scan the deployer's signature history (depth-guarded, per the `resolve_origin` high-activity-mint hang lesson): page `get_signatures_for_address`, fetch each tx, detect `initializeMint` / `initializeMint2` instructions on the **SPL Token and Token-2022** programs, and collect the created mints + creation times. Results are capped with an explicit `truncated` flag — **no silent caps**.

The DAS `getAssetsByCreator` path is deliberately **not** used: Metaplex "creators" is metadata, not the deployer wallet, and is empty for pump.fun mints — the same reason `resolve_origin` avoids it (§helius.py module docstring). The sig-scan is the validated path; its cost (≈1 `getTransaction` per signature) is the reason for the depth bound. This is the heaviest tool — a deliberate deep-dive the agent invokes when investigating a deployer, not a sub-second pre-trade check.

### D4 — Funding-source address set: curated, categorized, in-code

A version-controlled mapping mirroring the existing `LAUNCHPAD_AUTHORITIES` frozenset:

```python
FUNDING_SOURCES: dict[str, str] = {"<addr>": "cex" | "bridge" | "mixer", ...}
def classify_funder(address: str | None) -> str  # "cex" | "bridge" | "mixer" | "unknown"
```

Seeded with **cited** well-known Solana mainnet addresses (major CEX hot wallets; canonical bridge program/custody addresses; any documented mixer/tumbler addresses). Cite-or-omit: we only ship an address we can attribute; everything else classifies as `"unknown"`. Extensible by appending entries. No external data file and no third-party label API (avoids a new runtime dependency and keeps classification auditable in-repo).

### D5 — Raw reads, not new `Signal` codes

Both tools return structured **facts**, consistent with the existing three reads; the LLM and the verdict/`assess_risk` layer interpret them. Minting `MIXER_FUNDED` / `SERIAL_DEPLOYER` `Signal`s into `signals.py` is a separate change (it would extend `TokenProfile`/`assess_token_signals`) and is out of A.8b scope.

### D6 — Input contract: `mint` (re-resolve the deployer)

Both tools take `mint` and resolve the deployer internally via `resolve_origin`, for tool-surface consistency with the existing three reads and to reuse `@_forensic_read`'s `mint` validation. The small cost (one extra creation-tx resolution) buys a uniform agent-facing contract.

## Components & data flow

```
trace_funding(mint):
  resolve_origin(mint) -> deployer
  oldest_signature(deployer) -> sig -> get_transaction(sig)
  funder = fee_payer(tx)   (the wallet that signed+paid the seeding tx; None if it is the deployer itself)
  funded_at = creation_time(tx)
  source_type = classify_funder(funder)
  -> {mint, deployer, funder, source_type, funded_at}

get_deployer_token_history(mint):
  resolve_origin(mint) -> deployer
  bounded page over get_signatures_for_address(deployer):
    for each sig: get_transaction(sig); if it creates a mint, record (created_mint, created_at)
  -> {mint, deployer, created_mints: [{mint, created_at}...], count, truncated}
```

New `helius.py` surface (pure, injected client):
- `FUNDING_SOURCES`, `classify_funder(address) -> str`
- `funder_of(client, deployer) -> tuple[str | None, str | None]` → `(funder, funded_at)`: the **payer of the deployer's earliest tx** — `fee_payer(get_transaction(oldest_signature(deployer)))` is the wallet that signed+paid the transfer that seeded it. `funder` is `None` when that payer is the deployer itself (no identifiable inbound funder) or the tx is unresolved. Reuses `fee_payer` / `creation_time`.
- `created_mints(client, deployer, *, max_sigs: int, max_results: int) -> tuple[list[dict], bool]` → `(mints, truncated)`

`mcp_tools.py` handlers (`@_forensic_read`), each composing the helpers above: `trace_funding_dict` = `resolve_origin` + `funder_of` + `classify_funder`; `deployer_token_history_dict` = `resolve_origin` + `created_mints`.

`mcp/solana_forensics_mcp.py`: two new `@server.tool()` wrappers calling the handlers with the live client.

## Error handling & bounds

- `@_forensic_read` already rejects a blank mint and degrades any `HeliusError` / `httpx.HTTPError` / parse error (`ValueError`/`TypeError`/`AttributeError`/`KeyError`) to `{"error","mint"}` — both new handlers inherit this.
- Deployer unresolved → `trace_funding` returns `funder=None, source_type="unknown"`; `get_deployer_token_history` returns an empty `created_mints` with `count=0`.
- Both bounded against the signature-pagination hang: `get_deployer_token_history` caps signature pages and result count; `trace_funding` reads only the single earliest tx.

## Testing

TDD, fake-`HeliusClient` exact-dict unit tests (no network, no `mcp` package — CI-runnable), mirroring `test_mcp_tools.py` / `test_helius.py`:

- `classify_funder`: cex / bridge / mixer / unknown / `None`.
- `trace_funding`: each `source_type`; earliest-tx-not-a-transfer → unknown; deployer unresolved → unknown; blank mint → error.
- `get_deployer_token_history`: zero / one / many creations; both Token and Token-2022 `initializeMint(2)`; truncation sets `truncated=True`; deployer unresolved → empty; blank mint → error.
- Registration test asserts the **five**-tool surface now registers.
- Live validation (key-gated, key never printed/logged) on a bounded pump.fun mint before merge; flaky live on-chain data stays out of the committed suite.

## Out of scope

Multi-hop funding traversal; DAS-based creator history; `Signal` integration (`MIXER_FUNDED`/`SERIAL_DEPLOYER`); LP-burn/lock detection (`lp_secured` still default). Each is a separate tracked change.
