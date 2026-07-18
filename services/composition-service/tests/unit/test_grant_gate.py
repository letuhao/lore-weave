"""E0-4c — composition collaboration gate (authorize_book + works-router tiers).

Proves the book-grant chokepoint: none → 404 (OwnershipError, no oracle),
grantee-under-tier → 403 (InsufficientGrant), at/above tier → allowed. The works
router maps these and enforces read=VIEW / write=EDIT; composition_work is
BOOK-scoped (25 PM-9) — access is decided at this E0 book-grant gate, never in
the repo (which no longer filters on the actor).
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import CompositionWork
from app.grant_client import GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.packer.pack import OwnershipError

USER, PROJECT, BOOK = uuid4(), uuid4(), uuid4()


class _Grant:
    def __init__(self, level):
        self._level = level
    async def resolve_grant(self, book_id, user_id):
        return self._level
    async def resolve_access(self, book_id, user_id):
        return self._level, "active"


# ── authorize_book (pure) ─────────────────────────────────────────────


async def test_authorize_book_none_raises_ownership_404():
    with pytest.raises(OwnershipError):
        await authorize_book(_Grant(GrantLevel.NONE), BOOK, USER, GrantLevel.VIEW)


async def test_authorize_book_under_tier_raises_insufficient_403():
    # view-grantee on an edit operation.
    with pytest.raises(InsufficientGrant):
        await authorize_book(_Grant(GrantLevel.VIEW), BOOK, USER, GrantLevel.EDIT)


@pytest.mark.parametrize("held,need", [
    (GrantLevel.VIEW, GrantLevel.VIEW),
    (GrantLevel.EDIT, GrantLevel.VIEW),
    (GrantLevel.EDIT, GrantLevel.EDIT),
    (GrantLevel.OWNER, GrantLevel.EDIT),
])
async def test_authorize_book_at_or_above_tier_ok(held, need):
    lvl = await authorize_book(_Grant(held), BOOK, USER, need)
    assert lvl == held


# ── works router tier enforcement (TestClient) ───────────────────────


def _work():
    return CompositionWork(project_id=PROJECT, created_by=USER, book_id=BOOK, version=1)


def _client(level, *, work=None):
    from app.main import app
    from app.deps import (
        get_book_client_dep, get_grant_client_dep,
        get_knowledge_client_dep, get_works_repo,
    )
    from app.middleware.jwt_auth import get_bearer_token, get_current_user

    works = AsyncMock()
    works.get = AsyncMock(return_value=work)
    works.update = AsyncMock(return_value=_work())
    book = AsyncMock()
    book.get_book = AsyncMock(return_value={"title": "B"})
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_bearer_token] = lambda: "jwt"
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_knowledge_client_dep] = lambda: AsyncMock()
    app.dependency_overrides[get_book_client_dep] = lambda: book
    app.dependency_overrides[get_grant_client_dep] = lambda: _Grant(level)
    return TestClient(app), works


def _teardown():
    from app.main import app
    app.dependency_overrides.clear()


def test_create_work_view_grantee_403():
    c, _ = _client(GrantLevel.VIEW)
    try:
        r = c.post(f"/v1/composition/books/{BOOK}/work")
        assert r.status_code == 403
    finally:
        _teardown()


def test_create_work_non_grantee_404():
    c, _ = _client(GrantLevel.NONE)
    try:
        r = c.post(f"/v1/composition/books/{BOOK}/work")
        assert r.status_code == 404
    finally:
        _teardown()


def test_patch_work_view_grantee_403():
    # work exists (caller's own) but VIEW < EDIT → 403, and update never runs.
    c, works = _client(GrantLevel.VIEW, work=_work())
    try:
        r = c.patch(f"/v1/composition/works/{PROJECT}", json={"status": "archived"})
        assert r.status_code == 403
        works.update.assert_not_called()
    finally:
        _teardown()


def test_get_work_revoked_collaborator_404():
    # work row exists but grant is now NONE (revoked) → 404 (no stale read).
    c, _ = _client(GrantLevel.NONE, work=_work())
    try:
        r = c.get(f"/v1/composition/works/{PROJECT}")
        assert r.status_code == 404
    finally:
        _teardown()
