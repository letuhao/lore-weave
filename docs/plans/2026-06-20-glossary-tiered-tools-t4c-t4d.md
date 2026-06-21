# Plan — T4c chat-service AdminContext + T4d CMS admin chat panel → CP-6

**Epic:** Glossary Assistant Tiered MCP Tools. **Spec:** [`…tiered-tools.md`](../specs/2026-06-20-glossary-assistant-tiered-tools.md) §4b/§4c, §6.4/§6.7, §11 #4/#7, §12.1/12.2, INV-T2/T6, E17. **Buildplan:** [`…buildplan.md`](2026-06-20-glossary-assistant-tiered-tools-buildplan.md) §7 (T4c/T4d), §10.
**Depends:** CP-5 (T4a glossary `/mcp/admin` + T4b gateway `/mcp/admin`, both committed `3e91ae93`).
**Scope decision (CLARIFY, user-chosen):** FULL CMS panel (not minimal, not deferred) — port the main-FE SSE/suspend-resume infra into cms-frontend.

## Invariants this milestone must hold
- **INV-T2** — admin authority = RS256 `admin:write` in `X-Admin-Token`, NEVER `X-User-Id`. chat-service forwards the token; it does not synthesize admin authority.
- **INV-T6 / E17 (curation isolation, TESTED not trusted)** — an admin chat surface receives ONLY admin tools (`glossary_admin_*`) + `glossary_confirm_action`; it NEVER receives book/user tools. A book/user surface NEVER receives admin tools and NEVER dials `/mcp/admin`.
- **§6.7 / §11 #7** — `X-Admin-Token` is a bearer credential: never logged in chat-service (or any hop). Redact in every envelope/dump.
- **INV-T3** — admin propose tools mint a confirm-token only; the System write happens at `/v1/glossary/actions/admin/confirm` after human confirm (the FE confirm card, T4d).

## T4c — chat-service (Python)

