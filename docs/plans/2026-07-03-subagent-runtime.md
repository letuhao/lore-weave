# Plan — Subagent Runtime (scoped nested execution) · D-REG-P5-SUBAGENT-RUNTIME

**Design/spec:** [`docs/specs/2026-07-03-subagent-runtime.md`](../specs/2026-07-03-subagent-runtime.md) (serves as DESIGN + REVIEW).
**Size:** L (deep logic in the chat-service hot loop, a recursive call + isolation invariants, security-critical scope enforcement). `/review-impl` mandatory.
**Surface:** chat-service only (agent-registry resolver `/internal/subagents` already shipped P5-M1, returns `{name, description, system_prompt, tool_scope, model_ref, tier}` with higher-tier-shadow-by-name applied).

## Seams (verified against code)

- `_stream_with_tools` ([stream_service.py:555](../../services/chat-service/app/services/stream_service.py)) — the tool loop. `run_subagent` is handled **consumer-local, inline in the `for c in calls:` loop**, exactly like `find_tools` (line 872) — never federated (no cross-service cycle).
- The loop already carries every knob the nested run needs as params: `permission_mode`, `approval_check`, `hooks`, `discovery_catalog`, `surface_tracker`, `effective_limit`, `max_iterations`. The nested call reuses them (clamped).
- Resolver client: new `registry_subagents_client.py` mirroring `registry_hooks_client.py` (degrade-safe → [] on any failure).
- Turn resolution: `_emit_chat_turn` resolves hooks once per turn (line 2063); resolve subagents the same way, build the `run_subagent` schema (dynamic enum of names) and append to `tool_defs` iff ≥1 enabled subagent, and thread the resolved defs into `_stream_with_tools`.
- Frontend-tool exclusion: `is_frontend_tool` (frontend_tools.py:625); meta-tool names `FIND_TOOLS_NAME` + `run_subagent` itself excluded from any scoped set.
- Model: reuse the turn's `model_source`; use `def.model_ref` if non-empty else the turn's `model_ref` (v1 — per-subagent model_source is a future extension; invalid ref falls back, never hard-fails §7b.7).

## Milestones

- **M1** — pure `subagent_runtime.py`: `resolve_scoped_tools(catalog, tool_scope)` (fnmatch glob intersect + meta/frontend-tool exclusion), the depth guard, the `run_subagent` schema builder (dynamic enum + `result.error` on miss). Unit tests (glob intersect, exclusions, empty scope → [], `["*"]`, depth guard, unknown-name error). **TDD.**
- **M2** — wire `run_subagent` into `_stream_with_tools` inline handler: look up def by name (reject unknown/disabled with `result.error`), build isolated nested `messages` = `[{system: def.system_prompt}, {user: task}]`, run nested `_stream_with_tools` with the scoped tool set + `subagent_depth+1`, return **only** the synthesized text (result-size capped) as the tool result. Nested messages never enter the parent `working`. Resolve + advertise in `_emit_chat_turn`. Register the arg shape in the CLOSED_SET_ARGS contract (dynamic-enum note).
- **M3** — permission clamp (nested `permission_mode = min(caller, ...)`, never escalates) + **execute-time** scope enforcement (a nested call to a non-scoped tool returns `result.error`, never executes — the defense-in-depth negative-test guarantee, mirrors ask-mode block). Cancel + token-budget thread through.
- **M4** — `subagent_run` activity event (name, tools_used, ok, latency) + usage attribution (nested tokens summed into the turn total, design D10) tagged `subagent=<name>`.
- **M5** — live E2E-P5-A (real local model): a `lore-scout` subagent (`tool_scope=["glossary_search","kg_*"]`) — assert scoped-only tools, out-of-scope `book_write` unavailable AND force-call → `result.error`, main transcript has synthesized result but NOT nested messages/persona. `/review-impl` (isolation + scope-escape load-bearing). SESSION + COMMIT.

## Non-goals (v1, from spec)
Depth cap = 1 (no subagent-spawns-subagent); one synchronous sub-run per call (no parallel fan-out); no new provider path (reuses `_stream_with_tools`); no privilege escalation.

## Risk boundaries (checkpoint/commit points)
M1 (pure, isolated) → M2+M3 together (the loop seam + the two-place scope enforcement are one coherent security unit — commit together) → M4 (observability, additive) → M5 (proof + review). Commit at M1, at M3 (loop + enforcement), at M4, at M5.
