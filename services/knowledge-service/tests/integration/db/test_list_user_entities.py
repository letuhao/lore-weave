"""K19c.4 integration tests — list_user_entities against live Neo4j."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.entities import (
    ENTITIES_MAX_LIMIT,
    archive_entity,
    list_user_entities,
    merge_entity,
)


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (e:Entity {user_id: $user_id}) DETACH DELETE e",
                user_id=user_id,
            )


@pytest.mark.asyncio
async def test_list_user_entities_returns_global_scope_only(neo4j_driver, test_user):
    """Global-scope listing excludes project-scoped entities."""
    async with neo4j_driver.session() as session:
        await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Coffee drinker", kind="preference",
            source_type="chat_turn", confidence=0.9,
        )
        await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Vietnamese writer", kind="preference",
            source_type="chat_turn", confidence=0.85,
        )
        # Project-scoped — should NOT appear in global listing.
        await merge_entity(
            session, user_id=test_user, project_id="p-1",
            name="Master Kai", kind="character",
            source_type="book_content", confidence=0.8,
        )

        rows = await list_user_entities(session, user_id=test_user, scope="global")

    names = {e.name for e in rows}
    assert "Coffee drinker" in names
    assert "Vietnamese writer" in names
    assert "Master Kai" not in names
    assert len(rows) == 2
    # ordered newest-first; both were just created so any order is fine,
    # but all entries must have project_id=None per the scope filter.
    for e in rows:
        assert e.project_id is None


@pytest.mark.asyncio
async def test_list_user_entities_excludes_archived(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        ent = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Short sentences", kind="preference",
            source_type="chat_turn", confidence=0.9,
        )
        # Keep around (not archived) so list has something to return.
        await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Long paragraphs", kind="preference",
            source_type="chat_turn", confidence=0.9,
        )

        await archive_entity(
            session, user_id=test_user,
            canonical_id=ent.id, reason="user_archived",
        )

        rows = await list_user_entities(session, user_id=test_user, scope="global")

    names = {e.name for e in rows}
    assert "Short sentences" not in names
    assert "Long paragraphs" in names


@pytest.mark.asyncio
async def test_list_user_entities_user_isolation(neo4j_driver):
    """User A's global entities must not appear in User B's listing."""
    user_a = f"u-test-{uuid.uuid4().hex[:12]}"
    user_b = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        async with neo4j_driver.session() as session:
            await merge_entity(
                session, user_id=user_a, project_id=None,
                name="A's preference", kind="preference",
                source_type="chat_turn", confidence=0.9,
            )
            await merge_entity(
                session, user_id=user_b, project_id=None,
                name="B's preference", kind="preference",
                source_type="chat_turn", confidence=0.9,
            )

            a_rows = await list_user_entities(session, user_id=user_a, scope="global")
            b_rows = await list_user_entities(session, user_id=user_b, scope="global")

        a_names = {e.name for e in a_rows}
        b_names = {e.name for e in b_rows}
        assert a_names == {"A's preference"}
        assert b_names == {"B's preference"}
    finally:
        async with neo4j_driver.session() as session:
            for uid in (user_a, user_b):
                await session.run(
                    "MATCH (e:Entity {user_id: $user_id}) DETACH DELETE e",
                    user_id=uid,
                )


@pytest.mark.asyncio
async def test_list_user_entities_limit_clamped(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        for i in range(3):
            await merge_entity(
                session, user_id=test_user, project_id=None,
                name=f"Preference {i}", kind="preference",
                source_type="chat_turn", confidence=0.9,
            )

        # limit=0 clamps up to 1.
        rows_one = await list_user_entities(
            session, user_id=test_user, scope="global", limit=0,
        )
        assert len(rows_one) == 1

        # Huge limit clamps to ENTITIES_MAX_LIMIT (still only 3 rows exist).
        rows_many = await list_user_entities(
            session, user_id=test_user, scope="global",
            limit=ENTITIES_MAX_LIMIT * 10,
        )
        assert len(rows_many) == 3


@pytest.mark.asyncio
async def test_list_user_entities_rejects_unsupported_scope(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        with pytest.raises(ValueError):
            await list_user_entities(session, user_id=test_user, scope="project")


@pytest.mark.asyncio
async def test_archive_entity_is_idempotent_for_user_archived_reason(
    neo4j_driver, test_user,
):
    """K19c.4 review-impl L6: contract lock — `_ARCHIVE_CYPHER` has no
    `archived_at IS NULL` guard, so repeated `archive_entity` calls on
    the same row return the node every time (never None). This lets the
    DELETE endpoint be idempotent per RFC 9110. If someone later adds
    the guard, this test catches the breakage."""
    async with neo4j_driver.session() as session:
        ent = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Idempotent target", kind="preference",
            source_type="chat_turn", confidence=0.9,
        )

        first = await archive_entity(
            session, user_id=test_user,
            canonical_id=ent.id, reason="user_archived",
        )
        assert first is not None
        assert first.archived_at is not None

        second = await archive_entity(
            session, user_id=test_user,
            canonical_id=ent.id, reason="user_archived",
        )
        # Second call still matches + rewrites archived_at; returns
        # the row. Router translates this to another 204.
        assert second is not None
        # Archived_at bumps to a fresh datetime on each call.
        assert second.archived_at is not None
