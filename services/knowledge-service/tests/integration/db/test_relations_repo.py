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
    get_project_subgraph,
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


async def _entity(
    session, *, user_id: str, name: str, kind: str = "character",
    project_id: str = "p-1",
):
    return await merge_entity(
        session,
        user_id=user_id,
        project_id=project_id,
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
async def test_L7_create_relation_stamps_schema_version_and_graph_id(neo4j_driver, test_user):
    """L7: the resolved schema_version (M3) + graph_id seam (M2, NULL at v1) are
    persisted onto the written edge. Read back via raw Cypher — the Relation model
    doesn't surface these provenance/seam props."""
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        zhao = await _entity(session, user_id=test_user, name="Zhao")
        rel = await create_relation(
            session, user_id=test_user, subject_id=kai.id,
            predicate="trusts", object_id=zhao.id, schema_version=9,
        )
        assert rel is not None
        rid = relation_id(user_id=test_user, subject_id=kai.id, predicate="trusts", object_id=zhao.id)
        res = await session.run(
            "MATCH ()-[r:RELATES_TO {id: $rid}]->() RETURN r.schema_version AS sv, r.graph_id AS gid",
            rid=rid,
        )
        rec = await res.single()
    assert rec["sv"] == 9        # M3 schema_version stamp persisted
    assert rec["gid"] is None    # M2 graph_id seam present + NULL at v1

    # legacy/un-adopted write (schema_version omitted) → NULL, no behavior change
    async with neo4j_driver.session() as session:
        a = await _entity(session, user_id=test_user, name="Aoi")
        b = await _entity(session, user_id=test_user, name="Bo")
        await create_relation(session, user_id=test_user, subject_id=a.id, predicate="knows", object_id=b.id)
        rid2 = relation_id(user_id=test_user, subject_id=a.id, predicate="knows", object_id=b.id)
        res2 = await session.run(
            "MATCH ()-[r:RELATES_TO {id: $rid}]->() RETURN r.schema_version AS sv", rid=rid2,
        )
        rec2 = await res2.single()
    assert rec2["sv"] is None


@pytest.mark.asyncio
async def test_L7_create_relation_stamps_schema_version_on_match(neo4j_driver, test_user):
    """L7 activation (R3 MED): an edge first written pre-activation (schema_version
    NULL) is BACKFILLED on the next extraction under a resolved schema (ON MATCH),
    and a later legacy/un-adopted persist (schema_version NULL) does NOT wipe the
    stamp (COALESCE preserves it). graph_id stays untouched on MATCH."""
    async with neo4j_driver.session() as session:
        mei = await _entity(session, user_id=test_user, name="Mei")
        lan = await _entity(session, user_id=test_user, name="Lan")
        rid = relation_id(user_id=test_user, subject_id=mei.id, predicate="rivals", object_id=lan.id)

        # 1) pre-activation write — no schema_version → NULL stamp.
        await create_relation(
            session, user_id=test_user, subject_id=mei.id, predicate="rivals",
            object_id=lan.id, confidence=0.6,
        )
        res = await session.run(
            "MATCH ()-[r:RELATES_TO {id: $rid}]->() RETURN r.schema_version AS sv", rid=rid,
        )
        assert (await res.single())["sv"] is None

        # 2) re-extraction under a resolved schema → ON MATCH backfills the version.
        await create_relation(
            session, user_id=test_user, subject_id=mei.id, predicate="rivals",
            object_id=lan.id, confidence=0.9, schema_version=5,
        )
        res = await session.run(
            "MATCH ()-[r:RELATES_TO {id: $rid}]->() RETURN r.schema_version AS sv, r.graph_id AS gid",
            rid=rid,
        )
        rec = await res.single()
        assert rec["sv"] == 5      # backfilled on match
        assert rec["gid"] is None  # graph_id never set on match

        # 3) a later legacy persist (schema_version NULL) must NOT wipe the stamp.
        await create_relation(
            session, user_id=test_user, subject_id=mei.id, predicate="rivals",
            object_id=lan.id, confidence=0.95,
        )
        res = await session.run(
            "MATCH ()-[r:RELATES_TO {id: $rid}]->() RETURN r.schema_version AS sv", rid=rid,
        )
        assert (await res.single())["sv"] == 5  # COALESCE preserved


@pytest.mark.asyncio
async def test_L7_single_active_auto_closes_prior_open_instance(neo4j_driver, test_user):
    """Lane A (D-KG-L7-CARDINALITY): for a `single_active` edge type, writing a new
    instance for the same (subject, predicate) auto-closes the prior OPEN instance
    (different object), leaving exactly one `valid_until IS NULL` edge."""
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        sect_a = await _entity(session, user_id=test_user, name="SectA")
        sect_b = await _entity(session, user_id=test_user, name="SectB")

        # 1) Kai member_of SectA (single_active) — first open instance.
        r1 = await create_relation(
            session, user_id=test_user, subject_id=kai.id,
            predicate="member_of", object_id=sect_a.id, confidence=0.9,
            cardinality="single_active",
        )
        assert r1 is not None and r1.valid_until is None

        # 2) Kai member_of SectB (single_active) — should close the SectA edge.
        r2 = await create_relation(
            session, user_id=test_user, subject_id=kai.id,
            predicate="member_of", object_id=sect_b.id, confidence=0.9,
            cardinality="single_active",
        )
        assert r2 is not None and r2.valid_until is None

        # Exactly one open member_of edge from Kai; the SectA edge is closed.
        res = await session.run(
            "MATCH (s:Entity {id:$sid})-[r:RELATES_TO]->(o:Entity) "
            "WHERE r.predicate='member_of' "
            "RETURN o.id AS oid, r.valid_until AS vu",
            sid=kai.id,
        )
        rows = {rec["oid"]: rec["vu"] async for rec in res}
        assert rows[sect_a.id] is not None   # SectA auto-closed
        assert rows[sect_b.id] is None       # SectB the sole open instance


@pytest.mark.asyncio
async def test_L7_multi_active_keeps_both_open(neo4j_driver, test_user):
    """Regression: `multi_active` (the default, e.g. PURSUES) coexists — a second
    instance for the same (subject, predicate) does NOT close the first."""
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        d1 = await _entity(session, user_id=test_user, name="Power")
        d2 = await _entity(session, user_id=test_user, name="Revenge")

        await create_relation(
            session, user_id=test_user, subject_id=kai.id,
            predicate="pursues", object_id=d1.id, cardinality="multi_active",
        )
        await create_relation(
            session, user_id=test_user, subject_id=kai.id,
            predicate="pursues", object_id=d2.id, cardinality="multi_active",
        )
        res = await session.run(
            "MATCH (s:Entity {id:$sid})-[r:RELATES_TO]->() "
            "WHERE r.predicate='pursues' AND r.valid_until IS NULL "
            "RETURN count(r) AS open",
            sid=kai.id,
        )
        assert (await res.single())["open"] == 2  # both still open


@pytest.mark.asyncio
async def test_L7_no_cardinality_does_not_close(neo4j_driver, test_user):
    """Legacy: cardinality=None (default) never closes a prior instance — the
    auto-close path is opt-in."""
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        s1 = await _entity(session, user_id=test_user, name="S1")
        s2 = await _entity(session, user_id=test_user, name="S2")
        await create_relation(
            session, user_id=test_user, subject_id=kai.id,
            predicate="member_of", object_id=s1.id,  # no cardinality
        )
        await create_relation(
            session, user_id=test_user, subject_id=kai.id,
            predicate="member_of", object_id=s2.id,
        )
        res = await session.run(
            "MATCH (s:Entity {id:$sid})-[r:RELATES_TO]->() "
            "WHERE r.predicate='member_of' AND r.valid_until IS NULL "
            "RETURN count(r) AS open",
            sid=kai.id,
        )
        assert (await res.single())["open"] == 2  # both open — no auto-close


@pytest.mark.asyncio
async def test_L7_single_active_does_not_cross_user_boundary(neo4j_driver):
    """Tenancy: a single_active write for user A must NEVER close user B's open
    instance of the same predicate, even if the canonical ids collide."""
    ua = f"u-test-{uuid.uuid4().hex[:12]}"
    ub = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        async with neo4j_driver.session() as session:
            a_kai = await _entity(session, user_id=ua, name="Kai")
            a_sect = await _entity(session, user_id=ua, name="SectA")
            b_kai = await _entity(session, user_id=ub, name="Kai")
            b_sect = await _entity(session, user_id=ub, name="SectA")
            # B opens a single_active member_of edge.
            await create_relation(
                session, user_id=ub, subject_id=b_kai.id,
                predicate="member_of", object_id=b_sect.id,
                cardinality="single_active",
            )
            # A writes its own single_active member_of edge.
            await create_relation(
                session, user_id=ua, subject_id=a_kai.id,
                predicate="member_of", object_id=a_sect.id,
                cardinality="single_active",
            )
            # B's edge must still be open (A's close stayed in A's partition).
            res = await session.run(
                "MATCH (s:Entity {user_id:$uid})-[r:RELATES_TO]->() "
                "WHERE r.predicate='member_of' AND r.valid_until IS NULL "
                "RETURN count(r) AS open",
                uid=ub,
            )
            assert (await res.single())["open"] == 1
    finally:
        async with neo4j_driver.session() as session:
            for uid in (ua, ub):
                await session.run(
                    "MATCH (e:Entity {user_id: $uid}) DETACH DELETE e", uid=uid,
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
            include_archived_peer=True,
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


# ── K11.6-R1 review-fix tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_6_r1_find_1hop_default_returns_both_directions(
    neo4j_driver, test_user
):
    """K11.6-R1/R1 fix. The L2 RAG loader needs both
    Kai-as-subject AND Kai-as-object edges. Default direction is
    'both' so the previous outgoing-only shape no longer silently
    drops half the relations."""
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        ally = await _entity(session, user_id=test_user, name="Ally")
        admirer = await _entity(session, user_id=test_user, name="Admirer")
        # Kai → ally  (Kai is subject)
        await create_relation(
            session,
            user_id=test_user,
            subject_id=kai.id,
            predicate="ally_of",
            object_id=ally.id,
            confidence=0.9,
        )
        # admirer → Kai (Kai is object)
        await create_relation(
            session,
            user_id=test_user,
            subject_id=admirer.id,
            predicate="loyal_to",
            object_id=kai.id,
            confidence=0.9,
        )
        rels = await find_relations_for_entity(
            session, user_id=test_user, entity_id=kai.id
        )
    assert len(rels) == 2
    predicates = {(r.subject_name, r.predicate, r.object_name) for r in rels}
    assert ("Kai", "ally_of", "Ally") in predicates
    assert ("Admirer", "loyal_to", "Kai") in predicates


@pytest.mark.asyncio
async def test_k11_6_r1_find_1hop_outgoing_only(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        ally = await _entity(session, user_id=test_user, name="Ally")
        admirer = await _entity(session, user_id=test_user, name="Admirer")
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
            subject_id=admirer.id,
            predicate="loyal_to",
            object_id=kai.id,
            confidence=0.9,
        )
        rels = await find_relations_for_entity(
            session,
            user_id=test_user,
            entity_id=kai.id,
            direction="outgoing",
        )
    assert len(rels) == 1
    assert rels[0].subject_name == "Kai"
    assert rels[0].predicate == "ally_of"


@pytest.mark.asyncio
async def test_k11_6_r1_find_1hop_incoming_only(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        kai = await _entity(session, user_id=test_user, name="Kai")
        ally = await _entity(session, user_id=test_user, name="Ally")
        admirer = await _entity(session, user_id=test_user, name="Admirer")
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
            subject_id=admirer.id,
            predicate="loyal_to",
            object_id=kai.id,
            confidence=0.9,
        )
        rels = await find_relations_for_entity(
            session,
            user_id=test_user,
            entity_id=kai.id,
            direction="incoming",
        )
    assert len(rels) == 1
    assert rels[0].subject_name == "Admirer"
    assert rels[0].object_name == "Kai"
    assert rels[0].predicate == "loyal_to"


@pytest.mark.asyncio
async def test_k11_6_r1_find_1hop_validates_direction():
    with pytest.raises(ValueError, match="direction"):
        await find_relations_for_entity(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            entity_id="e",
            direction="sideways",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_k11_6_r1_find_1hop_project_id_filter(neo4j_driver, test_user):
    """K11.6-R1/R2 fix. project_id filter excludes cross-project
    edges. Two projects (p-1 and p-2) for the same user; an edge
    in p-2 must NOT appear when querying with project_id='p-1'."""
    async with neo4j_driver.session() as session:
        kai_p1 = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
            confidence=0.9,
        )
        ally_p1 = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Ally1",
            kind="character",
            source_type="book_content",
            confidence=0.9,
        )
        kai_p2 = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-2",
            name="Kai",
            kind="character",
            source_type="book_content",
            confidence=0.9,
        )
        ally_p2 = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-2",
            name="Ally2",
            kind="character",
            source_type="book_content",
            confidence=0.9,
        )
        await create_relation(
            session,
            user_id=test_user,
            subject_id=kai_p1.id,
            predicate="ally_of",
            object_id=ally_p1.id,
            confidence=0.9,
        )
        await create_relation(
            session,
            user_id=test_user,
            subject_id=kai_p2.id,
            predicate="ally_of",
            object_id=ally_p2.id,
            confidence=0.9,
        )
        # Querying the p-1 Kai with project_id=p-1 returns only
        # the p-1 ally relation.
        scoped = await find_relations_for_entity(
            session,
            user_id=test_user,
            entity_id=kai_p1.id,
            project_id="p-1",
        )
        assert len(scoped) == 1
        assert scoped[0].object_name == "Ally1"
        # No project filter returns only edges where p-1 Kai is
        # an endpoint — the p-2 edge has different endpoints.
        unscoped = await find_relations_for_entity(
            session,
            user_id=test_user,
            entity_id=kai_p1.id,
        )
        assert len(unscoped) == 1
        assert unscoped[0].object_name == "Ally1"


