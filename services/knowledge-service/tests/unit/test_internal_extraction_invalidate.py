"""P2 — unit tests for POST /internal/extraction/invalidate-cache/{book_id} (D5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app


_INTERNAL_TOKEN_HEADER = {"X-Internal-Token": "default_test_token"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def book_id() -> str:
    return str(uuid4())


def _patch_repo(return_value: tuple[int, int]) -> AsyncMock:
    """Mock both the pool helper (avoid 'not initialised' error) AND
    the repo's delete method to return controlled counts."""
    return AsyncMock(return_value=return_value)


def test_invalidate_returns_deletion_counts(client: TestClient, book_id: str):
    """H2 lock: response carries BOTH deleted_leaves AND deleted_raw."""
    with patch(
        "app.routers.internal_extraction.get_knowledge_pool",
        return_value=object(),  # cheap stand-in; repo's delete is what's called
    ), patch(
        "app.db.repositories.extraction_leaves.ExtractionLeavesRepo.delete_by_book",
        new=_patch_repo((5, 3)),
    ):
        resp = client.post(
            f"/internal/extraction/invalidate-cache/{book_id}",
            headers=_INTERNAL_TOKEN_HEADER,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted_leaves"] == 5
    assert body["deleted_raw"] == 3
    assert body["book_id"] == book_id
    assert sorted(body["invalidated_ops"]) == ["entity", "event", "fact", "relation"]


def test_invalidate_op_filter_restricts_targets(client: TestClient, book_id: str):
    """?op=entity restricts the DELETE to entity rows only."""
    delete_mock = AsyncMock(return_value=(2, 0))
    with patch(
        "app.routers.internal_extraction.get_knowledge_pool",
        return_value=object(),
    ), patch(
        "app.db.repositories.extraction_leaves.ExtractionLeavesRepo.delete_by_book",
        new=delete_mock,
    ):
        resp = client.post(
            f"/internal/extraction/invalidate-cache/{book_id}?op=entity",
            headers=_INTERNAL_TOKEN_HEADER,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["invalidated_ops"] == ["entity"]
    # Repo received only the entity op.
    call_kwargs = delete_mock.call_args.kwargs
    assert call_kwargs["ops"] == ["entity"]


def test_invalidate_invalid_op_returns_400(client: TestClient, book_id: str):
    resp = client.post(
        f"/internal/extraction/invalidate-cache/{book_id}?op=garbage",
        headers=_INTERNAL_TOKEN_HEADER,
    )
    assert resp.status_code == 400


def test_invalidate_requires_internal_token(client: TestClient, book_id: str):
    resp = client.post(
        f"/internal/extraction/invalidate-cache/{book_id}",
    )
    assert resp.status_code == 401


def test_invalidate_idempotent_zero_counts_on_already_empty(client: TestClient, book_id: str):
    """Second call returns deleted_leaves=0 because rows already gone."""
    with patch(
        "app.routers.internal_extraction.get_knowledge_pool",
        return_value=object(),
    ), patch(
        "app.db.repositories.extraction_leaves.ExtractionLeavesRepo.delete_by_book",
        new=AsyncMock(return_value=(0, 0)),
    ):
        resp = client.post(
            f"/internal/extraction/invalidate-cache/{book_id}",
            headers=_INTERNAL_TOKEN_HEADER,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted_leaves"] == 0
    assert body["deleted_raw"] == 0
