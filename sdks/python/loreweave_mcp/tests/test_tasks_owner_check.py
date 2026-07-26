"""M2 accept-caller OWNERSHIP CHECK — only the proposing user may drive their gate.

`_owner_check` lifts the caller identity from the request envelope (X-Internal-Token +
X-User-Id) and refuses when it doesn't match task.owner_user_id, so a leaked task_id
can't let a stranger trigger someone else's pending action. (The Go book domain enforces
the same invariant in its resolver; this guards the Python domains at the kit tool.)
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from loreweave_mcp.tasks import InMemoryTaskStore
from loreweave_mcp.tasks_wire import _owner_check

_TOKEN = "svc-secret"
_OWNER = "11111111-1111-1111-1111-111111111111"
_OTHER = "22222222-2222-2222-2222-222222222222"


def _ctx(headers: dict[str, str]):
    # build_tool_context reads ctx.request_context.request.headers.get(<lowercase>).
    return SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(headers=headers)))


def _hdrs(user_id: str, token: str = _TOKEN) -> dict[str, str]:
    # build_tool_context also requires x-session-id (the resume driver sends it).
    return {"x-internal-token": token, "x-user-id": user_id, "x-session-id": "sess-1"}


async def _store_with_task(owner: str):
    store = InMemoryTaskStore({"d": lambda o, p, i: None})
    task = await store.create(descriptor="d", owner_user_id=owner, payload={})
    return store, task.task_id


@pytest.mark.asyncio
async def test_owner_may_drive():
    store, tid = await _store_with_task(_OWNER)
    assert await _owner_check(_ctx(_hdrs(_OWNER)), _TOKEN, store, tid) is None


@pytest.mark.asyncio
async def test_stranger_is_refused():
    store, tid = await _store_with_task(_OWNER)
    assert await _owner_check(_ctx(_hdrs(_OTHER)), _TOKEN, store, tid) == "not_task_owner"


@pytest.mark.asyncio
async def test_missing_identity_is_refused():
    store, tid = await _store_with_task(_OWNER)
    # no x-user-id header ⇒ build_tool_context raises ⇒ identity_required
    assert await _owner_check(_ctx({"x-internal-token": _TOKEN}), _TOKEN, store, tid) == "identity_required"


@pytest.mark.asyncio
async def test_wrong_internal_token_is_refused():
    store, tid = await _store_with_task(_OWNER)
    assert await _owner_check(_ctx(_hdrs(_OWNER, token="wrong")), _TOKEN, store, tid) == "identity_required"


@pytest.mark.asyncio
async def test_no_token_configured_skips_the_check():
    # in-process / kit mode (no internal_token) ⇒ no envelope, no check.
    store, tid = await _store_with_task(_OWNER)
    assert await _owner_check(_ctx({}), None, store, tid) is None
