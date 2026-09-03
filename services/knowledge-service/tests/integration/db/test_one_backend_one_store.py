"""T54c — with the backend set to `age`, BOTH halves of the service read the same store.

🔴 **This is the measurement that stopped T54, inverted into a test.** Flipping
`KNOWLEDGE_GRAPH_BACKEND=age` on dev put the 19 `GraphStore` adopters on AGE and the 54
`graph_repos` binders on Neo4j — one conceptual graph, two stores, one of them empty, inside a
single service:

    18:39:50  K11.3: Neo4j schema applied successfully   <- Neo4j, 4926 entities
    18:39:51  AGE pool ready (graph=g_shared)            <- AGE, EMPTY

Extraction and context assembly are port adopters, so they would have read the empty one
without erroring. The pin was reverted; the plan calls this "the fragmentation this entire plan
exists to remove, recreated by its own cutover".

The split existed for exactly one reason: `graph_session()` could only ever return a Bolt
session. Since T83/T84 the repo layer runs on either engine, so the factory returns whichever
one is configured — and the two halves meet. The property is worth a test rather than a note,
because its failure mode is **silence**: an empty graph is a valid graph, and every read
against it succeeds and returns nothing.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

_GRAPH_ENV = "KNOWLEDGE_GRAPH_BACKEND"


@pytest_asyncio.fixture
async def age_backend(monkeypatch):
    """Point the whole process at AGE, with a throwaway graph and a real pool."""
    dsn = os.environ.get("TEST_AGE_DSN")
    if not dsn:
        pytest.skip("TEST_AGE_DSN not set")
    pytest.importorskip("asyncpg")

    from app.db import age_pool as age_pool_mod
    from app.db.age_bootstrap import create_age_pool

    # ⚠️ `create_age_pool`, not `asyncpg.create_pool(init=…)`. Its own docstring says why, and
    # the first cut of this fixture proved it: a pool with only `init` set works until a
    # connection is RELEASED, after which `cypher(unknown, unknown) does not exist` — the
    # search_path is a `server_settings` concern, not an init-hook one. The repo-layer half
    # passed and the PORT half failed, which reads exactly like the split this file tests for.
    pool = await create_age_pool(dsn, min_size=1, max_size=2)
    graph = "one_store_probe"
    async with pool.acquire() as conn:
        # `ag_catalog` has to be on the path before `ag_graph` resolves — the pool's `init`
        # sets it per connection, but the extension may only have been created a moment ago
        # by `ensure_age_extension`, on a connection that predates it.
        await conn.execute("LOAD 'age';")
        await conn.execute("SET search_path = ag_catalog, public;")
        if await conn.fetchval("SELECT count(*) FROM ag_graph WHERE name = $1", graph):
            await conn.execute(f"SELECT drop_graph('{graph}', true)")
        await conn.execute(f"SELECT create_graph('{graph}')")

    monkeypatch.setenv(_GRAPH_ENV, "age")
    monkeypatch.setattr(age_pool_mod, "_POOL", pool)
    # Patched in BOTH modules that resolve the name. `graph_store_provider` does
    # `from app.db.age_bootstrap import graph_name_for`, so it holds its own reference and
    # patching only the definition leaves the port on `g_shared` — which is how the first run
    # of this fixture failed: the repo-layer half wrote to the probe graph and the PORT half
    # looked in the real one. A split, produced by the test for the split.
    monkeypatch.setattr("app.db.age_bootstrap.graph_name_for", lambda _pid=None: graph)
    monkeypatch.setattr("app.adapters.graph_store_provider.graph_name_for",
                        lambda _pid=None: graph)
    try:
        yield graph
    finally:
        async with pool.acquire() as conn:
            await conn.execute("LOAD 'age';")
            await conn.execute("SET search_path = ag_catalog, public;")
            await conn.execute(f"SELECT drop_graph('{graph}', true)")
        await pool.close()


async def test_graph_session_follows_the_configured_backend(age_backend):
    """`graph_session()` — the name is historical — must hand back an AGE session when the
    configuration says AGE. This one function is what the whole split turned on."""
    from app.db.age_session import AgeCypherSession
    from app.db.graph import graph_session
    from app.db.neo4j_helpers import engine_of

    async with graph_session() as session:
        assert isinstance(session, AgeCypherSession), (
            f"the repo layer got a {type(session).__name__} while the backend is `age` — this "
            f"is the T54b split: the port adopters would read AGE and this half would read "
            f"Neo4j, and an empty graph answers every read without erroring"
        )
        assert engine_of(session) == "age", (
            "the session does not declare its engine, so every template renders as Neo4j "
            "Cypher against an AGE graph"
        )


async def test_the_repo_layer_and_the_PORT_read_the_SAME_store(age_backend):
    """The property the row is actually about: write through one half, read through the other.

    A `merge_entity` from the repo layer must be visible to a `GraphStore` read, because they
    are supposed to be the same graph. Under the split they were not, and nothing said so.
    """
    from app.adapters.graph_store_provider import get_graph_store
    from app.db.graph import graph_session
    from app.db.graph_repos import entities as en

    uid = f"u-{uuid.uuid4().hex[:8]}"
    proj = f"p-{uuid.uuid4().hex[:8]}"

    async with graph_session() as session:
        written = await en.merge_entity(session, user_id=uid, project_id=proj, name="Kai",
                                        kind="person", source_type="chapter")

    async with graph_session() as session:
        store = get_graph_store(session)
        # `find_entities_by_name` rather than a get-by-id: the port grows BY DEMAND (§10.1) and
        # has 21 operations, not a mirror of the repo layer. This is the one that answers
        # "is that entity in this store".
        seen = await store.find_entities_by_name(user_id=uid, project_id=proj, name="Kai")

    assert [e.id for e in seen] == [written.id], (
        f"the port saw {[e.id for e in seen]} where the repo layer had just written "
        f"{written.id}. That is the T54b split exactly: two stores behind one service, and "
        f"the read simply returns nothing — an empty graph is a valid graph."
    )


async def test_pinning_an_engine_OVERRIDES_the_configuration(age_backend):
    """`engine="neo4j"` is what the benchmarks and one-shot scripts use — they exist to compare
    engines or ran against a known one, so they must be able to name one even while the
    process is configured for the other. Without this the backend flip would silently
    repoint every benchmark at the engine it was measuring against."""
    from app.db.graph import graph_session
    from app.db.neo4j import Neo4jNotConfiguredError

    # No Bolt driver is initialised in this process, so asking for Neo4j must reach the Neo4j
    # path and fail THERE — proving the pin was honoured rather than quietly ignored.
    with pytest.raises(Neo4jNotConfiguredError):
        graph_session(engine="neo4j")


async def test_an_UNKNOWN_backend_refuses_rather_than_guessing(age_backend, monkeypatch):
    """Rule 9. A typo in the deploy config must not silently select an engine."""
    from app.db.graph import graph_session

    monkeypatch.setenv(_GRAPH_ENV, "memgraph")
    with pytest.raises(ValueError, match="not a graph backend"):
        graph_session()
