"""C17 — unit tests for the entity_alias_map backfill helper.

Covers ``run_backfill``'s contract:
  - happy path: inserts rows for every non-canonical alias
  - skips entity's own canonical_name (implicit redirect via id)
  - skips empty canonical_alias (defensive — extraction shouldn't
    produce these but a stray honorific-only alias would)
  - idempotent re-run (second sweep over same data inserts 0)
  - per-entity invalid user_id is counted as errored, doesn't abort

CLI shim (``_cli_main``) deliberately not unit-tested — it constructs
real pool + Neo4j session; coverage lives in ``run_backfill``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.db.migrations.backfill_entity_alias_map import run_backfill
from app.db.repositories.entity_alias_map import EntityAliasMapRepo


def _entity_record(
    user_id: str,
    project_id: str | None,
    kind: str,
    canonical_name: str,
    aliases: list[str],
    target_entity_id: str,
) -> MagicMock:
    """Mock Neo4j record matching the BACKFILL_LIST_ENTITIES Cypher
    RETURN shape (subscript access only — no .get())."""
    rec = MagicMock()
    data = {
        "user_id": user_id,
        "project_id": project_id,
        "kind": kind,
        "canonical_name": canonical_name,
        "aliases": aliases,
        "target_entity_id": target_entity_id,
    }
    rec.__getitem__.side_effect = lambda k: data[k]
    rec.get.side_effect = lambda k, default=None: data.get(k, default)
    return rec


def _make_session(records: list[MagicMock]) -> MagicMock:
    """Neo4j session whose run() returns an async iterator over the
    supplied record list. Mirrors the shape of run_read()'s result."""

    async def _async_iter():
        for r in records:
            yield r

    async def _run(_cypher, **_params):
        return _async_iter()

    session = MagicMock()
    session.run = _run
    return session


class _FakeRepo:
    """Minimal async-pool-free repo stub. Records bulk_backfill calls
    + emulates ON CONFLICT DO NOTHING semantics in Python so re-run
    idempotency can be asserted."""

    def __init__(self) -> None:
        self.store: set[tuple] = set()
        self.bulk_calls: list[list] = []

    async def bulk_backfill(self, rows) -> int:
        rows_list = list(rows)
        self.bulk_calls.append(rows_list)
        inserted = 0
        for r in rows_list:
            key = r[:4]  # (user_id, project_scope, kind, canonical_alias)
            if key in self.store:
                continue
            self.store.add(key)
            inserted += 1
        return inserted


@pytest.mark.asyncio
async def test_run_backfill_inserts_rows_for_aliases():
    user = str(uuid4())
    records = [
        _entity_record(
            user_id=user, project_id=None, kind="person",
            canonical_name="kai",
            aliases=["Kai", "Master Kai", "kai-shifu"],
            target_entity_id="tgt1",
        ),
    ]
    session = _make_session(records)
    repo = _FakeRepo()

    result = await run_backfill(repo, session)  # type: ignore[arg-type]

    assert result.total_entities == 1
    # "Kai" + "Master Kai" + "kai-shifu" all canonicalize to "kai" =
    # entity's own canonical_name → all three skipped as canonical.
    assert result.skipped_canonical == 3
    assert result.inserted == 0


@pytest.mark.asyncio
async def test_run_backfill_inserts_distinct_aliases():
    """Two aliases that canonicalize to DIFFERENT strings (and
    different from canonical_name) → 2 inserts. Note: 'Captain '
    is an honorific so canonicalize_entity_name('Captain Brave')
    → 'brave', which we therefore use as the entity's canonical_name."""
    user = str(uuid4())
    records = [
        _entity_record(
            user_id=user, project_id="proj1", kind="person",
            canonical_name="brave",  # post-honorific-strip canonical
            aliases=["Captain Brave", "Alice", "Lex"],
            target_entity_id="tgt_brave",
        ),
    ]
    session = _make_session(records)
    repo = _FakeRepo()

    result = await run_backfill(repo, session)  # type: ignore[arg-type]

    assert result.inserted == 2  # "alice" + "lex" (Captain Brave skipped)
    assert result.skipped_canonical == 1
    keys = {r[:4] for r in repo.bulk_calls[0]}
    from uuid import UUID
    assert (UUID(user), "proj1", "person", "alice") in keys
    assert (UUID(user), "proj1", "person", "lex") in keys


@pytest.mark.asyncio
async def test_run_backfill_skips_empty_canonical_alias():
    """Alias that canonicalizes to '' (pure whitespace or pure
    punctuation) is counted as skipped_empty, not inserted."""
    user = str(uuid4())
    records = [
        _entity_record(
            user_id=user, project_id=None, kind="person",
            canonical_name="kai",
            # "Kai" → "kai" (canonical-match)
            # "   " → "" (empty)
            # "***" → "" (punctuation strip)
            aliases=["Kai", "   ", "***"],
            target_entity_id="tgt1",
        ),
    ]
    session = _make_session(records)
    repo = _FakeRepo()
    result = await run_backfill(repo, session)  # type: ignore[arg-type]

    assert result.skipped_empty == 2
    assert result.skipped_canonical == 1
    assert result.inserted == 0


@pytest.mark.asyncio
async def test_run_backfill_idempotent_on_rerun():
    """Re-running the backfill on an already-populated table inserts 0
    new rows. Supports interrupted-and-restarted backfill runs."""
    user = str(uuid4())
    records = [
        _entity_record(
            user_id=user, project_id=None, kind="person",
            canonical_name="captain brave",
            aliases=["Alice", "Lex"],
            target_entity_id="tgt1",
        ),
    ]
    repo = _FakeRepo()

    # First sweep — fresh inserts.
    result1 = await run_backfill(
        repo, _make_session(records),  # type: ignore[arg-type]
    )
    assert result1.inserted == 2

    # Second sweep — same data, all dups.
    result2 = await run_backfill(
        repo, _make_session(records),  # type: ignore[arg-type]
    )
    assert result2.inserted == 0
    assert result2.total_entities == 1


@pytest.mark.asyncio
async def test_run_backfill_invalid_user_id_counted_as_errored():
    """A corrupted entity (e.g. user_id is None) is logged +
    incremented in errored_entities; sweep continues with the next
    entity."""
    good_user = str(uuid4())
    records = [
        _entity_record(
            user_id="not-a-uuid", project_id=None, kind="person",
            canonical_name="x", aliases=["Y"], target_entity_id="bad",
        ),
        _entity_record(
            user_id=good_user, project_id=None, kind="person",
            canonical_name="captain brave",
            aliases=["Alice"], target_entity_id="tgt_brave",
        ),
    ]
    session = _make_session(records)
    repo = _FakeRepo()
    result = await run_backfill(repo, session)  # type: ignore[arg-type]

    assert result.total_entities == 2
    assert result.errored_entities == 1
    assert result.inserted == 1  # only the good user's alias landed
