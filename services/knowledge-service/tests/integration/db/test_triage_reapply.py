"""E1 (D-KG-LH-NEO4J-REAPPLY) integration — the real ReapplyWriter writes a
corrected triage edge into live Neo4j via the central write path.

Skipped when TEST_NEO4J_URI is unset. Seeds entities via merge_entity, drives
``Neo4jReapplyWriter`` directly (the per-item unit the router loops), and asserts
the edge appears / the prior open instance auto-closes / dismiss writes nothing.

Spec: docs/specs/2026-06-21-kg-deferred-clearance.md §5 (E1).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.db.neo4j_repos.entities import merge_entity
from app.db.neo4j_repos.relations import create_relation, get_relation, relation_id
from app.db.ontology_models import TriageItem
from app.ontology.triage_apply import Neo4jReapplyWriter, apply_resolved

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-reapply-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (e:Entity {user_id: $user_id}) DETACH DELETE e",
                user_id=user_id,
            )


async def _entity(session, *, user_id, name, project_id="p-reapply"):
    return await merge_entity(
        session, user_id=user_id, project_id=project_id, name=name,
        kind="character", source_type="book_content", confidence=0.9,
    )


def _proposed_item(*, user_id, subject_id, object_id, predicate, item_type="proposed_edge"):
    return TriageItem(
        triage_id=uuid.uuid4(),
        user_id=uuid.uuid4(),  # PG owner uuid — irrelevant to the Neo4j write
        project_id="p-reapply",
        source={},
        item_type=item_type,
        payload={
            "source_entity_id": subject_id,
            "target_entity_id": object_id,
            "predicate": predicate,
        },
        signature=f"propose_edge:{predicate}:{subject_id}->{object_id}",
        status="pending",
        resolution=None,
        schema_version=None,
        created_at=datetime.now(timezone.utc),
        resolved_at=None,
        resolved_by=None,
    )


async def test_e1_map_writes_corrected_edge(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        a = await _entity(session, user_id=test_user, name="Kai")
        b = await _entity(session, user_id=test_user, name="Phoenix")
        item = _proposed_item(
            user_id=test_user, subject_id=a.id, object_id=b.id, predicate="ALLIES",
        )
        writer = Neo4jReapplyWriter(session, owner_user_id=test_user)
        did = await apply_resolved(item, "map", {}, writer=writer)
        assert did is True
        rel = await get_relation(
            session, user_id=test_user,
            relation_id=relation_id(
                user_id=test_user, subject_id=a.id, predicate="ALLIES", object_id=b.id
            ),
        )
    assert rel is not None
    assert rel.predicate == "ALLIES"
    assert rel.valid_until is None


async def test_e1_close_previous_closes_prior_open_instance(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        sect_a = await _entity(session, user_id=test_user, name="SectA")
        sect_b = await _entity(session, user_id=test_user, name="SectB")
        member = await _entity(session, user_id=test_user, name="Disciple")
        # Prior OPEN instance: member -CURRENT_SECT-> SectA.
        prior = await create_relation(
            session, user_id=test_user, subject_id=member.id,
            predicate="CURRENT_SECT", object_id=sect_a.id, confidence=0.9,
        )
        assert prior is not None and prior.valid_until is None

        # close_previous: member -CURRENT_SECT-> SectB with single_active auto-close.
        item = _proposed_item(
            user_id=test_user, subject_id=member.id, object_id=sect_b.id,
            predicate="CURRENT_SECT", item_type="edge_cardinality_conflict",
        )
        writer = Neo4jReapplyWriter(session, owner_user_id=test_user)
        did = await apply_resolved(item, "close_previous", {}, writer=writer)
        assert did is True

        prior_after = await get_relation(
            session, user_id=test_user,
            relation_id=relation_id(
                user_id=test_user, subject_id=member.id,
                predicate="CURRENT_SECT", object_id=sect_a.id,
            ),
        )
        new_after = await get_relation(
            session, user_id=test_user,
            relation_id=relation_id(
                user_id=test_user, subject_id=member.id,
                predicate="CURRENT_SECT", object_id=sect_b.id,
            ),
        )
    assert prior_after is not None and prior_after.valid_until is not None  # auto-closed
    assert new_after is not None and new_after.valid_until is None          # the only open one


async def test_e1_dismiss_writes_nothing(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        a = await _entity(session, user_id=test_user, name="X")
        b = await _entity(session, user_id=test_user, name="Y")
        item = _proposed_item(
            user_id=test_user, subject_id=a.id, object_id=b.id, predicate="ALLIES",
        )
        writer = Neo4jReapplyWriter(session, owner_user_id=test_user)
        did = await apply_resolved(item, "dismiss", {}, writer=writer)
        assert did is False  # dismiss is not a REAPPLY action
        rel = await get_relation(
            session, user_id=test_user,
            relation_id=relation_id(
                user_id=test_user, subject_id=a.id, predicate="ALLIES", object_id=b.id
            ),
        )
    assert rel is None  # nothing written
