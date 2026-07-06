# Plan: Context Compiler · Trace Inspector GUI (spec §11)

Spec: [`docs/specs/2026-07-03-context-budget-law.md`](../specs/2026-07-03-context-budget-law.md) §11
(the 86-item checklist §11a) + §13 (definition-of-done = tests, not self-report).
Draft mockup: [`design-drafts/context-management/context-compiler-inspector.html`](../../design-drafts/context-management/context-compiler-inspector.html).

## Current state (evidence — read before building)

**Already built (BE spine):**
- Per-turn context frame persisted to `chat_messages.context_breakdown` JSONB — the full
  `contextBudget` payload (`token_budget.context_budget_event`): `used_tokens` (=compiled),
  `context_length`, `effective_limit`, `pct`, `target`, `pct_of_target`, `until_compact_pct`,
  `breakdown` (15 categories, `token_budget.BREAKDOWN_CATEGORIES`), `baseline_tokens`,
  `entity_presence` (the T5 gate decision + matched tokens).
- Read endpoints (`services/chat-service/app/routers/messages.py`), both owner-gated + session-scoped:
  - `GET /v1/chat/sessions/{id}/context-history` → ordered SERIES of per-turn frames.
  - `GET /v1/chat/sessions/{id}/context-budget` → latest frame (seeds the header meter).
- Emit site: `stream_service.py` ~L2785 (`_emit_chat_turn`), one payload both persisted and
  SSE-emitted (`contextBudget` frame).

**Missing (this effort):**
- Derived frame fields: `raw_tokens` (naive-concat pre-compile), `reduction_pct`, `status_flags[]`
  (gated/included/compacted/overflow/elastic/continuity/collapsed/wire), `retrieval_mode`, `intent`.
- **Trace spans[]** — ordered `{phase, tier, category, action_text, delta_tokens, is_error}`, NEW
  instrumentation. Coupled to `raw_tokens`: `raw = compiled + Σ(saved deltas)`, so the accumulator
  that sums savings for `raw_tokens` IS the span list — build once, expose both.
- Frame **contract** `contracts/context-trace.contract.json` + real-turn conformance test.
- The entire **FE dockable Inspector panel** (only a static HTML mockup exists today).

## Milestones (leverage-per-risk; each a clean risk boundary, independently shippable)

### M1 — BE telemetry: the savings/trace accumulator
A `TraceSpan` accumulator threaded through the assembly path records each tier decision chat-service
can see (T0 result-serialization, T2 target check, T4 story_state, T5 grounding gate, T6 compaction).
At emit: `raw_tokens = compiled + Σ|drop deltas|`; `reduction_pct`; `status_flags[]` derived from the
existing signals (gated ← `entity_presence.grounding_needed=false`; compacted ← C_persist/compact
fired; elastic ← `task_weight<1`; overflow ← a rejected oversized result); `retrieval_mode` ←
settings/sealed-decision #1 (`prepend`/`hybrid`); `intent` ← a cheap label from `entity_presence` +
message shape. All ADDITIVE to the frame (old keys byte-identical → the existing meter + endpoints
keep working). **Attribution honesty:** chat-service emits spans only for cuts IT sees; T1 tool-side
reference-first projection arrives as an already-small result (folded into a small `results` bucket,
not a separate span) — documented, not confabulated. When nothing was cut, `raw≈compiled`,
`reduction≈0` — honest, not a fake headline.
- **Contract + proof:** `contracts/context-trace.contract.json` (required per-turn fields + the
  `TraceSpan` shape) + a conformance test that runs a REAL turn and asserts each field present AND
  non-null (mirror `frontend-tools.contract.json` + its test — do NOT hand-roll). Bind to the T2/T5/T6
  GATEs (a field the compiler forgot to emit → the GATE measurement is impossible → red).
- **Risk boundary:** the frame contract + hot-path threading. Commit here.

### M2 — FE dockable Inspector panel
Build the panel from the mockup, wired to M1's telemetry via `context-history` (+ a paginated/filter
variant if the series endpoint needs it). Turn list (search + status filters + pagination), context
pressure gauge (compiled/target/ceiling color states + target tick), allocation map (segmented bar +
legend + hover tooltip, 10 category colors), compile-trace waterfall (phase/tier/category/action/delta,
trace filters), inspector header chips, KPIs (avg reduction, tokens saved, model window), j/k nav.
- **MVC rules:** mount-without-unmount on hide (CSS `hidden`); split volatile per-turn state from
  stable session state (re-render rule); hooks own logic, components render.
- **Dockable studio integration:** register in `features/studio/panels/catalog.ts`; add id to the
  `ui_open_studio_panel` enum (`chat-service/app/services/frontend_tools.py`) + regenerate
  `contracts/frontend-tools.contract.json`; self-title via `props.api.setTitle`; session/book-scoped;
  standalone route too; `panelCatalogContract.test.ts` green.
- **Proof by EFFECT (§13b):** component/E2E tests asserting effects, not existence (compiled>target ⇒
  gauge over-target color; click 'gated' ⇒ only gated turns; `ui_open_studio_panel('context-inspector')`
  ⇒ panel mounts) + a live browser smoke (vite :5199 → gateway :3123, test account, local gemma, $0).
- **Risk boundary:** the shared spine files (catalog/enum/contract) + the panel. Commit here.

### M3 — enforcement (§13)
The CI meta-check script parses §11a, binds each non-`⊘manual` item to a `✓test:<id>`, and FAILS the
build if any item lacks a green test (mirror `language-rule-lint` philosophy). Wire the proof-refs into
§11a. Adversarial refute-pass (cold-start agent tries to REFUTE each checked item against code).
- **Risk boundary:** the manifest becomes un-gameable. Commit here.

## Verification (per milestone)
- **M1:** `python -m pytest tests -q -n auto --dist loadgroup` (chat-service) green incl. the new
  conformance test; `ai-provider-gate.py` clean; a real turn on the live stack persists a frame
  carrying every new field non-null (provider-truth, local gemma).
- **M2:** `cd frontend && npm run build` (tsc) + touched-feature tests green; `panelCatalogContract`
  + `frontendToolContract` green; live browser smoke opens the panel via the Command Palette and
  renders a real session's turns.
- **M3:** the meta-check runs green over §11a with every item carrying a proof-ref; refute-pass finds
  nothing (or its findings are fixed).

## Out of scope (consciously)
- T1 tool-side per-tool span attribution (the projection happens in the owning domain service; chat
  sees the already-small result). Tracked as a later cross-service telemetry item if a consumer needs
  it.
- Making other kernel consumers (roleplay, composition packer) emit `TraceSpan` — the Inspector works
  for them "for free" once they adopt the kernel (spec §12), but that adoption is its own deferred track.
- Live-update via SSE push of new frames — M2 ships poll/refetch; SSE upgrade is a follow-up if the
  poll UX is insufficient.
