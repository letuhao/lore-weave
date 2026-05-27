---
name: KNOWLEDGE_SERVICE_K21C_DESIGN
description: Phase K21 Cycle C design — FE tool-call indicator, per-project opt-out toggle, tool_calls read API, and the memory_remember user-confirmation (deferred-confirmation) flow
type: design
---

# Phase K21-C — Tool Calling: frontend + memory_remember confirmation

> **Status:** DESIGN (2026-05-17, session 57 cycle 15)
> **Authorized by:** PO at CLARIFY — Cycle C includes K21.7 safeguard 4
> (`memory_remember` user-confirmation) via a deferred-confirmation flow.
> **Closes:** the final slice of K21 — tasks K21.5, K21.12 (FE half),
> K21.7 safeguard 4, and the deferred D-K21B-05. After Cycle C, K21 — the
> last Track 3 feature phase — is complete.
> **Size:** XL — cross-service (knowledge-service + chat-service +
> frontend), 2 knowledge-service migrations. ~20 files.

---

## 1. Scope

| In scope | Task |
|---|---|
| `tool_calls` surfaced on the message-read API | D-K21B-05 |
| FE tool-call indicator on assistant messages | K21.5 |
| Per-project opt-out toggle(s) in the project form | K21.12-FE |
| `memory_remember` user-confirmation (deferred-confirmation) | K21.7 safeguard 4 |

After Cycle C, K21 is complete. Deferred follow-ups stay deferred
(D-K21B-01 shared-SDK, D-K21B-02 voice, D-K21B-06 live smoke).

---

## 2. What exists (audit, 2026-05-17)

- The FE chat stream hook [`useChatMessages.ts`](../../frontend/src/features/chat/hooks/useChatMessages.ts)
  dispatches SSE events via an if-else chain with **no `else`** — an
  unknown `type` is silently ignored, so Cycle B's `tool-call` event
  already degrades gracefully. The streamed assistant message is built
  locally (no refetch) — `content_parts` is assembled from accumulated
  reasoning/timing; the same hook must accumulate `tool-call` events.
- [`MemoryIndicator`](../../frontend/src/features/knowledge/components/MemoryIndicator.tsx)
  + the `memory-mode` event are the precedent for the K21.5 indicator.
- `ChatMessage` (FE `types.ts` + chat-service `app/models.py`) has no
  `tool_calls` field; chat-service `messages.py` `_row_to_message`
  doesn't surface it, though the `SELECT *` already returns the column.
- [`ProjectFormModal.tsx`](../../frontend/src/features/knowledge/components/ProjectFormModal.tsx)
  is the project create/edit form — the toggle home; mirror its existing
  `extraction_enabled` boolean. The public `PATCH /v1/knowledge/projects/{id}`
  already accepts `tool_calling_enabled` (Cycle B).
- Cycle A's [`executor.py`](../../services/knowledge-service/app/tools/executor.py)
  `_handle_memory_remember` writes the fact via `merge_fact` after the
  per-session rate-limit check (K21.7 safeguards 1–3).

---

## 3. Decisions

### D1 — D-K21B-05: surface `tool_calls` on the read API

chat-service `app/models.py` `ChatMessage` gains `tool_calls: list | None
= None`; `messages.py` `_row_to_message` parses `r["tool_calls"]` (JSONB
→ `json.loads`, reusing the `_parse_content_parts` idiom). FE `types.ts`
`ChatMessage` gains `tool_calls?: ToolCallRecord[] | null`.

### D2 — K21.5: the tool-call indicator

- `useChatMessages.ts` — handle the `tool-call` SSE event: accumulate
  `{tool, ok}` into a per-turn list, attach it to the locally-appended
  `assistantMessage.tool_calls` (the same way `content_parts` is built).
- NEW `frontend/src/features/chat/components/ToolCallIndicator.tsx` —
  a compact chip row rendered from `message.tool_calls`, mapping tool
  name → label ("🔍 Searched memory", "📚 Recalled an entity",
  "📅 Checked the timeline", "📝 Saved a memory", "🗑 Forgot a fact").
  Click expands a detail list. Mirrors `MemoryIndicator`.
- Rendered in [`AssistantMessage.tsx`](../../frontend/src/features/chat/components/AssistantMessage.tsx)
  (the K21 plan named `ChatMessage.tsx` — the actual component is
  `AssistantMessage.tsx`; plan-path drift). Works from both the live
  accumulated list and the persisted `tool_calls` (replay).

### D3 — K21.12-FE: project opt-out toggles

`ProjectFormModal.tsx` gains **two** toggles — `tool_calling_enabled`
(K21.12) and `memory_remember_confirm` (D4) — mirroring `extraction_enabled`.
The knowledge-feature `api.ts` / `types.ts` add both project fields to
the update payload + the `Project` type.

### D4 — K21.7 sf4: the `memory_remember_confirm` project setting

NEW `knowledge_projects.memory_remember_confirm BOOLEAN NOT NULL DEFAULT
false` — **opt-in**, default off (today's behavior — write directly — is
preserved). Plumbed through `Project` + `ProjectUpdate`. Not surfaced in
`build_context` — only the executor reads it.

### D5 — K21.7 sf4: the pending-facts store

