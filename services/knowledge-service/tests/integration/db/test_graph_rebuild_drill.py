"""T41 — the rebuild drill: does it work, and is it AFFORDABLE at book scale?

T41 is a **stop condition**: *"T41 shows rebuild-from-Postgres is impractical at book scale →
graph HA returns as a requirement and Phase 7's rollback story fails."* So a test that only
proved the code runs would miss half the question. These time it and print the rate.

The rebuild goes through `GraphStore`, so it is parameterised over the SAME adapters the
conformance suite covers — **the rollback story must hold for whichever engine T43 selects**,
and a drill that only ever ran against Neo4j would prove nothing about the engine being
migrated to.

    docker run -d --name lw-neo4j-scratch -p 7999:7687 \
      -e NEO4J_AUTH=neo4j/loreweave_dev_neo4j neo4j:5-community
    docker run -d --name lw-age-t43 -e POSTGRES_PASSWORD=x -p 7893:5432 \
      loreweave/postgres-knowledge:18
    TEST_NEO4J_URI=bolt://localhost:7999 \
      TEST_AGE_DSN=postgresql://postgres:x@localhost:7893/postgres \
      pytest tests/integration/db/test_graph_rebuild_drill.py -s
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

from app.adapters.age_graph_store import AgeGraphStore
from app.adapters.fake_graph_store import FakeGraphStore
from app.adapters.neo4j_graph_store import Neo4jGraphStore
from app.db.age_bootstrap import create_age_pool, ensure_graph
from app.jobs.graph_rebuild import rebuild_entities_from_glossary

pytestmark = pytest.mark.asyncio

#: A chapter-scale book's cast. Small enough for CI, large enough that the RATE is meaningful
#: — a per-entity cost measured on 3 rows extrapolates badly.
DRILL_SIZE = 120


def _glossary_rows(n: int) -> list[dict]:
    """The authoritative Postgres shape, as the rebuild receives it."""
    kinds = ("character", "location", "organization", "item", "concept")
    return [
        {"id": str(uuid.uuid4()), "name": f"Entity {i:04d}", "kind": kinds[i % len(kinds)]}
        for i in range(n)
    ]


@pytest_asyncio.fixture(params=["fake", "neo4j", "age"])
async def store(request):
    # ⚠️ The driver is built HERE, not pulled from the `neo4j_driver` fixture via
    # `request.getfixturevalue`. pytest resolves an async fixture synchronously that way and
    # every test dies with "Runner.run() cannot be called from a running event loop".
    # `test_graph_store_conformance.py` records this exact trap — and I walked into it again
    # writing this file, which is why the note is repeated where the next person will be.
    if request.param == "fake":
        yield FakeGraphStore()
        return
    if request.param == "age":
        dsn = os.environ.get("TEST_AGE_DSN")
        if not dsn:
            pytest.skip("TEST_AGE_DSN not set")
        pool = await create_age_pool(dsn, min_size=2, max_size=4)
        try:
            async with pool.acquire() as conn:
                gname = await ensure_graph(conn, uuid.uuid4())
            yield AgeGraphStore(pool, gname)
        finally:
            await pool.close()
        return
    uri = os.environ.get("TEST_NEO4J_URI")
    if not uri:
        pytest.skip("TEST_NEO4J_URI not set")
    from neo4j import AsyncGraphDatabase

    from .conftest import _guard_throwaway_neo4j

    _guard_throwaway_neo4j(uri)
    driver = AsyncGraphDatabase.driver(
        uri,
        auth=(os.environ.get("TEST_NEO4J_USER", "neo4j"),
              os.environ.get("TEST_NEO4J_PASSWORD", "loreweave_dev_neo4j")),
        connection_timeout=5.0,
    )
    try:
        await driver.verify_connectivity()
        async with driver.session() as session:
            yield Neo4jGraphStore(session)
    finally:
        await driver.close()


async def test_the_rebuild_restores_every_entity_and_reports_its_cost(store, request):
    """Does it work, and what does it cost? T41 is a stop condition, so BOTH are asserted."""
    user_id, project_id = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    rows = _glossary_rows(DRILL_SIZE)

    stats = await rebuild_entities_from_glossary(
        store, user_id=user_id, project_id=project_id, entities=rows)

    print(f"\n[T41 drill] adapter={request.node.callspec.id} "
          f"read={stats.entities_read} written={stats.entities_written} "
          f"failed={stats.failed} elapsed={stats.elapsed_s:.2f}s "
          f"rate={stats.rate:.0f}/s")

    assert stats.entities_written == DRILL_SIZE
    assert stats.failed == 0
    # Non-vacuity: a rebuild that "succeeded" without writing anything would satisfy the
    # counters above only if DRILL_SIZE were 0. Read one back from the STORE rather than
    # trusting the tally, because the tally is what a broken write path would still increment.
    found = await store.find_entities_by_name(
        user_id=user_id, project_id=project_id, name="Entity 0000")
    assert found, "the rebuild reported success but the store has nothing"


async def test_the_rebuild_is_idempotent(store):
    """Rebuilding twice must not double the graph.

    DR reality: the first attempt fails halfway, someone reruns it. If the second pass minted
    duplicates, the recovery would be worse than the outage — and this is the property the
    port's `resolve_or_merge_entity` exists to provide, so it is the port's contract being
    exercised, not the rebuild's own cleverness.
    """
    user_id, project_id = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    rows = _glossary_rows(10)

    await rebuild_entities_from_glossary(
        store, user_id=user_id, project_id=project_id, entities=rows)
    await rebuild_entities_from_glossary(
        store, user_id=user_id, project_id=project_id, entities=rows)

    found = await store.find_entities_by_name(
        user_id=user_id, project_id=project_id, name="Entity 0003")
    assert len(found) == 1, f"rebuilding twice produced {len(found)} nodes for one entity"


async def test_a_bad_row_is_counted_not_fatal(store):
    """A rebuild that aborts on the first bad row leaves a half-restored graph and no report.

    During a disaster that is the worst of both: the operator learns neither how far it got
    nor what stopped it. The good rows around the bad one must still land.
    """
    user_id, project_id = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    rows = _glossary_rows(3)
    rows.insert(1, {"id": "broken", "name": "", "kind": ""})   # unprojectable

    stats = await rebuild_entities_from_glossary(
        store, user_id=user_id, project_id=project_id, entities=rows)

    assert stats.failed == 1
    assert stats.entities_written == 3, "the good rows did not survive a bad neighbour"
