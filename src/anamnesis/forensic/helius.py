"""Helius forensic reads — a thin JSON-RPC client over the DAS + token RPC, plus
pure extractors that turn raw responses into risk-relevant fields.

Schema verified against the Helius DAS getAsset docs: ``result.token_info`` carries
``mint_authority``/``freeze_authority`` (absent == renounced == safe) and ``supply``;
``getTokenLargestAccounts`` returns ``result.value`` with raw string ``amount``s.

Deliberately NOT sourcing the deployer from ``result.creators``: the Helius docs
note DAS "creators" is Metaplex metadata — not the deployer wallet — and it is
empty for pump.fun mints, the exact case Anamnesis targets. Deployer resolution is
handled separately (pending the chosen strategy), so it is absent here by design.
"""

from __future__ import annotations

import httpx

HELIUS_RPC = "https://mainnet.helius-rpc.com/"


class HeliusError(RuntimeError):
    """A JSON-RPC error payload returned by the Helius endpoint."""


class HeliusClient:
    """Minimal Helius JSON-RPC client (DAS getAsset + standard token RPC)."""

    def __init__(self, api_key: str, *, timeout: float = 20.0) -> None:
        self._url = f"{HELIUS_RPC}?api-key={api_key}"
        self._client = httpx.Client(timeout=timeout)

    def __enter__(self) -> HeliusClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _rpc(self, method: str, params: dict | list) -> dict:
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