NEW Postgres table `knowledge_pending_facts` — a pending fact is a
transient queue item, not a graph node, so it lives in Postgres not
Neo4j: `pending_fact_id` (uuidv7 PK), `user_id`, `project_id`,
`session_id`, `fact_type`, `fact_text`, `created_at`. A new
`PendingFactsRepo`.

### D6 — K21.7 sf4: executor queues instead of writing

`executor.py` `_handle_memory_remember` — after the rate-limit check
(unchanged — a queued fact still consumes a slot) **and the
`neutralize_injection` pass (Cycle B MED#2 — run it before the
queue-vs-write branch so both paths inherit the defense)**, load the
project; if `project.memory_remember_confirm` is true → INSERT a
`knowledge_pending_facts` row carrying the **already-neutralized**
`fact_text` instead of calling `merge_fact`, and return
`{"queued": true, "pending_fact_id": …, "fact_text": …,
"fact_type": …}`. Otherwise → current behavior (`merge_fact` →
`{"remembered": true, …}`). A no-project chat has no setting → writes
directly. The LLM sees the `queued` result and tells the user the fact
is awaiting their confirmation. (REVIEW-DESIGN R1 — neutralizing at
queue time means the confirm path can't bypass the injection defense.)

### D7 — K21.7 sf4: the pending-facts endpoints

NEW public (JWT) router `app/routers/public/pending_facts.py`:
- `GET /v1/knowledge/pending-facts?session_id=` — list the caller's
  pending facts (optionally filtered to one chat session).
- `POST /v1/knowledge/pending-facts/{id}/confirm` — `merge_fact` the
  queued fact (confidence 0.7 + `source_type='llm_tool_call'`; the
  stored `fact_text` is already injection-neutralized per D6, so confirm
  writes it as-is) then delete the pending row; returns the created
  fact. 404 if the id isn't the caller's.
- `POST /v1/knowledge/pending-facts/{id}/reject` — delete the pending
  row; 404 on cross-user / missing.

### D8 — K21.7 sf4: the FE pending-facts review

NEW `usePendingFacts(sessionId)` hook + `PendingFactsCard.tsx`. The FE
discovers queued facts by **querying `GET /v1/knowledge/pending-facts`**
after a turn — NOT from the SSE event (D9) — so no `tool-call` event
change is needed. The card renders below the chat showing each pending
fact with **Confirm** / **Reject** buttons wired to the D7 endpoints;
a confirm/reject mutates then refetches. The hook refetches on
turn-end (chat-stream end).

### D9 — chat-service is unchanged for sf4

The executor handles queue-vs-write entirely; the chat-service
tool-loop and the `tool-call` SSE event are untouched. chat-service's
only Cycle-C change is D1 (the read-API field). The FE learns of queued
facts by polling `pending-facts`, decoupling the confirmation flow from
the one-shot SSE stream.

---

## 4. Test plan

- **knowledge-service** — the `memory_remember_confirm` column + the
  `pending_facts` table round-trip; the executor `_handle_memory_remember`
  queues (returns `{queued:true}` + inserts a row) when the setting is on
  and writes directly when off; the rate limit still gates queued facts;
  the 3 pending-facts endpoints — list (user-scoped), confirm
  (merge_fact + row deleted, cross-user 404), reject (row deleted,
  cross-user 404).
- **chat-service** — `_row_to_message` surfaces `tool_calls`; null when
  the column is null.
- **frontend** — `ToolCallIndicator` renders chips per tool + the empty
  case; `useChatMessages` accumulates `tool-call` events onto the
  appended message; `ProjectFormModal` toggles round-trip both new
  fields; `usePendingFacts` + `PendingFactsCard` — list, confirm, reject,
  empty state.

---

## 5. Files

**knowledge-service:** `app/db/migrate.py` (2 columns/table), `app/db/models.py`
(`Project`/`ProjectUpdate` + a `PendingFact` model), NEW
`app/db/repositories/pending_facts.py`, `app/tools/executor.py`
(`_handle_memory_remember`), NEW `app/routers/public/pending_facts.py`,
`app/main.py` (router), `app/deps.py` (repo DI) + tests.

**chat-service:** `app/models.py` (`ChatMessage.tool_calls`),
`app/routers/messages.py` (`_row_to_message`) + a test.

**frontend:** `features/chat/types.ts`, `features/chat/hooks/useChatMessages.ts`,
NEW `features/chat/components/ToolCallIndicator.tsx`,
`features/chat/components/AssistantMessage.tsx`, `features/chat/api.ts`,
NEW `features/chat/hooks/usePendingFacts.ts`, NEW
`features/chat/components/PendingFactsCard.tsx`,
`features/knowledge/components/ProjectFormModal.tsx`,
`features/knowledge/api.ts` + `features/knowledge/types.ts` + tests.

---

## 6. Deferred / out of scope

| ID | Note | Target |
|---|---|---|
| D-K21C-01 | No cleanup sweep for `knowledge_pending_facts` — a fact the user never confirms/rejects lives forever. A TTL sweep (à la the quarantine cleanup) is a follow-up. | knowledge-service polish |
| (carried) | D-K21B-01 (shared-SDK for tool schemas), D-K21B-02 (voice path), D-K21B-06 (live e2e smoke) remain deferred. | K21 follow-ups |
