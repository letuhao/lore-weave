"""C13 — ProposalsRepo (review gate) against a REAL Postgres (no mock-only pass).

Exercises the application-layer state machine on top of the C2 schema + trigger:
  * Q3 scoping (cross-user/cross-project get → None);
  * approve / reject / edit transitions;
  * illegal transitions raise IllegalTransitionError (in-app guard, before the
    DB trigger would reject the same jump);
  * mark_promoted stamps the promotion record + permanent origin markers and is
    idempotent (re-promote same entity → no-op; different entity → conflict);
  * promote retains origin='enrichment' (immutable) after canonization.

Skips when no real DB is reachable; verify-cycle-13.sh supplies it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.services.review import (
    IllegalTransitionError,
    ProposalsRepo,
    ReviewStatus,
)

pytestmark = pytest.mark.asyncio

_PROJECT = uuid.uuid4()
_USER = uuid.uuid4()
_OTHER_USER = uuid.uuid4()


async def _seed(conn) -> uuid.UUID:
    job_id = await conn.fetchval(
        """INSERT INTO enrichment_job (project_id, user_id, technique, entity_kind)
           VALUES ($1,$2,'template','location') RETURNING job_id""",
        _PROJECT, _USER,
    )
    return await conn.fetchval(
        """INSERT INTO enrichment_proposal
             (job_id, project_id, user_id, entity_kind, target_ref, content,
              technique, confidence, provenance_json)
           VALUES ($1,$2,$3,'location','蓬萊','蓬萊：东海仙山。',
                   'template', 0.30, '{"dimensions":{"历史":"上古仙山"}}'::jsonb)
           RETURNING proposal_id""",
        job_id, _PROJECT, _USER,
    )


async def test_scoping_cross_user_returns_none(pool):
    async with pool.acquire() as conn:
        pid = await _seed(conn)
    repo = ProposalsRepo(pool)
    assert await repo.get(user_id=_USER, project_id=_PROJECT, proposal_id=pid) is not None
    # cross-user → None (→404, no existence oracle).
    assert await repo.get(user_id=_OTHER_USER, project_id=_PROJECT, proposal_id=pid) is None


async def test_approve_then_promote_retains_origin_marker(pool):
    async with pool.acquire() as conn:
        pid = await _seed(conn)
    repo = ProposalsRepo(pool)
    # proposed → author_reviewing → approved
    await repo.set_status(user_id=_USER, project_id=_PROJECT, proposal_id=pid, to_status=ReviewStatus.AUTHOR_REVIEWING)
    p = await repo.set_status(user_id=_USER, project_id=_PROJECT, proposal_id=pid, to_status=ReviewStatus.APPROVED)
    assert p.review_status == "approved"
    assert p.confidence < 1.0
    assert p.promoted_entity_id is None

    entity_id = uuid.uuid4()
    promoted_at = datetime.now(timezone.utc)
    promoted = await repo.mark_promoted(
        user_id=_USER, project_id=_PROJECT, proposal_id=pid,
        promoted_entity_id=entity_id, promoted_by=_USER, promoted_at=promoted_at,
    )
    assert promoted.review_status == "promoted"
    # permanent origin markers retained (H0).
    assert promoted.origin == "enrichment"
    assert promoted.promoted_from_proposal_id == pid
    assert promoted.original_technique == "template"
    assert promoted.promoted_entity_id == entity_id
    assert promoted.promoted_by == _USER
    # confidence STILL < 1.0 in the proposal row (canon confidence is in the KG).
    assert promoted.confidence < 1.0


async def test_illegal_transition_rejected_in_app(pool):
    async with pool.acquire() as conn:
        pid = await _seed(conn)
    repo = ProposalsRepo(pool)
    # proposed → promoted is illegal (must go through approved).
    with pytest.raises(IllegalTransitionError):
        await repo.set_status(user_id=_USER, project_id=_PROJECT, proposal_id=pid, to_status=ReviewStatus.PROMOTED)
    # proposed → approved (skipping author_reviewing) is illegal.
    with pytest.raises(IllegalTransitionError):
        await repo.set_status(user_id=_USER, project_id=_PROJECT, proposal_id=pid, to_status=ReviewStatus.APPROVED)


async def test_promote_requires_approved(pool):
    async with pool.acquire() as conn:
        pid = await _seed(conn)
    repo = ProposalsRepo(pool)
    # still 'proposed' → mark_promoted must reject (must be approved first).
    with pytest.raises(IllegalTransitionError):
        await repo.mark_promoted(
            user_id=_USER, project_id=_PROJECT, proposal_id=pid,
            promoted_entity_id=uuid.uuid4(), promoted_by=_USER,
            promoted_at=datetime.now(timezone.utc),
        )


async def test_promote_idempotent_same_entity(pool):
    async with pool.acquire() as conn:
        pid = await _seed(conn)
    repo = ProposalsRepo(pool)
    await repo.set_status(user_id=_USER, project_id=_PROJECT, proposal_id=pid, to_status=ReviewStatus.AUTHOR_REVIEWING)
    await repo.set_status(user_id=_USER, project_id=_PROJECT, proposal_id=pid, to_status=ReviewStatus.APPROVED)
    entity_id = uuid.uuid4()
    at = datetime.now(timezone.utc)
    first = await repo.mark_promoted(
        user_id=_USER, project_id=_PROJECT, proposal_id=pid,
        promoted_entity_id=entity_id, promoted_by=_USER, promoted_at=at,
    )
    # re-promote SAME entity → idempotent no-op (no duplicate canon).
    again = await repo.mark_promoted(
        user_id=_USER, project_id=_PROJECT, proposal_id=pid,
        promoted_entity_id=entity_id, promoted_by=_USER, promoted_at=datetime.now(timezone.utc),
    )
    assert again.proposal_id == first.proposal_id
    assert again.promoted_entity_id == entity_id
    # re-promote a DIFFERENT entity → conflict.
    with pytest.raises(IllegalTransitionError):
        await repo.mark_promoted(
            user_id=_USER, project_id=_PROJECT, proposal_id=pid,
            promoted_entity_id=uuid.uuid4(), promoted_by=_USER, promoted_at=datetime.now(timezone.utc),
        )


async def test_edit_keeps_non_canon(pool):
    async with pool.acquire() as conn:
        pid = await _seed(conn)
    repo = ProposalsRepo(pool)
    edited = await repo.edit_content(
        user_id=_USER, project_id=_PROJECT, proposal_id=pid, content="蓬萊：改写后的仙山描述。",
    )
    assert edited.content.startswith("蓬萊：改写")
    assert edited.origin == "enrichment"
    assert edited.confidence < 1.0
    assert edited.review_status == "proposed"


async def _seed_null_target(conn) -> uuid.UUID:
    """A new-entity proposal: NULL target_ref but a faithful canonical_name (the
    FIX-1 surface). Proves the additive canonical_name column exists + persists."""
    job_id = await conn.fetchval(
        """INSERT INTO enrichment_job (project_id, user_id, technique, entity_kind)
           VALUES ($1,$2,'fabrication','location') RETURNING job_id""",
        _PROJECT, _USER,
    )
    return await conn.fetchval(
        """INSERT INTO enrichment_proposal
             (job_id, project_id, user_id, entity_kind, target_ref, canonical_name,
              content, technique, confidence, provenance_json)
           VALUES ($1,$2,$3,'location', NULL, '昆侖虛',
                   '凭空捏造的描述，绝不可成为名称。',
                   'fabrication', 0.30, '{"dimensions":{"历史":"虚构"}}'::jsonb)
           RETURNING proposal_id""",
        job_id, _PROJECT, _USER,
    )


async def test_canonical_name_column_persists_for_null_target_ref(pool):
    """FIX-1 (DB): the additive canonical_name column exists and round-trips; a
    new-entity proposal carries the faithful name with target_ref NULL."""
    async with pool.acquire() as conn:
        pid = await _seed_null_target(conn)
    repo = ProposalsRepo(pool)
    p = await repo.get(user_id=_USER, project_id=_PROJECT, proposal_id=pid)
    assert p is not None
    assert p.target_ref is None
    assert p.canonical_name == "昆侖虛"
    # the as_dict surface exposes it for the API layer.
    assert p.as_dict()["canonical_name"] == "昆侖虛"


async def test_set_writeback_entity_id_persists_and_is_idempotent(pool):
    """FIX-3 (DB): the additive writeback_entity_id column exists; the repo
    persists the resolved anchor id (NOT trigger-guarded, set in any state) and
    is idempotent (first write wins via COALESCE)."""
    async with pool.acquire() as conn:
        pid = await _seed(conn)
    repo = ProposalsRepo(pool)
    p0 = await repo.get(user_id=_USER, project_id=_PROJECT, proposal_id=pid)
    assert p0 is not None and p0.writeback_entity_id is None

    anchor = uuid.uuid4()
    p1 = await repo.set_writeback_entity_id(
        user_id=_USER, project_id=_PROJECT, proposal_id=pid, writeback_entity_id=anchor,
    )
    assert p1.writeback_entity_id == anchor
    # still NOT promoted — the H0 trigger did not reject this non-promotion write.
    assert p1.review_status == "proposed"
    assert p1.promoted_entity_id is None

    # idempotent: a second call with a different id keeps the first (COALESCE).
    p2 = await repo.set_writeback_entity_id(
        user_id=_USER, project_id=_PROJECT, proposal_id=pid, writeback_entity_id=uuid.uuid4(),
    )
    assert p2.writeback_entity_id == anchor
