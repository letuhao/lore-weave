"""K14.5-K14.7 — Unit tests for event handlers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.events.dispatcher import EventData
from app.events.handlers import (
    handle_chat_turn,
    handle_chapter_published,
    handle_chapter_unpublished,
    handle_chapter_deleted,
    handle_glossary_entity_updated,
)


_USER = uuid4()
_PROJECT = uuid4()
_BOOK = uuid4()
_CHAPTER = uuid4()


def _event(event_type, aggregate_id=None, payload=None):
    return EventData(
        stream="loreweave:events:chat",
        message_id="1-0",
        event_type=event_type,
        aggregate_id=aggregate_id or str(uuid4()),
        payload=payload or {},
        source="book",
        raw={},
    )


def _mock_pool():
    """Create a pool mock where acquire() is an async context manager."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock()

    @asynccontextmanager
    async def mock_acquire():
        yield mock_conn

    pool = MagicMock()
    pool.acquire = mock_acquire
    pool.fetchrow = mock_conn.fetchrow
    pool.execute = mock_conn.execute
    return pool, mock_conn


# ── K14.5: chat.turn_completed ───────────────────────────────────────


@pytest.mark.asyncio
@patch("app.events.handlers.should_extract", return_value=True)
async def test_chat_turn_queues_event_with_user_id(mock_gate):
    pool, conn = _mock_pool()
    event = _event(
        "chat.turn_completed",
        payload={"project_id": str(_PROJECT), "user_id": str(_USER)},
    )
    await handle_chat_turn(event, pool=pool)
    assert conn.fetchrow.call_count >= 1


@pytest.mark.asyncio
@patch("app.events.handlers.should_extract", return_value=True)
async def test_chat_turn_resolves_user_from_db(mock_gate):
    """user_id missing from payload — handler looks up from project."""
    pool, conn = _mock_pool()
    # First pool.fetchrow: user_id lookup from project
    pool.fetchrow = AsyncMock(return_value={"user_id": _USER})
    event = _event(
        "chat.turn_completed",
        payload={"project_id": str(_PROJECT)},  # no user_id
    )
    await handle_chat_turn(event, pool=pool)
    pool.fetchrow.assert_called_once()  # user lookup


@pytest.mark.asyncio
async def test_chat_turn_missing_project_id_skips():
    pool, conn = _mock_pool()
    event = _event("chat.turn_completed", payload={})
    await handle_chat_turn(event, pool=pool)
    conn.fetchrow.assert_not_called()


# ── CM3b/CM3c: chapter.published (graph-queue + passage-ingest) ──────


_REVISION = uuid4()


def _published_event(revision_id=str(_REVISION), book_id=str(_BOOK)):
    payload = {"book_id": book_id} if book_id else {}
    if revision_id is not None:
        payload["revision_id"] = revision_id
    return _event(
        "chapter.published", aggregate_id=str(_CHAPTER), payload=payload,
    )


def _book_client_with_sort(sort_order=7):
    """A book_client mock whose get_chapter_sort_orders (CM4 chapter_index
    source) returns the chapter's sort_order awaitably."""
    bc = MagicMock()
    bc.get_chapter_sort_orders = AsyncMock(return_value={_CHAPTER: sort_order})
    return bc


def _patch_pending_repo(monkeypatch):
    """Patch ExtractionPendingRepo so the graph-queue write is a no-op
    spy. Returns the upsert AsyncMock for assertions."""
    upsert = AsyncMock()
    repo_instance = MagicMock()
    repo_instance.upsert_chapter_pending = upsert
    monkeypatch.setattr(
        "app.events.handlers.ExtractionPendingRepo",
        lambda _pool: repo_instance,
    )
    return upsert


@pytest.mark.asyncio
async def test_chapter_published_queues_graph_and_skips_passages_when_no_embedding(
    monkeypatch,
):
    """canon=published: graph-queue ALWAYS written; passage-ingest skips
    cleanly when the project has no embedding config."""
    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": None, "embedding_dimension": None,
    })
    upsert = _patch_pending_repo(monkeypatch)

    await handle_chapter_published(_published_event(), pool=pool)

    upsert.assert_awaited_once()  # graph-queue at the pinned revision
    args = upsert.await_args.args
    assert args[2] == _CHAPTER and args[3] == _REVISION


@pytest.mark.asyncio
async def test_chapter_published_missing_revision_id_skips(monkeypatch):
    """No revision_id in payload → cannot pin canon → skip entirely
    (no graph-queue, no passage-ingest)."""
    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": "bge-m3", "embedding_dimension": 1024,
    })
    upsert = _patch_pending_repo(monkeypatch)

    await handle_chapter_published(_published_event(revision_id=None), pool=pool)

    upsert.assert_not_awaited()
    pool.fetchrow.assert_not_called()  # bails before project lookup


