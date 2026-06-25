"""T4.1 — unit tests for the Flywheel net-new delta helper.

Locks: exact counts per type, the capped named sample, the per-kind tagging of
new_items, the empty/None-record path, and that items lacking an id are dropped.
The Cypher is exercised against the real graph in the live-smoke (created_job_id
stamp → counts); here we mock run_read to pin the aggregation/shaping logic.
"""
from __future__ import annotations

import pytest

from app.db.neo4j_repos import flywheel as fw


class _FakeResult:
    def __init__(self, record):
        self._record = record

    async def single(self):
        return self._record


@pytest.mark.asyncio
async def test_aggregates_counts_and_tags_items_per_kind(monkeypatch):
    # entities, then events, then relations — the call order in get_flywheel_delta.
    records = [
        {"total": 3, "items": [{"id": "e1", "name": "Kael"}, {"id": "e2", "name": "Mira"}]},
        {"total": 1, "items": [{"id": "v1", "name": "The Duel at Dawn"}]},
        {"total": 2, "items": [{"id": "r1", "name": "Kael → ALLY_OF → Mira"}]},
    ]
    seen_params: list[dict] = []

    async def fake_run_read(session, cypher, **params):
        seen_params.append(params)
        return _FakeResult(records[len(seen_params) - 1])

    monkeypatch.setattr(fw, "run_read", fake_run_read)

    delta = await fw.get_flywheel_delta(session=object(), job_id="job-123", user_id="u-1")

    assert delta.entities_added == 3
    assert delta.events_added == 1
    assert delta.relations_added == 2
    # every query is scoped by BOTH job_id and user_id (tenant safety + attribution)
    assert all(p.get("job_id") == "job-123" and p.get("user_id") == "u-1" for p in seen_params)
    # new_items: 2 entities + 1 event + 1 relation, tagged by kind in that order
    kinds = [i.kind for i in delta.new_items]
    assert kinds == ["entity", "entity", "event", "relation"]
    assert delta.new_items[0].name == "Kael"
    assert "→" in delta.new_items[-1].name  # relation rendered subj → pred → obj


@pytest.mark.asyncio
async def test_caps_named_sample_per_type_but_counts_stay_exact(monkeypatch):
    big = {"total": 50, "items": [{"id": f"e{i}", "name": f"E{i}"} for i in range(50)]}
    empty = {"total": 0, "items": []}
    records = [big, empty, empty]

    async def fake_run_read(session, cypher, **params):
        fake_run_read.n = getattr(fake_run_read, "n", 0) + 1
        return _FakeResult(records[fake_run_read.n - 1])

    monkeypatch.setattr(fw, "run_read", fake_run_read)

    delta = await fw.get_flywheel_delta(
        session=object(), job_id="j", user_id="u", limit_per_type=6,
    )
    assert delta.entities_added == 50  # exact
    assert len([i for i in delta.new_items if i.kind == "entity"]) == 6  # capped


@pytest.mark.asyncio
async def test_none_record_and_idless_items(monkeypatch):
    records = [
        None,  # entities: no row
        {"total": 2, "items": [{"id": "v1", "name": "ok"}, {"id": None, "name": "drop me"}]},
        {"total": 0, "items": []},
    ]

    async def fake_run_read(session, cypher, **params):
        fake_run_read.n = getattr(fake_run_read, "n", 0) + 1
        return _FakeResult(records[fake_run_read.n - 1])

    monkeypatch.setattr(fw, "run_read", fake_run_read)

    delta = await fw.get_flywheel_delta(session=object(), job_id="j", user_id="u")
    assert delta.entities_added == 0  # None record → zero
    assert delta.events_added == 2
    # the id-less event item is filtered out of new_items
    assert [i.id for i in delta.new_items if i.kind == "event"] == ["v1"]
