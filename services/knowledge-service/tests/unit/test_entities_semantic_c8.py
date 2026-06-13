"""C8 — unit tests for the entities semantic layer.

Covers the additive C8 surface on GET /v1/knowledge/entities:
  - DERIVED `status` field on the Entity projection (3 precedence cases)
  - `status` filter param threaded to the repo
  - `sort_by=anchor_score` threaded to the repo (+ 422 on bad value)
  - `semantic_query` VECTOR path: provider-registry embed resolution,
    project-required, FTS-mutually-exclusive, not-indexed, 404, and a
    real vector-ranked result list.

Neo4j + provider-registry are mocked; the live cross-service proof is
the VERIFY-phase live-smoke on a built graph.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.neo4j_repos.entities import Entity, VectorSearchHit


_TEST_USER = uuid4()
_PROJECT_ID = uuid4()


def _entity(
    *,
    name: str = "Zhang Ruochen",
    glossary_entity_id: str | None = None,
    archived_at: datetime | None = None,
    kind: str = "character",
    anchor_score: float = 0.0,
) -> Entity:
    return Entity(
        id=f"ent-{name}",
        user_id=str(_TEST_USER),
        project_id=str(_PROJECT_ID),
        name=name,
        canonical_name=name.lower(),
        kind=kind,
        aliases=[name],
        glossary_entity_id=glossary_entity_id,
        archived_at=archived_at,
        anchor_score=anchor_score,
        mention_count=10,
        confidence=0.9,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _make_client():
    from app.main import app
    from app.middleware.jwt_auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    return TestClient(app, raise_server_exceptions=False)


# ── DERIVED status (model-level precedence) ──────────────────────────


def test_status_discovered_when_unanchored_and_active():
    assert _entity().status == "discovered"


def test_status_canonical_when_glossary_linked():
    assert _entity(glossary_entity_id="g-1").status == "canonical"


def test_status_archived_when_archived_at_set():
    assert _entity(archived_at=datetime.now(timezone.utc)).status == "archived"


def test_status_archived_wins_over_canonical_precedence():
    """C8-entity-status LOCKED precedence: archived > canonical. If a
    future write leaves both set, archived must win (it's out of the
    active retrieval set)."""
    e = _entity(
        glossary_entity_id="g-1",
        archived_at=datetime.now(timezone.utc),
    )
    assert e.status == "archived"


def test_status_serialized_in_api_payload():
    """The computed field must round-trip through the JSON response."""
    with patch(
        "app.routers.public.entities.list_entities_filtered",
        new_callable=AsyncMock,
        return_value=([_entity(glossary_entity_id="g-9")], 1),
    ), patch(
        "app.routers.public.entities.neo4j_session", new=lambda: _noop_session()
    ):
        client = _make_client()
        resp = client.get("/v1/knowledge/entities")
    assert resp.status_code == 200, resp.json()
    assert resp.json()["entities"][0]["status"] == "canonical"


# ── status filter + sort_by passthrough ──────────────────────────────


@patch(
    "app.routers.public.entities.list_entities_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_status_filter_threaded_to_repo(mock_list):
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get("/v1/knowledge/entities?status=discovered")
    assert resp.status_code == 200
    assert mock_list.await_args.kwargs["status"] == "discovered"


@patch(
    "app.routers.public.entities.list_entities_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_status_filter_rejects_unknown_value(mock_list):
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get("/v1/knowledge/entities?status=bogus")
    assert resp.status_code == 422
    mock_list.assert_not_awaited()


@patch(
    "app.routers.public.entities.list_entities_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_sort_by_anchor_score_threaded_to_repo(mock_list):
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get("/v1/knowledge/entities?sort_by=anchor_score")
    assert resp.status_code == 200
    assert mock_list.await_args.kwargs["sort_by"] == "anchor_score"


@patch(
    "app.routers.public.entities.list_entities_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_sort_by_defaults_to_mention_count(mock_list):
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get("/v1/knowledge/entities")
    assert resp.status_code == 200
    assert mock_list.await_args.kwargs["sort_by"] == "mention_count"


@patch(
    "app.routers.public.entities.list_entities_filtered", new_callable=AsyncMock
)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_sort_by_rejects_unknown_value(mock_list):
    mock_list.return_value = ([], 0)
    client = _make_client()
    resp = client.get("/v1/knowledge/entities?sort_by=confidence")
    assert resp.status_code == 422
    mock_list.assert_not_awaited()


# ── semantic_query VECTOR path ───────────────────────────────────────


def _project_stub(embedding_model="emb-model-ref", embedding_dimension=1024):
    p = MagicMock()
    p.embedding_model = embedding_model
    p.embedding_dimension = embedding_dimension
    return p


def _embed_result(dim=1024):
    r = MagicMock()
    r.embeddings = [[0.1] * dim]
    return r


def _patch_semantic_deps(projects_repo, embed_client):
    """C8 semantic deps are resolved lazily inside the route (not eager
    Depends) so the plain-browse path never stands up the pool. Patch
    the module-level getter references the route calls.

    BOTH getters are ASYNC in app.deps (the route `await`s them), so the
    patches MUST be AsyncMocks — a sync lambda here would mask the
    `await get_embedding_client()` requirement (live-smoke caught exactly
    this mock-vs-real drift)."""
    return (
        patch(
            "app.routers.public.entities.get_projects_repo",
            new=AsyncMock(return_value=projects_repo),
        ),
        patch(
            "app.routers.public.entities.get_embedding_client",
            new=AsyncMock(return_value=embed_client),
        ),
    )


@patch("app.routers.public.entities.find_entities_by_vector", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_semantic_query_returns_vector_ranked_results(mock_vec):
    """The happy path: project has an embedding model → query is embedded
    via the BYOK provider-registry model_ref → vector hits returned."""
    mock_vec.return_value = [
        VectorSearchHit(entity=_entity(name="Zhang Ruochen"), raw_score=0.91, weighted_score=0.91),
        VectorSearchHit(entity=_entity(name="Black Tortoise"), raw_score=0.77, weighted_score=0.62),
    ]
    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=_project_stub())
    embed_client = AsyncMock()
    embed_client.embed = AsyncMock(return_value=_embed_result())

    p1, p2 = _patch_semantic_deps(projects_repo, embed_client)
    client = _make_client()
    with p1, p2:
        resp = client.get(
            f"/v1/knowledge/entities?project_id={_PROJECT_ID}&semantic_query=神器"
        )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert [e["name"] for e in body["entities"]] == ["Zhang Ruochen", "Black Tortoise"]
    assert body["embedding_model"] == "emb-model-ref"
    # PROVIDER INVARIANT: the embed call resolved the model via the
    # project's model_ref (provider-registry), NOT a hardcoded name.
    assert embed_client.embed.await_args.kwargs["model_ref"] == "emb-model-ref"
    assert embed_client.embed.await_args.kwargs["model_source"] == "user_model"


def test_semantic_query_requires_project_id():
    client = _make_client()
    resp = client.get("/v1/knowledge/entities?semantic_query=神器")
    assert resp.status_code == 422
    assert "project_id" in resp.json()["detail"]


def test_semantic_query_mutually_exclusive_with_search():
    client = _make_client()
    resp = client.get(
        f"/v1/knowledge/entities?project_id={_PROJECT_ID}"
        f"&semantic_query=神器&search=zhang"
    )
    assert resp.status_code == 422


@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_semantic_query_project_not_found_404():
    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=None)
    p1, p2 = _patch_semantic_deps(projects_repo, AsyncMock())
    client = _make_client()
    with p1, p2:
        resp = client.get(
            f"/v1/knowledge/entities?project_id={_PROJECT_ID}&semantic_query=神器"
        )
    assert resp.status_code == 404


@patch("app.routers.public.entities.find_entities_by_vector", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_semantic_query_not_indexed_returns_empty(mock_vec):
    """Project with no embedding model → empty + null model (FE shows
    'not indexed yet'), and no vector call is made."""
    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=_project_stub(embedding_model=None, embedding_dimension=None))
    p1, p2 = _patch_semantic_deps(projects_repo, AsyncMock())
    client = _make_client()
    with p1, p2:
        resp = client.get(
            f"/v1/knowledge/entities?project_id={_PROJECT_ID}&semantic_query=神器"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["entities"] == []
    assert body["embedding_model"] is None
    mock_vec.assert_not_awaited()


@patch("app.routers.public.entities.find_entities_by_vector", new_callable=AsyncMock)
@patch("app.routers.public.entities.neo4j_session", new=lambda: _noop_session())
def test_semantic_query_status_filter_applied_post_vector(mock_vec):
    """status filter narrows the vector result set by derived status."""
    from app.main import app
    from app.deps import get_projects_repo, get_embedding_client

    mock_vec.return_value = [
        VectorSearchHit(entity=_entity(name="Canon", glossary_entity_id="g-1"), raw_score=0.9, weighted_score=0.9),
        VectorSearchHit(entity=_entity(name="Disc"), raw_score=0.8, weighted_score=0.4),
    ]
    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=_project_stub())
    embed_client = AsyncMock()
    embed_client.embed = AsyncMock(return_value=_embed_result())
    p1, p2 = _patch_semantic_deps(projects_repo, embed_client)
    client = _make_client()
    with p1, p2:
        resp = client.get(
            f"/v1/knowledge/entities?project_id={_PROJECT_ID}"
            f"&semantic_query=神器&status=canonical"
        )
    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()["entities"]]
    assert names == ["Canon"]
