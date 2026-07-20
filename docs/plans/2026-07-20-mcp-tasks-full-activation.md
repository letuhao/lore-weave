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
- **Slice board:** M1a `[ ]` · M1b `[ ]` · M1c `[ ]` · M2 `[ ]` · M3 `[ ]` · M4 `[ ]`  (done = an evidence string).
- **Invariants:** provider-gateway · language-rule · tenancy scope-key on `mcp_gate_tasks` (owner_user_id) · confirm_token fallback stays · no closure persisted.
- **Decisions / Parked / Debt / Drift:** (append as we go)
