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
| SP-0a | Python `mcp` pin → 1.28.1 (chat + knowledge) | **DONE** | containers already run 1.28.1; native elicitation+tasks present |
| SP-0b | Go 5 svcs `go-sdk` v1.6.1 → v1.7.0-pre.3 | **DONE** | all build + full test suites green; only a new transitive dep (x/time/rate) |
| SP-0c | ai-gateway TS `sdk@1.29.0` → `server`+`client@2.0.0-beta.4` | **NEEDS-DECISION** | NOT a repackage — a real API redesign of the load-bearing gateway proxy (setRequestHandler method-string, web-standard transport, ctx shape). Client side trivial; server side a rewrite. |
| SP-0 | (spike done — capability matrix above) | **DONE** | betas verified; D2 revised then user-ratified to adopt anyway |

## Decisions register (append as sealed)
- 2026-07-19 · **D2 FINAL (user-ratified 2026-07-19):** despite SP-0 evidence that betas aren't needed for
  capability, the user chose to **adopt the betas anyway** (future-proofing toward the 2026-07-28 RC, dev-phase).
  Execute incrementally, lowest-risk-first, gated: **SP-0a** Python → pin `mcp==1.28.1` (no v2 exists; latest 1.x);
  **SP-0b** Go 5 svcs `v1.6.1` → `v1.7.0-pre.3` (same module path); **SP-0c** ai-gateway TS `sdk@1.29.0` →
  `@modelcontextprotocol/server`+`client@2.0.0-beta.4` (repackaging — the real migration). Build+test gate each;
  live MCP round-trip at the end.
- 2026-07-19 · Sequencing: run **Phase 0 first** (root-cause fix, live-E2E-able, no SDK churn); SP-0 beta adoption deferred/parked because it blocks nothing in Phase 0 and destabilizes a live dev platform.
- 2026-07-19 · Phase-0 validator location: `frontend_tools.py::validate_frontend_tool_args(name, args, tool_def)` (keeps schema + validation together — the migration thesis).
- 2026-07-19 · Streak integration: a frontend-tool validation error containing `required: missing properties` feeds the SAME `blank_tool_args_streak` the backend feeds (shared cross-tool flailing counter); mirrors backend reset/increment rule exactly.

## SP-0 empirical findings (2026-07-19) — D2 versions PARTLY WRONG
Verified against live registries:
- **Python `mcp`: NO v2 beta exists on PyPI** — latest is **1.28.1** (1.x line). Spec's `mcp==2.0.0b1` is
  unbuildable. chat-service currently pinned `>=1.9,<2` (installed 1.27.2). ⇒ Python can only move within 1.x;
  the spike must determine whether 1.28.1 already exposes elicitation / tasks.
