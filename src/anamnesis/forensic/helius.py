"""Helius forensic reads — a thin JSON-RPC client over the DAS + token RPC, plus
pure extractors that turn raw responses into risk-relevant fields.

Schema verified against the Helius DAS docs: getAsset ``result.token_info`` carries
``mint_authority``/``freeze_authority`` (absent == renounced == safe) and ``supply``;
``getTokenLargestAccounts`` returns ``result.value`` with raw string ``amount``s;
``getTokenAccounts`` returns a ``total`` holder count by default.

Deployer resolution (the memory key) deliberately does NOT use ``result.creators``:
the Helius docs note DAS "creators" is Metaplex metadata — not the deployer wallet —
and it is empty for pump.fun mints. ``resolve_origin`` instead takes the fee-payer of
the mint's creation (oldest) transaction — the wallet that paid to deploy, which holds
even when the rugger renounces every authority — and falls back to the update authority
when that tx is unresolvable. It returns the creation timestamp from the same tx. The
fee-payer extraction is validated against a real deploy tx once a Helius key is available.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import httpx

from .signals import LpAssessment, LpStatus, TokenProfile

HELIUS_RPC = "https://mainnet.helius-rpc.com/"

# Known launchpad program / shared-authority addresses. Such an address is the update
# authority for thousands of mints at once, so falling back to it as a "deployer" would
# collapse every launchpad token onto one PDA — the exact false clustering the fee-payer
# design avoids on the happy path. A fallback that resolves to one of these is treated as
# "deployer unknown" instead. Seeded with well-known public program addresses; extended and
# validated against live Helius data once the API key (access gate #3) lands.
LAUNCHPAD_AUTHORITIES = frozenset({
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",  # pump.fun program
})

# Curated, categorized funding-source addresses (cite-or-omit). Each entry MUST resolve to the
# named entity on a public label source (e.g. solscan.io) before it is committed; an address we
# cannot attribute is omitted, so an unlabelled funder honestly classifies as "unknown" rather
# than guessed. Extend by appending entries.
FUNDING_SOURCES: dict[str, str] = {
    # CEX hot wallets — a deployer funded by a CEX withdrawal has that hot wallet as the fee
    # payer of its seeding tx. Verified against public Solana label sources; extend by appending.
    "is6MTRHEgyFLNTfYcuV4QBWLjrZBfmhVNYR6ccgr8KV": "cex",  # OKX: Hot Wallet — Solscan label
    "GJRs4FwHtemZ5ZE9x3FNvJ8TMwitKTh21yxdRPqn7npE": "cex",  # Coinbase Hot Wallet 2 — Solscan/Arkham
}


def classify_funder(address: str | None) -> str:
    """Classify a funding-source ``address`` as ``"cex"``/``"bridge"``/``"mixer"`` via the curated
    ``FUNDING_SOURCES`` set, else ``"unknown"`` (also when the address is missing)."""
    if not address:
        return "unknown"
    return FUNDING_SOURCES.get(address, "unknown")


class HeliusError(RuntimeError):
    """A JSON-RPC error payload returned by the Helius endpoint."""


class HeliusClient:
    """Minimal Helius JSON-RPC client (DAS getAsset + standard token/tx RPC)."""

    def __init__(self, api_key: str, *, timeout: float = 20.0) -> None:
        self._url = f"{HELIUS_RPC}?api-key={api_key}"
        self._client = httpx.Client(timeout=timeout)

    def __enter__(self) -> HeliusClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _rpc(self, method: str, params: dict | list) -> dict | list:
        resp = self._client.post(
            self._url,
            json={"jsonrpc": "2.0", "id": "anamnesis", "method": method, "params": params},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise HeliusError(f"{method} failed: {data['error']}")
        if "result" not in data:
            raise HeliusError(f"{method} returned no result: {data!r}")
        return data["result"]

    def get_asset(self, mint: str) -> dict:
        """DAS getAsset for a mint — token_info (authorities, supply), creators, etc."""
        return self._rpc("getAsset", {"id": mint})

    def get_token_largest_accounts(self, mint: str) -> list[dict]:
        """Top (up to 20) token accounts by balance — for holder concentration."""
        result = self._rpc("getTokenLargestAccounts", [mint])
        return (result or {}).get("value", [])

    def get_token_accounts(self, mint: str, *, page: int = 1, limit: int = 1000) -> dict:
        """getTokenAccounts for a mint — holders, paginated; the result carries ``total``."""
        return self._rpc("getTokenAccounts", {"mint": mint, "page": page, "limit": limit})

    def get_account_info(self, address: str, *, encoding: str = "jsonParsed") -> dict:
        """Account info for an address — returns ``result.value`` ({} when the account is null)."""
        result = self._rpc("getAccountInfo", [address, {"encoding": encoding}])
        return (result or {}).get("value") or {}

    def get_token_supply(self, mint: str) -> int:
        """Current total supply of a mint (raw base units)."""
        result = self._rpc("getTokenSupply", [mint])
        return int(((result or {}).get("value") or {}).get("amount") or 0)

    def get_signatures_for_address(
        self, address: str, *, before: str | None = None, limit: int = 1000
    ) -> list[dict]:
        """Confirmed signatures for an address, newest first (paginated via ``before``)."""
        options: dict = {"limit": limit}
        if before:
            options["before"] = before
        return self._rpc("getSignaturesForAddress", [address, options])

    def get_transaction(self, signature: str) -> dict:
        """A parsed transaction; accountKeys[0] is the fee payer."""
        return self._rpc(
            "getTransaction",
            [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
        )

    def oldest_signature(self, address: str, *, page_limit: int = 1000) -> str | None:
        """The earliest signature for an address — for a mint, its creation tx."""
        before: str | None = None
        oldest: str | None = None
        while True:
            page = self.get_signatures_for_address(address, before=before, limit=page_limit)
            if not page:
                break
            sig = page[-1].get("signature")
            if sig is None:  # malformed oldest entry — stop rather than KeyError
                break
            oldest = sig
            if len(page) < page_limit:
                break
            before = oldest
        return oldest


def parse_authorities(asset: dict) -> tuple[str | None, str | None]:
    """Return ``(mint_authority, freeze_authority)`` from a getAsset result.

    Absent/null == renounced == safe (``None``), matching ``TokenProfile`` semantics.
    """
    info = asset.get("token_info") or {}
    return info.get("mint_authority"), info.get("freeze_authority")


def top_holder_pct(largest_accounts: list[dict], supply: int) -> float:
    """Largest single holder as a percentage of total supply (``0.0`` if unknown)."""
    if not largest_accounts or not supply:
        return 0.0
    try:
        top = int(largest_accounts[0].get("amount"))
    except (TypeError, ValueError):  # missing/non-numeric amount — unknown, treat as safe
        return 0.0
    return top / supply * 100.0


def holder_count(client: HeliusClient, mint: str) -> int:
    """Total holders of a mint (token-account count) from getTokenAccounts ``total``."""
    result = client.get_token_accounts(mint, limit=1)
    return int((result or {}).get("total", 0))


def fee_payer(tx: dict) -> str | None:
    """The fee payer of a transaction — accountKeys[0] (jsonParsed obj or raw string)."""
    keys = (((tx or {}).get("transaction") or {}).get("message") or {}).get("accountKeys") or []
    if not keys:
        return None
    first = keys[0]
    return first["pubkey"] if isinstance(first, dict) else first


def creation_time(tx: dict) -> str | None:
    """ISO-8601 UTC timestamp from a transaction's ``blockTime`` (None if absent)."""
    block_time = (tx or {}).get("blockTime")
    if not block_time:
        return None
    return datetime.fromtimestamp(block_time, tz=timezone.utc).isoformat()


