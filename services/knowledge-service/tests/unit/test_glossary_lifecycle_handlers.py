"""Glossary lifecycle + curation event handlers (plan T27, T28).

WHY THIS FILE EXISTS AT ALL
---------------------------
T27 shipped `handle_glossary_entity_deleted` / `_restored` / `_purged` and its plan entry
claimed the consumers were unit-covered. They were not — no test in this service named any of
them. The Go side was proven live and the Python side was proven by reading it, which is the
exact asymmetry the plan's own "EVIDENCE PASTED, never a ticked box" rule exists to prevent.

WHAT THESE ASSERT
-----------------
Not "a handler runs" — which archive/restore call it makes, and with which `reason_prefix`.
Since T28 a KG node can be archived by TWO independent sources (the glossary entity was
trashed, or its status left `active`), and the whole correctness of the pair rests on neither
one silently undoing the other's retirement.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.events.dispatcher import EventData
from app.events.handlers import (
    handle_glossary_entity_deleted,
    handle_glossary_entity_purged,
    handle_glossary_entity_restored,
    handle_glossary_entity_status_changed,
)

_USER = uuid4()
_PROJECT = uuid4()
_BOOK = uuid4()
_ENTITY = uuid4()


def _event(event_type, payload):
    return EventData(
        stream="loreweave:events:glossary",
        message_id="1-0",
        event_type=event_type,
        aggregate_id=str(_ENTITY),
        payload=payload,
        source="glossary",
        raw={},
    )


def _payload(**over):
    base = {
        "book_id": str(_BOOK),
        "glossary_entity_id": str(_ENTITY),
        "actor_type": "user",
        "emitted_at": "2026-08-10T00:00:00Z",
    }
    base.update(over)
    return base


@pytest.fixture
def pool():
    """A pool that resolves the book to a KG project — the `_lifecycle_preamble` precondition.

    Without it every handler returns early on "no knowledge project for this book", and a test
    asserting "no archive call was made" would pass for the wrong reason.
    """
    p = AsyncMock()
    p.fetchrow = AsyncMock(return_value={"project_id": _PROJECT, "user_id": _USER})
    return p


@pytest.fixture(autouse=True)
def _neo4j_configured(monkeypatch):
    """`_lifecycle_preamble` skips when NEO4J_URI is unset (Track 1 mode)."""
    from app.config import settings

    monkeypatch.setattr(settings, "neo4j_uri", "bolt://test:7687", raising=False)


@asynccontextmanager
async def _session():
    yield MagicMock()


# ── T28: the curation axis ────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["inactive", "rejected", "draft"])
async def test_status_leaving_active_archives_with_that_reason(pool, status):
    """Retiring an entity must archive the KG node, tagged with WHICH status did it.

    Every consumer-facing glossary read filters `status = 'active'`, so a retired entity is
    already gone from the glossary's own canon reads. Before T28 the mirror kept the node and
    kept answering RAG queries about it.
    """
    entity = MagicMock(id="kg-node-1")
    with patch("app.db.neo4j.graph_session", _session), \
         patch("app.db.neo4j_repos.entities.get_entity_by_glossary_id",
               autospec=True, return_value=entity), \
         patch("app.db.neo4j_repos.entities.user_archive_entity", autospec=True) as archive, \
         patch("app.adapters.graph_store_provider.Neo4jGraphStore.archive_entity",
               new_callable=AsyncMock) as hard_archive:
        await handle_glossary_entity_status_changed(
            _event("glossary.entity_status_changed",
                   _payload(status=status, prior_status="active")),
            pool=pool,
        )
    archive.assert_awaited_once()
    assert archive.await_args.kwargs["reason"] == f"glossary_status_{status}"
    assert archive.await_args.kwargs["canonical_id"] == "kg-node-1"
    # NOT the glossary-deleted archive: that one nulls `glossary_entity_id`, and the KG sync
    # MERGEs on it — so the next edit to a still-editable rejected entity would fail to match
    # the anchorless node and create a second, un-archived twin of it.
    hard_archive.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_returning_to_active_restores_only_status_archives(pool):
    """A return to `active` un-archives — but ONLY a node this axis archived.

    `reason_prefix` is the whole guard: without it, reinstating an entity would also un-archive
    a node that is archived because the glossary entity is in the recycle bin, resurrecting a
    deleted entity into every RAG answer.
    """
    with patch("app.db.neo4j.graph_session", _session), \
         patch("app.db.neo4j_repos.entities.restore_entity_by_glossary_id",
               autospec=True, return_value=MagicMock(id="kg-node-1")) as restore, \
         patch("app.db.neo4j_repos.entities.user_archive_entity", autospec=True) as archive:
        await handle_glossary_entity_status_changed(
            _event("glossary.entity_status_changed",
                   _payload(status="active", prior_status="rejected")),
            pool=pool,
        )
    restore.assert_awaited_once()
    assert restore.await_args.kwargs["reason_prefix"] == "glossary_status_"
    archive.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_missing_from_payload_touches_nothing(pool):
    """A malformed event must not guess.

    Defaulting to archive would retire nodes on a producer bug; defaulting to restore would
    resurrect them. Neither is a safe silent choice, so the handler does nothing and warns.
    """
    with patch("app.db.neo4j.graph_session", _session), \
         patch("app.db.neo4j_repos.entities.user_archive_entity", autospec=True) as archive, \
         patch("app.db.neo4j_repos.entities.restore_entity_by_glossary_id",
               autospec=True) as restore:
        await handle_glossary_entity_status_changed(
            _event("glossary.entity_status_changed", _payload(prior_status="active")),
            pool=pool,
        )
    archive.assert_not_awaited()
    restore.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_change_on_a_book_with_no_kg_project_is_a_no_op(pool):
    """The cold-start answer for most books, and it must be silent rather than an error."""
    pool.fetchrow = AsyncMock(return_value=None)
    with patch("app.db.neo4j.graph_session", _session), \
         patch("app.db.neo4j_repos.entities.user_archive_entity", autospec=True) as archive:
        await handle_glossary_entity_status_changed(
            _event("glossary.entity_status_changed",
                   _payload(status="rejected", prior_status="active")),
            pool=pool,
        )
    archive.assert_not_awaited()


# ── T27: the lifecycle axis, and its boundary with T28's ─────────────────────


@pytest.mark.asyncio
async def test_delete_archives_with_the_glossary_deleted_reason(pool):
    entity = MagicMock(id="kg-node-1")
    with patch("app.db.neo4j.graph_session", _session), \
         patch("app.db.neo4j_repos.entities.get_entity_by_glossary_id",
               autospec=True, return_value=entity), \
         patch("app.adapters.graph_store_provider.Neo4jGraphStore.archive_entity",
               new_callable=AsyncMock) as archive:
        await handle_glossary_entity_deleted(
            _event("glossary.entity_deleted", _payload(op="deleted")), pool=pool,
        )
    archive.assert_awaited_once()
    assert archive.await_args.kwargs["reason"] == "glossary_deleted"


@pytest.mark.asyncio
async def test_recycle_bin_restore_does_not_undo_a_status_retirement(pool):
    """The boundary T28 created and has to hold.

    A recycle-bin restore says "this entity is no longer in the trash". It says nothing about
    whether the author still wants it live — that is the status axis. Restoring with the
    `glossary_deleted` prefix is what keeps a still-`rejected` entity archived.
    """
    with patch("app.db.neo4j.graph_session", _session), \
         patch("app.db.neo4j_repos.entities.restore_entity_by_glossary_id",
               autospec=True, return_value=None) as restore:
        await handle_glossary_entity_restored(
            _event("glossary.entity_restored", _payload(op="restored")), pool=pool,
        )
    restore.assert_awaited_once()
    assert restore.await_args.kwargs["reason_prefix"] == "glossary_deleted"


@pytest.mark.asyncio
async def test_purge_hard_deletes_the_node(pool):
    """A Postgres purge does not cascade to Neo4j, so without this the node outlives the
    entity that justified it and keeps answering queries about something permanently gone."""
    with patch("app.db.neo4j.graph_session", _session), \
         patch("app.db.neo4j_repos.entities.purge_entity_by_glossary_id",
               autospec=True, return_value=1) as purge:
        await handle_glossary_entity_purged(
            _event("glossary.entity_purged", _payload(op="purged")), pool=pool,
        )
    purge.assert_awaited_once()
    assert purge.await_args.kwargs["glossary_entity_id"] == str(_ENTITY)


def test_restore_cypher_scopes_on_the_archive_reason():
    """Assert the PREDICATE, not just that a parameter is passed.

    The handlers above prove the right `reason_prefix` reaches the repo. That is worthless if
    the Cypher ignores it — a mocked repo cannot tell you the query honours its own argument.
    """
    from app.db.neo4j_repos.entities import _RESTORE_BY_GLOSSARY_ID_CYPHER as cypher

    assert "$reason_prefix" in cypher, "the restore must consume the prefix it is handed"
    assert "archive_reason" in cypher and "STARTS WITH" in cypher
    assert "e.archived_at IS NULL" in cypher, (
        "re-anchoring a node that was never archived must stay idempotent"
    )


def test_both_archive_cyphers_let_the_first_reason_win():
    """The scoping above is only as good as the reason it scopes on.

    Retire an entity to `rejected` (archived, reason `glossary_status_rejected`), then trash
    it. If the delete OVERWRITES the reason, pulling it back out of the recycle bin un-archives
    a node the author still has marked rejected — resurrecting it through a route that never
    mentions status. `coalesce` makes the first archiver own the un-archive; every restore path
    clears the reason, so ownership lasts exactly as long as the archive.
    """
    from app.db.neo4j_repos import entities as repo

    for name in ("_ARCHIVE_CYPHER", "_USER_ARCHIVE_CYPHER"):
        cypher = getattr(repo, name)
        assert "e.archive_reason = coalesce(e.archive_reason, $reason)" in cypher, (
            f"{name} overwrites archive_reason — a second archiver would steal the un-archive"
        )
    for name in ("_RESTORE_CYPHER", "_RESTORE_BY_GLOSSARY_ID_CYPHER"):
        assert "e.archive_reason = NULL" in getattr(repo, name), (
            f"{name} must clear the reason, or ownership outlives the archive it came from"
        )
