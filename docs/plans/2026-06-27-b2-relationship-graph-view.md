# B.2 — Relationship-graph view (recall_cluster + interactive HTML) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Given a seed wallet/mint, traverse the agent's compounding memory and render an interactive relationship graph in which a serial rugger's tokens, prior rugs, the watchlisted token, cluster peers, and funding sources light up.

**Architecture:** A thin, read-only **view** over the existing bi-temporal memory — purely additive (like B.1). A pure BFS traversal (`memory/cluster.py`) produces a `ClusterGraph`; a pure renderer (`agent/graph_view.py`) turns it into a self-contained vis-network HTML; a thin `@register_tool("cluster_graph")` wrapper exposes it; a minimal stdlib static server (`agent/graph_server.py`, launched by `app.py`) serves the artifact so the agent can return a clickable URL. No on-chain reads, no writes.

**Tech Stack:** Python ≥3.12, stdlib only for traversal/render/serve (json, http.server), pytest, ruff. vis-network is loaded in the browser from CDN (no Python dep). qwen-agent only for the `@register_tool` wrapper (CI-skipped via `importorskip`).

## Global Constraints

- Python ≥3.12; `from __future__ import annotations` at the top of every new module (these are NOT FastMCP tool modules, so it is safe — matches `actions.py`/`serialize.py`).
- ruff default rule set (E4/E7/E9/F): **imports at top of file (E402)**, **no unused imports (F401)**; keep lines ≤ 100 cols, 4-space indent. `ruff check src tests` must be clean.
- Pure modules (`memory/cluster.py`, `agent/graph_view.py`, `agent/graph_server.py`) MUST import without `qwen-agent` / `mcp` / `openai` (they run in CI). The `@register_tool` wrapper lives inside the existing `if register_tool is not None:` block in `agent/tools.py` and is CI-skipped.
- Read-only: the view performs NO on-chain reads and NO memory writes — it only calls `memory.recall(...)`.
- Pure functions never call the clock; `now`/`as_of` are injected by the caller (the agent stamps its own — see memory `anamnesis-native-tool-registration-test`).
- Edge type strings are exact: `DEPLOYED`, `RUGGED`, `WATCHLISTED`, `SAME_CLUSTER`, `FUNDED_BY`, `PROVIDES_LP`.
- Config is read at import time; new settings are `ANAMNESIS_`-namespaced with safe defaults.
- Commits: GPG-signed (`git commit -S`), conventional type, **zero AI attribution**.

---

### Task 1: `memory/cluster.py` — data model + `recall_cluster`

**Files:**
- Create: `src/anamnesis/memory/cluster.py`
- Test: `tests/test_cluster.py`

**Interfaces:**
- Consumes: `ForensicMemory.recall(entity_key, as_of=None)`; `Edge` fields (`id`, `src`, `dst`, `type`, `provenance.method`, `provenance.confidence`).
- Produces:
  - `ClusterNode(id:str, kind:str, flags:tuple[str,...])` — `kind` ∈ wallet|token|funding|pool; `flags` ⊆ (deployer, rugged, watchlisted), sorted.
  - `ClusterEdge(src:str, dst:str, rel:str, method:str, confidence:float)`.
  - `ClusterGraph(seed:str, nodes:tuple, edges:tuple, depth:int, truncated:bool, as_of:str|None=None)`.
  - `recall_cluster(memory, seed, *, depth=2, rel_types=None, max_nodes=60, max_edges=150, as_of=None) -> ClusterGraph` — bounded, cycle-safe, undirected BFS; infers node kind + flags.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cluster.py
from anamnesis.memory.cluster import recall_cluster
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.models import Provenance, make_edge
from anamnesis.memory.repository import InMemoryRepository


def _e(rel, src, dst, method="first_party", conf=0.9, at="2026-01-01"):
    return make_edge(rel, src, dst, valid_from=at, recorded_at=at,
                     provenance=Provenance("helius:getAsset", method, conf))


