"""D-FROM-GLOSSARY-REPORTS-SUCCESS-HAVING-CREATED-NOTHING.

Measured 2026-08-26, batch c-kgedge3. The model called kg_add_nodes mode=from_glossary with
entity_ids=["Mira Solene", "Aldric Vane"] — NAMES, where the argument takes glossary entity
UUIDs — and the tool answered:

    ok: true, nodes: [], entities_seen: 0, nodes_created: 0, nodes_existing: 0

with the activity strip recording "Did kg_add_nodes". The model's next move assumed two nodes
existed. `entities_seen: 0` is the tool's own evidence that the argument matched nothing — it
was IN the payload and nothing acted on it.

The refusal is NARROW on purpose. Omitting entity_ids means "the whole active glossary", and a
book whose glossary is genuinely empty is a legitimate no-op rather than an error — and that is
also the path measured WORKING in c-kgedge4 (entities_seen 2, both nodes created, 5 of 5 runs).
Refusing on a bare zero would have broken the one route that succeeds, which is why the
predicate is "the caller NAMED ids and none of them matched".
"""
from __future__ import annotations

import inspect

import pytest

from app.tools import graph_schema_tools as gst

SRC = inspect.getsource(gst._handle_kg_project_entities_to_nodes)
ARGS_SRC = inspect.getsource(gst.KgAddNodesArgs) if hasattr(gst, "KgAddNodesArgs") else ""


def test_a_named_id_that_matches_nothing_is_refused():
    assert "res.seen == 0" in SRC, "a zero-match projection still reports success"
    assert "entity_ids and res.seen == 0" in SRC, (
        "the refusal is not gated on the caller having NAMED ids — it would fire on an empty "
        "glossary, which is a legitimate no-op and the path that works"
    )


def test_the_refusal_says_the_graph_is_UNCHANGED():
    """The whole harm was a caller believing nodes now exist."""
    at = SRC.index("res.seen == 0")
    msg = SRC[at:at + 900]
    assert "unchanged" in msg, "the refusal does not say nothing was written"


def test_the_refusal_names_the_id_family_and_its_supplier():
    at = SRC.index("res.seen == 0")
    msg = SRC[at:at + 900]
    assert "UUID" in msg, "the refusal does not say what an entity_id IS"
    assert "not names" in msg, "the refusal does not name the mistake that was actually made"
    assert "glossary_search" in msg, "the refusal names no supplier for a real id"
    assert "omit" in msg.lower(), "the refusal does not offer the easier route"


def test_a_PARTIAL_match_is_reported_too():
    """Naming five ids and matching three is the same defect in miniature: a cheerful success
    that never mentions the two which do not exist."""
    assert "0 < res.seen < len(entity_ids)" in SRC, (
        "a partial match is still reported as a complete projection"
    )


def test_the_empty_glossary_path_is_UNTOUCHED():
    """PRECISION / RECALL. The omit-entity_ids route is the one measured working end to end
    (c-kgedge4, 5/5). It must still return a payload, not a refusal."""
    at = SRC.index("res.seen == 0")
    guard = SRC[SRC.index("if entity_ids and"):at + 40]
    assert guard.startswith("if entity_ids and"), guard
    # and the success payload is still built unconditionally below the guard
    assert 'out: dict = {' in SRC[at:]
    assert '"entities_seen": res.seen' in SRC[at:]


def test_the_argument_says_what_it_takes():
    """The description read 'optional specific glossary entity ids' — never that they are
    UUIDs, nor where one comes from, so a NAME is the obvious thing to pass."""
    import pathlib

    server_src = pathlib.Path(inspect.getfile(gst)).parents[1].joinpath("mcp", "server.py")
    text = server_src.read_text(encoding="utf-8")
    at = text.index("mode=from_glossary: OMIT this")
    desc = text[at:at + 400]
    assert "UUID" in desc
    assert "not names" in desc
    assert "glossary_search" in desc


@pytest.mark.parametrize("seen,named,refuses", [
    (0, 2, True),    # the measured defect: named ids, nothing matched
    (0, 0, False),   # empty glossary, no ids named — a legitimate no-op
    (2, 2, False),   # the working path
    (1, 2, False),   # partial: reported in notes, not refused
])
@pytest.mark.asyncio
async def test_the_predicate_truth_table(monkeypatch, seen, named, refuses):
    """Pin all four cases so a later 'simplification' cannot collapse them into one.

    Drives the REAL handler. An earlier draft re-implemented the predicate here and asserted it
    matched itself — a tautology that would have stayed green through the entire defect, which
    is the trap this loop keeps finding in its own guards.
    """
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, MagicMock

    from app.extraction.anchor_loader import ProjectionResult
    from app.tools.executor import execute_tool
    from tests.unit.test_graph_schema_tools import _ctx

    @asynccontextmanager
    async def _fake_session(**_kwargs):
        yield object()

    monkeypatch.setattr("app.tools.graph_schema_tools.graph_session", _fake_session)
    monkeypatch.setattr(
        "app.clients.glossary_client.get_glossary_client", MagicMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "app.extraction.anchor_loader.project_glossary_entities_to_nodes",
        AsyncMock(return_value=ProjectionResult(
            created=seen, existing=0, seen=seen, skipped=0,
        )),
    )
    args = {"entity_ids": [f"id-{i}" for i in range(named)]} if named else {}
    res = await execute_tool(_ctx(), "kg_project_entities_to_nodes", args)
    if refuses:
        assert not res.success, res.result
        assert "matched a glossary entity" in res.error
        assert "unchanged" in res.error
    else:
        assert res.success, res.error
        assert res.result["entities_seen"] == seen
