"""Cycle 73e — unit tests for `auto_created` property on `:Entity`.

Covers:
1. `merge_entity` propagates the new `auto_created` kwarg to `run_write`
   so the Cypher's `$auto_created` parameter is set correctly.
2. Default `auto_created=False` is passed when caller omits the kwarg
   (regression-lock: existing callers — every extractor that already
   used `merge_entity` — preserve pre-73e behaviour).
3. `_MERGE_ENTITY_CYPHER` template contains both the ON CREATE SET
   line AND the ON MATCH promotion CASE — string-search regression-lock
   so the M1 fix can't be accidentally reverted without breaking this
   test.
4. `_node_to_entity` coalesces legacy nodes (lacking `auto_created`
   property) to `auto_created=False` — same backfill idiom as `version`.

Mocks `run_write` directly; live Neo4j integration tests live under
tests/integration/db/.
"""

from __future__ import annotations

import re

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.graph_repos.entities import (
    Entity,
    _MERGE_ENTITY_CYPHER,
    _node_to_entity,
    merge_entity,
)


def _entity_node(*, id: str = "ent-1", auto_created: bool | None = False) -> dict:
    """Dict shape returned by Neo4j for an :Entity node post-MERGE.

    When `auto_created=None`, the property is OMITTED entirely — simulating
    a legacy (pre-73e) node from the graph. _node_to_entity must coalesce
    to False.
    """
    base = {
        "id": id,
        "user_id": "u-1",
        "project_id": "p-1",
        "name": "Alice",
        "canonical_name": "alice",
        "kind": "character",
        "aliases": ["Alice"],
        "canonical_version": 1,
        "source_types": ["chapter"],
        "confidence": 0.9,
        "glossary_entity_id": None,
        "anchor_score": 0.0,
        "archived_at": None,
        "archive_reason": None,
        "evidence_count": 0,
        "mention_count": 0,
        "user_edited": False,
        "version": 1,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    if auto_created is not None:
        base["auto_created"] = auto_created
    return base


def _make_result(record: dict | None):
    result = MagicMock()
    result.single = AsyncMock(return_value=record)
    return result


# ── kwarg propagation ────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("app.db.graph_repos.entities.run_write", new_callable=AsyncMock)
async def test_merge_entity_auto_created_true_passes_kwarg_to_run_write(mock_run):
    """auto_created=True flows through to the Cypher $auto_created param."""
    mock_run.return_value = _make_result({"e": _entity_node(auto_created=True)})

    await merge_entity(
        session=MagicMock(),
        user_id="u-1",
        project_id="p-1",
        name="Alice",
        kind="character",
        source_type="chapter",
        confidence=0.3,
        auto_created=True,
    )

    assert mock_run.called
    _, kwargs = mock_run.call_args
    assert kwargs["auto_created"] is True, (
        "auto_created=True must propagate to run_write so Cypher's "
        "$auto_created param is set"
    )


@pytest.mark.asyncio
@patch("app.db.graph_repos.entities.run_write", new_callable=AsyncMock)
async def test_merge_entity_default_passes_auto_created_false_to_run_write(mock_run):
    """Caller omits `auto_created` → default False propagates.

    Regression-lock: every pre-73e merge_entity caller (relation writer,
    entity extractor, anchor pre-loader, alias-map redirect target)
    relied on the default behaviour. The Cypher ON MATCH promotion CASE
    explicitly fires only when `$auto_created = false`, so a missing
    default would either crash on undefined param OR set the flag to
    null and skip promotion silently.
    """
    mock_run.return_value = _make_result({"e": _entity_node(auto_created=False)})

    await merge_entity(
        session=MagicMock(),
        user_id="u-1",
        project_id="p-1",
        name="Alice",
        kind="character",
        source_type="chapter",
        confidence=0.9,
    )

    assert mock_run.called
    _, kwargs = mock_run.call_args
    assert kwargs["auto_created"] is False, (
        "default kwarg must propagate False; pre-73e callers depend on it"
    )


# ── Cypher template lock (M1 promotion regression-lock) ─────────────


def _statements(cypher: str) -> str:
    """`cypher` with its `//` comments removed.

    T78 merged the two arms, and the notes explaining WHY a field is or is not assigned now
    sit inside the query string. A text-lock that reads them is asserting about prose — the
    same blindness `port-adoption-gate.scan_dialect` had to fix the same day, one layer down.
    """
    return re.sub(r"//[^\n]*", "", cypher)


def test_merge_entity_cypher_takes_auto_created_from_the_param_ON_CREATE():
    """Regression-lock: a created node must take `$auto_created`, not `false`.

    §10.1 merged the arms — AGE has no `ON CREATE SET` — so the create path is now the
    `existed = false` leg of a CASE rather than a separate clause. The property it locks is
    unchanged: without it an auto-created node inherits the MATCH arm's `coalesce(null, false)`
    and lands as `false`, which is the "show auto-created" UI filter silently losing every row
    it exists to show.
    """
    body = _statements(_MERGE_ENTITY_CYPHER)
    assert "ON CREATE SET" not in body and "ON MATCH SET" not in body, (
        "the branch keywords are back — AGE has neither (§10.1)"
    )
    assert "ELSE $auto_created" in body, (
        "the create leg no longer takes $auto_created; a node minted with auto_created=True "
        "would be stored as False"
    )


def test_merge_entity_cypher_keeps_the_promotion_CASE_on_the_existed_leg():
    """Regression-lock (cycle 73e M1): a legit re-extraction clears the flag.

    Now gated on `existed`, because the demotion must apply to a node that was ALREADY there —
    applying it unconditionally is precisely the bug the test above locks against.
    """
    body = _statements(_MERGE_ENTITY_CYPHER)
    assert "e.auto_created = CASE" in body
    assert "WHEN existed AND $auto_created = false THEN false" in body, (
        "the promotion leg lost its `existed` guard or its condition"
    )
    assert "coalesce(e.auto_created, false)" in body


def test_the_comment_stripper_SEES_a_construct_that_is_really_there():
    """Non-vacuity for `_statements`: if it ate the whole query, both locks above would pass
    on an empty string. Validated on a construct the stripper was not written for."""
    assert "SET e.a = 1" in _statements("// ON CREATE SET is gone" + chr(10) + "SET e.a = 1")
    assert "ON CREATE SET" not in _statements("// ON CREATE SET is gone" + chr(10) + "SET e.a = 1")


# ── _node_to_entity coalesce for legacy nodes (M2 backward-compat) ──


def test_node_to_entity_legacy_node_without_auto_created_property_reads_as_false():
    """Pre-73e nodes lack `auto_created` property.

    `_node_to_entity` must coalesce missing property to False so reads
    don't crash and the "show auto-created" filter correctly classifies
    legacy nodes as non-auto-created (the safe default).

    Same backfill idiom as `version` coalesce; Cypher read sites must
    mirror with `coalesce(e.auto_created, false)`.
    """
    legacy_node = _entity_node(auto_created=None)  # property OMITTED
    entity = _node_to_entity(legacy_node)
    assert isinstance(entity, Entity)
    assert entity.auto_created is False, (
        "legacy node without auto_created property must read as False"
    )


def test_node_to_entity_new_node_with_auto_created_true_reads_as_true():
    """Post-73e auto-created node returns auto_created=True via Pydantic."""
    new_node = _entity_node(auto_created=True)
    entity = _node_to_entity(new_node)
    assert isinstance(entity, Entity)
    assert entity.auto_created is True


def test_node_to_entity_post_promotion_node_reads_as_false():
    """Entity that WAS auto-created but later got promoted (legit
    re-extraction fired ON MATCH promotion CASE) reads as False."""
    promoted_node = _entity_node(auto_created=False)
    entity = _node_to_entity(promoted_node)
    assert entity.auto_created is False
