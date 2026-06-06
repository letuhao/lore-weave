"""A2-S2 — fact-for-check read: live-Neo4j position windowing + isolation."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.entities import merge_entity
from app.db.neo4j_repos.entity_status import merge_entity_status
from app.db.neo4j_repos.events import merge_event
from app.db.neo4j_repos.fact_for_check import get_fact_for_check
from app.db.neo4j_repos.provenance import add_evidence, upsert_extraction_source
from app.db.neo4j_repos.relations import create_relation


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
    await create_relation(session, user_id=user_id, subject_id=kai.id,
                          predicate="loyal_to", object_id=bob.id, confidence=0.9)
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
            entity_ids=[], at_order=1_000)
    assert snap.entities == [] and snap.events == [] and snap.relations == []
