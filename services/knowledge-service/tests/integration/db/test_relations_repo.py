"""K11.6 integration tests — relations repository against live Neo4j.

Skipped when TEST_NEO4J_URI is unset. Each test scopes to a unique
user_id, builds a small entity graph via K11.5a's merge_entity,
and DETACH DELETEs in finally.

Acceptance (from K11.6 plan):
  - create_relation uses source_event_id for idempotency
  - 2-hop traversal works with fixture data
  - Temporal filter (valid_until IS NULL) applied
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.db.neo4j_repos.entities import (
    archive_entity,
    merge_entity,
    upsert_glossary_anchor,
)
from app.db.neo4j_repos.relations import (
    Relation,
    create_relation,
    find_relations_2hop,
    find_relations_for_entity,
    get_relation,
    invalidate_relation,
    relation_id,
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


async def _entity(session, *, user_id: str, name: str, kind: str = "character"):
    return await merge_entity(
        session,
        user_id=user_id,
        project_id="p-1",
        name=name,
        kind=kind,
        source_type="book_content",
        confidence=0.9,
    )


# ── relation_id ───────────────────────────────────────────────────────


def test_k11_6_relation_id_deterministic():
    a = relation_id("u-1", "subj-1", "loyal_to", "obj-1")
    b = relation_id("u-1", "subj-1", "loyal_to", "obj-1")
    assert a == b
    assert len(a) == 32


def test_k11_6_relation_id_distinct_per_predicate():
    a = relation_id("u-1", "subj-1", "loyal_to", "obj-1")
    b = relation_id("u-1", "subj-1", "enemy_of", "obj-1")
    assert a != b


def test_k11_6_relation_id_distinct_per_user():
    a = relation_id("u-1", "subj-1", "loyal_to", "obj-1")
    b = relation_id("u-2", "subj-1", "loyal_to", "obj-1")
    assert a != b


def test_k11_6_relation_id_rejects_empty_inputs():
    for kwargs in (
        dict(user_id="", subject_id="s", predicate="p", object_id="o"),
        dict(user_id="u", subject_id="", predicate="p", object_id="o"),
        dict(user_id="u", subject_id="s", predicate="", object_id="o"),
        dict(user_id="u", subject_id="s", predicate="p", object_id=""),
    ):
        with pytest.raises(ValueError):
            relation_id(**kwargs)


# ── create_relation ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_6_create_relation_creates_edge(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        phoenix = await _entity(session, user_id=test_user, name="Phoenix")
        rel = await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            predicate="loyal_to",
            object_id=phoenix.id,
            confidence=0.9,
            source_event_id="evt-1",
            source_chapter="ch-12",
        )
    assert rel is not None
    assert rel.user_id == test_user
    assert rel.subject_id == kai.id
    assert rel.object_id == phoenix.id
    assert rel.predicate == "loyal_to"
    assert rel.confidence == 0.9
    assert rel.source_event_ids == ["evt-1"]
    assert rel.source_chapter == "ch-12"
    assert rel.valid_until is None
    assert rel.pending_validation is False
    assert rel.subject_name == "Kai"
    assert rel.object_name == "Phoenix"
    assert rel.id == relation_id(
        user_id=test_user,
        subject_id=kai.id,
        predicate="loyal_to",
        object_id=phoenix.id,
    )


@pytest.mark.asyncio
async def test_k11_6_create_relation_is_idempotent_per_event(
    neo4j_driver, test_user
):
    """Re-running with the same source_event_id must NOT duplicate
    the event id in source_event_ids."""
    async with neo4j_driver.session() as session:
        a = await _entity(session, user_id=test_user, name="A")
        b = await _entity(session, user_id=test_user, name="B")
        await create_relation(
            session,
            user_id=test_user,
            subject_id=a.id,
            predicate="ally_of",
            object_id=b.id,
            confidence=0.9,
            source_event_id="evt-x",
        )
        rel = await create_relation(
            session,
            user_id=test_user,
            subject_id=a.id,
            predicate="ally_of",
            object_id=b.id,
            confidence=0.9,
            source_event_id="evt-x",  # same event
        )
    assert rel.source_event_ids == ["evt-x"]
    # Verify only one edge exists.
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (s:Entity {id:$s})-[r:RELATES_TO]->(o:Entity {id:$o}) "
            "RETURN count(r) AS n",
            s=a.id,
            o=b.id,
        )
        record = await result.single()
    assert record["n"] == 1


@pytest.mark.asyncio
async def test_k11_6_create_relation_accumulates_distinct_events(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        a = await _entity(session, user_id=test_user, name="A")
        b = await _entity(session, user_id=test_user, name="B")
        await create_relation(
            session,
            user_id=test_user,
            subject_id=a.id,
            predicate="ally_of",
            object_id=b.id,
            confidence=0.7,
            source_event_id="evt-1",
        )
        await create_relation(
            session,
            user_id=test_user,
            subject_id=a.id,
            predicate="ally_of",
            object_id=b.id,
            confidence=0.7,
            source_event_id="evt-2",
        )
        final = await create_relation(
            session,
            user_id=test_user,
            subject_id=a.id,
            predicate="ally_of",
            object_id=b.id,
            confidence=0.7,
            source_event_id="evt-3",
        )
    assert set(final.source_event_ids) == {"evt-1", "evt-2", "evt-3"}


@pytest.mark.asyncio
async def test_k11_6_create_relation_takes_max_confidence(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        a = await _entity(session, user_id=test_user, name="A")
        b = await _entity(session, user_id=test_user, name="B")
        # Pass 1 quarantined edge
        await create_relation(
            session,
            user_id=test_user,
            subject_id=a.id,
            predicate="ally_of",
            object_id=b.id,
            confidence=0.4,
            source_event_id="evt-1",
            pending_validation=True,
        )
        # Pass 2 LLM promotes
        promoted = await create_relation(
            session,
            user_id=test_user,
            subject_id=a.id,
            predicate="ally_of",
            object_id=b.id,
            confidence=0.95,
            source_event_id="evt-2",
            pending_validation=False,
        )
    assert promoted.confidence == 0.95
    assert promoted.pending_validation is False

    # A subsequent lower-confidence pattern hit must NOT downgrade.
    async with neo4j_driver.session() as session:
        downgrade_attempt = await create_relation(
            session,
            user_id=test_user,
            subject_id=a.id,
            predicate="ally_of",
            object_id=b.id,
            confidence=0.3,
            source_event_id="evt-3",
            pending_validation=True,
        )
    assert downgrade_attempt.confidence == 0.95
    assert downgrade_attempt.pending_validation is False


@pytest.mark.asyncio
async def test_k11_6_create_relation_returns_none_for_missing_endpoint(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        a = await _entity(session, user_id=test_user, name="A")
        rel = await create_relation(
            session,
            user_id=test_user,
            subject_id=a.id,
            predicate="ally_of",
            object_id="0" * 32,  # nonexistent
            confidence=0.9,
        )
    assert rel is None


@pytest.mark.asyncio
async def test_k11_6_create_relation_does_not_cross_user_boundary(neo4j_driver):
    user_a = f"u-test-{uuid.uuid4().hex[:12]}"
    user_b = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        async with neo4j_driver.session() as session:
            a_subj = await _entity(session, user_id=user_a, name="A")
            b_obj = await _entity(session, user_id=user_b, name="B")
            # user_a is the calling user but wants to create an
            # edge to user_b's node — must be rejected.
            rel = await create_relation(
                session,
                user_id=user_a,
                subject_id=a_subj.id,
                predicate="ally_of",
                object_id=b_obj.id,
                confidence=0.9,
            )
        assert rel is None
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (e:Entity) WHERE e.user_id IN [$ua, $ub] DETACH DELETE e",
                ua=user_a,
                ub=user_b,
            )


@pytest.mark.asyncio
async def test_k11_6_create_relation_validates_inputs():
    for kwargs, match in (
        (dict(subject_id="s", predicate="", object_id="o"), "predicate"),
        (dict(subject_id="", predicate="p", object_id="o"), "subject_id"),
        (dict(subject_id="s", predicate="p", object_id=""), "object_id"),
    ):
        with pytest.raises(ValueError, match=match):
            await create_relation(
                session=None,  # type: ignore[arg-type]
                user_id="u-1",
                **kwargs,
            )


# ── get_relation ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_6_get_relation_returns_none_when_missing(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        result = await get_relation(
            session, user_id=test_user, relation_id="0" * 32
        )
    assert result is None


@pytest.mark.asyncio
async def test_k11_6_get_relation_does_not_cross_user_boundary(neo4j_driver):
    user_a = f"u-test-{uuid.uuid4().hex[:12]}"
    user_b = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        async with neo4j_driver.session() as session:
            a = await _entity(session, user_id=user_a, name="A")
            b = await _entity(session, user_id=user_a, name="B")
            rel = await create_relation(
                session,
                user_id=user_a,
                subject_id=a.id,
                predicate="ally_of",
                object_id=b.id,
                confidence=0.9,
            )
            assert rel is not None
            from_b = await get_relation(
                session, user_id=user_b, relation_id=rel.id
            )
        assert from_b is None
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (e:Entity) WHERE e.user_id IN [$ua, $ub] DETACH DELETE e",
                ua=user_a,
                ub=user_b,
            )


# ── find_relations_for_entity (1-hop) ─────────────────────────────────


@pytest.mark.asyncio
async def test_k11_6_find_1hop_returns_outgoing_relations(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        ally = await _entity(session, user_id=test_user, name="Ally")
        enemy = await _entity(session, user_id=test_user, name="Enemy")
        await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            predicate="ally_of",
            object_id=ally.id,
            confidence=0.9,
        )
        await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            predicate="enemy_of",
            object_id=enemy.id,
            confidence=0.85,
        )
        rels = await find_relations_for_entity(
            session, user_id=test_user, entity_id=kai.id
        )
    assert len(rels) == 2
    predicates = {r.predicate for r in rels}
    assert predicates == {"ally_of", "enemy_of"}


@pytest.mark.asyncio
async def test_k11_6_find_1hop_min_confidence_filters_quarantine(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        suspect = await _entity(session, user_id=test_user, name="Suspect")
        await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            predicate="suspects",
            object_id=suspect.id,
            confidence=0.4,  # below 0.8 default → excluded
            pending_validation=True,
        )
        excluded = await find_relations_for_entity(
            session, user_id=test_user, entity_id=kai.id
        )
        included = await find_relations_for_entity(
            session,
            user_id=test_user,
            entity_id=kai.id,
            min_confidence=0.0,
            exclude_pending=False,
        )
    assert excluded == []
    assert len(included) == 1
    assert included[0].pending_validation is True


@pytest.mark.asyncio
async def test_k11_6_find_1hop_excludes_invalidated_relations(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        old_ally = await _entity(session, user_id=test_user, name="OldAlly")
        rel = await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            predicate="ally_of",
            object_id=old_ally.id,
            confidence=0.9,
        )
        before = await find_relations_for_entity(
            session, user_id=test_user, entity_id=kai.id
        )
        await invalidate_relation(
            session, user_id=test_user, relation_id=rel.id
        )
        after = await find_relations_for_entity(
            session, user_id=test_user, entity_id=kai.id
        )
    assert len(before) == 1
    assert after == []


@pytest.mark.asyncio
async def test_k11_6_find_1hop_excludes_archived_object_by_default(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        target = await upsert_glossary_anchor(
            session,
            user_id=test_user,
            project_id="p-1",
            glossary_entity_id="gloss-rel-arch",
            name="Target",
            kind="character",
        )
        await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            predicate="ally_of",
            object_id=target.id,
            confidence=0.9,
        )
        await archive_entity(
            session,
            user_id=test_user,
            canonical_id=target.id,
            reason="glossary_deleted",
        )
        active = await find_relations_for_entity(
            session, user_id=test_user, entity_id=kai.id
        )
        with_archived = await find_relations_for_entity(
            session,
            user_id=test_user,
            entity_id=kai.id,
            include_archived_object=True,
        )
    assert active == []
    assert len(with_archived) == 1


@pytest.mark.asyncio
async def test_k11_6_find_1hop_validates_inputs():
    with pytest.raises(ValueError, match="entity_id"):
        await find_relations_for_entity(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            entity_id="",
        )
    with pytest.raises(ValueError, match="min_confidence"):
        await find_relations_for_entity(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            entity_id="e",
            min_confidence=1.5,
        )
    with pytest.raises(ValueError, match="limit"):
        await find_relations_for_entity(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            entity_id="e",
            limit=0,
        )


# ── find_relations_2hop ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_6_find_2hop_traversal(neo4j_driver, test_user):
    """KSA L2 example: Kai's allies' loyalties.
       Kai —ally_of→ Phoenix —loyal_to→ Crown
       Kai —ally_of→ Drake —enemy_of→ Wraith"""
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        phoenix = await _entity(session, user_id=test_user, name="Phoenix")
        drake = await _entity(session, user_id=test_user, name="Drake")
        crown = await _entity(session, user_id=test_user, name="Crown")
        wraith = await _entity(session, user_id=test_user, name="Wraith")
        await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            predicate="ally_of",
            object_id=phoenix.id,
            confidence=0.95,
        )
        await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            predicate="ally_of",
            object_id=drake.id,
            confidence=0.9,
        )
        await create_relation(
            session,
            user_id=test_user,
            subject_id=phoenix.id,
            predicate="loyal_to",
            object_id=crown.id,
            confidence=0.9,
        )
        await create_relation(
            session,
            user_id=test_user,
            subject_id=drake.id,
            predicate="enemy_of",
            object_id=wraith.id,
            confidence=0.85,
        )
        # Hop1 must be ally_of, hop2 in {loyal_to, enemy_of}
        hops = await find_relations_2hop(
            session,
            user_id=test_user,
            entity_id=kai.id,
            hop1_types=["ally_of"],
            hop2_types=["loyal_to", "enemy_of"],
        )
    assert len(hops) == 2
    targets = {(h.via_name, h.hop2.predicate, h.hop2.object_name) for h in hops}
    assert ("Phoenix", "loyal_to", "Crown") in targets
    assert ("Drake", "enemy_of", "Wraith") in targets


@pytest.mark.asyncio
async def test_k11_6_find_2hop_excludes_self_loop_back_to_anchor(
    neo4j_driver, test_user
):
    """Kai —ally_of→ Phoenix —ally_of→ Kai must NOT appear in the
    results — the anchor cannot be both the source and a 2-hop
    target."""
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        phoenix = await _entity(session, user_id=test_user, name="Phoenix")
        await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            predicate="ally_of",
            object_id=phoenix.id,
            confidence=0.9,
        )
        await create_relation(
            session,
            user_id=test_user,
            subject_id=phoenix.id,
            predicate="ally_of",
            object_id=kai.id,
            confidence=0.9,
        )
        hops = await find_relations_2hop(
            session,
            user_id=test_user,
            entity_id=kai.id,
            hop1_types=["ally_of"],
        )
    assert hops == []


@pytest.mark.asyncio
async def test_k11_6_find_2hop_requires_hop1_types():
    with pytest.raises(ValueError, match="hop1_types"):
        await find_relations_2hop(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            entity_id="e",
            hop1_types=[],
        )


@pytest.mark.asyncio
async def test_k11_6_find_2hop_hop2_types_none_allows_any(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        phoenix = await _entity(session, user_id=test_user, name="Phoenix")
        crown = await _entity(session, user_id=test_user, name="Crown")
        await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            predicate="ally_of",
            object_id=phoenix.id,
            confidence=0.9,
        )
        await create_relation(
            session,
            user_id=test_user,
            subject_id=phoenix.id,
            predicate="serves",  # any predicate
            object_id=crown.id,
            confidence=0.9,
        )
        hops = await find_relations_2hop(
            session,
            user_id=test_user,
            entity_id=kai.id,
            hop1_types=["ally_of"],
            hop2_types=None,
        )
    assert len(hops) == 1
    assert hops[0].hop2.predicate == "serves"


# ── invalidate_relation ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_6_invalidate_sets_valid_until(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        ally = await _entity(session, user_id=test_user, name="Ally")
        rel = await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            predicate="ally_of",
            object_id=ally.id,
            confidence=0.9,
        )
        invalidated = await invalidate_relation(
            session, user_id=test_user, relation_id=rel.id
        )
    assert invalidated is not None
    assert invalidated.valid_until is not None


@pytest.mark.asyncio
async def test_k11_6_invalidate_with_explicit_timestamp(neo4j_driver, test_user):
    custom = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        ally = await _entity(session, user_id=test_user, name="Ally")
        rel = await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            predicate="ally_of",
            object_id=ally.id,
            confidence=0.9,
        )
        invalidated = await invalidate_relation(
            session,
            user_id=test_user,
            relation_id=rel.id,
            valid_until=custom,
        )
    assert invalidated.valid_until == custom


@pytest.mark.asyncio
async def test_k11_6_invalidate_returns_none_for_missing(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        result = await invalidate_relation(
            session, user_id=test_user, relation_id="0" * 32
        )
    assert result is None


@pytest.mark.asyncio
async def test_k11_6_invalidate_validates_input():
    with pytest.raises(ValueError, match="relation_id"):
        await invalidate_relation(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            relation_id="",
        )
