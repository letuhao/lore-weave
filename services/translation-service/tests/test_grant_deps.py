"""E0-4a gate unit tests — the executable guard on the book-grant chokepoint.

Exercises ``authorize_book`` (the single resolve→404/403→caller chokepoint) and
the ``require_book_grant`` dependency directly with a stub grant client, so the
anti-oracle behavior (none→404, under-tier→403, ≥need→pass returns caller) is
verified without a DB or book-service.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.grant_deps import (
    GrantLevel,
    authorize_book,
    clamp_effort_to_grant,
    require_book_grant,
)


# ── RE-Q11: effort-auth grant ceiling (spend authorization, the HIGH finding) ──


def test_clamp_effort_ceilings_by_grant():
    # View → none (can't spend any reasoning budget).
    assert clamp_effort_to_grant("high", int(GrantLevel.VIEW)) == ("none", True)
    # Edit caps at medium — a high request is CLAMPED (the escalation the finding kills).
    assert clamp_effort_to_grant("high", int(GrantLevel.EDIT)) == ("medium", True)
    assert clamp_effort_to_grant("medium", int(GrantLevel.EDIT)) == ("medium", False)
    assert clamp_effort_to_grant("low", int(GrantLevel.EDIT)) == ("low", False)
    # Manage / Owner → high allowed.
    assert clamp_effort_to_grant("high", int(GrantLevel.MANAGE)) == ("high", False)
    assert clamp_effort_to_grant("high", int(GrantLevel.OWNER)) == ("high", False)


def test_clamp_effort_normalizes_inputs():
    # "off"/unknown/empty → "none"; never raises on junk grant ints.
    assert clamp_effort_to_grant("off", int(GrantLevel.OWNER)) == ("none", False)
    assert clamp_effort_to_grant("garbage", int(GrantLevel.OWNER)) == ("none", False)
    assert clamp_effort_to_grant(None, int(GrantLevel.EDIT)) == ("none", False)
    assert clamp_effort_to_grant("high", 999)[0] == "none"  # unknown grant → fail-closed
    assert clamp_effort_to_grant("high", int(GrantLevel.NONE)) == ("none", True)


class _GC:
    def __init__(self, level):
        self._level = level

    async def resolve_grant(self, book_id, user_id):
        return self._level


@pytest.mark.asyncio
async def test_authorize_book_returns_caller_when_at_or_above_need():
    caller, book = uuid4(), uuid4()
    got = await authorize_book(_GC(GrantLevel.EDIT), book, caller, GrantLevel.EDIT)
    assert got == caller  # caller-attributed (NOT resolve-to-owner)
    # manage satisfies a view/edit/manage route
    for need in (GrantLevel.VIEW, GrantLevel.EDIT, GrantLevel.MANAGE):
        assert await authorize_book(_GC(GrantLevel.MANAGE), book, caller, need) == caller


@pytest.mark.asyncio
async def test_authorize_book_none_is_404():
    for need in (GrantLevel.VIEW, GrantLevel.EDIT, GrantLevel.MANAGE):
        with pytest.raises(HTTPException) as ei:
            await authorize_book(_GC(GrantLevel.NONE), uuid4(), uuid4(), need)
        assert ei.value.status_code == 404  # uniform anti-oracle


@pytest.mark.asyncio
async def test_authorize_book_under_tier_is_403():
    for need, held in [
        (GrantLevel.EDIT, GrantLevel.VIEW),
        (GrantLevel.MANAGE, GrantLevel.EDIT),
    ]:
        with pytest.raises(HTTPException) as ei:
            await authorize_book(_GC(held), uuid4(), uuid4(), need)
        assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_require_book_grant_dep_passes_and_returns_caller():
    caller, book = uuid4(), uuid4()
    dep = require_book_grant(GrantLevel.VIEW)
    got = await dep(book_id=book, caller=str(caller), gc=_GC(GrantLevel.VIEW))
    assert got == caller


@pytest.mark.asyncio
async def test_require_book_grant_dep_denies():
    dep = require_book_grant(GrantLevel.EDIT)
    with pytest.raises(HTTPException) as ei:  # no grant → 404
        await dep(book_id=uuid4(), caller=str(uuid4()), gc=_GC(GrantLevel.NONE))
    assert ei.value.status_code == 404
    with pytest.raises(HTTPException) as ei:  # under edit → 403
        await dep(book_id=uuid4(), caller=str(uuid4()), gc=_GC(GrantLevel.VIEW))
    assert ei.value.status_code == 403
