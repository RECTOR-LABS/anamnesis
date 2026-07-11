"""GET /api/graph/{deployer}: cluster-graph nodes/edges for the dashboard's graph view.

No engine logic lives here — `recall_cluster` (anamnesis.memory.cluster) already performs
the bounded, cycle-safe BFS walk over remembered edges around a seed, including node/edge
caps and truncation. This route only resolves the memory singleton via the `deps` module
(`from app import deps` then `deps.get_memory()`, never `from app.deps import get_memory`,
so tests can `monkeypatch.setattr(deps, "get_memory", ...)`) and reshapes the result through
`app.cards.graph_dict` for the wire.

Never 404s on an unknown deployer: `recall_cluster` degrades a seed with no remembered edges
to a single, flag-less "wallet" node (tests/test_cluster.py::test_empty_seed_is_single_node),
so there is no missing-deployer branch to special-case here — matching api/routes/assess.py's
philosophy of staying thin over an engine that already degrades gracefully.
"""
from __future__ import annotations

from fastapi import APIRouter

from anamnesis.memory.cluster import recall_cluster
from app import deps
from app.cards import graph_dict

router = APIRouter()


@router.get("/api/graph/{deployer}")
def get_graph(deployer: str) -> dict:
    return graph_dict(recall_cluster(deps.get_memory(), deployer))
