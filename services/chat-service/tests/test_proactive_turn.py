"""WS-3.5 / C7 (SD-C7) — the proactive-turn seam: fail-closed opt-in gate + assistant_proactive
attribution. The scheduler's proactive_nudge fires POST /internal/chat/assistant/proactive-turn."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.config import settings
from tests.conftest import FakeRecord

_AUTH = {"X-Internal-Token": settings.internal_service_token}
UID = str(uuid4())


def _prefs(assistant: dict):
    m = AsyncMock(return_value=SimpleNamespace(assistant=assistant))
    return patch("app.db.user_chat_ai_prefs.get_prefs", m)


@pytest.mark.asyncio
async def test_proactive_turn_fails_closed_when_not_enabled(client, mock_pool):
    # default OFF (no opt-in) → a NO-OP: no session, no message, no spend.
    with _prefs({}):  # proactive_enabled absent ⇒ False
        r = await client.post("/internal/chat/assistant/proactive-turn", headers=_AUTH,
                              json={"user_id": UID})
    assert r.status_code == 202
    assert r.json() == {"proactive": False, "reason": "not_enabled"}
    mock_pool._conn.fetchrow.assert_not_called()  # nothing written


@pytest.mark.asyncio
async def test_proactive_turn_explicit_false_is_noop(client, mock_pool):
    with _prefs({"proactive_enabled": False}):
        r = await client.post("/internal/chat/assistant/proactive-turn", headers=_AUTH, json={"user_id": UID})
    assert r.status_code == 202 and r.json()["proactive"] is False


def _grounded(text: str | None):
    """Patch the A4.2 helpers: fixed grounding snippets + a controllable generated message (None ⇒ the
    endpoint falls back to the static line)."""
    return (
        patch("app.routers.internal._recent_assistant_snippets", AsyncMock(return_value=["shipping the Q3 launch"])),
        patch("app.routers.internal._generate_proactive_content", AsyncMock(return_value=text)),
    )


@pytest.mark.asyncio
async def test_proactive_turn_enabled_writes_assistant_proactive_message(client, mock_pool):
    sess_id, msg_id = uuid4(), uuid4()
    mock_pool.fetchval = AsyncMock(return_value=None)  # no recent proactive turn (dedup passes)
    mock_pool._conn.fetchrow = AsyncMock(side_effect=[
        FakeRecord({"session_id": sess_id}),
        FakeRecord({"message_id": msg_id}),
    ])
    notify = AsyncMock(return_value=True)
    snip, gen = _grounded("How's the Q3 launch coming along?")
    with _prefs({"proactive_enabled": True}), snip, gen, \
         patch("app.routers.internal._resolve_distill_context",
               AsyncMock(return_value=("book-1", "user_model", uuid4(), "UTC"))), \
         patch("app.routers.internal._notify_proactive_checkin", notify):
        r = await client.post("/internal/chat/assistant/proactive-turn", headers=_AUTH, json={"user_id": UID})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["proactive"] is True and body["initiated_by"] == "assistant_proactive"
    # the session is bound to the book + given message_count/last_message_at (so it's discoverable)
    sess_sql = mock_pool._conn.fetchrow.await_args_list[0].args[0]
    assert "book_id" in sess_sql and "last_message_at" in sess_sql
    # the message INSERT stamped initiated_by='assistant_proactive'
    msg_call = mock_pool._conn.fetchrow.await_args_list[1]
    assert "chat_messages" in msg_call.args[0] and "'assistant_proactive'" in msg_call.args[0]
    # A4.2 — the persisted content is the GROUNDED LLM message, not the static line.
    assert msg_call.args[3] == "How's the Q3 launch coming along?"
    # R3 — the push fired for the committed turn's session, and its result is surfaced.
    notify.assert_awaited_once_with(UID, str(sess_id))
    assert body["notified"] is True


@pytest.mark.asyncio
async def test_proactive_turn_falls_back_to_static_when_generation_fails(client, mock_pool):
    # A4.2 — content generation is fail-SAFE: a None (LLM error/empty) never blocks the turn; it lands
    # with the static line so the user is still reached.
    from app.routers.internal import _PROACTIVE_STATIC
    sess_id, msg_id = uuid4(), uuid4()
    mock_pool.fetchval = AsyncMock(return_value=None)
    mock_pool._conn.fetchrow = AsyncMock(side_effect=[
        FakeRecord({"session_id": sess_id}), FakeRecord({"message_id": msg_id})])
    snip, gen = _grounded(None)  # generation unavailable
    with _prefs({"proactive_enabled": True}), snip, gen, \
         patch("app.routers.internal._resolve_distill_context",
               AsyncMock(return_value=("book-1", "user_model", uuid4(), "UTC"))), \
         patch("app.routers.internal._notify_proactive_checkin", AsyncMock(return_value=True)):
        r = await client.post("/internal/chat/assistant/proactive-turn", headers=_AUTH, json={"user_id": UID})
    assert r.status_code == 202
    assert mock_pool._conn.fetchrow.await_args_list[1].args[3] == _PROACTIVE_STATIC


@pytest.mark.asyncio
async def test_proactive_turn_notification_blip_still_persists_the_turn(client, mock_pool):
    # R3 — the push is BEST-EFFORT: a notification-service blip must NOT fail the turn (the message is
    # already committed); the turn succeeds with notified=False.
    sess_id, msg_id = uuid4(), uuid4()
    mock_pool.fetchval = AsyncMock(return_value=None)
    mock_pool._conn.fetchrow = AsyncMock(side_effect=[
        FakeRecord({"session_id": sess_id}), FakeRecord({"message_id": msg_id})])
    snip, gen = _grounded("How's it going?")
    with _prefs({"proactive_enabled": True}), snip, gen, \
         patch("app.routers.internal._resolve_distill_context",
               AsyncMock(return_value=("book-1", "user_model", uuid4(), "UTC"))), \
         patch("app.routers.internal._notify_proactive_checkin", AsyncMock(return_value=False)):
        r = await client.post("/internal/chat/assistant/proactive-turn", headers=_AUTH, json={"user_id": UID})
    assert r.status_code == 202
    body = r.json()
    assert body["proactive"] is True and body["notified"] is False  # turn stands, push didn't land


@pytest.mark.asyncio
async def test_proactive_notification_is_content_free():
    # R3 — the push carries NO diary content (it can land on a lock screen): only a stable title +
    # i18n key + the 'assistant' category + a session-scoped dedup key. Capture the POSTed body.
    from types import SimpleNamespace
    captured = {}

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, path, json=None):
            captured["path"] = path
            captured["json"] = json
            return SimpleNamespace(status_code=201)

    with patch("app.routers.internal.build_internal_client", lambda *a, **k: _FakeClient()):
        from app.routers.internal import _notify_proactive_checkin
        ok = await _notify_proactive_checkin(UID, "sess-123")
    assert ok is True
    assert captured["path"] == "/internal/notifications/"
    payload = captured["json"]
    assert payload["category"] == "assistant"
    assert payload["dedup_key"] == "proactive:sess-123"
    assert payload["message_key"] == "assistant.proactive_checkin"
    # content-free: no diary text — the title/body are generic, and there is no free 'content' field.
    blob = (payload.get("title", "") + payload.get("body", "")).lower()
    for leak in ("diary", "reflect", "colleague", "migration"):
        assert leak not in blob


@pytest.mark.asyncio
async def test_proactive_turn_dedups_recent(client, mock_pool):
    # cold-review MED-2 — a recent proactive turn (last 6 days) suppresses a new one (no daily spam).
    mock_pool.fetchval = AsyncMock(return_value=1)  # a recent assistant_proactive message exists
    with _prefs({"proactive_enabled": True}):
        r = await client.post("/internal/chat/assistant/proactive-turn", headers=_AUTH, json={"user_id": UID})
    assert r.status_code == 202
    assert r.json() == {"proactive": False, "reason": "already_recent"}
    mock_pool._conn.fetchrow.assert_not_called()  # nothing created


@pytest.mark.asyncio
async def test_proactive_turn_requires_internal_token(client):
    r = await client.post("/internal/chat/assistant/proactive-turn", json={"user_id": UID})
    assert r.status_code == 401


def test_proactive_enabled_must_be_bool():
    # a spend/interruption-causing toggle: a junk value must be REJECTED at the door, never read truthy.
    from app.routers.ai_settings import AiPrefsPatch
    with pytest.raises(Exception):
        AiPrefsPatch(assistant={"proactive_enabled": "yes"})
    # a real bool is accepted
    p = AiPrefsPatch(assistant={"proactive_enabled": True})
    assert p.assistant["proactive_enabled"] is True


def test_clean_proactive_text_strips_scaffolding_and_falls_back():
    from app.routers.internal import _clean_proactive_text
    # a clean model reply is returned as-is (quotes unwrapped)
    assert _clean_proactive_text('"How did the Q3 migration land?"') == "How did the Q3 migration land?"
    # a reply that is ONLY planning scaffolding → None (caller uses the static fallback, never junk)
    scaffold = "*   Role: assistant\n*   Goal: check-in\n*   Draft 1:\n*   Context: ..."
    assert _clean_proactive_text(scaffold) is None
    # empty / whitespace → None
    assert _clean_proactive_text("   ") is None
    # scaffolding THEN a real message → the message survives
    mixed = "Here is my plan:\n- think about it\nHow have things been since the launch settled?"
    assert _clean_proactive_text(mixed) == "How have things been since the launch settled?"


@pytest.mark.asyncio
async def test_get_proactive_enabled_fails_closed(client, mock_pool):
    with _prefs({}):
        r = await client.get("/internal/chat/assistant/proactive-enabled", headers=_AUTH, params={"user_id": UID})
    assert r.status_code == 200 and r.json() == {"proactive_enabled": False}
    with _prefs({"proactive_enabled": True}):
        r2 = await client.get("/internal/chat/assistant/proactive-enabled", headers=_AUTH, params={"user_id": UID})
    assert r2.json() == {"proactive_enabled": True}
