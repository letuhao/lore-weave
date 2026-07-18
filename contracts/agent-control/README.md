# Agent Control Plane — contracts

The shared, machine-checked contracts for the **agent control/governance plane** (spec:
[docs/specs/2026-07-16-agent-control-plane-sdk.md](../../docs/specs/2026-07-16-agent-control-plane-sdk.md)).
These are the boundary interface any agent-runtime consumes — chat-service (first consumer), roleplay/interview
(via chat's loop), and future background/game runtimes. **This directory is the source of truth; every
producer/consumer validates against it in its own test suite (ACP-6 — the both-sides discipline).**

> Moved here from `contracts/interview/` at the ACP extraction (2026-07-16). The working-memory/charter block
> is not interview-specific — it is the control plane's core anchor. Interview is one consumer.

## `working_memory.schema.json`

The pinned goal-state block. Two tiers mirroring goal-shielding:

- **`charter`** — the committed goal. Written **only by the goal authority** (a static template for interview
  ⇒ frozen; the world model in full roleplay ⇒ dynamic). The summarizing **executive can NEVER write
  `charter`** — this invariant keeps the memory/executive/anchoring core reusable when the goal becomes
  world-model-driven.
- **`state`** — the mutable progress estimate the executive rewrites. `covered` is monotonic (append-only);
  `remaining` is derived (`charter.checklist − state.covered`), never stored.

Producers/consumers (all validate against this schema in-test — ACP-6):
- **roleplay-service** (Rust) — `charter::freeze` produces the seed (PRODUCER; validated on real `freeze()`
  output, not a fixture — RW-8).
- **chat-service** (Python) — `WorkingMemory*` Pydantic models; `working_memory_seed` (frozen seed / degraded
  fallback), anchoring, `/evaluate`.
- **knowledge-service** (Python) — the `working_memory` block as SSOT (selector + store), the `executive`
  worker (writes `state` only), the rendered anchor from `POST /internal/context/build`.

## Other contracts in this directory

- `executive.init.schema.json` / `executive.tick.schema.json` — the executive HTTP request/response bodies
  (both the Python SDK and the Rust crate call these; every `tick` consumer passes a **server-authenticated**
  `user_id`, never a client-asserted one — RV-M8).
- *(added as the SDK lands: `workflow_definition`, `effect_ref`, `verdict`, and the memory/checkpoint/guardrail/
  trace shapes — published only as a real consumer reads them, per ACP-12.)*
