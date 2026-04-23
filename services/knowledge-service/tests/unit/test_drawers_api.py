"""K19e.5 — unit tests for the public drawer (passage) search endpoint.

Mocks ProjectsRepo, EmbeddingClient, and find_passages_by_vector.
Covers: happy path, cross-user 404, no-embedding-configured empty,
unsupported-dim empty, whitespace query short-circuit, EmbeddingError
→ 502, empty-embedding short-circuit, dim-mismatch ValueError → 502,
limit forwarding, query length validation.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.clients.embedding_client import EmbeddingError, EmbeddingResult
from app.db.models import Project
from app.db.neo4j_repos.passages import Passage, PassageSearchHit


_TEST_USER = uuid4()
_PROJECT_ID = uuid4()


def _project_stub(
    embedding_model: str | None = "bge-m3",
    embedding_dimension: int | None = 1024,
) -> Project:
    return Project(
        project_id=_PROJECT_ID,
        user_id=_TEST_USER,
        name="Crimson Echoes",
        description="",
        project_type="book",
        book_id=None,
        instructions="",
        extraction_enabled=False,
        extraction_status="disabled",
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        extraction_config={},
        last_extracted_at=None,
        estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"),
        is_archived=False,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _passage_stub(chunk_index: int = 0, text: str = "A bridge duel.") -> Passage:
    return Passage(
        id=f"pg-{chunk_index}",
        user_id=str(_TEST_USER),
        project_id=str(_PROJECT_ID),
        source_type="chapter",
        source_id="ch-12",
        chunk_index=chunk_index,
        text=text,
        embedding_model="bge-m3",
        is_hub=False,
        chapter_index=12,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _hit_stub(chunk_index: int = 0, score: float = 0.87) -> PassageSearchHit:
    return PassageSearchHit(
        passage=_passage_stub(chunk_index=chunk_index),
        raw_score=score,
        vector=None,
    )


@asynccontextmanager
async def _noop_session():
    yield MagicMock()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


_SENTINEL_DEFAULT_PROJECT = object()


def _make_client(
    project=_SENTINEL_DEFAULT_PROJECT,
    embed_return: EmbeddingResult | None = None,
    embed_raises: Exception | None = None,
):
    """Installs dependency overrides for the two collaborators the
    handler reaches for via Depends. Returns (client, projects_repo,
    embedding_client) so tests can inspect the mocks.

    The ``project`` default uses a sentinel rather than calling
    ``_project_stub()`` at module load (classic Python mutable-default
    footgun: every test that takes the default would share the same
    Project instance and a mutation by one test would leak into the
    next). ``None`` is a valid caller value (cross-user 404 test) so
    the sentinel disambiguates "default" from "explicitly None"."""
    if project is _SENTINEL_DEFAULT_PROJECT:
        project = _project_stub()
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    from app.deps import get_embedding_client, get_projects_repo

    projects_repo = MagicMock()
    projects_repo.get = AsyncMock(return_value=project)

    embedding_client = MagicMock()
    if embed_raises is not None:
        embedding_client.embed = AsyncMock(side_effect=embed_raises)
    else:
        embedding_client.embed = AsyncMock(
            return_value=embed_return
            or EmbeddingResult(
                embeddings=[[0.1] * 1024],
                dimension=1024,
                model="bge-m3",
            )
        )

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_embedding_client] = lambda: embedding_client
    return (
        TestClient(app, raise_server_exceptions=False),
        projects_repo,
        embedding_client,
    )


# ── happy path ───────────────────────────────────────────────────────


@patch(
    "app.routers.public.drawers.find_passages_by_vector",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.drawers.neo4j_session", new=lambda: _noop_session()
)
def test_drawers_happy(mock_find):
    mock_find.return_value = [_hit_stub(0, 0.9), _hit_stub(1, 0.8)]
    client, projects_repo, embedding_client = _make_client()
    resp = client.get(
        f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}"
        f"&query=bridge+duel"
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    assert body["embedding_model"] == "bge-m3"
    assert len(body["hits"]) == 2
    assert body["hits"][0]["raw_score"] == 0.9
    assert body["hits"][0]["id"] == "pg-0"
    # Default limit threaded through.
    call = mock_find.await_args.kwargs
    assert call["limit"] == 40
    assert call["dim"] == 1024
    assert call["embedding_model"] == "bge-m3"
    # Review-impl C5: vectors MUST stay off the public wire (dropping
    # to False would add ~4 KB × dim per hit). Lock it at unit level.
    assert call["include_vectors"] is False
    # Embedding client was called with the project's BYOK model.
    ec = embedding_client.embed.await_args.kwargs
    assert ec["model_ref"] == "bge-m3"
    assert ec["model_source"] == "user_model"
    assert ec["texts"] == ["bridge duel"]


@patch(
    "app.routers.public.drawers.find_passages_by_vector",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.drawers.neo4j_session", new=lambda: _noop_session()
)
def test_drawers_limit_forwarded(mock_find):
    mock_find.return_value = []
    client, _, _ = _make_client()
    resp = client.get(
        f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}"
        f"&query=test&limit=25"
    )
    assert resp.status_code == 200
    assert mock_find.await_args.kwargs["limit"] == 25


# ── empty-state branches ─────────────────────────────────────────────


@patch(
    "app.routers.public.drawers.find_passages_by_vector",
    new_callable=AsyncMock,
)
def test_drawers_whitespace_query_short_circuits(mock_find):
    """Whitespace-only query returns empty WITHOUT touching the
    embedding client — saves a provider-registry round-trip."""
    client, projects_repo, embedding_client = _make_client()
    resp = client.get(
        f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}&query=%20%20%20"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["hits"] == []
    assert body["embedding_model"] is None
    embedding_client.embed.assert_not_awaited()
    mock_find.assert_not_awaited()
    projects_repo.get.assert_not_awaited()


@patch(
    "app.routers.public.drawers.find_passages_by_vector",
    new_callable=AsyncMock,
)
def test_drawers_no_embedding_model_configured_returns_empty(mock_find):
    client, _, embedding_client = _make_client(
        project=_project_stub(embedding_model=None, embedding_dimension=None),
    )
    resp = client.get(
        f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}&query=test"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["hits"] == []
    assert body["embedding_model"] is None
    # No embed call, no vector search.
    embedding_client.embed.assert_not_awaited()
    mock_find.assert_not_awaited()


@patch(
    "app.routers.public.drawers.find_passages_by_vector",
    new_callable=AsyncMock,
)
def test_drawers_unsupported_dim_returns_empty(mock_find):
    """Project configured with a dim outside SUPPORTED_PASSAGE_DIMS
    (e.g. data drift) returns empty with the model name surfaced so
    the FE can log it."""
    client, _, embedding_client = _make_client(
        project=_project_stub(embedding_model="custom-999", embedding_dimension=999),
    )
    resp = client.get(
        f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}&query=test"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["hits"] == []
    assert body["embedding_model"] == "custom-999"
    embedding_client.embed.assert_not_awaited()
    mock_find.assert_not_awaited()


@patch(
    "app.routers.public.drawers.find_passages_by_vector",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.drawers.neo4j_session", new=lambda: _noop_session()
)
def test_drawers_embedding_returns_empty_vectors(mock_find):
    """Provider returned 200 OK but no embeddings — treat as empty."""
    mock_find.return_value = []
    client, _, _ = _make_client(
        embed_return=EmbeddingResult(
            embeddings=[],
            dimension=1024,
            model="bge-m3",
        ),
    )
    resp = client.get(
        f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}&query=test"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["hits"] == []
    assert body["embedding_model"] == "bge-m3"
    mock_find.assert_not_awaited()


# ── error branches ───────────────────────────────────────────────────


def test_drawers_cross_user_project_404():
    client, _, _ = _make_client(project=None)
    resp = client.get(
        f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}&query=test"
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "project not found"


@patch(
    "app.routers.public.drawers.find_passages_by_vector",
    new_callable=AsyncMock,
)
def test_drawers_embedding_error_502(mock_find):
    client, _, _ = _make_client(
        embed_raises=EmbeddingError("provider timeout", retryable=True),
    )
    resp = client.get(
        f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}&query=test"
    )
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["error_code"] == "provider_error"
    assert "timeout" in detail["message"]
    # Review-impl L3: retryable flag is propagated so the FE can
    # decide between retry button vs "fix config" messaging.
    assert detail["retryable"] is True
    mock_find.assert_not_awaited()


@patch(
    "app.routers.public.drawers.find_passages_by_vector",
    new_callable=AsyncMock,
)
def test_drawers_embedding_error_non_retryable(mock_find):
    """Non-retryable EmbeddingError (e.g. bad model ref 4xx) must
    surface retryable=False so the FE doesn't spin a retry loop."""
    client, _, _ = _make_client(
        embed_raises=EmbeddingError("unknown model", retryable=False),
    )
    resp = client.get(
        f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}&query=test"
    )
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["retryable"] is False
    mock_find.assert_not_awaited()


