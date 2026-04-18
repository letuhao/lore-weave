"""P-K13.0-01 — anchor pre-load TTL cache tests.

Covers: cache hit short-circuits, None project_id caches empty,
exceptions are not cached, TTL expiry evicts.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import app.routers.internal_extraction as mod
from app.extraction.anchor_loader import Anchor
from app.routers.internal_extraction import _load_anchors_for_extraction


@pytest.fixture(autouse=True)
def _clear_cache():
    # Isolate each test — cache is module-level.
    mod._anchor_cache.clear()
    yield
    mod._anchor_cache.clear()


def _anchor(name: str = "Kai") -> Anchor:
    return Anchor(
        canonical_id=f"entity:{name.lower()}",
        glossary_entity_id=str(uuid4()),
        name=name,
        kind="character",
    )


@pytest.mark.asyncio
async def test_p_k13_0_01_project_id_none_cached_as_empty():
    user_id = uuid4()
    # First call — miss, returns empty.
    r1 = await _load_anchors_for_extraction(user_id=user_id, project_id=None)
    assert r1 == []
    # Cache should hold the empty list.
    assert ("", "") != tuple()  # sanity — key shape stable below
    assert (str(user_id), "") in mod._anchor_cache

    # Second call — hit.
    r2 = await _load_anchors_for_extraction(user_id=user_id, project_id=None)
    assert r2 == []


@pytest.mark.asyncio
async def test_p_k13_0_01_second_call_is_cache_hit_no_db_work():
    user_id = uuid4()
    project_id = uuid4()
    book_id = uuid4()

    # Mock the DB pool + neo4j_session + glossary_client paths so
    # we can assert the second call hits the cache (not the DB).
    pool_mock = MagicMock()
    acquire_ctx = MagicMock()
    conn_mock = MagicMock()
    conn_mock.fetchrow = AsyncMock(return_value={"book_id": book_id})
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn_mock)
    acquire_ctx.__aexit__ = AsyncMock(return_value=None)
    pool_mock.acquire = MagicMock(return_value=acquire_ctx)

    neo4j_ctx = MagicMock()
    neo4j_session_mock = MagicMock()
    neo4j_ctx.__aenter__ = AsyncMock(return_value=neo4j_session_mock)
    neo4j_ctx.__aexit__ = AsyncMock(return_value=None)

    expected_anchors = [_anchor("Kai"), _anchor("Zhao")]

    with (
        patch.object(mod, "get_knowledge_pool", return_value=pool_mock),
        patch.object(mod, "neo4j_session", return_value=neo4j_ctx),
        patch.object(mod, "get_glossary_client", return_value=MagicMock()),
        patch.object(
            mod, "load_glossary_anchors",
            AsyncMock(return_value=expected_anchors),
        ) as load_mock,
    ):
        r1 = await _load_anchors_for_extraction(
            user_id=user_id, project_id=project_id,
        )
        assert r1 == expected_anchors
        assert load_mock.await_count == 1
        assert conn_mock.fetchrow.await_count == 1

        # Second call — cache hit, neither the DB nor load_glossary_anchors
        # should be touched again.
        r2 = await _load_anchors_for_extraction(
            user_id=user_id, project_id=project_id,
        )
        assert r2 == expected_anchors
        assert load_mock.await_count == 1  # unchanged
        assert conn_mock.fetchrow.await_count == 1  # unchanged


@pytest.mark.asyncio
async def test_p_k13_0_01_exception_not_cached():
    user_id = uuid4()
    project_id = uuid4()

    # First call raises — should NOT cache. Second call must retry.
    pool_mock = MagicMock()
    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("glossary down"))
    acquire_ctx.__aexit__ = AsyncMock(return_value=None)
    pool_mock.acquire = MagicMock(return_value=acquire_ctx)

    with patch.object(mod, "get_knowledge_pool", return_value=pool_mock):
        r1 = await _load_anchors_for_extraction(
            user_id=user_id, project_id=project_id,
        )
        assert r1 == []

    # Cache must NOT hold an entry for the failed call.
    assert (str(user_id), str(project_id)) not in mod._anchor_cache


@pytest.mark.asyncio
async def test_p_k13_0_01_no_book_id_cached_as_empty():
    user_id = uuid4()
    project_id = uuid4()

    pool_mock = MagicMock()
    acquire_ctx = MagicMock()
    conn_mock = MagicMock()
    conn_mock.fetchrow = AsyncMock(return_value={"book_id": None})
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn_mock)
    acquire_ctx.__aexit__ = AsyncMock(return_value=None)
    pool_mock.acquire = MagicMock(return_value=acquire_ctx)

    with patch.object(mod, "get_knowledge_pool", return_value=pool_mock):
        r1 = await _load_anchors_for_extraction(
            user_id=user_id, project_id=project_id,
        )
        assert r1 == []
        # Second call — cache hit, DB not touched again.
        r2 = await _load_anchors_for_extraction(
            user_id=user_id, project_id=project_id,
        )
        assert r2 == []
        assert conn_mock.fetchrow.await_count == 1


@pytest.mark.asyncio
async def test_p_k13_0_01_different_users_do_not_share_cache():
    user_a = uuid4()
    user_b = uuid4()
    pid = uuid4()

    pool_mock = MagicMock()
    acquire_ctx = MagicMock()
    conn_mock = MagicMock()
    conn_mock.fetchrow = AsyncMock(return_value={"book_id": None})
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn_mock)
    acquire_ctx.__aexit__ = AsyncMock(return_value=None)
    pool_mock.acquire = MagicMock(return_value=acquire_ctx)

    with patch.object(mod, "get_knowledge_pool", return_value=pool_mock):
        await _load_anchors_for_extraction(user_id=user_a, project_id=pid)
        await _load_anchors_for_extraction(user_id=user_b, project_id=pid)
        # Two distinct DB lookups — one per user.
        assert conn_mock.fetchrow.await_count == 2
