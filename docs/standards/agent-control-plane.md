# Agent Control Plane — the consumable governance/control standard

**Status:** 🟢 Active (built A0–A4, 2026-07-16). **Authoritative design:**
[`docs/specs/2026-07-16-agent-control-plane-sdk.md`](../specs/2026-07-16-agent-control-plane-sdk.md)
(ACP-1..20 + the RV-* review hardening). **Engine semantics:**
[`docs/specs/2026-07-15-agent-task-governance.md`](../specs/2026-07-15-agent-task-governance.md).

## What it governs

Any **agent-runtime** — a loop where an LLM decides and acts over multiple steps — consumes control/
governance through ONE surface, never by forking chat-service. Current consumers: chat-service (interactive,
the first/dogfood consumer) and interview/Practice (rides chat's loop). Future: background task-agent
runners, game-server agent logic.

## The boundary (three planes + one SDK)

- **Definition** — a runtime's own domain (e.g. roleplay-service) authors scripts and **freezes a charter**;
  it PRODUCES a charter conforming to the contract and then exits the data path. It owns **no** control loop.
- **Control** — chat-service (turn loop, anchor injection, drive) + knowledge-service (working-memory SSOT +
  the executive). The reusable engine.
- **Contract / SDK** — the coupling surface: [`contracts/agent-control/`](../../contracts/agent-control/)
  schemas + `sdks/python/loreweave_agent_control` (Python) + `crates/contracts-agent-control` (Rust). No
  consumer imports another service's code.

## The always-on rules (a violation is a `/review-impl` finding)

1. **No new god-service** (ACP-7) — extract into contracts + libs + the EXISTING services, never a 2nd monolith.
2. **The contract is machine-checked on EVERY side** (ACP-6) — a producer/consumer of a control contract
   validates against the schema in its own suite; a renamed field reds Rust + both Python suites.
3. **A producer stays a producer** — it emits a charter; it adds no executive/drive/enforcement.
4. **The harness returns a VERDICT; the consumer owns the loop** (RW-3) — the drive decision is verdict-only;
   streaming/re-prompt/chain-head mechanics stay in the consumer.
5. **Enforcement policy is per-runtime-MODE** (ACP-10) — the verdict machine is shared; interactive holds +
   re-prompts, autonomous PARKs + escalates (no user).
6. **Invariants pass through** — effect-probes are `/internal` grant-checked reads (not agent-logic); tenancy
   scope-keys are required (checkpoint writes are owner-scoped — RV-H4); models resolve per-user via
   provider-registry; no hardcoded model; secrets via env (not `JWT_SECRET`).
7. **Framework-agnostic port, not a dependency** (ACP-13) — an external framework (LangGraph/…) integrates as
   an adapter onto the hook port, subject to the invariants; never a rebuild ON it, and never built ahead of
   a real consumer.

## How it's enforced

- **Contract both-sides tests:** chat `test_working_memory` + knowledge `test_executive_contract` (jsonschema)
  + roleplay `charter.rs` (validates real `freeze()` output) — a schema drift reds all three.
- **SDK goldens:** `sdks/python/loreweave_agent_control/tests` pin the verdict-machine, state-merge,
  `compute_progress`, and the drive harness byte-for-byte.
- **Tenancy:** the real-DB `test_working_memory_repo` proves owner-scoped + lock-serialized executive writes.
- **`/review-impl`:** the ACP rules above are part of the standards gate for any change touching an
  agent-runtime, a control contract, or the SDK.

## Deferred (demand-pulled — tracked in the RUN-STATE parked register)

`D-ACP-DURABLE` (checkpoint replay on the outbox/saga substrate), `D-ACP-RUST-CLIENT` (the reqwest executive
client — no Rust caller yet), `D-ACP-ANCHOR-MOVE` (the model-coupled anchor render), `D-ACP-EXT-ADAPTER`
(external-framework adapter), `D-ACP-GRAPH/MULTIAGENT/TRACE` (WorkflowDefinition-as-DAG / governed handoff /
replayable eval studio). Each is gated on a real consumer — building ahead is the `build-for-an-absent-
consumer` anti-pattern.
