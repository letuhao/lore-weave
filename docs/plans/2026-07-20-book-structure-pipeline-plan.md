# Plan / RUN-STATE — Book Structure Pipeline (build)

**Spec:** [`docs/specs/2026-07-20-book-structure-pipeline.md`](../specs/2026-07-20-book-structure-pipeline.md) (v2, adversarially reviewed).
**Goal (committed):** plan + build the spec; **QC + `/review-impl` + a live e2e test per slice** to prove each works.
**Branch:** feat/frontend-tools-mcp-migration. **Started:** 2026-07-20.

## Commitment / invariants (re-read after any compaction)
- Resolver owner = **book-service** (holds chapters + the `structure_node_id` join key + lifecycle; calls
  composition for the *small* parts list + active work, bearer-forwarded — the `parts_import.go` pattern via
  `cfg.CompositionServiceURL`).
- **Parts are always read** (book_id-scoped, Work-independent) → Bug 4 can't recur.
- **LEFT-JOIN-safe:** a chapter whose `structure_node_id` points at an arc / foreign / archived / missing
  node falls to **Unassigned**, never dropped, never filed under an arc.
- **No silent seams:** no silent chapter truncation (book-service owns chapters locally — page fully);
  writes validate targets (P2); FE surfaces mutation errors (P2).
- **Rail = mode-by-content + toggle** (parts-only→parts; outline-only→unchanged; both→toggle; neither→flat).
- Each slice: TDD → VERIFY (paste real output) → `/review-impl` → **live e2e** (real stack) → commit.

## Composition endpoints the resolver uses
- `GET /v1/composition/books/{book_id}/parts` → `{items:[{part_id,title,sort_order,lifecycle_state}]}` (arc.py:574)
- `GET /v1/composition/books/{book_id}/work` → active work (`work_id`, `project_id|null`) (works.py resolve_work)

## Slice board (done ⇒ an EVIDENCE string, not a checkmark)
- **P1.1 [x] book-service `GET /v1/books/{id}/structure` resolver** — `book_structure.go` + `_test.go` + route.
  EVIDENCE: 4/4 unit tests (grouping/sort/counts, LEFT-JOIN-safety, chapter-conservation, sources passthrough)
  + `go vet` clean + full api suite green; e2e-live on repro book 019f8027 → `{parts:[Part 1 count 2],
  unassigned 0, kinds:{parts:true,outline:false}, sources:{parts:ok,work:ok}}`. No book-service
  route-conformance gate exists (glossary-only), so no contract entry needed. NOTE: resolver returns the
  parts skeleton + `active_work.project_id` (kinds.outline = project_id!=null, the P1 outline signal);
  chapters lazy-loaded per group by the FE (P1.2).
- **P1.2 [~] FE `useManuscriptTree` reads `/structure` + mode-by-content + `[Parts|Outline]` toggle.** Files:
  structureApi.ts, manuscriptLens.ts (pure), useBookStructure.ts, useManuscriptTree.ts (source now lens-derived),
  ManuscriptNavigator.tsx (toggle). `source` is content-derived so a Work-book WITH parts → 'chapters' → loads
  parts (Bug 4 gone); outline-only → unchanged; partless → flat. EVIDENCE: 147 manuscript tests green (6 new
  lens + refactored hook + navigator + a HIGH regression test) + `tsc --noEmit` clean. `/review-impl` caught +
  FIXED: (HIGH) a /structure ERROR left the rail permanently 'pending' → now degrades to flat; (MED) creating
  the FIRST part didn't flip the lens until the 5s cache expired → invalidate /structure on create/trash/restore.
  e2e-LIVE (browser, vite :5199 → gateway, repro book 019f8027 = Part 1 + a REAL Work = outline mode): the
  Manuscript navigator renders "PART · Part 1 · 2" with Chapter 1 + Chapter 2 nested, the [Parts|Outline]
  toggle present, footer "1 part · 2 ch". Before P1.2 this book was outline-mode → Part 1 HIDDEN (Bug 4);
  now it shows. **P1 COMPLETE — Bug 4 fixed end-to-end (resolver → FE → live browser).**
