"""E0-3 access-gate deny tests — the executable guard on resolve-to-owner.

These exercise the REAL dependency logic (require_project_grant / require_book_grant
/ require_job_grant) by calling the inner dep with a stubbed (owner, book_id) meta
and a stub grant client, so the route→need mapping and the anti-oracle behavior are
verified without a DB or book-service:

  - owner (caller==owner) passes at every tier and the repo runs as the owner;
  - a collaborator >= need passes and the dep returns the OWNER (resolve-to-owner);
  - a collaborator < need → 403; a non-grantee → 404; a book-less project for a
    non-owner → 404; a missing project/job → 404.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth.grant_deps import (
    GrantLevel,
    require_book_grant,
    require_job_grant,
    require_project_grant,
)


class _GC:
    """Stub grant client returning a fixed level for any (book, user)."""

    def __init__(self, level: GrantLevel):
        self._level = level

    async def resolve_grant(self, book_id, user_id):
        return self._level


async def _call_project(need, *, meta, caller, level):
    dep = require_project_grant(need)
    return await dep(meta=meta, caller=caller, gc=_GC(level))


async def _call_job(need, *, meta, caller, level):
    dep = require_job_grant(need)
    return await dep(meta=meta, caller=caller, gc=_GC(level))


# ── owner path (caller == project owner) ─────────────────────────────

@pytest.mark.asyncio
async def test_owner_passes_every_tier_and_returns_owner():
    owner = uuid4()
    for need in (GrantLevel.VIEW, GrantLevel.EDIT, GrantLevel.MANAGE, GrantLevel.OWNER):
        # grant client level is irrelevant for the owner (caller==owner short-circuit).
        got = await _call_project(need, meta=(owner, uuid4()), caller=owner, level=GrantLevel.NONE)
        assert got == owner


# ── collaborator path (resolve-to-owner) ─────────────────────────────

@pytest.mark.asyncio
async def test_collaborator_at_or_above_need_returns_owner():
    owner, caller, book = uuid4(), uuid4(), uuid4()
    # edit-grantee on an edit route → returns the OWNER (repo runs as owner).
    got = await _call_project(GrantLevel.EDIT, meta=(owner, book), caller=caller, level=GrantLevel.EDIT)
    assert got == owner
    # manage-grantee satisfies a view/edit/manage route.
    for need in (GrantLevel.VIEW, GrantLevel.EDIT, GrantLevel.MANAGE):
        got = await _call_project(need, meta=(owner, book), caller=caller, level=GrantLevel.MANAGE)
        assert got == owner


@pytest.mark.asyncio
async def test_collaborator_under_tier_is_403():
    owner, caller, book = uuid4(), uuid4(), uuid4()
    # view-grantee on an edit route, edit-grantee on manage, manage-grantee on owner.
    for need, held in [
        (GrantLevel.EDIT, GrantLevel.VIEW),
        (GrantLevel.MANAGE, GrantLevel.EDIT),
        (GrantLevel.OWNER, GrantLevel.MANAGE),
    ]:
        with pytest.raises(HTTPException) as ei:
            await _call_project(need, meta=(owner, book), caller=caller, level=held)
        assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_non_grantee_is_404_not_403():
    owner, caller, book = uuid4(), uuid4(), uuid4()
    # `none` collapses to 404 (no existence oracle) at every tier.
    for need in (GrantLevel.VIEW, GrantLevel.EDIT, GrantLevel.MANAGE, GrantLevel.OWNER):
        with pytest.raises(HTTPException) as ei:
            await _call_project(need, meta=(owner, book), caller=caller, level=GrantLevel.NONE)
        assert ei.value.status_code == 404


# ── book-less project → owner-only fallback (R1) ─────────────────────

@pytest.mark.asyncio
async def test_book_less_project_is_owner_only():
    owner, caller = uuid4(), uuid4()
    # owner still passes...
    assert await _call_project(GrantLevel.VIEW, meta=(owner, None), caller=owner, level=GrantLevel.OWNER) == owner
    # ...but a non-owner gets 404 with no book to resolve a grant on, even though the
    # stub grant client would have said OWNER (the gate must not consult it).
    with pytest.raises(HTTPException) as ei:
        await _call_project(GrantLevel.VIEW, meta=(owner, None), caller=caller, level=GrantLevel.OWNER)
    assert ei.value.status_code == 404


# ── missing project / job → 404 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_project_is_404():
    with pytest.raises(HTTPException) as ei:
        await _call_project(GrantLevel.VIEW, meta=None, caller=uuid4(), level=GrantLevel.OWNER)
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_missing_job_is_404():
    with pytest.raises(HTTPException) as ei:
        await _call_job(GrantLevel.VIEW, meta=None, caller=uuid4(), level=GrantLevel.OWNER)
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_job_collaborator_returns_owner():
    owner, caller, book = uuid4(), uuid4(), uuid4()
    got = await _call_job(GrantLevel.VIEW, meta=(owner, book), caller=caller, level=GrantLevel.VIEW)
    assert got == owner


# ── book-scoped gate (raw-search) ────────────────────────────────────

@pytest.mark.asyncio
async def test_require_book_grant_tiers():
    book, caller = uuid4(), uuid4()
    dep = require_book_grant(GrantLevel.VIEW)
    # >= view → returns caller (book-scoped routes don't owner-substitute)
    assert await dep(book_id=book, caller=caller, gc=_GC(GrantLevel.VIEW)) == caller
    # none → 404
    with pytest.raises(HTTPException) as ei:
        await dep(book_id=book, caller=caller, gc=_GC(GrantLevel.NONE))
    assert ei.value.status_code == 404
    # under tier → 403
    dep_edit = require_book_grant(GrantLevel.EDIT)
    with pytest.raises(HTTPException) as ei:
        await dep_edit(book_id=book, caller=caller, gc=_GC(GrantLevel.VIEW))
    assert ei.value.status_code == 403
