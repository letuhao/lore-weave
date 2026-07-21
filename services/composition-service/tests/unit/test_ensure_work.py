"""P5a — the consolidated canonical-first Work-ensure primitive (`work_resolution.ensure_work`).

Three divergent copies used to exist (plan_forge._ensure_work canonical-first; routers/works +
mcp/server pending-only). The pending-only ones were a latent F5 fork: a book that ALREADY has a
canonical marked Work would get a SECOND, pending Work minted (the two live under different
partial-unique indexes, so neither collides), and an EDIT-grantee's fork can never be backfilled
(knowledge create is owner-only). This locks the ONE primitive they now all route through — the
canonical-first invariant is the whole point, so it is the first test.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

from app.work_resolution import ensure_work


def _work(*, source_work_id=None, tag=""):
    return SimpleNamespace(source_work_id=source_work_id, id=uuid4(), _tag=tag)


@pytest.mark.asyncio
async def test_a_canonical_work_resolves_to_ITSELF_and_NEVER_forks_a_second_pending():
    """THE F5 fork this primitive kills. If a book has a canonical marked Work, ensure_work must return
    THAT — never fall through to create_pending (which would mint an un-backfillable fork)."""
    canonical = _work(source_work_id=None, tag="canonical")
    works = AsyncMock()
    works.resolve_by_book.return_value = [canonical]
    got = await ensure_work(works, uuid4(), created_by=uuid4())
    assert got is canonical
    works.create_pending.assert_not_called()          # never forked
    works.get_pending_for_book.assert_not_called()    # short-circuits before the pending branch


@pytest.mark.asyncio
async def test_a_marked_DERIVATIVE_is_not_mistaken_for_the_canonical():
    """resolve_by_book returns marked works; only the one with source_work_id IS NULL is canonical. A
    book whose only marked work is a derivative (source_work_id set) has NO canonical → fall to pending."""
    derivative = _work(source_work_id=uuid4(), tag="derivative")
    pending = _work(source_work_id=None, tag="pending")
    works = AsyncMock()
    works.resolve_by_book.return_value = [derivative]
    works.get_pending_for_book.return_value = pending
    got = await ensure_work(works, uuid4(), created_by=uuid4())
    assert got is pending
    works.create_pending.assert_not_called()


@pytest.mark.asyncio
async def test_no_canonical_returns_an_existing_pending_without_creating():
    pending = _work(source_work_id=None, tag="pending")
    works = AsyncMock()
    works.resolve_by_book.return_value = []            # no MARKED works
    works.get_pending_for_book.return_value = pending
    got = await ensure_work(works, uuid4(), created_by=uuid4())
    assert got is pending
    works.create_pending.assert_not_called()


@pytest.mark.asyncio
async def test_creates_a_pending_only_when_none_exists_stamping_created_by_as_actor():
    created = _work(source_work_id=None, tag="created")
    cb, bid = uuid4(), uuid4()
    works = AsyncMock()
    works.resolve_by_book.return_value = []
    works.get_pending_for_book.return_value = None
    works.create_pending.return_value = created
    got = await ensure_work(works, bid, created_by=cb)
    assert got is created
    works.create_pending.assert_awaited_once_with(cb, bid)  # created_by is a plain actor stamp (PM-9)


@pytest.mark.asyncio
async def test_a_create_RACE_re_gets_the_winners_pending_row_never_500s():
    """The partial-unique index caps pending at one per book, so a concurrent loser must re-get the
    winner's row (matching the index predicate) instead of raising."""
    raced = _work(source_work_id=None, tag="raced")
    works = AsyncMock()
    works.resolve_by_book.return_value = []
    works.get_pending_for_book.side_effect = [None, raced]  # first miss → create → re-get finds winner
    works.create_pending.side_effect = asyncpg.UniqueViolationError("duplicate key")
    got = await ensure_work(works, uuid4(), created_by=uuid4())
    assert got is raced


@pytest.mark.asyncio
async def test_a_truly_stuck_conflict_re_raises_so_the_caller_can_map_it():
    """If the race re-get finds NOTHING and no canonical appeared either, re-raise — the router maps
    this to 409, the MCP path to a ValueError; swallowing it would hide a real conflict."""
    works = AsyncMock()
    works.resolve_by_book.return_value = []
    works.get_pending_for_book.side_effect = [None, None]
    works.create_pending.side_effect = asyncpg.UniqueViolationError("duplicate key")
    with pytest.raises(asyncpg.UniqueViolationError):
        await ensure_work(works, uuid4(), created_by=uuid4())
