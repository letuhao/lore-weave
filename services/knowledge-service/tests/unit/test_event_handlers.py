"""K14.5-K14.7 — Unit tests for event handlers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.events.dispatcher import EventData
from app.events.handlers import (
    handle_chat_turn,
    handle_chat_message_feedback,
    handle_chapter_published,
    handle_chapter_unpublished,
    handle_chapter_kg_indexed,
    handle_chapter_kg_excluded,
    handle_chapter_deleted,
    handle_glossary_entity_updated,
    handle_translation_published,
)


@pytest.fixture(autouse=True)
def _not_kg_excluded(monkeypatch):
    """review-impl: the KG-write handlers re-check the LIVE kg_exclude state against
    book-service before writing (an at-least-once redelivery must not resurrect a chapter
    the user has since forgotten). `is_chapter_kg_excluded` FAILS CLOSED, so without a stub
    every handler test would skip its write.

    Default: not excluded. Tests that want the exclusion path override this explicitly.
    """
    client = MagicMock()
    client.is_chapter_kg_excluded = AsyncMock(return_value=False)
    monkeypatch.setattr("app.clients.book_client.get_book_client", lambda: client)
    return client


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


# ── Track 4 P3b — chat.message_feedback ─────────────────────────────


def _feedback_payload(**overrides):
    from datetime import datetime, timezone
    base = {
        "user_id": str(_USER),
        "project_id": str(_PROJECT),
        "session_id": str(uuid4()),
        "message_id": str(uuid4()),
        "rating": 1,
        "message_created_at": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
@patch("app.db.repositories.entity_access.EntityAccessRepo.apply_feedback", new_callable=AsyncMock)
async def test_feedback_applies_boost_with_full_payload(mock_apply):
    mock_apply.return_value = 3
    payload = _feedback_payload()
    await handle_chat_message_feedback(_event("chat.message_feedback", payload=payload), pool=AsyncMock())
    mock_apply.assert_awaited_once()
    args = mock_apply.await_args.args
    assert str(args[0]) == payload["user_id"]      # tenancy scope threaded
    assert str(args[1]) == payload["project_id"]
    assert str(args[2]) == payload["session_id"]
    assert args[3] == 1


@pytest.mark.asyncio
@patch("app.db.repositories.entity_access.EntityAccessRepo.apply_feedback", new_callable=AsyncMock)
async def test_feedback_skips_legacy_payload_without_p3b_keys(mock_apply):
    # old producers (no project_id/message_created_at) → silent skip, never raise
    await handle_chat_message_feedback(
        _event("chat.message_feedback", payload={
            "user_id": str(_USER), "session_id": str(uuid4()), "rating": 1,
        }),
        pool=AsyncMock(),
    )
    mock_apply.assert_not_called()


@pytest.mark.asyncio
@patch("app.db.repositories.entity_access.EntityAccessRepo.apply_feedback", new_callable=AsyncMock)
async def test_feedback_rejects_out_of_range_rating(mock_apply):
    await handle_chat_message_feedback(
        _event("chat.message_feedback", payload=_feedback_payload(rating=5)),
        pool=AsyncMock(),
    )
    mock_apply.assert_not_called()


@pytest.mark.asyncio
# WS-1.3: the D6 gate now GATES the enqueue (it used to be computed and only logged).
# A normal project may extract; the assistant may not. See test_d6_chat_turn_gate.py.
@patch("app.events.handlers.may_extract_chat_turn", new_callable=AsyncMock)
@patch("app.events.handlers.should_extract", return_value=True)
@patch("app.events.handlers.ExtractionPendingRepo")
async def test_chat_turn_enqueues_aggregate_type_chat(mock_repo_cls, mock_gate, mock_d6):
    mock_d6.return_value = True
    # FD-2 regression: enqueue as aggregate_type='chat' so the worker-ai chat
    # drainer (WHERE aggregate_type='chat') consumes it. Was 'chat_session' →
    # never drained → chat knowledge was never extracted.
    pool, _ = _mock_pool()
    repo = MagicMock()
    repo.queue_event = AsyncMock()
    mock_repo_cls.return_value = repo
    event = _event(
        "chat.turn_completed", aggregate_id=str(_USER),
        payload={"project_id": str(_PROJECT), "user_id": str(_USER)},
    )
    await handle_chat_turn(event, pool=pool)
    req = repo.queue_event.await_args.args[1]
    assert req.aggregate_type == "chat"


@pytest.mark.asyncio
@patch("app.events.handlers.may_extract_chat_turn", new_callable=AsyncMock)
@patch("app.events.handlers.should_extract", return_value=True)
async def test_chat_turn_resolves_user_from_db(mock_gate, mock_d6):
    """user_id missing from payload — handler looks up from project."""
    mock_d6.return_value = True
    pool, conn = _mock_pool()
    # First pool.fetchrow: user_id lookup from project.
    # (WS-1.3: the D6 gate reads the project row too, so this is no longer the ONLY
    # fetchrow — assert it happened, not that it happened exactly once.)
    pool.fetchrow = AsyncMock(return_value={"user_id": _USER})
    event = _event(
        "chat.turn_completed",
        payload={"project_id": str(_PROJECT)},  # no user_id
    )
    await handle_chat_turn(event, pool=pool)
    pool.fetchrow.assert_called()  # user lookup happened


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
    source) returns the chapter's sort_order awaitably.

    review-impl: it MUST also carry `is_chapter_kg_excluded` — the KG-write handlers now
    re-check the live exclusion state before writing (an at-least-once redelivery must not
    resurrect a forgotten chapter). A mock that lags the real client's surface is exactly
    what hides a contract change: without this the handler would await a bare MagicMock.
    """
    bc = MagicMock()
    bc.get_chapter_sort_orders = AsyncMock(return_value={_CHAPTER: sort_order})
    bc.is_chapter_kg_excluded = AsyncMock(return_value=False)
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


