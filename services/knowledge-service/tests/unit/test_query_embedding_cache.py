"""P-K18.3-01 — query embedding TTL cache tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

import app.context.selectors.passages as passages_mod
from app.clients.embedding_client import EmbeddingError, EmbeddingResult
from app.context.intent.classifier import Intent, IntentResult
from app.context.selectors.passages import select_l3_passages


USER_UUID = UUID("22222222-2222-2222-2222-222222222222")


def _intent() -> IntentResult:
    return IntentResult(
        intent=Intent.SPECIFIC_ENTITY,
        entities=("Arthur",),
        signals=(),
        hop_count=1,
        recency_weight=0.0,
    )


def _embed_result(dim: int = 1024) -> EmbeddingResult:
    return EmbeddingResult(
        embeddings=[[0.1] * dim], dimension=dim, model="bge-m3",
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    passages_mod._query_embedding_cache.clear()
    yield
    passages_mod._query_embedding_cache.clear()


@pytest.mark.asyncio
async def test_repeated_query_hits_cache_and_skips_embedding_call(monkeypatch):
    # Two identical messages in the same project+model should only
    # embed once; the second call reuses the cached vector.
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=[]),
    )

    args = dict(
        user_id="u1", project_id="p1", message="Tell me about Arthur.",
        intent=_intent(),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    await select_l3_passages(MagicMock(), client, **args)
    await select_l3_passages(MagicMock(), client, **args)

    # First call embedded once; second call hit cache.
    assert client.embed.await_count == 1


@pytest.mark.asyncio
async def test_different_message_misses_cache(monkeypatch):
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=[]),
    )

    common = dict(
        user_id="u1", project_id="p1",
        intent=_intent(),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    await select_l3_passages(MagicMock(), client, message="a", **common)
    await select_l3_passages(MagicMock(), client, message="b", **common)

    assert client.embed.await_count == 2


@pytest.mark.asyncio
async def test_different_project_misses_cache(monkeypatch):
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=[]),
    )

    common = dict(
        user_id="u1", message="Tell me.",
        intent=_intent(),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    await select_l3_passages(MagicMock(), client, project_id="p1", **common)
    await select_l3_passages(MagicMock(), client, project_id="p2", **common)

    assert client.embed.await_count == 2


@pytest.mark.asyncio
async def test_different_model_misses_cache(monkeypatch):
    # Same message + project but different embedding model produces
    # incompatible vectors — must NOT share cache entries.
    client = MagicMock()
    client.embed = AsyncMock(
        side_effect=[_embed_result(1024), _embed_result(1536)],
    )
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=[]),
    )

    common = dict(
        user_id="u1", project_id="p1", message="Tell me.",
        intent=_intent(),
        user_uuid=USER_UUID,
    )
    await select_l3_passages(
        MagicMock(), client, embedding_model="bge-m3", embedding_dim=1024,
        **common,
    )
    await select_l3_passages(
        MagicMock(), client,
        embedding_model="text-embedding-3-small", embedding_dim=1536,
        **common,
    )

    assert client.embed.await_count == 2


@pytest.mark.asyncio
async def test_embedding_error_not_cached(monkeypatch):
    # A provider failure MUST NOT populate the cache — a transient
    # outage shouldn't lock in empty results for 30s.
    client = MagicMock()
    client.embed = AsyncMock(
        side_effect=[
            EmbeddingError("upstream 503", retryable=True),
            _embed_result(),
        ],
    )
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=[]),
    )

    args = dict(
        user_id="u1", project_id="p1", message="Retry me.",
        intent=_intent(),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    r1 = await select_l3_passages(MagicMock(), client, **args)
    assert r1 == []
    r2 = await select_l3_passages(MagicMock(), client, **args)
    # Second call should have hit embed again (not cached) — proof
    # that failure didn't populate the cache.
    assert client.embed.await_count == 2
    assert r2 == []


@pytest.mark.asyncio
async def test_different_user_misses_cache(monkeypatch):
    # review-impl fix: two users can share a project but may be
    # using different providers under the same embedding-model NAME
    # — their vectors aren't interchangeable. Cache key includes
    # user identity so they don't cross-contaminate.
    client = MagicMock()
    client.embed = AsyncMock(return_value=_embed_result())
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=[]),
    )

    user_a = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    user_b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    common = dict(
        user_id="u1", project_id="p1", message="Same message",
        intent=_intent(),
        embedding_model="bge-m3", embedding_dim=1024,
    )
    await select_l3_passages(MagicMock(), client, user_uuid=user_a, **common)
    await select_l3_passages(MagicMock(), client, user_uuid=user_b, **common)
    assert client.embed.await_count == 2


@pytest.mark.asyncio
async def test_empty_embeddings_response_not_cached(monkeypatch):
    # Provider returned 200 but with empty embeddings list. Same
    # principle — don't cache a "no result" so the next call retries.
    client = MagicMock()
    client.embed = AsyncMock(
        side_effect=[
            EmbeddingResult(embeddings=[], dimension=1024, model="bge-m3"),
            _embed_result(),
        ],
    )
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=[]),
    )

    args = dict(
        user_id="u1", project_id="p1", message="Empty please.",
        intent=_intent(),
        embedding_model="bge-m3", embedding_dim=1024,
        user_uuid=USER_UUID,
    )
    await select_l3_passages(MagicMock(), client, **args)
    await select_l3_passages(MagicMock(), client, **args)
    assert client.embed.await_count == 2
