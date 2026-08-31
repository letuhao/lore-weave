"""T78 — the `existed` legs of the two merged MERGE queries, on a live Neo4j.

§10.1 merged every `ON CREATE SET` / `ON MATCH SET` pair into one unconditional `SET`, because
AGE has neither keyword. Most fields fold into `coalesce`. The ones that cannot are gated on an
`existed` flag read before the MERGE — and three of those legs had NO coverage: bites 4, 5 and 6
each rewrote one into its wrong form and the whole suite stayed green.

All three fail the same way, which is the way every hole this run has found fails: a **silent
absence**. Nothing errors, every row is well-formed, and the damage is a fact that quietly
stopped being true — a job credited with work it did not do, a relation an author closed that is
open again, an edge quarantined by Pass 1 that reads as validated.

    bite 4   e.created_job_id = coalesce(e.created_job_id, $job_id)   -> attribution back-fills
    bite 5   r.valid_until drops its `NOT existed` leg                -> a closed edge reopens
    bite 6   r.pending_validation drops its `existed` guard           -> quarantine is dropped

Measured on the dev graph the same day: 4413 of 4926 :Entity nodes have a null `created_job_id`,
so bite 4 is not a corner — it is 90% of the graph, one extraction away.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n {user_id: $user_id}) DETACH DELETE n", user_id=user_id,
            )


# ── bite 4: net-new attribution ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_later_job_does_not_STEAL_credit_for_creating_the_entity(
    neo4j_driver, test_user,
):
    """`created_job_id` is the T4.1 flywheel's net-new signal: which job first minted a node.

    `coalesce` reads as the safe idiom and is the exact bug here. The 4413 nodes with a null
    `created_job_id` are null on purpose — pre-T4.1 nodes and non-job writes — so a coalesce
    hands each of them to whichever job happens to touch it next, and that job's "entities
    created" number silently counts work someone else did.
    """
    from app.db.graph_repos.entities import merge_entity

    proj = f"p-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        # Created by NO job at all — the shape 4413 dev nodes are in.
        first = await merge_entity(
            session, user_id=test_user, project_id=proj, name="Kai",
            kind="person", source_type="chapter", job_id=None,
        )
        await merge_entity(
            session, user_id=test_user, project_id=proj, name="Kai",
            kind="person", source_type="chapter", job_id="job-LATER",
        )
        row = await (await session.run(
            "MATCH (e:Entity {id: $id, user_id: $u}) RETURN e.created_job_id AS j",
            id=first.id, u=test_user,
        )).single()
        assert row["j"] is None, (
            f"a later job claimed credit for creating this node (created_job_id={row['j']!r}). "
            f"It is set ONLY on create; a match must leave it exactly as it is, null included"
        )

        # ...and the create leg still records the job that DID mint the node.
        minted = await merge_entity(
            session, user_id=test_user, project_id=proj, name="Rin",
            kind="person", source_type="chapter", job_id="job-FIRST",
        )
        row = await (await session.run(
            "MATCH (e:Entity {id: $id, user_id: $u}) RETURN e.created_job_id AS j",
            id=minted.id, u=test_user,
        )).single()
        assert row["j"] == "job-FIRST", (
            "the create leg stopped recording the minting job — net-new attribution is now "
            "null for every node, which is the opposite failure and just as silent"
        )


# ── bites 5 and 6: what a rewired RELATES_TO carries across ────────────────────────────


async def _merge_and_read_rewired(session, *, user_id, project_id, **relkw):
    """Build loser -[knows]-> other, merge loser into winner, return the winner's new edge."""
    from app.db.graph_repos.entities import merge_entities, merge_entity
    from app.db.graph_repos.relations import create_relation

    tag = uuid.uuid4().hex[:6]
    loser = await merge_entity(session, user_id=user_id, project_id=project_id,
                               name=f"Kai{tag}", kind="person", source_type="chapter")
    winner = await merge_entity(session, user_id=user_id, project_id=project_id,
                                name=f"Kai Zhou{tag}", kind="person", source_type="chapter")
    other = await merge_entity(session, user_id=user_id, project_id=project_id,
                               name=f"Rin{tag}", kind="person", source_type="chapter")

    rel = await create_relation(session, user_id=user_id, subject_id=loser.id,
                                predicate="knows", object_id=other.id, **relkw)
    assert rel is not None, "fixture is wrong — the relation was not created"

    await merge_entities(session, user_id=user_id, source_id=loser.id, target_id=winner.id)

    row = await (await session.run(
        "MATCH (w:Entity {id: $w, user_id: $u})-[r:RELATES_TO]->(o:Entity {id: $o}) "
        "RETURN r.valid_until AS vu, r.pending_validation AS pv",
        w=winner.id, o=other.id, u=user_id,
    )).single()
    assert row is not None, "the relation was not rewired onto the winner at all"
    return row