### Files
1. **`app/models.py`** — `AdminContext(BaseModel)` marker (no PII; presence = admin surface; optional `label` for UI). Add `admin_context: AdminContext | None = None` to `SendMessageRequest`. (Token arrives as a header, NOT in the body — bearer hygiene.)
2. **`app/routers/messages.py`** — `send_message` + `submit_tool_result`: add `x_admin_token: str | None = Header(default=None)`. Thread `admin_context` (body) + `admin_token` (header) into `stream_response` / `resume_stream_response`. The admin token is SEPARATE from the user bearer consumed by `get_current_user` (the admin is still a logged-in user; admin authority is the extra RS256 token).
3. **`app/client/knowledge_client.py`**
   - `get_admin_tool_definitions(admin_token: str) -> list[dict]` — fetch from `{base}/mcp/admin` with `X-Internal-Token` + `X-Admin-Token`. Cache the CATALOG process-wide (`_admin_tool_definitions`) — the catalog is identical for every admin; only the per-request token varies, so the token is NOT part of the cache key and is NOT cached. Returns `[]` on failure (degrade tool-free, same as the user path). No admin token → return `[]` (can't list).
   - `mcp_execute_tool(..., admin_token: str | None = None)` — when `admin_token` is set, dial `{base}/mcp/admin` with `X-Admin-Token` (+ `X-Internal-Token`), and DO NOT send `X-User-Id` (admin authority is the RS256 token, INV-T2). When absent, unchanged (`/mcp` + `X-User-Id`).
   - Bearer hygiene: the admin token is never passed to `logger.*`. Existing warnings log only `exc`/tool-name shapes — audit they don't dump headers.
4. **`app/services/stream_service.py`**
   - `stream_response(..., admin_context: dict | None = None, admin_token: str | None = None)`.
   - Tool-def selection: **if `admin_context`** → `tool_defs = await knowledge_client.get_admin_tool_definitions(admin_token)` and append ONLY `GLOSSARY_CONFIRM_ACTION_TOOL` (so the agent can surface the System confirm card). Do NOT append `propose_edit` / `glossary_propose_entity_edit` (book/user write-backs) — admin surface curation. The user/book branch is unchanged and never fetches the admin catalog.
   - Skill prompt: inject an admin section (teach the System-tier propose→confirm workflow) when `admin_context` — mirrors the `inject_glossary_skill` gate.
   - `_emit_chat_turn(..., admin_token: str | None = None)`: pass `admin_token` to the backend tool exec call so `glossary_admin_*` route to `/mcp/admin`. `is_frontend_tool` / `glossary_confirm_action` suspend-path unchanged.
   - `resume_stream_response`: thread `admin_token`; on resume re-advertise `glossary_confirm_action` (already does) — gate the book/user frontend tools off when it was an admin surface (carry an `admin` flag in the suspended-run row, OR re-derive from the resume request's `X-Admin-Token`). Simplest: the resume request re-sends `X-Admin-Token`; if present, use the admin catalog + only `glossary_confirm_action`.
5. **`app/services/glossary_skill.py`** — add the admin-surface prompt section (System-tier: read standards, propose create/patch/delete by CODE, always confirm; never claim a write before `action_done`).
6. **Tests** (`tests/`):
   - `test_admin_surface_curation` — admin_context → tool_defs are admin-only + `glossary_confirm_action`; assert NO `glossary_propose_entity_edit` / `propose_edit` / user/book tool names. (E17 half 1.)
   - `test_book_surface_no_admin` — book_context → NO `glossary_admin_*` names; never calls `/mcp/admin`. (E17 half 2.)
   - `test_admin_exec_routes_to_admin_endpoint` — `mcp_execute_tool(admin_token=…)` dials `/mcp/admin`, sends `X-Admin-Token`, sends NO `X-User-Id`. (INV-T2.)
   - `test_admin_token_never_logged` — capture logs across a failing admin fetch/exec; assert the token string never appears.
   - `test_admin_no_token_degrades` — admin_context but no `X-Admin-Token` → empty tool_defs (no crash, no leak).

### VERIFY (T4c)
`pytest` green incl. the 5 new tests; existing chat suite unchanged. Cross-service token: a live federation smoke is folded into CP-6.

## T4d — cms-frontend (TypeScript) — FULL panel

### Approach: port-not-reinvent
cms-frontend is pure CRUD with NO streaming ([`cms-frontend/src/api.ts`](../../cms-frontend/src/api.ts)). The main FE has reusable SSE infra: `frontend/src/features/chat/useChatMessages.ts`, the `x-loreweave-stream-format: agui` parser, and the suspend/resume protocol. T4d ports a minimal-but-complete version keyed to the `cms_auth` admin token.

### Files (mini-design at BUILD; React-MVC per CLAUDE.md)
- `cms-frontend/src/features/admin-chat/` — `hooks/` (controller: SSE stream, suspend/resume, send), `components/` (AdminChatPanel, message list, AdminConfirmCard), `api.ts` (POST message w/ `X-Admin-Token` from `cms_auth`; POST confirm → `/v1/glossary/actions/admin/confirm`; preview → `/actions/admin/preview`), `types.ts`.
- The agui stream parser ported from the main FE (text deltas, tool_call events, suspend/resume frames).
- **AdminConfirmCard** — renders the System-tier confirm card keyed on the `system_*` descriptor; on Confirm POSTs the `confirm_token` to `/v1/glossary/actions/admin/confirm` (NOT the user `/actions/confirm`); the endpoint is chosen by descriptor authority. Surfaces `action_done` / `token_expired` / `action_error` / `cancelled` back to resume.
- Admin token wiring: read RS256 from `cms_auth` localStorage (already minted via `/v1/admin/session`); attach as `X-Admin-Token`. On 401 (token expired mid-session) → re-exchange via `/v1/admin/session` (A5) OR surface a re-auth prompt (decide at BUILD; minimal = re-auth prompt, track `D-T4D-ADMIN-TOKEN-REFRESH` if deferred).

### VERIFY (T4d / CP-6)
- cms-frontend typecheck/build green; component tests for AdminConfirmCard endpoint selection (admin descriptor → admin confirm endpoint) + curation (panel only advertises what chat-service returns).
- **CP-6 end-to-end live-smoke:** cms chat → "add a steampunk system genre" → propose mints card → human Confirm → System write lands; a non-admin chat can neither see nor reach admin tools (INV-T6 end-to-end). `/review-impl` already ran on the T4 auth boundary at CP-5; re-confirm no regression.

## Deferred (carry-in / new)
- `D-T4-ADMIN-PREVIEW-CURRENTSTATE` (from CP-5) — admin preview echoes token params vs re-rendering current state; T4d's confirm card uses `/actions/admin/preview` so this is where it's resolved or consciously accepted.
- `D-T4D-ADMIN-TOKEN-REFRESH` (potential) — transparent admin-token re-exchange on 401 mid-conversation; minimal v1 may surface a re-auth prompt instead.

## Risk boundaries (checkpoint/commit cadence)
1. **T4c complete + pytest green** → commit (chat-service backend; safe to land before the FE).
2. **T4d complete + CP-6 live-smoke** → commit (the FE panel + end-to-end proof).
3. POST-REVIEW at CP-6 (the shippable admin-end-to-end boundary).
