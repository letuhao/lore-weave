"""Integration-test DB fixture.

Connects to a real Postgres using TEST_KNOWLEDGE_DB_URL (or falls back to
KNOWLEDGE_DB_URL). If the DB is unreachable, the test is skipped — this
keeps `pytest` runnable on a dev host without Docker, while Gate 2 runs
against the compose-managed Postgres so the DB is guaranteed.
"""

import os

import asyncpg
import pytest
import pytest_asyncio

from app.db.migrate import run_migrations


def _dsn() -> str | None:
    return os.environ.get("TEST_KNOWLEDGE_DB_URL") or os.environ.get("KNOWLEDGE_DB_URL")


@pytest_asyncio.fixture
async def pool():
    """Function-scoped pool — avoids pytest-asyncio session/function
    loop-scope conflicts. Creating a pool is ~10ms; negligible for
    integration tests. Each test gets a clean DB via TRUNCATE.
    """
    dsn = _dsn()
    if not dsn or "u:p@h" in dsn:
        pytest.skip("no real KNOWLEDGE_DB_URL set")
    try:
        p = await asyncpg.create_pool(dsn, min_size=1, max_size=4, command_timeout=5)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"DB unreachable: {exc}")
    await run_migrations(p)
    async with p.acquire() as conn:
        await conn.execute(
            "TRUNCATE knowledge_projects, knowledge_summaries RESTART IDENTITY CASCADE"
        )
    try:
        yield p
    finally:
        await p.close()
