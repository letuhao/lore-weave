"""T54e — the migration, proven against a REAL Neo4j and a REAL AGE.

The unit tests hold the property policy; nothing they assert can prove that AGE accepts what
this module writes, or that the migrated graph reads back the way the service expects. Only
two live engines can, and that is the half T54d found missing on dev: `KNOWLEDGE_GRAPH_BACKEND`
said `age`, the AGE store held zero entities, and every gate in the tree was green.

    docker run -d --name lw-neo4j-scratch -p 7999:7687 \
      -e NEO4J_AUTH=neo4j/loreweave_dev_neo4j neo4j:5-community
    docker run -d --name lw-age-t54e -e POSTGRES_PASSWORD=x -p 7893:5432 \
      loreweave/postgres-knowledge:18
    TEST_NEO4J_URI=bolt://localhost:7999 \
      TEST_AGE_DSN=postgresql://postgres:x@localhost:7893/postgres \
      pytest tests/integration/db/test_neo4j_to_age_migration_live.py

Both are throwaways (rule 6). The fixture seeds its own source graph and DETACH DELETEs it in
a finally, per this directory's convention — Neo4j community has no per-test truncate.
"""

from __future__ import annotations

import os
import re
import uuid

import pytest
import pytest_asyncio

from app.db.age_bootstrap import create_age_pool, graph_name_for
from app.db.age_session import age_repo_session
from app.db.migrations.neo4j_to_age import (
    PER_PROJECT_LAYOUT,
    SHARED_GRAPH,
    migrate,
    verify,
)

pytestmark = pytest.mark.asyncio


#: `verify` compares EXACT counts, which is the cutover's own precondition — dev's 433 project
#: graphs and `g_shared` all hold zero. A destination carrying rows from another test reports
#: EXTRA, and the first run of this file did exactly that (`EXTRA g_shared/Book: 2, source 1`),
#: which reads like a migration defect and is not one. So the precondition is ESTABLISHED here
#: rather than hoped for — behind the same throwaway guard the rest of this directory uses,
#: because establishing it means dropping every graph in the database.
_THROWAWAY = re.compile(r"(?i)(test|smoke|audit|scratch|throwaway|tmp|sandbox|ephemeral)")


def _guard_throwaway(dsn: str) -> None:
    db = dsn.rsplit("/", 1)[-1].split("?", 1)[0]
    if not _THROWAWAY.search(db):
        raise RuntimeError(
            f"REFUSING: TEST_AGE_DSN database {db!r} is not a throwaway DB (the name must "
            f"contain test/smoke/audit/…). This fixture DROPs every AGE graph in it — point "
            f"it at a disposable DB, never a real knowledge store."
        )


@pytest_asyncio.fixture
async def age_pool():
    dsn = os.environ.get("TEST_AGE_DSN")
    if not dsn:
        pytest.skip("TEST_AGE_DSN not set — the migration needs a real destination")
    _guard_throwaway(dsn)  # refuse a real store BEFORE the drop below
    pool = await create_age_pool(dsn, min_size=2, max_size=4)
    try:
        async with pool.acquire() as conn:
            for row in await conn.fetch("SELECT name FROM ag_catalog.ag_graph"):
                await conn.execute(
                    f"SELECT ag_catalog.drop_graph('{row['name']}', true)"
                )
        yield pool
    finally:
        await pool.close()


async def _graph_exists(pool, project_key) -> bool:
    async with pool.acquire() as conn:
        return bool(
            await conn.fetchval(
                "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1",
                graph_name_for(project_key),
            )
        )


