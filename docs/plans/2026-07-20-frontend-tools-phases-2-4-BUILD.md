# Frontend-Tools Migration — Phases 2–4 BUILD plan (2026-07-20)

Spec: [`docs/specs/2026-07-19-frontend-tools-mcp-migration.md`](../specs/2026-07-19-frontend-tools-mcp-migration.md).
Decision (2026-07-20): **full staged refactor** — build Phases 2, 3, 4, each with its own
`/review-impl` + a real E2E, accepting that the correctness root-cause is already banked by
Phase 0 (the win here is architectural: retire the chat-service-local parallel construct so
`tools/list` is the single contract).

## Commitment / invariants (re-read after any compaction)

- **The contract stays the SoT.** `contracts/frontend-tools.contract.json` is the single
  schema source for every frontend tool. A new consumer (ai-gateway) READS it — it does not
  re-declare the schemas (the "one name for one concept" rule; the machine-check must still
  hold both/all sides).
- **No silent no-op, ever.** A `ui_*` tool with an out-of-enum arg must return a tool ERROR
  (the `required`/`enum` signal), never resolve to nothing. This is the exact bug the spec
  exists to kill; every slice keeps a test that proves it.
- **No UX regression.** `ui_*` are resolve-immediately today (no human gate); they stay that
  way. The mechanism moves from "chat-service frontend-tool suspend → FE resolves" to
  "ai-gateway returns a directive → FE acts on the tool result". The user-visible behavior
  (agent navigates the app) is unchanged.
- **Capability parity before retirement.** A construct is retired (Phase 4) only after its
  MCP-native replacement is proven live for every domain that used it.

## Enum-SoT decision (the crux)

ai-gateway must validate `ui_*` args (the `panel_id` enum lives in the contract, not in
ai-gateway). **Constraint found:** ai-gateway's Docker build context is `services/ai-gateway`,
so the repo-root `contracts/frontend-tools.contract.json` is NOT in the image at runtime —
ai-gateway cannot read it live. Decision: **commit a `ui-tools.ts` mirror in ai-gateway** (the
7 `ui_*` schemas as TS constants) + a **vitest drift test** that reads the repo-root contract
(relative path — runs in the repo checkout, not the image) and asserts the mirror == the
contract's `ui_*` slice. The contract stays the single SoT; the mirror is a machine-checked
polyglot copy (same pattern as the other cross-language mirrors). ai-gateway exposes them as
consumer-local tools (the `tool_list`/`tool_load`/`find_tools` shape in `mcp/handlers.ts`, no
downstream provider).

## Slices (each: build → review-impl → E2E → commit)

### Phase 3 — `ui_*` → ai-gateway-local validated directive tools

- **P3.1 (ai-gateway)** — load the `ui_*` contract slice; prepend them to `handleListTools`;
  in `handleCallTool`, dispatch `ui_*` locally: validate args against the schema (enum/
  allowlist) → return `{ structuredContent: { directive: { tool, args } } }`; invalid →
  `toolErrorEnvelope`. Unit tests: valid → directive; out-of-enum `panel_id` → error (no
  silent no-op); drift test vs the contract.
- **P3.2 + P3.3 = ONE ATOMIC CUTOVER** (found 2026-07-20 during scoping — they cannot ship
  independently without breaking nav or guessing the emission shape):
  - *P3.2 (chat-service)* — remove `ui_*` from `FRONTEND_TOOL_NAMES`/`is_frontend_tool` so they
    stop being intercepted at the suspend seam and route to ai-gateway (federated), which returns
    the `io.loreweave/ui-directive`. **Preserve the F7c nav-intent FILTER**: `ui_open_studio_panel`
    must be filtered OUT of the advertised federated catalog on non-nav-intent turns (else +880
    tok/turn regression) — move `_is_panel_nav_intent` from a frontend-tool ADD-condition to a
    catalog FILTER. The directive rides the normal `TOOL_CALL_RESULT` event (`e.content` = the
    directive JSON).
  - *P3.3 (FE)* — a new additive executor acts on a `ToolCallRecord.result.type ===
    'io.loreweave/ui-directive'` (reuse `resolveUiTool`/`uiNavScope` from the suspend path),
    idempotent by `toolCallId`; retire the `ui_*` branch of `useUiToolExecutor` (the suspend
    path). Coexists cleanly — the suspend path is simply no longer fed once P3.2 stops suspending.
  - *Why atomic:* P3.2 alone returns a directive the FE ignores (nav breaks); P3.3 alone can't be
    tested without knowing P3.2's emission shape. Ship + browser-E2E together.
  - **Emission shape (traced):** `runChatStream` TOOL_CALL_RESULT handler JSON-parses `e.content`
    → `ToolCallRecord.result`. P3.2 must ensure the ui_* result's `e.content` is the directive
    JSON (`{type, tool, args}`) so the FE's `result.type` check fires.
- **P3.4 (E2E)** — browser: an agent turn that calls `ui_navigate` navigates the app; an
  out-of-enum `ui_open_studio_panel` surfaces an error, not a silent no-op.

### Phase 2 — `propose_edit` (KIND B) → task-shaped + elicitation

- **P2.1** — `propose_edit` becomes task-shaped via the durable gate: the proposed text rides
  as task content (`input_required`); accept → the FE applies it to the editor (client
  effect), decline/cancel otherwise; optional scalar edit via an elicitation `string`. Reuses
  the `TaskConfirmCard`/gate the durable-gate track built. E2E through the real loop.

### Phase 4 — retire duplication

- **P4.1** — once every KIND-A/B/C construct is MCP-native + proven, remove the retired
  `frontend_tools.py` schemas, the parallel advertisement, and the now-single-consumer parts
  of `frontend-tools.contract.json`; update `docs/standards/mcp-tool-io.md`. Guard: the
  contract drift test + a "no orphaned frontend-tool name" test.

## Registers (append as we go)

- **Decisions:**
  - enum-SoT = ai-gateway commits a `ui-tools.ts` mirror + a vitest drift test vs the contract
    (ai-gateway can't read the repo-root contract at runtime; Docker context = the service dir).
  - **F7c-collision split (found 2026-07-20):** Phase 3 collides with F7c's turn-context
    advertisement gating — `_is_panel_nav_intent` (advertise `ui_open_studio_panel` only on a
    nav-intent turn, saving ~880 tok) + the compact-variant description are per-turn, chat-service
    concerns a stateless ai-gateway can't replicate. Split: **ai-gateway owns the `ui_*` DEFINITION
    + VALIDATION + EXECUTION (directive); chat-service keeps the per-turn advertisement FILTER**
    (it already filters which federated tools to advertise — the nav-intent gate stays a consumer
    concern, keyed on the tool name, now sourced from the federated catalog). No default token
    regression: the full description is the default (compact A/B is `settings.compact_studio_panel_desc`,
    default OFF).
- **Parked:** —
- **Debt:**
  - `D-F7C-ADVERTISE-SNAPSHOT-STALE` (pre-existing, unrelated track).
  - `D-P3-COMPACT-PANEL-DESC` — the F7c compact-`panel_id`-description A/B (default OFF) is not ported
    to ai-gateway in P3; revisit if the A/B is ever turned on (re-implement as an ai-gateway variant
    or drop the experiment).
- **Drift:** —
