"""T25q — `age_anchor_scores` against a REAL AGE graph.

The resolver is what makes §3.3c's answer real: `anchor_score` is read from its authority per
query instead of copied onto the vector row, where it would drift by construction. A hand-run
proves it once; this is the version CI runs.

⚠️ **Three of these four cases are about what the resolver must NOT do.** `glossary.py` ranks
by `attributes["anchor_score"] or 0.0`, so every way of being wrong here collapses a weighted
ranking into raw cosine order — an answer that looks correct and is not:

    inventing a score for an unknown id   -> that entity ranks as if anchored
    leaking across tenants               -> another user's bucket ranks this user's hits
    returning {} on any hiccup           -> every score becomes 0.0, order becomes cosine
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

from app.adapters.age_anchor_scores import age_anchor_scores
from app.db.graph_repos import entities as en

_GRAPH = "anchor_scores_conformance"


class _OneConnPool:
    """Pool-shaped wrapper over a single connection — the resolver only ever `acquire()`s."""

    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Acquire:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Acquire()


@pytest_asyncio.fixture
async def age_conn():
    dsn = os.environ.get("TEST_AGE_DSN")
    if not dsn:
        pytest.skip("TEST_AGE_DSN not set — the AGE half is not being exercised")
    asyncpg = pytest.importorskip("asyncpg")
    from app.db.age_session import AgeCypherSession

    conn = await asyncpg.connect(dsn)
    try:
        # 🔴 CREATE the extension, do not assume it. `prepare()` does `LOAD 'age'` and puts
        # `ag_catalog` on the search path — it does NOT run `CREATE EXTENSION`, which is what
        # actually creates that schema and with it `ag_graph` / `drop_graph`. The app reaches
        # them through `create_age_pool()` → `ensure_age_extension()`, and this fixture
        # connects with raw asyncpg, so it never passes that seam.
        #
        # Against a FRESH database the next line therefore failed, not the test:
        #
        #   asyncpg.exceptions.UndefinedTableError: relation "ag_graph" does not exist
        #   asyncpg.exceptions.UndefinedFunctionError: function drop_graph(unknown, boolean)
        #   does not exist
        #
        # The CI leg creates `loreweave_age_test` empty on purpose and says so: "No CREATE
        # EXTENSION here: create_age_pool() calls ensure_age_extension() itself ... so a
        # missing extension would be a real bug rather than a setup gap this step papered
        # over." That reasoning holds for the app; this fixture is not the app. Same statement
        # `ensure_age_extension` runs, on a connection instead of a pool.
        await conn.execute("CREATE EXTENSION IF NOT EXISTS age")
        await AgeCypherSession.prepare(conn)
        if await conn.fetchval("SELECT count(*) FROM ag_graph WHERE name = $1", _GRAPH):
            await conn.execute(f"SELECT drop_graph('{_GRAPH}', true)")
        await conn.execute(f"SELECT create_graph('{_GRAPH}')")
        yield conn
    finally:
        try:
            await conn.execute(f"SELECT drop_graph('{_GRAPH}', true)")
        finally:
            await conn.close()


@pytest_asyncio.fixture
async def resolver(age_conn, monkeypatch):
    from app.db.age_session import AgeCypherSession
    import app.adapters.age_anchor_scores as mod

    # The module binds `graph_name_for` at import, so the patch goes HERE rather than on
    # `age_bootstrap` — a detail that cost a probe run to find, and one a future reader of
    # this fixture would otherwise pay for again.
    monkeypatch.setattr(mod, "graph_name_for", lambda _p=None: _GRAPH)
    session = AgeCypherSession(age_conn, _GRAPH)
    return age_anchor_scores(_OneConnPool(age_conn)), session


@pytest.mark.asyncio
async def test_it_reads_the_score_from_the_graph_and_leaves_the_unknown_ABSENT(resolver):
    resolve, session = resolver
    uid, proj = f"u-{uuid.uuid4().hex[:8]}", f"p-{uuid.uuid4().hex[:8]}"
    anchored = await en.merge_entity(session, user_id=uid, project_id=proj, name="Anchored",
                                     kind="person", source_type="chapter")
    plain = await en.merge_entity(session, user_id=uid, project_id=proj, name="Plain",
                                  kind="person", source_type="chapter")
    await age_conn_set_score(session, anchored.id, 0.6363636363636364)

    ghost = f"never-existed-{uuid.uuid4().hex[:8]}"
    got = await resolve(uid, [anchored.id, plain.id, ghost])

    assert got[anchored.id] == pytest.approx(0.6363636363636364)
    assert got[plain.id] == 0.0                      # merge_entity's coalesce default
    # ABSENT, not None and not 0.0. The store maps a miss to None itself; inventing a value
    # here would make an entity the authority never heard of rank as if it were anchored.
    assert ghost not in got


@pytest.mark.asyncio
async def test_it_does_NOT_cross_tenants(resolver):
    """The `user_id` predicate is the tenancy boundary, not a filter for tidiness: another
    user's bucket ranking this user's hits is a cross-tenant read with no error attached."""
    resolve, session = resolver
    uid, proj = f"u-{uuid.uuid4().hex[:8]}", f"p-{uuid.uuid4().hex[:8]}"
    mine = await en.merge_entity(session, user_id=uid, project_id=proj, name="Mine",
                                 kind="person", source_type="chapter")
    await age_conn_set_score(session, mine.id, 1.0)

    assert await resolve(f"someone-else-{uuid.uuid4().hex[:6]}", [mine.id]) == {}


@pytest.mark.asyncio
async def test_an_empty_id_list_asks_the_database_NOTHING(resolver):
    """A search with no hits must not pay for a query, and `IN []` is a shape AGE need never
    be handed."""
    resolve, _ = resolver
    assert await resolve("u-any", []) == {}


async def age_conn_set_score(session, entity_id: str, score: float) -> None:
    rows = await session._conn.fetch(
        f"SELECT * FROM cypher('{session._graph}', $s$ "
        f"MATCH (e:Entity {{id: '{entity_id}'}}) SET e.anchor_score = {score} "
        f"RETURN e.anchor_score $s$) AS t(v agtype)")
    assert rows, f"the fixture failed to set a score on {entity_id}"
