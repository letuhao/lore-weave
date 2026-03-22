"""Shared fixtures for translation-service tests."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Provide required env vars before any app module is imported
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test_secret_for_unit_tests_32chars!!")


class FakeRecord(dict):
    """Minimal asyncpg-Record substitute: supports dict() and key access."""
    pass


@pytest.fixture
def fake_pool():
    """AsyncMock that mimics asyncpg.Pool's common methods."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchval = AsyncMock(return_value=None)
    pool.execute = AsyncMock(return_value=None)
    return pool


@pytest.fixture
def client(fake_pool):
    """
    FastAPI TestClient with DB pool + lifespan fully mocked.
    Each test can customise fake_pool.fetchrow etc. before making requests.
    """
    from fastapi.testclient import TestClient

    with (
        patch("app.database.create_pool", new_callable=AsyncMock, return_value=fake_pool),
        patch("app.database.close_pool", new_callable=AsyncMock),
        patch("app.database.get_pool", return_value=fake_pool),
        patch("app.migrate.run_migrations", new_callable=AsyncMock),
    ):
        from app.main import app
        # Override get_db to return our fake pool directly
        from app.deps import get_current_user, get_db

        async def _user():
            return "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

        async def _db():
            return fake_pool

        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_db] = _db

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

        app.dependency_overrides.clear()
