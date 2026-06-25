"""Manual live validation of LP-secured detection (key-gated). NEVER prints the Helius key.

Usage:
  line=$(grep -E '^(export )?ANAMNESIS_HELIUS_API_KEY=' ~/Documents/secret/.env | tail -1)
  export ANAMNESIS_HELIUS_API_KEY="${line#*=}"
  PYTHONPATH=src .venv/bin/python scripts/lp_smoke.py <mint> [<mint> ...]
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
            print(f"\n{mint} -> {a.status.value}  ({len(a.evidence)} pools)")
            for e in a.evidence:
                usd = f"${e.liquidity_usd:,.0f}" if e.liquidity_usd else "n/a"
                print(f"  [{e.venue}] {e.method} secured={e.secured} liq={usd} lp_mint={e.lp_mint}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: lp_smoke.py <mint> [<mint> ...]")
    main(sys.argv[1:])
