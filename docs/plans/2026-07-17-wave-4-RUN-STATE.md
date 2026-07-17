# Wave-4 BUILD — RUN-STATE (the on-disk commitment; re-read after every compaction)

## GOAL (set 2026-07-17)
Build + QC **both** Wave-4 features, including a Playwright E2E script AND a blackbox Playwright-MCP
smoke (drive the real app as a user) for each:
- `docs/specs/2026-07-17-arc-template-drift-view.md` (S)
- `docs/specs/2026-07-17-motif-graph-canvas.md` (XL)

**DONE means** (evidence pasted into the transcript, not merely claimed):
- unit/integration tests green (pasted counts), tsc clean;
- `/review-impl` run (no unresolved HIGH);
- a Playwright E2E spec committed per feature;
- a blackbox Playwright-MCP run per feature (real browser, real app) — pasted observation;
- cross-service live-smoke for the graph-canvas (BE+FE) — pasted;
- SESSION_HANDOFF / this RUN-STATE updated + committed.

## INVARIANTS (do not violate)
- FE MVC (hooks own logic, components render), no localStorage for user data, tenancy scope keys,
  Frontend-Tool Contract (enum panel_id both sides), no-silent-fail, i18n via `i18n_translate.py`.
- Shared checkout: multiple sessions on `feat/context-budget-law` — stage ONLY my files; re-verify HEAD
  after commits (a concurrent reset already dropped one of my commits once).

## SLICE BOARD  (DONE requires an EVIDENCE string, not a checkbox)

### A · arc-template-drift-view (S, FE-only)
- [x] A1 type reconcile: `ArcDriftReport` stub DELETED → `getArcTemplateDrift` returns real `ArcConformance`.
- [x] A2 `ArcTemplateDriftView.tsx` (summary + coverage + pacing + succession + folded; honest empties; null motif_code → `#ord`) + 11 en i18n keys.
- [x] A3 swapped the `<pre>` in `DriftSection` for `<ArcTemplateDriftView>` (no_provenance/gone/unapplied/loading branches kept).
- [x] A4 tests: REWROTE the fictional `thread_coverage` fixture → real `thread_progress` shape (E1); `ArcTemplateDriftView.test.tsx` (clean verdict, derived summary, null-code→#ord, pacing-NC, empty threads). **EVIDENCE: 14 passed** (5 view + panel suite).
- [x] A5 i18n +11 keys × 17 locales via `i18n_translate.py` (0 failed); tsc clean (arc-drift files); **EVIDENCE: 898 passed** (arcTemplates + motif + studio panels).
- [ ] A6 Playwright E2E spec + blackbox Playwright-MCP smoke
- [ ] A7 /review-impl + commit

### B · motif graph-canvas (XL, BE-first)
- [ ] B1 BE: `motif_graph_layout` migration + `MotifGraphLayoutRepo` (get + batch merge + OCC) + tests
- [ ] B2 BE: `GET /books/{id}/motif-graph` + `PATCH …/layout` (batch, OCC 412, owner-scoped) + route tests
- [ ] B3 FE: `MotifGraphCanvas` (reactflow v11: controlled + onNodesChange + threshold + cursor drop) + bespoke layered auto-layout + `posOf` fallback + pending-map debounced persist + 412 reseed + edge create/delete + read-only
- [ ] B4 FE: `useMotifGraph` hook
- [ ] B5 register `motif-graph` panel (catalog + enum + contract regen + i18n)
- [ ] B6 tests: PlanCanvasDrag-style RF unit + persist test + Playwright CDP live-drag
- [ ] B7 blackbox Playwright-MCP smoke + cross-service live-smoke (drag → PATCH → DB → reload persists)
- [ ] B8 /review-impl + commit

## REGISTERS (append as you go)
### DECISIONS
- (build order: A before B — A is FE-only quick win, B is XL BE-first)
### PARKED
### DEBT
### DRIFT (near-misses — an empty log at the end is dishonest)
