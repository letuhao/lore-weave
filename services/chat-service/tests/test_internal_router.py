"""FD-2 — internal chat-turn text endpoint (worker-ai fetches turn text for KG)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.config import settings
from tests.conftest import FakeRecord

MSG_ID = str(uuid4())
PARENT_ID = uuid4()
_AUTH = {"X-Internal-Token": settings.internal_service_token}


@pytest.mark.asyncio
async def test_turn_text_joins_user_and_assistant(client, mock_pool):
    # assistant message (has a parent user message) → then the parent's content.
    mock_pool.fetchrow = AsyncMock(side_effect=[
        FakeRecord({"role": "assistant", "content": "a disgraced knight.",
                    "parent_message_id": PARENT_ID}),
        FakeRecord({"content": "who is Kael?"}),
    ])
    r = await client.get(f"/internal/chat/turns/{MSG_ID}/text", headers=_AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["text"] == "who is Kael?\n\na disgraced knight."


@pytest.mark.asyncio
async def test_turn_text_no_parent_returns_assistant_only(client, mock_pool):
    mock_pool.fetchrow = AsyncMock(return_value=FakeRecord(
        {"role": "assistant", "content": "standalone message.", "parent_message_id": None}))
    r = await client.get(f"/internal/chat/turns/{MSG_ID}/text", headers=_AUTH)
    assert r.status_code == 200 and r.json()["text"] == "standalone message."


@pytest.mark.asyncio
async def test_turn_text_non_assistant_ignores_parent(client, mock_pool):
    # A user message id must NOT walk to its parent (a prior assistant turn) —
    # that would prepend unrelated text. Only the message's own content returns.
    fetchrow = AsyncMock(return_value=FakeRecord(
        {"role": "user", "content": "who is Kael?", "parent_message_id": PARENT_ID}))
    mock_pool.fetchrow = fetchrow
    r = await client.get(f"/internal/chat/turns/{MSG_ID}/text", headers=_AUTH)
    assert r.status_code == 200 and r.json()["text"] == "who is Kael?"
    # exactly one DB read — the parent lookup is skipped for a non-assistant msg.
    assert fetchrow.await_count == 1


@pytest.mark.asyncio
async def test_turn_text_not_found(client, mock_pool):
    mock_pool.fetchrow = AsyncMock(return_value=None)
    r = await client.get(f"/internal/chat/turns/{MSG_ID}/text", headers=_AUTH)
    assert r.status_code == 200
    assert r.json() == {"found": False, "text": ""}


@pytest.mark.asyncio
async def test_turn_text_requires_internal_token(client):
    # no token → 401 (the guard fires before any DB access).
    r = await client.get(f"/internal/chat/turns/{MSG_ID}/text")
    assert r.status_code == 401
    r2 = await client.get(f"/internal/chat/turns/{MSG_ID}/text",
                          headers={"X-Internal-Token": "wrong"})
    assert r2.status_code == 401


# ── W1 (W0 §7) — GET /internal/tool-health ──────────────────────────────────


@pytest.mark.asyncio
async def test_tool_health_aggregates_per_tool(client, mock_pool):
    fetch = AsyncMock(return_value=[
        FakeRecord({"tool": "glossary_book_patch", "calls": 10, "errors": 4}),
        FakeRecord({"tool": "memory_search", "calls": 20, "errors": 0}),
    ])
    mock_pool.fetch = fetch
    r = await client.get("/internal/tool-health", headers=_AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["days"] == 7  # default window
    assert body["total_calls"] == 30
    assert body["total_errors"] == 4
    assert body["error_rate"] == round(4 / 30, 4)
    by_tool = {t["tool"]: t for t in body["tools"]}
    assert by_tool["glossary_book_patch"]["error_rate"] == 0.4
    assert by_tool["memory_search"]["error_rate"] == 0.0
    # the SQL unnests tool_calls jsonb and windows on created_at.
    sql = fetch.await_args.args[0]
    assert "jsonb_array_elements" in sql
    assert "make_interval" in sql
    # days is passed as the bind param.
    assert fetch.await_args.args[1] == 7


@pytest.mark.asyncio
async def test_tool_health_custom_window_and_empty(client, mock_pool):
    mock_pool.fetch = AsyncMock(return_value=[])
    r = await client.get("/internal/tool-health?days=30", headers=_AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body == {"days": 30, "total_calls": 0, "total_errors": 0,
                    "error_rate": 0.0, "tools": []}


@pytest.mark.asyncio
async def test_tool_health_days_validated(client, mock_pool):
    mock_pool.fetch = AsyncMock(return_value=[])
    assert (await client.get("/internal/tool-health?days=0", headers=_AUTH)).status_code == 422
    assert (await client.get("/internal/tool-health?days=91", headers=_AUTH)).status_code == 422


@pytest.mark.asyncio
async def test_tool_health_requires_internal_token(client):
    assert (await client.get("/internal/tool-health")).status_code == 401
    r = await client.get("/internal/tool-health", headers={"X-Internal-Token": "wrong"})
    assert r.status_code == 401


# ── WS-1.8 (spec 06 §Q10) — GET /internal/chat/messages/day-window ───────────

_DW = "/internal/chat/messages/day-window"


def _dw_params(**over):
    p = {"user_id": str(uuid4()), "book_id": str(uuid4()), "local_date": "2026-03-10"}
    p.update(over)
    return p


@pytest.mark.asyncio
async def test_day_window_requires_internal_token(client):
    # The guard fires before any DB access — no token / wrong token → 401.
    assert (await client.get(_DW, params=_dw_params())).status_code == 401
    r = await client.get(_DW, params=_dw_params(), headers={"X-Internal-Token": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_day_window_limit_is_bounded(client, mock_pool):
    # A caller cannot ask for an unbounded window: limit is clamped to [1, 50000].
    mock_pool.fetch = AsyncMock(return_value=[])
    assert (await client.get(_DW, params=_dw_params(limit=0), headers=_AUTH)).status_code == 422
    assert (await client.get(_DW, params=_dw_params(limit=50001), headers=_AUTH)).status_code == 422
    # book_id is OPTIONAL (T-4: session_kind='assistant' is the server-side discriminator, so a
    # missing book_id does NOT widen the scope) — the required params are user_id + local_date.
    ok = {"user_id": str(uuid4()), "local_date": "2026-03-10"}  # no book_id
    assert (await client.get(_DW, params=ok, headers=_AUTH)).status_code == 200
    bad = {"local_date": "2026-03-10"}  # no user_id
    assert (await client.get(_DW, params=bad, headers=_AUTH)).status_code == 422


@pytest.mark.asyncio
async def test_day_window_shape_and_truncation_via_mock(client, mock_pool):
    # Even with the dev DB down, prove the handler's shaping: fetch returns limit+1 rows → the
    # extra is dropped and truncated=true; tool_names/timestamps are serialized as JSON-safe.
    now = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)

    def row(seq, tools):
        return FakeRecord({
            "message_id": uuid4(), "session_id": uuid4(), "role": "user",
            "content": f"m{seq}", "sequence_num": seq, "local_date": date(2026, 3, 10),
            "created_at": now, "tool_names": tools,
        })

    # limit=2 → handler fetches 3; returning 3 signals truncation.
    mock_pool.fetch = AsyncMock(return_value=[row(0, ["glossary_recall"]), row(1, None), row(2, None)])
    r = await client.get(_DW, params=_dw_params(limit=2), headers=_AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["message_count"] == 2  # the +1 probe row is dropped
    assert body["truncated"] is True
    assert body["messages"][0]["tool_names"] == ["glossary_recall"]
    assert body["messages"][1]["tool_names"] == []  # NULL tool_calls → empty list, not null
    assert body["messages"][0]["local_date"] == "2026-03-10"
    assert body["messages"][0]["created_at"].startswith("2026-03-10T09:00")


# ── A1 / P-10 — POST /internal/assistant/distill (the "End my day" trigger) ──

_DISTILL = "/internal/chat/assistant/distill"


def _distill_body(**over):
    b = {"user_id": str(uuid4()), "book_id": str(uuid4()),
         "model_source": "user_model", "model_ref": str(uuid4())}
    b.update(over)
    return b


@pytest.mark.asyncio
async def test_distill_trigger_requires_internal_token(client):
    r = await client.post(_DISTILL, json=_distill_body())
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_distill_trigger_enqueues_with_server_default_entry_date(client):
    # entry_date omitted → the endpoint stamps TODAY server-side (D-R14: never trust a client day).
    today = datetime.now(timezone.utc).date().isoformat()
    with patch("app.events.distill_enqueue.enqueue_distill", new=AsyncMock(return_value="1-0")) as enq:
        r = await client.post(_DISTILL, json=_distill_body(language="vi"), headers=_AUTH)
    assert r.status_code == 202
    body = r.json()
    assert body["enqueued"] is True and body["entry_date"] == today and body["message_id"] == "1-0"
    kw = enq.await_args.kwargs
    assert kw["entry_date"] == today and kw["entry_zone"] == "UTC" and kw["language"] == "vi"
    assert kw["model_source"] == "user_model"


@pytest.mark.asyncio
async def test_distill_trigger_honours_an_explicit_entry_date(client):
    with patch("app.events.distill_enqueue.enqueue_distill", new=AsyncMock(return_value="1-0")) as enq:
        r = await client.post(_DISTILL, json=_distill_body(entry_date="2026-03-10"), headers=_AUTH)
    assert r.status_code == 202 and r.json()["entry_date"] == "2026-03-10"
    assert enq.await_args.kwargs["entry_date"] == "2026-03-10"


@pytest.mark.asyncio
async def test_distill_trigger_surfaces_an_enqueue_failure_as_503(client):
    # A lost enqueue = a silently un-journaled day → must NOT be swallowed (503, not 202).
    with patch("app.events.distill_enqueue.enqueue_distill", new=AsyncMock(side_effect=RuntimeError("redis down"))):
        r = await client.post(_DISTILL, json=_distill_body(), headers=_AUTH)
    assert r.status_code == 503


# ── WS-2.6a legs 2+3 — POST /internal/assistant/reextract (correction reconcile) ──

_REEXTRACT = "/internal/chat/assistant/reextract"


def _reextract_body(**over):
    b = {"user_id": str(uuid4()), "book_id": str(uuid4()), "entry_date": "2026-03-10",
         "body": "Alice froze the Q3 budget, not Minh.",
         "model_source": "user_model", "model_ref": str(uuid4())}
    b.update(over)
    return b


# ── WS-3.0 — server-side distill-context resolution (headless scheduled run) ──


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeInternalClient:
    """Async-context-manager stand-in for build_internal_client — returns the diary book."""

    def __init__(self, book_id):
        self._book_id = book_id

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        if "diary" in url:
            return _FakeResp(200, {"book_id": self._book_id, "lifecycle": "active"})
        return _FakeResp(404, {})


@pytest.mark.asyncio
async def test_distill_headless_resolves_book_model_tz_serverside(client):
    """WS-3.0 (D-B1) — a scheduled tick posts ONLY {user_id}; the trigger resolves the diary book,
    the distill model (distill default), and the tz server-side."""
    uid = str(uuid4())
    book_id = str(uuid4())
    model_ref = str(uuid4())

    prov = AsyncMock()
    # 'distill' default resolves first (chat fallback not reached).
    prov.get_default_model = AsyncMock(side_effect=lambda cap, u: ("user_model", model_ref) if cap == "distill" else None)
    auth = AsyncMock()
    auth.get_user_timezone = AsyncMock(return_value="Asia/Ho_Chi_Minh")

    with patch("app.routers.internal.build_internal_client", return_value=_FakeInternalClient(book_id)), \
         patch("app.client.provider_client.get_provider_client", return_value=prov), \
         patch("app.client.auth_client.get_auth_client", return_value=auth), \
         patch("app.events.distill_enqueue.enqueue_distill", new=AsyncMock(return_value="7-0")) as enq:
        r = await client.post(_DISTILL, json={"user_id": uid}, headers=_AUTH)

    assert r.status_code == 202, r.text
    kw = enq.await_args.kwargs
    assert kw["book_id"] == book_id
    assert kw["model_source"] == "user_model" and kw["model_ref"] == model_ref
    assert kw["entry_zone"] == "Asia/Ho_Chi_Minh"
    prov.get_default_model.assert_any_await("distill", uid)


@pytest.mark.asyncio
async def test_distill_headless_422_when_no_model_configured(client):
    """A user with no distill/chat default → 422 (the scheduler logs + skips; never a silent no-op)."""
    uid = str(uuid4())
    prov = AsyncMock()
    prov.get_default_model = AsyncMock(return_value=None)  # neither distill nor chat
    auth = AsyncMock()
    auth.get_user_timezone = AsyncMock(return_value="UTC")

    with patch("app.routers.internal.build_internal_client", return_value=_FakeInternalClient(str(uuid4()))), \
         patch("app.client.provider_client.get_provider_client", return_value=prov), \
         patch("app.client.auth_client.get_auth_client", return_value=auth):
        r = await client.post(_DISTILL, json={"user_id": uid}, headers=_AUTH)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_reextract_trigger_requires_internal_token(client):
    r = await client.post(_REEXTRACT, json=_reextract_body())
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_reextract_trigger_enqueues_the_corrected_body_and_day(client):
    with patch("app.events.distill_enqueue.enqueue_reextract", new=AsyncMock(return_value="9-0")) as enq:
        r = await client.post(_REEXTRACT, json=_reextract_body(language="vi"), headers=_AUTH)
    assert r.status_code == 202
    body = r.json()
    assert body["enqueued"] is True and body["entry_date"] == "2026-03-10" and body["message_id"] == "9-0"
    kw = enq.await_args.kwargs
    assert kw["entry_date"] == "2026-03-10" and kw["language"] == "vi"
    assert "Alice" in kw["body"] and kw["model_source"] == "user_model"


@pytest.mark.asyncio
async def test_reextract_trigger_rejects_an_empty_body(client):
    r = await client.post(_REEXTRACT, json=_reextract_body(body="   "), headers=_AUTH)
    assert r.status_code == 422  # a correction must carry text


@pytest.mark.asyncio
async def test_reextract_trigger_surfaces_an_enqueue_failure_as_503(client):
    # A lost enqueue = a correction that never reconciles (recall keeps the wrong fact) → not swallowed.
    with patch("app.events.distill_enqueue.enqueue_reextract", new=AsyncMock(side_effect=RuntimeError("redis down"))):
        r = await client.post(_REEXTRACT, json=_reextract_body(), headers=_AUTH)
    assert r.status_code == 503
