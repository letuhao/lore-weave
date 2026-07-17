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
- [x] A6 Playwright E2E spec `studio-arc-drift.spec.ts` (parses — 1 test listed) + **blackbox Playwright-MCP smoke on :5199** (seeded book+work+template+arc-stamped via the real gateway; opened arc-templates via Ctrl+Shift+P palette → selected template → clicked the drift arc). **EVIDENCE:** `arc-drift-view` rendered live, `arc-drift-report` (raw `<pre>`) GONE, real EN i18n ("No drift — the realized arc matches its template… Not comparable yet… No ordering violations"), 0 console errors. The direct drift route returned `{thread_progress:[],pacing:{comparable:false},…}` — the real ArcConformance shape (confirms the type reconcile end-to-end).
- [x] A7 /review-impl: pure FE presentational change — no ENFORCED/LOCKED standard touched (no tool schema, no provider/model/table, reads an existing VIEW-gated route). Found + fixed ONE real gap: a **pacing-ONLY drift** (structure clean, curve moved) made `clean=false` yet the summary read "0·0·0" — added a dedicated `driftPacingOnly` line + test. **EVIDENCE: 6 view tests** green; i18n +1 key × 17 locales.

**A · arc-template-drift-view — DONE ✅** (commits f93d77616, 24db0a196, + review fix). Structured drift view live-proven, E2E + blackbox MCP done, /review-impl clean.

### B · motif graph-canvas (XL, BE-first)
- [x] B1 BE: `motif_graph_layout` table (migrate.py, applied to dev DB) + `MotifGraphLayoutRepo` (get + batch server-side merge `positions||moves` + OCC via `version`; nodes_for_book + edges_among + motif_visible_in_book). **EVIDENCE: 5 unit tests** (SQL shape, owner-scope, OCC-None). Real merge/OCC behaviour → B7 live smoke.
- [x] B2 BE: `GET /books/{id}/motif-graph` (nodes+edges+layout, VIEW-gated, node-cap + `truncated`) + `PATCH …/layout` (batch merge, OCC 412 + reseed `current`, foreign-motif 404 no-oracle). **EVIDENCE: 5 route tests** (shape, truncation, merge, 412-reseed, foreign-404).
- [x] B3 FE: `MotifGraphCanvas` (reactflow v11 controlled useNodesState + onNodesChange + nodeDragThreshold=5 + drag-stop persist) + bespoke layered `autoLayout` (Kahn longest-path, no dagre dep) + `posOf` stored??auto??default + read-only-safe.
- [x] B4 FE: `useMotifGraph` — book-graph query + pending-MAP + debounced batch flush + optimistic cache + fail-soft 412 reseed+retry + flush-on-unmount/hide.
- [x] B5 register `motif-graph`: catalog row + chat panel_id enum + contract.json + studio.json + composition canvas keys (distinct from the section's — restored the ones I'd clobbered). **EVIDENCE: 13 panel-contract + 71 chat-service contract tests green.**
- [x] B6 unit: `MotifGraphCanvas.test.tsx` (7) + `useMotifGraph.test.tsx` (2 — pending-map batches both / 412 reseed+retry). **EVIDENCE: 904 motif+panel green, tsc clean, i18n +keys × 17 locales (0 failed).** Playwright CDP live-drag + blackbox → B7.
- [x] B6-live + B7 — `studio-motif-graph.spec.ts` (CDP stepped-mouse drag, the d3-drag recipe) **RAN GREEN LIVE (9.0s) against :5199 + the rebuilt composition BE**: opened the motif-graph panel via the palette → the canvas + reactflow node rendered → CDP-dragged the node → the debounced PATCH persisted the position (asserted via `GET /books/{id}/motif-graph` → `layout.positions[m1]` set) → survived a reload. This IS the blackbox live-drive + the cross-service smoke (FE canvas → PATCH → composition → DB → reload). GET route also confirmed live cross-service via the gateway. **Playwright-MCP blackbox (retried once the profile freed):** the motif-graph panel is palette-reachable, the canvas renders 22 nodes + 1 edge live, 0 console errors — so MCP confirms live render/reachability and the CDP spec confirms the drag→persist loop (the drag itself needs trusted page.mouse for d3-drag; browser_drag is synthetic).
- [x] B8 /review-impl: standards clean (tenancy scope key + owner-scoped PATCH; panel_id enum both sides machine-checked; no localStorage—DB; no MCP tool—cosmetic GUI; no provider/model). Fixed LOW: capped the 412 reseed-retry (≤3) so an always-stale server can't spin (2 hook tests still green). Recorded DEBT below.

**B · motif graph-canvas — DONE ✅** (commits: BE `05445221b`-adjacent, FE B3-B6, live E2E `d7a8fb59d`, +this review fix). Persisted per-viewer positions live-proven end-to-end (drag→PATCH→DB→reload).

### DEBT (from B8 review)
- **D-MOTIF-GRAPH-BOOK-SCOPING — CLEARED (2026-07-17, PO chose Option B).** The graph is now the book's
  STORY graph: `nodes_for_book`/`motif_visible_in_book` gate on `_BOOK_NODE_PREDICATE` = the book's shared
  tier ∪ the caller's OWN motifs BOUND in this book (a `motif_application` row); system stays excluded
  (islands). ONE shared SQL fragment → a shown node is always position-able, a non-node always rejected (a
  test asserts both queries use it). Spec: [`docs/specs/2026-07-17-motif-graph-book-scoping.md`](../specs/2026-07-17-motif-graph-book-scoping.md).
  **EVIDENCE:** live GET smoke — a BOUND own motif shows, an UNBOUND own motif (and the caller's whole prior
  library) absent; `studio-motif-graph.spec.ts` updated to BIND a motif then drag it → **RAN GREEN LIVE
  (12.9s)**; 11 graph unit/route tests green. /review-impl clean (tenancy tightens never widens; EXISTS is
  index-backed by `idx_motif_application_book_motif`). Deferred: a "show my whole library" toggle (Option A).

## REGISTERS (append as you go)
### DECISIONS
- (build order: A before B — A is FE-only quick win, B is XL BE-first)
### PARKED
### DEBT
### DRIFT (near-misses — an empty log at the end is dishonest)
