"""A.10 demo seed — make the compounding-memory demo reproducible.

Seeds a real serial rugger's prior-rug history (first-party RUGGED edges, written via
ForensicMemory directly to simulate the agent's own grounded observations from past sessions)
so the live agent, run against another real token by that deployer, flags it HIGH from memory
alone. Also measures the honest "N× faster than re-deriving cold" metric.

The pure core (build_seed_edges, assert_resettable) is unit-tested without live services; the
CLI shell (scripts/seed_demo.py) wires the Mongo client + Helius. Imports cleanly without
qwen-agent/mcp/openai (CI subset) — pymongo/forensic deps are imported lazily in the I/O paths.

Design: docs/design/2026-06-27-a10-demo-seed-design.md
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from . import config
from .logging_setup import quiet_http_loggers
from .memory.alerts import ALERTS_COLLECTION
from .memory.graph import ForensicMemory
from .memory.models import Edge, Provenance, make_edge
from .memory.mongo_store import COLLECTION as RELATIONS_COLLECTION
from .memory.mongo_store import MongoRepository

# --- The approved demo anchor (real serial rugger, found via Helius 2026-06-27) -----------
# sF2ww… launched 13 mints (Nov 2025 -> 2026-06-27), nearly all dead / zero-liquidity.
DEPLOYER = "sF2wwbFkuzD9mT6YfwXmLE14qyzJVaf2QEDg8dZkMvv"

# Its newest token. On its OWN live signals it scores LOW (renounced authorities) — the
# "looks clean" half of the contrast. NOT seeded: the demo assesses it live, resolve_origin
# resolves it back to DEPLOYER, and the remembered rugs then drive the verdict HIGH.
DEMO_MINT = "GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump"

SEED_SOURCE = "seed:prior-session-observation"


@dataclass(frozen=True)
class RugSeed:
    """A prior rug to seed: its real mint, when it was true on-chain (valid_from), and the
    staggered past-session date the agent 'observed' it (recorded_at) — the bi-temporal split."""

    mint: str
    valid_from: str   # the token's real 2025 on-chain creation date
    recorded_at: str  # a fixed past-session date this month (deterministic -> idempotent)


# Three confirmed-dead 2025 tokens by DEPLOYER, observed across past sessions (the staggered
# recorded_at yields the as-of/time-travel beat). 3 distinct first-party rugs -> 0.85 -> HIGH.
PRIOR_RUGS = [
    RugSeed("3qFSoG3TcNs8QhcgBe5Ra3UgsLWd2k9QZXfs1KY3pump",
            valid_from="2025-11-16", recorded_at="2026-06-05"),
    RugSeed("258YRv1dTEEYAxQFJkXuLJ5zYVKjG1SJA5ueeCqvpump",
            valid_from="2025-11-20", recorded_at="2026-06-15"),
    RugSeed("A1473c8sov1uue8KAjMCHZGRgnDQYn6UJbY33p1ipump",
            valid_from="2025-12-05", recorded_at="2026-06-22"),
]


def build_seed_edges(deployer: str, rugs: list[RugSeed]) -> list[Edge]:
    """Build the first-party DEPLOYED + RUGGED edges for a deployer's prior rugs.

    Each rug yields a DEPLOYED edge (recalled context; not scored) and a RUGGED edge (the
    scored prior-rug evidence). method='first_party' is REQUIRED — risk comes only from
    first-party rugs, and the remember TOOL would force 'claimed' (poisoning defense), so the
    seed writes these directly (make_edge names the demo seed as an intended writer).
    """
    edges: list[Edge] = []
    for r in rugs:
        prov = Provenance(source=SEED_SOURCE, method="first_party", confidence=1.0)
        for etype in ("DEPLOYED", "RUGGED"):
            edges.append(make_edge(
                etype, deployer, r.mint,
                valid_from=r.valid_from, recorded_at=r.recorded_at, provenance=prov,
            ))
    return edges


def collection_counts(client, db_name: str) -> dict:
    """Current document counts in the two collections this seed touches — shown before a
    destructive --reset so the operator sees exactly what (and how much) is at stake."""
    db = client[db_name]
    return {
        RELATIONS_COLLECTION: db[RELATIONS_COLLECTION].count_documents({}),
        ALERTS_COLLECTION: db[ALERTS_COLLECTION].count_documents({}),
    }


def reset_collections(client, db_name: str) -> dict:
    """Clear ONLY relations + alert_drafts in db_name; never drops the database, never touches
    any other collection. Returns the deleted counts.

    Deliberately NOT name-guarded: dev and the deployed instance share the db name 'anamnesis'
    (config default), so a name blocklist cannot tell them apart and only gives false
    confidence. The real safety lives in the caller (main): --reset is a dry run that prints the
    target db + host + counts, and only --reset --force actually clears — an explicit,
    target-visible confirmation rather than a guess at the db's identity."""
    db = client[db_name]
    return {
        RELATIONS_COLLECTION: db[RELATIONS_COLLECTION].delete_many({}).deleted_count,
        ALERTS_COLLECTION: db[ALERTS_COLLECTION].delete_many({}).deleted_count,
    }