@pytest.mark.asyncio
async def test_k11_6_r1_find_2hop_project_id_filter(neo4j_driver, test_user):
    """K11.6-R1/R2 fix. 2-hop must not cross project boundaries
    when project_id is set."""
    async with neo4j_driver.session() as session:
        # In p-1: Kai → Phoenix → Crown
        kai = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
            confidence=0.9,
        )
        phoenix = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Phoenix",
            kind="character",
            source_type="book_content",
            confidence=0.9,
        )
        crown = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Crown",
            kind="character",
            source_type="book_content",
            confidence=0.9,
        )
        # In p-2: a stray entity that should NOT be reachable
        rogue = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-2",
            name="Rogue",
            kind="character",
            source_type="book_content",
            confidence=0.9,
        )
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
            predicate="loyal_to",
            object_id=crown.id,
            confidence=0.9,
        )
        # Cross-project edge: Phoenix (p-1) → Rogue (p-2)
        await create_relation(
            session,
            user_id=test_user,
            subject_id=phoenix.id,
            predicate="loyal_to",
            object_id=rogue.id,
            confidence=0.9,
        )
        # With project_id=p-1, only Kai → Phoenix → Crown is
        # returned. The cross-project Rogue path is filtered out.
        scoped = await find_relations_2hop(
            session,
            user_id=test_user,
            entity_id=kai.id,
            hop1_types=["ally_of"],
            hop2_types=["loyal_to"],
            project_id="p-1",
        )
        assert len(scoped) == 1
        assert scoped[0].hop2.object_name == "Crown"
        # Without project_id, both targets are reachable.
        unscoped = await find_relations_2hop(
            session,
            user_id=test_user,
            entity_id=kai.id,
            hop1_types=["ally_of"],
            hop2_types=["loyal_to"],
        )
        targets = {h.hop2.object_name for h in unscoped}
        assert targets == {"Crown", "Rogue"}