def _mem(*edges):
    m = ForensicMemory(InMemoryRepository())
    if edges:
        m.remember(list(edges), now="2026-01-01")
    return m


def test_reaches_deployed_tokens_with_kinds_and_flags():
    mem = _mem(_e("DEPLOYED", "dep", "tokA"), _e("RUGGED", "dep", "tokA"),
               _e("WATCHLISTED", "dep", "tokFresh", method="derived", conf=0.7))
    ids = {n.id: n for n in recall_cluster(mem, "dep", depth=1).nodes}
    assert set(ids) == {"dep", "tokA", "tokFresh"}
    assert ids["dep"].kind == "wallet" and "deployer" in ids["dep"].flags
    assert ids["tokA"].kind == "token" and "rugged" in ids["tokA"].flags
    assert "watchlisted" in ids["tokFresh"].flags


def test_depth_bounds_the_walk():
    mem = _mem(_e("SAME_CLUSTER", "dep", "peer"), _e("DEPLOYED", "peer", "tokP"))
    assert {n.id for n in recall_cluster(mem, "dep", depth=1).nodes} == {"dep", "peer"}
    assert {n.id for n in recall_cluster(mem, "dep", depth=2).nodes} == {"dep", "peer", "tokP"}


def test_undirected_reaches_funding_and_peers_with_kinds():
    mem = _mem(_e("FUNDED_BY", "dep", "cex:binance"), _e("SAME_CLUSTER", "dep", "peer"))
    ids = {n.id: n for n in recall_cluster(mem, "dep", depth=1).nodes}
    assert ids["cex:binance"].kind == "funding" and ids["peer"].kind == "wallet"


def test_rel_types_filter():
    mem = _mem(_e("DEPLOYED", "dep", "tokA"), _e("FUNDED_BY", "dep", "cex"))
    g = recall_cluster(mem, "dep", depth=1, rel_types=frozenset({"DEPLOYED"}))
    assert {n.id for n in g.nodes} == {"dep", "tokA"}
    assert all(e.rel == "DEPLOYED" for e in g.edges)


def test_dedups_and_is_cycle_safe():
    mem = _mem(_e("SAME_CLUSTER", "a", "b"), _e("SAME_CLUSTER", "b", "a"))
    g = recall_cluster(mem, "a", depth=3)
    assert {n.id for n in g.nodes} == {"a", "b"}
    assert len(g.edges) == len({(e.src, e.dst, e.rel) for e in g.edges})


def test_empty_seed_is_single_node():
    g = recall_cluster(_mem(), "ghost", depth=2)
    assert [n.id for n in g.nodes] == ["ghost"] and g.edges == () and g.truncated is False


def test_size_cap_sets_truncated():
    mem = _mem(*[_e("DEPLOYED", "hub", f"tok{i}") for i in range(20)])
    g = recall_cluster(mem, "hub", depth=1, max_nodes=5)
    assert g.truncated is True and len(g.nodes) <= 5


