"""K11.5a integration tests — entities repository against live Neo4j.

Skipped when `TEST_NEO4J_URI` is unset. Each test creates entities
under a unique `user_id` and cleans up via DETACH DELETE in a
fixture so concurrent test runs don't collide.

Acceptance criteria (from K11.5 plan):
  - merge_entity is idempotent (re-running creates no duplicates)
  - upsert_glossary_anchor sets anchor_score=1.0 and is idempotent
  - archive_entity preserves the node + relationships (no cascade)
  - find_entities_by_name uses canonical lookup + alias match
  - delete_entities_with_zero_evidence only deletes user's own nodes
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.canonical import entity_canonical_id
from app.db.neo4j_repos.entities import (
    archive_entity,
    delete_entities_with_zero_evidence,
    find_entities_by_name,
    get_entity,
    merge_entity,
    restore_entity,
    upsert_glossary_anchor,
)


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    """Yield a unique user_id for the test, then DETACH DELETE every
    Entity owned by that user so the test leaves zero rows behind."""
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (e:Entity {user_id: $user_id}) DETACH DELETE e",
                user_id=user_id,
            )


# ── merge_entity ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_5a_merge_entity_creates_node(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        entity = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Master Kai",
            kind="character",
            source_type="book_content",
            confidence=0.8,
        )
    assert entity.user_id == test_user
    assert entity.project_id == "p-1"
    assert entity.name == "Master Kai"  # display preserved
    assert entity.canonical_name == "kai"
    assert entity.kind == "character"
    assert entity.confidence == 0.8
    assert entity.aliases == ["Master Kai"]
    assert entity.source_types == ["book_content"]
    assert entity.glossary_entity_id is None
    assert entity.anchor_score == 0.0
    assert entity.archived_at is None
    assert entity.evidence_count == 0
    assert entity.id == entity_canonical_id(
        user_id=test_user, project_id="p-1", name="Master Kai", kind="character"
    )


@pytest.mark.asyncio
async def test_k11_5a_merge_entity_is_idempotent(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        a = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
            confidence=0.6,
        )
        b = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
            confidence=0.6,
        )
    assert a.id == b.id
    # Verify only one node exists for this id.
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (e:Entity {id: $id}) RETURN count(e) AS n",
            id=a.id,
        )
        record = await result.single()
    assert record["n"] == 1


@pytest.mark.asyncio
async def test_k11_5a_merge_entity_canonicalizes_honorifics(neo4j_driver, test_user):
    """Merging "Master Kai" then "kai" then "KAI" should hit the
    SAME node — three distinct display spellings, one canonical id."""
    async with neo4j_driver.session() as session:
        a = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Master Kai",
            kind="character",
            source_type="book_content",
        )
        b = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="kai",
            kind="character",
            source_type="chat",
        )
        c = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="KAI",
            kind="character",
            source_type="manual",
        )
    assert a.id == b.id == c.id
    # The third merge sees all three aliases accumulated.
    assert set(c.aliases) == {"Master Kai", "kai", "KAI"}
    assert set(c.source_types) == {"book_content", "chat", "manual"}


@pytest.mark.asyncio
async def test_k11_5a_merge_entity_takes_max_confidence(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="pattern",
            confidence=0.3,
        )
        result = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="llm",
            confidence=0.9,
        )
    assert result.confidence == 0.9
    # Lower confidence on a third merge does NOT lower the value.
    async with neo4j_driver.session() as session:
        result = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="pattern2",
            confidence=0.1,
        )
    assert result.confidence == 0.9


# ── upsert_glossary_anchor ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_5a_upsert_glossary_anchor_creates_anchored_entity(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        entity = await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-kai-1",
            name="Kai",
            kind="character",
            aliases=["Kai", "Master Kai", "Flame Kai"],
        )
    assert entity.glossary_entity_id == "gloss-kai-1"
    assert entity.anchor_score == 1.0
    assert entity.confidence == 1.0
    assert entity.archived_at is None
    assert entity.source_types == ["glossary"]
    assert "Kai" in entity.aliases
    assert "Master Kai" in entity.aliases
    assert "Flame Kai" in entity.aliases


@pytest.mark.asyncio
async def test_k11_5a_upsert_glossary_anchor_is_idempotent(neo4j_driver, test_user):
    """Two calls to upsert_glossary_anchor with the same args
    yield the same id and overwrite (not append) the canonical
    fields. Glossary is the SSOT for name/kind/aliases."""
    async with neo4j_driver.session() as session:
        a = await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-1",
            name="Kai",
            kind="character",
            aliases=["Kai", "K"],
        )
        b = await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-1",
            name="Kai",
            kind="character",
            aliases=["Kai", "Kai-shifu"],  # aliases changed in glossary
        )
    assert a.id == b.id
    # Second upsert overwrote aliases with the new glossary list.
    assert set(b.aliases) == {"Kai", "Kai-shifu"}
    assert b.anchor_score == 1.0


@pytest.mark.asyncio
async def test_k11_5a_upsert_anchor_promotes_existing_discovered_entity(
    neo4j_driver, test_user
):
    """A discovered entity merged from extraction can be promoted
    to a glossary anchor by calling upsert_glossary_anchor with the
    same canonical_id. This is the K-G-P-1 promotion path."""
    async with neo4j_driver.session() as session:
        discovered = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
            confidence=0.7,
        )
        anchored = await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-promoted",
            name="Kai",
            kind="character",
            aliases=["Kai"],
        )
    assert discovered.id == anchored.id
    assert anchored.glossary_entity_id == "gloss-promoted"
    assert anchored.anchor_score == 1.0


# ── get_entity ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_5a_get_entity_returns_none_when_missing(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        result = await get_entity(
            session,
            user_id=test_user,
            canonical_id="0" * 32,
        )
    assert result is None


@pytest.mark.asyncio
async def test_k11_5a_get_entity_does_not_cross_user_boundary(neo4j_driver):
    """An entity owned by user A must NOT be visible to user B
    even if B somehow knows the canonical_id."""
    user_a = f"u-test-{uuid.uuid4().hex[:12]}"
    user_b = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        async with neo4j_driver.session() as session:
            a = await merge_entity(
                session,
                user_id=user_a,
                project_id="p-1",
                name="Kai",
                kind="character",
                source_type="book_content",
            )
            from_b_perspective = await get_entity(
                session,
                user_id=user_b,
                canonical_id=a.id,
            )
        assert from_b_perspective is None
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (e:Entity) WHERE e.user_id IN [$ua, $ub] DETACH DELETE e",
                ua=user_a,
                ub=user_b,
            )


# ── find_entities_by_name ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_5a_find_by_name_matches_canonical_form(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Master Kai",
            kind="character",
            source_type="book_content",
        )
        # Search by a different display spelling — canonical match still wins.
        results = await find_entities_by_name(
            session,
            user_id=test_user,
            project_id="p-1",
            name="kai",
        )
    assert len(results) == 1
    assert results[0].canonical_name == "kai"
    assert results[0].name == "Master Kai"


@pytest.mark.asyncio
async def test_k11_5a_find_by_name_matches_alias(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai the Flame",
            kind="character",
            source_type="book_content",
        )
        # Searching by the exact alias spelling hits the alias arm.
        results = await find_entities_by_name(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai the Flame",
        )
    assert len(results) == 1


@pytest.mark.asyncio
async def test_k11_5a_find_by_name_excludes_archived_by_default(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        e = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
        )
        await archive_entity(
            session,
            user_id=test_user,
            canonical_id=e.id,
            reason="user_archive",
        )
        active = await find_entities_by_name(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
        )
        all_including_archived = await find_entities_by_name(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            include_archived=True,
        )
    assert active == []
    assert len(all_including_archived) == 1
    assert all_including_archived[0].archived_at is not None


@pytest.mark.asyncio
async def test_k11_5a_find_by_name_ranks_anchored_above_discovered(
    neo4j_driver, test_user
):
    """Anchored entities (anchor_score=1.0) should sort before
    discovered ones (anchor_score<1.0) when both match a name."""
    async with neo4j_driver.session() as session:
        # Different kinds so they don't collapse to the same id.
        await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Phoenix",
            kind="character",
            source_type="book_content",
            confidence=0.5,
        )
        await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-phoenix",
            name="Phoenix",
            kind="creature",
        )
        results = await find_entities_by_name(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Phoenix",
        )
    assert len(results) == 2
    assert results[0].anchor_score == 1.0
    assert results[0].kind == "creature"
    assert results[1].anchor_score == 0.0
    assert results[1].kind == "character"


# ── archive / restore ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_5a_archive_sets_fields_and_clears_anchor(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        anchored = await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-kai-arch",
            name="Kai",
            kind="character",
        )
        archived = await archive_entity(
            session,
            user_id=test_user,
            canonical_id=anchored.id,
            reason="glossary_deleted",
        )
    assert archived is not None
    assert archived.archived_at is not None
    assert archived.anchor_score == 0.0
    assert archived.glossary_entity_id is None


@pytest.mark.asyncio
async def test_k11_5a_archive_preserves_node_and_relationships(neo4j_driver, test_user):
    """KSA §3.4.F invariant: archive must NEVER cascade-delete.
    The node still exists, RELATES_TO and EVIDENCED_BY edges remain
    traversable. Verified by checking the node count before/after."""
    async with neo4j_driver.session() as session:
        e = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
        )
        # Add a fake outgoing edge so we can verify it survives.
        await session.run(
            "MATCH (e:Entity {id: $id}) "
            "CREATE (e)-[:RELATES_TO {predicate: 'mentor_of'}]->"
            "(:Entity {id: 'fake-target', user_id: $user_id, "
            "name: 'Target', canonical_name: 'target', kind: 'character', "
            "aliases: ['Target'], canonical_version: 1, source_types: ['test'], "
            "confidence: 0.0, anchor_score: 0.0, evidence_count: 0})",
            id=e.id,
            user_id=test_user,
        )
        await archive_entity(
            session,
            user_id=test_user,
            canonical_id=e.id,
            reason="user_archive",
        )
        result = await session.run(
            "MATCH (e:Entity {id: $id})-[r:RELATES_TO]->(t) "
            "RETURN e, r, t",
            id=e.id,
        )
        record = await result.single()
    assert record is not None
    assert record["e"]["archived_at"] is not None
    assert record["r"]["predicate"] == "mentor_of"
    assert record["t"]["name"] == "Target"


@pytest.mark.asyncio
async def test_k11_5a_restore_clears_archive_fields(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        e = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
        )
        await archive_entity(
            session,
            user_id=test_user,
            canonical_id=e.id,
            reason="user_archive",
        )
        restored = await restore_entity(
            session,
            user_id=test_user,
            canonical_id=e.id,
        )
    assert restored is not None
    assert restored.archived_at is None
    # Per docstring: anchor_score is NOT recomputed by restore.
    assert restored.anchor_score == 0.0


@pytest.mark.asyncio
async def test_k11_5a_archive_returns_none_for_missing_entity(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        result = await archive_entity(
            session,
            user_id=test_user,
            canonical_id="0" * 32,
            reason="user_archive",
        )
    assert result is None


# ── delete_entities_with_zero_evidence ────────────────────────────────


@pytest.mark.asyncio
async def test_k11_5a_delete_zero_evidence_only_targets_zero_count(
    neo4j_driver, test_user
):
    """Three entities: two with evidence_count=0, one with 1.
    The cleanup deletes the two and leaves the one untouched."""
    async with neo4j_driver.session() as session:
        a = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="A",
            kind="character",
            source_type="book_content",
        )
        b = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="B",
            kind="character",
            source_type="book_content",
        )
        c = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="C",
            kind="character",
            source_type="book_content",
        )
        # Bump c's evidence_count to 1 so it survives.
        await session.run(
            "MATCH (e:Entity {id: $id}) SET e.evidence_count = 1",
            id=c.id,
        )
        deleted = await delete_entities_with_zero_evidence(
            session,
            user_id=test_user,
            project_id="p-1",
        )
    assert deleted == 2
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (e:Entity {user_id: $user_id}) RETURN count(e) AS n",
            user_id=test_user,
        )
        record = await result.single()
    assert record["n"] == 1
    # And the survivor is c.
    async with neo4j_driver.session() as session:
        survivor = await get_entity(session, user_id=test_user, canonical_id=c.id)
    assert survivor is not None
    assert survivor.name == "C"
    # Sanity: a and b are gone.
    async with neo4j_driver.session() as session:
        for missing_id in (a.id, b.id):
            gone = await get_entity(
                session, user_id=test_user, canonical_id=missing_id
            )
            assert gone is None


@pytest.mark.asyncio
async def test_k11_5a_delete_zero_evidence_does_not_cross_users(neo4j_driver):
    """Cleanup for user A must NEVER touch user B's entities."""
    user_a = f"u-test-{uuid.uuid4().hex[:12]}"
    user_b = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        async with neo4j_driver.session() as session:
            a_entity = await merge_entity(
                session,
                user_id=user_a,
                project_id="p-1",
                name="Kai",
                kind="character",
                source_type="book_content",
            )
            b_entity = await merge_entity(
                session,
                user_id=user_b,
                project_id="p-1",
                name="Kai",
                kind="character",
                source_type="book_content",
            )
            deleted = await delete_entities_with_zero_evidence(
                session,
                user_id=user_a,
            )
        assert deleted == 1
        async with neo4j_driver.session() as session:
            survivor = await get_entity(
                session, user_id=user_b, canonical_id=b_entity.id
            )
            ghost = await get_entity(
                session, user_id=user_a, canonical_id=a_entity.id
            )
        assert survivor is not None
        assert survivor.user_id == user_b
        assert ghost is None
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (e:Entity) WHERE e.user_id IN [$ua, $ub] DETACH DELETE e",
                ua=user_a,
                ub=user_b,
            )
