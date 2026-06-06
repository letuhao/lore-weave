"""mui #4 LOW-1 — unit tests for the POST /internal/context/glossary-semantic
endpoint handler (project resolution + degrade-to-empty). Calls the route
function directly with mocked deps; neo4j_session + select_glossary_semantic
are patched so no Neo4j/embed is touched.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.clients.glossary_client import GlossaryEntityForContext
from app.routers import context as ctx

USER = uuid4()
PROJECT = uuid4()
BOOK = uuid4()


class _FakeSession:
    async def __aenter__(self):
        return MagicMock()

    async def __aexit__(self, *a):
        return False


def _req():
    return ctx.GlossarySemanticRequest(user_id=USER, project_id=PROJECT, query="封神之人")


def _repo(project):
    repo = MagicMock()
    repo.get = AsyncMock(return_value=project)
    return repo


async def _call(monkeypatch, *, project, semantic_return=None):
    monkeypatch.setattr(ctx, "neo4j_session", lambda: _FakeSession())
    sem = AsyncMock(return_value=semantic_return or [])
    monkeypatch.setattr(ctx, "select_glossary_semantic", sem)
    resp = await ctx.glossary_semantic(
        _req(),
        projects_repo=_repo(project),
        glossary_client=MagicMock(),
        embedding_client=MagicMock(),
    )
    return resp, sem


@pytest.mark.asyncio
async def test_missing_project_returns_empty(monkeypatch):
    resp, sem = await _call(monkeypatch, project=None)
    assert resp.items == []
    sem.assert_not_awaited()  # no project → never runs semantic


@pytest.mark.asyncio
async def test_project_without_book_returns_empty(monkeypatch):
    proj = SimpleNamespace(book_id=None, embedding_model="m", embedding_dimension=1024, project_id=PROJECT)
    resp, sem = await _call(monkeypatch, project=proj)
    assert resp.items == []
    sem.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_without_embedding_model_returns_empty(monkeypatch):
    proj = SimpleNamespace(book_id=BOOK, embedding_model=None, embedding_dimension=None, project_id=PROJECT)
    resp, sem = await _call(monkeypatch, project=proj)
    assert resp.items == []
    sem.assert_not_awaited()


@pytest.mark.asyncio
async def test_happy_path_returns_semantic_items(monkeypatch):
    proj = SimpleNamespace(book_id=BOOK, embedding_model="m", embedding_dimension=1024, project_id=PROJECT)
    row = GlossaryEntityForContext(entity_id="g1", cached_name="姜子牙", kind_code="character", tier="semantic")
    resp, sem = await _call(monkeypatch, project=proj, semantic_return=[row])
    assert [e.entity_id for e in resp.items] == ["g1"]
    sem.assert_awaited_once()