def measure_metric(memory: ForensicMemory, helius, deployer: str) -> dict:
    """Measure "has this deployer rugged before?" two ways and report the speedup.

    memory: recall_deployer_history + trust_weighted_risk — one indexed query.
    cold:   created_mints (scan the deployer's signatures) + build_token_profile on each prior
            mint, i.e. re-deriving the rug history from on-chain scratch.
    """
    from .forensic.helius import build_token_profile, created_mints
    from .forensic.lp import LpAnalyzer
    from .forensic.pools import DexScreenerClient

    t0 = time.perf_counter()
    history = memory.recall_deployer_history(deployer)
    mem_risk = memory.trust_weighted_risk(history)
    mem_s = time.perf_counter() - t0

    dex = DexScreenerClient()
    try:
        t0 = time.perf_counter()
        mints, _ = created_mints(helius, deployer)
        for m in mints:
            build_token_profile(helius, m["mint"], lp_resolver=LpAnalyzer(dex).assess)
        cold_s = time.perf_counter() - t0
    finally:
        dex.close()

    return {
        "deployer": deployer,
        "memory_seconds": mem_s,
        "cold_seconds": cold_s,
        "speedup_x": (cold_s / mem_s) if mem_s > 0 else float("inf"),
        "memory_risk": mem_risk,
        "rugs_recalled": sum(1 for e in history if e.type == "RUGGED"),
        "mints_scanned_cold": len(mints),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    # Quiet httpx/httpcore INFO before any live-HTTP path (e.g. --metric does Helius reads) so the
    # api-key carried in the request URL is never logged if the caller enabled verbose logging.
    quiet_http_loggers()
    parser = argparse.ArgumentParser(description="Seed the Anamnesis demo memory (A.10).")
    parser.add_argument("--reset", action="store_true",
                        help="clear the demo collections before seeding (dry run unless --force)")
    parser.add_argument("--force", action="store_true",
                        help="with --reset: actually clear (without it, --reset only previews)")
    parser.add_argument("--metric", action="store_true",
                        help="measure + print the memory-vs-cold N× speedup, then exit")
    args = parser.parse_args(argv)

    from pymongo import MongoClient

    client = MongoClient(config.require("ANAMNESIS_MONGODB_URI"))
    db_name = config.ANAMNESIS_DB
    memory = ForensicMemory(MongoRepository(client, db_name))

    if args.metric:
        from .forensic.helius import HeliusClient

        helius = HeliusClient(config.require("ANAMNESIS_HELIUS_API_KEY"))
        with helius:
            result = measure_metric(memory, helius, DEPLOYER)
        print(f"memory: {result['memory_seconds'] * 1000:.1f} ms "
              f"({result['rugs_recalled']} rugs recalled, risk={result['memory_risk']:.2f})")
        print(f"cold:   {result['cold_seconds']:.1f} s "
              f"({result['mints_scanned_cold']} mints scanned on-chain)")
        print(f"=> {result['speedup_x']:,.0f}x faster from memory")
        return 0

    if args.reset:
        counts = collection_counts(client, db_name)  # also forces the connection -> client.address
        addr = client.address  # (host, port) — never credentials
        target = f"{db_name!r} @ {addr[0]}:{addr[1]}" if addr else f"{db_name!r}"
        if not args.force:
            print(f"--reset DRY RUN — would clear {counts} from {target}.")
            print("This DESTROYS accumulated first-party memory + the pending-alert queue. "
                  "Confirm the db+host above, then re-run with --reset --force.")
            return 2
        print(f"--reset --force: clearing {target} (was {counts})")
        print(f"cleared {reset_collections(client, db_name)}")

    edges = build_seed_edges(DEPLOYER, PRIOR_RUGS)
    memory.remember(edges, now=_now_iso())
    print(f"seeded {len(edges)} edges ({len(PRIOR_RUGS)} prior rugs) for deployer "
          f"{DEPLOYER} into {db_name!r}.")
    print(f"demo mint (assess live): {DEMO_MINT}")
    return 0
