"""The KG neighborhood endpoint the gateway has always called and nobody ever served.

`kal-read.controller.ts` builds `/internal/books/{id}/kg/neighborhood`, and the route it backs
is published in `contracts/api/knowledge-gateway/kal.v1.yaml` — so the spec advertised a 404.
These tests pin the contract the gateway actually depends on: the `Edge` projection, the
cold-start 200, the `hops` refusal, and the `as_of` drop.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.routers import internal_kg_neighborhood as mod

_BOOK = uuid4()
_PROJECT = uuid4()
_USER = uuid4()
_ENTITY = str(uuid4())
_TOKEN = "test-internal-token"


@pytest.fixture
def app(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "internal_service_token", _TOKEN, raising=False)
    monkeypatch.setattr(settings, "neo4j_uri", "bolt://test:7687", raising=False)
    a = FastAPI()
    a.include_router(mod.router)
    return a


@pytest.fixture
def client(app):
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t",
        headers={"X-Internal-Token": _TOKEN},
    )


def _pool(row):
    p = MagicMock()
    p.fetchrow = AsyncMock(return_value=row)
    return p


_LIVE_PROJECT = {"project_id": _PROJECT, "user_id": _USER}


@asynccontextmanager
async def _session():
    yield MagicMock()


def _detail(relations, truncated=False, total=0):
    d = MagicMock()
    d.relations = relations
    d.relations_truncated = truncated
    d.total_relations = total
    return d


def _rel(subject, obj, predicate="knows", vf=None, vt=None):
    r = MagicMock()
    r.subject_id, r.object_id, r.predicate = subject, obj, predicate
    r.valid_from_ordinal, r.valid_to_ordinal = vf, vt
    return r


@pytest.mark.asyncio
async def test_returns_edges_in_the_published_shape(client, monkeypatch):
    """`from_entity`/`to_entity` carry direction explicitly.

    The gateway reads `data.edges` and forwards it verbatim, so the field names here ARE the
    public contract — a rename would break the FE with a 200.
    """
    monkeypatch.setattr(mod, "get_knowledge_pool", lambda: _pool(_LIVE_PROJECT))
    with patch("app.db.graph.graph_session", _session), \
         patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.neighborhood",
               autospec=True,
               return_value=_detail([_rel("a", "b", "mentors", vf=3, vt=None)], total=1)):
        async with client as c:
            r = await c.get(f"/internal/books/{_BOOK}/kg/neighborhood?entity_id={_ENTITY}")
    assert r.status_code == 200
    body = r.json()
    assert body["edges"] == [{
        "predicate": "mentors", "from_entity": "a", "to_entity": "b",
        "valid_from_ordinal": 3, "valid_to_ordinal": None,
    }]
    assert body["temporal_capability"]["glossary"] == "ordinal_valid_time"


@pytest.mark.asyncio
async def test_the_project_scope_reaches_the_graph_read(client, monkeypatch):
    """The glossary FK is unique per (user, project) — an unscoped lookup returns an
    arbitrary project's node. The same defect that put every lifecycle archive in the DLQ."""
    monkeypatch.setattr(mod, "get_knowledge_pool", lambda: _pool(_LIVE_PROJECT))
    with patch("app.db.graph.graph_session", _session), \
         patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.neighborhood",
               autospec=True, return_value=_detail([])) as read:
        async with client as c:
            await c.get(f"/internal/books/{_BOOK}/kg/neighborhood?entity_id={_ENTITY}&cap=7")
    kwargs = read.await_args.kwargs
    assert kwargs["project_id"] == str(_PROJECT)
    assert kwargs["user_id"] == str(_USER)
    assert kwargs["rel_cap"] == 7


@pytest.mark.asyncio
async def test_cap_is_clamped_to_the_contract_ceiling(client, monkeypatch):
    """An uncapped neighbourhood on a hub entity is how a prompt budget disappears."""
    monkeypatch.setattr(mod, "get_knowledge_pool", lambda: _pool(_LIVE_PROJECT))
    with patch("app.db.graph.graph_session", _session), \
         patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.neighborhood",
               autospec=True, return_value=_detail([])) as read:
        async with client as c:
            await c.get(f"/internal/books/{_BOOK}/kg/neighborhood?entity_id={_ENTITY}&cap=9999")
    assert read.await_args.kwargs["rel_cap"] == mod._MAX_CAP


@pytest.mark.asyncio
async def test_a_book_with_no_kg_project_is_an_empty_200(client, monkeypatch):
    """Cold start is the expected answer for most books, not an error. A 404 would force
    every caller to treat a normal state as a failure."""
    monkeypatch.setattr(mod, "get_knowledge_pool", lambda: _pool(None))
    async with client as c:
        r = await c.get(f"/internal/books/{_BOOK}/kg/neighborhood?entity_id={_ENTITY}")
    assert r.status_code == 200
    assert r.json()["edges"] == []


@pytest.mark.asyncio
async def test_an_entity_with_no_kg_node_is_an_empty_200(client, monkeypatch):
    """A glossary entity that was never synced into the graph is empty, not missing."""
    monkeypatch.setattr(mod, "get_knowledge_pool", lambda: _pool(_LIVE_PROJECT))
    with patch("app.db.graph.graph_session", _session), \
         patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.neighborhood",
               autospec=True, return_value=None):
        async with client as c:
            r = await c.get(f"/internal/books/{_BOOK}/kg/neighborhood?entity_id={_ENTITY}")
    assert r.status_code == 200
    assert r.json()["edges"] == []


@pytest.mark.asyncio
async def test_multi_hop_is_refused_not_silently_narrowed(client, monkeypatch):
    """The port is one-hop. Answering a 2-hop request with 1-hop edges hands back a
    truthful-looking subgraph missing half of what was asked for, and the caller cannot tell.
    The contract was narrowed to `maximum: 1` rather than the endpoint pretending."""
    monkeypatch.setattr(mod, "get_knowledge_pool", lambda: _pool(_LIVE_PROJECT))
    async with client as c:
        r = await c.get(f"/internal/books/{_BOOK}/kg/neighborhood?entity_id={_ENTITY}&hops=2")
    assert r.status_code == 422
    assert "1 hop" in r.text


@pytest.mark.asyncio
async def test_as_of_is_dropped_when_the_kg_cannot_honour_it(client, monkeypatch):
    """Dropping the filter loses precision; honouring it dishonestly loses the reader's plot.
    `temporal_capability.kg` is how the caller learns which happened (T26)."""
    from app.config import settings

    monkeypatch.setattr(settings, "kg_temporal_enabled", False, raising=False)
    monkeypatch.setattr(mod, "get_knowledge_pool", lambda: _pool(_LIVE_PROJECT))
    with patch("app.db.graph.graph_session", _session), \
         patch("app.adapters.neo4j_graph_store.Neo4jGraphStore.neighborhood",
               autospec=True, return_value=_detail([])):
        async with client as c:
            r = await c.get(
                f"/internal/books/{_BOOK}/kg/neighborhood?entity_id={_ENTITY}&as_of_chapter=12"
            )
    assert r.status_code == 200
    assert r.json()["temporal_capability"]["kg"] == "temporal_unsupported"


@pytest.mark.asyncio
async def test_the_endpoint_the_gateway_builds_actually_exists(app):
    """The whole point. `kal-read.controller.ts` builds this exact path, and for the life of
    the route nothing served it — including in a published OpenAPI contract."""
    paths = {r.path for r in app.routes}
    assert "/internal/books/{book_id}/kg/neighborhood" in paths
