"""Shared fixtures for jobs-service tests.

Env vars are set BEFORE any `app.*` import because `config.Settings` is fail-fast
(no defaults for the required secrets)."""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test_secret_for_unit_tests_32chars!!")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_internal_token")

TEST_USER = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture
def spy_pool():
    """An asyncpg-pool stand-in that records execute/fetch calls."""
    pool = AsyncMock()
    pool.execute = AsyncMock(return_value="INSERT 0 1")
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=0)
    return pool


@pytest.fixture
def client(spy_pool):
    """FastAPI TestClient with DB + the projection consumer stubbed."""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    _stub = MagicMock()
    _stub.run = AsyncMock()
    _stub.stop = AsyncMock()
    _stub.close = AsyncMock()

    with (
        patch("app.database.create_pool", new_callable=AsyncMock, return_value=spy_pool),
        patch("app.database.close_pool", new_callable=AsyncMock),
        patch("app.database.get_pool", return_value=spy_pool),
        patch("app.migrate.run_migrations", new_callable=AsyncMock),
        patch("app.main.JobProjectionConsumer", return_value=_stub),
    ):
        from app.deps import get_current_user, get_db
        from app.main import app

        async def _user():
            return TEST_USER

        async def _db():
            return spy_pool

        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_db] = _db
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c
        app.dependency_overrides.clear()
