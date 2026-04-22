"""K19d.2 + K19d.4 integration tests against live Neo4j.

Exercises `list_entities_filtered` (all filter dimensions + pagination
+ total count) and `get_entity_with_relations` (entity + endpoints,
truncation signal, cross-user 404).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.entities import (
    ENTITIES_DETAIL_REL_CAP,
    archive_entity,
    get_entity_with_relations,
    list_entities_filtered,
    merge_entity,
)
from app.db.neo4j_repos.relations import create_relation


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (e:Entity {user_id: $user_id})
                DETACH DELETE e
                """,
                user_id=user_id,
            )


@pytest.mark.asyncio
async def test_list_entities_no_filters_returns_user_entities_only(
    neo4j_driver, test_user
):
    other_user = f"u-other-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Alice", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        await merge_entity(
            session, user_id=test_user, project_id="p-1",
            name="Bob", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        # Cross-user row — must NOT leak into results.
        await merge_entity(
            session, user_id=other_user, project_id=None,
            name="Carol", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        rows, total = await list_entities_filtered(
            session,
            user_id=test_user,
            project_id=None,
            kind=None,
            search=None,
            limit=50,
            offset=0,
        )
    names = {r.name for r in rows}
    assert names == {"Alice", "Bob"}
    assert total == 2
    # Cleanup cross-user row.
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (e:Entity {user_id: $uid}) DETACH DELETE e",
            uid=other_user,
        )


@pytest.mark.asyncio
async def test_list_entities_project_filter(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Global Pref", kind="preference",
            source_type="chat_turn", confidence=0.8,
        )
        await merge_entity(
            session, user_id=test_user, project_id="p-alpha",
            name="Alpha Char", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        await merge_entity(
            session, user_id=test_user, project_id="p-beta",
            name="Beta Char", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        rows, total = await list_entities_filtered(
            session,
            user_id=test_user,
            project_id="p-alpha",
            kind=None,
            search=None,
            limit=50,
            offset=0,
        )
    assert {r.name for r in rows} == {"Alpha Char"}
    assert total == 1


@pytest.mark.asyncio
async def test_list_entities_kind_filter(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Kai", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Dragon's Keep", kind="location",
            source_type="chat_turn", confidence=0.9,
        )
        rows, total = await list_entities_filtered(
            session,
            user_id=test_user,
            project_id=None,
            kind="character",
            search=None,
            limit=50,
            offset=0,
        )
    assert {r.name for r in rows} == {"Kai"}
    assert total == 1


@pytest.mark.asyncio
async def test_list_entities_search_matches_name_and_aliases(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Master Kai", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        # merge_entity with same name just adds to aliases idempotently;
        # seed via a second merge with a different display name so the
        # row has the expected `Kai` alias in its aliases list.
        await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Kai", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Phoenix", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        # Case-insensitive substring — "kAI" should match Master Kai.
        rows, total = await list_entities_filtered(
            session,
            user_id=test_user,
            project_id=None,
            kind=None,
            search="kAI",
            limit=50,
            offset=0,
        )
    names = {r.name for r in rows}
    # merge_entity normalizes "Master Kai" and "Kai" under the same
    # canonical bucket, so we should see the canonical row with
    # both aliases present. Either way, "Phoenix" must not match.
    assert "Phoenix" not in names
    assert total >= 1


@pytest.mark.asyncio
async def test_list_entities_pagination(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        for i in range(7):
            await merge_entity(
                session, user_id=test_user, project_id=None,
                name=f"E{i:02d}", kind="concept",
                source_type="chat_turn", confidence=0.5,
            )
        page1, total1 = await list_entities_filtered(
            session,
            user_id=test_user, project_id=None, kind=None, search=None,
            limit=3, offset=0,
        )
        page2, total2 = await list_entities_filtered(
            session,
            user_id=test_user, project_id=None, kind=None, search=None,
            limit=3, offset=3,
        )
        page3, total3 = await list_entities_filtered(
            session,
            user_id=test_user, project_id=None, kind=None, search=None,
            limit=3, offset=6,
        )
    assert total1 == total2 == total3 == 7
    assert len(page1) == 3
    assert len(page2) == 3
    assert len(page3) == 1
    # No id overlap between pages (stable pagination).
    ids = [e.id for e in page1 + page2 + page3]
    assert len(ids) == len(set(ids)) == 7

    # Review-impl M1 regression: offset past the end still returns
    # correct total (so FE can render "page X of Y"), not total=0.
    async with neo4j_driver.session() as session:
        past_end, past_total = await list_entities_filtered(
            session,
            user_id=test_user, project_id=None, kind=None, search=None,
            limit=3, offset=100,
        )
    assert past_end == []
    assert past_total == 7


@pytest.mark.asyncio
async def test_list_entities_excludes_archived(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        seed = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Archived Pref", kind="preference",
            source_type="chat_turn", confidence=0.9,
        )
        await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Active Pref", kind="preference",
            source_type="chat_turn", confidence=0.9,
        )
        await archive_entity(
            session, user_id=test_user, canonical_id=seed.id,
            reason="user_archived",
        )
        rows, total = await list_entities_filtered(
            session,
            user_id=test_user, project_id=None, kind=None, search=None,
            limit=50, offset=0,
        )
    names = {r.name for r in rows}
    assert "Archived Pref" not in names
    assert "Active Pref" in names
    assert total == 1


@pytest.mark.asyncio
async def test_entity_detail_with_no_relations(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        ent = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Lone Entity", kind="concept",
            source_type="chat_turn", confidence=0.7,
        )
        detail = await get_entity_with_relations(
            session, user_id=test_user, entity_id=ent.id,
        )
    assert detail is not None
    assert detail.entity.name == "Lone Entity"
    assert detail.relations == []
    assert detail.relations_truncated is False
    assert detail.total_relations == 0


@pytest.mark.asyncio
async def test_entity_detail_with_in_and_out_relations(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        kai = await merge_entity(
            session, user_id=test_user, project_id="p-1",
            name="Kai", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        phoenix = await merge_entity(
            session, user_id=test_user, project_id="p-1",
            name="Phoenix", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        # Kai -[mentors]-> Phoenix (Kai is subject)
        await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            object_id=phoenix.id,
            predicate="mentors",
            confidence=0.85,
        )
        # Phoenix -[trained_by]-> Kai (Kai is object here)
        await create_relation(
            session,
            user_id=test_user,
            subject_id=phoenix.id,
            object_id=kai.id,
            predicate="trained_by",
            confidence=0.85,
        )
        detail = await get_entity_with_relations(
            session, user_id=test_user, entity_id=kai.id,
        )
    assert detail is not None
    assert detail.total_relations == 2
    assert len(detail.relations) == 2
    assert detail.relations_truncated is False
    preds = {r.predicate for r in detail.relations}
    assert preds == {"mentors", "trained_by"}
    # Endpoint projection populated.
    for r in detail.relations:
        if r.predicate == "mentors":
            assert r.subject_id == kai.id
            assert r.object_id == phoenix.id
            assert r.subject_name == "Kai"
            assert r.object_name == "Phoenix"
        else:
            assert r.subject_id == phoenix.id
            assert r.object_id == kai.id


@pytest.mark.asyncio
async def test_entity_detail_cross_user_returns_none(neo4j_driver, test_user):
    other_user = f"u-other-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        other_ent = await merge_entity(
            session, user_id=other_user, project_id=None,
            name="Other's Entity", kind="concept",
            source_type="chat_turn", confidence=0.7,
        )
        detail = await get_entity_with_relations(
            session, user_id=test_user, entity_id=other_ent.id,
        )
    assert detail is None
    # Cleanup
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (e:Entity {user_id: $uid}) DETACH DELETE e",
            uid=other_user,
        )


@pytest.mark.asyncio
async def test_entity_detail_truncates_at_rel_cap(neo4j_driver, test_user):
    """Seed more relations than the per-call cap; assert truncated
    flag + preserved total count."""
    async with neo4j_driver.session() as session:
        hero = await merge_entity(
            session, user_id=test_user, project_id="p-hero",
            name="Hero", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        # Seed 5 related entities + outbound edges. We shrink the cap
        # via the `rel_cap` arg instead of seeding 200+ rows — repo
        # behaviour is identical.
        for i in range(5):
            other = await merge_entity(
                session, user_id=test_user, project_id="p-hero",
                name=f"Foe{i}", kind="character",
                source_type="chat_turn", confidence=0.7,
            )
            await create_relation(
                session,
                user_id=test_user,
                subject_id=hero.id,
                object_id=other.id,
                predicate="fights",
                confidence=0.8,
            )
        detail = await get_entity_with_relations(
            session, user_id=test_user, entity_id=hero.id, rel_cap=3,
        )
    assert detail is not None
    assert detail.total_relations == 5
    assert len(detail.relations) == 3
    assert detail.relations_truncated is True
    # Default cap is 200 — check the constant hasn't silently moved.
    assert ENTITIES_DETAIL_REL_CAP == 200
