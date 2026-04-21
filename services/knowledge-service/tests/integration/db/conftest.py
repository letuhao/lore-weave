"""Integration-test DB fixtures.

Connects to a real Postgres using TEST_KNOWLEDGE_DB_URL (or falls back to
KNOWLEDGE_DB_URL). If the DB is unreachable, the test is skipped — this
keeps `pytest` runnable on a dev host without Docker, while Gate 2 runs
against the compose-managed Postgres so the DB is guaranteed.

Also provides a shared `neo4j_driver` fixture for K11.5+ Neo4j repo
tests (skipped when TEST_NEO4J_URI is unset).
"""

import os

import asyncpg
import pytest
import pytest_asyncio

from app.db.migrate import run_migrations
from app.db.neo4j_schema import run_neo4j_schema


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
            "TRUNCATE knowledge_projects, knowledge_summaries, "
            "user_knowledge_budgets, job_logs "
            "RESTART IDENTITY CASCADE"
        )
    try:
        yield p
    finally:
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
        yield driver
    finally:
        await driver.close()