def test_as_of_excludes_later_edges():
    mem = ForensicMemory(InMemoryRepository())
    mem.remember([_e("DEPLOYED", "dep", "tokA", at="2026-01-01")], now="2026-01-01")
    mem.remember([_e("RUGGED", "dep", "tokA", at="2026-03-01")], now="2026-03-01")
    early = recall_cluster(mem, "dep", depth=1, as_of="2026-02-01")
    assert {(e.src, e.dst, e.rel) for e in early.edges} == {("dep", "tokA", "DEPLOYED")}
    assert early.as_of == "2026-02-01"
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/python -m pytest tests/test_cluster.py -q`
Expected: FAIL — `ModuleNotFoundError: anamnesis.memory.cluster`.

- [ ] **Step 3: Implement `memory/cluster.py`**

```python
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
```

- [ ] **Step 4: Run, verify pass + ruff**

Run: `.venv/bin/python -m pytest tests/test_cluster.py -q` → Expected: PASS (8 passed).
Run: `.venv/bin/ruff check src/anamnesis/memory/cluster.py tests/test_cluster.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/memory/cluster.py tests/test_cluster.py
git commit -S -m "feat: recall_cluster — bounded multi-hop memory traversal (B.2)"
```

---

### Task 2: `agent/graph_view.py` — `render_cluster_html`

**Files:**
- Create: `src/anamnesis/agent/graph_view.py`
- Test: `tests/test_graph_view.py`

**Interfaces:**
- Consumes: `ClusterGraph`, `ClusterNode`, `ClusterEdge` (Task 1).
- Produces: `render_cluster_html(cluster, *, generated_at:str|None=None) -> str` — a self-contained HTML page (vis-network CDN `<script>`, nodes/edges inlined as JSON, color by flag).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_graph_view.py
import json

from anamnesis.agent.graph_view import render_cluster_html
from anamnesis.memory.cluster import ClusterEdge, ClusterGraph, ClusterNode


def _graph():
    return ClusterGraph(
        seed="dep",
        nodes=(ClusterNode("dep", "wallet", ("deployer",)),
               ClusterNode("tokA", "token", ("rugged",)),
               ClusterNode("tokFresh", "token", ("watchlisted",))),
        edges=(ClusterEdge("dep", "tokA", "RUGGED", "first_party", 0.95),
               ClusterEdge("dep", "tokFresh", "WATCHLISTED", "derived", 0.7)),
        depth=1, truncated=False,
    )


def _dataset_payload(html, var):
    line = next(ln for ln in html.splitlines() if f"const {var} = new vis.DataSet(" in ln)
    return json.loads(line[line.index("(") + 1: line.rindex(")")])


def test_self_contained_and_embeds_nodes_and_edges():
    html = render_cluster_html(_graph())
    assert "vis-network" in html and "<script src=" in html and "new vis.Network" in html
    for nid in ("dep", "tokA", "tokFresh"):
        assert nid in html
    assert "RUGGED" in html and "WATCHLISTED" in html


def test_inlines_valid_json_datasets():
    html = render_cluster_html(_graph())
    assert {d["id"] for d in _dataset_payload(html, "nodes")} == {"dep", "tokA", "tokFresh"}
    assert len(_dataset_payload(html, "edges")) == 2


def test_colors_rugged_and_watchlisted_distinctly():
    html = render_cluster_html(_graph())
    assert "#e23b3b" in html and "#f0a020" in html  # rugged red, watchlisted amber


def test_includes_generated_at_when_given():
    assert "2026-06-27T10:00:00Z" in render_cluster_html(_graph(), generated_at="2026-06-27T10:00:00Z")
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/python -m pytest tests/test_graph_view.py -q`
Expected: FAIL — `ModuleNotFoundError: anamnesis.agent.graph_view`.

- [ ] **Step 3: Implement `agent/graph_view.py`**