def _kg_excluded_event():
    return _event(
        "chapter.kg_excluded",
        aggregate_id=str(_CHAPTER),
        payload={"book_id": str(_BOOK)},
    )


# ── WS-0.8: chapter.kg_indexed — the handler whose ABSENCE made the whole
#            feature a silent no-op (spec §3.7) ──


@pytest.mark.asyncio
async def test_chapter_kg_indexed_queues_extraction(monkeypatch):
    """THE HEADLINE. An indexed DRAFT chapter must actually enter the graph.

    Without this handler, book-service commits the pointer, re-parses the scenes,
    returns 200, and the UI shows "indexed" — while the event matches no registration,
    is logged at DEBUG, and is acked into the void. No extraction_pending row ⇒
    worker-ai's incremental drain enumerates nothing ⇒ zero facts. The UI says
    "indexed"; the graph has nothing.
    """
    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": None, "embedding_dimension": None,
    })
    upsert = _patch_pending_repo(monkeypatch)

    # A pure DRAFT index: never published.
    await handle_chapter_kg_indexed(
        _kg_indexed_event(revision_id=_REVISION, published_revision_id=None), pool=pool,
    )

    upsert.assert_awaited_once()
    args = upsert.await_args.args
    assert args[2] == _CHAPTER and args[3] == _REVISION, (
        "the extraction must be queued at the INDEXED revision"
    )
    # Attributable: the pending row records which event armed it (the repo used to
    # hardcode 'chapter.published').
    assert upsert.await_args.kwargs.get("event_type") == "chapter.kg_indexed"


@pytest.mark.asyncio
async def test_chapter_kg_indexed_draft_ingests_passages_as_canon_false(monkeypatch):
    """Spec §3.7 / P1-8 — the INVERSE bug guard.

    canon = (revision_id == published_revision_id). A DRAFT chapter the user indexed has
    NO published revision, so its passages must ingest as canon=False. Blindly copying
    chapter.published's canon=True would surface unreviewed draft prose in every
    `surface=canon` read — raw_search maintains a deliberate draft/canon split.
    """
    ingest = AsyncMock()
    monkeypatch.setattr("app.events.handlers._ingest_published_passages", ingest)

    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": "bge-m3", "embedding_dimension": 1024,
    })
    _patch_pending_repo(monkeypatch)

    await handle_chapter_kg_indexed(
        _kg_indexed_event(revision_id=_REVISION, published_revision_id=None), pool=pool,
    )

    ingest.assert_awaited_once()
    assert ingest.await_args.kwargs["canon"] is False, (
        "a DRAFT chapter's passages must NOT be canon — draft prose must not surface "
        "as canonical (spec §3.7 / P1-8)"
    )


