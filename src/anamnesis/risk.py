"""Verdict composition — fuse live on-chain signals with remembered risk.

The defining property: memory alone can drive a HIGH verdict. A token whose
live signals look clean is still flagged HIGH when its deployer carries
remembered prior-rug history — this is the compounding-memory payoff made
concrete.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .forensic.signals import Signal

HIGH_THRESHOLD = 0.6
MEDIUM_THRESHOLD = 0.3
_HIGH_WEIGHT = 0.5
_MEDIUM_WEIGHT = 0.2


@dataclass
class Verdict:
    level: str  # "low" | "medium" | "high"
    score: float  # 0..1
    rationale: str
    cited_signals: list[Signal] = field(default_factory=list)
    remembered: list = field(default_factory=list)


def compose_verdict(signals: list[Signal], memory_edges: list, memory_risk: float) -> Verdict:
    live = _HIGH_WEIGHT * sum(1 for s in signals if s.severity == "high") \
        + _MEDIUM_WEIGHT * sum(1 for s in signals if s.severity == "medium")
    score = min(max(live, memory_risk), 1.0)  # memory alone can drive risk
    level = "high" if score >= HIGH_THRESHOLD else "medium" if score >= MEDIUM_THRESHOLD else "low"

    why: list[str] = []
    if memory_risk >= HIGH_THRESHOLD:
        why.append("deployer has remembered prior rug history")
    elif memory_risk >= MEDIUM_THRESHOLD:
        why.append("deployer has remembered partial rug history")
    if any(s.severity == "high" for s in signals):
        why.append("live high-severity on-chain signals present")
    elif any(s.severity == "medium" for s in signals):
        why.append("live medium-severity on-chain signals present")
    rationale = "; ".join(why) or "no significant risk signals or memory"

    return Verdict(level, score, rationale, cited_signals=signals, remembered=list(memory_edges))
