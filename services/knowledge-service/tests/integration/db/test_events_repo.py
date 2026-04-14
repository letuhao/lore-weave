"""K11.7 events repository — integration tests against live Neo4j.

Skipped when TEST_NEO4J_URI is unset. Each test scopes to a unique
user_id and DETACH DELETEs in finally.

Acceptance:
  - Merge is idempotent
  - Temporal queries work (event_user_order range scan)
  - Chapter cascade lookup uses event_user_chapter
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.events import (
    delete_events_with_zero_evidence,
    event_id,
    get_event,
    list_events_for_chapter,
    list_events_in_order,
    merge_event,
)


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (e:Event {user_id: $user_id}) DETACH DELETE e",
                user_id=user_id,
            )


# ── event_id ──────────────────────────────────────────────────────────


def test_k11_7_event_id_deterministic():
    a = event_id("u-1", "p-1", "ch-12", "Kai duels Zhao")
    b = event_id("u-1", "p-1", "ch-12", "Kai duels Zhao")
    assert a == b
    assert len(a) == 32


def test_k11_7_event_id_canonicalizes_title():
    a = event_id("u-1", "p-1", "ch-12", "Kai duels Zhao")
    b = event_id("u-1", "p-1", "ch-12", "  KAI Duels Zhao!  ")
    assert a == b


def test_k11_7_event_id_distinct_per_chapter():
    a = event_id("u-1", "p-1", "ch-12", "Kai duels Zhao")
    b = event_id("u-1", "p-1", "ch-13", "Kai duels Zhao")
    assert a != b


def test_k11_7_event_id_rejects_empty_title():
    with pytest.raises(ValueError, match="title"):
        event_id("u-1", "p-1", "ch-12", "")


def test_k11_7_event_id_rejects_punctuation_only_title():
    with pytest.raises(ValueError, match="canonicalizes to empty"):
        event_id("u-1", "p-1", "ch-12", "!!!")


# ── merge_event ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_merge_event_creates_node(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        ev = await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Kai duels Zhao",
            summary="The duel at the bridge",
            chapter_id="ch-12",
            event_order=42,
            chronological_order=10,
            participants=["entity-kai", "entity-zhao"],
            confidence=0.9,
        )
    assert ev.user_id == test_user
    assert ev.title == "Kai duels Zhao"
    assert ev.canonical_title == "kai duels zhao"
    assert ev.chapter_id == "ch-12"
    assert ev.event_order == 42
    assert ev.chronological_order == 10
    assert set(ev.participants) == {"entity-kai", "entity-zhao"}
    assert ev.confidence == 0.9
    assert ev.evidence_count == 0


@pytest.mark.asyncio
async def test_k11_7_merge_event_is_idempotent(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        a = await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Kai duels Zhao",
            chapter_id="ch-12",
            event_order=42,
            confidence=0.5,
        )
        b = await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="kai DUELS zhao",  # cosmetic spelling diff
            chapter_id="ch-12",
            event_order=42,
            confidence=0.5,
        )
    assert a.id == b.id
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (e:Event {id: $id}) RETURN count(e) AS n", id=a.id
        )
        record = await result.single()
    assert record["n"] == 1


@pytest.mark.asyncio
async def test_k11_7_merge_event_unions_participants_dedups(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Battle",
            chapter_id="ch-1",
            participants=["a", "b"],
        )
        result = await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Battle",
            chapter_id="ch-1",
            participants=["b", "c"],
        )
    assert set(result.participants) == {"a", "b", "c"}


@pytest.mark.asyncio
async def test_k11_7_merge_event_takes_max_confidence(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Battle",
            chapter_id="ch-1",
            confidence=0.4,
        )
        promoted = await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Battle",
            chapter_id="ch-1",
            confidence=0.9,
        )
        downgrade = await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Battle",
            chapter_id="ch-1",
            confidence=0.2,
        )
    assert promoted.confidence == 0.9
    assert downgrade.confidence == 0.9


@pytest.mark.asyncio
async def test_k11_7_merge_event_summary_first_write_wins(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Battle",
            chapter_id="ch-1",
            summary="The original summary",
        )
        # Re-merge without a summary — existing one preserved.
        result = await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Battle",
            chapter_id="ch-1",
            summary=None,
        )
    assert result.summary == "The original summary"


# ── get_event ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_get_event_returns_none_when_missing(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        result = await get_event(session, user_id=test_user, event_id="0" * 32)
    assert result is None


@pytest.mark.asyncio
async def test_k11_7_get_event_does_not_cross_user_boundary(neo4j_driver):
    user_a = f"u-test-{uuid.uuid4().hex[:12]}"
    user_b = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        async with neo4j_driver.session() as session:
            ev = await merge_event(
                session,
                user_id=user_a,
                project_id="p-1",
                title="Secret",
                chapter_id="ch-1",
            )
            from_b = await get_event(
                session, user_id=user_b, event_id=ev.id
            )
        assert from_b is None
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (e:Event) WHERE e.user_id IN [$ua, $ub] DETACH DELETE e",
                ua=user_a,
                ub=user_b,
            )


# ── list_events_for_chapter ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_list_events_for_chapter(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="First",
            chapter_id="ch-1",
            event_order=1,
        )
        await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Second",
            chapter_id="ch-1",
            event_order=2,
        )
        # Different chapter — must NOT appear in ch-1 list.
        await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="OtherChapter",
            chapter_id="ch-2",
            event_order=10,
        )
        events = await list_events_for_chapter(
            session, user_id=test_user, chapter_id="ch-1"
        )
    assert [e.title for e in events] == ["First", "Second"]


@pytest.mark.asyncio
async def test_k11_7_list_events_for_chapter_validates_input():
    with pytest.raises(ValueError, match="chapter_id"):
        await list_events_for_chapter(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            chapter_id="",
        )


# ── list_events_in_order ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_list_events_in_order_full_timeline(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        for i, title in enumerate(["A", "B", "C", "D"]):
            await merge_event(
                session,
                user_id=test_user,
                project_id="p-1",
                title=title,
                chapter_id="ch-1",
                event_order=i,
            )
        events = await list_events_in_order(
            session, user_id=test_user, project_id="p-1"
        )
    assert [e.title for e in events] == ["A", "B", "C", "D"]


@pytest.mark.asyncio
async def test_k11_7_list_events_in_order_bounded_range(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        for i, title in enumerate(["A", "B", "C", "D", "E"]):
            await merge_event(
                session,
                user_id=test_user,
                project_id="p-1",
                title=title,
                chapter_id="ch-1",
                event_order=i,
            )
        bounded = await list_events_in_order(
            session,
            user_id=test_user,
            project_id="p-1",
            after_order=0,  # > 0 → starts at index 1 (B)
            before_order=4,  # < 4 → stops at index 3 (D)
        )
    assert [e.title for e in bounded] == ["B", "C", "D"]


@pytest.mark.asyncio
async def test_k11_7_list_events_in_order_validates_range():
    with pytest.raises(ValueError, match="must be < before_order"):
        await list_events_in_order(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            project_id="p-1",
            after_order=5,
            before_order=3,
        )


@pytest.mark.asyncio
async def test_k11_7_list_events_in_order_project_id_filter(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="P1Event",
            chapter_id="ch-1",
            event_order=1,
        )
        await merge_event(
            session,
            user_id=test_user,
            project_id="p-2",
            title="P2Event",
            chapter_id="ch-1",
            event_order=2,
        )
        scoped = await list_events_in_order(
            session, user_id=test_user, project_id="p-1"
        )
    assert [e.title for e in scoped] == ["P1Event"]


# ── delete_events_with_zero_evidence ──────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_delete_events_zero_evidence(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        a = await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="A",
            chapter_id="ch-1",
        )
        b = await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="B",
            chapter_id="ch-1",
        )
        survivor = await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Survivor",
            chapter_id="ch-1",
        )
        await session.run(
            "MATCH (e:Event {id: $id}) SET e.evidence_count = 1",
            id=survivor.id,
        )
        deleted = await delete_events_with_zero_evidence(
            session, user_id=test_user, project_id="p-1"
        )
    assert deleted == 2
    async with neo4j_driver.session() as session:
        gone_a = await get_event(session, user_id=test_user, event_id=a.id)
        gone_b = await get_event(session, user_id=test_user, event_id=b.id)
        kept = await get_event(
            session, user_id=test_user, event_id=survivor.id
        )
    assert gone_a is None
    assert gone_b is None
    assert kept is not None
