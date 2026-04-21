"""K16.12 — Unit tests for cost tracking API."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

_NO_PROJECT = object()
_TEST_USER = uuid4()
_TEST_PROJECT = uuid4()


@pytest.fixture(autouse=True)
def _clear_overrides():
    from app.main import app
    yield
    app.dependency_overrides.clear()


def _project_stub():
    from app.db.models import Project
    return Project(
        project_id=_TEST_PROJECT, user_id=_TEST_USER, name="Test",
        description="", project_type="translation", book_id=uuid4(),
        instructions="", extraction_enabled=False, extraction_status="disabled",
        extraction_config={}, estimated_cost_usd=Decimal("5.00"),
        actual_cost_usd=Decimal("3.50"), is_archived=False, version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_client(*, project=None, user_budget: Decimal | None = None):
    from app.main import app
    from app.deps import get_projects_repo, get_user_budgets_repo
    from app.middleware.jwt_auth import get_current_user

    if project is _NO_PROJECT:
        repo_return = None
    else:
        repo_return = project if project is not None else _project_stub()

    projects_repo = AsyncMock()
    projects_repo.get = AsyncMock(return_value=repo_return)

    # K16.12: user budget repo mock. `user_budget` kwarg lets each test
    # pick the cap state: None (default → no cap set), a Decimal → cap
    # stored. The router's GET /costs handler reads via `.get()`.
    user_budgets_repo = AsyncMock()
    user_budgets_repo.get = AsyncMock(return_value=user_budget)
    user_budgets_repo.upsert = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_user_budgets_repo] = lambda: user_budgets_repo

    return TestClient(app, raise_server_exceptions=False), user_budgets_repo


@patch("app.routers.public.costs.get_knowledge_pool")
def test_get_user_costs(mock_pool):
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={
        "all_time": Decimal("15.00"),
        "current_month": Decimal("3.50"),
    })
    mock_pool.return_value = pool

    client, _budget_repo = _make_client()  # no user_budget → null cap
    resp = client.get("/v1/knowledge/costs")
    assert resp.status_code == 200
    data = resp.json()
    assert float(data["all_time_usd"]) == 15.0
    assert float(data["current_month_usd"]) == 3.5
    # K16.12 additive fields: both null when no user-wide cap is set.
    assert data["monthly_budget_usd"] is None
    assert data["monthly_remaining_usd"] is None


@patch("app.routers.public.costs.get_knowledge_pool")
def test_get_user_costs_with_budget_returns_remaining(mock_pool):
    """K16.12: budget set, spent < cap → remaining = cap - spent."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={
        "all_time": Decimal("40.00"),
        "current_month": Decimal("7.50"),
    })
    mock_pool.return_value = pool

    client, _budget_repo = _make_client(user_budget=Decimal("20.00"))
    resp = client.get("/v1/knowledge/costs")
    assert resp.status_code == 200
    data = resp.json()
    assert float(data["monthly_budget_usd"]) == 20.0
    assert float(data["monthly_remaining_usd"]) == 12.5


@patch("app.routers.public.costs.get_knowledge_pool")
def test_get_user_costs_clamps_remaining_at_zero_when_overspent(mock_pool):
    """K16.12: user overspent (via per-project try_spend before setting
    aggregate cap) → remaining clamped to 0, not negative."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={
        "all_time": Decimal("40.00"),
        "current_month": Decimal("30.00"),
    })
    mock_pool.return_value = pool

    client, _budget_repo = _make_client(user_budget=Decimal("10.00"))
    resp = client.get("/v1/knowledge/costs")
    assert resp.status_code == 200
    data = resp.json()
    assert float(data["monthly_budget_usd"]) == 10.0
    assert float(data["monthly_remaining_usd"]) == 0.0


def test_set_user_budget_happy_path():
    """K16.12: PUT /me/budget with a decimal cap."""
    client, budget_repo = _make_client()
    resp = client.put(
        "/v1/knowledge/me/budget",
        json={"ai_monthly_budget_usd": "42.50"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ai_monthly_budget_usd"] == "42.50"
    # review-impl L4: response echoes user_id for symmetry with
    # PUT /projects/{id}/budget.
    assert data["user_id"] == str(_TEST_USER)
    budget_repo.upsert.assert_awaited_once_with(_TEST_USER, Decimal("42.50"))


def test_set_user_budget_null_clears_cap():
    """K16.12: PUT /me/budget with null body clears the cap."""
    client, budget_repo = _make_client()
    resp = client.put("/v1/knowledge/me/budget", json={"ai_monthly_budget_usd": None})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ai_monthly_budget_usd"] is None
    assert data["user_id"] == str(_TEST_USER)
    budget_repo.upsert.assert_awaited_once_with(_TEST_USER, None)


def test_set_user_budget_rejects_negative():
    """K16.12: Field(ge=0) → 422 for negative decimals."""
    client, _budget_repo = _make_client()
    resp = client.put(
        "/v1/knowledge/me/budget",
        json={"ai_monthly_budget_usd": "-1.00"},
    )
    assert resp.status_code == 422


@patch("app.routers.public.costs.get_knowledge_pool")
def test_get_project_costs(mock_pool):
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={
        "monthly_budget_usd": Decimal("25.00"),
        "current_month_spent_usd": Decimal("8.50"),
        "current_month_key": datetime.now(timezone.utc).strftime("%Y-%m"),
    })
    pool.fetch = AsyncMock(return_value=[])
    mock_pool.return_value = pool

    client, _budget_repo = _make_client()
    resp = client.get(f"/v1/knowledge/projects/{_TEST_PROJECT}/costs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == str(_TEST_PROJECT)
    assert float(data["monthly_budget_usd"]) == 25.0
    assert float(data["current_month_usd"]) == 8.5


def test_get_project_costs_not_found():
    client, _budget_repo = _make_client(project=_NO_PROJECT)
    resp = client.get(f"/v1/knowledge/projects/{_TEST_PROJECT}/costs")
    assert resp.status_code == 404


@patch("app.routers.public.costs.get_knowledge_pool")
def test_set_project_budget(mock_pool):
    pool = AsyncMock()
    pool.execute = AsyncMock()
    mock_pool.return_value = pool

    client, _budget_repo = _make_client()
    resp = client.put(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/budget",
        json={"monthly_budget_usd": "25.00"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["monthly_budget_usd"] == "25.00"


@patch("app.routers.public.costs.get_knowledge_pool")
def test_set_project_budget_null_unlimited(mock_pool):
    pool = AsyncMock()
    pool.execute = AsyncMock()
    mock_pool.return_value = pool

    client, _budget_repo = _make_client()
    resp = client.put(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/budget",
        json={"monthly_budget_usd": None},
    )
    assert resp.status_code == 200
    assert resp.json()["monthly_budget_usd"] is None


def test_set_budget_project_not_found():
    client, _budget_repo = _make_client(project=_NO_PROJECT)
    resp = client.put(
        f"/v1/knowledge/projects/{_TEST_PROJECT}/budget",
        json={"monthly_budget_usd": "10.00"},
    )
    assert resp.status_code == 404