# ── C18 — get_project_subgraph (live Neo4j) ───────────────────────────


@pytest.mark.asyncio
async def test_c18_subgraph_partition_isolation(neo4j_driver, test_user):
    """Project-wide subgraph returns ONLY the (user, project) partition —
    no cross-project, no cross-user bleed (adversary F2, executed for
    real against Neo4j, not a string assertion)."""
    other_user = f"u-other-{uuid.uuid4().hex[:12]}"
    try:
        async with neo4j_driver.session() as session:
            # project A (target)
            a1 = await _entity(session, user_id=test_user, name="A1", project_id="pA")
            a2 = await _entity(session, user_id=test_user, name="A2", project_id="pA")
            await create_relation(
                session, user_id=test_user, subject_id=a1.id,
                predicate="ally_of", object_id=a2.id, confidence=0.9,
            )
            # project B (same user, different project) — must NOT appear
            b1 = await _entity(session, user_id=test_user, name="B1", project_id="pB")
            b2 = await _entity(session, user_id=test_user, name="B2", project_id="pB")
            await create_relation(
                session, user_id=test_user, subject_id=b1.id,
                predicate="ally_of", object_id=b2.id, confidence=0.9,
            )
            # other user, project A name collision — must NOT appear
            o1 = await _entity(session, user_id=other_user, name="A1", project_id="pA")
            o2 = await _entity(session, user_id=other_user, name="A2", project_id="pA")
            await create_relation(
                session, user_id=other_user, subject_id=o1.id,
                predicate="ally_of", object_id=o2.id, confidence=0.9,
            )

            sg = await get_project_subgraph(
                session, user_id=test_user, project_id="pA",
            )
        ids = {n.id for n in sg.nodes}
        assert ids == {a1.id, a2.id}, "only project-A nodes for this user"
        assert b1.id not in ids and b2.id not in ids, "cross-project bleed"
        assert o1.id not in ids and o2.id not in ids, "cross-user bleed"
        # the single in-partition edge is present, no foreign edges
        assert len(sg.edges) == 1
        edge_endpoints = {sg.edges[0].source, sg.edges[0].target}
        assert edge_endpoints == {a1.id, a2.id}
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (e:Entity {user_id: $u}) DETACH DELETE e", u=other_user,
            )