```python
"""Render a ClusterGraph to a self-contained interactive HTML page (vis-network).

Pure string-building over stdlib json — no Python rendering dependency, no qwen-agent
import, so it runs in CI. The page loads vis-network from CDN and inlines the node/edge
data; nodes are colored by flag so rugged / watchlisted / deployer entities light up.
"""
from __future__ import annotations

import html as _html
import json

from ..memory.cluster import ClusterGraph

_VIS_CDN = "https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"

_RUGGED = "#e23b3b"       # red — a prior rug
_WATCHLISTED = "#f0a020"  # amber — flagged by B.1
_DEPLOYER = "#3b6fe2"     # blue — a deploying wallet (the hub)
_FUNDING = "#9b59b6"      # purple
_POOL = "#1abc9c"         # teal
_TOKEN = "#888888"        # grey — a plain token
_WALLET = "#cfcfcf"       # light grey — a plain wallet

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>__HEADING__</title>
<script src="__VIS_CDN__"></script>
<style>
  body { margin:0; font-family: system-ui, sans-serif; background:#0d1117; color:#e6edf3; }
  #h { padding:10px 14px; font-size:14px; border-bottom:1px solid #30363d; }
  #net { width:100vw; height:calc(100vh - 44px); }
  .legend { color:#9aa4af; font-size:12px; }
</style>
</head>
<body>
<div id="h"><strong>__HEADING__</strong>
  <span class="legend">— red=rugged · amber=watchlisted · blue=deployer · purple=funding · teal=pool</span></div>
<div id="net"></div>
<script>
  const nodes = new vis.DataSet(__NODES__);
  const edges = new vis.DataSet(__EDGES__);
  new vis.Network(document.getElementById("net"), {nodes: nodes, edges: edges}, {
    physics: {stabilization: true},
    nodes: {font: {color: "#e6edf3"}},
    edges: {arrows: "to", font: {size: 10, color: "#9aa4af"}, color: {color: "#5a6675"}}
  });
</script>
</body>
</html>
"""


def _node_color(node) -> str:
    if "rugged" in node.flags:
        return _RUGGED
    if "watchlisted" in node.flags:
        return _WATCHLISTED
    if "deployer" in node.flags:
        return _DEPLOYER
    return {"funding": _FUNDING, "pool": _POOL, "token": _TOKEN}.get(node.kind, _WALLET)


def _node_label(node) -> str:
    short = node.id if len(node.id) <= 12 else f"{node.id[:4]}…{node.id[-4:]}"
    return short + "".join(f" [{f}]" for f in node.flags)


def _default_heading(cluster: ClusterGraph) -> str:
    rugged = sum(1 for n in cluster.nodes if "rugged" in n.flags)
    watched = sum(1 for n in cluster.nodes if "watchlisted" in n.flags)
    extra = (f" (as of {cluster.as_of})" if cluster.as_of else "") + \
            (" — truncated" if cluster.truncated else "")
    return (f"Cluster around {cluster.seed}: {len(cluster.nodes)} entities, "
            f"{len(cluster.edges)} relations, {rugged} prior rug(s), {watched} watchlisted{extra}")


def render_cluster_html(cluster: ClusterGraph, *, generated_at: str | None = None) -> str:
    heading = _default_heading(cluster)
    if generated_at:
        heading += f" · generated {generated_at}"
    nodes = [{"id": n.id, "label": _node_label(n), "color": _node_color(n),
              "shape": "box" if n.kind == "token" else "dot",
              "title": f"{n.kind}{''.join(' · ' + f for f in n.flags)}\n{n.id}"}
             for n in cluster.nodes]
    edges = [{"from": e.src, "to": e.dst, "label": e.rel,
              "title": f"{e.rel} · method={e.method} · conf={e.confidence:.2f}"}
             for e in cluster.edges]
    return (
        _HTML_TEMPLATE
        .replace("__HEADING__", _html.escape(heading, quote=True))
        .replace("__VIS_CDN__", _VIS_CDN)
        .replace("__NODES__", json.dumps(nodes))
        .replace("__EDGES__", json.dumps(edges))
    )
```

- [ ] **Step 4: Run, verify pass + ruff**

Run: `.venv/bin/python -m pytest tests/test_graph_view.py -q` → PASS (4 passed).
Run: `.venv/bin/ruff check src/anamnesis/agent/graph_view.py tests/test_graph_view.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/agent/graph_view.py tests/test_graph_view.py
git commit -S -m "feat: render_cluster_html — self-contained vis-network graph (B.2)"
```

---

### Task 3: `agent/graph_view.py` — `write_cluster_html` + `cluster_graph_handler`

**Files:**
- Modify: `src/anamnesis/agent/graph_view.py` (append)
- Test: `tests/test_graph_view.py` (append)

