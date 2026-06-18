"""T2.1 Cast & Codex — live-Neo4j integration for the (:Fact)-[:ABOUT]->(:Entity)
edge, spoiler-windowed fact reads, status from_order projection, and the ABOUT
transfer on entity merge. Skipped when TEST_NEO4J_URI is unset.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.entities import merge_entity, merge_entities
from app.db.neo4j_repos.entity_status import (
    merge_entity_status,
    statuses_detail_at_order,
)
from app.db.neo4j_repos.facts import list_facts_for_entity, merge_fact


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n {user_id: $user_id}) "
                "WHERE n:Fact OR n:Entity OR n:EntityStatus DETACH DELETE n",
                user_id=user_id,
            )


async def _mk_entity(session, user_id, name):
    return await merge_entity(
        session, user_id=user_id, project_id="p-1", name=name,
        kind="character", source_type="book_content", confidence=0.9,
    )


# ── ABOUT edge + windowed per-entity facts ────────────────────────────


@pytest.mark.asyncio
async def test_fact_about_edge_and_window(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        kael = await _mk_entity(session, test_user, "Kael")
        # ch2 fact (from_order=2M) and ch5 fact (from_order=5M), both ABOUT Kael.
        await merge_fact(
            session, user_id=test_user, project_id="p-1", type="decision",
            content="broke the oath", confidence=0.9,
            subject_id=kael.id, from_order=2_000_000,
        )
        await merge_fact(
            session, user_id=test_user, project_id="p-1", type="milestone",
            content="became king", confidence=0.9,
            subject_id=kael.id, from_order=5_000_000,
        )
        # an unlinked universal claim (no subject) must NOT show under Kael.
        await merge_fact(
            session, user_id=test_user, project_id="p-1", type="preference",
            content="the empire was vast", confidence=0.9,
        )

        # window through ch3 (ceiling 3_999_999): only the ch2 fact passes.
        windowed = await list_facts_for_entity(
            session, user_id=test_user, entity_id=kael.id, before_order=3_999_999)
        assert [f.content for f in windowed] == ["broke the oath"]

        # window through ch5: both linked facts (ordered by from_order ASC).
        full = await list_facts_for_entity(
            session, user_id=test_user, entity_id=kael.id, before_order=5_999_999)
        assert [f.content for f in full] == ["broke the oath", "became king"]

        # no window → all linked facts; the universal claim is still excluded.
        unbounded = await list_facts_for_entity(
            session, user_id=test_user, entity_id=kael.id, before_order=None)
        assert {f.content for f in unbounded} == {"broke the oath", "became king"}


@pytest.mark.asyncio
async def test_fact_about_edge_idempotent(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        kael = await _mk_entity(session, test_user, "Kael")
        for _ in range(3):  # re-extraction stamps the same fact + ABOUT thrice
            await merge_fact(
                session, user_id=test_user, project_id="p-1", type="decision",
                content="broke the oath", confidence=0.9,
                subject_id=kael.id, from_order=2_000_000,
            )
        r = await session.run(
            "MATCH (f:Fact {user_id:$u})-[r:ABOUT]->(e:Entity {id:$eid}) "
            "RETURN count(r) AS edges, count(DISTINCT f) AS facts",
            u=test_user, eid=kael.id,
        )
        row = await r.single()
        assert row["edges"] == 1 and row["facts"] == 1  # one node, one edge


@pytest.mark.asyncio
async def test_fact_null_from_order_excluded_by_finite_window(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        kael = await _mk_entity(session, test_user, "Kael")
        await merge_fact(  # legacy / chat-tool fact: no from_order
            session, user_id=test_user, project_id="p-1", type="decision",
            content="legacy decision", confidence=0.9, subject_id=kael.id,
        )
        windowed = await list_facts_for_entity(
            session, user_id=test_user, entity_id=kael.id, before_order=9_000_000)
        assert windowed == []  # NULL from_order never passes a finite window
        unbounded = await list_facts_for_entity(
            session, user_id=test_user, entity_id=kael.id, before_order=None)
        assert [f.content for f in unbounded] == ["legacy decision"]


@pytest.mark.asyncio
async def test_fact_pending_excluded(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        kael = await _mk_entity(session, test_user, "Kael")
        await merge_fact(
            session, user_id=test_user, project_id="p-1", type="decision",
            content="quarantined", confidence=0.2, pending_validation=True,
            subject_id=kael.id, from_order=1_000_000,
        )
        out = await list_facts_for_entity(
            session, user_id=test_user, entity_id=kael.id, before_order=9_000_000)
        assert out == []  # low-confidence pending fact is not an "established" fact


# ── status from_order projection ──────────────────────────────────────


@pytest.mark.asyncio
async def test_statuses_detail_returns_from_order(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        s = await merge_entity_status(
            session, user_id=test_user, project_id="p-1", entity_id="e-1",
            status="gone", from_order=1_000_010)
        await session.run(
            "MATCH (s:EntityStatus {id:$id}) SET s.evidence_count = 1", id=s.id)
        detail = await statuses_detail_at_order(
            session, user_id=test_user, project_id="p-1",
            entity_ids=["e-1", "e-2"], at_order=2_000_000)
    assert detail["e-1"] == {"status": "gone", "from_order": 1_000_010}
    assert detail["e-2"] == {"status": "active", "from_order": None}  # default, no drop


# ── ABOUT transfers on entity merge (review-impl MED-3) ───────────────


@pytest.mark.asyncio
async def test_about_edge_transfers_on_merge(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        dupe = await _mk_entity(session, test_user, "Kael Duplicate")
        canonical = await _mk_entity(session, test_user, "Kael")
        await merge_fact(
            session, user_id=test_user, project_id="p-1", type="decision",
            content="broke the oath", confidence=0.9,
            subject_id=dupe.id, from_order=2_000_000,
        )
        # the fact is about the duplicate; before merge, canonical has none.
        assert await list_facts_for_entity(
            session, user_id=test_user, entity_id=canonical.id, before_order=None) == []

        await merge_entities(
            session, user_id=test_user, source_id=dupe.id, target_id=canonical.id)

        # after merge the fact follows to the canonical entity (no orphan).
        moved = await list_facts_for_entity(
            session, user_id=test_user, entity_id=canonical.id, before_order=None)
        assert [f.content for f in moved] == ["broke the oath"]
