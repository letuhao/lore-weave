"""F3 slice 1+2 — story valid-time axis + ordinal-aware interval-split close.

Unit tests at the ``run_write`` seam (the live Neo4j proof is the integration
suite). Here we assert:
  - the LOCKED half-open interval convention + null-sink ceiling (§12.3.1),
  - the ordinal columns flow into the fact/relation MERGE,
  - ``maintain_chain=True`` fires the ordinal-aware close AFTER the merge, and
    ``maintain_chain=False`` / no-ordinal stays byte-identical legacy,
  - ``valid_from_ordinal`` unifies with ``from_order`` on a fact.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db.neo4j_repos import facts as fm
from app.db.neo4j_repos import relations as rm
from app.db.neo4j_repos import temporal as tm
from app.db.neo4j_repos.events import _NULL_ORDER_SENTINEL
from app.db.neo4j_repos.facts import merge_fact
from app.db.neo4j_repos.relations import create_relation

_USER = uuid4()
_SUBJ = "ent-subj-1"
_OBJ = "ent-obj-1"


def _result(record):
    r = MagicMock()
    r.single = AsyncMock(return_value=record)
    return r


# ── interval convention (§12.3.1, D1) ───────────────────────────────────


def test_open_ceiling_is_the_kg_null_sink_not_spoiler_window():
    """The open-interval ceiling reuses events' INT64_MAX null-sink — NOT
    spoiler_window's fail-closed -1 (the opposite sentinel)."""
    assert tm.ORDINAL_OPEN_CEILING == _NULL_ORDER_SENTINEL == 9223372036854775807
    assert tm.ORDINAL_OPEN_CEILING > 0  # null-sink, never a fail-closed -1


def test_valid_to_ordinal_eff_resolves_open_to_ceiling():
    assert tm.valid_to_ordinal_eff(None) == tm.ORDINAL_OPEN_CEILING
    assert tm.valid_to_ordinal_eff(500) == 500
    assert tm.valid_to_ordinal_eff(0) == 0


def test_as_of_predicate_is_half_open():
    """[from, to): include the lower bound, exclude the upper; open = +∞."""
    pred = tm.AS_OF_ORDINAL_PREDICATE.format(a="f")
    assert "f.valid_from_ordinal <= $as_of_ordinal" in pred
    assert "f.valid_to_ordinal IS NULL OR $as_of_ordinal < f.valid_to_ordinal" in pred
    # matches the contract (views.yaml): valid_from <= N AND (valid_to IS NULL OR N < valid_to)


def test_maintain_chain_cypher_is_ordinal_aware_not_wallclock():
    """The close re-derives valid_to from valid_from_ordinal ORDER, never
    datetime() — this is the A2 fix (single_active closed by wall-clock)."""
    for cy in (tm.MAINTAIN_FACT_CHAIN_CYPHER, tm.MAINTAIN_RELATION_CHAIN_CYPHER):
        assert "ORDER BY" in cy and "valid_from_ordinal ASC" in cy
        assert "valid_until IS NULL" in cy           # only survivors
        assert "valid_from_ordinal IS NOT NULL" in cy  # positionless excluded
        assert "datetime()" in cy  # only for updated_at, see next assert
        # the CLOSE value is the next survivor's valid_from_ordinal, never now()
        assert "nxt.valid_from_ordinal" in cy
        assert "$open_ceiling" in cy