@pytest.mark.asyncio
async def test_chapter_kg_indexed_at_the_published_revision_is_canon(monkeypatch):
    """The other half of the rule: indexing a chapter AT its published revision means
    the pinned prose IS the canon, so its passages are canon=True."""
    ingest = AsyncMock()
    monkeypatch.setattr("app.events.handlers._ingest_published_passages", ingest)

    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": "bge-m3", "embedding_dimension": 1024,
    })
    _patch_pending_repo(monkeypatch)

    await handle_chapter_kg_indexed(
        _kg_indexed_event(revision_id=_REVISION, published_revision_id=_REVISION),
        pool=pool,
    )

    ingest.assert_awaited_once()
    assert ingest.await_args.kwargs["canon"] is True


# ── review-impl P0: an EXCLUDED chapter must never reach the graph, by ANY door ──


@pytest.mark.asyncio
async def test_publishing_an_excluded_chapter_does_not_index_it(monkeypatch):
    """THE P0. Refusing to move the pointer in book-service is NOT enough.

    `handle_chapter_published` is what enqueues the extraction and ingests canon passages,
    and it cannot see kg_exclude (a book-service column). So publishing — or re-publishing
    — a chapter the user asked us to forget silently re-indexed it: the pointer stayed
    NULL while the facts landed in the graph. The exclusion must ride the EVENT.
    """
    ingest = AsyncMock()
    monkeypatch.setattr("app.events.handlers._ingest_published_passages", ingest)
    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": "bge-m3", "embedding_dimension": 1024,
    })
    upsert = _patch_pending_repo(monkeypatch)

    ev = _event("chapter.published", aggregate_id=str(_CHAPTER), payload={
        "book_id": str(_BOOK), "revision_id": str(_REVISION), "kg_exclude": True,
    })
    await handle_chapter_published(ev, pool=pool)

    upsert.assert_not_awaited(), (
        "an excluded chapter must NOT be queued for extraction — the user removed it "
        "from their knowledge graph"
    )
    ingest.assert_not_awaited(), "an excluded chapter must NOT get passages"


@pytest.mark.asyncio
async def test_a_redelivered_index_event_cannot_resurrect_a_forgotten_chapter(
    monkeypatch, _not_kg_excluded,
):
    """review-impl: the payload alone is not enough — the bus is at-least-once.

    A `chapter.kg_indexed` message can be redelivered and reclaimed AFTER the user
    excluded the chapter. Acting on the (now stale) payload would RESURRECT forgotten
    prose — facts, passages and a re-armed extraction — permanently, with no further event
    to undo it. So the handler re-checks the LIVE state before writing.
    """
    _not_kg_excluded.is_chapter_kg_excluded = AsyncMock(return_value=True)  # excluded SINCE the emit

    ingest = AsyncMock()
    monkeypatch.setattr("app.events.handlers._ingest_published_passages", ingest)
    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": "bge-m3", "embedding_dimension": 1024,
    })
    upsert = _patch_pending_repo(monkeypatch)

    # The stale payload still says "not excluded" — it was true when it was emitted.
    await handle_chapter_kg_indexed(
        _kg_indexed_event(revision_id=_REVISION, published_revision_id=None), pool=pool,
    )

    upsert.assert_not_awaited(), (
        "a stale/redelivered event resurrected a chapter the user had forgotten — the "
        "handler must re-check the LIVE kg_exclude state, not trust the payload"
    )
    ingest.assert_not_awaited()