@pytest_asyncio.fixture
async def seeded(neo4j_driver):
    """A source graph with the shapes the dev census actually holds.

    Deliberately NOT a minimal fixture. Each element is a property class the migration has to
    decide about, and leaving one out is how a green run hides a defect:

      * `datetime()` timestamps        — the ZONED DATETIME the conversion exists for
      * `event_date_iso` as a STRING   — the in-world date that must NOT be converted
      * `embedding_1024` float list    — the property that is dropped
      * `aliases` string list          — the list that must SURVIVE the drop
      * an unscoped Book/Part pair     — the `g_shared` component
      * two projects                   — so a cross-graph leak has somewhere to leak to
    """
    p1 = f"t54e-{uuid.uuid4()}"
    p2 = f"t54e-{uuid.uuid4()}"
    book = f"t54e-book-{uuid.uuid4()}"
    part = f"t54e-part-{uuid.uuid4()}"
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (e1:Entity {id: $e1, project_id: $p1, user_id: 'u1', name: 'Kai',
                               canonical_name: 'kai', kind: 'character', aliases: ['Kai', 'K'],
                               confidence: 0.5, embedding_1024: [0.1, 0.2, 0.3],
                               created_at: datetime(), updated_at: datetime()})
            CREATE (e2:Entity {id: $e2, project_id: $p1, user_id: 'u1', name: 'Mira',
                               canonical_name: 'mira', kind: 'character', aliases: ['Mira'],
                               confidence: 0.9, created_at: datetime(), updated_at: datetime()})
            CREATE (e3:Entity {id: $e3, project_id: $p2, user_id: 'u2', name: 'Other',
                               canonical_name: 'other', kind: 'character', aliases: [],
                               confidence: 0.1, created_at: datetime(), updated_at: datetime()})
            CREATE (v1:Event  {id: $v1, project_id: $p1, user_id: 'u1', title: 'The duel',
                               canonical_title: 'the duel', event_date_iso: '1247-03-02',
                               created_at: datetime(), updated_at: datetime()})
            CREATE (b:Book {book_id: $book, book_title: 'B', created_at: datetime(),
                            updated_at: datetime(), summary_embedding: [0.4, 0.5]})
            CREATE (pt:Part {part_id: $part, book_id: $book, part_index: 1,
                             created_at: datetime(), updated_at: datetime()})
            CREATE (e1)-[:RELATES_TO {id: $r1, predicate: 'knows', confidence: 0.7,
                                      subject_id: $e1, object_id: $e2, user_id: 'u1',
                                      created_at: datetime(), updated_at: datetime(),
                                      valid_from: datetime()}]->(e2)
            CREATE (e1)-[:RELATES_TO {id: $r2, predicate: 'rivals', confidence: 0.4,
                                      subject_id: $e1, object_id: $e2, user_id: 'u1',
                                      created_at: datetime(), updated_at: datetime(),
                                      valid_from: datetime()}]->(e2)
            CREATE (b)-[:HAS_CHILD]->(pt)
            """,
            e1=f"{p1}-e1", e2=f"{p1}-e2", e3=f"{p2}-e3", v1=f"{p1}-v1",
            p1=p1, p2=p2, book=book, part=part, r1=f"{p1}-r1", r2=f"{p1}-r2",
        )
    try:
        yield {"p1": p1, "p2": p2, "book": book, "part": part}
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.project_id IN [$p1, $p2] OR n.book_id = $book "
                "DETACH DELETE n",
                p1=p1, p2=p2, book=book,
            )
        # AGE needs no cleanup here: `age_pool` DROPs every graph before each test, which is
        # the empty-destination precondition `verify` compares against. The first live run had
        # neither, and six accumulated Books read as `g_shared/Book: 6 != 1` — a migration
        # defect that was not one.


#: ⚠️ **Every assertion below scopes to the fixture's OWN rows, and the full-suite run is why.**
#: `migrate()` reads the ENTIRE source graph — that is its job — and the throwaway Neo4j is
#: shared with the rest of `tests/integration/db`, which had left **981 entities and 343
#: RELATES_TO** in it. Run alone the file was 9/9; run with its neighbours the totals were
#: someone else's. A migration test that assumes it owns the source is testing an empty
#: machine, and production is never one.


async def _one(pool, project_key, cypher, column="n"):
    async with age_repo_session(pool, project_key) as session:
        result = await session.run(cypher)
        rows = await result.data()
        return rows[0][column] if rows else None


async def test_the_migration_lands_WHOLE_and_verify_agrees(neo4j_driver, age_pool, seeded):
    """The headline: plan, apply, then COUNT the destination rather than trust the writer."""
    async with neo4j_driver.session() as session:
        plan = await migrate(session, age_pool, apply=True)
        problems = await verify(session, age_pool, plan)
    assert problems == [], f"the migrated graph does not match the plan: {problems}"
    assert plan.total_nodes >= 6 and plan.total_rels >= 2

    assert await _one(
        age_pool, None,
        f"MATCH (n:Entity) WHERE n.project_id IN ['{seeded['p1']}', '{seeded['p2']}'] RETURN count(n) AS n",
    ) == 3, (
        "all three entities land in ONE graph — the default layout is the topology "
        "the SERVICE reads, and Neo4j holds every project in one database too"
    )
    assert await _one(
        age_pool, None,
        f"MATCH ()-[r:RELATES_TO]->() WHERE r.user_id = 'u1' AND "
        f"r.subject_id = '{seeded['p1']}-e1' RETURN count(r) AS n",
    ) == 2


async def test_created_at_arrives_as_an_INTEGER_the_way_AGE_writes_it(
    neo4j_driver, age_pool, seeded
):
    """The claim the whole module turns on, checked on the destination rather than in Python.

    `cypher_dialect` renders `{NOW}` as `timestamp()` on AGE — an epoch-millis INTEGER — so a
    row this migration writes has to be comparable with every row the service writes after it.
    An ISO string here would order against those integers, and `graph_repos/entities.py:264`
    is a live reader of that ordering.
    """
    async with neo4j_driver.session() as session:
        await migrate(session, age_pool, apply=True)
    value = await _one(
        age_pool, None,
        f"MATCH (n:Entity) WHERE n.id = '{seeded['p1']}-e1' RETURN n.created_at AS n",
    )
    assert isinstance(value, int), f"created_at came back as {type(value).__name__}: {value!r}"
    assert value > 1_700_000_000_000, "epoch MILLIS, not seconds — a 1000x error still sorts"

    in_world = await _one(
        age_pool, None,
        f"MATCH (n:Event) WHERE n.id = '{seeded['p1']}-v1' RETURN n.event_date_iso AS n",
    )
    assert in_world == "1247-03-02", (
        "the in-world date is a STRING by design; converting it would rewrite a bi-temporal "
        "value with nothing downstream reporting an error"
    )


async def test_the_embedding_is_ABSENT_and_the_alias_list_SURVIVED(
    neo4j_driver, age_pool, seeded
):
    """Both halves, because either alone passes for the wrong reason: a migration that dropped
    every list would satisfy the first assertion and lose 13 227 values on the real graph."""
    async with neo4j_driver.session() as session:
        await migrate(session, age_pool, apply=True)
    assert await _one(
        age_pool, None,
        f"MATCH (n:Entity) WHERE n.id = '{seeded['p1']}-e1' "
        f"RETURN n.embedding_1024 IS NULL AS n",
    ) is True
    assert await _one(
        age_pool, None,
        f"MATCH (n:Entity) WHERE n.id = '{seeded['p1']}-e1' RETURN n.aliases AS n"
    ) == ["Kai", "K"]


async def test_running_it_TWICE_does_not_duplicate_a_single_row(
    neo4j_driver, age_pool, seeded
):
    """Idempotency is the property that makes a migration re-runnable after a partial failure,
    and `MERGE` only delivers it if the key is the natural one. Keyed on an internal element id
    the second run would double everything — which is why `LABEL_KEYS` refuses a label it does
    not know rather than falling back."""
    async with neo4j_driver.session() as session:
        await migrate(session, age_pool, apply=True)
        first = await _one(
            age_pool, None,
            f"MATCH (n) WHERE n.project_id = '{seeded['p1']}' RETURN count(n) AS n",
        )
        plan = await migrate(session, age_pool, apply=True)
        second = await _one(
            age_pool, None,
            f"MATCH (n) WHERE n.project_id = '{seeded['p1']}' RETURN count(n) AS n",
        )
        problems = await verify(session, age_pool, plan)
    assert second == first, f"a re-run changed the node count {first} -> {second}"
    assert problems == []
    assert await _one(
        age_pool, None,
        f"MATCH ()-[r:RELATES_TO]->() WHERE r.subject_id = '{seeded['p1']}-e1' "
        f"RETURN count(r) AS n",
    ) == 2, "the relationship MERGE is not idempotent"


async def test_the_UNSCOPED_hierarchy_lands_in_the_shared_graph_with_its_edge(
    neo4j_driver, age_pool, seeded
):
    """24 structural nodes and 33 HAS_CHILD edges on dev carry no `project_id`. They have to go
    somewhere, the edge has to survive the trip, and both endpoints must land in the SAME graph
    or AGE cannot hold the relationship at all."""
    async with neo4j_driver.session() as session:
        await migrate(session, age_pool, apply=True)
    assert graph_name_for(None) == "g_shared"
    assert await _one(
        age_pool, None,
        "MATCH (:Book)-[r:HAS_CHILD]->(:Part) RETURN count(r) AS n",
    ) >= 1


async def test_a_DRY_RUN_writes_nothing(neo4j_driver, age_pool, seeded):
    """The control arm for every test above. Without it they would all pass just as well
    against a module that ignored `apply` and always wrote."""
    probe = f"t54e-dry-{uuid.uuid4()}"
    async with neo4j_driver.session() as session:
        await session.run(
            "CREATE (:Entity {id: $i, project_id: $p, user_id: 'u', name: 'Ghost', "
            "canonical_name: 'ghost', kind: 'character', created_at: datetime(), "
            "updated_at: datetime()})",
            i=f"{probe}-e", p=probe,
        )
        try:
            plan = await migrate(session, age_pool, apply=False)
            assert None in plan.graphs, "the dry run did not even PLAN the row"
            # Absence of the GRAPH, not a zero row count. The first version asked AGE to
            # count inside a graph that had never been created and got
            # `InvalidSchemaNameError` — the right answer arriving as an error. Asserting
            # the catalog says it plainly, and it is the stronger claim: a dry run that
            # created an empty graph would still have written DDL.
            assert not await _graph_exists(age_pool, None), (
                "a dry run created the destination graph"
            )
        finally:
            await session.run("MATCH (n {project_id: $p}) DETACH DELETE n", p=probe)


async def test_TWO_relationships_between_the_SAME_pair_both_survive(
    neo4j_driver, age_pool, seeded
):
    """The regression the real data found, and node counts cannot see it.

    The first writer merged on `(a)-[:TYPE]->(b)`, so a second RELATES_TO between the same two
    entities collapsed into the first. Running against iso's extraction output returned
    `MISSING …/RELATES_TO: destination 11, source 12`; measured across both graphs, RELATES_TO
    is the ONLY type with parallel edges (183 pairs on dev, worst 10) and the ONLY type carrying
    an `id` — so the id is the merge key. On dev the old key would have dropped at least 183
    relationships with every node count intact.
    """
    async with neo4j_driver.session() as session:
        await migrate(session, age_pool, apply=True)
    predicates = []
    async with age_repo_session(age_pool, None) as session:
        result = await session.run(
            f"MATCH ()-[r:RELATES_TO]->() WHERE r.subject_id = '{seeded['p1']}-e1' "
            f"RETURN r.predicate AS n ORDER BY r.predicate"
        )
        predicates = [row["n"] for row in await result.data()]
    assert predicates == ["knows", "rivals"], (
        f"both edges must survive with their own properties; got {predicates}"
    )


async def test_the_migrated_graph_is_readable_through_the_SERVICE_SESSION(
    neo4j_driver, age_pool, seeded
):
    """🔴 The check that would have caught T54f, and none of the tests above can.

    Every assertion in this file names a graph. The migration's first cut named 433 of them —
    one per project, because iso's AGE store visibly held 120 populated `p-…` graphs — and
    those graphs belong to **T43's shadow harness**, not to the service. The service opens
    exactly one:

        app/db/neo4j.py:184                  age_repo_session(age_pool())          -> g_shared
        adapters/graph_store_provider.py:98  AgeGraphStore(pool, graph_name_for(None))

    So a migration into per-project graphs lands where the service cannot see it — the same
    empty store T54d found, produced by the fix for it, and every count above would still have
    been green because they were counting the graphs the migration had just written.

    This test asks the question from the other end: open the session the SERVICE would open,
    with no project argument at all, and see whether the data is there.
    """
    async with neo4j_driver.session() as session:
        await migrate(session, age_pool, apply=True)
    async with age_repo_session(age_pool) as service_session:   # no project — as db/neo4j.py
        result = await service_session.run(
            f"MATCH (n:Entity) WHERE n.project_id IN "
            f"['{seeded['p1']}', '{seeded['p2']}'] RETURN count(n) AS n"
        )
        rows = await result.data()
    assert rows and rows[0]["n"] == 3, (
        "the service's own session sees {} entities — the migration wrote somewhere it does "
        "not read".format(rows[0]["n"] if rows else 0)
    )


async def test_the_PER_PROJECT_layout_is_still_available_for_the_HARNESS(
    neo4j_driver, age_pool, seeded
):
    """The control on the default, and the reason the other layout was not simply deleted.

    T43's shadow harness and both backend benchmarks construct `AgeGraphStore(pool, gname)` per
    project deliberately — that topology is real, it is just not the service's. Keeping it
    opt-in means the refusals it needs (cross-graph edges, adoption) stay reachable and tested
    rather than becoming dead code guarded by nothing.
    """
    async with neo4j_driver.session() as session:
        plan = await migrate(session, age_pool, apply=True, layout=PER_PROJECT_LAYOUT)
        problems = await verify(session, age_pool, plan)
    assert problems == []
    assert seeded["p1"] in plan.graphs and seeded["p2"] in plan.graphs
    assert await _one(age_pool, seeded["p1"], "MATCH (n:Entity) RETURN count(n) AS n") == 2
    assert await _one(age_pool, seeded["p2"], "MATCH (n:Entity) RETURN count(n) AS n") == 1
    assert await _one(
        age_pool, None,
        f"MATCH (n:Entity) WHERE n.project_id IN "
        f"['{seeded['p1']}', '{seeded['p2']}'] RETURN count(n) AS n",
    ) == 0, "under the harness layout nothing scoped belongs in the shared graph"
    assert graph_name_for(None) == SHARED_GRAPH