@pytest.mark.asyncio
async def test_chapter_published_no_project_skips(monkeypatch):
    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value=None)
    upsert = _patch_pending_repo(monkeypatch)

    await handle_chapter_published(_published_event(), pool=pool)

    pool.fetchrow.assert_called_once()
    upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_chapter_published_ingests_passages_at_pinned_revision(monkeypatch):
    """CM3c: embedding configured + NEO4J_URI → ingest_chapter_passages is
    called with the PINNED revision_id and delete_stale_on_missing=False."""
    from contextlib import asynccontextmanager

    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": "bge-m3", "embedding_dimension": 1024,
    })
    upsert = _patch_pending_repo(monkeypatch)

    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"

        @asynccontextmanager
        async def fake_session():
            yield MagicMock()

        ingest_mock = AsyncMock()
        monkeypatch.setattr("app.db.neo4j.neo4j_session", fake_session)
        monkeypatch.setattr(
            "app.extraction.passage_ingester.ingest_chapter_passages", ingest_mock,
        )
        monkeypatch.setattr(
            "app.clients.book_client.get_book_client",
            lambda: _book_client_with_sort(7),
        )
        monkeypatch.setattr(
            "app.clients.embedding_client.get_embedding_client",
            lambda: MagicMock(),
        )

        await handle_chapter_published(_published_event(), pool=pool)

    upsert.assert_awaited_once()  # graph-queue still written
    ingest_mock.assert_awaited_once()
    kw = ingest_mock.await_args.kwargs
    assert kw["embedding_model"] == "bge-m3"
    assert kw["embedding_dim"] == 1024
    assert kw["revision_id"] == _REVISION  # pinned, not the live draft
    assert kw["delete_stale_on_missing"] is False  # transient None mustn't wipe
    assert kw["chapter_index"] == 7  # CM4: stamped from book-service sort_order


@pytest.mark.asyncio
async def test_chapter_published_passage_failure_does_not_block_graph_queue(
    monkeypatch,
):
    """Best-effort isolation invariant: the graph-queue is written BEFORE
    passage-ingest, and a passage-ingest exception is swallowed — so a failing
    embed must NOT lose the (already-written) graph-extraction queue, and the
    handler must not raise. Guards the queue-first ordering against future
    reorders."""
    from contextlib import asynccontextmanager

    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": "bge-m3", "embedding_dimension": 1024,
    })
    upsert = _patch_pending_repo(monkeypatch)

    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"

        @asynccontextmanager
        async def fake_session():
            yield MagicMock()

        # ingest blows up — must be swallowed, queue must survive.
        ingest_mock = AsyncMock(side_effect=RuntimeError("embed 503"))
        monkeypatch.setattr("app.db.neo4j.neo4j_session", fake_session)
        monkeypatch.setattr(
            "app.extraction.passage_ingester.ingest_chapter_passages", ingest_mock,
        )
        monkeypatch.setattr(
            "app.clients.book_client.get_book_client",
            lambda: _book_client_with_sort(7),
        )
        monkeypatch.setattr(
            "app.clients.embedding_client.get_embedding_client",
            lambda: MagicMock(),
        )

        # Must NOT raise despite the ingest failure.
        await handle_chapter_published(_published_event(), pool=pool)

    upsert.assert_awaited_once()  # graph-queue survived the passage failure
    ingest_mock.assert_awaited_once()


# ── CM3b/CM3c: chapter.unpublished (graph + passage retract) ─────────


def _unpublished_event():
    return _event(
        "chapter.unpublished",
        aggregate_id=str(_CHAPTER),
        payload={"book_id": str(_BOOK)},
    )


