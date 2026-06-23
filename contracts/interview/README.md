# Interview-Practice Roleplay — contracts

POC for the MMO `roleplay-service`. Spec: [docs/specs/2026-06-23-interview-roleplay.md](../../docs/specs/2026-06-23-interview-roleplay.md).
Plan: [docs/plans/2026-06-23-interview-roleplay.md](../../docs/plans/2026-06-23-interview-roleplay.md).

## `working_memory.schema.json`

The pinned goal-state block. Two tiers mirroring goal-shielding:

- **`charter`** — the committed goal. Written **only by the goal authority** (static template here
  ⇒ frozen; the world model in full roleplay ⇒ dynamic). The summarizing **executive can NEVER
  write `charter`** — this invariant is what keeps the memory/executive/anchoring core reusable
  when the goal becomes world-model-driven.
- **`state`** — the mutable progress estimate the executive rewrites. `covered` is monotonic
  (append-only); `remaining` is derived (`charter.checklist − state.covered`), never stored.

Owners:
- `chat-service` — `session_templates` (the goal authority for interview), `chat_sessions.working_memory_seed`
  (the frozen charter seed / degraded fallback), anchoring, `/evaluate`.
- `knowledge-service` — the `working_memory` block as SSOT (selector + store), the `executive`
  worker, and the rendered `working_memory` string returned by `POST /internal/context/build`.

## `build_context` contract change

`POST /internal/context/build` response (`ContextBuildResponse`) gains:

- **`working_memory: string`** (default `""`) — the rendered anchor text chat-service pins into the
  system block AND tail-injects (depth-0). `""` when the session has no working-memory block
  (non-interview session, or knowledge-service build predating this field — backward compatible).
