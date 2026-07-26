"""Phase E2 — mining query layer + mining API endpoint tests."""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db.mining import (
    get_config_quality,
    get_default_drift,
    get_model_matrix,
    get_outcome_recompute,
)
from app.deps import get_current_user, get_db
from app.main import app

USER_ID = uuid.uuid4()
USER_STR = str(USER_ID)


# ── FakePool helpers ──────────────────────────────────────────────────


class FakeMiningPool:
    """Captures fetch/fetchval calls and returns configurable rows."""

    def __init__(self, *, rows=None, total=0):
        self._rows = rows or []
        self._total = total
        self.fetch_calls: list = []
        self.fetchval_calls: list = []

    def acquire(self):
        pool = self

        class _Acq:
            async def __aenter__(self_):
                return pool

            async def __aexit__(self_, *a):
                return False

        return _Acq()

    async def fetch(self, sql, *params):
        self.fetch_calls.append((sql, params))
        return self._rows

    async def fetchval(self, sql, *params):
        self.fetchval_calls.append((sql, params))
        return self._total


def _quality_row(**over):
    base = {
        "genre": "Tiên hiệp",
        "config_hash": "a" * 64,
        "run_count": 5,
        "succeeded": 4,
        "avg_entities_on_success": 12.0,
        "success_rate": 0.8,
    }
    base.update(over)
    return base


def _matrix_row(**over):
    base = {
        "model_ref": "qwen-model-uuid",
        "scope": "chapter",
        "has_filter": True,
        "run_count": 10,
        "succeeded": 9,
        "weighted_outcome": 0.93,
    }
    base.update(over)
    return base


def _drift_row(**over):
    base = {
        "target": "precision_filter.categories",
        "base_default_version": "v1",
        "affected_projects": 3,
        "distinct_after_values": 1,
        "drift_pattern": "convergent",
        "runs_with_outcome": 7,
    }
    base.update(over)
    return base


def _recompute_row(**over):
    base = {
        "run_id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "pipeline_outcome": "succeeded",
        "created_at": "2026-06-01T00:00:00+00:00",
        "post_run_corrections": 0,
        "recomputed_outcome": "succeeded",
    }
    base.update(over)
    return base


# ── Query-layer tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_config_quality_returns_items_and_exploration():
    pool = FakeMiningPool(rows=[_quality_row()])
    result = await get_config_quality(pool, user_id=USER_ID)
    # Two fetch calls: top-N + exploration
    assert len(pool.fetch_calls) == 2
    assert "items" in result and "exploration" in result
    assert result["items"][0]["genre"] == "Tiên hiệp"


@pytest.mark.asyncio
async def test_get_config_quality_user_id_is_first_param():
    """user_id must be $1 on both queries (strict isolation)."""
    pool = FakeMiningPool()
    await get_config_quality(pool, user_id=USER_ID)
    for _, params in pool.fetch_calls:
        assert params[0] == USER_ID


@pytest.mark.asyncio
async def test_get_config_quality_cold_start_returns_empty():
    pool = FakeMiningPool(rows=[])
    result = await get_config_quality(pool, user_id=USER_ID)
    assert result["items"] == []
    assert result["exploration"] == []


@pytest.mark.asyncio
async def test_get_config_quality_power_user_segmentation_param_forwarded():
    pool = FakeMiningPool()
    await get_config_quality(
        pool, user_id=USER_ID,
        segment_power_users=True, power_user_threshold=5,
    )
    _, params = pool.fetch_calls[0]
    assert params[2] is True    # segment_power_users
    assert params[3] == 5       # power_user_threshold


@pytest.mark.asyncio
async def test_get_model_matrix_returns_list():
    pool = FakeMiningPool(rows=[_matrix_row()])
    result = await get_model_matrix(pool, user_id=USER_ID)
    assert len(result) == 1
    assert result[0]["model_ref"] == "qwen-model-uuid"


@pytest.mark.asyncio
async def test_get_model_matrix_user_id_is_first_param():
    pool = FakeMiningPool()
    await get_model_matrix(pool, user_id=USER_ID)
    _, params = pool.fetch_calls[0]
    assert params[0] == USER_ID


@pytest.mark.asyncio
async def test_get_default_drift_returns_list():
    pool = FakeMiningPool(rows=[_drift_row()])
    result = await get_default_drift(pool, user_id=USER_ID)
    assert result[0]["drift_pattern"] == "convergent"


@pytest.mark.asyncio
async def test_get_outcome_recompute_returns_items_and_total():
    pool = FakeMiningPool(rows=[_recompute_row()], total=1)
    result = await get_outcome_recompute(pool, user_id=USER_ID)
    assert "items" in result and "total" in result
    assert result["total"] == 1
    assert result["items"][0]["recomputed_outcome"] == "succeeded"


@pytest.mark.asyncio
async def test_get_outcome_recompute_cold_start_empty():
    pool = FakeMiningPool(rows=[], total=0)
    result = await get_outcome_recompute(pool, user_id=USER_ID)
    assert result["items"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_outcome_recompute_excludes_generation_corrections():
    """/review-impl slice-2 HIGH#1: the outcome-recompute corrections join MUST
    restrict to extraction target_types. Composition co-write corrections
    (target_type='generation') share the book's knowledge project_id + carry
    source_extraction_run_id IS NULL, so without this filter they'd be miscounted
    as extraction corrections and falsely degrade an extraction run's outcome."""
    pool = FakeMiningPool(rows=[], total=0)
    await get_outcome_recompute(pool, user_id=USER_ID)
    data_sql = pool.fetch_calls[0][0]
    assert "c.target_type IN ('entity', 'relation', 'event', 'fact')" in data_sql


# ── Mining API endpoint tests ─────────────────────────────────────────


def _client(pool):
    app.dependency_overrides[get_current_user] = lambda: USER_STR
    app.dependency_overrides[get_db] = lambda: pool
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_config_quality_endpoint_happy_path():
    pool = FakeMiningPool(rows=[_quality_row()])
    client = _client(pool)
    resp = client.get("/v1/learning/mining/config-quality")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and "exploration" in body


def test_config_quality_endpoint_requires_auth():
    client = TestClient(app)
    resp = client.get("/v1/learning/mining/config-quality")
    assert resp.status_code == 401


def test_model_matrix_endpoint_happy_path():
    pool = FakeMiningPool(rows=[_matrix_row()])
    client = _client(pool)
    resp = client.get("/v1/learning/mining/model-matrix")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


def test_default_drift_endpoint_happy_path():
    pool = FakeMiningPool(rows=[_drift_row()])
    client = _client(pool)
    resp = client.get("/v1/learning/mining/default-drift")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["drift_pattern"] == "convergent"


def test_outcome_recompute_endpoint_happy_path():
    pool = FakeMiningPool(rows=[_recompute_row()], total=1)
    client = _client(pool)
    resp = client.get("/v1/learning/mining/outcome-recompute")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


def test_outcome_recompute_cold_start():
    pool = FakeMiningPool(rows=[], total=0)
    client = _client(pool)
    resp = client.get("/v1/learning/mining/outcome-recompute")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []
