# Plan — MCP-Tasks durable gate: FULL ACTIVATION track

- **Date:** 2026-07-20
- **Owner specs:** [`2026-07-19-mcp-tasks-durable-gate.md`](../specs/2026-07-19-mcp-tasks-durable-gate.md) · [`2026-07-19-frontend-tools-mcp-migration.md`](../specs/2026-07-19-frontend-tools-mcp-migration.md)
- **Trigger:** user chose "Full activation track" (2026-07-20) after the completeness audit. This finishes the two specs past the `tasks_gate_enabled` activation boundary.
- **Size:** XL — 2 SDK kits (Go + Python) + 2+ domain services + chat-service + ai-gateway + DB migrations + a deployment flip. Multi-milestone.

---

## 0. The design correction that reshapes M1 (found in the audit)

The SESSION_HANDOFF called the persistent `TaskStore` **"a drop-in for the same interface."** **It is not.** The current interface persists an **executor CLOSURE**:

```go
Create(descriptor string, executor TaskExecutor, inputRequests any, ttlMs int) (*Task, error)
//                         ^^^^^^^^^^^^^^^^^^^^^^ func(ctx, inputs)(any,error) — closes over the payload
```

A closure **cannot be serialized to a DB row**, so a second replica (or the same replica after a restart/deploy) has no way to run the gated write on accept. In-memory works only because propose+accept happen in the same process. **True multi-replica durability requires evolving the interface** so the durable state is *data*, not a function.

### The fix — the **resolver-registry** pattern (standard durable-saga shape)

The gated write is reconstructed on *any* replica from persisted **data** + a **code-registered resolver**:

1. A domain registers, at startup, a `descriptor → resolver` map where
   `resolver(ctx, payload, inputs) (result, error)` is the real write (today's executor body, but reading its inputs from `payload` instead of a closure).
2. `Create(descriptor, payload, inputRequests, ttlMs)` persists `{task_id, status, descriptor, payload_json, input_requests_json, owner_user_id, ttl, timestamps}` — **no closure**.
3. `ProvideInput(accept)` on any replica: load the row → `resolver := registry[descriptor]` → run `resolver(ctx, payload, inputs)` → persist terminal status+result. The row's single-winner/`resolving` guard (an atomic `UPDATE … WHERE status='input_required'`) is the multi-replica double-confirm guard.

This is a **superset** of the in-memory store: the in-memory store becomes registry-based too (holds rows in a map, same `Create(descriptor, payload, …)` signature), so **in-memory and persistent share ONE interface** and all existing lifecycle tests port over. The payload is exactly the dict each call site *already* builds for the confirm card / HMAC token (book: `{op, book_id, chapter_id}`; composition: the derive payload), so binding "to the confirm/consumed-token layer" (spec §4.3, T3c-REMAINING) falls out naturally — same payload, same execute-by-payload logic.

**Blast radius of the interface change:** both kits' `tasks.{go,py}` (Task: `executor`→`payload`; store: add registry) + `tasks_wire.{go,py}` (`OpenGate`/`GateOrConfirm`: `executor`→`payload`, resolver registered once) + 2 call sites + their unit tests. Additive-then-cutover so nothing breaks mid-refactor.

---

## Milestones (each: TDD → VERIFY → review-impl → live-E2E → commit)

### M1 — resolver-registry interface + persistent stores  *(the prerequisite)*
- **M1a — kit interface evolution (Go + Python), IN-MEMORY still the only impl.** Change `Task.executor`→`payload`; add a `TaskResolverRegistry`; `Create(descriptor, payload, …)`; `OpenGate`/`GateOrConfirm` take `payload` + a registered resolver. Port the 2 call sites + all unit tests. **No behavior change, no persistence yet** — pure shape change, provable by the existing lifecycle tests going green on the new signature. Provider-gate + language-rule clean.
- **M1b — persistent store: book-service (Go).** Migration `mcp_gate_tasks` (book DB); `PgTaskStore` implementing the M1a interface (atomic single-winner `UPDATE`); wire book-service to it. Live-prove propose→accept **across two processes** (or a restart) → the write still commits exactly once; double-accept refused; TTL lapse.
- **M1c — persistent store: composition-service (Python).** Same table in composition DB; `PgTaskStore` (asyncpg); wire composition to it. Live-prove the derive gate across a restart.

### M2 — ACTIVATE (flip `tasks_gate_enabled` + wire the driver)  *(deployment-affecting)*
- chat-service **declares the tasks capability** per-request (`tasks_capability_meta`, currently dormant) behind `tasks_gate_enabled`; the detect→suspend→provide-input driver (already built) goes live.
- ai-gateway forwarding verified for the handle-in-content path (already forwards `task_provide_input`; confirm no `tasks/get` needed for the confirm gate).
- **Full-stack live E2E:** a real agent turn opens the book-delete / composition-derive gate → holds (nothing written) → human Confirm → committed exactly once; Decline → cancelled; across a replica restart mid-hold.
- Setting hygiene (CLAUDE.md settings standard): `tasks_gate_enabled` is a **deploy-time kill-switch/ceiling**, not a per-user knob — keep it a global env flag (correct tier).

### M3 — migrate the remaining KIND-C confirms to task-shaped
- `glossary_confirm_action`, `confirm_action`, `propose_record_edit`, `glossary_propose_entity_edit` → `gate_or_confirm` on their owning domains (glossary Go, book/composition). Each keeps its `confirm_token` fallback (sealed OQ3). Live-E2E each.

### M4 — retire the bespoke construct (frontend-tools Phase 4 / tasks T4)
- Once every KIND-C confirm is task-shaped **and activated**, retire the chat-service-local `confirm_action`/`glossary_confirm_action`/`propose_record_edit`/`propose_edit`/studio-`ui_*` **advertisement** defs (source from the catalog) + delete `frontend-tools.contract.json`; `tools/list` is the single contract. Update `docs/standards/mcp-tool-io.md`.

---

## Decisions (SEALED 2026-07-20 — user-confirmed)
- **D-A (architecture) → SEALED: resolver-registry.** Evolve `TaskStore` to persist `{descriptor, payload}` + a startup-registered `descriptor → resolver` map; in-memory + persistent share ONE interface; the non-persistable closure is removed. The only multi-replica-correct shape; spec-intended.
- **D-B (table) → SEALED:** one `mcp_gate_tasks` table per domain DB (book, composition, later glossary), NOT a shared chat-side table (domain owns its task state — spec OQ5). Reuses each domain's existing migration runner. Scope key: `owner_user_id` (tenancy).
- **D-C (rollout of the flip) → SEALED:** `tasks_gate_enabled` stays a **global deploy-time flag** (kill-switch/ceiling tier, not a per-user knob), flipped on only after M1b/M1c land (multi-replica-safe).

## Cadence (user-directed 2026-07-20)
**Checkpoint per milestone.** Each milestone: TDD → QC → real live-E2E → review-impl → commit, **then STOP** and present. The user sets a fresh `/goal` per milestone; the agent does NOT auto-advance to the next milestone. The actual production flip (M2) is a separate deploy step the user owns.

---

## RUN-STATE (living; re-read after any compaction)
- **Commitment:** finish both specs past activation, multi-replica-correct, each slice review-impl'd + live-E2E'd.
- **Slice board:**
  - **M1a `[x]`** — resolver-registry interface evolution (Go + Python kits), in-memory only. Evidence: Go kit `go test` green (incl. new `TestTaskAcceptWithNoResolverFails`); book-service build + `internal/api` green **including the real /mcp+Postgres DB-E2E** (`mcp_actions_tasks_db_test.go`) — proves the Go call-site resolver preserves behavior; Python kit 100 tests green (incl. `test_accept_with_no_resolver_fails`); composition module imports clean with the derive resolver registered; provider-gate OK.
  - **M1b `[x]`** — book-service persistent `PgTaskStore` + `mcp_gate_tasks` migration. Evidence: migration added to
    `migrate.Up()` and PROVEN to run on startup (drop table → a `dbTestServer→migrate.Up` test recreates it); 5 new
    real-Postgres tests green (`mcp_gate_task_store_db_test.go`): **multi-replica propose-on-A/accept-on-B**, concurrent
    **single-winner** (atomic input_required→working claim), decline, TTL-lapse, cancel-idempotent; the 2 existing T3c
    `/mcp`+Postgres durable-gate tests now exercise `PgTaskStore` end-to-end and pass; full `internal/api` suite green
    WITH the DB (BOOK_TEST_DATABASE_URL). Note: one pre-existing scenes-backfill test fails only in full-suite ordering
    (shared-dev-DB pollution) — passes in isolation, unrelated to M1b (confirmed by stashing migrate.go).
  - **M1c `[x]`** — composition-service persistent `PgTaskStore` (asyncpg) + `mcp_gate_tasks` in `run_migrations`.
    Evidence: 5 new real-Postgres tests green (`tests/integration/db/test_pg_task_store.py` vs
    `loreweave_composition_test`): multi-replica propose-on-A/accept-on-B, concurrent single-winner (`asyncio.gather`),
    decline, TTL-lapse, cancel-idempotent — and the fixture's `run_migrations` CREATED the table (migration wired).
    `PgTaskStore` takes a pool GETTER (built at import before the pool exists); JSONB via `json.dumps`/`::jsonb`;
    owner as `uuid.UUID`. composition module imports clean with the store; kit 100 tests green; provider-gate OK.
    **M1 COMPLETE** — the persistence foundation is done on both domains.
  - **M2 `[~]`** — durable-gate activation MACHINERY complete + owner-check + service-layer live-proven; the
    production flip + browser-card smoke are the explicit remaining ops step (below). Evidence:
    - **Accept-caller ownership check** — implemented (Go book: resolver `ctx`-check; Python: kit `_owner_check` in the
      provide-input tool via `build_tool_context`), 5 kit unit tests, and **LIVE on deployed composition** (real
      `/mcp`→ai-gateway→Postgres): a STRANGER accept → `not_task_owner` with the task untouched (`input_required`); the
      OWNER accept → passes the check, the resolver runs on the persisted `{descriptor,owner,payload}` and the terminal
      outcome persists. ⇒ resolves the M2 owner-check DEBT.
    - **Deployed PgTaskStore + migration-on-startup** — dropped `mcp_gate_tasks`, restarted composition AND book →
      each service's `run_migrations`/`Up` recreated the table on real startup; the composition owner-check E2E ran
      against the deployed `PgTaskStore` (persistent, not in-memory).
    - **Activation switch** — chat-service declares tasks caps when `tasks_gate_enabled` (knowledge_client.py:758);
      the caps→task path is proven (the live `/mcp` test used the identical `tasks_capability_meta()` caps envelope and
      composition returned a durable task). The suspend→resume→provide-input DRIVER is fully unit-covered.
    - **CONSCIOUS DECISION — `tasks_gate_enabled` default stays `False`.** The production flip (default→True) is a
      deploy-time ops decision (sealed D-C; the `confirm_token` fallback is the no-regression default, OQ3). The one
      browser-unverified piece — the task-sourced confirm CARD rendering in a real agent turn — needs a full model+FE
      turn, blocked on **test-account data** (no book chapters in loreweave_book; the derive source's EDIT grant drifted
      since §6.2) + model tool-call reliability. The FE card path is UNCHANGED code (handle-in-content → the same
      pending suspend shape the confirm card already renders), and the driver is unit-covered. **Recorded as the final
      pre-activation smoke, NOT silently skipped.** (DRIFT vs the plan's literal "real agent turn": proven at the `/mcp`
      cross-service layer instead — the same domain-side contract — because the agent turn is data/model-blocked.)
  - **M3 `[x]` — every migratable KIND-C confirm is now task-shaped + ACTIVATED.**
    - **book** (`47d1e888c`): one dispatching `resolveBookAction` for all write descriptors (publish/unpublish/
      delete/purge); grantForOp security mapping; DB-tested.
    - **composition** (`0d9b04a29`): 7 tools (publish/generate/5 authoring-run) via per-descriptor resolvers reusing
      `_execute_*`. 5 tools left on confirm_token (need the token for the replay-ledger + billing key — a real
      constraint).
    - **glossary** (`3db85a772`): 15 tools / 14 descriptors via ONE dispatching resolver that replays
      `dispatchConfirmEffect` through an httptest recorder (byte-identical effects; tokenless-effect + single-winner
      verified). 2 left on confirm_token (dual-mode / System-tier).
    - **CRITICAL FEDERATION FIX** (`db503e09d` + provide-input follow-up): Go `Out=any` tools + the `Result any`
      field in `ProvideInputResult` made the SDK emit an `outputSchema.properties.result` the ai-gateway's zod
      validator REJECTS — failing the WHOLE provider's list-tools so book+glossary tools were UNROUTABLE (silently,
      since T3c — only ever tested via the raw `/mcp` handler, never the gateway). Fixed at the kit root
      (permissive `{type:object}` schema). **LIVE-PROVEN through the gateway:** catalog 165→264 tools; book +
      glossary tools now route; composition owner-check (stranger→not_task_owner) still holds; `tasks_gate_enabled`
      flipped True + all 4 domains redeployed.
    - **Feature-parity note:** glossary `execute_plan`'s per-op `enabled_ops` opt-in can't ride the task path (the
      resume driver passes only `{task_id, accepted}`) → safely degrades to additive-only. Tracked.
  - M4 `[ ]`  (done = an evidence string).
- **Invariants:** provider-gateway · language-rule · tenancy scope-key on `mcp_gate_tasks` (owner_user_id) · confirm_token fallback stays · no closure persisted.
- **Decisions / Parked / Debt / Drift:**
  - **DEBT → M2 (accept-caller ownership check) → RESOLVED (M2.1, `771ffb5a0`).** Go book enforces `caller==owner` in
    its resolver (`ctx`); Python enforces it in the kit's provide-input tool (`_owner_check` via `build_tool_context`,
    `register_task_endpoints(internal_token=…)`). 5 kit unit tests + LIVE on deployed composition (stranger →
    `not_task_owner`, task untouched; owner → passes). A leaked task_id can no longer drive another user's gate.
  - **DRIFT (M1a, near-miss).** SESSION_HANDOFF called the persistent store "a drop-in" — it was not (closure
    unpersistable). Caught in the audit; the resolver-registry evolution is the corrected foundation.
  - **DRIFT (M1a evidence correction).** The M1a commit claimed book-service "DB-E2E green" — but those tests SKIP
    without `BOOK_TEST_DATABASE_URL` (they skipped). M1b ran them for real (they pass) — retroactively validating M1a.
    Lesson: assert DB tests actually RAN, not just that the suite said "ok".
  - **DEBT (low, M1b — resolver/status non-atomicity).** In `PgTaskStore.ProvideInput` the resolver's real write and
    the terminal-status UPDATE are not in ONE transaction (the resolver is domain code owning its own tx). A crash
    between them leaves a committed write on a `working` task → lapses to `failed` after TTL (a false-negative). Re-accept
    is refused (status≠input_required), so no double-write. Same non-atomicity class as the existing confirm-token
    mint→execute path; acceptable for the confirm gate. Revisit only if it bites (a resolver that accepts a tx handle).
