# Cycle 26 — VERIFY evidence (BE-unit)

**Cycle:** 26 — Critic override enforcement (composition). dị bản M3. BE-unit verify.

## Acceptance gate
`bash scripts/raid/verify-cycle-26.sh` → **exit 0 (PASS)**.

## Unit token
`unit: derivative critic flags override slip + passes compliant scene`

## What ran
- `tests/unit/test_critic_override.py` — 10 tests (detector + orchestrator + wiring spy).
- `tests/unit/test_engine_router.py` — 40 tests incl. the router-level WIRING test
  `test_critique_derivative_dimension_FIRES_at_call_site`.
- `tests/unit/test_critic.py` — 15 tests (existing LLM critic, regression).
- Full composition unit suite: **478 passed**.
- `python -m py_compile app/engine/critic_override.py app/routers/engine.py` → OK.
- `python scripts/ai-provider-gate.py` → OK (composition stays AI-free — the dimension
  is deterministic, no provider SDK import).

## Behaviours proven
1. **Flags an injected override slip** — an overridden field (张若尘 → "now a woman")
   that reverts to its canon/base value ("a young man, the male lead") in the passage →
   a structured `override_slip` finding (entity_id + field + expected-vs-found).
2. **Passes a compliant scene** — override honoured (overridden value present, base
   absent) → no finding.
3. **Delta internal consistency** — an overridden field that also added a `canon_rule`
   but reverts to base → a `delta_inconsistency` finding.
4. **WIRING (anti-no-op)** — both a unit spy-injection test AND a router-level test
   prove the dimension actually FIRES at the `/critique` call site for a derivative
   Work (base lens queried at the SOURCE project; detector ran; finding persisted to
   the job). A wired-but-uninvoked dimension would leave `critic=None`.
5. **No activation on a canon Work** — no `source_work_id` → dimension returns []
   WITHOUT querying the base lens (spy-asserted).
6. **Inherited entity not flagged** — only overridden fields are enforced; a
   non-overridden entity at its canon value is never a slip.

## Reuse (no re-merge)
The dimension loads the active `entity_override[]` via C25's `build_derivative_context`
and reconciles knowledge-id → glossary-anchor via C25's `_resolve_override_anchors` —
it does NOT re-implement `apply_entity_overrides` / `merge_present` (grep-asserted in
the verify script).