- **Go `go-sdk`: `v1.7.0-pre.3` available** (newer than spec's pre.1). Currently v1.6.1 across 5 services.
- **TS `@modelcontextprotocol/server`+`client`: `2.0.0-beta.4`** (past spec's beta.1). ai-gateway on `sdk@^1.29.0`.
- **Linchpin:** chat-service (Python, the gate orchestrator) has no v2 → native Tasks/elicitation feasibility
  depends entirely on Python 1.28.1's surface. Spike settles it before any adoption.

## SP-0 CAPABILITY MATRIX (verified 2026-07-19) — D2 OVERTURNED
Spiked each SDK in isolation (installed/introspected, no service changes):

| SDK (current **stable**) | Elicitation (human gate) | Tasks ext (durability) |
|---|---|---|
| Python `mcp` **1.28.1** (chat-service client — ALREADY installed & running in-container) | ✓ `Context.elicit`/`ServerSession.elicit`, form+URL | ✓ experimental: `Task`, `TASK_STATUS_INPUT_REQUIRED`, `tasks/get`, `task_context`/`task_scope` |
| Go `go-sdk` **v1.6.1** (5 domain servers) | ✓ `ServerSession.Elicit` | ✗ (not in v1.6.1 **nor** in v1.7.0-pre.3 beta) |
| TS `@modelcontextprotocol/sdk` **1.29.0** (ai-gateway) | ✓ `ElicitRequest`/`elicitation/create` in types | types present |

**Conclusion: the beta v2 SDKs are NOT needed.** The human-gate primitive (**elicitation**) is on ALL current
stable SDKs; the Tasks extension is on Python stable and irrelevant on Go (absent in stable AND beta), with
`chat_suspended_runs` covering durability regardless. The v2 betas add only stateless-core/MRTR/auth-hardening —
orthogonal to Phases 1-2. Adopting them = cross-service dep-bump + TS repackaging risk for ZERO capability gain.

**Revised recommendation (supersedes D2):** DO NOT adopt beta v2 SDKs. Build Phases 1-2 on current stable SDKs
(native elicitation gate). Optional safe hygiene: tighten chat-service `mcp>=1.9,<2` → `>=1.28,<2` to lock the
version already running (has tasks+elicitation). Go stays v1.6.1; ai-gateway stays sdk 1.29.0.

**Root cause of the wrong D2:** the spec's version research overweighted the 2026-07-28 RC blog and missed that
elicitation (stable since 2025-11-25) + the Tasks extension (experimental) already ship in the CURRENT stable SDKs.

### CORRECTION (2026-07-19, after user pointed to the actual releases)
My "no Python v2 exists" claim above was **WRONG** — a methodology error (`pip index versions mcp` hides
pre-releases; `--pre` reveals **`2.0.0b2, 2.0.0b1, 2.0.0a3/a2/a1`**). The Python beta v2 **exists** and installs.
**But adopting v2 is a major rewrite, not a pin:**
- **`mcp.server.fastmcp` is REMOVED in v2** (replaced by a new `MCPServer`/`McpServer` high-level API). The shared
  `loreweave_mcp` kit + **6 Python services** build their MCP servers on `FastMCP` via `@mcp_server.tool()` — ~9.3k
  lines (composition 5686, knowledge 1829, translation 1190, jobs 446, lore-enrichment 147, + chat client).
- Client: `mcp.client.streamable_http.streamablehttp_client` → **`streamable_http_client`** (rename); httpx→httpx2.
- `ClientSession`, `transport_security.TransportSecuritySettings` survive.

**DECISION (user-ratified 2026-07-19): SKIP the v2 migration for now; continue to Phase 1 on stable.** Rationale:
zero capability gain (elicitation already on stable 1.28.1, FastMCP intact), stable v2 lands **2026-07-28** (building
against the moving beta risks re-work), and Phase 1 (the actual bug-driven value) is buildable now on stable.
**When we DO adopt v2** (best after the 2026-07-28 stable): do it via a **FastMCP→MCPServer ADAPTER inside the
`loreweave_mcp` kit** — the single chokepoint (`make_stateless_fastmcp`) — so the 6 services stay untouched behind
the same `@mcp_server.tool()` facade. SP-0a keeps the stable 1.28.1 pin (valid; FastMCP intact); SP-0b Go pre.3
stays (harmless; Go has no v2); SP-0c gateway rewrite deferred with the rest.

## PHASE 1 FEASIBILITY FINDING (2026-07-19) — the real blocker is the GATEWAY, not the SDKs
Verified in ai-gateway src: the proxy has **zero elicitation handling**. The inbound proxy Server advertises
capabilities `{tools, resources, prompts}` only (no `elicitation`), and the per-call federation `Client`s
(`executeTool`/`readResource`/`getPrompt`) are built with no elicitation capability and no server→client
request-relay. So a domain MCP tool calling `ServerSession.Elicit(...)` mid-call has nowhere to send it — the
**native elicitation human-gate cannot flow through the current gateway**, regardless of SDK version.

**Consequence:** Phases 1-2 (and by extension the "native gate" end-state of the whole migration) are gated on
building **bidirectional elicitation relay through the stateless per-request proxy** (domain server → federation
client → proxy server → chat client) — a substantial, LOAD-BEARING gateway build. It is buildable (unbuilt infra,
not externally blocked), but it is big + risky + delivers **no new user-facing capability**: the human gate ALREADY
works today via the `confirm_token` + frontend-tool-suspend pattern (which Phase 0 just hardened with validation).

**So the value calculus for the rest of the migration:** Phase 0 fixed the actual reported bug. Phases 1-4 are an
architectural migration (move the gate from the working confirm_token/suspend pattern onto native MCP elicitation),
whose prerequisite is a risky gateway elicitation-relay build — same "big re-architecture, zero capability gain"
shape as the deferred v2 adoption. **Recommendation: treat Phase 0 as the shipped value; defer the
elicitation-relay-dependent Phases 1-2 as a deliberate, planned gateway slice (authorize explicitly).** Phase 3
(ui_* → ai-gateway-local directive tools, NO human gate) is the one remaining phase that does NOT need the relay.

## Parked / debt register
- Go native Tasks durability (if ever wanted) — not in Go stable or beta today; `chat_suspended_runs` bridges it. Revisit if Go tasks ships.
- **ai-gateway elicitation relay** — prerequisite for native Phases 1-2; unbuilt, load-bearing, no new capability. Deferred pending explicit authorization.

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
