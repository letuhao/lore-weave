"""F3 slice 5 — entity_canonical_snapshots repo against live Postgres.

Locks the §12.1 versioned-regenerable-cache contract:
  - upsert + valid-read round-trip,
  - staleness on newer fact coverage (rebuild-on-read, B3),
  - staleness on fold_algo_version bump (B0/F6),
  - re-fold at the same identity overwrites + resets failure state,
  - fold-failure backoff to 'unbuildable' at MAX_FOLD_ATTEMPTS (B4).

Skipped when no real KNOWLEDGE_DB_URL (the `pool` fixture skips).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.db.repositories.entity_canonical_snapshots import (
    MAX_FOLD_ATTEMPTS,
    EntityCanonicalSnapshotsRepo,
    snapshot_content_hash,
)

_NOW = datetime(2026, 6, 30, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_upsert_then_valid_read_roundtrip(pool):
    repo = EntityCanonicalSnapshotsRepo(pool)
    user, entity = uuid4(), f"ent-{uuid4().hex[:8]}"
    snap = await repo.upsert_snapshot(
        user_id=user, project_id=None, entity_id=entity,
        as_of_ordinal=500, content="who is this now",
        fold_algo_version=1, fact_coverage_at=_NOW,
    )
    assert snap.content_hash == snapshot_content_hash("who is this now")
    assert snap.canonical_status == "ready"
    # same coverage → cache HIT
    got = await repo.get_valid_snapshot(
        user_id=user, entity_id=entity, as_of_ordinal=500,
        fold_algo_version=1, current_fact_coverage_at=_NOW,
    )
    assert got is not None and got.content == "who is this now"


@pytest.mark.asyncio
async def test_newer_fact_coverage_invalidates_snapshot(pool):
    """A late / back-filled fact bumps the entity's max updated_at → the snapshot
    is stale → cache MISS → caller rebuilds from facts (B3 self-heal)."""
    repo = EntityCanonicalSnapshotsRepo(pool)
    user, entity = uuid4(), f"ent-{uuid4().hex[:8]}"
    await repo.upsert_snapshot(
        user_id=user, project_id=None, entity_id=entity,
        as_of_ordinal=500, content="v1", fold_algo_version=1,
        fact_coverage_at=_NOW,
    )
    # a fact arrived AFTER the snapshot's coverage → stale
    later = _NOW + timedelta(minutes=5)
    got = await repo.get_valid_snapshot(
        user_id=user, entity_id=entity, as_of_ordinal=500,
        fold_algo_version=1, current_fact_coverage_at=later,
    )
    assert got is None  # rebuild-on-read


@pytest.mark.asyncio
async def test_fold_algo_version_bump_invalidates(pool):
    """A strategy/prompt/model change bumps fold_algo_version → the old-version
    row is invalid → rebuild (B0/F6)."""
    repo = EntityCanonicalSnapshotsRepo(pool)
    user, entity = uuid4(), f"ent-{uuid4().hex[:8]}"
    await repo.upsert_snapshot(
        user_id=user, project_id=None, entity_id=entity,
        as_of_ordinal=500, content="v1", fold_algo_version=1,
        fact_coverage_at=_NOW,
    )
    # reading at the NEW algo version finds no row at that key → miss
    got = await repo.get_valid_snapshot(
        user_id=user, entity_id=entity, as_of_ordinal=500,
        fold_algo_version=2, current_fact_coverage_at=_NOW,
    )
    assert got is None


@pytest.mark.asyncio
async def test_refold_same_identity_overwrites_and_resets(pool):
    repo = EntityCanonicalSnapshotsRepo(pool)
    user, entity = uuid4(), f"ent-{uuid4().hex[:8]}"
    await repo.upsert_snapshot(
        user_id=user, project_id=None, entity_id=entity,
        as_of_ordinal=500, content="old", fold_algo_version=1,
        fact_coverage_at=_NOW,
    )
    later = _NOW + timedelta(minutes=10)
    snap2 = await repo.upsert_snapshot(
        user_id=user, project_id=None, entity_id=entity,
        as_of_ordinal=500, content="rebuilt", fold_algo_version=1,
        fact_coverage_at=later,
    )
    assert snap2.content == "rebuilt"
    assert snap2.fact_coverage_at == later
    assert snap2.canonical_status == "ready" and snap2.fold_attempts == 0


@pytest.mark.asyncio
async def test_fold_failure_backoff_to_unbuildable(pool):
    """A poison fact can't wedge an entity forever: after MAX_FOLD_ATTEMPTS
    failures the snapshot is quarantined 'unbuildable' and reads return None so
    the FE falls back to the structured facts (B4)."""
    repo = EntityCanonicalSnapshotsRepo(pool)
    user, entity = uuid4(), f"ent-{uuid4().hex[:8]}"
    status = None
    for _ in range(MAX_FOLD_ATTEMPTS):
        status = await repo.record_fold_failure(
            user_id=user, entity_id=entity, as_of_ordinal=500,
            fold_algo_version=1,
        )
    assert status == "unbuildable"
    # an unbuildable snapshot reads as None (caller degrades to facts)
    got = await repo.get_valid_snapshot(
        user_id=user, entity_id=entity, as_of_ordinal=500,
        fold_algo_version=1, current_fact_coverage_at=None,
    )
    assert got is None


@pytest.mark.asyncio
async def test_mark_dirty_flags_rows(pool):
    repo = EntityCanonicalSnapshotsRepo(pool)
    user, entity = uuid4(), f"ent-{uuid4().hex[:8]}"
    await repo.upsert_snapshot(
        user_id=user, project_id=None, entity_id=entity,
        as_of_ordinal=500, content="x", fold_algo_version=1,
        fact_coverage_at=_NOW,
    )
    n = await repo.mark_dirty(user_id=user, entity_id=entity)
    assert n == 1
    # a stale-by-status row is still 'dirty' → read at same coverage still HIT?
    # dirty is a re-fold hint, not an invalidation; the staleness check governs
    # validity. With unchanged coverage the row is still served.
    got = await repo.get_valid_snapshot(
        user_id=user, entity_id=entity, as_of_ordinal=500,
        fold_algo_version=1, current_fact_coverage_at=_NOW,
    )
    assert got is not None and got.canonical_status == "dirty"
