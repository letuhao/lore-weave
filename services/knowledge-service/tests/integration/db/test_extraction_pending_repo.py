"""K10.5 extraction_pending repository integration tests.

Coverage:
  - queue_event idempotency (duplicate event_id is no-op)
  - queue_event ownership gate (cross-user / nonexistent → None)
  - count_pending / fetch_pending FIFO ordering
  - fetch_pending only returns unprocessed rows
  - mark_processed transitions correctly + is no-op on re-mark
  - clear_pending deletes only unprocessed rows
  - cross-user defense-in-depth via JOIN on knowledge_projects
  - cascade delete from parent project
  - Pydantic validation rejects empty event_type / aggregate_type
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.db.models import ProjectCreate
from app.db.repositories.extraction_pending import (
    ExtractionPendingQueueRequest,
    ExtractionPendingRepo,
)
from app.db.repositories.projects import ProjectsRepo


# ── helpers ─────────────────────────────────────────────────────────────


async def _make_project(pool, user_id: UUID) -> UUID:
    repo = ProjectsRepo(pool)
    proj = await repo.create(
        user_id, ProjectCreate(name="K10.5 test", project_type="general")
    )
    return proj.project_id


def _request(
    project_id: UUID,
    *,
    event_id: UUID | None = None,
    event_type: str = "chapter.saved",
    aggregate_type: str = "chapter",
    aggregate_id: UUID | None = None,
) -> ExtractionPendingQueueRequest:
    return ExtractionPendingQueueRequest(
        project_id=project_id,
        event_id=event_id or uuid4(),
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id or uuid4(),
    )


# ── queue_event ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k10_5_queue_event_happy_path(pool):
    repo = ExtractionPendingRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)

    req = _request(project_id, event_type="chapter.saved", aggregate_type="chapter")
    row = await repo.queue_event(user, req)

    assert row is not None
    assert row.user_id == user
    assert row.project_id == project_id
    assert row.event_id == req.event_id
    assert row.event_type == "chapter.saved"
    assert row.aggregate_type == "chapter"
    assert row.aggregate_id == req.aggregate_id
    assert row.processed_at is None


@pytest.mark.asyncio
async def test_k10_5_queue_event_is_idempotent(pool):
    """K10.5 acceptance criterion: duplicate event_id is a no-op.
    Second queue with the same event_id must return the SAME row
    (same pending_id, same created_at) rather than inserting a
    second copy."""
    repo = ExtractionPendingRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)

    event_id = uuid4()
    req = _request(project_id, event_id=event_id)
    first = await repo.queue_event(user, req)
    assert first is not None

    # Same event_id — should return the SAME row, not a new one.
    second = await repo.queue_event(user, req)
    assert second is not None
    assert second.pending_id == first.pending_id
    assert second.created_at == first.created_at

    # Count is still 1.
    assert await repo.count_pending(user, project_id) == 1


@pytest.mark.asyncio
async def test_k10_5_queue_event_keeps_first_payload_on_duplicate(pool):
    """K10.5-I4: when a duplicate (project_id, event_id) call
    arrives with DIFFERENT event_type / aggregate_type / aggregate_id,
    the FIRST call's payload wins. event_id is sourced from
    `loreweave_events.event_log.id` which is supposed to be a
    globally-unique event identifier — two callers passing the
    same event_id with different payload data is a CALLER bug,
    not a queue concern. The repo silently keeps the first; this
    test documents and locks the behaviour."""
    repo = ExtractionPendingRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)

    event_id = uuid4()
    first_agg = uuid4()
    second_agg = uuid4()
    first = await repo.queue_event(
        user,
        ExtractionPendingQueueRequest(
            project_id=project_id,
            event_id=event_id,
            event_type="chapter.saved",
            aggregate_type="chapter",
            aggregate_id=first_agg,
        ),
    )
    assert first is not None
    assert first.event_type == "chapter.saved"
    assert first.aggregate_id == first_agg

    # Second call with same event_id, completely different payload.
    second = await repo.queue_event(
        user,
        ExtractionPendingQueueRequest(
            project_id=project_id,
            event_id=event_id,
            event_type="chapter.deleted",
            aggregate_type="paragraph",
            aggregate_id=second_agg,
        ),
    )
    # Same row returned, FIRST payload preserved.
    assert second is not None
    assert second.pending_id == first.pending_id
    assert second.event_type == "chapter.saved"  # NOT chapter.deleted
    assert second.aggregate_type == "chapter"  # NOT paragraph
    assert second.aggregate_id == first_agg  # NOT second_agg

    # Count is still 1.
    assert await repo.count_pending(user, project_id) == 1


@pytest.mark.asyncio
async def test_k10_5_queue_event_unknown_project_returns_none(pool):
    repo = ExtractionPendingRepo(pool)
    user = uuid4()
    bogus_project = uuid4()  # does not exist in knowledge_projects
    row = await repo.queue_event(user, _request(bogus_project))
    assert row is None
    assert await repo.count_pending(user, bogus_project) == 0


@pytest.mark.asyncio
async def test_k10_5_queue_event_cross_user_returns_none(pool):
    """User B cannot queue an event into User A's project even with
    a valid project_id. The CTE's `WHERE EXISTS (SELECT 1 FROM
    knowledge_projects WHERE user_id = $1 AND ...)` short-circuits
    the INSERT to zero rows."""
    repo = ExtractionPendingRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    project_a = await _make_project(pool, user_a)

    row = await repo.queue_event(user_b, _request(project_a))
    assert row is None
    # A's queue is still empty — no orphan row planted.
    assert await repo.count_pending(user_a, project_a) == 0


# ── count_pending / fetch_pending ───────────────────────────────────────


@pytest.mark.asyncio
async def test_k10_5_count_pending_filters_processed(pool):
    """count_pending counts only rows where processed_at IS NULL."""
    repo = ExtractionPendingRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)

    # Queue 3 events.
    rows = []
    for _ in range(3):
        r = await repo.queue_event(user, _request(project_id))
        assert r is not None
        rows.append(r)

    assert await repo.count_pending(user, project_id) == 3

    # Process one — count drops.
    assert await repo.mark_processed(user, rows[0].pending_id) is True
    assert await repo.count_pending(user, project_id) == 2


@pytest.mark.asyncio
async def test_k10_5_count_pending_cross_user_returns_zero(pool):
    """User B asking about User A's project gets 0 — no information
    leak, no error message."""
    repo = ExtractionPendingRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    project_a = await _make_project(pool, user_a)
    await repo.queue_event(user_a, _request(project_a))
    await repo.queue_event(user_a, _request(project_a))

    assert await repo.count_pending(user_a, project_a) == 2
    assert await repo.count_pending(user_b, project_a) == 0


@pytest.mark.asyncio
async def test_k10_5_fetch_pending_fifo_order(pool):
    """K10.5 acceptance criterion: fetch returns in created_at
    order. We seed with explicit small sleeps to ensure the
    timestamps are distinct, then verify the order is preserved."""
    import asyncio

    repo = ExtractionPendingRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)

    queued = []
    for _ in range(5):
        r = await repo.queue_event(user, _request(project_id))
        queued.append(r)
        # Tiny sleep to guarantee distinct created_at even at
        # microsecond resolution.
        await asyncio.sleep(0.001)

    fetched = await repo.fetch_pending(user, project_id)
    assert [f.pending_id for f in fetched] == [q.pending_id for q in queued]


@pytest.mark.asyncio
async def test_k10_5_fetch_pending_respects_limit(pool):
    repo = ExtractionPendingRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    for _ in range(10):
        await repo.queue_event(user, _request(project_id))

    page = await repo.fetch_pending(user, project_id, limit=3)
    assert len(page) == 3


@pytest.mark.asyncio
async def test_k10_5_fetch_pending_excludes_processed(pool):
    repo = ExtractionPendingRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)

    rows = []
    for _ in range(4):
        rows.append(await repo.queue_event(user, _request(project_id)))

    # Process the first 2.
    await repo.mark_processed(user, rows[0].pending_id)
    await repo.mark_processed(user, rows[1].pending_id)

    pending = await repo.fetch_pending(user, project_id)
    assert len(pending) == 2
    pending_ids = {p.pending_id for p in pending}
    assert pending_ids == {rows[2].pending_id, rows[3].pending_id}


@pytest.mark.asyncio
async def test_k10_5_fetch_pending_cross_user_returns_empty(pool):
    """Defense-in-depth: even if extraction_pending.user_id somehow
    drifts, the JOIN through knowledge_projects keeps cross-user
    reads empty."""
    repo = ExtractionPendingRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    project_a = await _make_project(pool, user_a)
    await repo.queue_event(user_a, _request(project_a))

    assert await repo.fetch_pending(user_b, project_a) == []


# ── mark_processed ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k10_5_mark_processed_happy_path(pool):
    repo = ExtractionPendingRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    row = await repo.queue_event(user, _request(project_id))
    assert row is not None

    assert await repo.mark_processed(user, row.pending_id) is True
    # Verify by re-fetching: row is gone from pending list.
    assert await repo.count_pending(user, project_id) == 0


@pytest.mark.asyncio
async def test_k10_5_mark_processed_is_idempotent(pool):
    """Re-marking an already-processed row returns False (no row
    transitioned). Audit-trail-friendly: the first processed_at
    timestamp is not overwritten on the second call."""
    repo = ExtractionPendingRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    row = await repo.queue_event(user, _request(project_id))
    assert row is not None

    assert await repo.mark_processed(user, row.pending_id) is True
    # Second call: already processed → no-op → False.
    assert await repo.mark_processed(user, row.pending_id) is False


@pytest.mark.asyncio
async def test_k10_5_mark_processed_cross_user_returns_false(pool):
    """User B cannot mark User A's row processed. The JOIN through
    knowledge_projects gates the UPDATE."""
    repo = ExtractionPendingRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    project_a = await _make_project(pool, user_a)
    row = await repo.queue_event(user_a, _request(project_a))
    assert row is not None

    assert await repo.mark_processed(user_b, row.pending_id) is False
    # Row still unprocessed for A.
    assert await repo.count_pending(user_a, project_a) == 1


@pytest.mark.asyncio
async def test_k10_5_mark_processed_nonexistent_returns_false(pool):
    repo = ExtractionPendingRepo(pool)
    user = uuid4()
    assert await repo.mark_processed(user, uuid4()) is False


# ── clear_pending ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k10_5_clear_pending_removes_unprocessed(pool):
    repo = ExtractionPendingRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)
    for _ in range(5):
        await repo.queue_event(user, _request(project_id))

    deleted = await repo.clear_pending(user, project_id)
    assert deleted == 5
    assert await repo.count_pending(user, project_id) == 0


@pytest.mark.asyncio
async def test_k10_5_clear_pending_preserves_processed_audit_rows(pool):
    """clear_pending only deletes WHERE processed_at IS NULL — the
    audit trail of already-processed events stays so the worker's
    history is preserved."""
    repo = ExtractionPendingRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)

    rows = []
    for _ in range(4):
        rows.append(await repo.queue_event(user, _request(project_id)))
    # Process 2.
    await repo.mark_processed(user, rows[0].pending_id)
    await repo.mark_processed(user, rows[1].pending_id)

    deleted = await repo.clear_pending(user, project_id)
    assert deleted == 2  # only the 2 unprocessed

    # Audit rows still exist (count_pending excludes them but they're
    # in the table).
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM extraction_pending WHERE project_id = $1",
            project_id,
        )
    assert total == 2


@pytest.mark.asyncio
async def test_k10_5_clear_pending_cross_user_returns_zero(pool):
    repo = ExtractionPendingRepo(pool)
    user_a = uuid4()
    user_b = uuid4()
    project_a = await _make_project(pool, user_a)
    await repo.queue_event(user_a, _request(project_a))

    deleted = await repo.clear_pending(user_b, project_a)
    assert deleted == 0
    # A's queue is intact.
    assert await repo.count_pending(user_a, project_a) == 1


# ── cascade delete ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k10_5_cascade_delete_cleans_pending_rows(pool):
    """ON DELETE CASCADE on the project_id FK: deleting the parent
    project removes all extraction_pending rows automatically.
    K7d /v1/knowledge/user-data delete relies on this to fully
    purge a user's queue state."""
    repo = ExtractionPendingRepo(pool)
    projects_repo = ProjectsRepo(pool)
    user = uuid4()
    project_id = await _make_project(pool, user)

    for _ in range(3):
        await repo.queue_event(user, _request(project_id))
    assert await repo.count_pending(user, project_id) == 3

    await projects_repo.delete(user, project_id)
    # Direct SQL count to bypass the JOIN (which would also return 0
    # because the project no longer exists).
    async with pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM extraction_pending WHERE project_id = $1",
            project_id,
        )
    assert n == 0


# ── Pydantic field validation (no DB needed) ────────────────────────────


def test_k10_5_queue_request_rejects_empty_event_type():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ExtractionPendingQueueRequest(
            project_id=uuid4(),
            event_id=uuid4(),
            event_type="",
            aggregate_type="chapter",
            aggregate_id=uuid4(),
        )


def test_k10_5_queue_request_rejects_empty_aggregate_type():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ExtractionPendingQueueRequest(
            project_id=uuid4(),
            event_id=uuid4(),
            event_type="chapter.saved",
            aggregate_type="",
            aggregate_id=uuid4(),
        )


def test_k10_5_queue_request_rejects_oversized_event_type():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ExtractionPendingQueueRequest(
            project_id=uuid4(),
            event_id=uuid4(),
            event_type="x" * 101,
            aggregate_type="chapter",
            aggregate_id=uuid4(),
        )
