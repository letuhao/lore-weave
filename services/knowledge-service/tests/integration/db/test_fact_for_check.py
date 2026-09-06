"""A2-S2 — fact-for-check read: live-Neo4j position windowing + isolation."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.graph_repos.entities import merge_entity
from app.db.graph_repos.entity_status import merge_entity_status
from app.db.graph_repos.events import merge_event
from app.db.graph_repos.fact_for_check import get_fact_for_check
from app.db.graph_repos.provenance import add_evidence, upsert_extraction_source
from app.db.graph_repos.relations import create_relation


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.user_id = $u DETACH DELETE n", u=user_id,
            )


async def _seed(session, user_id, project_id):
    """Kai (dies at order 5_000_000), Bob. Events: 'Kai walks' @3M, 'Kai dies'
    @5M. Relation Kai loyal_to Bob. Status Kai gone from 5M (evidenced)."""
    kai = await merge_entity(session, user_id=user_id, project_id=project_id,
                             name="Kai", kind="character", source_type="book_content")
    bob = await merge_entity(session, user_id=user_id, project_id=project_id,
                             name="Bob", kind="character", source_type="book_content")
    src = await upsert_extraction_source(session, user_id=user_id, project_id=project_id,
                                         source_type="chapter", source_id="ch-1")
    await merge_event(session, user_id=user_id, project_id=project_id,
                      title="Kai walks", summary="Kai walks to town.",
                      event_order=3_000_000, participants=["Kai"],
                      source_type="chapter", confidence=0.9)
    await merge_event(session, user_id=user_id, project_id=project_id,
                      title="Kai dies", summary="Kai is slain.",
                      event_order=5_000_000, participants=["Kai"],
                      source_type="chapter", confidence=0.9)
    # T36 — the relation carries a STORY position, as every real write does
    # (`maintain_chain` stamps it). A positionless edge is excluded by the
    # as-of read on purpose; see test_relation_positionless_is_excluded.
    await create_relation(session, user_id=user_id, subject_id=kai.id,
                          predicate="loyal_to", object_id=bob.id, confidence=0.9,
                          valid_from_ordinal=1_000_000)
    st = await merge_entity_status(session, user_id=user_id, project_id=project_id,
                                   entity_id=kai.id, status="gone", from_order=5_000_000)
    await add_evidence(session, user_id=user_id, target_label="EntityStatus",
                       target_id=st.id, source_id=src.id, extraction_model="x",
                       confidence=0.9, job_id="j")
    return kai.id, bob.id


@pytest.mark.asyncio
async def test_fact_for_check_before_death(neo4j_driver, test_user):
    P = "p-1"
    async with neo4j_driver.session() as session:
        kai_id, bob_id = await _seed(session, test_user, P)
        snap = await get_fact_for_check(
            session, user_id=test_user, project_id=P,
            entity_ids=[kai_id, bob_id], at_order=4_999_999)

    assert snap.at_order == 4_999_999
    # status: before the death → Kai active, Bob active.
    by_id = {e.entity_id: e for e in snap.entities}
    assert by_id[kai_id].status == "active"
    assert by_id[bob_id].status == "active"
    assert by_id[kai_id].name == "Kai" and by_id[kai_id].kind == "character"
    # events ≤ P: only 'Kai walks' @3M (the death @5M is AFTER P).
    titles = {e.title for e in snap.events}
    assert titles == {"Kai walks"}
    # relation Kai loyal_to Bob present.
    assert any(r.subject_id == kai_id and r.predicate == "loyal_to"
               and r.object_id == bob_id for r in snap.relations)


@pytest.mark.asyncio
async def test_fact_for_check_after_death(neo4j_driver, test_user):
    P = "p-1"
    async with neo4j_driver.session() as session:
        kai_id, bob_id = await _seed(session, test_user, P)
        snap = await get_fact_for_check(
            session, user_id=test_user, project_id=P,
            entity_ids=[kai_id, bob_id], at_order=9_000_000)

    by_id = {e.entity_id: e for e in snap.entities}
    # after the death → Kai gone (the SCORE signal), Bob still active.
    assert by_id[kai_id].status == "gone"
    assert by_id[bob_id].status == "active"
    # events ≤ P now include both 'Kai walks' and 'Kai dies', newest first.
    titles = [e.title for e in snap.events]
    assert titles == ["Kai dies", "Kai walks"]


@pytest.mark.asyncio
async def test_fact_for_check_user_isolation(neo4j_driver, test_user):
    P = "p-1"
    async with neo4j_driver.session() as session:
        kai_id, bob_id = await _seed(session, test_user, P)
        other = f"u-other-{uuid.uuid4().hex[:8]}"
        snap = await get_fact_for_check(
            session, user_id=other, project_id=P,
            entity_ids=[kai_id, bob_id], at_order=9_000_000)

    # cross-user: the ids resolve to nothing; status defaults active; no events.
    assert snap.events == []
    assert snap.relations == []
    assert all(e.name is None for e in snap.entities)  # no metadata leaked
    assert all(e.status == "active" for e in snap.entities)  # no status leaked


@pytest.mark.asyncio
async def test_fact_for_check_empty_ids(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        snap = await get_fact_for_check(
            session, user_id=test_user, project_id="p-1",
            entity_ids=[], glossary_entity_ids=[], at_order=1_000)
    assert snap.entities == [] and snap.events == [] and snap.relations == []


@pytest.mark.asyncio
async def test_fact_for_check_resolves_glossary_cast_ids(neo4j_driver, test_user):
    """A2-S3 — composition passes GLOSSARY cast ids; fact-for-check resolves
    them to :Entity via the glossary_entity_id FK and returns status@P + the
    glossary_entity_id back for correlation."""
    P = "p-1"
    async with neo4j_driver.session() as session:
        kai = await merge_entity(session, user_id=test_user, project_id=P,
                                 name="Kai", kind="character", source_type="book_content")
        # stamp the glossary FK (set by glossary-sync in production).
        await session.run(
            "MATCH (e:Entity {id:$id}) SET e.glossary_entity_id = 'g-kai'", id=kai.id)
        src = await upsert_extraction_source(session, user_id=test_user, project_id=P,
                                             source_type="chapter", source_id="ch-1")
        st = await merge_entity_status(session, user_id=test_user, project_id=P,
                                       entity_id=kai.id, status="gone", from_order=5_000_000)
        await add_evidence(session, user_id=test_user, target_label="EntityStatus",
                           target_id=st.id, source_id=src.id, extraction_model="x",
                           confidence=0.9, job_id="j")
        # query by the GLOSSARY id (what composition holds), not the :Entity id.
        snap = await get_fact_for_check(
            session, user_id=test_user, project_id=P,
            glossary_entity_ids=["g-kai"], at_order=9_000_000)

    assert len(snap.entities) == 1
    e = snap.entities[0]
    assert e.entity_id == kai.id
    assert e.glossary_entity_id == "g-kai"  # correlated back to the cast id
    assert e.status == "gone"               # status@9M (after the death)


# ── T36 — a role is position-windowed (D-CANON-CHECK-BLIND-TO-ROLE) ──────────


async def _seed_role_change(session, user_id, project_id):
    """Kai serves Bob from ch.1, then serves Carol from ch.6 — `maintain_chain`
    closes the Bob arc at 6M. The canon check at ch.3 must see Bob and NOT
    Carol; at ch.9 it must see Carol and NOT Bob.

    This is the register's stated acceptance case in miniature: a trap laid by
    the antagonist of the moment is misattributed exactly when the check is
    handed a role that has already ended."""
    kai = await merge_entity(session, user_id=user_id, project_id=project_id,
                             name="Kai", kind="character", source_type="book_content")
    bob = await merge_entity(session, user_id=user_id, project_id=project_id,
                             name="Bob", kind="character", source_type="book_content")
    carol = await merge_entity(session, user_id=user_id, project_id=project_id,
                               name="Carol", kind="character", source_type="book_content")
    await create_relation(session, user_id=user_id, subject_id=kai.id,
                          predicate="serves", object_id=bob.id, confidence=0.9,
                          valid_from_ordinal=1_000_000, maintain_chain=True)
    await create_relation(session, user_id=user_id, subject_id=kai.id,
                          predicate="serves", object_id=carol.id, confidence=0.9,
                          valid_from_ordinal=6_000_000, maintain_chain=True)
    return kai.id, bob.id, carol.id


@pytest.mark.asyncio
async def test_role_that_ended_is_absent_after_it_ends(neo4j_driver, test_user):
    """THE defect. Before T36 the check was handed 'Kai serves Bob' at EVERY
    position, including long after the arc closed — `find_relations_for_entity`
    has taken `as_of_ordinal` since T18, but this call site never passed it."""
    P = "p-1"
    async with neo4j_driver.session() as session:
        kai, bob, carol = await _seed_role_change(session, test_user, P)
        late = await get_fact_for_check(
            session, user_id=test_user, project_id=P,
            entity_ids=[kai, bob, carol], at_order=9_000_000)

    objs = {(r.predicate, r.object_id) for r in late.relations}
    assert ("serves", carol) in objs, "the role in force at ch.9 must be present"
    assert ("serves", bob) not in objs, (
        "a role that ENDED at ch.6 must not read as live at ch.9 — "
        "this is D-CANON-CHECK-BLIND-TO-ROLE")


@pytest.mark.asyncio
async def test_role_not_yet_begun_is_absent_before_it_starts(neo4j_driver, test_user):
    """The mirror half, and the one a 'current relations' read gets wrong in the
    other direction: Carol's role begins at ch.6 and must be invisible at ch.3,
    or the check leaks the future into a spoiler-windowed read."""
    P = "p-1"
    async with neo4j_driver.session() as session:
        kai, bob, carol = await _seed_role_change(session, test_user, P)
        early = await get_fact_for_check(
            session, user_id=test_user, project_id=P,
            entity_ids=[kai, bob, carol], at_order=3_000_000)

    objs = {(r.predicate, r.object_id) for r in early.relations}
    assert ("serves", bob) in objs, "the role in force at ch.3 must be present"
    assert ("serves", carol) not in objs, (
        "a role that BEGINS at ch.6 must not be visible at ch.3 — that is a "
        "spoiler leak, the same axis error pointing forward")


@pytest.mark.asyncio
async def test_relation_carries_the_interval_that_answered(neo4j_driver, test_user):
    """The window must be legible in the payload, not just applied — a judge
    reading 'Kai serves Bob' needs to know it has held since ch.1."""
    P = "p-1"
    async with neo4j_driver.session() as session:
        kai, bob, carol = await _seed_role_change(session, test_user, P)
        early = await get_fact_for_check(
            session, user_id=test_user, project_id=P,
            entity_ids=[kai, bob, carol], at_order=3_000_000)

    rel = next(r for r in early.relations if r.object_id == bob)
    assert rel.valid_from_ordinal == 1_000_000
    assert rel.valid_to_ordinal == 6_000_000  # closed by the ch.6 supersession


@pytest.mark.asyncio
async def test_relation_positionless_is_excluded(neo4j_driver, test_user):
    """T18's rule, asserted at this call site: an edge that cannot be placed on
    the axis must not be mixed into an answer whose whole value is that it is
    placed. On the dev graph this is 286 of 905 edges, so it is not a corner."""
    P = "p-1"
    async with neo4j_driver.session() as session:
        kai = await merge_entity(session, user_id=test_user, project_id=P,
                                 name="Kai", kind="character", source_type="book_content")
        bob = await merge_entity(session, user_id=test_user, project_id=P,
                                 name="Bob", kind="character", source_type="book_content")
        # no valid_from_ordinal — legacy / positionless.
        await create_relation(session, user_id=test_user, subject_id=kai.id,
                              predicate="knows", object_id=bob.id, confidence=0.9)
        snap = await get_fact_for_check(
            session, user_id=test_user, project_id=P,
            entity_ids=[kai.id, bob.id], at_order=3_000_000)

    assert snap.relations == []