@pytest.mark.asyncio
async def test_chapter_published_still_ingests_as_canon(monkeypatch):
    """Regression: the publish path is unchanged by the WS-0.8 refactor."""
    ingest = AsyncMock()
    monkeypatch.setattr("app.events.handlers._ingest_published_passages", ingest)

    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": "bge-m3", "embedding_dimension": 1024,
    })
    upsert = _patch_pending_repo(monkeypatch)

    await handle_chapter_published(_published_event(), pool=pool)

    assert ingest.await_args.kwargs["canon"] is True
    assert upsert.await_args.kwargs.get("event_type") == "chapter.published"


def _kg_indexed_event(revision_id=None, published_revision_id=None):
    payload = {"book_id": str(_BOOK), "chapter_id": str(_CHAPTER)}
    if revision_id is not None:
        payload["revision_id"] = str(revision_id)
    if published_revision_id is not None:
        payload["published_revision_id"] = str(published_revision_id)
    return _event(
        "chapter.kg_indexed", aggregate_id=str(_CHAPTER), payload=payload,
    )


# ── WS-0.8: unpublish NO LONGER retracts (spec §3.8 / acceptance #9 / D-R5) ──


@pytest.mark.asyncio
async def test_chapter_unpublished_does_not_retract_the_knowledge_graph(monkeypatch):
    """THE D-R5 LOCK. An EDITORIAL unpublish must NOT destroy the user's index.

    Publishing no longer gates the knowledge graph, so the old `canon = published`
    symmetry ("unpublish removes what publish added") is gone. A user who clicked
    "Add to knowledge" and later unpublished for ordinary editorial reasons must not
    silently lose their knowledge graph for that chapter — book-service still (correctly)
    reports it as indexed. Retraction is kg_exclude's job now.

    Instead the chapter's passages are DEMOTED to canon=False: it is still in the graph,
    but it is no longer canonical.
    """
    from contextlib import asynccontextmanager

    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={"project_id": _PROJECT, "user_id": _USER})

    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"

        @asynccontextmanager
        async def fake_session():
            yield MagicMock()

        remove_mock = AsyncMock(return_value=3)
        delete_mock = AsyncMock(return_value=7)
        set_canon_mock = AsyncMock(return_value=5)
        monkeypatch.setattr("app.db.neo4j.neo4j_session", fake_session)
        monkeypatch.setattr(
            "app.db.neo4j_repos.provenance.remove_evidence_for_natural_key", remove_mock,
        )
        monkeypatch.setattr(
            "app.db.neo4j_repos.passages.delete_passages_for_source", delete_mock,
        )
        monkeypatch.setattr(
            "app.db.neo4j_repos.passages.set_canon_for_source", set_canon_mock,
        )

        await handle_chapter_unpublished(_unpublished_event(), pool=pool)

    remove_mock.assert_not_awaited(), (
        "unpublish must NOT retract graph evidence — the user's 'add to knowledge' "
        "request survives an editorial unpublish (spec §3.8 / acceptance #9)"
    )
    delete_mock.assert_not_awaited(), (
        "unpublish must NOT delete passages — that would destroy the user's index"
    )
    pool.execute.assert_not_awaited(), (
        "unpublish must NOT drop the pending row — the queued extraction is still wanted"
    )

    # It DEMOTES instead: still indexed, no longer canonical.
    set_canon_mock.assert_awaited_once()
    ck = set_canon_mock.await_args.kwargs
    assert ck["canon"] is False
    assert ck["source_type"] == "chapter"
    assert ck["source_id"] == str(_CHAPTER)
    assert ck["user_id"] == str(_USER)


@pytest.mark.asyncio
async def test_chapter_unpublished_demotion_failure_is_non_fatal(monkeypatch):
    """A demotion failure must not raise — it self-heals on the next publish/index."""
    from contextlib import asynccontextmanager

    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={"project_id": _PROJECT, "user_id": _USER})

    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"

        @asynccontextmanager
        async def fake_session():
            yield MagicMock()

        monkeypatch.setattr("app.db.neo4j.neo4j_session", fake_session)
        monkeypatch.setattr(
            "app.db.neo4j_repos.passages.set_canon_for_source",
            AsyncMock(side_effect=RuntimeError("neo4j transient")),
        )

        await handle_chapter_unpublished(_unpublished_event(), pool=pool)  # must not raise


