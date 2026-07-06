# Plan — #20 Agent Mode implementation (autonomous long-run, no PO checkpoints)

> User explicitly authorized a single continuous run through BUILD→VERIFY→REVIEW→SESSION→COMMIT with no
> stop-and-ask checkpoints for this task (2026-07-05). Ambiguities below are resolved by architect judgment,
> documented with rationale, not deferred to a question. Spec: [`20_agent_mode.md`](../specs/2026-07-01-writing-studio/20_agent_mode.md).

## Remaining implementation decisions (locked here, not asked)

| # | Decision | Rationale |
|---|---|---|
| P1 | New endpoint `PATCH /v1/composition/authoring-runs/{run_id}/pause-policy` body `{pause_after_each_unit: bool}`, owner-only, any non-`closed` state | Smallest addition consistent with existing REST shape; mirrors the other single-purpose action endpoints (`/pause`, `/resume`) rather than overloading a generic PATCH. |
| P2 | REST `create` defaults `pause_after_each_unit` to `true` if omitted (UI always sends it anyway); MCP `_create` has NO default — Pydantic required field, omitting it is a 422, not a silent `true` | REST is UI-only (a human is right there to toggle it); MCP can be chat-invoked unattended, so silence must not resolve to a guess (D4b in spec). |
| P3 | Heartbeat staleness threshold: **30s** while `status='running'`, no staleness concept otherwise | Starting default per spec's "derive from real cadence, don't invent" note — flagged as tunable, not load-bearing to correctness (health chip is advisory, not a gate). |
| P4 | `agent-mode` panel is ONE component tree with 3 internal view states (not 3 catalog panels) | D1, matches `ExtensionsPage`/`TranslationPanel` precedent. |
| P5 | Backend and frontend are fully disjoint file trees (`services/composition-service/**` vs `frontend/**`) → build in **parallel**, two independent agents, zero shared-file risk between them | No cross-dependency: FE panel calls REST (already documented in spec); MCP tools are a separate consumer of the same service layer, not something FE calls directly. |
| P6 | Both new FE panels (`agent-mode`, `chapter-revision-compare`) + their `catalog.ts`/i18n registration built by the SAME agent, not two parallel agents | Avoids the exact `catalog.ts`/i18n-locale collision class this project has hit before (memory `dock2-fork-risk-in-parallel-panel-fanout`, i18n collision during #19). |

## Execution order

1. **Parallel dispatch** — Backend agent (composition-service: migration, model, driver, PATCH endpoint, 11 MCP tools, tests) + Frontend agent (`agent-mode` + `chapter-revision-compare` panels, hooks, catalog, i18n, tests) — both background, both self-contained.
2. **Integration** (me, serial, after both land): live-smoke both `pause_after_each_unit` entry paths (UI-created run vs MCP-created run with no Studio panel open) — this is the exact edge case the whole P1-P3 redesign exists to close, must be proven, not assumed.
3. **VERIFY**: full composition-service suite + full relevant frontend suites, `tsc`/eslint clean.
4. **REVIEW**: `/review-impl`-style self-adversarial pass over the combined diff (both agents' work integrated) — standards gate (provider/tenancy/language rule/frontend-tool-contract as applicable), coverage gate.
5. Fix any HIGH/MED found; re-VERIFY.
6. **SESSION**: update `docs/sessions/SESSION_HANDOFF.md`, memory.
7. **COMMIT**: exact-pathspec staging (never `git add -A`, shared checkout), new commit(s) at reasonable boundaries (backend commit, frontend commit, or one combined — decide at COMMIT time based on how cleanly they separate).

No step above pauses for approval; the whole sequence runs to completion in this turn/session.