- **P2.1a [x] Backend write silent-seam:** `setChapterPart` (HTTP, the FE drag path) validates the target is a
  LIVE part of this book via `validatePartTarget` (reuses P1.1's composition fetch) → typed error instead of
  silently accepting any UUID. EVIDENCE: go vet + e2e-live (bad UUID→422 BOOK_PART_NOT_FOUND, good→200,
  null-unhome→200, archived-part→422). review-impl: no HIGH (VIEW/EDIT-gated, 502 on composition outage).
- **P2.1b [x] FE surfaces part-mutation errors** — a `runAct(promise, msg)` wrapper toasts on failure; applied
  to ALL 8 mutation sites (create/rename/trash/restore/drag-move/reorder-up/down). A failed mutation now shows
  a toast instead of silently reverting on reload. EVIDENCE: 34 navigator vitest + tsc clean + browser
  regression (navigator still renders Part 1 + toggle, 0 console errors; the P2.1a 422 is what runAct now
  surfaces). The failed-drag case is the highest-value (a stale/bad part target → 422 → toast, no silent revert).
- **P2.1c [ ] mobile "Move to part…" affordance** (chapter→part is native-drag only — no touch path). DEFERRED.
- **P3 DECISION (user, 2026-07-20): Option C — soft-cascade via a dedicated `book_lifecycle` column.**
  Bounded realization (composition has ~20 book_id-scoped tables; a column on all is XL + leak-prone): put
  `book_lifecycle TEXT DEFAULT 'active'` on the TWO manuscript-structure ANCHOR tables — `structure_node`
  (parts/arcs) + `composition_work` (the Work) — which the spec's own model defines as "the book's manuscript
  structure". The 18 deep planning/generation tables are reached THROUGH a Work → gating the Work covers
  user-facing reads (extending the column to them = tracked follow-up). Order-safe RE-READ (not payload-trust,
  the codebase pattern): the consumer reads `GET /internal/books/{id}/projection` (returns lifecycle_state +
  kind for ANY state) and sets the column. NO kind-gate needed (a diary has no structure_node/composition_work
  rows → the cascade UPDATE is a 0-row no-op). Sub-slices:
  - **P3.1 [x] book-service:** `emitBookLifecycleChanged` (aggregate_type='book', payload {book_id}) via new
    `insertOutboxEventTyped`; a shared `transitionBookLifecycleTx` makes BOTH transition sites (HTTP
    `transitionBookLifecycle` + MCP `mcpTransitionBook`, previously bare-Exec + emit-nothing) transactional +
    atomic-emit. Resolver `getBookStructure` gates on the book's own lifecycle (non-active → empty skeleton +
    `book_lifecycle` marker, no composition fetch). EVIDENCE: new emit DB test green (trash/restore/re-trash/
    purge → 1/2/4 book.lifecycle_changed rows, book_id in payload, lifecycle correct) + **full api suite green
    27.5s (no regression from the tx refactor of the working lifecycle path)** + go vet + db-safety-gate=0.
    Relay auto-routes aggregate_type='book' → `loreweave:events:book` (zero worker-infra change). Inert until
    P3.2's consumer (events pile harmlessly, MAXLEN-trimmed).
  - **P3.2 [ ] composition:** migration (book_lifecycle ×2 anchor tables) + new `BookLifecycleConsumer`
    (mirrors `CompositionEventConsumer`: re-read projection → UPDATE book_lifecycle WHERE book_id) + wire into
    worker `__main__` + `/parts` (arc.py) & work-resolution reads exclude non-active. Python tests.
  - **P3.3 [ ] live e2e:** trash repro book → structure hidden (resolver + /parts) → restore → visible.
