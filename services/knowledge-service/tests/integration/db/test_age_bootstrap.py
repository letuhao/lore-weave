"""AGE bootstrap against a real AGE (plan T42c).

These run against `loreweave/postgres-knowledge:18` (T42b), which is the only place the
three extensions exist together. They skip without `TEST_AGE_DSN`, and the skip is fine
here in a way it is NOT for `test_graph_store_conformance.py`: that suite makes a
correctness claim about an adapter, so a silent degradation there would be a lie. This one
proves environment facts, and its facts are re-proved by the image smoke on every build.

    docker run -d --name lw-age-t42c -e POSTGRES_PASSWORD=x -p 7893:5432 \
      loreweave/postgres-knowledge:18
    TEST_AGE_DSN=postgresql://postgres:x@localhost:7893/postgres \
      pytest tests/integration/db/test_age_bootstrap.py
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

from app.db.age_bootstrap import (
    AGE_SEARCH_PATH,
    create_age_pool,
    ensure_graph,
    graph_name_for,
    init_age_connection,
)


def _dsn() -> str:
    dsn = os.environ.get("TEST_AGE_DSN")
    if not dsn:
        pytest.skip("TEST_AGE_DSN not set — needs the T42b image (AGE + pgvector)")
    return dsn


@pytest_asyncio.fixture
async def age_pool():
    pool = await create_age_pool(_dsn(), min_size=2, max_size=4)
    try:
        yield pool
    finally:
        await pool.close()


# ── naming: the rules were measured against AGE, so assert them against AGE ──


def test_a_bare_uuid_would_be_rejected_so_the_scheme_transforms_it():
    """Both transformations are load-bearing, and this pins WHY rather than just the output."""
    pid = "019f37f0-cb1c-70d1-9a3e-2c672b0086e5"
    name = graph_name_for(pid)
    assert name == "g_019f37f0cb1c70d19a3e2c672b0086e5"
    assert "-" not in name, "AGE rejects dashes in a graph name"
    assert not name[0].isdigit(), (
        "AGE rejects a leading digit, and ~half of all UUIDs start with one — a scheme that "
        "only stripped dashes would pass in testing and fail for half of real projects"
    )
    assert len(name) >= 3, "AGE's minimum graph-name length is 3"


def test_an_unscoped_project_gets_the_shared_graph():
    assert graph_name_for(None) == "g_shared"


def test_a_name_that_could_not_be_a_legal_identifier_is_refused_here():
    with pytest.raises(ValueError):
        graph_name_for("")


async def test_the_derived_name_is_actually_accepted_by_age(age_pool):
    """The regex is belt and braces; AGE is the authority. This asks AGE."""
    async with age_pool.acquire() as conn:
        name = await ensure_graph(conn, uuid.uuid4())
        got = await conn.fetchval(
            "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1", name)
        assert got == 1


# ── session state: the trap this module exists for ──


async def test_every_pooled_connection_can_run_cypher(age_pool):
    """`LOAD` and `search_path` are per-SESSION. Without the pool's `init` hook this fails
    on whichever connection happened not to be set up — an intermittent bug that looks like
    a broken AGE install rather than a missing session step.

    The pool holds >=2 connections and they are held OPEN simultaneously, so this genuinely
    exercises more than one; acquiring them in sequence could hand back the same connection
    twice and prove nothing.
    """
    async with age_pool.acquire() as c1, age_pool.acquire() as c2:
        for conn in (c1, c2):
            path = await conn.fetchval("SHOW search_path")
            assert "ag_catalog" in path, f"search_path lacks ag_catalog: {path!r}"
        gname = await ensure_graph(c1, uuid.uuid4())
        # Created on c1, queried on c2 — the exact cross-connection case that fails when the
        # session setup is done once at startup instead of per connection.
        rows = await c2.fetch(
            f"SELECT * FROM cypher('{gname}', $$ RETURN 1 $$) as (v agtype)")
        assert rows, "a graph created on one pooled connection was unusable on another"


async def test_ensure_graph_is_idempotent(age_pool):
    """`create_graph` has no IF NOT EXISTS and RAISES when the graph exists, so this asks
    `ag_graph` instead. A second call must be a no-op, not an error."""
    pid = uuid.uuid4()
    async with age_pool.acquire() as conn:
        first = await ensure_graph(conn, pid)
        second = await ensure_graph(conn, pid)
        assert first == second
        assert await conn.fetchval(
            "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1", first) == 1


async def test_two_projects_get_two_graphs(age_pool):
    async with age_pool.acquire() as conn:
        a = await ensure_graph(conn, uuid.uuid4())
        b = await ensure_graph(conn, uuid.uuid4())
        assert a != b
        assert await conn.fetchval(
            "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = ANY($1::text[])",
            [a, b]) == 2


async def test_the_search_path_constant_is_what_the_session_actually_gets(age_pool):
    """Pins the constant to observed behaviour — otherwise editing `AGE_SEARCH_PATH` to
    something AGE tolerates but resolves differently would go unnoticed."""
    async with age_pool.acquire() as conn:
        assert AGE_SEARCH_PATH.split(",")[0].strip() == "ag_catalog"
        path = await conn.fetchval("SHOW search_path")
        assert path.split(",")[0].strip() == "ag_catalog", (
            "ag_catalog must come FIRST or cypher()/agtype resolve to something else"
        )


async def test_the_search_path_SURVIVES_a_release_back_to_the_pool(age_pool):
    """THE regression test for this module, and the bug it was written after.

    Putting `SET search_path` on asyncpg's `init` hook looks correct — once per physical
    connection — and works for exactly ONE acquire. asyncpg issues `RESET ALL` when a
    connection is released, which returns every GUC to its STARTUP value, so the `SET` is
    undone. The failure therefore appears on the second use of a connection, not the first:
    it passes in any script that never releases, and in the first request after a restart.

    Acquiring twice in sequence forces a release in between, which is the whole point —
    holding two connections at once would not exercise the reset at all.
    """
    async with age_pool.acquire() as conn:
        first = await conn.fetchval("SHOW search_path")
    async with age_pool.acquire() as conn:
        second = await conn.fetchval("SHOW search_path")
    assert second.split(",")[0].strip() == "ag_catalog", (
        f"search_path was {first!r} on first acquire and {second!r} after a release — "
        "RESET ALL wiped it, so it must be a server_setting (startup parameter), not a SET"
    )


async def test_an_init_only_pool_is_the_broken_shape_this_module_avoids():
    """Pins the trap itself, so the module's design cannot be 'simplified' back into it.

    Builds the pool the tempting way — `init` doing both LOAD and SET — and asserts the
    search_path is GONE after a release. If a future asyncpg stops resetting GUCs this test
    reds and the docstring's reasoning gets re-examined, which is the right outcome either
    way.
    """
    import asyncpg

    async def init_both(conn):
        await init_age_connection(conn)
        await conn.execute(f"SET search_path = {AGE_SEARCH_PATH}")

    pool = await asyncpg.create_pool(_dsn(), min_size=1, max_size=1, init=init_both)
    try:
        async with pool.acquire() as conn:
            assert (await conn.fetchval("SHOW search_path")).startswith("ag_catalog")
        async with pool.acquire() as conn:
            after = await conn.fetchval("SHOW search_path")
        assert not after.startswith("ag_catalog"), (
            "asyncpg no longer resets GUCs on release — `server_settings` may no longer be "
            "required, so re-read the module docstring before simplifying it"
        )
    finally:
        await pool.close()