@pytest.mark.asyncio
async def test_chapter_unpublished_retracts_graph_and_passages(monkeypatch):
    """Symmetry: unpublish retracts BOTH the graph evidence AND the L3
    passages (so the semantic index doesn't keep published-era passages)."""
    from contextlib import asynccontextmanager

    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(
        return_value={"project_id": _PROJECT, "user_id": _USER}
    )

    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"

        @asynccontextmanager
        async def fake_session():
            yield MagicMock()

        remove_mock = AsyncMock(return_value=3)
        cleanup_mock = AsyncMock(return_value=MagicMock(total=2))
        delete_mock = AsyncMock(return_value=7)
        monkeypatch.setattr("app.db.neo4j.neo4j_session", fake_session)
        # CM3b-RETRACT-FIX: handler now retracts via the NATURAL-KEY helper
        # (hashes the source id) — the raw-id call removed zero edges.
        monkeypatch.setattr(
            "app.db.neo4j_repos.provenance.remove_evidence_for_natural_key",
            remove_mock,
        )
        # /review-impl MED: cleanup is deliberately NOT called here (it would
        # race a concurrent same-project extraction outside the job lock).
        monkeypatch.setattr(
            "app.db.neo4j_repos.provenance.cleanup_zero_evidence_nodes",
            cleanup_mock,
        )
        monkeypatch.setattr(
            "app.db.neo4j_repos.passages.delete_passages_for_source", delete_mock,
        )

        await handle_chapter_unpublished(_unpublished_event(), pool=pool)

    pool.execute.assert_awaited()  # pending row dropped
    # CM3b-RETRACT-FIX regression-lock: the retract is called with the
    # NATURAL KEY (user, project, source_type, source_id), so the helper can
    # hash the right ExtractionSource id. The pre-fix bug passed the raw
    # chapter_id straight to a hashed-id MATCH → zero edges removed.
    remove_mock.assert_awaited_once()
    rk = remove_mock.await_args.kwargs
    assert rk["source_type"] == "chapter"
    assert rk["source_id"] == str(_CHAPTER)
    assert rk["user_id"] == str(_USER)
    assert rk["project_id"] == str(_PROJECT)
    # /review-impl MED regression-lock: NO orphan sweep in the unpublish path
    # (races concurrent extraction outside the job lock; reconciler GCs instead).
    cleanup_mock.assert_not_awaited()
    delete_mock.assert_awaited_once()
    dk = delete_mock.await_args.kwargs
    assert dk["source_type"] == "chapter"
    assert dk["source_id"] == str(_CHAPTER)
    assert dk["user_id"] == str(_USER)


@pytest.mark.asyncio
async def test_chapter_unpublished_passage_retract_independent_of_graph_failure(
    monkeypatch,
):
    """R3-WARN#2: if the graph retract raises, the passage retract must
    STILL run (independent best-effort steps), else published-era passages
    linger after unpublish."""
    from contextlib import asynccontextmanager

    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(
        return_value={"project_id": _PROJECT, "user_id": _USER}
    )

    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"

        @asynccontextmanager
        async def fake_session():
            yield MagicMock()

        remove_mock = AsyncMock(side_effect=RuntimeError("neo4j transient"))
        delete_mock = AsyncMock(return_value=7)
        monkeypatch.setattr("app.db.neo4j.neo4j_session", fake_session)
        # CM3b-RETRACT-FIX: handler retracts via the natural-key helper now.
        monkeypatch.setattr(
            "app.db.neo4j_repos.provenance.remove_evidence_for_natural_key",
            remove_mock,
        )
        monkeypatch.setattr(
            "app.db.neo4j_repos.passages.delete_passages_for_source", delete_mock,
        )

        # Must NOT raise (both steps swallow their own errors).
        await handle_chapter_unpublished(_unpublished_event(), pool=pool)

    remove_mock.assert_awaited_once()
    delete_mock.assert_awaited_once()  # ran despite the graph-retract failure


# ── K14.7: chapter.deleted ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_chapter_deleted_clears_pending():
    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={"project_id": _PROJECT, "user_id": _USER})

    event = _event(
        "chapter.deleted",
        aggregate_id=str(_CHAPTER),
        payload={"book_id": str(_BOOK)},
    )

    with patch("app.config.settings") as ms:
        ms.neo4j_uri = ""
        await handle_chapter_deleted(event, pool=pool)

    pool.execute.assert_called_once()


@pytest.mark.asyncio
async def test_chapter_deleted_no_project_skips():
    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value=None)

    event = _event(
        "chapter.deleted",
        aggregate_id=str(_CHAPTER),
        payload={"book_id": str(_BOOK)},
    )
    await handle_chapter_deleted(event, pool=pool)
    pool.execute.assert_not_called()


# ── C4 (K14): glossary.entity_updated ────────────────────────────────

_ENTITY = uuid4()


def _glossary_event(payload=None, aggregate_id=None):
    return EventData(
        stream="loreweave:events:glossary",
        message_id="9-0",
        event_type="glossary.entity_updated",
        aggregate_id=aggregate_id or str(_ENTITY),
        payload=payload
        if payload is not None
        else {
            "book_id": str(_BOOK),
            "glossary_entity_id": str(_ENTITY),
            "name": "玉虛宮",
            "kind": "location",
            "aliases": ["玉虚宫"],
            "short_description": "Kunlun HQ",
            "op": "updated",
            "source_type": "glossary",
        },
        source="glossary",
        raw={},
    )


@asynccontextmanager
async def _fake_neo4j_session():
    yield MagicMock()


