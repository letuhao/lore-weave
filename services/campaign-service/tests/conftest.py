"""Shared fixtures for campaign-service tests."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Set env vars BEFORE any app.* import (config.Settings is fail-fast) ──
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test_secret_for_unit_tests_32chars!!")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_internal_token")

TEST_USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class FakeRecord(dict):
    """Minimal asyncpg.Record substitute: dict() + key access."""
    pass


@pytest.fixture
def fake_pool():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchval = AsyncMock(return_value=0)
    pool.execute = AsyncMock(return_value="UPDATE 1")
    pool.executemany = AsyncMock(return_value=None)

    # `async with pool.acquire() as conn:` → conn is the pool itself.
    class _AcquireCM:
        async def __aenter__(self):
            return pool
        async def __aexit__(self, *exc):
            return False

    _tx = MagicMock()
    _tx.__aenter__ = AsyncMock(return_value=pool)
    _tx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=_AcquireCM())
    pool.transaction = MagicMock(return_value=_tx)
    return pool


@pytest.fixture
def client(fake_pool):
    """FastAPI TestClient with DB + background tasks (consumer/driver) stubbed."""
    from fastapi.testclient import TestClient

    _stub = MagicMock()
    _stub.run = AsyncMock()
    _stub.stop = AsyncMock()
    _stub.close = AsyncMock()

    with (
        patch("app.database.create_pool", new_callable=AsyncMock, return_value=fake_pool),
        patch("app.database.close_pool", new_callable=AsyncMock),
        patch("app.database.get_pool", return_value=fake_pool),
        patch("app.migrate.run_migrations", new_callable=AsyncMock),
        patch("app.main.ProjectionConsumer", return_value=_stub),
        patch("app.main.SagaDriver", return_value=_stub),
    ):
        from app.main import app
        from app.deps import get_current_user, get_db

        async def _user():
            return TEST_USER

        async def _db():
            return fake_pool

        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_db] = _db
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c
        app.dependency_overrides.clear()
