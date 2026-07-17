# PlanForge — out-of-scope / follow-up inventory (seed for planning)

> Everything assessed as OUT OF SCOPE during the S3 closure + PROPOSE-BLIND build (2026-07-17),
> gathered so each can be turned into its own plan/spec. Grouped by whether it needs a real design
> (A), is an eval/measurement follow-up (B), or is cross-track hygiene not owned here (C).
>
> **Nothing below blocks a shipped feature** — PROPOSE-BLIND is CLOSED and correctly gated OFF; these
> are the "make it better / clean up / measure more" items.

## A · Needs a real spec/plan (design-heavy)

### A1 · Deterministic protagonist injection into the proposed spec  ⭐ highest-value
**Why:** the A/B eval proved prompt-based cast grounding does NOT move a 26B local model — a
character-less braindump yields no cast, so grounding has nothing to anchor (report:
`2026-07-17-propose-blind-ab-eval.md`). The reliable fix is to stop depending on model compliance:
have the gather lens **seed the book's existing protagonist/cast directly into `layers.characters`**
(carrying `glossary_entity_id`), the same deterministic mechanism the rules-path merge already uses.
**Scope:** composition-service engine (existing_state + normalize/merge), a decision on how many cast
to inject + how they interact with the model's own character output, then a **re-run of the A/B eval**
to see if cast continuity finally beats blind. Owner: PlanForge-v2. Size: M–L.

### A2 · De-fixture the LLM propose prompts (MATERIALIZE_SYSTEM / ANALYZE_SYSTEM)
**Why:** the two system prompts still carry POC-fixture rules welded to ONE novel — "character name:
use 'Nữ chính'", "Arc 2 MUST have exactly 7 events (Nhập Môn … Quyết Định Tiếp Tục)", specific
Vietnamese trait lists. These compete with (and in the A/B, dominated) the CONTINUITY grounding, and
they are the LLM-side of the SAME "fixture severing" bug that `propose.py` already fixed for RULES
mode (see its module docstring — the P-06 correctness bug). A book the model has never seen still gets
another novel's scaffolding nudged into its plan. **Scope:** rewrite both system prompts to parse
what's given + emit nothing where nothing is stated (mirror propose.py's rule); re-baseline the
fidelity eval fixtures that currently depend on the hardcodes. Owner: PlanForge-v2. Size: L (touches
the eval harness). **This is a real latent defect, not just an enhancement.**

### A3 · Cast enrichment in the KAL roster (role / kind / mention-rank)
**Why:** the PROPOSE-BLIND gather lens can only show existing cast as `{name}` because the KAL roster
is DELIBERATELY projection-restricted to `{entity_id, name}` (`services/knowledge-gateway/src/kal/
kal-read.controller.ts:107`). Role/kind/mention-frequency would let the gather lens rank + label cast
(cap by importance, not arrival order) and give the proposer richer continuity signal. **Scope:**
knowledge-gateway (TS) — widen the roster projection (+ possibly the upstream glossary list endpoint);
weigh against why it was restricted (bounded payload). Cross-service, out of composition. Owner:
knowledge-gateway / KAL. Size: M.

## B · Eval / measurement follow-ups (lighter, gated on A)

### B1 · Character-rich braindump A/B re-eval
Re-run the PROPOSE-BLIND A/B with a braindump that DOES drive a protagonist's continuation (the
2026-07-17 run used a deliberately character-less braindump to test pure injection, and refuted it).
Best done AFTER A1 so there is a cast to measure. If grounding then beats blind → flip the ceiling.

### B2 · Stronger-model A/B re-measure
The 26B local model did not follow the CONTINUITY name-override even when strengthened. Re-measure on
a larger model to separate "grounding doesn't help" from "this model won't follow it".

## C · Cross-track hygiene (surfaced here, NOT owned by PlanForge)

### C1 · `test_progress_router.py::test_get_progress_shapes_response` is RED on the shared checkout
`app/routers/progress.py:124` calls `progress.get_goal(...)`, which is implemented on NEITHER the real
`ProgressService` nor the test stub → 500 / AttributeError. This is another session's incomplete S6
goal-table work (`BE-P2`, noted "70%"). **Owner: the S6 progress/goal track.** Not touched by
PROPOSE-BLIND; flagged so it isn't mistaken for a PROPOSE-BLIND regression.

### C2 · S4 motif-suggest `SceneMotifsSection.tsx` uncommitted + its i18n
During the PROPOSE-BLIND work the i18n-completeness gate blocked on `composition.json`
`motif.suggest.degraded*` (S4's keys, en-only). Filled the 17 locales to unblock (commit `5c38757ec`),
but `SceneMotifsSection.tsx` (the consumer) remains uncommitted in the shared working tree. **Owner:
the S4 motif-tenancy track** — commit its FE + verify the degraded-suggest surface.

### C3 · 17-locale parity for OTHER studio namespaces (pre-existing backlog)
The i18n gate is at parity for the namespaces PROPOSE-BLIND touched (studio, composition), but the
broader ~102-issue parity backlog across other namespaces remains (convergence §6.1). Platform-wide
i18n track, not feature work.

## Suggested planning order
1. **A2 (de-fixture prompts)** — a real latent defect + unblocks A1's measurement (fixtures stop
   polluting the output). 2. **A1 (deterministic injection)** — the highest-value path to making
   grounding actually work. 3. **B1/B2 re-eval** — decide the ceiling flip on fresh evidence.
4. **A3** — cross-service, do when the knowledge-gateway track is open. C1–C3 are each their own
   track's cleanup.
