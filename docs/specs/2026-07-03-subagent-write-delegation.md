# Spec — Subagent Write Delegation · D-REG-P5-SUBAGENT-WRITE-DELEGATION

**Status:** ✅ SHIPPED 2026-07-03. Extends the subagent runtime
([`2026-07-03-subagent-runtime.md`](2026-07-03-subagent-runtime.md), `_run_subagent_call` +
`_stream_with_tools` in `stream_service.py`). Owner surface: chat-service.

> **Design pivot (2026-07-03).** The original draft proposed a heavy *nested-suspend / two-level
> resume* so a subagent's write could reach the human `tool_approval` card. A capability audit
> (SESSION note below) showed that was **over-engineered for safety**: tenancy is enforced at the
> **tool layer** (every MCP tool re-authenticates the `X-User-Id`+internal-token envelope and
> grant-gates its scope; destructive/priced Tier-W ops are mint→human-JWT-confirm only, structurally
> unable to execute from an agent loop). So a subagent write is **safe by construction** — bounded to
> the same tenant's data the caller could already touch, and to the subagent's `tool_scope` whitelist.
> The read-only clamp was a *conservative default*, not the security boundary. The shipped design is
> therefore the **simpler** one below; the nested-suspend machinery was **not built** (and isn't
> needed).

---

## 1. Problem

The v1 subagent was clamped read-only (`permission_mode='ask'`), so a persona could read + reason
but never perform a write — even a write the caller could do and even in a write-mode turn.

## 2. What "safe" rests on (why this is simple)

The two invariants that make write-delegation safe were verified against code, not assumed:
1. **Tool-layer tenancy is absolute.** Each MCP tool resolves identity from the trusted envelope
   (never a model arg — `ForbidExtra` blocks smuggling), then gates the target by scope
   (book→grant VIEW/EDIT/MANAGE/OWNER, user→owner-equality, project→owner-keyed). 403/404 collapse
   (anti-oracle). Centralised in the shared Go/Python MCP kits.
2. **Destructive/priced writes can't execute from a loop.** Tier-W/S tools only MINT an HMAC
   confirm-token; the real write is a browser-JWT-only `/actions/confirm` route (no agent-mintable
   JWT). A headless sub-run additionally can't call `confirm_action` (a frontend tool, excluded from
   every subagent scope), so it cannot complete a Tier-W op even by minting a token.

Given those, the only thing left to decide is **consent**: does the caller's turn permit writes, and
which writes may auto-commit without a per-call human prompt.

## 3. Shipped design — "allowlisted Tier-A, no suspend"

1. **Clamp `= min(caller, write)`** — `clamp_permission_mode(caller_mode)` in `subagent_runtime.py`:
   `write` only when the caller's turn is a write turn; `ask`/`plan` keep the sub-run read-only. A
   subagent can never EXCEED the caller (no escalation); `plan` collapses to `ask` (a subagent never
   authors plan artifacts). Wired at the `_run_subagent_call` call site (`caller_permission_mode=
   permission_mode`) and used as the nested `_stream_with_tools`'s `permission_mode`.
2. **Real tier in the plain path.** `_stream_with_tools` previously hardcoded `tier="R"` on the
   non-discovery (subagent) path; fixed to read the true tier from `plain_index` — otherwise a
   write-mode subagent would auto-commit ANY Tier-A tool unchecked. (Discovery/main-turn path
   unchanged.)
3. **Allowlisted Tier-A auto-commits; un-allowlisted returns a `result.error`.** In a write sub-run
   (`subagent_depth>0`), an **allowlisted** Tier-A tool (its `approval_check` passes) auto-commits in
   scope exactly like the main turn. An **un-allowlisted** Tier-A tool — which on the main turn would
   raise the one-time `tool_approval` suspend — instead returns a self-correctable `result.error`
   ("not pre-approved; a subagent can't request approval"), because a headless sub-run has no client
   to answer the card. Same treatment for a `require_approval` **hook** inside a sub-run. No silent
   no-op, no swallowed suspend.
4. **Everything else unchanged.** `tool_scope` whitelist (advertise + execute), depth cap 1,
   frontend/meta tool exclusion, Tier-W mint-only, token attribution — all as v1.

## 4. What did NOT change (and why the alternative was dropped)
- **No `subagent_frame`, no two-level resume, no `suspended_runs` migration.** The nested-suspend
  path existed only to route a delegated write through the human card; since the write is already
  tenancy-safe and un-allowlisted writes simply don't run, the card is unnecessary. Dropping it
  removes a novel, security-critical suspend/resume surface.
- **Consent model:** granting a subagent a write-mode turn + a `tool_scope` + allowlisting the tools
  IS the consent. The human still gates any *new* tool via the normal main-turn approval before it
  can be delegated.

## 5. Testing (shipped)
- `test_subagent_call.py`: `clamp_permission_mode` — write caller → `write`; ask/plan → `ask`
  (never exceeds caller).
- `test_subagent_loop_scope.py::TestWriteDelegation`: (a) allowlisted Tier-A **executes** in a write
  sub-run (real `mcp_execute_tool` await, no suspend); (b) un-allowlisted Tier-A returns a
  `result.error` ("not pre-approved"), **does not execute, does not suspend**, and the sub-model
  receives the error result.
- Regression: full `test_permission_modes` + `test_stream_tools` + `test_plan_mode` green (the
  tier-resolution change touches the shared loop).

## 6. Follow-up (tracked, not blocking)
- **Live E2E-P5-D** (optional): a `book-editor` persona (`tool_scope=["book_*"]`) in a write turn →
  delegates an allowlisted `book_chapter_save_draft` → the draft really lands (tenancy-scoped);
  un-allowlisted `book_delete` (Tier-W) → mints a token it cannot confirm → no delete. Deferred to a
  live-smoke pass; the loop behaviour is unit-proven.
