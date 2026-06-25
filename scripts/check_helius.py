"""Phase-0 access smoke (gate #3): prove the Helius data layer by pulling a real
token's authorities via DAS getAsset — the riskiest seam, so confirm it early.

Prereqs: ``pip install httpx`` and ANAMNESIS_HELIUS_API_KEY set in .env.
Run:     ``PYTHONPATH=src python scripts/check_helius.py``
Expect:  a non-empty ``authorities: [...]`` list for the test mint.
"""

from __future__ import annotations

import httpx

from anamnesis.config import helius_rpc_url

# USDC mint — a stable, always-present asset for the connectivity check.
TEST_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


def main() -> None:
    resp = httpx.post(
        helius_rpc_url(),
        json={
            "jsonrpc": "2.0",
            "id": "anamnesis-smoke",
            "method": "getAsset",
            "params": {"id": TEST_MINT},
        },
        timeout=20,
    )
    resp.raise_for_status()
    result = resp.json().get("result") or {}
    authorities = result.get("authorities", [])
    print(f"authorities: {authorities}")
    if not authorities:
        raise SystemExit("FAIL: empty authorities — check the API key or endpoint.")


if __name__ == "__main__":
    main()
