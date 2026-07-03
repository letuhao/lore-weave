"""A4 — schema-component usage counts (orphan-guard) over the derived graph.

Pure-logic unit tests for `count_component_usage`: node_kind/edge_type run a
Cypher count (stubbed), fact_type/vocab_value/unknown return None (not counted).
The live Neo4j query is exercised by the endpoint at runtime, not here.
"""
from __future__ import annotations

import pytest

from app.db.neo4j_repos import schema_usage


class _FakeResult:
    def __init__(self, total: int | None) -> None:
        self._total = total

    async def single(self):
        return {"total": self._total} if self._total is not None else None


def _stub_run_read(monkeypatch, total, captured):
    async def fake_run_read(session, cypher, **params):
        captured["cypher"] = cypher
        captured["params"] = params
        return _FakeResult(total)

    monkeypatch.setattr(schema_usage, "run_read", fake_run_read)


@pytest.mark.asyncio
async def test_node_kind_counts_entities(monkeypatch):
    captured: dict = {}
    _stub_run_read(monkeypatch, 5, captured)
    n = await schema_usage.count_component_usage(
        None, user_id="u1", project_id="p1", node_type="node_kind", code="character"
    )
    assert n == 5
    assert "Entity" in captured["cypher"] and "e.kind" in captured["cypher"]
    assert captured["params"] == {"user_id": "u1", "project_id": "p1", "code": "character"}


@pytest.mark.asyncio
async def test_edge_type_counts_live_relations(monkeypatch):
    captured: dict = {}
    _stub_run_read(monkeypatch, 12, captured)
    n = await schema_usage.count_component_usage(
        None, user_id="u1", project_id="p1", node_type="edge_type", code="LOVER_OF"
    )
    assert n == 12
    # scoped by subject project + live-only (valid_until IS NULL)
    assert "RELATES_TO" in captured["cypher"] and "r.valid_until IS NULL" in captured["cypher"]
    assert "s.project_id" in captured["cypher"]


@pytest.mark.asyncio
async def test_no_rows_is_zero(monkeypatch):
    _stub_run_read(monkeypatch, None, {})
    n = await schema_usage.count_component_usage(
        None, user_id="u1", project_id="p1", node_type="node_kind", code="ghost"
    )
    assert n == 0  # single() -> None => 0, NOT None (node_kind IS counted)


class _FakeAsyncRows:
    """Async-iterable stand-in for a Neo4j multi-row result (`async for rec in …`)."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def __aiter__(self):
        self._it = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


@pytest.mark.asyncio
async def test_usage_summary_groups_by_code(monkeypatch):
    async def fake_run_read(session, cypher, **params):
        if "e.kind AS code" in cypher:
            return _FakeAsyncRows([{"code": "character", "n": 5}, {"code": "location", "n": 2}])
        return _FakeAsyncRows([{"code": "LOVER_OF", "n": 3}, {"code": None, "n": 9}])

    monkeypatch.setattr(schema_usage, "run_read", fake_run_read)
    out = await schema_usage.usage_summary(None, user_id="u", project_id="p")
    assert out == {
        "node_kind": {"character": 5, "location": 2},
        "edge_type": {"LOVER_OF": 3},  # the None-code row is dropped
    }


@pytest.mark.asyncio
async def test_observed_components_kinds_and_edges(monkeypatch):
    async def fake_run_read(session, cypher, **params):
        if "e.kind AS code" in cypher:
            return _FakeAsyncRows([{"code": "character", "n": 8}, {"code": None, "n": 1}])
        return _FakeAsyncRows([
            {"code": "MENTORS", "n": 4, "source_kinds": ["character", None], "target_kinds": ["character"]},
        ])

    monkeypatch.setattr(schema_usage, "run_read", fake_run_read)
    out = await schema_usage.observed_components(None, user_id="u", project_id="p")
    assert out["node_kinds"] == [{"code": "character", "count": 8}]  # None dropped
    assert out["edge_types"] == [{
        "code": "MENTORS", "count": 4,
        "source_kinds": ["character"],  # None filtered out
        "target_kinds": ["character"],
    }]


@pytest.mark.asyncio
@pytest.mark.parametrize("node_type", ["fact_type", "vocab_value", "vocab_set", "bogus"])
async def test_uncounted_types_return_none(monkeypatch, node_type):
    # These never hit Cypher — run_read would raise if called.
    async def boom(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("run_read should not run for an uncounted type")

    monkeypatch.setattr(schema_usage, "run_read", boom)
    n = await schema_usage.count_component_usage(
        None, user_id="u1", project_id="p1", node_type=node_type, code="x"
    )
    assert n is None  # caller distinguishes "not counted" from "0 uses"
