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
