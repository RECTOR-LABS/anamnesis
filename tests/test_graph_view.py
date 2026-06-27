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
    html = render_cluster_html(_graph(), generated_at="2026-06-27T10:00:00Z")
    assert "2026-06-27T10:00:00Z" in html
