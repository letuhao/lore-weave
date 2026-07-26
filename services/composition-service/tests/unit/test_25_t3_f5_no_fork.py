"""25-T3 — grantee-widening / the F5 zero-pending-forks regression.

PM-9 (spec 25) claims *"the F5 fork bug dies structurally"*: an EDIT-grantee B running
PlanForge on a book the owner A already has a canonical Work for must ATTACH to A's
canonical Work, never fork a private pending Work of its own (which knowledge-create,
owner-only, could then never backfill). `_ensure_work` was rewritten to be caller-
INDEPENDENT for exactly this — and **nothing tested it** (the load-bearing claim with
zero coverage, this run's audit found).

This pins the composition-side mechanism by EFFECT: called AS B, `_ensure_work` returns
A's canonical and creates NOTHING (create_pending is never called). The live grantee-
through-MCP leg (a real EDIT grant across the gateway + book-service) is the cross-
service half, parked under §7 P-CONC while those services are concurrently owned.
"""
from __future__ import annotations

import types
from uuid import uuid4

import pytest

from app.services.plan_forge_service import PlanForgeService


class _FakeWorks:
    """Caller-INDEPENDENT resolve (no user_id param) — the de-user'd repo (PM-9)."""

    def __init__(self, marked, pending=None):
        self._marked = list(marked)
        self._pending = pending
        self.create_calls = 0

    async def resolve_by_book(self, book_id):
        return list(self._marked)

    async def get_pending_for_book(self, book_id):
        return self._pending

    async def create_pending(self, created_by, book_id):
        self.create_calls += 1
        return types.SimpleNamespace(
            id=uuid4(), project_id=None, source_work_id=None, created_by=created_by
        )


class _Svc:
    """Stand-in self — `_ensure_work` touches only `self._works`."""

    def __init__(self, works):
        self._works = works


def _work(created_by, source_work_id):
    return types.SimpleNamespace(
        id=uuid4(), project_id=uuid4(), source_work_id=source_work_id, created_by=created_by
    )


@pytest.mark.asyncio
async def test_grantee_B_attaches_to_owner_canonical_zero_forks():
    owner_a = uuid4()
    grantee_b = uuid4()
    canonical = _work(created_by=owner_a, source_work_id=None)
    works = _FakeWorks([canonical])

    got = await PlanForgeService._ensure_work(_Svc(works), uuid4(), created_by=grantee_b)

    assert got is canonical, "grantee B did not attach to the owner's canonical Work (F5 fork)"
    assert got.created_by == owner_a, "the resolved Work must stay the owner's, not B's"
    assert works.create_calls == 0, "B forked a pending Work — the exact F5 regression"


@pytest.mark.asyncio
async def test_canonical_chosen_regardless_of_created_at_order():
    # A derivative that sorts before the canonical must NOT be picked (mirrors 25-T4).
    owner_a = uuid4()
    canonical = _work(created_by=owner_a, source_work_id=None)
    derivative = _work(created_by=owner_a, source_work_id=canonical.id)
    works = _FakeWorks([derivative, canonical])

    got = await PlanForgeService._ensure_work(_Svc(works), uuid4(), created_by=uuid4())
    assert got is canonical
    assert works.create_calls == 0


@pytest.mark.asyncio
async def test_creates_a_pending_only_when_no_marked_or_pending_exists():
    b = uuid4()
    works = _FakeWorks([], pending=None)
    got = await PlanForgeService._ensure_work(_Svc(works), uuid4(), created_by=b)
    assert works.create_calls == 1, "a genuinely unplanned book should mint exactly one pending Work"
    assert got.created_by == b, "the fresh pending Work is stamped with the acting caller (attribution)"
