# FD-2 — chat→KG extraction (make the dead path real)

**Cycle:** LOOM-76 · **Size:** L · cross-3-services (chat-service + knowledge-service + worker-ai)
**PO decision (CLARIFY):** BUILD it fully (option A).

## The dead chain (diagnosed)
1. chat-service emits `chat.turn_completed` (`aggregate_type='chat'`, aggregate_id=assistant `msg_id`, payload = ids + content **lengths**, no text) — `stream_service.py:899`.
2. knowledge `handle_chat_turn` enqueues into `extraction_pending` with **`aggregate_type="chat_session"`** — `handlers.py:82`. **BUG-1: re-labels the event's `chat` → `chat_session`.**
3. worker-ai `_enumerate_pending_chat_turns` drains **`aggregate_type='chat'`** — `runner.py:946` → never matches the `chat_session` rows.
4. worker passes **`text=""`** — `runner.py:1593`. **BUG-2: no-op even if consumed.**

## Build

### 1. knowledge-service — fix the type (BUG-1)
`handlers.py:82` `aggregate_type="chat_session"` → `"chat"` (align with the event's own type + the worker drainer + the canonical `'chat'` source filter in mcp/server.py). Existing stale `chat_session` rows stay unconsumed (they were empty no-ops anyway).

### 2. chat-service — internal turn-text endpoint (the missing fetch)
New `app/routers/internal.py`: `GET /internal/chat/turns/{message_id}/text`, guarded by `X-Internal-Token` (== `settings.internal_service_token`; chat-service has no inbound internal endpoint yet → add a tiny `require_internal_token` dep). Given the assistant `message_id`: fetch its `content` + `role` + `parent_message_id` from `chat_messages`; fetch the parent (user) message's `content`; return `{"text": "<user>\n\n<assistant>", "found": bool}` (404 → found=false). Joins the full turn (Q+A) — the meaningful extraction unit.

### 3. worker-ai — ChatClient + wire (BUG-2)
- `clients.py`: `class ChatClient` (mirrors KnowledgeClient: httpx + `X-Internal-Token`). `get_turn_text(message_id) -> str | None` — joined turn text on 200; **None on 404 / empty / transport failure** (best-effort, logged). Matches the chat path's existing best-effort posture (a transient miss degrades to today's empty no-op — documented LOW; transient-retry is a deferred improvement).
- `config.py`: `chat_service_internal_url` (default `http://chat-service:<port>`).
- `main.py`: construct `ChatClient`, thread into `process_job` via `wrapper`.
- `runner.py`: thread `chat_client` through `wrapper(305)` + `process_job(1170)`; at the turn loop replace `text=""` with `text = await chat_client.get_turn_text(turn["aggregate_id"]) or ""`. Empty → extract_pass2 still no-ops gracefully (source row written, idempotent).

## Tests
- chat-service: `GET /internal/chat/turns/{id}/text` happy (joins user+assistant), missing-parent (assistant only), 404, bad-token 401.
- worker-ai: `ChatClient.get_turn_text` happy/404/transport→None; runner uses the fetched text (regression: a non-empty turn text reaches `_extract_and_persist`, not "").
- knowledge: `handle_chat_turn` enqueues `aggregate_type="chat"` (non-default lock so the worker can drain it).

## VERIFY (cross-3-services → live-smoke REQUIRED)
Rebuild chat + knowledge + worker-ai. Live: post a chat turn (or seed a chat_messages row + a `chat.turn_completed` → extraction_pending `chat` row) → run an extraction job → assert the worker fetched real turn text (not "") and extract_pass2 produced/persisted candidates from it.

## /review-impl
At POST-REVIEW (new service boundary + cross-3-services contract). Focus: the X-Internal-Token guard on the new endpoint; the None-vs-text degrade; the type-fix doesn't strand other consumers of `chat_session`; turn-text join correctness.
