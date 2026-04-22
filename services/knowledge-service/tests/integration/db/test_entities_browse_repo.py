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
    MergeEntitiesError,
    archive_entity,
    get_entity,
    get_entity_with_relations,
    list_entities_filtered,
    merge_entities,
    merge_entity,
    update_entity_fields,
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


# ── K19d γ-a — update_entity_fields + user_edited lock ──────────────


@pytest.mark.asyncio
async def test_update_entity_fields_sets_user_edited_and_renames(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        ent = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Kai", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        # Baseline: user_edited defaults to false on CREATE.
        baseline = await get_entity(session, user_id=test_user, canonical_id=ent.id)
        assert baseline is not None
        assert baseline.user_edited is False

        updated = await update_entity_fields(
            session,
            user_id=test_user,
            entity_id=ent.id,
            name="Kai the Brave",
            kind=None,
            aliases=["Kai the Brave", "Sir Kai"],
        )
    assert updated is not None
    assert updated.name == "Kai the Brave"
    assert updated.canonical_name == "kai the brave"
    assert updated.kind == "character"  # unchanged
    assert set(updated.aliases) == {"Kai the Brave", "Sir Kai"}
    assert updated.user_edited is True


@pytest.mark.asyncio
async def test_update_entity_fields_cross_user_returns_none(
    neo4j_driver, test_user
):
    other_user = f"u-other-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        other_ent = await merge_entity(
            session, user_id=other_user, project_id=None,
            name="Stranger", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        result = await update_entity_fields(
            session,
            user_id=test_user,
            entity_id=other_ent.id,
            name="Hijacked",
            kind=None,
            aliases=None,
        )
    assert result is None
    # Confirm other user's entity is untouched.
    async with neo4j_driver.session() as session:
        still_there = await get_entity(
            session, user_id=other_user, canonical_id=other_ent.id,
        )
    assert still_there is not None
    assert still_there.name == "Stranger"
    assert still_there.user_edited is False
    # Cleanup
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (e:Entity {user_id: $uid}) DETACH DELETE e",
            uid=other_user,
        )


@pytest.mark.asyncio
async def test_merge_entity_respects_user_edited_aliases_lock(
    neo4j_driver, test_user
):
    """The core contract of K19d γ-a: after the user edits aliases
    via PATCH, future `merge_entity` calls with new name variants
    must NOT re-append those variants — the user's list stays
    authoritative until they unlock (future cycle: explicit unset)."""
    async with neo4j_driver.session() as session:
        ent = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Kai", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        # Bare ent already has alias ['Kai']. Add a variant the
        # extractor discovered naturally first.
        _ = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Master Kai", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        pre_edit = await get_entity(
            session, user_id=test_user, canonical_id=ent.id,
        )
        assert pre_edit is not None
        assert "Master Kai" in pre_edit.aliases

        # User edits aliases — removes "Master Kai" and pins just
        # "Kai" + "K.".
        await update_entity_fields(
            session,
            user_id=test_user,
            entity_id=ent.id,
            name=None,
            kind=None,
            aliases=["Kai", "K."],
        )
        post_edit = await get_entity(
            session, user_id=test_user, canonical_id=ent.id,
        )
        assert post_edit is not None
        assert post_edit.user_edited is True
        assert set(post_edit.aliases) == {"Kai", "K."}

        # Extractor re-runs with the "Master Kai" variant. Before
        # γ-a the merge_entity ON MATCH branch would have appended
        # "Master Kai" back. After γ-a the `user_edited=true` gate
        # short-circuits the CASE and aliases stay at [Kai, K.].
        await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Master Kai", kind="character",
            source_type="chat_turn", confidence=0.95,
        )
        post_reextract = await get_entity(
            session, user_id=test_user, canonical_id=ent.id,
        )
    assert post_reextract is not None
    # Aliases DID NOT re-add "Master Kai".
    assert "Master Kai" not in post_reextract.aliases
    assert set(post_reextract.aliases) == {"Kai", "K."}
    # But confidence bump still applied — non-alias updates aren't
    # gated on user_edited (the user's authority is over display
    # fields, not scoring signals).
    assert post_reextract.confidence >= 0.95


