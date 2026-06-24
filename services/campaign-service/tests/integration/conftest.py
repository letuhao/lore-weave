"""Integration-test DB fixture (mirrors knowledge-service/tests/integration/db).

Connects to a real Postgres via TEST_CAMPAIGN_DB_URL (or CAMPAIGN_DB_URL). If
unreachable/unset, the test SKIPS — so `pytest` stays runnable on a dev host
without a DB, while the compose-managed Postgres (Gate 2 / dev stack) exercises
the real SQL semantics (notably the S4d pause-threshold CASE, which a fake pool
cannot verify).
"""

import os

import asyncpg
import pytest
import pytest_asyncio

from app.migrate import run_migrations


def _dsn() -> str | None:
    return os.environ.get("TEST_CAMPAIGN_DB_URL") or os.environ.get("CAMPAIGN_DB_URL")


@pytest_asyncio.fixture
async def pool():
    dsn = _dsn()
    if not dsn:
        pytest.skip("no TEST_CAMPAIGN_DB_URL / CAMPAIGN_DB_URL set — skipping live DB test")
    try:
        p = await asyncpg.create_pool(dsn, min_size=1, max_size=4, command_timeout=5)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"DB unreachable: {exc}")
    await run_migrations(p)
    async with p.acquire() as conn:
        await conn.execute(
            "TRUNCATE campaigns, campaign_chapters, campaign_usage_seen, campaign_activity "
            "RESTART IDENTITY CASCADE"
        )
    try:
        yield p
    finally:
        await p.close()
