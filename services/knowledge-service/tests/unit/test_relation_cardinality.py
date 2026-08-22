"""Lane A (D-KG-L7-CARDINALITY) — single_active edge auto-close in create_relation.

These are unit tests at the `run_write` seam (the live PG+Neo4j integration that
actually proves the close is the §6 E2E; here we assert the *control flow*: a
`single_active` cardinality fires the close query before the MERGE, while
`multi_active`/None never does and the legacy create cypher stays byte-identical).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.db.cypher_dialect import render

import pytest

from app.db.neo4j_repos import relations as m
from app.db.neo4j_repos.relations import create_relation

_TEST_USER = uuid4()
_SUBJ = "ent-subj-1"
_OBJ = "ent-obj-1"


def _make_result(record):
    r = MagicMock()
    r.single = AsyncMock(return_value=record)
    return r


def _created_record(predicate="disciple_of"):
    return {
        "rel": {
            "id": "rel-1", "user_id": str(_TEST_USER), "subject_id": _SUBJ,
            "object_id": _OBJ, "predicate": predicate, "confidence": 1.0,
            "valid_from": datetime.now(timezone.utc), "valid_until": None,
            "pending_validation": False,
        },
        "subj": {"name": "A", "kind": "character"},
        "obj": {"name": "B", "kind": "character"},
    }


# ── cypher regression-lock ──────────────────────────────────────────

def test_close_cypher_is_user_scoped_and_open_only():
    """The close query closes ONLY the open instance, in the SAME tenant
    partition, and never the new edge's own id (no self-close on idempotent
    re-create)."""
    cy = m._CLOSE_PRIOR_SINGLE_ACTIVE_CYPHER
    assert "$user_id" in cy
    assert "rp.user_id = $user_id" in cy
    assert "rp.valid_until IS NULL" in cy
    assert "rp.id <> $relation_id" in cy
    assert "SET rp.valid_until = {NOW}" in cy
    # F5, RESTATED for the merged form (T71): AGE has no ON MATCH SET, so "must not touch
    # valid_until on match" is now "must not assign valid_until AT ALL" — an absent property
    # IS null on create, and any assignment here would fire on match too and resurrect a
    # relation an author had invalidated. Auto-close stays a SEPARATE query.
    assert "r.valid_until" not in m._CREATE_RELATION_CYPHER, (
        "create_relation assigns valid_until — on a re-extraction that would resurrect an "
        "edge the author closed. It must not be set here at all."
    )


# ── single_active fires the close before the create ─────────────────

@pytest.mark.asyncio
@patch("app.db.neo4j_repos.relations.run_write", new_callable=AsyncMock)
async def test_single_active_closes_prior_then_creates(mock_run):
    # first call = close (returns count result), second = the MERGE create
    mock_run.side_effect = [
        _make_result({"closed": 1}),
        _make_result(_created_record()),
    ]
    rel = await create_relation(
        session=MagicMock(), user_id=str(_TEST_USER),
        subject_id=_SUBJ, predicate="disciple_of", object_id=_OBJ,
        cardinality="single_active",
    )
    assert rel is not None and rel.predicate == "disciple_of"
    assert mock_run.await_count == 2
    # first query is the close
    first_cypher = mock_run.await_args_list[0].args[1]
    assert first_cypher == m._CLOSE_PRIOR_SINGLE_ACTIVE_CYPHER
    # second is the create
    second_cypher = mock_run.await_args_list[1].args[1]
    assert second_cypher == m._CREATE_RELATION_CYPHER


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.relations.run_write", new_callable=AsyncMock)
async def test_multi_active_does_not_close(mock_run):
    mock_run.return_value = _make_result(_created_record(predicate="pursues"))
    rel = await create_relation(
        session=MagicMock(), user_id=str(_TEST_USER),
        subject_id=_SUBJ, predicate="pursues", object_id=_OBJ,
        cardinality="multi_active",
    )
    assert rel is not None
    # only the create query — no close
    assert mock_run.await_count == 1
    assert mock_run.await_args_list[0].args[1] == m._CREATE_RELATION_CYPHER


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.relations.run_write", new_callable=AsyncMock)
async def test_none_cardinality_is_legacy_no_close(mock_run):
    """Default (cardinality=None) is byte-identical to the legacy path — exactly
    one query, the create."""
    mock_run.return_value = _make_result(_created_record(predicate="ally_of"))
    rel = await create_relation(
        session=MagicMock(), user_id=str(_TEST_USER),
        subject_id=_SUBJ, predicate="ally_of", object_id=_OBJ,
    )
    assert rel is not None
    assert mock_run.await_count == 1
    assert mock_run.await_args_list[0].args[1] == m._CREATE_RELATION_CYPHER