@patch(
    "app.routers.public.drawers.find_passages_by_vector",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.drawers.neo4j_session", new=lambda: _noop_session()
)
def test_drawers_empty_inner_vector_returns_empty(mock_find):
    """Review-impl L4: provider returns ``EmbeddingResult(embeddings=
    [[]])`` (outer list non-empty, inner vector empty). Before the
    fix, this fell through to find_passages_by_vector which raised
    ValueError and surfaced a misleading ``embedding_dim_mismatch``
    502. Now handled as empty response — same remedy for the user
    (check provider config) but without the false-error code."""
    client, _, _ = _make_client(
        embed_return=EmbeddingResult(
            embeddings=[[]],
            dimension=1024,
            model="bge-m3",
        ),
    )
    resp = client.get(
        f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}&query=test"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["hits"] == []
    assert body["embedding_model"] == "bge-m3"
    mock_find.assert_not_awaited()


@patch(
    "app.routers.public.drawers.find_passages_by_vector",
    new_callable=AsyncMock,
)
@patch(
    "app.routers.public.drawers.neo4j_session", new=lambda: _noop_session()
)
def test_drawers_dim_mismatch_502(mock_find):
    """If the live embedding's length disagrees with the project's
    stored ``embedding_dimension`` (user changed model out-of-band),
    find_passages_by_vector raises ValueError — we catch it and return
    502 with a structured code instead of leaking a 500."""
    mock_find.side_effect = ValueError(
        "query_vector length 1536 does not match dim 1024"
    )
    client, _, _ = _make_client()
    resp = client.get(
        f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}&query=test"
    )
    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert detail["error_code"] == "embedding_dim_mismatch"
    assert "1536" in detail["message"]


# ── query-validation branches ────────────────────────────────────────


def test_drawers_query_length_rejected():
    client, _, _ = _make_client()
    # min_length=1
    resp = client.get(
        f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}&query="
    )
    assert resp.status_code == 422
    # max_length=1000
    long_q = "x" * 1001
    resp = client.get(
        f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}&query={long_q}"
    )
    assert resp.status_code == 422


def test_drawers_limit_range_rejected():
    client, _, _ = _make_client()
    assert (
        client.get(
            f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}"
            f"&query=test&limit=0"
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/v1/knowledge/drawers/search?project_id={_PROJECT_ID}"
            f"&query=test&limit=500"
        ).status_code
        == 422
    )


def test_drawers_bad_project_uuid_rejected():
    client, _, _ = _make_client()
    resp = client.get(
        "/v1/knowledge/drawers/search?project_id=not-a-uuid&query=test"
    )
    assert resp.status_code == 422
