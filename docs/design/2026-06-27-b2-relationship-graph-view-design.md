# B.2 — Relationship-graph view: `recall_cluster` + interactive HTML (design)

- **Date:** 2026-06-27
- **Status:** Approved — ready for implementation plan
- **Task:** SPEC Phase B — "relationship-graph view" (the visual half; the acts half shipped in **B.1**, PR#20)
- **Depends on:** `memory/graph.py` + `memory/repository.py` + `memory/models.py` (A.6 — `Edge`, `ForensicMemory.recall`, bi-temporal as-of); `agent/tools.py` + `agent/agent.py` (A.9 — native `@register_tool` wrappers, `NATIVE_TOOLS`, singletons); `config.py`; `app.py` (the Qwen-Agent WebUI launcher)

## Goal

Deliver the SPEC Phase-B demo beat — **"the graph lights up the cluster"** (`SPEC.md` §"Build phases"). Given a seed wallet/token, traverse the agent's compounding memory and render an **interactive relationship graph** in which a serial rugger's tokens, prior rugs, the freshly watchlisted token, cluster-peer wallets, and funding sources all light up — the visual payoff of the compounding-memory thesis.

**DoD (from SPEC):** a remembered repeat offender's cluster renders as a navigable graph that visibly connects the dots (the rug history is cited and the new token is flagged); inspectable from the chat surface.

This is a thin, **read-only view** over memory — purely additive, like B.1. It visualizes what memory already knows; it performs no on-chain reads and no writes.

## Decisions

### D1 — Scope: a view over memory, not an investigator

`cluster_graph` traverses and renders the **already-remembered** bi-temporal graph. It does NOT fetch new on-chain data — that is `assess_risk`'s job, and the edges those investigations write are exactly what the cluster then reflects. This keeps B.2 pure (no Helius/DEX), fast (one DB read path), and CI-testable end-to-end. Read-only: no graph editing or write-actions from the view.

### D2 — Render surface: a self-contained interactive HTML (vis-network)

The chat UI is Qwen-Agent's built-in Gradio WebUI (`qwen-agent[gui]`, no custom frontend — a deliberate SPEC choice). The graph is rendered as a **self-contained HTML page** using **vis-network** loaded from CDN, with the node/edge data inlined as JSON. Chosen over: structured-JSON-only (no actual "light up"), Mermaid (Gradio renders the source, not a diagram), and server-rendered Graphviz SVG (static, plus a `graphviz` system binary on ECS). vis-network gives pan/zoom/hover interactivity with **zero Python rendering dependency** — the render is pure string-building over stdlib `json`.

*Trade-off:* the CDN `<script>` means the page needs internet to render. Acceptable — the demo/host machine is online; vendoring the (large) JS is rejected as bloat (avoid Israf).

### D3 — Traversal: all forensic relations, depth 2, undirected walk, size-bounded

`recall_cluster` walks **every** edge type (`DEPLOYED`, `RUGGED`, `WATCHLISTED`, `SAME_CLUSTER`, `FUNDED_BY`, `PROVIDES_LP`) from the seed, treating edges as **undirected** for the walk (so a deployer reaches its tokens, its cluster peers, and their tokens) while **preserving direction** in the render. Default `depth=2`. `rel_types` stays a filterable parameter (default = all) so a tighter view is one argument away. `as_of` is threaded through `recall` for the bi-temporal "cluster as it was known then" view — near-free and on-thesis.

The richer all-relations scope (over the B.1 forward contract's tentative `[SAME_CLUSTER, FUNDED_BY]`) is what surfaces the deployer→tokens→rug receipts that ARE the demo.

### D4 — Node kind + flags inferred from incident edges (no nodes collection)

Memory stores **edges**; nodes are implicit in `src`/`dst`. A node's `kind` and `flags` are inferred from the edges touching it:

- **kind:** `dst` of `DEPLOYED`/`RUGGED`/`WATCHLISTED` → `token`; `dst` of `FUNDED_BY` → `funding`; `dst` of `PROVIDES_LP` → `pool`; `src` of any wallet-edge and both `SAME_CLUSTER` endpoints → `wallet`. Ambiguous/none → `wallet` (the common case) — recorded as a small, documented precedence rule.
- **flags** (⊆ `{rugged, watchlisted, deployer}`) — what makes a node "light up": `rugged` = is `dst` of a `RUGGED` edge; `watchlisted` = is `dst` of a `WATCHLISTED` edge (B.1); `deployer` = is `src` of a `DEPLOYED` edge.

A node accumulates flags across all its incident edges (a token can be both `rugged` and `watchlisted`).

### D5 — Structure: pure traversal + pure render + thin wrapper (the B.1 pattern)

- `memory/cluster.py` — pure BFS traversal: `ClusterNode`, `ClusterEdge`, `ClusterGraph`, `recall_cluster`.
- `agent/graph_view.py` — pure presentation: `render_cluster_html`, `write_cluster_html`, and `cluster_graph_handler` (ties traversal → render → summary). No qwen-agent import → runs in CI.
- `agent/tools.py` — a `@register_tool("cluster_graph")` wrapper inside the existing `if register_tool is not None:` block; needs only `_memory()` + the configured graphs dir/URL + `_now()` (**no Helius/DEX** — simpler than `assess_risk`).

### D6 — Serving: a minimal standalone static file server beside `app.py`

To make the generated `.html` clickable inside the Gradio demo, `app.py` launches a tiny `http.server`-based static file server (daemon thread) over the graphs directory, **decoupled from qwen-agent's WebUI internals** (which wrap Gradio and don't cleanly expose their FastAPI app). The handler writes the file and returns a `url` built from `config.GRAPHS_BASE_URL`; the agent surfaces that link. For the local/video demo, the filesystem `html_path` (or `file://`) also works. The pure handler takes `out_dir` + `base_url` injected, so it stays CI-testable; only the server launch (in `app.py`, an untested entrypoint) is runtime-coupled.

### D7 — Bounding: size-capped, never silently truncated

A hub wallet could fan out to a huge subgraph (cf. the Helius RPC-storm lesson). `recall_cluster` caps at `max_nodes` (default 60) and `max_edges` (default 150); on hitting a cap it stops expanding and sets `truncated=True`, which the handler's summary states explicitly ("showing 60 of N+; refine the seed"). No silent cap. A `visited` set guards cycles/self-loops.

### D8 — Purity & CI-safety

`memory/cluster.py` and `agent/graph_view.py` import without `qwen-agent`/`mcp`/`openai` (they run in CI — see memory `anamnesis-ci-installs-fixed-dep-subset`). Pure functions never call the clock; `now`/`as_of` are injected by the caller (the agent stamps its own). The `@register_tool` wrapper stays CI-skipped via `importorskip` (memory `anamnesis-native-tool-registration-test`). No `from __future__ import annotations` concern (these are not FastMCP modules; `from __future__` is used, consistent with `actions.py`/`serialize.py`).

## Data model

```python
# memory/cluster.py
@dataclass(frozen=True)
class ClusterNode:
    id: str
    kind: str            # "wallet" | "token" | "funding" | "pool"
    flags: tuple[str, ...]  # subset of ("rugged", "watchlisted", "deployer"), sorted

@dataclass(frozen=True)
class ClusterEdge:
    src: str
    dst: str
    rel: str             # edge.type
    method: str          # provenance.method (for the hover tooltip)
    confidence: float    # provenance.confidence

@dataclass(frozen=True)
class ClusterGraph:
    seed: str
    nodes: tuple[ClusterNode, ...]
    edges: tuple[ClusterEdge, ...]
    depth: int
    truncated: bool
    as_of: str | None = None
```

## Components & signatures

```python
# memory/cluster.py  (pure; CI-tested)
def recall_cluster(
    memory: ForensicMemory, seed: str, *,
    depth: int = 2, rel_types: frozenset[str] | None = None,
    max_nodes: int = 60, max_edges: int = 150, as_of: str | None = None,
) -> ClusterGraph
    # BFS over memory.recall(node, as_of); undirected walk, rel-filtered, cycle-safe,
    # size-bounded (-> truncated). Infers node kind + flags (D4).

# agent/graph_view.py  (pure; CI-tested)
def render_cluster_html(cluster: ClusterGraph, *, title: str | None = None) -> str
    # self-contained HTML: vis-network CDN <script>, nodes/edges inlined as JSON,
    # color by flag (rugged=red, watchlisted=amber, deployer=blue, funding=purple,
    # pool=teal, plain=grey), edge label = rel, tooltip = "method conf".
def write_cluster_html(cluster: ClusterGraph, out_dir: str) -> str   # -> absolute file path
def cluster_graph_handler(
    memory: ForensicMemory, seed: str, now: str, *,
    out_dir: str, base_url: str, depth: int = 2, as_of: str | None = None,
) -> dict
    # -> {seed, node_count, edge_count, rugged, watchlisted, truncated,
    #     html_path, url, summary}
```

## Tool surface (native `@register_tool`, mirroring existing handlers)

| Tool | Behaviour |
|------|-----------|
| `cluster_graph` | Traverse the remembered relationship graph around a wallet/mint and render an interactive HTML view; returns a one-line summary + a clickable URL. Read-only; visualizes memory only. |

Wired into `agent.py::NATIVE_TOOLS` (→ `build_function_list`). Backed by the pure `cluster_graph_handler`; the wrapper injects `_memory()`, `config.GRAPHS_DIR`, `config.GRAPHS_BASE_URL`, and `_now()`. The system prompt (`prompts.py`) gets one line so the agent offers the graph when a user asks "show / who else / connections".

## Config additions (`config.py`)

- `GRAPHS_DIR` — where rendered HTML is written (default `./graphs`, created if absent).
- `GRAPHS_PORT` / `GRAPHS_BASE_URL` — the static server's port and the base URL the handler builds links from (defaults `7866` / `http://localhost:7866`). Env-overridable for ECS (`ANAMNESIS_` namespaced, per the project secret convention).

## Testing

Pure unit tests, CI-runnable (no qwen-agent/mcp/openai; no DB beyond the in-memory repo):

- **recall_cluster:** depth bound (depth=1 vs 2 reach); `rel_types` filter; undirected reach (deployer → cluster-peer → peer's token); edge/node dedup; **size cap → `truncated=True`**; node-kind inference (token/wallet/funding/pool); flag inference (rugged/watchlisted/deployer, accumulated); cycle safety; **`as_of`** view (a node added later is absent from an earlier as-of cluster); empty/unknown seed → single-node graph.
- **render_cluster_html:** every node id + edge appears; correct color/group for rugged + watchlisted; self-contained (contains the vis-network `<script src>` and a valid `JSON`-parsable payload); title reflects seed + counts + as-of.
- **cluster_graph_handler:** summary dict shape + counts (incl. rugged/watchlisted/truncated); writes a file under `out_dir`; `url` built from `base_url`.
- **Tool registration** (`@register_tool`): CI-skipped via `importorskip`; `cluster_graph` in `TOOL_REGISTRY`; `NATIVE_TOOLS` assertion in `test_agent_assembly.py` updated.

## File plan

**New:**
- `src/anamnesis/memory/cluster.py` — `ClusterNode`, `ClusterEdge`, `ClusterGraph`, `recall_cluster`.
- `src/anamnesis/agent/graph_view.py` — `render_cluster_html`, `write_cluster_html`, `cluster_graph_handler`.
- `tests/test_cluster.py`, `tests/test_graph_view.py`.

**Modified:**
- `src/anamnesis/agent/tools.py` — `@register_tool("cluster_graph")` wrapper + a `_graphs_dir()`/config accessor.
- `src/anamnesis/agent/agent.py` — add `"cluster_graph"` to `NATIVE_TOOLS`.
- `src/anamnesis/agent/prompts.py` — one line so the agent offers the graph view.
- `src/anamnesis/config.py` — `GRAPHS_DIR`, `GRAPHS_PORT`, `GRAPHS_BASE_URL`.
- `app.py` — launch the minimal static file server (daemon thread) over `GRAPHS_DIR`.
- `tests/test_agent_assembly.py` — extend the pinned `NATIVE_TOOLS` assertion.

## Out of scope (B.2) / forward contract

- **Live on-chain cluster expansion** — the view reflects memory; expanding via fresh RPC reads is an `assess_risk`/investigation concern, not the view's.
- **Hosted serving hardening** (TLS, auth, a real CDN for the artifacts) — A.10/deploy; B.2 ships a minimal static server sufficient for the demo.
- **Graph editing / write-actions** from the view; **bespoke design system / custom Gradio frontend** (SPEC non-goal).
- **Vendored vis-network** (offline rendering) — deferred unless an air-gapped demo is required.

## References

- `SPEC.md` §"Build phases" (Phase B — "relationship-graph view … graph lights up the cluster"), §Architecture ("thin UI + relationship-graph view").
- Prior art for structure: `docs/design/2026-06-27-b1-memoryagent-acts-design.md` (pure-core + thin-wrapper, injected clock, CI-skip), `docs/design/2026-06-24-a9-agent-assembly-design.md` (WebUI/`app.py`, `NATIVE_TOOLS`).
- Memories: `anamnesis-native-tool-registration-test`, `anamnesis-ruff-default-ruleset`, `anamnesis-ci-installs-fixed-dep-subset`, `anamnesis-helius-key-leak-and-rpc-fanout` (bounding lesson).