# ── WS-0.8: kg_excluded IS the retraction path now (spec §3.8 / P1-7) ──


@pytest.mark.asyncio
async def test_chapter_kg_excluded_retracts_graph_and_passages(monkeypatch):
    """The retraction that unpublish used to perform now hangs off kg_exclude.

    Without it the toggle would be a LIE: facts and passages extracted from a chapter
    the user later marks "forget this" would simply stay in the graph.
    """
    from contextlib import asynccontextmanager

    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={"project_id": _PROJECT, "user_id": _USER})

    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"

        @asynccontextmanager
        async def fake_session():
            yield MagicMock()

        remove_mock = AsyncMock(return_value=3)
        cleanup_mock = AsyncMock(return_value=MagicMock(total=2))
        delete_mock = AsyncMock(return_value=7)
        monkeypatch.setattr("app.db.neo4j.neo4j_session", fake_session)
        # Retract by NATURAL KEY (the helper hashes the ExtractionSource id) — a raw-id
        # call matches a hashed-id MATCH and removes ZERO edges.
        monkeypatch.setattr(
            "app.db.neo4j_repos.provenance.remove_evidence_for_natural_key", remove_mock,
        )
        # NO orphan sweep here: this handler runs OUTSIDE the one-active-job-per-project
        # extraction lock, so cleanup could race a concurrent extraction and delete an
        # in-flight node. The offline reconciler GCs them safely.
        monkeypatch.setattr(
            "app.db.neo4j_repos.provenance.cleanup_zero_evidence_nodes", cleanup_mock,
        )
        monkeypatch.setattr(
            "app.db.neo4j_repos.passages.delete_passages_for_source", delete_mock,
        )

        await handle_chapter_kg_excluded(_kg_excluded_event(), pool=pool)

    # The pending row is dropped FIRST, so an in-flight extraction cannot re-canonize
    # the chapter the user just excluded.
    pool.execute.assert_awaited()

    remove_mock.assert_awaited_once()
    rk = remove_mock.await_args.kwargs
    assert rk["source_type"] == "chapter"
    assert rk["source_id"] == str(_CHAPTER)
    assert rk["user_id"] == str(_USER)
    assert rk["project_id"] == str(_PROJECT)

    cleanup_mock.assert_not_awaited()

    delete_mock.assert_awaited_once()
    dk = delete_mock.await_args.kwargs
    assert dk["source_type"] == "chapter"
    assert dk["source_id"] == str(_CHAPTER)
    assert dk["user_id"] == str(_USER)


@pytest.mark.asyncio
async def test_chapter_kg_excluded_passage_retract_independent_of_graph_failure(
    monkeypatch,
):
    """R3-WARN#2 + review-impl P1.

    TWO properties, and they are both load-bearing:
      1. INDEPENDENCE — if the graph retract raises, the passage retract must STILL run,
         else the user's retracted prose lingers in the semantic index.
      2. IT MUST NOT ACK A FAILURE — the handler RE-RAISES at the end. Swallowing the
         error and ACKing meant the user's "forget this chapter" silently never happened:
         Neo4j blipped for one second and their facts stayed in the graph FOREVER, with
         nothing left to trigger another attempt. Raising sends it to the consumer's
         retry → DLQ path. Both retracts are idempotent, so redelivery is safe.
    """
    from contextlib import asynccontextmanager

    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={"project_id": _PROJECT, "user_id": _USER})

    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"

        @asynccontextmanager
        async def fake_session():
            yield MagicMock()

        remove_mock = AsyncMock(side_effect=RuntimeError("neo4j transient"))
        delete_mock = AsyncMock(return_value=7)
        monkeypatch.setattr("app.db.neo4j.neo4j_session", fake_session)
        monkeypatch.setattr(
            "app.db.neo4j_repos.provenance.remove_evidence_for_natural_key", remove_mock,
        )
        monkeypatch.setattr(
            "app.db.neo4j_repos.passages.delete_passages_for_source", delete_mock,
        )

        # (2) A partially-failed RETRACTION must NOT be acked.
        with pytest.raises(RuntimeError, match="retraction incomplete"):
            await handle_chapter_kg_excluded(_kg_excluded_event(), pool=pool)

    remove_mock.assert_awaited_once()
    # (1) It ran despite the graph-retract failure.
    delete_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_chapter_kg_excluded_success_does_not_raise(monkeypatch):
    """The happy path must still ACK cleanly — only a FAILED retraction retries."""
    from contextlib import asynccontextmanager

    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={"project_id": _PROJECT, "user_id": _USER})

    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"

        @asynccontextmanager
        async def fake_session():
            yield MagicMock()

        monkeypatch.setattr("app.db.neo4j.neo4j_session", fake_session)
        monkeypatch.setattr(
            "app.db.neo4j_repos.provenance.remove_evidence_for_natural_key",
            AsyncMock(return_value=3),
        )
        monkeypatch.setattr(
            "app.db.neo4j_repos.passages.delete_passages_for_source",
            AsyncMock(return_value=7),
        )

        await handle_chapter_kg_excluded(_kg_excluded_event(), pool=pool)  # no raise


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


