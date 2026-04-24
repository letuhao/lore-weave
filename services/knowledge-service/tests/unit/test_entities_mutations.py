"""C9 — unit tests for entity mutation helpers with optimistic concurrency.

Covers ``update_entity_fields`` version check + bump and
``unlock_entity_user_edited`` flag flip. Mocks ``run_write`` directly
(live Neo4j integration tests live under tests/integration/db/).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.neo4j_repos.entities import (
    Entity,
    update_entity_fields,
    unlock_entity_user_edited,
)
from app.db.repositories import VersionMismatchError


def _entity_node(
    *,
    id: str = "ent-1",
    user_id: str = "u-1",
    name: str = "Kai",
    kind: str = "character",
    aliases: list[str] | None = None,
    version: int = 3,
    user_edited: bool = False,
) -> dict:
    """Dict shape returned by Neo4j for an :Entity node. _node_to_entity
    handles the `.items()` branch, so a plain dict suffices."""
    return {
        "id": id,
        "user_id": user_id,
        "project_id": "p-1",
        "name": name,
        "canonical_name": name.lower(),
        "kind": kind,
        "aliases": aliases or [name],
        "canonical_version": 1,
        "source_types": ["chapter"],
        "confidence": 0.9,
        "glossary_entity_id": None,
        "anchor_score": 0.0,
        "archived_at": None,
        "archive_reason": None,
        "evidence_count": 3,
        "mention_count": 5,
        "user_edited": user_edited,
        "version": version,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def _make_result(record: dict | None):
    result = MagicMock()
    result.single = AsyncMock(return_value=record)
    return result


# ── update_entity_fields: version flow ──────────────────────────────


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.entities.run_write", new_callable=AsyncMock)
async def test_update_entity_applies_on_matching_version(mock_run):
    """When expected_version matches the DB's current_version, the
    FOREACH body runs — Cypher returns the post-write entity + applied=True."""
    post_write = _entity_node(name="Kai", version=4, user_edited=True)
    mock_run.return_value = _make_result({"e": post_write, "applied": True})

    updated = await update_entity_fields(
        session=MagicMock(),
        user_id="u-1",
        entity_id="ent-1",
        name="Kai",
        kind=None,
        aliases=None,
        expected_version=3,
    )
    assert updated is not None
    assert updated.version == 4
    assert updated.user_edited is True
    # expected_version threaded to Cypher as a kwarg.
    assert mock_run.await_args.kwargs["expected_version"] == 3


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.entities.run_write", new_callable=AsyncMock)
async def test_update_entity_raises_on_version_mismatch(mock_run):
    """When expected_version is stale, FOREACH skips — Cypher returns
    the pre-write entity + applied=False. Helper raises
    VersionMismatchError carrying the current Entity so the router can
    return it in the 412 body."""
    pre_write = _entity_node(name="Kai", version=5, user_edited=False)
    mock_run.return_value = _make_result({"e": pre_write, "applied": False})

    with pytest.raises(VersionMismatchError) as exc_info:
        await update_entity_fields(
            session=MagicMock(),
            user_id="u-1",
            entity_id="ent-1",
            name="KaiTheRenamed",
            kind=None,
            aliases=None,
            expected_version=3,
        )
    carried = exc_info.value.current
    assert isinstance(carried, Entity)
    assert carried.version == 5
    assert carried.user_edited is False  # pre-write state


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.entities.run_write", new_callable=AsyncMock)
async def test_update_entity_returns_none_on_missing(mock_run):
    """Cross-user or missing id — MATCH produces no row, Cypher returns
    no record. Helper returns None (router collapses to 404)."""
    mock_run.return_value = _make_result(None)

    result = await update_entity_fields(
        session=MagicMock(),
        user_id="u-1",
        entity_id="missing",
        name="X",
        kind=None,
        aliases=None,
        expected_version=1,
    )
    assert result is None


# ── unlock_entity_user_edited: no If-Match, idempotent ──────────────


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.entities.run_write", new_callable=AsyncMock)
async def test_unlock_flips_user_edited_and_bumps_version(mock_run):
    unlocked = _entity_node(version=6, user_edited=False)
    mock_run.return_value = _make_result({"e": unlocked})

    result = await unlock_entity_user_edited(
        session=MagicMock(), user_id="u-1", entity_id="ent-1",
    )
    assert result is not None
    assert result.user_edited is False
    assert result.version == 6


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.entities.run_write", new_callable=AsyncMock)
async def test_unlock_returns_none_on_missing(mock_run):
    """Cross-user / missing id — returns None, router 404s."""
    mock_run.return_value = _make_result(None)

    result = await unlock_entity_user_edited(
        session=MagicMock(), user_id="u-1", entity_id="missing",
    )
    assert result is None


# ── Entity.version: coalesce backfill for pre-C9 nodes ──────────────


def test_entity_defaults_version_to_1_when_missing():
    """Pre-C9 nodes lack the version property. _node_to_entity must
    provide a sane default so existing entities are readable after the
    C9 migration without a batch backfill."""
    from app.db.neo4j_repos.entities import _node_to_entity
    node = _entity_node()
    del node["version"]  # simulate pre-C9 node
    entity = _node_to_entity(node)
    assert entity.version == 1


def test_cypher_version_coalesce_default_matches_read_path():
    """/review-impl HIGH lock: if ``_node_to_entity`` defaults missing
    version to N, every Cypher coalesce over e.version / t.version
    MUST also default to N. Otherwise pre-C9 entities read version=N
    but compare as version=M internally, so FE's ``If-Match: W/"N"``
    never matches and the row becomes permanently uneditable.

    Reads the Cypher string literals at import time and scans for any
    ``coalesce(e.version, 0)`` / ``coalesce(t.version, 0)`` left over
    from the original implementation. A future edit that reintroduces
    a zero default will trip this test.
    """
    from app.db.neo4j_repos import entities as m

    cypher_snippets = [
        ("_UPDATE_ENTITY_FIELDS_CYPHER", m._UPDATE_ENTITY_FIELDS_CYPHER),
        ("_UNLOCK_ENTITY_CYPHER", m._UNLOCK_ENTITY_CYPHER),
        ("_MERGE_ENTITY_CYPHER", m._MERGE_ENTITY_CYPHER),
        ("_MERGE_UPDATE_TARGET_CYPHER", m._MERGE_UPDATE_TARGET_CYPHER),
    ]
    for name, cypher in cypher_snippets:
        assert "coalesce(e.version, 0)" not in cypher, (
            f"{name}: uses 0 as coalesce default; must be 1 to match "
            f"_node_to_entity's read-path default"
        )
        assert "coalesce(t.version, 0)" not in cypher, (
            f"{name}: uses 0 as coalesce default; must be 1 to match "
            f"_node_to_entity's read-path default"
        )


@pytest.mark.asyncio
@patch("app.db.neo4j_repos.entities.run_write", new_callable=AsyncMock)
async def test_update_entity_pre_c9_node_with_expected_version_1_applies(
    mock_run,
):
    """/review-impl HIGH regression test: a pre-C9 node (no version
    property stored) is readable as version=1 via _node_to_entity and
    MUST be editable with ``If-Match: W/"1"``. This test represents
    the unit-level surface of the coalesce-alignment fix. It mocks
    ``run_write`` to return what the corrected Cypher SHOULD produce —
    applied=True, post-write version=2 — for a caller sending
    expected_version=1 against a node that was pre-C9 (we simulate by
    having the post-write node come back with version=2 without
    explicitly modelling the coalesce step; the contract test at
    ``test_cypher_version_coalesce_default_matches_read_path``
    anchors the Cypher side so the two tests together cover the
    invariant end-to-end."""
    post_write = _entity_node(name="Kai", version=2, user_edited=True)
    mock_run.return_value = _make_result({"e": post_write, "applied": True})

    updated = await update_entity_fields(
        session=MagicMock(),
        user_id="u-1",
        entity_id="pre-c9-ent",
        name="Kai",
        kind=None,
        aliases=None,
        expected_version=1,
    )
    assert updated is not None
    assert updated.version == 2
    assert mock_run.await_args.kwargs["expected_version"] == 1
