"""AGE bootstrap against a real AGE (plan T42c).

These run against `loreweave/postgres-knowledge:18` (T42b), which is the only place the
three extensions exist together. They skip without `TEST_AGE_DSN` — which is now a
DEVELOPER convenience only: as of 2026-08-12 `python-integration-tests.yml` builds the
image, runs the image smoke, starts the container and sets `TEST_AGE_DSN`, so nothing here
skips in CI.

⚠️ The paragraph this replaces argued the skip was harmless "because its facts are re-proved
by the image smoke on every build". That was FALSE when written: `scripts/postgres-knowledge-
image-smoke.sh` was wired into no workflow at all, so the fallback proof it deferred to ran
on no build, and `TEST_AGE_DSN` was set by no workflow either. Both halves of the argument
were absent, and the suite reported green in CI by never executing. Found by
`scripts/test-dsn-coverage-gate.py`. Recorded rather than quietly deleted, because the shape
— a skip defended by pointing at another check that turns out not to run — is the one this
repo keeps re-discovering.

Locally, use a database whose name carries a throwaway marker (the same rule CI follows):

    docker run -d --name lw-age-t42c -e POSTGRES_PASSWORD=x -p 7893:5432 \
      loreweave/postgres-knowledge:18
    docker exec lw-age-t42c psql -U postgres -c "CREATE DATABASE loreweave_age_test;"
    TEST_AGE_DSN=postgresql://postgres:x@localhost:7893/loreweave_age_test \
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


# ── injection: the second quoting layer (found by /review-impl, QC-7) ────────


async def test_a_value_containing_the_dollar_quote_tag_cannot_escape_the_sql(age_pool):
    """🔴 REGRESSION for a real injection vector in `AgeGraphStore._run`.

    AGE cannot take query parameters, so values are interpolated into Cypher, and that Cypher
    is itself wrapped in a SQL dollar-quoted string. TWO layers of quoting — and only the
    inner one was being escaped. `_lit` handles quotes, backslashes and newlines correctly
    (each verified), but `$` is not a JSON escape, so a value carrying the delimiter closed
    the SQL string early:

        name = 'evil$CY$ ) as (v agtype); DROP TABLE IF EXISTS pwned; --'
        -> PostgresSyntaxError: syntax error at or near "canonical_name"

    It errored rather than executing — luck, not design. The payload reached the SQL parser
    AS SQL.

    The fix widens the tag until it is absent from the body, so the delimiter cannot be
    forged. This test drives the exact payload end-to-end and then reads the value back:
    **storing it intact is the assertion**, because an adapter that silently mangled or
    dropped the value would also "not be injectable" while being wrong.
    """
    import uuid as _uuid

    from app.adapters.age_graph_store import AgeGraphStore
    from app.db.age_bootstrap import ensure_graph as _ensure

    async with age_pool.acquire() as conn:
        gname = await _ensure(conn, _uuid.uuid4())
    store = AgeGraphStore(age_pool, gname)

    payloads = [
        "evil$CY$ ) as (v agtype); DROP TABLE IF EXISTS pwned; --",
        "$CY$",
        "$CYX$ and $CYXX$ too",   # the widening must survive being anticipated
        'a" OR 1=1 //',
        "back\\slash",   # explicit: an unknown escape is a SyntaxWarning now, an error later
        "line1\nline2",
    ]
    for payload in payloads:
        e = await store.resolve_or_merge_entity(
            user_id=f"u-{_uuid.uuid4().hex[:8]}", project_id="p-inject",
            name=payload, kind="character", source_type="chapter")
        assert e.name == payload, (
            f"payload was not stored intact: {e.name!r} != {payload!r} — an adapter that "
            "mangles input is not 'safe', it is silently lossy"
        )

    # The database is still there. A successful breakout of the earlier payload would have
    # run its trailing statements.
    async with age_pool.acquire() as conn:
        assert await conn.fetchval("SELECT 1") == 1


# ── A23: the write path dropped the port's own parameters ────────────────────


async def test_resolve_or_merge_entity_PERSISTS_the_ports_three_parameters(age_pool):
    """The port declares `auto_created`, `provenance` and `job_id`; this adapter accepted and
    DISCARDED all three, along with every lifecycle field the Neo4j writer maintains.

    That is the root of what A21 found on the READ side: live AGE entities held
    `version = NULL`, and the read-side coalesce was papering over a writer that never wrote
    it. Optimistic concurrency was not merely mis-read on the default backend — it was not
    being maintained at all.

    Driven against a real AGE graph because the defect is in the Cypher, not in Python: a
    unit test with a fake session would assert the string this adapter builds, which is the
    thing under suspicion.
    """
    import uuid as _uuid

    from app.adapters.age_graph_store import AgeGraphStore
    from app.db.age_bootstrap import ensure_graph as _ensure

    async with age_pool.acquire() as conn:
        gname = await _ensure(conn, _uuid.uuid4())
    store = AgeGraphStore(age_pool, gname)

    uid, pid = f"u-{_uuid.uuid4().hex[:8]}", f"p-{_uuid.uuid4().hex[:8]}"
    job = str(_uuid.uuid4())

    first = await store.resolve_or_merge_entity(
        user_id=uid, project_id=pid, name="Kai", kind="person",
        source_type="chapter", confidence=0.9,
        auto_created=True, provenance="extraction", job_id=job,
    )
    assert first.auto_created is True, "the port's `auto_created` reached the graph"
    assert first.version == 1, "a created entity starts at version 1"
    assert first.created_at is not None and first.updated_at is not None

    # The MERGE arm: same identity tuple, so this must UPDATE rather than mint.
    second = await store.resolve_or_merge_entity(
        user_id=uid, project_id=pid, name="Kai", kind="person",
        source_type="chat", confidence=0.9,
        auto_created=False, provenance="human_authored", job_id=str(_uuid.uuid4()),
    )
    assert second.id == first.id, "the upsert minted a second node"
    assert second.version == 2, (
        f"version did not increment on the merge arm ({first.version} -> {second.version}); "
        f"OCC cannot work if the writer never advances it"
    )
    assert second.auto_created is False, (
        "a later auto_created=False call is a REAL extraction claiming the node — the Neo4j "
        "writer documents exactly this arm, and dropping the parameter lost it"
    )

    rows = await store._run(
        f"MATCH (e:Entity {{id: '{first.id}'}}) RETURN e", columns="v agtype")
    from app.adapters.age_graph_store import _props

    props = _props(rows[0]["v"])
    assert sorted(props.get("provenances") or []) == ["extraction", "human_authored"], (
        f"provenances must ACCUMULATE a deduped set, mirroring source_types: "
        f"{props.get('provenances')}"
    )
    assert props.get("created_job_id") == job, (
        "created_job_id credits the job that MINTED the node and must not move to the second "
        "job — the Neo4j writer sets it create-only for exactly this reason"
    )