- **P3.1-OLD [scoped] Lifecycle cascade — sealed spec design is WRONG; needs a human call.** Scoping
  against real code found: (1) composition has **no dedicated book-lifecycle column** — `structure_node`
  has only `is_archived`, `composition_work` only `status active|archived`, BOTH *user-archive* flags. The
  spec §4.6 "soft-trash cascade" would overload them → the **un-archive-orphan bug** ([[feedback_symmetric_unarchive_orphans_node]]):
  restore would un-archive acts the user manually archived. (2) **No book-row purge sweeper exists** —
  `purge_pending` is terminal-but-retained (row lingers), so the "orphan" is LOGICAL (dead book, live
  structure) not a physical FK orphan. (3) TWO emit sites: HTTP `transitionBookLifecycle` (server.go:1188,
  non-tx) + MCP `mcpTransitionBook` (mcp_actions.go:880, already in a tx). GOOD NEWS: worker-infra
  auto-relays any `aggregate_type` to `loreweave:events:<type>` (outbox_relay.go:220, default MAXLEN) → the
  emit needs ZERO worker-infra change; composition's `CompositionEventConsumer` (events/consumer.py) is the
  exact consumer pattern to mirror (REQUIRED_EVENTS guard against silent-ack-into-void). **The real value
  (reclaim orphaned composition structure on purge) is a DESTRUCTIVE cross-service hard-delete that
  CONTRADICTS the user's "important data is soft-delete" principle** → surfaced for a design decision
  (options A: hard-delete-on-purge scoped by book_id; B: add a dedicated `book_trashed` column + soft-cascade
  — bigger blast radius; C: read-side resolver lifecycle-join only, non-destructive; D: defer). Kind-gate to
  novel (diary has no composition structure).
- **P4.1 [ ] Agent + guidance (rescoped):** `book_get_structure` MCP + metadata-vs-structure tool-selection guidance (or `book_get_overview`). Fixes Bug 2.
- **P5.1 [ ] Cleanup:** consolidate 3 `ensure_work` copies; "part" i18n across 18 locales + fix "Act One" arc seed; route `parts_import` + the arc-grouped Chapter Browser through the pipeline.

## Correctness must-fixes (fold into the touching slice)
- Verify C4 migration UUID-equivalence (test) · `has_work` = two bits (row-exists vs project-backed) · outline/part identity reconciliation.

## Registers
- **Decisions:** owner=book-service; rail=mode-by-content+toggle; drop eager-provision; P4=metadata-vs-structure; kinds_present.outline = the resolved active Work's `work.project_id`!=null (mirrors the FE's resolveActiveWork; a lazy/null-project Work ⇒ outline=false = 'chapters' mode).
- **Parked:** —
- **Debt:** (1) MED — no unit/contract test pins composition's `/parts` response shape the resolver parses (a
  field rename silently degrades parts to empty). `/work` shape now has `decodeStructureWork` regression tests;
  `/parts` still relies on the e2e. (2) LOW — the MCP tool `book_chapter_set_part` (agent path) is NOT yet
  target-validated like the HTTP path: the MCP ctx has `user_id` but no user bearer, and composition's `/parts`
  is bearer/VIEW-gated, so validation needs a new composition internal parts route (X-Internal-Token + X-User-Id).
  Mitigated: the resolver's LEFT-JOIN-safety makes a bad agent target read as Unassigned (visible, not lost).
- **Drift:** (P3) The sealed spec (§4.6/§7) prescribed a "soft-trash / restore / hard-delete cascade" of
  composition structure. Scoping against real code proved that design partially WRONG: composition has no
  dedicated book-lifecycle column, so a soft-trash cascade would ride `is_archived`/`status` and reintroduce
  the un-archive-orphan bug on restore. A sealed decision that turns out wrong + a destructive cross-service
  op = a mandatory human checkpoint (WORKFLOW.md), so P3 was STOPPED at design and surfaced rather than
  autonomously built. This is why "scope the slice against real code before building" is in the goal.
- **Drift:** P1.1 `/review-impl` + the Work-book e2e caught a REAL parse bug — `fetchStructureWork` read the top-level `book_project_id` (null for a resolved work) instead of the nested `work.project_id`, so kinds.outline was ALWAYS false → the FE toggle would never appear for a planned book. FIXED + regression-tested (`decodeStructureWork`) + re-e2e'd (repro book with a real Work → outline:true, parts still present). This is why e2e-per-slice is in the goal.
