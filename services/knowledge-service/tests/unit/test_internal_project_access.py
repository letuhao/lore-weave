"""T55/g — `GET /internal/projects/{id}/access`, the primitive §8.7 says the last three
federations are blocked on.

The endpoint is thin on purpose: its whole job is to express
`app.auth.grant_deps._resolve_owner`'s three branches as a LEVEL instead of as an exception,
on a contract `hasProjectAccess` in the gateway can consume exactly as `hasBookAccess`
consumes book-service's. So the tests are about the BRANCHES and the NO-ORACLE property, not
about plumbing.

⚠️ The sharpest rule here is the one that looks like a missing feature: **a project that does
not exist and a project the caller has no grant on must be INDISTINGUISHABLE.** book-service
spells it *"Always 200 {grant_level}; `none` for missing/forbidden (no oracle, R4)"*. A 404 on
one and a 200-`none` on the other would let any caller with an internal token enumerate which
project ids exist by reading status codes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from loreweave_grants import GrantLevel

from app.routers.internal_project_access import _LEVEL_NAME, _project_grant_level, project_access


def _repo(meta):
    r = MagicMock()
    r.project_meta = AsyncMock(return_value=meta)
    return r


def _gc(level=GrantLevel.NONE, raises=None):
    g = MagicMock()
    g.resolve_grant = AsyncMock(side_effect=raises) if raises else AsyncMock(return_value=level)
    return g


@pytest.mark.asyncio
async def test_the_owner_gets_owner_without_consulting_the_book_grant():
    """Owner wins outright — `_resolve_owner`'s first branch. The book grant is not even
    asked, which matters for a book-less project and saves a network hop for every other."""
    owner = uuid4()
    gc = _gc(GrantLevel.NONE)
    lvl = await _project_grant_level(uuid4(), owner, _repo((owner, uuid4())), gc)
    assert lvl is GrantLevel.OWNER
    gc.resolve_grant.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("granted", [GrantLevel.VIEW, GrantLevel.EDIT, GrantLevel.MANAGE])
async def test_a_project_with_a_book_DEFERS_to_the_book_grant(granted):
    """Second branch, and parametrised over the tiers because collapsing them to a boolean
    is how a `view` collaborator would silently read as `manage` downstream."""
    book = uuid4()
    caller = uuid4()
    gc = _gc(granted)
    lvl = await _project_grant_level(uuid4(), caller, _repo((uuid4(), book)), gc)
    assert lvl is granted
    gc.resolve_grant.assert_awaited_once_with(book, caller)


@pytest.mark.asyncio
async def test_a_BOOK_LESS_project_is_owner_only_R1():
    """Third branch. A book-less project has no grant surface to defer to, so anyone who is
    not the owner gets NONE — never a fallback to 'well, there is no book, so allow'."""
    gc = _gc(GrantLevel.OWNER)          # would grant if it were consulted
    lvl = await _project_grant_level(uuid4(), uuid4(), _repo((uuid4(), None)), gc)
    assert lvl is GrantLevel.NONE
    gc.resolve_grant.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_missing_project_and_a_forbidden_one_are_INDISTINGUISHABLE():
    """The no-oracle rule (R4), asserted on the RESPONSES rather than on the levels — a
    caller sees the payload, not the enum, and it is the payload that would leak."""
    missing = await project_access(
        project_id=uuid4(), user_id=uuid4(), repo=_repo(None), gc=_gc())
    forbidden = await project_access(
        project_id=uuid4(), user_id=uuid4(),
        repo=_repo((uuid4(), uuid4())), gc=_gc(GrantLevel.NONE))
    assert missing == forbidden == {"grant_level": "none", "lifecycle_state": ""}


@pytest.mark.asyncio
async def test_a_grant_check_that_ERRORS_reads_as_no_access():
    """Fail-closed. An exception resolving the book grant must not surface as a grant, and
    must not 500 either — a 500 is itself an oracle (it says the project exists)."""
    out = await project_access(
        project_id=uuid4(), user_id=uuid4(),
        repo=_repo((uuid4(), uuid4())),
        gc=_gc(raises=RuntimeError("book-service unreachable")))
    assert out == {"grant_level": "none", "lifecycle_state": ""}


@pytest.mark.asyncio
async def test_a_repo_that_ERRORS_also_reads_as_no_access():
    """The other side of the same door — validated on a case the guard was not derived from,
    since the `try` was written with the grant client in mind."""
    repo = MagicMock()
    repo.project_meta = AsyncMock(side_effect=RuntimeError("pool exhausted"))
    out = await project_access(
        project_id=uuid4(), user_id=uuid4(), repo=repo, gc=_gc())
    assert out == {"grant_level": "none", "lifecycle_state": ""}


def test_every_grant_level_has_a_wire_NAME():
    """Derived-not-listed, in the small: an unmapped level would fall through
    `_LEVEL_NAME.get(level, "none")` and silently DOWNGRADE a real grant to none. That fails
    closed, which is the safe direction and exactly why it would never be noticed."""
    assert set(_LEVEL_NAME) == set(GrantLevel), (
        f"GrantLevel has members with no wire name: {set(GrantLevel) - set(_LEVEL_NAME)}")
    # and the names must be the ones book-service emits, not new spellings
    from loreweave_grants import parse_grant_level
    for level, name in _LEVEL_NAME.items():
        assert parse_grant_level(name) is level, (
            f"{name!r} does not round-trip back to {level!r} through the SDK's own parser")