**Interfaces:**
- Consumes: `render_cluster_html` (Task 2); `recall_cluster` (Task 1); `ForensicMemory`.
- Produces:
  - `write_cluster_html(cluster, out_dir, *, generated_at=None) -> str` (absolute file path).
  - `cluster_graph_handler(memory, seed, now, *, out_dir, base_url, depth=2, as_of=None) -> dict` → `{seed, node_count, edge_count, rugged, watchlisted, truncated, html_path, url, summary}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_graph_view.py` (add imports at the TOP of the file with the others):

```python
# add to the top imports:
from pathlib import Path

from anamnesis.agent.graph_view import cluster_graph_handler, write_cluster_html
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.models import Provenance, make_edge
from anamnesis.memory.repository import InMemoryRepository
```

```python
def _rugger_mem():
    m = ForensicMemory(InMemoryRepository())
    def e(rel, src, dst, method="first_party"):
        return make_edge(rel, src, dst, valid_from="2026-01-01", recorded_at="2026-01-01",
                         provenance=Provenance("helius:getAsset", method, 0.95))
    m.remember([e("DEPLOYED", "dep", "tokA"), e("RUGGED", "dep", "tokA"),
                e("WATCHLISTED", "dep", "tokFresh", "derived")], now="2026-01-01")
    return m


def test_write_cluster_html_creates_file(tmp_path):
    from anamnesis.memory.cluster import recall_cluster
    path = write_cluster_html(recall_cluster(_rugger_mem(), "dep"), str(tmp_path))
    assert path.endswith(".html") and Path(path).is_file()
    assert "new vis.Network" in Path(path).read_text(encoding="utf-8")


def test_cluster_graph_handler_summary_and_url(tmp_path):
    out = cluster_graph_handler(_rugger_mem(), "dep", "2026-06-27T10:00:00Z",
                                out_dir=str(tmp_path), base_url="http://localhost:7866")
    assert out["seed"] == "dep" and out["node_count"] == 3 and out["edge_count"] >= 2
    assert out["rugged"] == ["tokA"] and out["watchlisted"] == ["tokFresh"]
    assert out["truncated"] is False
    assert out["url"].startswith("http://localhost:7866/") and out["url"].endswith(".html")
    assert Path(out["html_path"]).is_file()
    assert "2026-06-27T10:00:00Z" in Path(out["html_path"]).read_text(encoding="utf-8")


def test_cluster_graph_handler_base_url_trailing_slash(tmp_path):
    out = cluster_graph_handler(_rugger_mem(), "dep", "n",
                                out_dir=str(tmp_path), base_url="http://h:7866/")
    assert "//" not in out["url"].split("://", 1)[1]  # no double slash after the scheme
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/python -m pytest tests/test_graph_view.py -q`
Expected: FAIL — `ImportError: cannot import name 'cluster_graph_handler'`.

- [ ] **Step 3: Implement (append to `agent/graph_view.py`)**

Add imports at the top (with the existing ones):

```python
import os

from ..memory.cluster import recall_cluster
from ..memory.graph import ForensicMemory
```

Append:

```python
def _filename(cluster: ClusterGraph) -> str:
    def slug(s: str) -> str:
        return "".join(c if c.isalnum() else "_" for c in s)[:24]
    asof = f"_asof_{slug(cluster.as_of)}" if cluster.as_of else ""
    return f"cluster_{slug(cluster.seed)}{asof}.html"


def write_cluster_html(cluster: ClusterGraph, out_dir: str, *, generated_at: str | None = None) -> str:
    """Render the cluster and write it to `out_dir` under a deterministic filename
    (re-rendering the same seed overwrites in place). Returns the absolute path."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, _filename(cluster))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_cluster_html(cluster, generated_at=generated_at))
    return os.path.abspath(path)


def cluster_graph_handler(
    memory: ForensicMemory, seed: str, now: str, *,
    out_dir: str, base_url: str, depth: int = 2, as_of: str | None = None,
) -> dict:
    """Traverse memory around `seed`, render the interactive graph to a file, and return a
    JSON-able summary + a clickable URL. Read-only: visualizes memory; no on-chain reads."""
    cluster = recall_cluster(memory, seed, depth=depth, as_of=as_of)
    path = write_cluster_html(cluster, out_dir, generated_at=now)
    rugged = sorted(n.id for n in cluster.nodes if "rugged" in n.flags)
    watchlisted = sorted(n.id for n in cluster.nodes if "watchlisted" in n.flags)
    url = base_url.rstrip("/") + "/" + os.path.basename(path)
    summary = (
        f"Rendered a {len(cluster.nodes)}-entity / {len(cluster.edges)}-relation cluster "
        f"around {seed}: {len(rugged)} prior rug(s), {len(watchlisted)} watchlisted"
        + (" (truncated — refine the seed)" if cluster.truncated else "")
    )
    return {
        "seed": seed, "node_count": len(cluster.nodes), "edge_count": len(cluster.edges),
        "rugged": rugged, "watchlisted": watchlisted, "truncated": cluster.truncated,
        "html_path": path, "url": url, "summary": summary,
    }
```