@pytest.mark.asyncio
async def test_merge_entity_without_user_edited_still_appends_aliases(
    neo4j_driver, test_user
):
    """Regression guard: pre-γ-a behaviour is preserved for
    un-edited nodes. Without this the coalesce fallback could
    silently break existing extraction flows.

    Uses "Master Phoenix" as a re-extraction variant because
    canonicalize_entity_name strips "master " — the two display
    names hash to the SAME canonical_id and hit `merge_entity`'s
    ON MATCH branch. "The Phoenix" would NOT work here because
    "the" isn't in the honorific strip list → different id →
    different node → alias append never runs.
    """
    async with neo4j_driver.session() as session:
        ent = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Phoenix", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        assert ent.user_edited is False
        await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Master Phoenix", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        after = await get_entity(
            session, user_id=test_user, canonical_id=ent.id,
        )
    assert after is not None
    assert after.user_edited is False
    # Alias append ran because user_edited was false.
    assert "Master Phoenix" in after.aliases


# ── K19d γ-b — merge_entities integration ───────────────────────────


@pytest.mark.asyncio
async def test_merge_entities_rewires_outgoing_relation(
    neo4j_driver, test_user
):
    """source → other gets rewired to target → other, with
    source's relation_id replaced by the new target-pinned id."""
    async with neo4j_driver.session() as session:
        kai = await merge_entity(
            session, user_id=test_user, project_id="p",
            name="Kai", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        # Different name hitting different canonical_id so target
        # is a separate entity we merge INTO.
        captain = await merge_entity(
            session, user_id=test_user, project_id="p",
            name="Captain Brave", kind="character",
            source_type="chat_turn", confidence=0.85,
        )
        other = await merge_entity(
            session, user_id=test_user, project_id="p",
            name="Phoenix", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        # Kai -[mentors]-> Phoenix (to be rewired to Captain).
        await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            object_id=other.id,
            predicate="mentors",
            confidence=0.8,
        )
        target = await merge_entities(
            session,
            user_id=test_user,
            source_id=kai.id,
            target_id=captain.id,
        )
    assert target.id == captain.id
    assert target.user_edited is True
    # Post-merge fetch to inspect the rewired relation.
    async with neo4j_driver.session() as session:
        detail = await get_entity_with_relations(
            session, user_id=test_user, entity_id=captain.id,
        )
        # Source (Kai) is gone.
        kai_after = await get_entity(
            session, user_id=test_user, canonical_id=kai.id,
        )
    assert kai_after is None
    assert detail is not None
    assert detail.total_relations == 1
    assert detail.relations[0].predicate == "mentors"
    assert detail.relations[0].subject_id == captain.id
    assert detail.relations[0].object_id == other.id


@pytest.mark.asyncio
async def test_merge_entities_unions_aliases_and_source_types(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        a = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Alice", kind="character",
            source_type="chat_turn", confidence=0.5,
        )
        # Extractor adds a variant so `a` has two aliases.
        _ = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Master Alice", kind="character",
            source_type="chapter", confidence=0.7,
        )
        b = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Captain Brave", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        target = await merge_entities(
            session,
            user_id=test_user,
            source_id=a.id,
            target_id=b.id,
        )
    # Union of aliases preserved, deduped.
    assert set(target.aliases) >= {"Captain Brave", "Alice", "Master Alice"}
    assert len(target.aliases) == len(set(target.aliases))
    # Source types from both entities.
    assert set(target.source_types) >= {"chat_turn", "chapter"}
    # Max confidence (source had 0.7, target had 0.9).
    assert target.confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_merge_entities_sums_counters(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        a = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Alpha", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        b = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Captain Brave", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        # Hand-set mention_count + evidence_count on both entities
        # to verify the sum.
        await session.run(
            "MATCH (e:Entity) WHERE e.user_id = $u AND e.id IN [$a, $b] "
            "SET e.mention_count = 10, e.evidence_count = 4",
            u=test_user, a=a.id, b=b.id,
        )
        target = await merge_entities(
            session,
            user_id=test_user,
            source_id=a.id,
            target_id=b.id,
        )
    assert target.mention_count == 20
    assert target.evidence_count == 8


@pytest.mark.asyncio
async def test_merge_entities_same_id_raises(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        a = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Solo", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        with pytest.raises(MergeEntitiesError) as excinfo:
            await merge_entities(
                session,
                user_id=test_user,
                source_id=a.id,
                target_id=a.id,
            )
    assert excinfo.value.error_code == "same_entity"


@pytest.mark.asyncio
async def test_merge_entities_cross_user_raises_not_found(
    neo4j_driver, test_user
):
    other_user = f"u-other-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        a = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Mine", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        b = await merge_entity(
            session, user_id=other_user, project_id=None,
            name="Theirs", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        with pytest.raises(MergeEntitiesError) as excinfo:
            await merge_entities(
                session,
                user_id=test_user,
                source_id=a.id,
                target_id=b.id,
            )
    assert excinfo.value.error_code == "entity_not_found"
    # Cleanup
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (e:Entity {user_id: $uid}) DETACH DELETE e",
            uid=other_user,
        )


@pytest.mark.asyncio
async def test_merge_entities_archived_source_raises(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        a = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Old", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        b = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Captain New", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        await archive_entity(
            session, user_id=test_user, canonical_id=a.id,
            reason="user_archived",
        )
        with pytest.raises(MergeEntitiesError) as excinfo:
            await merge_entities(
                session,
                user_id=test_user,
                source_id=a.id,
                target_id=b.id,
            )
    assert excinfo.value.error_code == "entity_archived"


@pytest.mark.asyncio
async def test_merge_entities_glossary_conflict_raises(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        a = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Anchored A", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        b = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Captain Anchored B", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        # Hand-set distinct glossary_entity_id values.
        await session.run(
            "MATCH (e:Entity {id: $aid, user_id: $u}) "
            "SET e.glossary_entity_id = 'gloss-A'",
            aid=a.id, u=test_user,
        )
        await session.run(
            "MATCH (e:Entity {id: $bid, user_id: $u}) "
            "SET e.glossary_entity_id = 'gloss-B'",
            bid=b.id, u=test_user,
        )
        with pytest.raises(MergeEntitiesError) as excinfo:
            await merge_entities(
                session,
                user_id=test_user,
                source_id=a.id,
                target_id=b.id,
            )
    assert excinfo.value.error_code == "glossary_conflict"


@pytest.mark.asyncio
async def test_merge_entities_drops_source_self_relation(
    neo4j_driver, test_user
):
    """Review-impl H1 regression: source has a self-relation (rare
    but the extractor can produce one). Previous logic would rewire
    it to `(target)-[...]->(source)`, then DETACH DELETE source
    would destroy the fresh edge — silent data loss. The fix skips
    self-relations entirely during rewire so nothing is created to
    be destroyed, and target ends up without a ghost edge."""
    async with neo4j_driver.session() as session:
        a = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Clone", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        b = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Captain Twin", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        # Hand-craft a self-relation on source.
        await session.run(
            """
            MATCH (s:Entity {id: $sid, user_id: $u})
            MERGE (s)-[r:RELATES_TO {id: 'self-rel-x'}]->(s)
            ON CREATE SET r.user_id = $u, r.subject_id = $sid,
                r.object_id = $sid, r.predicate = 'thinks-about',
                r.confidence = 0.5, r.created_at = datetime(),
                r.updated_at = datetime(), r.valid_until = NULL,
                r.pending_validation = false
            """,
            sid=a.id, u=test_user,
        )

        target = await merge_entities(
            session,
            user_id=test_user,
            source_id=a.id,
            target_id=b.id,
        )
        # Target has NO self-relation — the source's self-relation
        # was dropped, not re-homed onto target with a dangling
        # object pointer.
        self_rel_result = await session.run(
            """
            MATCH (t:Entity {id: $tid, user_id: $u})-[r:RELATES_TO]->(t)
            RETURN count(r) AS n
            """,
            tid=target.id, u=test_user,
        )
        self_rel_row = await self_rel_result.single()
    assert self_rel_row is not None
    assert self_rel_row["n"] == 0


@pytest.mark.asyncio
async def test_merge_entities_inherits_glossary_anchor_when_target_lacks(
    neo4j_driver, test_user
):
    """Source anchored, target un-anchored → target inherits."""
    async with neo4j_driver.session() as session:
        anchored = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Mentor Kai", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        unanchored = await merge_entity(
            session, user_id=test_user, project_id=None,
            name="Captain Phoenix", kind="character",
            source_type="chat_turn", confidence=0.9,
        )
        await session.run(
            "MATCH (e:Entity {id: $aid, user_id: $u}) "
            "SET e.glossary_entity_id = 'gloss-kai'",
            aid=anchored.id, u=test_user,
        )
        target = await merge_entities(
            session,
            user_id=test_user,
            source_id=anchored.id,
            target_id=unanchored.id,
        )
    assert target.glossary_entity_id == "gloss-kai"
