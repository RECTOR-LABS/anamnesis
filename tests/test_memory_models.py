from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.models import Edge, Provenance, make_edge, make_edge_id


def _edge(**kw) -> Edge:
    base = dict(
        type="DEPLOYED", src="wallet1", dst="mintA",
        valid_from="2026-01-01", valid_to=None, recorded_at="2026-06-01",
        superseded_at=None, provenance=Provenance("helius:getAsset", "first_party", 0.95),
    )
    base.update(kw)
    base["id"] = make_edge_id(
        base["type"], base["src"], base["dst"], base["recorded_at"],
        base["provenance"].method, base["provenance"].source,
    )
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


def test_find_edges_returns_deterministic_recorded_at_order(repo):
    # Both backends must agree on sequence, not just membership: results come back
    # in a stable (recorded_at, id) order regardless of insertion order.
    repo.upsert_edge(_edge(type="DEPLOYED", recorded_at="2026-03-01"))
    repo.upsert_edge(_edge(type="RUGGED", recorded_at="2026-01-15"))
    repo.upsert_edge(_edge(type="FUNDED_BY", recorded_at="2026-02-01"))
    assert [e.recorded_at for e in repo.find_edges("wallet1")] == [
        "2026-01-15", "2026-02-01", "2026-03-01",
    ]


def test_as_of_date_includes_a_datetime_recorded_earlier_that_day(repo):
    # B-5: recorded_at may be a full datetime (e.g. Helius creation_time) while a caller
    # queries with a bare date. A fact recorded at 12:34 on 2026-06-01 MUST be visible at
    # as_of="2026-06-01"; a naive lexicographic compare drops it (the bare date is a
    # prefix of the datetime, so it sorts FIRST and recorded_at <= as_of is false). The
    # as-of bound must be normalized to the END of the day so any same-day record counts.
    repo.upsert_edge(_edge(recorded_at="2026-06-01T12:34:56+00:00"))
    assert len(repo.find_edges("wallet1", as_of="2026-06-01")) == 1   # known that day
    assert repo.find_edges("wallet1", as_of="2026-05-31") == []        # before it existed


def test_as_of_date_excludes_a_fact_superseded_earlier_that_day(repo):
    # B-5 (supersession side): a datetime superseded_at vs a bare-date as_of. A belief
    # superseded at 08:00 on 2026-06-05 must NOT appear in the as_of="2026-06-05" view —
    # the same lexicographic prefix effect wrongly KEEPS it (datetime sorts after the
    # bare-date bound, so superseded_at <= as_of is false).
    repo.upsert_edge(_edge(recorded_at="2026-06-01", superseded_at="2026-06-05T08:00:00+00:00"))
    assert repo.find_edges("wallet1", as_of="2026-06-05") == []        # superseded by then
    assert len(repo.find_edges("wallet1", as_of="2026-06-04")) == 1    # still current the day before


def test_make_edge_canonicalizes_every_stored_timestamp():
    # B-5 (write side): make_edge is the canonical write path — it normalizes every stored
    # temporal field to one fixed-width ISO-8601 UTC instant regardless of the writer's
    # input granularity, so the as-of compare in find_edges is sound by construction. A
    # bare date is the START of that day.
    e = make_edge("RUGGED", "w", "t", valid_from="2026-06-01", recorded_at="2026-06-01",
                  provenance=Provenance("helius:getAsset", "first_party", 0.95))
    assert e.recorded_at == "2026-06-01T00:00:00.000000+00:00"
    assert e.valid_from == "2026-06-01T00:00:00.000000+00:00"


def test_make_edge_normalizes_offset_so_as_of_uses_true_instant(repo):
    # B-5: a recorded_at with a non-UTC offset is canonicalized to UTC on write, so the
    # as-of compare reflects the TRUE instant, not the wall-clock string. 18:00+07:00 is
    # 11:00Z — visible at as_of 12:00Z; an un-normalized "18" would sort past "12" and drop
    # (the leak the code-review caught: stored offsets/`Z` defeat the read-only fix).
    mem = ForensicMemory(repo)
    mem.remember([make_edge("RUGGED", "w", "t", valid_from="2026-06-01",
                            recorded_at="2026-06-01T18:00:00+07:00",
                            provenance=Provenance("helius:getAsset", "first_party", 0.95))],
                 now="2026-06-01T18:00:00+07:00")
    assert len(mem.recall("w", as_of="2026-06-01T12:00:00+00:00")) == 1   # 11:00Z <= 12:00Z
    assert mem.recall("w", as_of="2026-06-01T10:00:00+00:00") == []        # 11:00Z > 10:00Z
