"""mui #4 K-2 — unit tests for the semantic-first wiring in
select_glossary_for_context (chat path). Verifies: no embedding_client →
FTS (semantic skipped); semantic-first merges pinned ahead; empty semantic
falls back to FTS. select_glossary_semantic + neo4j_session are patched so
no embed/Neo4j is touched.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.clients.glossary_client import GlossaryEntityForContext
from app.context.selectors import glossary as gsel

USER = uuid4()
PROJECT = uuid4()
BOOK = uuid4()


def _ctx(eid: str, tier: str = "semantic") -> GlossaryEntityForContext:
    return GlossaryEntityForContext(entity_id=eid, kind_code="character", tier=tier)


class _FakeSession:
    async def __aenter__(self):
        return MagicMock()

    async def __aexit__(self, *a):
        return False


def _fake_session():
    return _FakeSession()


def _proj():
    return SimpleNamespace(
        book_id=BOOK, embedding_model="emb-uuid", embedding_dimension=1024,
        project_id=PROJECT,
    )


@pytest.mark.asyncio
async def test_no_embedding_client_skips_semantic_uses_fts(monkeypatch):
    sem = AsyncMock()
    monkeypatch.setattr(gsel, "select_glossary_semantic", sem)
    client = MagicMock()
    client.select_for_context = AsyncMock(return_value=[_ctx("e-fts", tier="recent")])

    out = await gsel.select_glossary_for_context(
        client, user_id=USER, project=_proj(), message="", embedding_client=None,
    )

    sem.assert_not_awaited()  # semantic never attempted without an embed client
    assert [e.entity_id for e in out] == ["e-fts"]


@pytest.mark.asyncio
async def test_semantic_first_merges_pinned_ahead(monkeypatch):
    monkeypatch.setattr(gsel, "neo4j_session", _fake_session)
    monkeypatch.setattr(
        gsel, "select_glossary_semantic",
        AsyncMock(return_value=[_ctx("e-sem", tier="semantic")]),
    )
    client = MagicMock()
    # empty-query select-for-context returns pinned + recent; only pinned kept.
    client.select_for_context = AsyncMock(
        return_value=[_ctx("e-pin", tier="pinned"), _ctx("e-rec", tier="recent")]
    )

    out = await gsel.select_glossary_for_context(
        client, user_id=USER, project=_proj(), message="封神之人",
        embedding_client=MagicMock(),
    )

    # pinned ahead, then semantic; the recent row (not pinned) is dropped (AC3).
    assert [e.entity_id for e in out] == ["e-pin", "e-sem"]


@pytest.mark.asyncio
async def test_empty_semantic_falls_back_to_fts(monkeypatch):
    monkeypatch.setattr(gsel, "neo4j_session", _fake_session)
    monkeypatch.setattr(gsel, "select_glossary_semantic", AsyncMock(return_value=[]))
    client = MagicMock()
    client.select_for_context = AsyncMock(return_value=[_ctx("e-fts", tier="recent")])

    out = await gsel.select_glossary_for_context(
        client, user_id=USER, project=_proj(), message="",
        embedding_client=MagicMock(),
    )

    # semantic empty → FTS path (single empty-query call); pinned not fetched.
    assert [e.entity_id for e in out] == ["e-fts"]
    assert client.select_for_context.await_count == 1
