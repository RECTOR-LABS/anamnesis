import json
from pathlib import Path

from anamnesis.agent.graph_view import (
    cluster_graph_handler,
    render_cluster_html,
    write_cluster_html,
)
from anamnesis.memory.cluster import ClusterEdge, ClusterGraph, ClusterNode, recall_cluster
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.models import Provenance, make_edge
from anamnesis.memory.repository import InMemoryRepository


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
    html = render_cluster_html(_graph(), generated_at="2026-06-27T10:00:00Z")
    assert "2026-06-27T10:00:00Z" in html


def _rugger_mem():
    m = ForensicMemory(InMemoryRepository())

    def e(rel, src, dst, method="first_party"):
        return make_edge(rel, src, dst, valid_from="2026-01-01", recorded_at="2026-01-01",
                         provenance=Provenance("helius:getAsset", method, 0.95))

    m.remember([e("DEPLOYED", "dep", "tokA"), e("RUGGED", "dep", "tokA"),
                e("WATCHLISTED", "dep", "tokFresh", "derived")], now="2026-01-01")
    return m


def test_write_cluster_html_creates_file(tmp_path):
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
