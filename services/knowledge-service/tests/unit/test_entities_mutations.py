"""C9 — unit tests for entity mutation helpers with optimistic concurrency.

Covers ``update_entity_fields`` version check + bump and
``unlock_entity_user_edited`` flag flip. Mocks ``run_write`` directly
(live Neo4j integration tests live under tests/integration/db/).
"""

from __future__ import annotations

import re

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.graph_repos.entities import (
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
#
# T80 rewrote this path from one FOREACH-gated statement into TWO statements in one explicit
# transaction, because the FOREACH form was not atomic: 39 of 40 concurrent pairs both applied
# and both were told they had. These stay MOCK tests of the control flow — a mock has no lock,
# which is exactly why the race was invisible here for as long as it was. The property they
# cannot see is pinned live in `tests/integration/db/test_occ_is_actually_atomic.py`.


def _tx_session(records: list):
    """A session whose transaction hands back `records` in order, one per `run`."""
    tx = MagicMock()
    tx.run = AsyncMock(side_effect=[_make_result(r) for r in records])
    tx.commit = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=tx)
    tx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.begin_transaction = AsyncMock(return_value=tx)
    return session, tx


@pytest.mark.asyncio
async def test_update_entity_applies_on_matching_version():
    """Version matches → the second statement runs and its post-write node is returned."""
    before = {"name": "OldKai", "kind": "character", "aliases": ["OldKai"]}
    locked = {"e": _entity_node(name="OldKai", version=3), "current_version": 3,
              "before": before}
    post_write = {"e": _entity_node(name="Kai", version=4, user_edited=True)}
    session, tx = _tx_session([locked, post_write])

    updated, got_before = await update_entity_fields(
        session=session, user_id="u-1", entity_id="ent-1",
        name="Kai", kind=None, aliases=None, expected_version=3,
    )
    assert updated is not None
    assert updated.version == 4
    assert updated.user_edited is True
    assert got_before == before
    assert tx.run.await_count == 2, "the apply statement did not run"
    assert tx.run.await_args_list[1].kwargs["next_version"] == 4, (
        "the new version must come from the version read UNDER THE LOCK, not from the "
        "caller's expected_version — they are equal here, and a bug that used the wrong one "
        "would still pass if this asserted on 3"
    )
    tx.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_entity_raises_on_version_mismatch():
    """Stale expected_version → the apply statement must NOT run, and the CURRENT entity is
    carried on the exception so the router can put it in the 412 body."""
    locked = {"e": _entity_node(name="Kai", version=5), "current_version": 5, "before": None}
    session, tx = _tx_session([locked])

    with pytest.raises(VersionMismatchError) as exc_info:
        await update_entity_fields(
            session=session, user_id="u-1", entity_id="ent-1",
            name="KaiTheRenamed", kind=None, aliases=None, expected_version=3,
        )
    carried = exc_info.value.current
    assert isinstance(carried, Entity)
    assert carried.version == 5
    assert tx.run.await_count == 1, "a mismatched version still ran the write"
    tx.commit.assert_awaited_once(), (
        "the transaction must COMMIT on a mismatch — the locked read normalised a legacy "
        "null version, and raising inside the block would roll that back"
    )


@pytest.mark.asyncio
async def test_update_entity_returns_none_on_missing():
    """Cross-user or missing id — the locked read matches nothing."""
    session, tx = _tx_session([None])

    result, before = await update_entity_fields(
        session=session, user_id="u-1", entity_id="missing",
        name="X", kind=None, aliases=None, expected_version=1,
    )
    assert result is None
    assert before is None
    assert tx.run.await_count == 1


# ── unlock_entity_user_edited: no If-Match, idempotent ──────────────


@pytest.mark.asyncio
@patch("app.db.graph_repos.entities.run_write", new_callable=AsyncMock)
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
@patch("app.db.graph_repos.entities.run_write", new_callable=AsyncMock)
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
    from app.db.graph_repos.entities import _node_to_entity
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
    from app.db.graph_repos import entities as m

    cypher_snippets = [
        ("_UNLOCK_ENTITY_CYPHER", m._UNLOCK_ENTITY_CYPHER),
        ("_MERGE_ENTITY_CYPHER", m._MERGE_ENTITY_CYPHER),
        ("_LOCK_AND_READ_ENTITY_CYPHER", m._LOCK_AND_READ_ENTITY_CYPHER),
        ("_APPLY_ENTITY_FIELDS_CYPHER", m._APPLY_ENTITY_FIELDS_CYPHER),
        ("_MERGE_UPDATE_TARGET_CYPHER", m._MERGE_UPDATE_TARGET_CYPHER),
    ]
    for name, raw in cypher_snippets:
        # T78 — strip Cypher `//` comments first. The merged `_MERGE_ENTITY_CYPHER` explains
        # in a comment WHY `coalesce(e.version, 0) + 1` is the wrong translation (4272 of 4926
        # dev nodes have no `version`, and the old match arm sent every one of them to 2), and
        # this scan read the explanation as the mistake. Prose is not code — the same fix
        # `port-adoption-gate.scan_dialect` needed on the same day.
        cypher = re.sub(r"//[^\n]*", "", raw)
        assert "coalesce(e.version, 0)" not in cypher, (
            f"{name}: uses 0 as coalesce default; must be 1 to match "
            f"_node_to_entity's read-path default"
        )
        assert "coalesce(t.version, 0)" not in cypher, (
            f"{name}: uses 0 as coalesce default; must be 1 to match "
            f"_node_to_entity's read-path default"
        )


@pytest.mark.asyncio
async def test_update_entity_pre_c9_node_with_expected_version_1_applies():
    """/review-impl HIGH regression: a pre-C9 node stores no `version`, reads as 1 via
    `_node_to_entity`, and MUST be editable with ``If-Match: W/"1"``.

    T80 made this the LOCKED READ's job rather than a coalesce inside the gate — statement 1
    is literally `SET e.version = coalesce(e.version, 1)`, so the node is normalised in the
    same transaction that then reads it. 4272 of 4926 dev nodes are in this state, which is
    why the path is worth a test of its own rather than a note.
    """
    locked = {"e": _entity_node(name="Kai", version=1), "current_version": 1,
              "before": {"name": "Kai", "kind": "character", "aliases": ["Kai"]}}
    post_write = {"e": _entity_node(name="Kai", version=2, user_edited=True)}
    session, tx = _tx_session([locked, post_write])

    updated, _before = await update_entity_fields(
        session=session, user_id="u-1", entity_id="pre-c9-ent",
        name="Kai", kind=None, aliases=None, expected_version=1,
    )
    assert updated is not None
    assert updated.version == 2
    assert "coalesce(e.version, 1)" in tx.run.await_args_list[0].args[0], (
        "the locked read stopped normalising a missing version — a pre-C9 node would report "
        "current_version as null and never match any If-Match the client can send"
    )
