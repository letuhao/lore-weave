"""T83 — real `neo4j_repos` functions, unchanged, executed against Apache AGE.

§10.1 says two things bind the repo layer to Neo4j: **"the Cypher dialect and the session
type"**. T77–T82 took the dialect ratchet to zero, which is a reading, not a proof — every repo
function still went through `session.run(...)`, and nothing but a Bolt session had ever answered
that call. This file is the proof, and it is a FLOOR: the count may rise, never fall.

⚠️ **Running it is what found three separate reasons "dialect 0" was not portability.**

1. **51 hardcoded engine literals.** Every call site said `render(TEMPLATE, "neo4j")`. The
   dialect scan counts Neo4j-only *constructs*, and a string literal naming the engine is not
   one — so the ratchet read zero while the layer named one engine 51 times. The first run
   failed on `function datetime does not exist`. Rendering moved into
   `run_read`/`run_read_any_owner`/`run_write`, keyed on `engine_of(session)`.
2. **Seven call sites bypass those helpers** and lost their render with the other 51. Four unit
   suites and 620 integration tests were green at that moment; only a query reaching a real
   database could tell. Now derived by AST in `test_every_bypass_site_renders.py`.
3. **Two queries were valid Cypher on Neo4j and rejected by AGE** — both written days earlier
   in this same migration:
       `RETURN DISTINCT e … ORDER BY`   -> *for SELECT DISTINCT, ORDER BY expressions must
                                           appear in select list*   (now `WITH DISTINCT e`)
       `ORDER BY rel.confidence`        -> *could not find rte for rel* — AGE cannot order by
                                           an alias the RETURN defines (now ordered on `r`)

None of the three is visible to a test that mocks the session, and none is visible to a ratchet
that counts constructs. Only executing the function against the other engine finds them.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

#: Shrink-only. Every function below has been observed to run against a live AGE graph and
#: return a domain object the repo layer's own model accepts.
_PROVEN_ON_AGE = 12

_GRAPH = "repo_conformance"


@pytest_asyncio.fixture
async def age_session():
    """An `AgeCypherSession` over a throwaway graph, dropped afterwards either way."""
    dsn = os.environ.get("TEST_AGE_DSN")
    if not dsn:
        pytest.skip("TEST_AGE_DSN not set — skipping the AGE half of the repo layer")
    asyncpg = pytest.importorskip("asyncpg")

    from app.db.age_session import AgeCypherSession

    conn = await asyncpg.connect(dsn)
    try:
        await AgeCypherSession.prepare(conn)
        if await conn.fetchval("SELECT count(*) FROM ag_graph WHERE name = $1", _GRAPH):
            await conn.execute(f"SELECT drop_graph('{_GRAPH}', true)")
        await conn.execute(f"SELECT create_graph('{_GRAPH}')")
        yield AgeCypherSession(conn, _GRAPH)
        await conn.execute(f"SELECT drop_graph('{_GRAPH}', true)")
    finally:
        await conn.close()


async def test_the_repo_layer_runs_against_AGE_unchanged(age_session):
    """Twelve calls, no engine branch anywhere in them.

    Each assertion is on the DOMAIN OBJECT, not on "it did not raise": a query that runs and
    returns the wrong shape is the failure mode this whole migration keeps finding, and
    `AgeVertex` exists precisely because AGE's envelope would otherwise hand every caller the
    internal graph id under the name `id`.
    """
    from app.db.neo4j_repos import entities as en
    from app.db.neo4j_repos import provenance as pv
    from app.db.neo4j_repos import relations as rl

    ran = 0
    uid = f"u-{uuid.uuid4().hex[:8]}"
    proj = f"p-{uuid.uuid4().hex[:8]}"
    s = age_session

    kai = await en.merge_entity(s, user_id=uid, project_id=proj, name="Kai", kind="person",
                                source_type="chapter", confidence=0.9)
    ran += 1
    assert kai.name == "Kai" and kai.user_id == uid, (
        f"the domain object came back wrong: {kai!r}. An AGE vertex is "
        f"`{{id, label, properties}}` and its `id` is the INTERNAL graph id — reading the "
        f"envelope instead of `properties` yields a well-formed Entity with the wrong id."
    )

    again = await en.merge_entity(s, user_id=uid, project_id=proj, name="Kai", kind="person",
                                  source_type="chapter", confidence=0.9)
    ran += 1
    assert again.id == kai.id, "the merge is not idempotent on AGE — it minted a second node"

    fetched = await en.get_entity(s, user_id=uid, canonical_id=kai.id)
    ran += 1
    assert fetched is not None and fetched.id == kai.id

    by_name = await en.find_entities_by_name(s, user_id=uid, project_id=proj, name="Kai")
    ran += 1
    assert [e.id for e in by_name] == [kai.id], (
        f"name resolution returned {[e.id for e in by_name]} — this is the query whose "
        f"`RETURN DISTINCT … ORDER BY` AGE rejects outright"
    )

    detail = await en.get_entity_with_relations(s, user_id=uid, entity_id=kai.id)
    ran += 1
    assert detail is not None and detail.entity.id == kai.id and detail.relations == []

    rin = await en.merge_entity(s, user_id=uid, project_id=proj, name="Rin", kind="person",
                                source_type="chapter")
    ran += 1

    rel = await rl.create_relation(s, user_id=uid, subject_id=kai.id, predicate="knows",
                                   object_id=rin.id, confidence=0.8)
    ran += 1
    assert rel is not None and rel.subject_id == kai.id and rel.object_id == rin.id

    hops = await rl.find_relations_for_entity(s, user_id=uid, entity_id=kai.id,
                                              direction="both")
    ran += 1
    assert [r.id for r in hops] == [rel.id], (
        f"1-hop returned {[r.id for r in hops]} — this is the query whose `ORDER BY rel.…` "
        f"AGE cannot resolve, because `rel` is defined by the RETURN it is ordering"
    )

    src = await pv.upsert_extraction_source(s, user_id=uid, project_id=proj,
                                            source_type="chapter", source_id="ch-1")
    ran += 1
    assert src.source_id == "ch-1"

    counts = await pv.add_evidence(s, user_id=uid, target_label="Entity", target_id=kai.id,
                                   source_id=src.id, job_id="job-1", extraction_model="m",
                                   confidence=0.9)
    ran += 1
    assert counts.evidence_count == 1

    cites = await pv.list_evidence_for_target(s, user_id=uid, target_label="Entity",
                                              target_id=kai.id)
    ran += 1
    assert [c.source_id for c in cites] == [src.id]

    archived = await en.archive_entity(s, user_id=uid, canonical_id=kai.id,
                                       reason="user_deleted")
    ran += 1
    assert archived is not None and archived.archived_at is not None

    assert ran >= _PROVEN_ON_AGE, (
        f"only {ran} repo functions were exercised against AGE; the floor is {_PROVEN_ON_AGE}. "
        f"This number is shrink-only — a function that stops being proven is a regression in "
        f"the claim, not a smaller test."
    )


async def test_a_session_that_forgets_to_declare_its_engine_is_caught_here(age_session):
    """⚠️ The first run of `AgeCypherSession` omitted `engine = "age"`, `engine_of` fell back to
    Neo4j, and EVERY query failed at the database with `function datetime does not exist`.

    The fallback is right for a Bolt session and silently wrong for anything else, so the
    declaration is asserted rather than trusted — it is one deleted line from turning this whole
    file into a Neo4j test wearing an AGE fixture.
    """
    from app.db.neo4j_helpers import engine_of

    assert engine_of(age_session) == "age", (
        "the AGE session does not declare its engine, so every template renders as Neo4j "
        "Cypher and this file proves nothing about AGE"
    )
