# Spec + Plan — Arc-Template Drift View (Wave-4)

> **Status:** ready to build · **Size:** S (FE-only; presentational + one shared type + one hook) · **Track:** Wave-4 (was `D-ARC-TEMPLATE-DRIFT-VIEW`) · **Owner surface:** `arc-templates` Studio panel (S2 storyBible).

## 1 · Problem & corrected scope

The backend for "spec **vs TEMPLATE**" drift is fully shipped — a realized/authored arc (`structure_node`) drifting from the `arc_template` it was materialized from — distinct from `quality-conformance` which is "spec vs **PROSE**". The RUN-STATE called it "a route with zero FE consumers"; **verified false**: a crude consumer already ships — `DriftSection` in [`ArcTemplatesPanel.tsx:215-258`](../../frontend/src/features/studio/panels/ArcTemplatesPanel.tsx#L215) fetches the report and dumps it as raw JSON in a `<pre data-testid="arc-drift-report">` ([:253](../../frontend/src/features/studio/panels/ArcTemplatesPanel.tsx#L253)).

**So the feature is not "build a consumer" — it is "replace the `<pre>` JSON dump with an honest structured view."** That is S-sized: a presentational component + a type reconciliation + (optionally) a thin hook. **No new panel, no registration.**

## 2 · The contract (design to this)

The FE already calls REST via [`arcTemplates/api.ts:40-56`](../../frontend/src/features/composition/arcTemplates/api.ts#L40) `getArcTemplateDrift(projectId, arcId, token)`:

- **REST:** `GET /works/{project_id}/conformance?scope=arc_template_drift&arc_id=<structure_node.id>` ([conformance.py:334-404](../../services/composition-service/app/routers/conformance.py#L334)). `arc_id` is a **`structure_node.id`** (the realized arc), NOT an `arc_template_id`. `project_id` is the prose-axis Work (its `book_id` must == the arc's book).
- **Three honest states**, already discriminated by the shim → `{ report, state }`:
  - `ok` — 200, the report.
  - `no_provenance` — **422 `NO_TEMPLATE_PROVENANCE`** (the node was never materialized from a template → nothing to drift against).
  - `gone` — **404 `NOT_FOUND`** (the template was deleted).
- **Decision (locked): read REST, not the MCP tool.** The MCP `composition_arc_template_drift` ([server.py:5095-5140](../../services/composition-service/app/mcp/server.py#L5095)) wraps the same report as `{available, reason|report}` — a *different* envelope. The FE already uses REST + HTTP-status discrimination; do not introduce a second envelope. (The MCP tool stays the agent-facing twin.)

### 2.1 · The `report` shape — IDENTICAL to `ArcConformance`

`build_arc_conformance()` ([arc_conformance.py:258-379](../../services/composition-service/app/engine/arc_conformance.py#L258)) returns the **same shape** as the spec-vs-prose arc report (the drift path just feeds an `arc_template` with `by_structure=False`):

```
{ scope:"arc", available:true, coarse:true, causal_verified:false,
  arc_id, arc_template_id, arc_name, chapter_count,
  thread_progress: [ {thread, label, planned:int, covered:int, missing:[{motif_code, ord}]} ],
  pacing: { comparable, planned:number[], realized:[{chapter_index,avg_tension,scenes}], max_drift:number|null },
  succession: { causal_verified:false, threads:[{thread,label,transitions,legal,unrelated,violations:[{from_motif_id,to_motif_id}]}] },
  unmaterialized: [ {motif_code:string|null, thread:string|null, ord:int} ] }
```

**There is NO status/verdict enum.** Drift is expressed as component SIGNALS — the view derives its own summary:
- **Coverage gaps** — `thread_progress[].missing` = template placements (by `motif_code`) that never bound in the realized arc (planned-but-absent).
- **Folded/removed slots** — `unmaterialized` = template `layout` placements that produced no binding (the closest thing to "removed/moved").
- **Pacing drift** — `pacing.max_drift` (tension deviation planned→realized), `comparable` guards a meaningful compare.
- **Succession violations** — `succession.threads[].violations` (illegal motif→motif transitions).

The `deep` overlay is prose-drift (different axis) — **out of scope** (the MCP tool forces `deep=false`; the drift view is coarse/structural only).

### 2.2 · Type reconciliation (a required sub-task)

`arcTemplates/api.ts:29-34`'s `ArcDriftReport` is a **loose, inaccurate stub** (`thread_coverage`, …). The real wire shape is `ArcConformance` ([`motif/types.ts:280-293`](../../frontend/src/features/composition/motif/types.ts#L280) + `ArcThreadProgress`/`ArcPacing`/`ArcSuccessionThread`). **Reconcile:** point `getArcTemplateDrift` at the real `ArcConformance` type (drop the stub), so the view and the chapter/arc conformance views share ONE type. (`report.scope` is hardcoded `"arc"` even on the drift path — the view keys off `arc_template_id` presence, not scope, to label it "template drift".)

## 3 · Design

**Reuse, don't reinvent.** The dropped-but-intact [`ArcConformancePanel.tsx:63-127`](../../frontend/src/features/composition/motif/components/ArcConformancePanel.tsx#L63) already renders this exact report shape (thread_progress / pacing / succession / unmaterialized). Lift its render JSX into a presentational component:

- **`ArcTemplateDriftView.tsx`** (new, presentational, ~≤100 lines) — props `{ report: ArcConformance }`. Renders four honest sections:
  1. **Header** — `arc_name` + a derived one-line drift summary ("N coverage gaps · pacing drift M · K succession violations · J folded slots"; "no drift — the realized arc matches its template" when all zero).
  2. **Coverage** — per `thread_progress`: `covered/planned` + the `missing` motif_codes (the un-bound template placements).
  3. **Pacing** — `max_drift` + planned-vs-realized tension (only when `comparable`; else an honest "not comparable yet").
  4. **Succession + folded** — `violations` per thread + the `unmaterialized` (folded) placements.
  Each section renders an honest empty ("no gaps" / "no violations"), never a blank.
- **`DriftSection` swap** — in `ArcTemplatesPanel.tsx`, replace the `<pre>{JSON.stringify(...)}</pre>` ([:253](../../frontend/src/features/studio/panels/ArcTemplatesPanel.tsx#L253)) with `<ArcTemplateDriftView report={drift.data.report} />`. Keep the existing `no_provenance` / `gone` / `unapplied` / `loading` branches + testids verbatim (they already exist: `driftNoProvenance`, `driftGone`, `driftUnapplied`, `driftLoading`).
- **Hook:** the existing `useQuery` inside `DriftSection` is fine; no new hook needed unless the render grows (keep it inline — YAGNI).

**No registration.** `arc-templates` is already registered end-to-end (catalog + panel_id enum + contract + i18n). This is a section swap inside it. Only NEW i18n keys under `motif.arc.templates.drift*` (section labels + the summary strings), filled to 17 locales via `scripts/i18n_translate.py`.

## 4 · Standards / invariants

- **Frontend-Tool Contract:** untouched — no tool schema change (drift reads an existing REST route; the MCP twin already exists and is unchanged).
- **Tenancy:** the route is already VIEW-gated on the arc's book (derived from the row); the view adds no new data access.
- **No-silent-fail:** the three honest states (ok/no_provenance/gone) + the per-section empties are the whole point — the view NEVER shows a blank or a fake "no drift" when data is missing.
- **i18n:** new keys through the pipeline (never hand-rolled), en complete first.

## 5 · Plan (phases)

| # | Phase | Work |
|---|---|---|
| 1 | Type reconcile | Point `getArcTemplateDrift` at `ArcConformance` (drop the `ArcDriftReport` stub); export the shared type. |
| 2 | Build view | `ArcTemplateDriftView.tsx` — lift + adapt the 4 sections from `ArcConformancePanel.tsx:63-127`; derive the drift summary; honest empties. en i18n keys `motif.arc.templates.drift*`. |
| 3 | Swap | Replace the `<pre>` in `DriftSection` with the view; keep the no_provenance/gone/unapplied/loading branches + testids. |
| 4 | Tests | Extend [`ArcTemplatesPanel.test.tsx:103-112`](../../frontend/src/features/studio/panels/__tests__/ArcTemplatesPanel.test.tsx#L103) (the drift test) to assert the structured sections render (not the `<pre>`); mirror the `ArcConformancePanel.test.tsx` `REPORT()` fixture for a full-drift render + the all-zero "no drift" + the no_provenance/gone empties. |
| 5 | i18n + VERIFY | `scripts/i18n_translate.py --ns composition`; run the motif FE suite + tsc; a live browser smoke of the arc-templates panel drift section (structured view renders, honest empties). |

**VERIFY gate:** motif FE suite green + tsc clean + the ArcTemplatesPanel drift test asserts the structured render + a live smoke that the section shows real sections (not raw JSON). No BE change → no cross-service smoke needed.

**Out of scope (won't-fix here):** the `deep` prose-drift overlay (different axis); persisting a drift snapshot (`persist_conformance_state` deliberately never persists the template-drift path — [orchestrate:278-297](../../services/composition-service/app/engine/arc_conformance_orchestrate.py#L278)); re-run/spend (drift is a $0 read, no Tier-W confirm needed — unlike conformance re-run).
