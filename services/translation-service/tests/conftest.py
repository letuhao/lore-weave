"""Shared fixtures for translation-service tests."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Provide required env vars before any app module is imported
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test_secret_for_unit_tests_32chars!!")
# Phase 4c-α: app.llm_client imports app.config at module load, which
# instantiates Settings() — these are required for tests that touch
# the SDK wrapper. Other test modules patch around config so they
# weren't sensitive to missing values; new tests that touch
# llm_client need them set up-front.
os.environ.setdefault("RABBITMQ_URL", "amqp://test:test@localhost:5672/")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test_internal_token")


@pytest.fixture(autouse=True)
def _stub_model_name_resolve(monkeypatch):
    """P4 / producer-emit backfill — the create paths resolve the model NAME via
    provider-registry (HTTP) for the 'pending' lifecycle event's model/params. Each router
    does `from ..model_name import resolve_model_name`, so the binding lives in EACH router
    module — patch all of them (raising=False if a module isn't imported). Stub keeps the
    suite hermetic + fast (best-effort None on failure, but a real connect costs DNS latency)."""
    stub = AsyncMock(return_value="qwen2.5-7b-instruct")
    for target in (
        "app.routers.jobs.resolve_model_name",
        "app.routers.extraction.resolve_model_name",        # glossary-extract (Slice A)
        "app.routers.glossary_translate.resolve_model_name",  # glossary-translate (Slice B)
    ):
        monkeypatch.setattr(target, stub, raising=False)


@pytest.fixture(autouse=True)
def _hermetic_knowledge_brief(monkeypatch):
    """M4b: keep the suite hermetic + fast.

    The V3 orchestrator builds a per-chapter knowledge brief, whose first step is
    a glossary `select-for-context` HTTP call. In unit tests that host isn't
    reachable, so it degrades to empty — but only after paying DNS-fail latency
    per test. Default it to an empty fetch (no network); tests that exercise the
    brief override `knowledge_context.fetch_context_entities` themselves.
    """
    async def _no_entities(*a, **k):
        return []
    monkeypatch.setattr(
        "app.workers.v3.knowledge_context.fetch_context_entities",
        _no_entities, raising=False,
    )

    # M4d-1: the orchestrator also fetches a cross-chapter timeline memo. Default
    # it to empty (no network); tests that exercise it override fetch_timeline.
    from app.workers.knowledge_client import TimelineBrief

    async def _no_timeline(*a, **k):
        return TimelineBrief.empty()
    monkeypatch.setattr(
        "app.workers.v3.knowledge_context.fetch_timeline",
        _no_timeline, raising=False,
    )


class FakeRecord(dict):
    """Minimal asyncpg-Record substitute: supports dict() and key access."""
    pass


class _GrantStub:
    """E0-4a test seam: stands in for the book-service grant client. Default OWNER
    so existing router tests (which run as the row owner) pass the gate unchanged;
    a test can set ``.level`` to drive a deny (NONE → 404, under-tier → 403)."""

    def __init__(self, level):
        self.level = level

    async def resolve_grant(self, book_id, user_id):
        return self.level

    async def resolve_access(self, book_id, user_id):
        return self.level, "active"


@pytest.fixture
def grant_stub():
    from app.grant_client import GrantLevel
    return _GrantStub(GrantLevel.OWNER)


@pytest.fixture
def fake_pool():
    """AsyncMock that mimics asyncpg.Pool's common methods."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchval = AsyncMock(return_value=None)
    pool.execute = AsyncMock(return_value=None)

    # Support `async with pool.acquire() as conn:` + `async with conn.transaction():`.
    # The acquired connection IS the pool mock, so conn.fetchrow/execute are the same
    # mocks each test configures — transactional code (e.g. create_job, W7) stays
    # testable without rewriting per-test assertions.
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
def client(fake_pool, grant_stub):
    """
    FastAPI TestClient with DB pool + lifespan fully mocked.
    Each test can customise fake_pool.fetchrow etc. before making requests.

    E0-4a: the book-grant client dep is overridden with ``grant_stub`` (default
    OWNER) so existing tests pass-through; a deny test sets ``grant_stub.level``.
    """
    from fastapi.testclient import TestClient

    # M5c: stub the glossary-staleness consumer so the lifespan never opens a real
    # Redis connection in tests (an unresolvable 'redis' host otherwise blocks
    # TestClient teardown on the connect attempt — a multi-minute suite hang).
    _stub_consumer = MagicMock()
    _stub_consumer.run = AsyncMock()
    _stub_consumer.stop = AsyncMock()
    _stub_consumer.close = AsyncMock()

    with (
        patch("app.database.create_pool", new_callable=AsyncMock, return_value=fake_pool),
        patch("app.database.close_pool", new_callable=AsyncMock),
        patch("app.database.get_pool", return_value=fake_pool),
        patch("app.migrate.run_migrations", new_callable=AsyncMock),
        patch("app.broker.connect_broker", new_callable=AsyncMock),
        patch("app.broker.close_broker", new_callable=AsyncMock),
        patch("app.routers.jobs.publish", new_callable=AsyncMock),
        patch("app.routers.jobs.publish_event", new_callable=AsyncMock),
        patch("app.main.GlossaryStaleConsumer", return_value=_stub_consumer),
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
        # E0-4a: route the book-grant gate to the stub (default OWNER → pass).
        from app.grant_deps import get_grant_client_dep
        app.dependency_overrides[get_grant_client_dep] = lambda: grant_stub

        with TestClient(app, raise_server_exceptions=True) as c:
            yield c

        app.dependency_overrides.clear()
