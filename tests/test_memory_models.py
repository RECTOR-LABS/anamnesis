from anamnesis.memory.models import Edge, Provenance, make_edge_id


def _edge(**kw) -> Edge:
    base = dict(
        type="DEPLOYED", src="wallet1", dst="mintA",
        valid_from="2026-01-01", valid_to=None, recorded_at="2026-06-01",
        superseded_at=None, provenance=Provenance("helius:getAsset", "first_party", 0.95),
    )
    base.update(kw)
    base["id"] = make_edge_id(base["type"], base["src"], base["dst"], base["recorded_at"])
    return Edge(**base)


def test_find_by_either_endpoint(repo):
    repo.upsert_edge(_edge())
    assert len(repo.find_edges("wallet1")) == 1
    assert len(repo.find_edges("mintA")) == 1
    assert repo.find_edges("nobody") == []


def test_current_view_excludes_superseded(repo):
    e = _edge()
    e.superseded_at = "2026-06-05"
    repo.upsert_edge(e)
    assert repo.find_edges("wallet1") == []  # superseded -> hidden in current view
    assert len(repo.find_edges("wallet1", as_of="2026-06-03")) == 1  # but known as of then


def test_as_of_time_travel_returns_belief_at_that_time(repo):
    # Recorded 06-01, superseded 06-05: invisible before it was recorded and once
    # superseded; visible only across the window it was the current belief.
    e = _edge(recorded_at="2026-06-01")
    e.superseded_at = "2026-06-05"
    repo.upsert_edge(e)
    assert repo.find_edges("wallet1", as_of="2026-05-31") == []      # not yet recorded
    assert len(repo.find_edges("wallet1", as_of="2026-06-01")) == 1  # recorded that day
    assert len(repo.find_edges("wallet1", as_of="2026-06-04")) == 1  # still believed
    assert repo.find_edges("wallet1", as_of="2026-06-05") == []      # superseded that day