@pytest.mark.asyncio
async def test_a_CLOSED_relation_stays_closed_when_it_is_rewired(neo4j_driver, test_user):
    """F5 resurrection, reached from the other side.

    T71 hit this by ASSIGNING `valid_until`; here it is reached by failing to. The match arm
    resolves "either side open -> open", which is right for two edges being combined and wrong
    for an edge being created: on a new edge `r.valid_until` is null, so the open rule fires and
    a relation the author closed comes back open on the winner.
    """
    from app.db.graph_repos.entities import merge_entities, merge_entity
    from app.db.graph_repos.relations import create_relation, invalidate_relation

    proj = f"p-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        tag = uuid.uuid4().hex[:6]
        loser = await merge_entity(session, user_id=test_user, project_id=proj,
                                   name=f"Kai{tag}", kind="person", source_type="chapter")
        winner = await merge_entity(session, user_id=test_user, project_id=proj,
                                    name=f"Kai Zhou{tag}", kind="person", source_type="chapter")
        other = await merge_entity(session, user_id=test_user, project_id=proj,
                                   name=f"Rin{tag}", kind="person", source_type="chapter")
        rel = await create_relation(session, user_id=test_user, subject_id=loser.id,
                                    predicate="knows", object_id=other.id, confidence=0.9)
        assert rel is not None
        await invalidate_relation(session, user_id=test_user, relation_id=rel.id)

        closed = await (await session.run(
            "MATCH ()-[r:RELATES_TO {id: $id}]->() RETURN r.valid_until AS vu", id=rel.id,
        )).single()
        assert closed["vu"] is not None, "fixture is wrong — the relation is not closed"

        await merge_entities(session, user_id=test_user,
                             source_id=loser.id, target_id=winner.id)
        row = await (await session.run(
            "MATCH (w:Entity {id: $w, user_id: $u})-[r:RELATES_TO]->(o:Entity {id: $o}) "
            "RETURN r.valid_until AS vu", w=winner.id, o=other.id, u=test_user,
        )).single()
        assert row is not None and row["vu"] is not None, (
            "merging the entity RE-OPENED a closed relation on the winner — every as-of read "
            "before the close now returns an edge the author had ended"
        )


@pytest.mark.asyncio
async def test_a_QUARANTINED_relation_stays_quarantined_when_it_is_rewired(
    neo4j_driver, test_user,
):
    """The AND-combine is a rule about two edges meeting; on a NEW edge there is nothing to
    combine with, and `null AND true` is false. So a Pass-1 quarantined edge would arrive on
    the winner already validated — visible to every reader that filters quarantine out, with
    no review having happened."""
    proj = f"p-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        row = await _merge_and_read_rewired(
            session, user_id=test_user, project_id=proj,
            confidence=0.4, pending_validation=True,
        )
        assert row["pv"] is True, (
            "a QUARANTINED relation was rewired as VALIDATED — Pass 1's quarantine is gone and "
            "the edge is now indistinguishable from a reviewed one"
        )


@pytest.mark.asyncio
async def test_a_VALIDATED_relation_is_still_rewired_as_validated(neo4j_driver, test_user):
    """The other direction, on a case the guard was NOT derived from: adding an `existed` leg
    must not turn every rewired edge into a quarantined one."""
    proj = f"p-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        row = await _merge_and_read_rewired(
            session, user_id=test_user, project_id=proj,
            confidence=0.9, pending_validation=False,
        )
        assert row["pv"] is False, (
            "a validated relation came out quarantined — the create leg is copying the wrong "
            "value, which would bury reviewed edges in the triage queue"
        )
