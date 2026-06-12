"""DB integration-test fixtures (RAID C2).

Mirrors knowledge-service tests/integration/db/conftest.py: a function-scoped
pool keyed on TEST_LORE_ENRICHMENT_DB_URL (fallback LORE_ENRICHMENT_DB_URL).
If the DB is unreachable / unset, tests SKIP — so `pytest` stays runnable on a
dev host without Docker, while verify-cycle-2.sh provides the real compose
Postgres so the H0 round-trip actually exercises constraints + triggers (no
mock-only false-green).
"""

from __future__ import annotations

import os

import asyncpg
import pytest
import pytest_asyncio

from app.db.migrate import run_down_migrations, run_migrations


def _dsn() -> str | None:
    return (
        os.environ.get("TEST_LORE_ENRICHMENT_DB_URL")
        or os.environ.get("LORE_ENRICHMENT_DB_URL")
    )


@pytest_asyncio.fixture
async def pool():
    """Function-scoped pool against a real Postgres. Skips when no reachable
    DSN. Starts each test from a clean schema: down-migrate then up-migrate so
    the round-trip itself is exercised on every run."""
    dsn = _dsn()
    # The root conftest sets a throwaway localhost DSN for import-time fail-fast;
    # treat that placeholder as "no real DB" so unit-only runs skip cleanly.
    if not dsn or "test:test@localhost" in dsn:
        pytest.skip("no real LORE_ENRICHMENT_DB_URL set")
    try:
        p = await asyncpg.create_pool(dsn, min_size=1, max_size=4, command_timeout=5)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"DB unreachable: {exc}")
    # Clean slate, then apply — proves down→up works as a fixture side effect.
    await run_down_migrations(p)
    await run_migrations(p)
    try:
        yield p
    finally:
        await p.close()
