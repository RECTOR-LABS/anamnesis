"""Cluster traversal — a bounded, multi-hop walk over the bi-temporal memory graph.

`recall_cluster` BFS-walks the remembered relationship edges around a seed wallet/token,
treating edges as undirected so a deployer reaches its tokens, its cluster peers, and their
tokens. READ-ONLY: it visualizes what memory already knows (no on-chain reads, no writes).
Node kind + flags are inferred from incident edge types so the render can light up rugged /
watchlisted / deployer nodes. Pure over an injected ForensicMemory — CI-testable.
"""
from __future__ import annotations

from dataclasses import dataclass

from .graph import ForensicMemory

# Edge types whose dst is a token mint (vs a funding source / pool / wallet).
_TOKEN_DST = frozenset({"DEPLOYED", "RUGGED", "WATCHLISTED"})


@dataclass(frozen=True)
class ClusterNode:
    id: str
    kind: str               # "wallet" | "token" | "funding" | "pool"
    flags: tuple[str, ...]  # sorted subset of ("deployer", "rugged", "watchlisted")


@dataclass(frozen=True)
class ClusterEdge:
    src: str
    dst: str
    rel: str
    method: str
    confidence: float


@dataclass(frozen=True)
class ClusterGraph:
    seed: str
    nodes: tuple[ClusterNode, ...]
    edges: tuple[ClusterEdge, ...]
    depth: int
    truncated: bool
    as_of: str | None = None


def _build_nodes(node_ids: set[str], edges: list[ClusterEdge]) -> list[ClusterNode]:
    token_dst, funding_dst, pool_dst = set(), set(), set()
    deployer_src, rugged_dst, watchlisted_dst = set(), set(), set()
    for e in edges:
        if e.rel in _TOKEN_DST:
            token_dst.add(e.dst)
        if e.rel == "FUNDED_BY":
            funding_dst.add(e.dst)
        if e.rel == "PROVIDES_LP":
            pool_dst.add(e.dst)
        if e.rel == "DEPLOYED":
            deployer_src.add(e.src)
        if e.rel == "RUGGED":
            rugged_dst.add(e.dst)
        if e.rel == "WATCHLISTED":
            watchlisted_dst.add(e.dst)
    nodes = []
    for nid in sorted(node_ids):
        if nid in token_dst:
            kind = "token"
        elif nid in funding_dst:
            kind = "funding"
        elif nid in pool_dst:
            kind = "pool"
        else:
            kind = "wallet"
        flags = [f for f, members in (("deployer", deployer_src), ("rugged", rugged_dst),
                                      ("watchlisted", watchlisted_dst)) if nid in members]
        nodes.append(ClusterNode(id=nid, kind=kind, flags=tuple(flags)))
    return nodes


def recall_cluster(
    memory: ForensicMemory,
    seed: str,
    *,
    depth: int = 2,
    rel_types: frozenset[str] | None = None,
    max_nodes: int = 60,
    max_edges: int = 150,
    as_of: str | None = None,
) -> ClusterGraph:
    """Bounded, cycle-safe, undirected BFS over remembered edges around `seed`.

    Treats edges as undirected for reachability (preserving direction in the result),
    filters by `rel_types` (None = all), caps at `max_nodes`/`max_edges` (-> `truncated`,
    surfaced, never silent), and threads `as_of` for a bi-temporal view.
    """
    visited: set[str] = set()
    node_ids: set[str] = {seed}
    edges_by_id: dict[str, ClusterEdge] = {}
    truncated = False
    frontier = [seed]
    for _ in range(max(depth, 1)):
        nxt: list[str] = []
        for node in frontier:
            if node in visited:
                continue
            visited.add(node)
            for e in memory.recall(node, as_of=as_of):
                if rel_types is not None and e.type not in rel_types:
                    continue
                if e.id not in edges_by_id:
                    if len(edges_by_id) >= max_edges:
                        truncated = True
                    else:
                        edges_by_id[e.id] = ClusterEdge(
                            e.src, e.dst, e.type, e.provenance.method, e.provenance.confidence
                        )
                for nb in (e.src, e.dst):
                    if nb == node or nb in node_ids:
                        continue
                    if len(node_ids) >= max_nodes:
                        truncated = True
                    else:
                        node_ids.add(nb)
                        nxt.append(nb)
        frontier = nxt
        if not frontier:
            break
    # Keep only edges whose endpoints both made the node set (drop danglers created when a
    # node cap was hit mid-expansion), so the rendered graph is self-consistent.
    edges = [e for e in edges_by_id.values() if e.src in node_ids and e.dst in node_ids]
    nodes = _build_nodes(node_ids, edges)
    return ClusterGraph(
        seed=seed,
        nodes=tuple(nodes),
        edges=tuple(sorted(edges, key=lambda e: (e.src, e.dst, e.rel))),
        depth=depth,
        truncated=truncated,
        as_of=as_of,
    )
