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

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.neo4j_repos.entities import (
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
@patch("app.db.neo4j_repos.entities.run_write", new_callable=AsyncMock)
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
@patch("app.db.neo4j_repos.entities.run_write", new_callable=AsyncMock)
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


def test_merge_entity_cypher_has_auto_created_on_create_clause():
    """`_MERGE_ENTITY_CYPHER` ON CREATE SET must include $auto_created.

    Regression-lock: removing this line would let auto-created nodes
    silently inherit null on create, breaking the "show auto-created"
    UI filter from cycle 73e onward.
    """
    assert "e.auto_created = $auto_created" in _MERGE_ENTITY_CYPHER
    # The ON CREATE block must include the assignment (not just
    # ON MATCH). We look for the assignment NOT preceded by `CASE`
    # to verify it's in the ON CREATE arm.
    on_create_section = _MERGE_ENTITY_CYPHER.split("ON MATCH")[0]
    assert "e.auto_created = $auto_created" in on_create_section, (
        "ON CREATE arm must set auto_created from the param"
    )


def test_merge_entity_cypher_has_promotion_case_on_match():
    """`_MERGE_ENTITY_CYPHER` ON MATCH SET must include the promotion CASE.

    Regression-lock (cycle 73e M1 fix): any legit re-extraction
    (`$auto_created = false`) clears a previously-auto-created flag.
    Removing this CASE would orphan auto-created entities permanently
    in the "show auto-created" UI list — they'd never be promoted
    via subsequent legitimate writes.
    """
    on_match_section = _MERGE_ENTITY_CYPHER.split("ON MATCH")[1]
    assert "e.auto_created = CASE" in on_match_section
    assert "WHEN $auto_created = false THEN false" in on_match_section
    assert "coalesce(e.auto_created, false)" in on_match_section


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