# ── merge_fact wires the ordinal columns + unifies with from_order ──────


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.facts.run_write", new_callable=AsyncMock)
async def test_merge_fact_defaults_valid_from_ordinal_to_from_order(mock_run):
    mock_run.return_value = _result({"f": {
        "id": "f1", "user_id": str(_USER), "type": "milestone",
        "content": "c", "canonical_content": "c",
    }})
    await merge_fact(
        MagicMock(), user_id=str(_USER), project_id="p1",
        type="milestone", content="reaches 黄极境", from_order=500_000_000,
    )
    kwargs = mock_run.await_args_list[0].kwargs
    assert kwargs["valid_from_ordinal"] == 500_000_000  # unified with from_order
    assert kwargs["open_ceiling"] == tm.ORDINAL_OPEN_CEILING


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.facts.run_write", new_callable=AsyncMock)
async def test_merge_fact_explicit_ordinal_wins_over_from_order(mock_run):
    mock_run.return_value = _result({"f": {
        "id": "f1", "user_id": str(_USER), "type": "milestone",
        "content": "c", "canonical_content": "c",
    }})
    await merge_fact(
        MagicMock(), user_id=str(_USER), project_id="p1",
        type="milestone", content="x", from_order=100, valid_from_ordinal=300,
    )
    assert mock_run.await_args_list[0].kwargs["valid_from_ordinal"] == 300


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.facts.run_write", new_callable=AsyncMock)
async def test_merge_fact_maintain_chain_fires_after_merge_with_subject(mock_run):
    mock_run.return_value = _result({"f": {
        "id": "f1", "user_id": str(_USER), "type": "milestone",
        "content": "c", "canonical_content": "c",
    }})
    await merge_fact(
        MagicMock(), user_id=str(_USER), project_id="p1",
        type="milestone", content="x", from_order=500,
        subject_id=_SUBJ, maintain_chain=True,
    )
    # 1: MERGE fact, 2: link subject, 3: maintain_chain
    cyphers = [c.args[1] for c in mock_run.await_args_list]
    assert fm._MERGE_FACT_CYPHER in cyphers
    assert tm.MAINTAIN_FACT_CHAIN_CYPHER in cyphers
    assert cyphers.index(tm.MAINTAIN_FACT_CHAIN_CYPHER) > cyphers.index(fm._MERGE_FACT_CYPHER)


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.facts.run_write", new_callable=AsyncMock)
async def test_merge_fact_no_chain_without_ordinal(mock_run):
    """maintain_chain requested but the fact is positionless → no close (it has
    no place on the story axis)."""
    mock_run.return_value = _result({"f": {
        "id": "f1", "user_id": str(_USER), "type": "milestone",
        "content": "c", "canonical_content": "c",
    }})
    await merge_fact(
        MagicMock(), user_id=str(_USER), project_id="p1",
        type="milestone", content="x", from_order=None,
        subject_id=_SUBJ, maintain_chain=True,
    )
    cyphers = [c.args[1] for c in mock_run.await_args_list]
    assert tm.MAINTAIN_FACT_CHAIN_CYPHER not in cyphers


# ── create_relation wires the ordinal columns + ordinal-aware close ────


def _rel_record():
    return {
        "rel": {
            "id": "rel-1", "user_id": str(_USER), "subject_id": _SUBJ,
            "object_id": _OBJ, "predicate": "pursues", "confidence": 1.0,
            "valid_from": datetime.now(timezone.utc), "valid_until": None,
            "pending_validation": False,
        },
        "subj": {"name": "A", "kind": "character"},
        "obj": {"name": "B", "kind": "character"},
    }


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.relations.run_write", new_callable=AsyncMock)
async def test_create_relation_passes_ordinal_and_ceiling(mock_run):
    mock_run.return_value = _result(_rel_record())
    await create_relation(
        MagicMock(), user_id=str(_USER), subject_id=_SUBJ,
        predicate="pursues", object_id=_OBJ, valid_from_ordinal=300_000_000,
    )
    kwargs = mock_run.await_args_list[0].kwargs
    assert kwargs["valid_from_ordinal"] == 300_000_000
    assert kwargs["open_ceiling"] == tm.ORDINAL_OPEN_CEILING


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.relations.run_write", new_callable=AsyncMock)
async def test_create_relation_maintain_chain_fires_after_create(mock_run):
    mock_run.return_value = _result(_rel_record())
    await create_relation(
        MagicMock(), user_id=str(_USER), subject_id=_SUBJ,
        predicate="pursues", object_id=_OBJ,
        valid_from_ordinal=300, maintain_chain=True,
    )
    cyphers = [c.args[1] for c in mock_run.await_args_list]
    assert rm._CREATE_RELATION_CYPHER == cyphers[0]
    assert tm.MAINTAIN_RELATION_CHAIN_CYPHER == cyphers[-1]


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.relations.run_write", new_callable=AsyncMock)
async def test_create_relation_legacy_path_unchanged(mock_run):
    """No ordinal + no maintain_chain ⇒ exactly one write (the create), byte-
    identical legacy behaviour."""
    mock_run.return_value = _result(_rel_record())
    await create_relation(
        MagicMock(), user_id=str(_USER), subject_id=_SUBJ,
        predicate="ally_of", object_id=_OBJ,
    )
    assert mock_run.await_count == 1
    assert mock_run.await_args_list[0].args[1] == rm._CREATE_RELATION_CYPHER


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.relations.run_write", new_callable=AsyncMock)
async def test_single_active_and_maintain_chain_are_distinct(mock_run):
    """single_active (wall-clock close) and maintain_chain (ordinal close) are
    independent — both can be requested; they fire different queries."""
    mock_run.side_effect = [
        _result({"closed": 1}),       # single_active close
        _result(_rel_record()),        # create
        _result({"maintained": 2}),    # maintain_chain
    ]
    await create_relation(
        MagicMock(), user_id=str(_USER), subject_id=_SUBJ,
        predicate="member_of", object_id=_OBJ,
        cardinality="single_active", valid_from_ordinal=300, maintain_chain=True,
    )
    cyphers = [c.args[1] for c in mock_run.await_args_list]
    assert cyphers[0] == rm._CLOSE_PRIOR_SINGLE_ACTIVE_CYPHER
    assert cyphers[1] == rm._CREATE_RELATION_CYPHER
    assert cyphers[2] == tm.MAINTAIN_RELATION_CHAIN_CYPHER
