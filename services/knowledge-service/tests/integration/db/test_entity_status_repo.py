"""A2-S1 :EntityStatus repository — pure id tests + live-Neo4j integration."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.entity_status import (
    STATUS_VALUES,
    delete_entity_status_with_zero_evidence,
    entity_status_id,
    list_gone_entities,
    merge_entity_status,
    status_at_order,
)


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (s:EntityStatus {user_id: $user_id}) DETACH DELETE s",
                user_id=user_id,
            )
            await session.run(
                "MATCH (e:Entity {user_id: $user_id}) DETACH DELETE e",
                user_id=user_id,
            )


# ── entity_status_id (pure) ───────────────────────────────────────────

def test_status_id_deterministic():
    a = entity_status_id("u-1", "p-1", "e-1", 5, "gone")
    b = entity_status_id("u-1", "p-1", "e-1", 5, "gone")
    assert a == b and len(a) == 32


def test_status_id_distinct_per_order_and_status():
    base = entity_status_id("u-1", "p-1", "e-1", 5, "gone")
    assert base != entity_status_id("u-1", "p-1", "e-1", 9, "gone")   # later order
    assert base != entity_status_id("u-1", "p-1", "e-1", 5, "active") # revival
    assert base != entity_status_id("u-1", "p-1", "e-2", 5, "gone")   # other entity


def test_status_id_rejects_invalid():
    with pytest.raises(ValueError, match="status must be one of"):
        entity_status_id("u-1", "p-1", "e-1", 5, "dead")
    with pytest.raises(ValueError, match="from_order must be an int"):
        entity_status_id("u-1", "p-1", "e-1", "5", "gone")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="entity_id is required"):
        entity_status_id("u-1", "p-1", "", 5, "gone")


def test_status_values_constant():
    assert set(STATUS_VALUES) == {"active", "gone"}


# ── live Neo4j ────────────────────────────────────────────────────────

async def _evidence(driver, status_id: str, n: int) -> None:
    """Simulate the A2-S1b persist add_evidence (sets evidence_count)."""
    async with driver.session() as session:
        await session.run(
            "MATCH (s:EntityStatus {id: $id}) SET s.evidence_count = $n",
            id=status_id, n=n,
        )


@pytest.mark.asyncio
async def test_merge_and_idempotent(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        a = await merge_entity_status(
            session, user_id=test_user, project_id="p-1", entity_id="e-1",
            status="gone", from_order=1_000_005, source_chapter="ch-3")
        b = await merge_entity_status(
            session, user_id=test_user, project_id="p-1", entity_id="e-1",
            status="gone", from_order=1_000_005)
    assert a.id == b.id and a.status == "gone" and a.from_order == 1_000_005
    async with neo4j_driver.session() as session:
        r = await session.run("MATCH (s:EntityStatus {id:$id}) RETURN count(s) AS n", id=a.id)
        assert (await r.single())["n"] == 1


@pytest.mark.asyncio
async def test_status_at_order_default_and_transitions(neo4j_driver, test_user):
    # e-1 dies at order 1_000_010, revives at 1_000_020; e-2 never changes.
    async with neo4j_driver.session() as session:
        gone = await merge_entity_status(session, user_id=test_user, project_id="p-1",
                                         entity_id="e-1", status="gone", from_order=1_000_010)
        back = await merge_entity_status(session, user_id=test_user, project_id="p-1",
                                         entity_id="e-1", status="active", from_order=1_000_020)
    await _evidence(neo4j_driver, gone.id, 1)
    await _evidence(neo4j_driver, back.id, 1)

    async with neo4j_driver.session() as session:
        # before the death → active (default, no transition ≤ P)
        before = await status_at_order(session, user_id=test_user, project_id="p-1",
                                       entity_ids=["e-1", "e-2"], at_order=1_000_005)
        # between death and revival → gone; e-2 has none → active (NOT dropped)
        mid = await status_at_order(session, user_id=test_user, project_id="p-1",
                                    entity_ids=["e-1", "e-2"], at_order=1_000_015)
        # after revival → active again (latest ≤ P wins)
        after = await status_at_order(session, user_id=test_user, project_id="p-1",
                                      entity_ids=["e-1"], at_order=1_000_025)
    assert before == {"e-1": "active", "e-2": "active"}
    assert mid == {"e-1": "gone", "e-2": "active"}
    assert after == {"e-1": "active"}


@pytest.mark.asyncio
async def test_unevidenced_status_does_not_count(neo4j_driver, test_user):
    # a merged-but-unevidenced (evidence_count=0) transition must NOT win.
    async with neo4j_driver.session() as session:
        await merge_entity_status(session, user_id=test_user, project_id="p-1",
                                  entity_id="e-1", status="gone", from_order=1_000_010)
        res = await status_at_order(session, user_id=test_user, project_id="p-1",
                                    entity_ids=["e-1"], at_order=1_000_999)
    assert res == {"e-1": "active"}  # un-evidenced gone ignored → default active


@pytest.mark.asyncio
async def test_delete_zero_evidence_and_isolation(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        kept = await merge_entity_status(session, user_id=test_user, project_id="p-1",
                                         entity_id="e-1", status="gone", from_order=1_000_010)
        await merge_entity_status(session, user_id=test_user, project_id="p-1",
                                  entity_id="e-2", status="gone", from_order=1_000_010)
    await _evidence(neo4j_driver, kept.id, 1)  # e-1 evidenced, e-2 not
    async with neo4j_driver.session() as session:
        deleted = await delete_entity_status_with_zero_evidence(
            session, user_id=test_user, project_id="p-1")
        # cross-user delete is a no-op
        other = await delete_entity_status_with_zero_evidence(
            session, user_id=f"u-other-{uuid.uuid4().hex[:8]}")
    assert deleted == 1 and other == 0
    async with neo4j_driver.session() as session:
        r = await session.run("MATCH (s:EntityStatus {user_id:$u}) RETURN count(s) AS n", u=test_user)
        assert (await r.single())["n"] == 1  # only the evidenced one survives


# ── list_gone_entities (D-KG-EXTRACTION-CANON-WIRE) ────────────────────

async def _entity_node(driver, *, user_id, project_id, entity_id, name, canonical_name):
    async with driver.session() as session:
        await session.run(
            "MERGE (e:Entity {id: $id}) SET e.user_id=$u, e.project_id=$p, "
            "e.name=$name, e.canonical_name=$cn",
            id=entity_id, u=user_id, p=project_id, name=name, cn=canonical_name,
        )


@pytest.mark.asyncio
async def test_list_gone_entities_returns_only_currently_gone(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        gone = await merge_entity_status(session, user_id=test_user, project_id="p-1",
                                         entity_id="e-1", status="gone", from_order=1_000_010)
        # e-2 dies then revives -- latest transition is 'active', must NOT appear.
        e2_gone = await merge_entity_status(session, user_id=test_user, project_id="p-1",
                                            entity_id="e-2", status="gone", from_order=1_000_010)
        e2_back = await merge_entity_status(session, user_id=test_user, project_id="p-1",
                                            entity_id="e-2", status="active", from_order=1_000_020)
    await _evidence(neo4j_driver, gone.id, 1)
    await _evidence(neo4j_driver, e2_gone.id, 1)
    await _evidence(neo4j_driver, e2_back.id, 1)

    async with neo4j_driver.session() as session:
        result = await list_gone_entities(session, user_id=test_user, project_id="p-1")
    ids = {r["entity_id"] for r in result}
    assert ids == {"e-1"}
    assert next(r for r in result if r["entity_id"] == "e-1")["from_order"] == 1_000_010


@pytest.mark.asyncio
async def test_list_gone_entities_joins_entity_name(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        gone = await merge_entity_status(session, user_id=test_user, project_id="p-1",
                                         entity_id="e-1", status="gone", from_order=1_000_010)
    await _evidence(neo4j_driver, gone.id, 1)
    await _entity_node(neo4j_driver, user_id=test_user, project_id="p-1",
                       entity_id="e-1", name="Alice", canonical_name="alice")

    async with neo4j_driver.session() as session:
        result = await list_gone_entities(session, user_id=test_user, project_id="p-1")
    assert result == [{"entity_id": "e-1", "name": "Alice", "canonical_name": "alice",
                       "from_order": 1_000_010}]


@pytest.mark.asyncio
async def test_list_gone_entities_tolerates_missing_entity_node(neo4j_driver, test_user):
    """No :Entity node found -- name/canonical_name are None, not a crash."""
    async with neo4j_driver.session() as session:
        gone = await merge_entity_status(session, user_id=test_user, project_id="p-1",
                                         entity_id="e-orphan", status="gone", from_order=1_000_010)
    await _evidence(neo4j_driver, gone.id, 1)

    async with neo4j_driver.session() as session:
        result = await list_gone_entities(session, user_id=test_user, project_id="p-1")
    assert result == [{"entity_id": "e-orphan", "name": None, "canonical_name": None,
                       "from_order": 1_000_010}]


@pytest.mark.asyncio
async def test_list_gone_entities_excludes_unevidenced(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        await merge_entity_status(session, user_id=test_user, project_id="p-1",
                                  entity_id="e-1", status="gone", from_order=1_000_010)
        result = await list_gone_entities(session, user_id=test_user, project_id="p-1")
    assert result == []  # evidence_count=0 by default -- un-evidenced ignored


@pytest.mark.asyncio
async def test_list_gone_entities_scoped_to_project(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        p1 = await merge_entity_status(session, user_id=test_user, project_id="p-1",
                                       entity_id="e-1", status="gone", from_order=1_000_010)
        p2 = await merge_entity_status(session, user_id=test_user, project_id="p-2",
                                       entity_id="e-2", status="gone", from_order=1_000_010)
    await _evidence(neo4j_driver, p1.id, 1)
    await _evidence(neo4j_driver, p2.id, 1)

    async with neo4j_driver.session() as session:
        result = await list_gone_entities(session, user_id=test_user, project_id="p-1")
    assert {r["entity_id"] for r in result} == {"e-1"}


@pytest.mark.asyncio
async def test_list_gone_entities_empty_when_none_gone(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        result = await list_gone_entities(session, user_id=test_user, project_id="p-1")
    assert result == []
