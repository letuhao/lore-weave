"""Integration-test DB fixture (mirrors knowledge-service/tests/integration/db).

db-safety-gate: guarded-dir — every DB fixture here refuses a non-throwaway DSN via
_guard_throwaway() before it runs its destructive TRUNCATE, so it can never wipe a real
service database. (See CLAUDE.md › "Destructive DB ops in tests" + scripts/db-safety-gate.py.)

Connects to a real Postgres via TEST_CAMPAIGN_DB_URL. If unreachable/unset, the test
SKIPS — so `pytest` stays runnable on a dev host without a DB, while the compose-managed
Postgres (Gate 2 / dev stack) exercises the real SQL semantics (notably the S4d
pause-threshold CASE, which a fake pool cannot verify).
"""

import os
import re

import asyncpg
import pytest
import pytest_asyncio

from app.migrate import run_migrations

# A disposable test DB name carries one of these markers; a real service DB
# (loreweave_campaign) carries none. Mirrors book-service/internal/testsafe + the
# kg-integration-tests-truncate-shared-dev-db lesson.
_THROWAWAY = re.compile(r"(?i)(test|smoke|audit|scratch|throwaway|tmp|sandbox|ephemeral)")


def _dsn() -> str | None:
    # ONLY the dedicated test var — never fall back to the production CAMPAIGN_DB_URL,
    # which in any dev shell points at the real loreweave_campaign the TRUNCATE would wipe.
    return os.environ.get("TEST_CAMPAIGN_DB_URL")


def _guard_throwaway(dsn: str) -> None:
    db = dsn.rsplit("/", 1)[-1].split("?", 1)[0]
    if not _THROWAWAY.search(db):
        raise RuntimeError(
            f"REFUSING: TEST_CAMPAIGN_DB_URL database {db!r} is not a throwaway DB "
            "(the name must contain test/smoke/audit/…). This fixture TRUNCATEs tables — "
            "point it at a disposable DB, never the real loreweave_campaign."
        )


@pytest_asyncio.fixture
async def pool():
    dsn = _dsn()
    if not dsn:
        pytest.skip("no TEST_CAMPAIGN_DB_URL set — skipping live DB test")
    _guard_throwaway(dsn)  # refuse a real DB BEFORE any destructive statement
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
