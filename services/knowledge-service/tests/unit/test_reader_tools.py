"""W11-M2 — the reader "ask the lore" tools' SECURITY properties (spec §4.2).

These are the properties a spoiler gate lives or dies by, driven through the real
execute_tool validate→dispatch path with the external reads mocked:
  * fail-closed — a reader with NO position sees an EMPTY windowed read, never all;
  * anti-oracle — a non-grantee gets a uniform "project not found";
  * resolve-to-owner — reads run as the OWNER, never the caller;
  * the glossary +1 inclusion — a reader AT chapter N sees N's canon (glossary is
    exclusive `<`), and facts are windowed with an int cutoff, never None (= no window).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from loreweave_grants import GrantLevel

from app.tools.executor import ToolContext, execute_tool

_OWNER = uuid4()
_READER = uuid4()          # a VIEW grantee, distinct from the owner
_BOOK = uuid4()
_PROJECT = uuid4()
_CHAPTER = uuid4()


def _mk_ctx(*, caller, grant_client, projects_repo, book_client) -> ToolContext:
    return ToolContext(
        user_id=caller,
        project_id=_PROJECT,
        session_id="sess-reader",
        projects_repo=projects_repo,
        pending_facts_repo=AsyncMock(),
        embedding_client=AsyncMock(),
        redis=None,
        book_client=book_client,
        reranker_client=AsyncMock(),
        grant_client=grant_client,
    )


def _repo(*, owner=_OWNER, book_id=_BOOK):
    repo = AsyncMock()
    repo.project_meta = AsyncMock(return_value=(owner, book_id))
    repo.get = AsyncMock(return_value=SimpleNamespace(
        project_id=_PROJECT, user_id=owner, book_id=book_id, name="X",
    ))
    return repo


def _grant(level=GrantLevel.OWNER):
    g = AsyncMock()
    g.resolve_grant = AsyncMock(return_value=level)
    return g


def _book_client(*, position=_CHAPTER, sort_order=5):
    bc = AsyncMock()
    bc.get_reading_position = AsyncMock(return_value=position)
    bc.get_chapter_sort_orders = AsyncMock(
        return_value=({_CHAPTER: sort_order} if position is not None else {})
    )
    return bc


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


# ── the review MED: null position → empty cast, glossary never called ────────
@pytest.mark.asyncio
async def test_browse_entities_null_position_returns_empty_cast():
    gc = MagicMock()
    gc.list_known_entities_for_chapter = AsyncMock(return_value=[{"name": "SpoilerChar"}])
    ctx = _mk_ctx(
        caller=_OWNER, grant_client=_grant(GrantLevel.OWNER),
        projects_repo=_repo(), book_client=_book_client(position=None),  # NO position
    )
    with patch("app.tools.reader_tools.get_glossary_client", return_value=gc):
        res = await execute_tool(ctx, "lore_browse_entities", {})
    assert res.success
    assert res.result["entities"] == []               # NOT the full cast
    assert res.result["window_available"] is False
    gc.list_known_entities_for_chapter.assert_not_called()  # never even queried


# ── the +1 inclusion + windowed happy path ───────────────────────────────────
@pytest.mark.asyncio
async def test_browse_entities_windows_glossary_at_before_plus_one():
    gc = MagicMock()
    gc.list_known_entities_for_chapter = AsyncMock(return_value=[{"name": "Alice"}])
    ctx = _mk_ctx(
        caller=_OWNER, grant_client=_grant(GrantLevel.OWNER),
        projects_repo=_repo(), book_client=_book_client(position=_CHAPTER, sort_order=5),
    )
    with patch("app.tools.reader_tools.get_glossary_client", return_value=gc):
        res = await execute_tool(ctx, "lore_browse_entities", {})
    assert res.success
    assert res.result["entities"] == [{"name": "Alice"}]
    # reader AT chapter 5 (inclusive) → glossary exclusive '<' → before_chapter_index=6
    _, kwargs = gc.list_known_entities_for_chapter.call_args
    assert kwargs["before_chapter_index"] == 6
    # recency_window=0 → the FULL met-so-far cast, not just the last ~100 chapters
    assert kwargs["recency_window"] == 0


@pytest.mark.asyncio
async def test_browse_entities_kind_filter_matches_kind_code():
    # The glossary row serializes the kind as `kind_code`; filtering on 'kind' would
    # drop every row. Prove the filter keeps a matching kind_code and drops others.
    gc = MagicMock()
    gc.list_known_entities_for_chapter = AsyncMock(return_value=[
        {"name": "Alice", "kind_code": "character"},
        {"name": "Rivertown", "kind_code": "location"},
    ])
    ctx = _mk_ctx(
        caller=_OWNER, grant_client=_grant(GrantLevel.OWNER),
        projects_repo=_repo(), book_client=_book_client(position=_CHAPTER, sort_order=5),
    )
    with patch("app.tools.reader_tools.get_glossary_client", return_value=gc):
        res = await execute_tool(ctx, "lore_browse_entities", {"kind": "character"})
    assert res.success
    assert [e["name"] for e in res.result["entities"]] == ["Alice"]


@pytest.mark.asyncio
async def test_reader_tools_unavailable_without_book_client():
    # A ToolContext with no book_client (a non-live surface) → clean tool error,
    # never an AttributeError-as-500. Mirrors the story_search guard.
    ctx = ToolContext(
        user_id=_OWNER, project_id=_PROJECT, session_id="s",
        projects_repo=_repo(), pending_facts_repo=AsyncMock(),
        embedding_client=AsyncMock(), redis=None,
        book_client=None, reranker_client=None, grant_client=_grant(GrantLevel.OWNER),
    )
    res = await execute_tool(ctx, "lore_browse_entities", {})
    assert not res.success
    assert "not available" in res.error.lower()


# ── resolve-to-owner: reads run as OWNER, not the calling reader ──────────────
@pytest.mark.asyncio
async def test_reads_run_as_owner_not_caller():
    gc = MagicMock()
    gc.list_known_entities_for_chapter = AsyncMock(return_value=[])
    with patch("app.tools.reader_tools.get_glossary_client", return_value=gc), \
         patch("app.tools.reader_tools.run_hybrid_search", new_callable=AsyncMock) as rhs:
        rhs.return_value = SimpleNamespace(hits=[{"snippet": "x", "sortOrder": 3}])
        ctx = _mk_ctx(
            caller=_READER,  # a VIEW grantee, NOT the owner
            grant_client=_grant(GrantLevel.VIEW),
            projects_repo=_repo(owner=_OWNER),
            book_client=_book_client(position=_CHAPTER, sort_order=5),
        )
        res = await execute_tool(ctx, "lore_ask", {"query": "who is Alice"})
    assert res.success
    # the RAG read ran as the OWNER (resolve-to-owner), never as the reader
    _, kwargs = rhs.call_args
    assert kwargs["user_id"] == _OWNER
    assert kwargs["before_sort_order"] == 5
    # and the reader's OWN position was fetched (ctx.user_id = the reader)
    ctx.book_client.get_reading_position.assert_awaited_once_with(_BOOK, _READER)


# ── anti-oracle: a non-grantee gets a uniform refusal ────────────────────────
@pytest.mark.asyncio
async def test_non_grantee_gets_anti_oracle_refusal():
    ctx = _mk_ctx(
        caller=_READER, grant_client=_grant(GrantLevel.NONE),  # no access
        projects_repo=_repo(owner=_OWNER), book_client=_book_client(),
    )
    res = await execute_tool(ctx, "lore_browse_entities", {})
    assert not res.success
    assert "project not found" in res.error.lower()  # no existence oracle


# ── fail-closed facts: lore_entity passes an INT cutoff, never None, project-scoped
@pytest.mark.asyncio
async def test_entity_facts_windowed_with_int_cutoff_never_none():
    with patch("app.tools.reader_tools.neo4j_session", new=lambda: _noop_session()), \
         patch("app.tools.reader_tools.resolve_kg_entity_id_by_glossary_id",
               new_callable=AsyncMock) as resolve, \
         patch("app.tools.reader_tools.list_facts_for_entity", new_callable=AsyncMock) as facts, \
         patch("app.tools.reader_tools.statuses_detail_at_order", new_callable=AsyncMock) as st:
        resolve.return_value = "kg-sha-123"  # the glossary id resolves to a KG node
        facts.return_value = []
        st.return_value = {}
        # null position → before_order must be -1 (fail-closed), NOT None (= no window)
        ctx = _mk_ctx(
            caller=_OWNER, grant_client=_grant(GrantLevel.OWNER),
            projects_repo=_repo(), book_client=_book_client(position=None),
        )
        res = await execute_tool(ctx, "lore_entity", {"entity_id": "glossary-uuid"})
    assert res.success
    # the glossary id was resolved to a KG id, project-scoped (tenant-safe)
    _, rkwargs = resolve.call_args
    assert rkwargs["glossary_entity_id"] == "glossary-uuid"
    assert rkwargs["project_id"] == str(_PROJECT)
    # the KG reads used the RESOLVED id, an int fail-closed cutoff, and project scope
    _, fkwargs = facts.call_args
    assert fkwargs["entity_id"] == "kg-sha-123"
    assert fkwargs["before_order"] == -1 and fkwargs["before_order"] is not None
    assert fkwargs["project_id"] == str(_PROJECT)
    _, skwargs = st.call_args
    assert skwargs["at_order"] == -1
    assert skwargs["entity_ids"] == ["kg-sha-123"]


@pytest.mark.asyncio
async def test_entity_with_no_kg_anchor_returns_empty_not_wrong_active():
    # A canon entity with no KG anchor (or an id outside this project) → resolve None
    # → no KG reads at all, honest empty result (NOT a silent wrong 'active'/[]).
    with patch("app.tools.reader_tools.neo4j_session", new=lambda: _noop_session()), \
         patch("app.tools.reader_tools.resolve_kg_entity_id_by_glossary_id",
               new_callable=AsyncMock) as resolve, \
         patch("app.tools.reader_tools.list_facts_for_entity", new_callable=AsyncMock) as facts, \
         patch("app.tools.reader_tools.statuses_detail_at_order", new_callable=AsyncMock) as st:
        resolve.return_value = None
        ctx = _mk_ctx(
            caller=_OWNER, grant_client=_grant(GrantLevel.OWNER),
            projects_repo=_repo(), book_client=_book_client(position=_CHAPTER, sort_order=5),
        )
        res = await execute_tool(ctx, "lore_entity", {"entity_id": "unanchored"})
    assert res.success
    assert res.result["kg_entity_id"] is None
    assert res.result["facts"] == []
    facts.assert_not_called()  # no KG read on an unresolved id
    st.assert_not_called()


# ── fail-closed timeline: null position → no events ──────────────────────────
@pytest.mark.asyncio
async def test_timeline_null_position_is_empty():
    with patch("app.tools.reader_tools.list_events_filtered", new_callable=AsyncMock) as ev:
        ev.return_value = ([SimpleNamespace(model_dump=lambda mode: {})], 1)
        ctx = _mk_ctx(
            caller=_OWNER, grant_client=_grant(GrantLevel.OWNER),
            projects_repo=_repo(), book_client=_book_client(position=None),
        )
        res = await execute_tool(ctx, "lore_timeline", {})
    assert res.success
    assert res.result["events"] == []
    assert res.result["total"] == 0
    ev.assert_not_called()  # the query is skipped entirely on an unpinned position
