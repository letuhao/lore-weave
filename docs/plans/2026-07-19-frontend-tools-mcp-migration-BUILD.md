# BUILD PLAN + RUN-STATE — Frontend-tools → MCP migration

- **Spec (sealed):** [`docs/specs/2026-07-19-frontend-tools-mcp-migration.md`](../specs/2026-07-19-frontend-tools-mcp-migration.md)
- **Goal (this run):** implement the sealed spec in multiple **slices**; each slice = review-impl + QC + bug-fix + a **real live E2E** that proves it works.
- **Branch:** builds on `fix/chat-persist-checkpoints` (persist fix committed there).
- **Re-read this file first after any compaction.**

## Commitment / invariants (do not re-litigate from memory)
1. Every agent-invocable capability is a **server-side MCP tool** → inherits schema + validation + discovery.
2. Human gate + durability = **Tasks + Elicitation** shape (native later; `chat_suspended_runs` bridges durability until SP-0 confirms native Tasks).
3. **Phase 0 validator is the standard `Draft202012Validator` against each tool's canonical `inputSchema`** — NOT a hand-rolled check (distinct from the reverted hotfix).
4. Fail-open: a validator that cannot judge a call (no schema) must never block it.
5. No destabilizing beta-SDK bump as slice 1 — SP-0 (beta adoption) is tracked separately; it blocks nothing in Phase 0.

## Slice board (done = evidence string)
| # | Slice | State | Evidence |
|---|---|---|---|
| S1 | **Phase 0 — MCP-native validation seam** (reject bad frontend-tool args before suspend; standard `required: missing properties` signal) | **DONE (live-E2E proven)** | 149 mock + 15 validator/seam tests; live HTTP E2E both paths |
| S2 | Phase 1 — KIND C → native MCP + task-shaped gate | pending | — |
| S3 | Phase 2 — KIND B (`propose_edit`) → MCP tool + elicitation | pending | — |
| S4 | Phase 3 — KIND A (`ui_*`) → validated directive tools (ai-gateway-local) | pending | — |
| S5 | Phase 4 — retire `frontend_tools.py` schemas + contract; `tools/list` = single contract | pending | — |
| SP-0 | Beta v2 SDK spike + adoption (Tasks/elicitation-send/MCP-Apps capability matrix) | parked | informs S2–S5; blocks none |

## Decisions register (append as sealed)
- 2026-07-19 · Sequencing: run **Phase 0 first** (root-cause fix, live-E2E-able, no SDK churn); SP-0 beta adoption deferred/parked because it blocks nothing in Phase 0 and destabilizes a live dev platform.
- 2026-07-19 · Phase-0 validator location: `frontend_tools.py::validate_frontend_tool_args(name, args, tool_def)` (keeps schema + validation together — the migration thesis).
- 2026-07-19 · Streak integration: a frontend-tool validation error containing `required: missing properties` feeds the SAME `blank_tool_args_streak` the backend feeds (shared cross-tool flailing counter); mirrors backend reset/increment rule exactly.

## Parked / debt register
- SP-0 beta-SDK adoption (Python `2.0.0b1`, Go `v1.7.0-pre.1`, TS `server`+`client@2.0.0-beta.1`) — parked; do before native-Tasks work.

## Drift log (record near-misses honestly)
- 2026-07-19 · Pre-existing, unrelated failure found during S1 VERIFY:
  `test_plan_mode.py::TestPlanSkillAutoInject::test_plan_mode_with_pins_appends_plan_forge`
  asserts `codes == ["glossary", "plan_forge"]` but a `glossary_shaping` companion skill now
  auto-appends → `["glossary","glossary_shaping","plan_forge"]`. **Confirmed fails on baseline
  (git-stash of my diff) → NOT caused by this slice.** Out of scope (plan-mode skill injection,
  different subsystem — defer gate #1). Tracked in SESSION_HANDOFF Deferred; not fixed in S1.
- 2026-07-19 · Some chat-service suites (`test_permission_modes`, part of `test_plan_mode`, K21B
  tool tests) HANG on real network/embedding-service calls at dev time — pre-existing (noted in
  the persist-fix session). My change is chat-service-local and covered by 149 mock-based tests +
  2 integration seam tests; those network suites don't touch the frontend-tool seam.

## REVIEW (S1) — /review-impl findings + resolution
- **MED [completeness]** — the seam's `_fe_def` fallback (`generic_frontend_tool_def`) omitted the two
  book-scoped glossary tools → they'd fail-open (skip validation) when called-but-not-advertised.
  **FIXED:** added `frontend_tool_def_by_name` (complete map) as the seam fallback.
- **LOW [enforcement]** — no test asserted every frontend tool resolves to a validatable schema.
  **FIXED:** `test_every_frontend_tool_name_resolves_to_a_validatable_schema` iterates FRONTEND_TOOL_NAMES.
- **Regression check (cleared):** confirmed `GlossaryDiffCard`/`ui_*`/`propose_edit` read every required arg
  from `record.args` (FE never supplies book_id/resource_ref from context — GlossaryDiffCard comment:
  "schema makes this unreachable"), so requiring them cannot false-reject a legitimate call.
- **Standards gate:** [Frontend-Tool Contract] strengthened (runtime enum enforcement); provider-gateway /
  model-names / tenancy / language / secrets / gateway untouched (pure chat-service-internal, no new I/O).

## VERIFY evidence (S1)
- `test_frontend_tool_validation.py` — 12 new unit tests (incident payload, enum, additionalProperties, fail-open) PASS.
- `test_stream_tools.py::TestFrontendToolValidationSeam` — 2 new integration tests driving the REAL
  `_stream_with_tools` seam: bad args → `tool_call ok:False` + `required: missing properties` + NO
  suspend + run continues; valid args → still suspends. PASS.
- 149 mock-based chat-service tests PASS together (stream_tools, frontend_tool_validation,
  frontend_tools, frontend_tools_contract, terminal_persist, message_read).

## LIVE E2E evidence (S1) — real gateway → live chat-service (my code deployed) → lm_studio
Deployed the 2 changed files into `infra-chat-service-1` (docker cp + restart; health 200, clean boot).
- **In-container deterministic proof** — the exact production `validate_frontend_tool_args` in the live
  container rejects the 019f771a payload: `required: missing properties: ['operation', 'text']; Additional
  properties are not allowed (...)`; valid call → None; all 12 frontend tools resolve to a schema.
- **Live HTTP valid path** — real turn (test account, Gemma-4 26B, editor_context) → model sent
  `{"operation":"insert_at_cursor","text":"The rain fell softly..."}` → passed the seam → `suspended` +
  `pendingToolCall` (a proper Apply card).
- **Live HTTP invalid path (the bug)** — model instructed to send malformed args → sent
  `{"base_version":"v1","domain":"book"}` (the incident shape) → `TOOL_CALL_RESULT {"ok":false,"error":
  "invalid arguments for \"propose_edit\": required: missing properties: ['operation','text']; ..."}` →
  **0 `suspended`, 0 `pendingToolCall`** = NO un-appliable card. Bug fixed end-to-end.

> NOTE: the live container was hot-patched (docker cp) for the E2E; the image rebuild bakes the committed
> source on next `compose build` — a deploy step, not part of this commit.
