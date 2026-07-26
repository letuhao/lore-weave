"""25-T4 — derivative-separation: a book-scoped agent read resolves the CANONICAL Work,
never a derivative.

The tenancy bug this guards (DR-B): `agent_native.resolve_scope` took `marked[0]` — the
FIRST Work by `created_at` — instead of the one whose `source_work_id IS NULL`. Normally
the canonical is created first, so `marked[0]` is incidentally right. But archive-and-
recreate is permitted (PM-4's partial unique only forbids TWO live canonicals): archive the
canonical, and a derivative that already exists now PREDATES the recreated canonical. Then
`resolve_by_book` (ORDER BY created_at) returns `[derivative, canonical]`, `marked[0]` is the
derivative, and all three agent reads (package_tree / diagnostics / find_references) serve the
derivative's spec, tests, lock and runs as the book's.

28 §AN-2 (28:502-510) makes the canonical predicate (`source_work_id IS NULL AND active`)
NORMATIVE. This test reds on the pre-fix `marked[0]` and greens once resolve_scope uses the
existing `resolve_canonical_work` helper. It is 25-T4, the battery whose absence let the bug
ship (there was no test asserting canonical-only READ resolution).
"""
from __future__ import annotations

import types
from uuid import uuid4

import pytest

from app.services.agent_native import resolve_scope


class _FakeWorks:
    """Only the two methods resolve_scope calls."""

    def __init__(self, marked, pending=None):
        self._marked = marked
        self._pending = pending

    async def resolve_by_book(self, book_id):
        return self._marked

    async def get_pending_for_book(self, book_id):
        return self._pending


def _work(source_work_id):
    return types.SimpleNamespace(id=uuid4(), project_id=uuid4(), source_work_id=source_work_id)


@pytest.mark.asyncio
async def test_resolve_scope_picks_canonical_not_a_preceding_derivative():
    canonical = _work(source_work_id=None)
    derivative = _work(source_work_id=canonical.id)
    # Archive-and-recreate ordering: the older derivative sorts FIRST, then the recreated
    # canonical — exactly what `resolve_by_book`'s ORDER BY created_at yields. marked[0] is
    # the derivative, which is the whole bug.
    marked = [derivative, canonical]

    work, project_id = await resolve_scope(_FakeWorks(marked), uuid4())

    assert work is canonical, (
        "resolve_scope served a DERIVATIVE's spec as the book's — the marked[0] tenancy bug"
    )
    assert project_id == (canonical.project_id or canonical.id)


@pytest.mark.asyncio
async def test_resolve_scope_single_canonical_unchanged():
    canonical = _work(source_work_id=None)
    work, project_id = await resolve_scope(_FakeWorks([canonical]), uuid4())
    assert work is canonical
    assert project_id == (canonical.project_id or canonical.id)


@pytest.mark.asyncio
async def test_resolve_scope_no_marked_falls_through_to_pending():
    # A pending (null-project) Work is not marked; resolve_scope must still return it by its
    # surrogate id (the C16 fall-through), never deny a real-but-unbackfilled book.
    pending = _work(source_work_id=None)
    pending.project_id = None
    work, project_id = await resolve_scope(_FakeWorks([], pending=pending), uuid4())
    assert work is pending
    assert project_id == pending.id
