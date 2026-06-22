from anamnesis.memory.models import Edge, Provenance, make_edge_id
from anamnesis.memory.repository import InMemoryRepository


def _edge(**kw) -> Edge:
    base = dict(
        type="DEPLOYED", src="wallet1", dst="mintA",
        valid_from="2026-01-01", valid_to=None, recorded_at="2026-06-01",
        superseded_at=None, provenance=Provenance("helius:getAsset", "first_party", 0.95),
    )
    base.update(kw)
    base["id"] = make_edge_id(base["type"], base["src"], base["dst"], base["recorded_at"])
    return Edge(**base)


def test_find_by_either_endpoint():
    repo = InMemoryRepository()
    repo.upsert_edge(_edge())
    assert len(repo.find_edges("wallet1")) == 1
    assert len(repo.find_edges("mintA")) == 1
    assert repo.find_edges("nobody") == []


def test_current_view_excludes_superseded():
    repo = InMemoryRepository()
    e = _edge()
    e.superseded_at = "2026-06-05"
    repo.upsert_edge(e)
    assert repo.find_edges("wallet1") == []  # superseded -> hidden in current view
    assert len(repo.find_edges("wallet1", as_of="2026-06-03")) == 1  # but known as of then
