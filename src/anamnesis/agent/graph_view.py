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