# ── KG-ML M2: translation.published → dual-index vi passages ─────────


def _translation_event(book_id=str(_BOOK), chapter_id=str(_CHAPTER), lang="vi"):
    payload = {}
    if book_id:
        payload["book_id"] = book_id
    if chapter_id:
        payload["chapter_id"] = chapter_id
    if lang:
        payload["target_language"] = lang
    return EventData(
        stream="loreweave:events:translation",
        message_id="1-0",
        event_type="translation.published",
        aggregate_id=str(uuid4()),  # chapter_translation_id
        payload=payload,
        source="translation",
        raw={},
    )


@pytest.mark.asyncio
async def test_translation_published_dual_indexes_vi(monkeypatch):
    """M2: resolves project → fetches active vi text → ingests with
    text_override + source_lang='vi' (index-only). Never touches the graph
    queue (no extraction)."""
    from contextlib import asynccontextmanager

    pool, _conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": "bge-m3", "embedding_dimension": 1024,
    })
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
            "app.clients.embedding_client.get_embedding_client", lambda: MagicMock(),
        )
        tc = MagicMock()
        tc.get_active_translation_text = AsyncMock(return_value="Bá tước Dracula…")
        monkeypatch.setattr(
            "app.clients.translation_client.get_translation_client", lambda: tc,
        )

        await handle_translation_published(_translation_event(), pool=pool)

    ingest_mock.assert_awaited_once()
    kw = ingest_mock.await_args.kwargs
    assert kw["source_lang"] == "vi"
    assert kw["text_override"] == "Bá tước Dracula…"
    assert kw["canon"] is True
    assert kw["chapter_index"] == 7
    tc.get_active_translation_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_translation_published_skips_when_no_active_text(monkeypatch):
    """No active translation text for the language → no ingest (clean skip)."""
    pool, _conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": "bge-m3", "embedding_dimension": 1024,
    })
    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"
        ingest_mock = AsyncMock()
        monkeypatch.setattr(
            "app.extraction.passage_ingester.ingest_chapter_passages", ingest_mock,
        )
        tc = MagicMock()
        tc.get_active_translation_text = AsyncMock(return_value=None)
        monkeypatch.setattr(
            "app.clients.translation_client.get_translation_client", lambda: tc,
        )
        await handle_translation_published(_translation_event(), pool=pool)

    ingest_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_translation_published_skips_when_no_project(monkeypatch):
    """No knowledge project for the book → clean no-op, no translation fetch."""
    pool, _conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value=None)
    tc = MagicMock()
    tc.get_active_translation_text = AsyncMock()
    monkeypatch.setattr(
        "app.clients.translation_client.get_translation_client", lambda: tc,
    )
    await handle_translation_published(_translation_event(), pool=pool)

    pool.fetchrow.assert_called_once()
    tc.get_active_translation_text.assert_not_called()


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
