"""assess_risk — the forensic decision pipeline: live signals + remembered
deployer history -> verdict.

This is the compounding-memory payoff made executable: a fresh, clean-looking
token from a deployer we have seen rug before is flagged HIGH on memory alone.
Pure over its inputs (a built TokenProfile + a ForensicMemory), so the whole
"session-1 misses -> session-5 catches" behavior is unit-testable without the
LLM, the network, or a database.
"""

from __future__ import annotations

from .forensic.signals import TokenProfile, assess_token_signals
from .memory.graph import ForensicMemory
from .risk import Verdict, compose_verdict


def assess_risk(
    profile: TokenProfile, memory: ForensicMemory, *, as_of: str | None = None
) -> Verdict:
    """Fuse a token's live signals with its deployer's remembered history into a Verdict.

    The deployer's prior DEPLOYED/RUGGED history is recalled from memory and trust-weighted;
    ``compose_verdict`` lets that remembered risk drive the verdict even when the live
    on-chain signals are clean. An unresolved deployer simply carries no memory.
    """
    signals = assess_token_signals(profile)
    history = (
        memory.recall_deployer_history(profile.deployer, as_of=as_of)
        if profile.deployer
        else []
    )
    memory_risk = memory.trust_weighted_risk(history)
    return compose_verdict(signals, history, memory_risk)
