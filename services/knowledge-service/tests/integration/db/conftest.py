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


# ── the vector Postgres (plan T23) ───────────────────────────────────────────
#
# A SECOND Postgres, not the one above: `PgVectorStore` runs on the T22 image
# (PG18 + pgvector + pgvectorscale), which the knowledge DB is not. It gets its own env var
# for the same reason `TEST_KNOWLEDGE_DB_URL` never falls back to `KNOWLEDGE_DB_URL` — a
# fallback is how a test suite finds a real database. The fixture lives HERE rather than in
# the test module because this file's contract is that no test opens its own pool: the
# throwaway guard has to be unavoidable, and one that a test file could route around is
# decoration.


def _vector_dsn() -> str | None:
    return os.environ.get("TEST_VECTOR_DB_URL")


@pytest_asyncio.fixture
async def vector_pool():
    """Pool on a disposable pgvector Postgres, with its tables dropped before each test.

    Start one with:

        docker run -d --name lw-vec-test -e POSTGRES_PASSWORD=… \\
          -e POSTGRES_DB=loreweave_vectors_test -p 7995:5432 \\
          loreweave/postgres-knowledge:18
        export TEST_VECTOR_DB_URL=postgresql://postgres:…@localhost:7995/loreweave_vectors_test
    """
    dsn = _vector_dsn()
    if not dsn:
        pytest.skip("TEST_VECTOR_DB_URL not set — skipping live pgvector test")
    _guard_throwaway(dsn)  # refuse a real DB BEFORE any DROP
    try:
        p = await asyncpg.create_pool(dsn, min_size=1, max_size=4, command_timeout=30)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"vector DB unreachable: {exc}")
    try:
        from app.adapters.pg_vector_store import entity_table, passage_table
        from app.db.graph_repos.passages import SUPPORTED_PASSAGE_DIMS

        async with p.acquire() as conn:
            # DROP, not TRUNCATE: these tests also assert on the SCHEMA (which indexes
            # exist, what the planner does with them), so a leftover index from a previous
            # run would let a test pass on somebody else's DDL.
            for dim in SUPPORTED_PASSAGE_DIMS:
                for table in (passage_table(dim), entity_table(dim)):
                    await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        yield p
    finally:
        await p.close()


# The dev graph runs on 7687 inside the compose network and 7688 on the host, and it holds
# REAL data. These tests create and DETACH DELETE nodes, so pointing TEST_NEO4J_URI at it
# would write into somebody's book. The Postgres fixture above has refused a non-throwaway
# DSN since the kg-integration-tests-truncate-shared-dev-db incident; this one never did —
# closed in plan T20.
#
# Neo4j Community has no multi-database, so "throwaway" cannot be a database NAME here the
# way it is for Postgres. The equivalent is a DEDICATED INSTANCE: an explicit opt-in, plus a
# refusal of the ports the dev stack publishes.
# 7687/7688 are the base stack's; 27687/27688 are the SAME graphs republished by the
# isolated stack (`infra/docker-compose.isolated.yml`, base + 20000). T42a found the gap the
# hard way: the guard matched `f":{port}" in uri` as a SUBSTRING, and ":7688" is not a
# substring of "localhost:27688" — so the isolated dev graph sailed straight through a check
# written to refuse it, and a conformance run wrote into it. A port map added months after
# the guard silently widened what the guard was blind to.
_DEV_NEO4J_PORTS = ("7687", "7688", "27687", "27688")


def _neo4j_port(uri: str) -> str | None:
    """The PORT component, not a substring of the URI. See `_DEV_NEO4J_PORTS`."""
    from urllib.parse import urlsplit

    try:
        # `bolt://host:7688` parses; a bare `host:7688` does not, so give it a scheme.
        parsed = urlsplit(uri if "://" in uri else f"bolt://{uri}")
        return str(parsed.port) if parsed.port else None
    except ValueError:
        return None


def _guard_throwaway_neo4j(uri: str) -> None:
    if os.environ.get("TEST_NEO4J_ALLOW_SHARED") == "1":
        # Escape hatch for CI, where the graph IS disposable and its port is whatever the
        # service container published. Explicit, so nobody reaches it by accident.
        return
    if _neo4j_port(uri) in _DEV_NEO4J_PORTS:
        raise RuntimeError(
            f"REFUSING: TEST_NEO4J_URI {uri!r} looks like the shared DEV graph "
            f"(ports {'/'.join(_DEV_NEO4J_PORTS)} — the base stack's and the isolated "
            "stack's republication of them). These tests CREATE and DETACH DELETE nodes — "
            "point them at a disposable Neo4j instance of their own, or set "
            "TEST_NEO4J_ALLOW_SHARED=1 if the target really is disposable."
        )


from app.db.graph_repos.vector_indexes import ensure_passage_vector_index
from app.domain.passage_contract import SUPPORTED_PASSAGE_DIMS


def _neo4j_dsn() -> tuple[str, str, str] | None:
    uri = os.environ.get("TEST_NEO4J_URI")
    if not uri:
        return None
    _guard_throwaway_neo4j(uri)
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

@pytest_asyncio.fixture
async def passage_vector_index(neo4j_driver):
    """T65 — these reads need `passage_embeddings_<dim>`, and NOTHING creates it any more.

    T25 ③ deleted the passage vector DDL from `neo4j_schema.cypher` because §3.3 cut the
    passage scope over to Postgres. That was correct and it left a third consumer nobody
    named: T25j/T25n found the two BENCHMARKS and gave them
    `ensure_passage_vector_index`; this suite reads the same index and was missed. It went
    unnoticed because dev and iso still hold the index PHYSICALLY — removing a declaration
    does not drop what exists — so only a FRESH Neo4j shows it, and the unit suite cannot.

    Same remedy as the benchmarks: the reader owns its index.
    """
    async with neo4j_driver.session() as session:
        for dim in SUPPORTED_PASSAGE_DIMS:
            await ensure_passage_vector_index(session, dim)
    yield
