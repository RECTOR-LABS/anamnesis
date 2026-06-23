"""Helius forensic reads — a thin JSON-RPC client over the DAS + token RPC, plus
pure extractors that turn raw responses into risk-relevant fields.

Schema verified against the Helius DAS getAsset docs: ``result.token_info`` carries
``mint_authority``/``freeze_authority`` (absent == renounced == safe) and ``supply``;
``getTokenLargestAccounts`` returns ``result.value`` with raw string ``amount``s.

Deployer resolution (the memory key) deliberately does NOT use ``result.creators``:
the Helius docs note DAS "creators" is Metaplex metadata — not the deployer wallet —
and it is empty for pump.fun mints. Instead ``resolve_deployer`` takes the fee-payer
of the mint's creation (oldest) transaction — the wallet that paid to deploy, which
holds even when the rugger renounces every authority — and falls back to the update
authority when the creation tx is unresolvable. The fee-payer extraction is validated
against a real deploy transaction once a Helius key is available (the live tracer).
"""

from __future__ import annotations

import httpx

HELIUS_RPC = "https://mainnet.helius-rpc.com/"


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
        return data["result"]

    def get_asset(self, mint: str) -> dict:
        """DAS getAsset for a mint — token_info (authorities, supply), creators, etc."""
        return self._rpc("getAsset", {"id": mint})

    def get_token_largest_accounts(self, mint: str) -> list[dict]:
        """Top (up to 20) token accounts by balance — for holder concentration."""
        result = self._rpc("getTokenLargestAccounts", [mint])
        return result.get("value", [])

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
            oldest = page[-1]["signature"]
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
    top = int(largest_accounts[0]["amount"])
    return top / supply * 100.0


def fee_payer(tx: dict) -> str | None:
    """The fee payer of a transaction — accountKeys[0] (jsonParsed obj or raw string)."""
    keys = (((tx or {}).get("transaction") or {}).get("message") or {}).get("accountKeys") or []
    if not keys:
        return None
    first = keys[0]
    return first["pubkey"] if isinstance(first, dict) else first


def update_authority(asset: dict) -> str | None:
    """The asset's update authority — the ``full``-scope entry, else the first, else None."""
    authorities = asset.get("authorities") or []
    for entry in authorities:
        if "full" in (entry.get("scopes") or []):
            return entry.get("address")
    return authorities[0].get("address") if authorities else None


def resolve_deployer(client: HeliusClient, mint: str) -> str | None:
    """Resolve a mint's deployer wallet (its memory key).

    Primary: the fee payer of the mint's creation (oldest) transaction — robust even
    when every authority is renounced. Fallback: the update authority from getAsset.
    """
    signature = client.oldest_signature(mint)
    if signature:
        payer = fee_payer(client.get_transaction(signature))
        if payer:
            return payer
    return update_authority(client.get_asset(mint))
