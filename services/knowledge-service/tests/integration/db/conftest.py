"""Integration-test DB fixtures.

db-safety-gate: guarded-dir — the `pool` fixture here refuses a non-throwaway DSN via
_guard_throwaway() BEFORE it runs its destructive TRUNCATE, and every DB test under this
directory acquires its connection from that single guarded pool (no test opens its own
Postgres pool). So this tree can never TRUNCATE a real service database. (See CLAUDE.md ›
"Destructive DB ops in tests" + scripts/db-safety-gate.py.)

Connects to a real Postgres using TEST_KNOWLEDGE_DB_URL — the dedicated test var ONLY. It
never falls back to the production KNOWLEDGE_DB_URL, which in any dev shell points at the
real loreweave_knowledge the TRUNCATE would wipe. If the DB is unreachable/unset, the test
is skipped — this keeps `pytest` runnable on a dev host without Docker, while Gate 2 runs
against the compose-managed Postgres so the DB is guaranteed.

Also provides a shared `neo4j_driver` fixture for K11.5+ Neo4j repo
tests (skipped when TEST_NEO4J_URI is unset).
"""

import os
import re

import asyncpg
import pytest
import pytest_asyncio

from app.db.migrate import run_migrations
from app.db.neo4j_schema import run_neo4j_schema

# A disposable test DB name carries one of these markers; a real service DB
# (loreweave_knowledge) carries none. Mirrors campaign-service/tests/integration/conftest
# + the kg-integration-tests-truncate-shared-dev-db lesson.
_THROWAWAY = re.compile(r"(?i)(test|smoke|audit|scratch|throwaway|tmp|sandbox|ephemeral)")


def _dsn() -> str | None:
    # ONLY the dedicated test var — never fall back to the production KNOWLEDGE_DB_URL,
    # which in any dev shell points at the real loreweave_knowledge the TRUNCATE would wipe.
    return os.environ.get("TEST_KNOWLEDGE_DB_URL")


def _guard_throwaway(dsn: str) -> None:
    db = dsn.rsplit("/", 1)[-1].split("?", 1)[0]
    if not _THROWAWAY.search(db):
        raise RuntimeError(
            f"REFUSING: TEST_KNOWLEDGE_DB_URL database {db!r} is not a throwaway DB "
            "(the name must contain test/smoke/audit/…). This fixture TRUNCATEs tables — "
            "point it at a disposable DB, never the real loreweave_knowledge."
        )


@pytest_asyncio.fixture
async def pool():
    """Function-scoped pool — avoids pytest-asyncio session/function
    loop-scope conflicts. Creating a pool is ~10ms; negligible for
    integration tests. Each test gets a clean DB via TRUNCATE.
    """
    dsn = _dsn()
    if not dsn or "u:p@h" in dsn:
        pytest.skip("no real TEST_KNOWLEDGE_DB_URL set")
    _guard_throwaway(dsn)  # refuse a real DB BEFORE any destructive statement
    try:
        p = await asyncpg.create_pool(dsn, min_size=1, max_size=4, command_timeout=5)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"DB unreachable: {exc}")
    await run_migrations(p)
    async with p.acquire() as conn:
        await conn.execute(
            "TRUNCATE knowledge_projects, knowledge_summaries, "
            "user_knowledge_budgets, job_logs "
            "RESTART IDENTITY CASCADE"
        )
    # K27 (2026-07-24) — also expose this throwaway pool as the GLOBAL `_knowledge_pool`.
    # Tests that drive a real handler (e.g. the context-build router) reach a production code
    # path that calls `get_knowledge_pool()` DIRECTLY, not through a DI'd repo — a call added
    # after these tests were written. Overriding the repos alone left that global unset, so 12
    # test_context_build tests died with "knowledge pool not initialised". This is a HARNESS
    # gap, not a code bug; setting the global here (guarded throwaway pool, reset on teardown)
    # restores them. See RUN-STATE K27.
    from app.db import pool as _pool_mod

    _prev = _pool_mod._knowledge_pool
    _pool_mod._knowledge_pool = p
    try:
        yield p
    finally:
        _pool_mod._knowledge_pool = _prev
        await p.close()


def _neo4j_dsn() -> tuple[str, str, str] | None:
    uri = os.environ.get("TEST_NEO4J_URI")
    if not uri:
        return None
    user = os.environ.get("TEST_NEO4J_USER", "neo4j")
    password = os.environ.get("TEST_NEO4J_PASSWORD", "loreweave_dev_neo4j")
    return uri, user, password


@pytest_asyncio.fixture
async def neo4j_driver():
    """Function-scoped Neo4j driver. Skips when TEST_NEO4J_URI is
    unset. Applies the K11.3 schema (idempotent) on first use so
    every Neo4j integration test can assume constraints + indexes
    + vector indexes exist.

    Each test that mutates entities should clean up its own nodes
    via DETACH DELETE in a finally — there is no global truncate
    because Neo4j community edition has no `TRUNCATE GRAPH`
    equivalent and `MATCH (n) DETACH DELETE n` would clobber data
    from concurrent tests.
    """
    from neo4j import AsyncGraphDatabase

    dsn = _neo4j_dsn()
    if dsn is None:
        pytest.skip("TEST_NEO4J_URI not set — skipping live Neo4j test")
    uri, user, password = dsn
    try:
        driver = AsyncGraphDatabase.driver(
            uri,
            auth=(user, password),
            connection_timeout=5.0,
        )
        await driver.verify_connectivity()
    except Exception as exc:
        pytest.skip(f"Neo4j unreachable at {uri}: {exc}")
    try:
        await run_neo4j_schema(driver)
        # K27 (2026-07-24) — also expose this as the GLOBAL app.db.neo4j driver, so a test
        # that drives a real handler / execute_tool (which calls get_neo4j_driver() directly,
        # not this local fixture) works instead of hitting "Neo4j driver not initialised". Same
        # harness gap the PG `pool` fixture had. Reset on teardown.
        from app.db import neo4j as _neo4j_mod

        _prev = _neo4j_mod._driver
        _neo4j_mod._driver = driver
        try:
            yield driver
        finally:
            _neo4j_mod._driver = _prev
    finally:
        await driver.close()
