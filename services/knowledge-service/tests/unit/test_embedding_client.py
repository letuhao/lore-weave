"""K12.2 — Unit tests for embedding client."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
import respx

from app.clients.embedding_client import EmbeddingClient, EmbeddingError


_BASE_URL = "http://provider-registry:8085"


@pytest.fixture
def client():
    c = EmbeddingClient(
        base_url=_BASE_URL,
        internal_token="test-token",
        timeout_s=5.0,
    )
    yield c


@pytest.mark.asyncio
async def test_embed_success(client):
    with respx.mock() as mock:
        mock.post(f"{_BASE_URL}/internal/embed").respond(200, json={
            "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            "dimension": 3,
            "model": "text-embedding-3-small",
        })
        result = await client.embed(
            user_id=uuid4(),
            model_source="user_model",
            model_ref=str(uuid4()),
            texts=["hello", "world"],
        )
    assert len(result.embeddings) == 2
    assert result.dimension == 3
    assert result.model == "text-embedding-3-small"


@pytest.mark.asyncio
async def test_embed_provider_error_raises(client):
    with respx.mock() as mock:
        mock.post(f"{_BASE_URL}/internal/embed").respond(502, json={
            "detail": "provider down",
        })
        with pytest.raises(EmbeddingError) as exc_info:
            await client.embed(
                user_id=uuid4(),
                model_source="user_model",
                model_ref=str(uuid4()),
                texts=["hello"],
            )
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_embed_bad_model_not_retryable(client):
    with respx.mock() as mock:
        mock.post(f"{_BASE_URL}/internal/embed").respond(400, json={
            "detail": "model not found",
        })
        with pytest.raises(EmbeddingError) as exc_info:
            await client.embed(
                user_id=uuid4(),
                model_source="user_model",
                model_ref=str(uuid4()),
                texts=["hello"],
            )
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
async def test_embed_recovers_stale_model_from_embedding_default(client):
    """A deleted/re-added model gets a new UUID; retry with the user's
    provider-registry embedding fallback instead of surfacing a 404."""
    user_id = uuid4()
    old_ref = str(uuid4())
    new_ref = str(uuid4())
    with respx.mock() as mock:
        embed_route = mock.post(f"{_BASE_URL}/internal/embed").mock(
            side_effect=[
                httpx.Response(404, json={"code": "EMBED_MODEL_NOT_FOUND"}),
                httpx.Response(200, json={
                    "embeddings": [[0.1, 0.2, 0.3]],
                    "dimension": 3,
                    "model": "qwen3-embedding-4b",
                }),
            ],
        )
        default_route = mock.get(f"{_BASE_URL}/internal/default-models/embedding").respond(
            200, json={"user_model_id": new_ref, "model_source": "user_model"},
        )
        result = await client.embed(
            user_id=user_id,
            model_source="user_model",
            model_ref=old_ref,
            texts=["hello"],
        )
    assert result.model == "qwen3-embedding-4b"
    assert default_route.called
    assert default_route.calls[0].request.url.params["user_id"] == str(user_id)
    assert embed_route.call_count == 2
    assert new_ref in embed_route.calls[1].request.content.decode()


@pytest.mark.asyncio
async def test_embed_timeout_retryable(client):
    with respx.mock() as mock:
        mock.post(f"{_BASE_URL}/internal/embed").mock(
            side_effect=httpx.TimeoutException("timed out"),
        )
        with pytest.raises(EmbeddingError) as exc_info:
            await client.embed(
                user_id=uuid4(),
                model_source="user_model",
                model_ref=str(uuid4()),
                texts=["hello"],
            )
    assert exc_info.value.retryable is True
