# glossary edit-existing — frontend-propose + diff card — P3 plan

- **Date:** 2026-06-10 · **Phase:** P3 · **Size:** XL · **PO:** default v2.2; `/review-impl` at POST-REVIEW (write/concurrency path). PO chose: full edit scope (incl. attribute values), glossary-page surface now, no `/amaw`.
- **Goal:** the assistant proposes an edit to an **existing** entity; the chat run SUSPENDS, the browser renders a **glossary diff card** (old→new), the user Applies (version-checked patch, H5) or Dismisses; the resume reports the **real** outcome (H6). Consumer-side, **not** gateway-routed (the "executor" is the human clicking Apply). Spec: [`2026-06-10-glossary-assistant-architecture.md`](../specs/2026-06-10-glossary-assistant-architecture.md) §17.3 / §18 DoD.

## Decisions (CLARIFY/DESIGN)
- **H5 token = entity `updated_at`** — synchronous, bumped by BOTH `patchEntity` and `patchAttributeValue` (the latter's CTE bumps `glossary_entities.updated_at` on every attr edit). NOT `entity_revisions` (async outbox projection — would false-409/miss).
- **Single PATCH target per proposal** — short_description (entity col) OR one attribute value (name/aliases/any attr are all `entity_attribute_values`). Keeps Apply **atomic** (one PATCH, one version check, no partial-apply), reuses battle-tested handlers + triggers (cached_name K2a, short_description K3.3b auto-regen). Multi-field = sequential proposals. *Multi-field-atomic = deferred (would fork the write/trigger logic into a new endpoint).*
- **412 Precondition Failed** on version drift (HTTP-correct for `If-Match`; matches existing D-K8-03 codebase precedent). Spec said 409 — aligning to precedent/HTTP. Code `GLOSS_VERSION_CONFLICT`.
- **If-Match opt-in** — absent header ⇒ unchanged behavior (the `/v1` glossary UI paths don't send it; no regression).
- **Surface** — add `book_context:{book_id}` to the send/resume request; advertise the glossary edit frontend tool when `editor_context OR book_context`. P1/P2 glossary read/propose tools already reach chat via the gateway list-tools.
- **`glossary_propose_entity_edit` is a FRONTEND tool** (browser-executed, suspend/resume) — lives only in chat `frontend_tools.py`; NOT added to the glossary MCP server, NOT gateway-routed.

## Reuse (verified)
- chat: `frontend_tools.py` (FRONTEND_TOOL_NAMES + defs), `is_frontend_tool`, the suspend branch in `stream_service._stream_with_tools` (340-416), `resume_stream_response` (1002+), `ToolResultRequest`.
- glossary: `patchEntity` (tx + outbox emit), `patchAttributeValue` (CTE), `loadEntityDetail` (already returns `updated_at` + per-attr `attr_value_id`).
- FE: `ProposeEditCard` pattern, by-name routing in `AssistantMessage` (133-144), `submitToolResult` in `useChatMessages`, `glossaryApi.patchEntity`/`patchAttributeValue`, `apiJson` (custom headers + throws `{status,code,body}`), BFF already CORS-allows + forwards `If-Match`.

## Build steps
### 1. glossary-service (Go) — If-Match optimistic concurrency
- `patchEntity`: read `If-Match`. When present, add version guard. Inside the existing tx, after the UPDATE returns RowsAffected==0, branch: if `If-Match` present AND entity still exists (in book) ⇒ **412 `GLOSS_VERSION_CONFLICT`**, else 404. Implement by adding `AND updated_at = $base::timestamptz` to the UPDATE WHERE when If-Match present; on 0 rows do an in-tx existence check to pick 412 vs 404.
- `patchAttributeValue`: when `If-Match` present, run a **guarded CTE** (in-SQL, no TOCTOU): the entity-bump UPDATE carries `AND updated_at = $base::timestamptz`; if 0 rows affected (existence already verified by `verifyAttrValueInEntity`) ⇒ **412**. Keep the no-If-Match path exactly as today.
- Tests: `entity_version_test.go` — (a) patchEntity If-Match match→200+bumped, (b) stale→412, (c) no-header→200 (back-comat); `attribute_version_test.go` — match→200, stale→412. DB-backed (`openTestDB`, skip-local) + a non-DB 412-path assertion if feasible.

### 2. chat-service (Python) — frontend tool + surface + truthful resume
- `frontend_tools.py`: add `glossary_propose_entity_edit` to `FRONTEND_TOOL_NAMES` + a `GLOSSARY_PROPOSE_EDIT_TOOL` def. Args: `book_id, entity_id, base_version, target("short_description"|"attribute"), attr_value_id?, field_label, old_value, new_value, rationale?`. Description encodes H6 outcomes (saved/conflict/error/dismissed; claim success only on saved). `frontend_tool_defs(book_scoped: bool)` returns propose_edit (editor only) + glossary edit (book-scoped).
- `models.py`: `SendMessageRequest.book_context: BookContext|None` (book_id). `ToolResultRequest.outcome` doc → `applied_saved|applied_conflict|applied_error|dismissed` (+ legacy applied/dismissed for propose_edit). 
- `stream_service.py`: advertise glossary edit tool when `editor_context or book_context`; thread `book_context` through `stream_response`/`_emit_chat_turn`; resume keeps it advertised (mirror editor_context resumed:true).
- `routers/messages.py`: pass `book_context` into `stream_response`.
- Tests: extend `test_frontend_tools` / a new `test_glossary_edit_tool` — tool advertised iff book_context/editor_context; resume passes through each outcome enum; is_frontend_tool('glossary_propose_entity_edit').

### 3. frontend (React) — shared diff card + version-checked Apply + surface
- `components/GlossaryDiffCard.tsx` (shared, mount per surface): renders field_label + old→new (strike old / highlight new) + rationale + Apply/Dismiss. Apply: target=short_description → `patchEntity(..., {short_description:new}, {ifMatch:base_version})`; target=attribute → `patchAttributeValue(..., attrValueId, {original_value:new}, {ifMatch:base_version})`. Map result → outcome: ok→`applied_saved`; `status===412||409`→`applied_conflict` (toast "changed since proposed — re-open"); else→`applied_error`. Then `submitToolResult(runId, toolCallId, outcome)`.
- `glossary/api.ts`: add optional `ifMatch` to `patchEntity`/`patchAttributeValue` → set `headers:{'If-Match':ifMatch}`.
- `chat/api.ts` + `useChatMessages`: `submitToolResult` outcome type widened to the enum; `streamPost` sends `book_context` when provided; `useChatMessages(sessionId, editorContext?, composeMode?, bookContext?)`.
- `AssistantMessage.tsx`: route `pending && tool==='glossary_propose_entity_edit'` → `GlossaryDiffCard` (H15), keep propose_edit → ProposeEditCard.
- Glossary page chat: pass `bookContext={book_id}` so the edit tool is advertised + the card renders there.
- i18n: `glossaryEdit.*` keys ×4 (en/vi/ja/zh-TW) — label/apply/dismiss/applied/conflict/error.
- Tests: `useChatMessages.glossaryEdit.test` (book_context sent; resume outcome enum) + a `GlossaryDiffCard` render/apply/409 test.

### 4. VERIFY
- glossary `go build ./... && go test ./internal/api/...` (DB tests skip locally / run CI).
- chat `pytest` (frontend-tool + resume).
- FE `vitest` + `tsc --noEmit` + i18n parity.
- **Cross-service live-smoke token** (≥2 services: chat+glossary+BFF+FE) — attempt a real stack-up Apply→412 on drift; else `LIVE-SMOKE deferred to D-GLOSSARY-EDIT-LIVE-SMOKE` or `live infra unavailable`.

## AC (§18 P3 DoD)
AC1 frontend tool advertised/suspends (reuse machinery) · AC2 **H5** version-checked Apply → 412 on drift · AC3 **H6** truthful resume (4-outcome enum, success only on saved) · AC4 **H15** by-name card routing · AC5 shared diff card (mount per surface) · AC6 INV-1/SEC-4 never auto-commits · AC7 If-Match opt-in (no /v1 regression).

## Risks
- TOCTOU in attribute guard → closed by in-SQL guarded CTE (not select-then-update).
- `updated_at` RFC3339 round-trip exactness (PG µs ↔ Go RFC3339Nano) — verified equal; document as the version-token contract.
- Coarse token = any intervening write (even unrelated field) → 412 (correct optimistic-concurrency; user re-opens). Acceptable.
- Partial-apply impossible (single PATCH per proposal).
- Multi-field-atomic deferred → **D-GLOSSARY-EDIT-ATOMIC**.
