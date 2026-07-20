"""ext-tasks capability gating (T1c(2) safety primitive).

`client_supports_tasks(ctx)` reads whether THIS request's client declared the
ext-tasks extension; `gate_or_confirm(...)` is the one call a domain KIND-C tool
makes — a durable task if the client can drive it, else today's confirm_token
result. This is the guard that makes flipping a real tool safe: a non-tasks client
(pre-driver chat-service, the public edge, external agents) is never stranded.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from loreweave_mcp.tasks import InMemoryTaskStore
from loreweave_mcp.tasks_wire import (
    GATE_RESULT_TYPE,
    TASKS_EXTENSION,
    client_supports_tasks,
    gate_or_confirm,
)

_CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"


def _ctx(meta):
    return SimpleNamespace(request_context=SimpleNamespace(meta=meta))


def _tasks_meta_dict():
    return {_CAPS_KEY: {"extensions": {TASKS_EXTENSION: {}}}}


class _ExtraModel:
    """Stand-in for a pydantic _meta carrying the caps as an extra field."""
    def __init__(self, extra):
        self.model_extra = extra


# ── client_supports_tasks ─────────────────────────────────────────────────────
def test_dict_meta_declares_tasks():
    assert client_supports_tasks(_ctx(_tasks_meta_dict())) is True


def test_dict_meta_without_tasks_extension():
    assert client_supports_tasks(_ctx({_CAPS_KEY: {"extensions": {}}})) is False


def test_dict_meta_without_caps():
    assert client_supports_tasks(_ctx({"something": "else"})) is False


def test_no_meta_is_false():
    assert client_supports_tasks(_ctx(None)) is False


def test_no_request_context_is_false():
    assert client_supports_tasks(SimpleNamespace()) is False


def test_pydantic_extra_meta_declares_tasks():
    meta = _ExtraModel({_CAPS_KEY: {"extensions": {TASKS_EXTENSION: {}}}})
    assert client_supports_tasks(_ctx(meta)) is True


def test_malformed_meta_fails_closed():
    # a caps node that isn't a mapping must not raise → fail-closed to confirm_token
    assert client_supports_tasks(_ctx({_CAPS_KEY: 123})) is False


# ── gate_or_confirm dispatch ──────────────────────────────────────────────────
async def _resolver(owner_user_id, payload, inputs):
    return {"done": True}


@pytest.mark.asyncio
async def test_gate_or_confirm_tasks_client_gets_a_task():
    store = InMemoryTaskStore({"book.publish": _resolver})
    out = await gate_or_confirm(
        _ctx(_tasks_meta_dict()), store,
        descriptor="book.publish", owner_user_id="u1", payload={"chapter_id": "ch1"},
        input_requests={"title": "Publish?"},
        confirm_fallback=lambda: {"confirm_token": "tok", "descriptor": "book.publish"},
    )
    assert out["type"] == GATE_RESULT_TYPE
    assert out["taskId"].startswith("task_")
    assert "confirm_token" not in out


@pytest.mark.asyncio
async def test_gate_or_confirm_non_tasks_client_gets_confirm_token():
    store = InMemoryTaskStore({"book.publish": _resolver})
    called = {"fallback": False}

    def _fallback():
        called["fallback"] = True
        return {"confirm_token": "tok", "descriptor": "book.publish"}

    out = await gate_or_confirm(
        _ctx(None), store,  # client did NOT declare tasks
        descriptor="book.publish", owner_user_id="u1", payload={"chapter_id": "ch1"},
        input_requests={"title": "Publish?"},
        confirm_fallback=_fallback,
    )
    assert called["fallback"] is True
    assert out["confirm_token"] == "tok"
    assert "type" not in out
    # and no task was created (the store stays empty)
    with pytest.raises(Exception):
        await store.get("task_anything")
