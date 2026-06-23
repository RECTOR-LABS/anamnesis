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

from .signals import TokenProfile

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


LpResolver = Callable[[HeliusClient, str], bool]


def _lp_unverified(client: HeliusClient, mint: str) -> bool:
    """Conservative default: liquidity unverified -> treated as not secured (unsafe)."""
    return False


def build_token_profile(
    client: HeliusClient, mint: str, *, lp_resolver: LpResolver = _lp_unverified
) -> TokenProfile:
    """Assemble a ``TokenProfile`` for a mint from grounded Helius reads.

    Pulls authorities + supply (getAsset), holder concentration (largest accounts),
    holder count (getTokenAccounts), and deployer + creation time (the creation tx).
    ``lp_resolver`` decides ``lp_secured``; the default treats unverified liquidity as
    unsecured, pending first-party LP-burn/lock detection.
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
        lp_secured=lp_resolver(client, mint),
        top_holder_pct=top_holder_pct(largest, supply),
        holder_count=holder_count(client, mint),
        created_at=created_at,
    )