@pytest.mark.asyncio
async def test_glossary_updated_triggers_sync(monkeypatch):
    """Happy path: event with full payload + project found + NEO4J_URI set
    → calls sync_glossary_entity_to_neo4j with resolved user/project."""
    pool, _conn = _mock_pool()
    pool.fetchrow = AsyncMock(
        return_value={"project_id": _PROJECT, "user_id": _USER}
    )

    sync_mock = AsyncMock(
        return_value={"glossary_entity_id": str(_ENTITY), "action": "updated",
                      "canonical_name": "玉虛宮"}
    )
    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"
        monkeypatch.setattr("app.db.neo4j.neo4j_session", _fake_neo4j_session)
        monkeypatch.setattr(
            "app.extraction.glossary_sync.sync_glossary_entity_to_neo4j",
            sync_mock,
        )
        await handle_glossary_entity_updated(_glossary_event(), pool=pool)

    pool.fetchrow.assert_called_once()  # project/user resolution
    sync_mock.assert_awaited_once()
    kw = sync_mock.await_args.kwargs
    assert kw["glossary_entity_id"] == str(_ENTITY)
    assert kw["user_id"] == str(_USER)
    assert kw["project_id"] == str(_PROJECT)
    assert kw["name"] == "玉虛宮"
    assert kw["kind"] == "location"
    assert kw["aliases"] == ["玉虚宫"]


@pytest.mark.asyncio
async def test_glossary_updated_idempotent_on_replay(monkeypatch):
    """At-least-once delivery: re-processing the SAME event simply calls
    sync again (MERGE is keyed on glossary_entity_id → no duplication).
    We assert the handler invokes sync once per delivery with a stable
    MERGE key, which is the idempotency contract."""
    pool, _conn = _mock_pool()
    pool.fetchrow = AsyncMock(
        return_value={"project_id": _PROJECT, "user_id": _USER}
    )
    sync_mock = AsyncMock(
        return_value={"glossary_entity_id": str(_ENTITY), "action": "updated",
                      "canonical_name": "玉虛宮"}
    )
    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"
        monkeypatch.setattr("app.db.neo4j.neo4j_session", _fake_neo4j_session)
        monkeypatch.setattr(
            "app.extraction.glossary_sync.sync_glossary_entity_to_neo4j",
            sync_mock,
        )
        ev = _glossary_event()
        await handle_glossary_entity_updated(ev, pool=pool)
        await handle_glossary_entity_updated(ev, pool=pool)  # replay

    assert sync_mock.await_count == 2
    # Both calls carry the identical MERGE key (user_id, glossary_entity_id).
    keys = {
        (c.kwargs["user_id"], c.kwargs["glossary_entity_id"])
        for c in sync_mock.await_args_list
    }
    assert keys == {(str(_USER), str(_ENTITY))}


@pytest.mark.asyncio
async def test_glossary_updated_skips_when_no_project(monkeypatch):
    """No knowledge project for the book → clean no-op, no sync call."""
    pool, _conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value=None)
    sync_mock = AsyncMock()
    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"
        monkeypatch.setattr(
            "app.extraction.glossary_sync.sync_glossary_entity_to_neo4j",
            sync_mock,
        )
        await handle_glossary_entity_updated(_glossary_event(), pool=pool)

    pool.fetchrow.assert_called_once()
    sync_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_glossary_updated_skips_when_no_neo4j(monkeypatch):
    """Track 1 mode (NEO4J_URI unset) → skip sync, never raise. Canonical
    data stays safe in Postgres; backfill re-converges later."""
    pool, _conn = _mock_pool()
    pool.fetchrow = AsyncMock(
        return_value={"project_id": _PROJECT, "user_id": _USER}
    )
    sync_mock = AsyncMock()
    with patch("app.config.settings") as ms:
        ms.neo4j_uri = ""  # Track 1
        monkeypatch.setattr(
            "app.extraction.glossary_sync.sync_glossary_entity_to_neo4j",
            sync_mock,
        )
        await handle_glossary_entity_updated(_glossary_event(), pool=pool)

    sync_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_glossary_updated_skips_empty_name_or_kind():
    """A fresh-create event with empty name/kind must NOT attempt a sync
    (can't MERGE a meaningful entity) and must NOT even resolve project —
    the populated follow-up event handles it. Also no exception."""
    pool, _conn = _mock_pool()
    payload = {
        "book_id": str(_BOOK),
        "glossary_entity_id": str(_ENTITY),
        "name": "",        # draft not yet named
        "kind": "",
        "op": "created",
        "source_type": "glossary",
    }
    await handle_glossary_entity_updated(
        _glossary_event(payload=payload), pool=pool
    )
    pool.fetchrow.assert_not_called()


@pytest.mark.asyncio
async def test_glossary_updated_missing_ids_skips():
    """Missing book_id/glossary_entity_id → warn + skip, no project lookup."""
    pool, _conn = _mock_pool()
    payload = {"name": "x", "kind": "location"}  # no ids
    await handle_glossary_entity_updated(
        _glossary_event(payload=payload, aggregate_id=""), pool=pool
    )
    pool.fetchrow.assert_not_called()