- [ ] **Step 4: Run, verify pass + ruff**

Run: `.venv/bin/python -m pytest tests/test_graph_view.py -q` → PASS (7 passed).
Run: `.venv/bin/ruff check src/anamnesis/agent/graph_view.py tests/test_graph_view.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/agent/graph_view.py tests/test_graph_view.py
git commit -S -m "feat: write_cluster_html + cluster_graph_handler (B.2 view handler)"
```

---

### Task 4: Wire `cluster_graph` into config, tools, agent, and prompts

**Files:**
- Modify: `src/anamnesis/config.py` (graphs settings)
- Modify: `src/anamnesis/agent/tools.py` (`@register_tool("cluster_graph")` wrapper + import)
- Modify: `src/anamnesis/agent/agent.py` (`NATIVE_TOOLS`)
- Modify: `src/anamnesis/agent/prompts.py` (one rule)
- Test: `tests/test_config.py` (append), `tests/test_agent_assembly.py` (pinned list), `tests/test_agent_tool_registration.py` (append)

**Interfaces:**
- Consumes: `cluster_graph_handler` (Task 3); existing `_memory()`, `_now()`, `_args()`, `config` in `tools.py`.
- Produces: registered tool `cluster_graph`; `config.GRAPHS_DIR`, `config.GRAPHS_PORT`, `config.GRAPHS_BASE_URL`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_graphs_config_defaults_present():
    from anamnesis import config
    assert config.GRAPHS_DIR
    assert isinstance(config.GRAPHS_PORT, int) and config.GRAPHS_PORT > 0
    assert config.GRAPHS_BASE_URL.startswith("http")
```

In `tests/test_agent_assembly.py`, update the pinned native-tool assertion:

```python
    assert fl[1:] == ["recall", "remember", "assess_risk", "watchlist_add", "draft_alert",
                      "list_pending_alerts", "cluster_graph"]
