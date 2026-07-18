"""WS-1.4 review-impl M2 — the assistant-project endpoint must bind ONLY to a diary.

Ownership of the book is not enough: anchoring the assistant's knowledge project to a
shareable NOVEL the caller owns would let a collaborator on that novel read the assistant's
private extracted memory (knowledge authorizes project reads by resolve-to-owner on the
project's book). So the endpoint checks kind='diary' and fails closed otherwise.

Unit test — calls the endpoint function directly with fakes; no DB, no TestClient.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException, Response

from app.clients.grant_client import GrantLevel
from app.routers.public.projects import (
    AssistantProjectCreate,
    provision_assistant_project,
)


class _FakeGrant:
    def __init__(self, level: GrantLevel) -> None:
        self._level = level

    async def resolve_grant(self, book_id, user_id) -> GrantLevel:
        return self._level


class _FakeBookClient:
    def __init__(self, kind) -> None:
        self._kind = kind

    async def get_book_kind(self, book_id, user_id):
        return self._kind


class _SpyRepo:
    def __init__(self) -> None:
        self.calls = 0

    async def get_or_create_assistant_project(self, user_id, book_id, name):
        self.calls += 1
        return object(), True  # the endpoint returns this straight through


async def _call(kind, *, grant=GrantLevel.OWNER):
    repo = _SpyRepo()
    body = AssistantProjectCreate(book_id=uuid4())
    try:
        await provision_assistant_project(
            body=body,
            response=Response(),
            user_id=uuid4(),
            repo=repo,  # type: ignore[arg-type]
            grant=_FakeGrant(grant),  # type: ignore[arg-type]
            book_client=_FakeBookClient(kind),  # type: ignore[arg-type]
        )
    finally:
        _call.last_repo_calls = repo.calls  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_novel_book_is_refused_and_the_project_is_not_created():
    with pytest.raises(HTTPException) as exc:
        await _call("novel")
    assert exc.value.status_code == 404  # uniform no-oracle 404
    assert _call.last_repo_calls == 0, "the assistant project must NOT be created for a novel"


@pytest.mark.asyncio
async def test_an_unreachable_book_kind_is_treated_as_non_diary_and_refused():
    # get_book_kind returns None on any book-service failure — fail CLOSED, not open.
    with pytest.raises(HTTPException) as exc:
        await _call(None)
    assert exc.value.status_code == 404
    assert _call.last_repo_calls == 0


@pytest.mark.asyncio
async def test_a_non_owner_is_refused_before_the_kind_check():
    with pytest.raises(HTTPException) as exc:
        await _call("diary", grant=GrantLevel.NONE)
    assert exc.value.status_code == 404
    assert _call.last_repo_calls == 0


@pytest.mark.asyncio
async def test_a_diary_owned_by_the_caller_provisions():
    await _call("diary")
    assert _call.last_repo_calls == 1, "an owned diary must reach the get-or-create"
