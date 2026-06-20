"""LH integration tests -- kg_triage_items repo against a real Postgres.

Requires TEST_KNOWLEDGE_DB_URL; skips otherwise via the shared `pool` fixture.
Exercises park / list_grouped (by signature) / resolve_signature (batch) /
dismiss + cross-tenant isolation end-to-end.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.repositories.triage import SUGGESTED_ACTIONS, TriageRepo

pytestmark = pytest.mark.asyncio


async def _truncate(pool):
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE kg_triage_items RESTART IDENTITY CASCADE")


async def test_park_then_list_grouped_one_row_per_signature(pool):
    await _truncate(pool)
    repo = TriageRepo(pool)
    owner = uuid4()
    project = f"proj-{uuid4()}"

    # 3 "curiosity" vocab items + 2 "LOVER_OF" edge mismatch items + 1 dismissed.
    for _ in range(3):
        await repo.park(
            user_id=owner, project_id=project,
            item_type="unknown_vocab_value", signature="drive:curiosity",
            payload={"set": "drive", "value": "curiosity"},
            source={"chapter_ord": 12},
        )
    for _ in range(2):
        await repo.park(
            user_id=owner, project_id=project,
            item_type="edge_kind_mismatch", signature="LOVER_OF:char->org",
            payload={"predicate": "LOVER_OF", "src_kind": "character", "tgt_kind": "organization"},
        )

    groups, has_more = await repo.list_grouped(user_id=owner, project_id=project)
    assert has_more is False
    assert len(groups) == 2  # one row per signature, not per item
    by_sig = {g.signature: g for g in groups}
    assert by_sig["drive:curiosity"].count == 3
    assert by_sig["drive:curiosity"].item_type == "unknown_vocab_value"
    assert by_sig["drive:curiosity"].suggested_actions == SUGGESTED_ACTIONS["unknown_vocab_value"]
    assert by_sig["drive:curiosity"].sample_payload["value"] == "curiosity"
    assert by_sig["LOVER_OF:char->org"].count == 2
    # ordered by count DESC -> curiosity (3) before lover (2)
    assert groups[0].signature == "drive:curiosity"


async def test_item_type_filter(pool):
    await _truncate(pool)
    repo = TriageRepo(pool)
    owner = uuid4()
    project = f"proj-{uuid4()}"
    await repo.park(user_id=owner, project_id=project, item_type="unknown_vocab_value",
                    signature="drive:curiosity", payload={})
    await repo.park(user_id=owner, project_id=project, item_type="unknown_edge_type",
                    signature="HATES", payload={})
    groups, _ = await repo.list_grouped(
        user_id=owner, project_id=project, item_type="unknown_edge_type"
    )
    assert {g.signature for g in groups} == {"HATES"}


async def test_resolve_signature_batches_all_pending(pool):
    await _truncate(pool)
    repo = TriageRepo(pool)
    owner = uuid4()
    project = f"proj-{uuid4()}"
    for _ in range(4):
        await repo.park(user_id=owner, project_id=project,
                        item_type="unknown_vocab_value", signature="drive:curiosity", payload={})

    affected = await repo.resolve_signature(
        user_id=owner, project_id=project, signature="drive:curiosity",
        action="map", params={"map_to": "uncover_truth"},
        resolved_by=str(owner), new_status="resolved",
    )
    assert affected == 4
    # all 4 now resolved -> pending list empty
    pending, _ = await repo.list_grouped(user_id=owner, project_id=project, status="pending")
    assert pending == []
    resolved, _ = await repo.list_grouped(user_id=owner, project_id=project, status="resolved")
    assert len(resolved) == 1 and resolved[0].count == 4


async def test_resolve_signature_only_touches_pending(pool):
    """A 2nd resolve of the same signature affects 0 (already terminal)."""
    await _truncate(pool)
    repo = TriageRepo(pool)
    owner = uuid4()
    project = f"proj-{uuid4()}"
    await repo.park(user_id=owner, project_id=project,
                    item_type="unknown_vocab_value", signature="drive:curiosity", payload={})
    first = await repo.resolve_signature(
        user_id=owner, project_id=project, signature="drive:curiosity",
        action="dismiss", params={}, resolved_by=str(owner), new_status="resolved",
    )
    assert first == 1
    second = await repo.resolve_signature(
        user_id=owner, project_id=project, signature="drive:curiosity",
        action="dismiss", params={}, resolved_by=str(owner), new_status="resolved",
    )
    assert second == 0


async def test_glossary_handoff_sets_pending_glossary(pool):
    await _truncate(pool)
    repo = TriageRepo(pool)
    owner = uuid4()
    project = f"proj-{uuid4()}"
    await repo.park(user_id=owner, project_id=project, item_type="unknown_node_kind",
                    signature="kind:bloodline", payload={"proposed_kind": "bloodline"})
    affected = await repo.resolve_signature(
        user_id=owner, project_id=project, signature="kind:bloodline",
        action="promote_to_glossary_kind", params={}, resolved_by=str(owner),
        new_status="pending_glossary",
    )
    assert affected == 1
    handed, _ = await repo.list_grouped(
        user_id=owner, project_id=project, status="pending_glossary"
    )
    assert len(handed) == 1 and handed[0].signature == "kind:bloodline"


async def test_dismiss_single_item(pool):
    await _truncate(pool)
    repo = TriageRepo(pool)
    owner = uuid4()
    project = f"proj-{uuid4()}"
    item = await repo.park(user_id=owner, project_id=project,
                           item_type="unknown_vocab_value", signature="drive:x", payload={})
    ok = await repo.dismiss(user_id=owner, project_id=project,
                            triage_id=item.triage_id, resolved_by=str(owner))
    assert ok is True
    # second dismiss -> already terminal -> False (404 at router)
    again = await repo.dismiss(user_id=owner, project_id=project,
                               triage_id=item.triage_id, resolved_by=str(owner))
    assert again is False


# ── tenancy: user B can never see/resolve/dismiss user A's triage ────────────
async def test_cross_tenant_isolation(pool):
    await _truncate(pool)
    repo = TriageRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    project = f"proj-{uuid4()}"  # SAME project id -- isolation is on user_id too
    item = await repo.park(user_id=user_a, project_id=project,
                           item_type="unknown_vocab_value", signature="drive:curiosity", payload={})

    # B lists the same project -> sees NOTHING (scoped by user_id).
    b_groups, _ = await repo.list_grouped(user_id=user_b, project_id=project)
    assert b_groups == []

    # B resolves A's signature -> affects 0 rows.
    affected = await repo.resolve_signature(
        user_id=user_b, project_id=project, signature="drive:curiosity",
        action="map", params={}, resolved_by=str(user_b), new_status="resolved",
    )
    assert affected == 0

    # B dismisses A's item by id -> False (not visible to B).
    assert await repo.dismiss(user_id=user_b, project_id=project,
                              triage_id=item.triage_id, resolved_by=str(user_b)) is False

    # A still sees their pending item intact.
    a_groups, _ = await repo.list_grouped(user_id=user_a, project_id=project)
    assert len(a_groups) == 1 and a_groups[0].count == 1


async def test_cross_project_isolation_same_user(pool):
    """Same user, two projects -> triage doesn't leak across projects."""
    await _truncate(pool)
    repo = TriageRepo(pool)
    owner = uuid4()
    proj_a = f"proj-{uuid4()}"
    proj_b = f"proj-{uuid4()}"
    await repo.park(user_id=owner, project_id=proj_a,
                    item_type="unknown_vocab_value", signature="drive:x", payload={})
    b_groups, _ = await repo.list_grouped(user_id=owner, project_id=proj_b)
    assert b_groups == []


async def test_list_grouped_pagination(pool):
    await _truncate(pool)
    repo = TriageRepo(pool)
    owner = uuid4()
    project = f"proj-{uuid4()}"
    # 3 distinct signatures, 1 item each.
    for i in range(3):
        await repo.park(user_id=owner, project_id=project,
                        item_type="unknown_edge_type", signature=f"EDGE_{i}", payload={})
    page1, more1 = await repo.list_grouped(user_id=owner, project_id=project, limit=2)
    assert len(page1) == 2 and more1 is True
    page2, more2 = await repo.list_grouped(user_id=owner, project_id=project, limit=2, offset=2)
    assert len(page2) == 1 and more2 is False