@pytest.mark.asyncio
async def test_c18_subgraph_node_cap_and_determinism(neo4j_driver, test_user):
    """The node cap is honoured AND the same query returns the same
    capped node set across calls (deterministic order — C19 stability)."""
    async with neo4j_driver.session() as session:
        ents = []
        for i in range(8):
            ents.append(
                await _entity(
                    session, user_id=test_user, name=f"N{i:02d}", project_id="pC",
                )
            )
        sg1 = await get_project_subgraph(
            session, user_id=test_user, project_id="pC", limit=5,
        )
        sg2 = await get_project_subgraph(
            session, user_id=test_user, project_id="pC", limit=5,
        )
    assert len(sg1.nodes) == 5, "node cap honoured"
    assert sg1.node_cap_hit is True
    assert [n.id for n in sg1.nodes] == [n.id for n in sg2.nodes], "deterministic"


@pytest.mark.asyncio
async def test_c18_subgraph_ego_expansion_bounded(neo4j_driver, test_user):
    """Ego-expansion from a center returns the hop-bounded neighbourhood,
    partition-scoped, with the center included. 1 hop reaches direct
    neighbours only; a 2-hop-away node is excluded at hops=1."""
    async with neo4j_driver.session() as session:
        center = await _entity(session, user_id=test_user, name="Center", project_id="pE")
        near = await _entity(session, user_id=test_user, name="Near", project_id="pE")
        far = await _entity(session, user_id=test_user, name="Far", project_id="pE")
        await create_relation(
            session, user_id=test_user, subject_id=center.id,
            predicate="ally_of", object_id=near.id, confidence=0.9,
        )
        await create_relation(
            session, user_id=test_user, subject_id=near.id,
            predicate="ally_of", object_id=far.id, confidence=0.9,
        )
        sg1 = await get_project_subgraph(
            session, user_id=test_user, project_id="pE", center=center.id, hops=1,
        )
        sg2 = await get_project_subgraph(
            session, user_id=test_user, project_id="pE", center=center.id, hops=2,
        )
    ids1 = {n.id for n in sg1.nodes}
    assert center.id in ids1 and near.id in ids1
    assert far.id not in ids1, "2-hop node must not appear at hops=1"
    ids2 = {n.id for n in sg2.nodes}
    assert far.id in ids2, "2-hop node reachable at hops=2"


@pytest.mark.asyncio
async def test_c18_subgraph_excludes_inactive_edges(neo4j_driver, test_user):
    """Low-confidence / invalidated edges are excluded; a node reachable
    only via a quarantined edge does not appear as an orphan (F3)."""
    async with neo4j_driver.session() as session:
        c = await _entity(session, user_id=test_user, name="C", project_id="pF")
        good = await _entity(session, user_id=test_user, name="Good", project_id="pF")
        quarantined = await _entity(session, user_id=test_user, name="Quar", project_id="pF")
        await create_relation(
            session, user_id=test_user, subject_id=c.id,
            predicate="ally_of", object_id=good.id, confidence=0.9,
        )
        # below the default 0.8 min_confidence → must be excluded
        await create_relation(
            session, user_id=test_user, subject_id=c.id,
            predicate="ally_of", object_id=quarantined.id, confidence=0.3,
        )
        sg = await get_project_subgraph(
            session, user_id=test_user, project_id="pF", center=c.id, hops=1,
        )
    ids = {n.id for n in sg.nodes}
    assert good.id in ids
    assert quarantined.id not in ids, "node reachable only via a low-conf edge is excluded"