```

Append to `tests/test_agent_tool_registration.py`:

```python
def test_cluster_graph_tool_is_registered():
    assert "cluster_graph" in TOOL_REGISTRY
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_agent_assembly.py -q`
Expected: FAIL — `AttributeError: module 'anamnesis.config' has no attribute 'GRAPHS_DIR'` and the `fl[1:]` assertion mismatch.

- [ ] **Step 3a: Add config settings** — append to `src/anamnesis/config.py`:

```python
# Relationship-graph view (B.2). Where rendered cluster HTML is written, and the base URL the
# agent links to (a minimal static server over GRAPHS_DIR is launched by app.py).
GRAPHS_DIR = os.environ.get("ANAMNESIS_GRAPHS_DIR", "graphs")
GRAPHS_PORT = int(os.environ.get("ANAMNESIS_GRAPHS_PORT", "7866"))
GRAPHS_BASE_URL = os.environ.get("ANAMNESIS_GRAPHS_BASE_URL", f"http://localhost:{GRAPHS_PORT}")
```

- [ ] **Step 3b: Add the tool import + wrapper in `tools.py`**

Add to the top-level imports (near `from .actions import ...`):

```python
from .graph_view import cluster_graph_handler
```

Inside the `if register_tool is not None:` block, after `ListPendingAlertsTool`, add:

```python
    @register_tool("cluster_graph")
    class ClusterGraphTool(BaseTool):
        description = ("Render an interactive relationship-graph of everything the agent "
                       "REMEMBERS around a wallet or token — its tokens, prior rugs, watchlist "
                       "flags, cluster peers, and funding. Returns a summary + a link. "
                       "Read-only (visualizes memory; performs no on-chain reads).")
        parameters = [
            {"name": "seed", "type": "string", "required": True,
             "description": "The wallet or mint address to center the graph on."},
            {"name": "as_of", "type": "string", "required": False,
             "description": "Optional ISO timestamp for an as-of (time-travel) cluster view."},
        ]

        def call(self, params, **kwargs) -> str:
            a = _args(params)
            return json.dumps(cluster_graph_handler(
                _memory(), a["seed"], _now(),
                out_dir=config.GRAPHS_DIR, base_url=config.GRAPHS_BASE_URL,
                as_of=a.get("as_of"),
            ))
```

- [ ] **Step 3c: Add the tool name in `agent/agent.py`** — extend `NATIVE_TOOLS`:

```python
NATIVE_TOOLS = ["recall", "remember", "assess_risk", "watchlist_add", "draft_alert",
                "list_pending_alerts", "cluster_graph"]
```

- [ ] **Step 3d: Add one prompt rule in `agent/prompts.py`** — insert before the closing `This is forensic, provenance-grounded analysis, not financial advice.` line:

```python
6. SHOW THE CLUSTER. When the user asks who else is connected, to see the network, or to
   visualize a deployer's history, call `cluster_graph(seed)` to render the remembered
   relationship graph (rugs and watchlisted tokens light up) and share the returned link.

```

- [ ] **Step 4: Run, verify**

Run: `.venv/bin/python -m pytest -q` → PASS (registration test runs where qwen-agent is installed, else SKIPS; full pure suite green).
Run: `.venv/bin/ruff check src tests` → clean.
If qwen-agent is installed locally: `.venv/bin/python -m pytest tests/test_agent_tool_registration.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/config.py src/anamnesis/agent/tools.py src/anamnesis/agent/agent.py \
        src/anamnesis/agent/prompts.py tests/test_config.py tests/test_agent_assembly.py \
        tests/test_agent_tool_registration.py
git commit -S -m "feat: wire cluster_graph tool into the agent (config + tool + prompt)"
```

---

### Task 5: `agent/graph_server.py` + launch it from `app.py`

**Files:**
- Create: `src/anamnesis/agent/graph_server.py`
- Modify: `app.py` (start the static server before the WebUI)
- Test: `tests/test_graph_server.py`

**Interfaces:**
- Consumes: `config.GRAPHS_DIR`, `config.GRAPHS_PORT` (in `app.py`).
- Produces: `make_graph_server(directory:str, port:int) -> ThreadingHTTPServer` — bound but not started; serves `directory`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_graph_server.py
import urllib.request
from threading import Thread

from anamnesis.agent.graph_server import make_graph_server


def test_serves_files_from_directory(tmp_path):
    (tmp_path / "cluster_x.html").write_text("<html>hi</html>", encoding="utf-8")
    server = make_graph_server(str(tmp_path), 0)  # port 0 -> OS-assigned ephemeral port
    port = server.server_address[1]
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        body = urllib.request.urlopen(f"http://127.0.0.1:{port}/cluster_x.html", timeout=5).read()
        assert b"hi" in body
    finally:
        server.shutdown()
        server.server_close()


def test_creates_missing_directory(tmp_path):
    target = tmp_path / "graphs"
    server = make_graph_server(str(target), 0)
    try:
        assert target.is_dir()
    finally:
        server.server_close()
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/python -m pytest tests/test_graph_server.py -q`
Expected: FAIL — `ModuleNotFoundError: anamnesis.agent.graph_server`.

