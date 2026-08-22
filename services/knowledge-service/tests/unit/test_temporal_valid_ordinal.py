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

from app.db.cypher_dialect import render

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
        # §10.2 — the TEMPLATE carries `{NOW}`; what executes carries the engine's
        # spelling. Assert on the rendered form, because that is what Neo4j sees.
        assert "datetime()" in render(cy, "neo4j")  # only for updated_at, see next
        # the CLOSE value is the next STRICTLY-GREATER survivor's valid_from_ordinal, never now()
        # — strictly-greater so a same-ordinal tie can't collapse into a zero-width [base,base)
        # interval (the A2 bug); mirrors the Postgres maintain_chain core.
        assert "x.valid_from_ordinal > cur.valid_from_ordinal" in cy
        assert "greaters[0]" in cy
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
    assert render(fm._MERGE_FACT_CYPHER, "neo4j") in cyphers
    assert render(tm.MAINTAIN_FACT_CHAIN_CYPHER, "neo4j") in cyphers
    assert cyphers.index(render(tm.MAINTAIN_FACT_CHAIN_CYPHER, "neo4j")) > cyphers.index(
        render(fm._MERGE_FACT_CYPHER, "neo4j"))


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
    assert render(rm._CREATE_RELATION_CYPHER, "neo4j") == cyphers[0]
    assert render(tm.MAINTAIN_RELATION_CHAIN_CYPHER, "neo4j") == cyphers[-1]


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
    assert mock_run.await_args_list[0].args[1] == render(rm._CREATE_RELATION_CYPHER, "neo4j")


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
    assert cyphers[1] == render(rm._CREATE_RELATION_CYPHER, "neo4j")
    assert cyphers[2] == render(tm.MAINTAIN_RELATION_CHAIN_CYPHER, "neo4j")


# ── T46: pin-aware supersession, the KG half ────────────────────────────────────────────
#
# `bitemporal-parity-gate` carried this as the plan's ONE recorded asymmetry: "pin-aware
# supersession: postgres HAS it, neo4j does NOT — an author's EXPLICIT close survives
# re-derivation in glossary and would be overwritten in the graph — the KG has no pin concept
# at all." T46's row says to MOVE THE MATURE SIDE, not rewrite from the weaker one, so these
# mirror the Postgres `maintain_chain`'s `AND ef.valid_to_pinned = false` clause-for-clause.
#
# The single-writer invariant (§12.3.3 LOCKED) is preserved and that is the whole design: a
# pin is NOT a competing deriver of valid_to, it is an authored INPUT the one deriver skips.


def _chain_cyphers():
    """Every maintainer that re-derives valid_to. Fixing one and not the others would leave
    an author's close surviving an append and dying on a retract — the worst of both."""
    return {
        "fact chain": tm.MAINTAIN_FACT_CHAIN_CYPHER,
        "relation chain": tm.MAINTAIN_RELATION_CHAIN_CYPHER,
        "restitch all fact chains": tm._RESTITCH_ALL_FACT_CHAINS_CYPHER,
        "restitch all relation chains": tm._RESTITCH_ALL_RELATION_CHAINS_CYPHER,
    }


def test_EVERY_chain_maintainer_skips_a_pinned_valid_to():
    """A pinned instance keeps its authored bound in all four maintainers.

    Four, not one: `merge_fact` re-runs the chain on append and the retract sweep re-runs the
    restitch variants. A pin honoured on append and overwritten on retract is not a pin.
    """
    for name, cy in _chain_cyphers().items():
        assert "valid_to_pinned" in cy, f"{name} has no pin concept"
        assert "CASE WHEN coalesce(cur.valid_to_pinned, false) THEN cur.valid_to_ordinal" in cy, (
            f"{name} still derives valid_to for a pinned instance — an author's explicit "
            f"close is overwritten by the next append or retract"
        )


def test_the_pin_guard_COALESCES_so_pre_pin_nodes_are_unchanged():
    """The guard must be a strict no-op for every node written before pins existed. Without
    `coalesce`, `cur.valid_to_pinned` is NULL on those nodes and the CASE goes unknown —
    which in Cypher is not true, but relying on that is how a three-valued-logic bug ships.
    """
    for name, cy in _chain_cyphers().items():
        assert "coalesce(cur.valid_to_pinned, false)" in cy, name
        assert "cur.valid_to_pinned = true" not in cy, (
            f"{name} compares the flag directly instead of coalescing — a NULL flag on a "
            f"pre-pin node would take the unknown branch"
        )


def test_a_pinned_row_keeps_its_TIMESTAMP_too():
    """`updated_at` is how an operator sees whether derivation touched a row. Bumping it on a
    row the maintainer deliberately skipped reports work that did not happen."""
    for name, cy in _chain_cyphers().items():
        assert (
            "cur.updated_at =\n      CASE WHEN coalesce(cur.valid_to_pinned, false) "
            "THEN cur.updated_at ELSE datetime() END" in render(cy, "neo4j")
        ), f"{name} bumps updated_at on a pinned row it did not modify"


def test_the_pinned_EFF_bound_is_the_authored_close_not_the_open_ceiling():
    """`valid_to_ordinal_eff` drives as-of reads. A pinned close at N means the value is
    ABSENT after N; falling back to `$open_ceiling` would make an explicitly-closed fact read
    as still holding forever — the exact opposite of what the author said."""
    for name, cy in _chain_cyphers().items():
        assert "THEN coalesce(cur.valid_to_ordinal, $open_ceiling)" in cy, name


def test_extraction_BACKFILLS_a_story_position_but_never_MOVES_one():
    """F3, and it had NO guard until T71 — found by a bite that nothing caught.

    `create_relation` is the EXTRACTION path: an edge first written positionless gains a
    position when a later positioned source re-mentions it, and an edge that already has one
    keeps it. That is `coalesce(r.valid_from_ordinal, $valid_from_ordinal)` — stored first.

    `recreate_relation` is the AUTHOR path and is deliberately the OPPOSITE:
    `coalesce($valid_from_ordinal, r.valid_from_ordinal)` — parameter first, because an author
    supplying a position may MOVE an edge that had one.

    ⚠️ The two differ only in argument order, which is exactly the kind of difference a merge
    flattens by accident. Flipping create's order lets a re-extraction shove an edge to a
    different chapter — invisible at write time, and it moves what every as-of read returns.
    Both directions are pinned here so neither can drift into the other.
    """
    import re

    from app.db.neo4j_repos import relations as rm

    assert re.search(
        r"r\.valid_from_ordinal\s*=\s*coalesce\(\s*r\.valid_from_ordinal\s*,",
        rm._CREATE_RELATION_CYPHER,
    ), (
        "create_relation must be coalesce(r.valid_from_ordinal, $valid_from_ordinal) — "
        "STORED first. The other order lets a re-extraction MOVE an edge that was already "
        "placed, which silently changes every as-of read."
    )
    assert re.search(
        r"r\.valid_from_ordinal\s*=\s*coalesce\(\s*\$valid_from_ordinal\s*,",
        rm._RECREATE_RELATION_CYPHER,
    ), (
        "recreate_relation must be coalesce($valid_from_ordinal, r.valid_from_ordinal) — "
        "PARAMETER first, so an author may reposition an edge (T36)."
    )