def update_authority(asset: dict) -> str | None:
    """The asset's update authority — the ``full``-scope entry, else the first, else None."""
    authorities = asset.get("authorities") or []
    for entry in authorities:
        if "full" in (entry.get("scopes") or []):
            return entry.get("address")
    return authorities[0].get("address") if authorities else None


def resolve_origin(client: HeliusClient, mint: str) -> tuple[str | None, str | None]:
    """Return ``(deployer, created_at)`` from the mint's creation (oldest) tx.

    The deployer is the creation-tx fee payer, falling back to the update authority;
    created_at is that tx's ``blockTime`` (ISO UTC). Either may be ``None``. The creation
    tx is fetched once so both fields come from a single round trip. A fallback that lands
    on a known launchpad shared authority (see ``LAUNCHPAD_AUTHORITIES``) is discarded —
    collapsing every launchpad mint onto one PDA would manufacture a false deployer
    cluster, so the deployer is left unknown (``None``) instead.
    """
    signature = client.oldest_signature(mint)
    deployer: str | None = None
    created_at: str | None = None
    if signature:
        tx = client.get_transaction(signature)
        deployer = fee_payer(tx)
        created_at = creation_time(tx)
    if deployer is None:
        candidate = update_authority(client.get_asset(mint))
        deployer = None if candidate in LAUNCHPAD_AUTHORITIES else candidate
    return deployer, created_at


def resolve_deployer(client: HeliusClient, mint: str) -> str | None:
    """The mint's deployer wallet (its memory key) — see :func:`resolve_origin`."""
    return resolve_origin(client, mint)[0]


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


LpResolver = Callable[[HeliusClient, str], LpAssessment]


def _lp_unanalyzed(client: HeliusClient, mint: str) -> LpAssessment:
    """Default: liquidity not analyzed -> honest UNKNOWN (never a false 'not secured').

    The real LpAnalyzer (forensic/lp.py) is injected by the caller (MCP entrypoint); keeping
    it out of helius.py keeps this module free of the aggregator/lp dependency.
    """
    return LpAssessment(LpStatus.UNKNOWN, [])


def build_token_profile(
    client: HeliusClient, mint: str, *, lp_resolver: LpResolver = _lp_unanalyzed
) -> TokenProfile:
    """Assemble a ``TokenProfile`` for a mint from grounded Helius reads.

    Pulls authorities + supply (getAsset), holder concentration (largest accounts),
    holder count (getTokenAccounts), and deployer + creation time (the creation tx).
    ``lp_resolver`` decides ``lp``; the default reports UNKNOWN (not analyzed) — the real
    LpAnalyzer is injected by the MCP entrypoint.
    """
    asset = client.get_asset(mint)
    info = asset.get("token_info") or {}
    supply = int(info.get("supply") or 0)
    mint_authority, freeze_authority = parse_authorities(asset)
    largest = client.get_token_largest_accounts(mint)
    deployer, created_at = resolve_origin(client, mint)
    return TokenProfile(
        mint=mint,
        deployer=deployer,
        mint_authority=mint_authority,
        freeze_authority=freeze_authority,
        lp=lp_resolver(client, mint),
        top_holder_pct=top_holder_pct(largest, supply),
        holder_count=holder_count(client, mint),
        created_at=created_at,
    )