- [ ] **Step 3a: Implement `agent/graph_server.py`**

```python
"""A minimal static file server for rendered relationship-graph HTML (B.2).

Decoupled from the Qwen-Agent WebUI (which wraps Gradio and does not cleanly expose its
FastAPI app): app.py runs this in a daemon thread over config.GRAPHS_DIR so the agent's
cluster_graph links resolve. Stdlib-only (no qwen-agent), so it imports in CI.
"""
from __future__ import annotations

import functools
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


def make_graph_server(directory: str, port: int) -> ThreadingHTTPServer:
    """Build (but do not start) a threaded HTTP server serving `directory`.

    The directory is created if absent so the server binds cleanly before any graph is
    written. Call `.serve_forever()` (typically in a daemon thread) to run it; pass port=0
    for an OS-assigned port (used in tests)."""
    os.makedirs(directory, exist_ok=True)
    handler = functools.partial(SimpleHTTPRequestHandler, directory=directory)
    return ThreadingHTTPServer(("", port), handler)
```

- [ ] **Step 3b: Launch it from `app.py`** — add top-level imports and start the server in `main()`:

Add near the top (with `from anamnesis.agent.agent import build_agent`):

```python
from anamnesis import config
from anamnesis.agent.graph_server import make_graph_server
```

Replace `main()` with:

```python
def main() -> None:
    from threading import Thread

    from qwen_agent.gui import WebUI

    # Serve rendered relationship graphs so the agent's cluster_graph links resolve.
    server = make_graph_server(config.GRAPHS_DIR, config.GRAPHS_PORT)
    Thread(target=server.serve_forever, daemon=True).start()
    WebUI(build_agent(), chatbot_config=CHATBOT_CONFIG).run()
```

- [ ] **Step 4: Run, verify pass + ruff + full suite + app entrypoint**

Run: `.venv/bin/python -m pytest tests/test_graph_server.py tests/test_app_entrypoint.py -q` → PASS.
Run: `.venv/bin/python -m pytest -q` → PASS (full suite).
Run: `.venv/bin/ruff check src tests app.py` → clean.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/agent/graph_server.py app.py tests/test_graph_server.py
git commit -S -m "feat: minimal static graph server, launched beside the WebUI (B.2)"
```

---

## Final verification (after all tasks)

- [ ] `.venv/bin/python -m pytest -q` → all green (in-memory)
- [ ] `.venv/bin/python -m pytest -q --store=mongo` → all green (mongomock; unset `ANAMNESIS_MONGODB_URI` to force mongomock, or ensure the dev-Mongo tunnel is up)
- [ ] `.venv/bin/ruff check src tests app.py` → clean
- [ ] If qwen-agent is installed locally: `cluster_graph` resolves in `TOOL_REGISTRY` and a quick `cluster_graph_handler` smoke renders a real `.html`
- [ ] `git log --oneline main..HEAD` shows 5 focused, signed commits
- [ ] Open a PR `feat/b2-relationship-graph-view` → `main`; CI green; merge `--merge --delete-branch`.

## Spec coverage map

| Spec section | Task |
|---|---|
| D1 view-over-memory (read-only) | 1, 3 |
| D2 interactive vis-network HTML | 2 |
| D3 all-relations / depth / undirected / rel_types / as_of | 1 |
| D4 node kind + flag inference | 1 |
| D5 pure traversal + pure render + thin wrapper | 1, 2, 3, 4 |
| D6 minimal static-serve beside app.py | 5 |
| D7 size cap → truncated (no silent cap) | 1 |
| D8 CI-purity + injected clock + CI-skipped wrapper | all (pure modules; wrapper in the guarded block) |
| Tool surface + agent wiring + prompt | 4 |
| Config (ANAMNESIS_-namespaced) | 4 |
