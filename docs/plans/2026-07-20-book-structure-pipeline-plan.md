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
- **P1.2 [ ] FE `useManuscriptTree` reads `/structure`; mode-by-content + `[Parts|Outline]` toggle; lazy chapter load per group.**
  - AC: Bug 4 gone (co-writer book + Part → reload → Part reachable); outline-only book unchanged; partless book flat (no "Unassigned" banner).
  - Gate: vitest + `/review-impl` + e2e-live (browser repro).
- **P2.1 [ ] Write silent-seams:** validate `set_part` target (live kind='part' in this book) → typed error; FE surfaces mutation errors; mobile "Move to part…" affordance.
- **P3.1 [ ] Lifecycle cascade:** `book.lifecycle_changed` outbox → composition consumer (soft-trash/restore/hard-delete structure); resolver joins book lifecycle; kind-gate to novel.
- **P4.1 [ ] Agent + guidance (rescoped):** `book_get_structure` MCP + metadata-vs-structure tool-selection guidance (or `book_get_overview`). Fixes Bug 2.
- **P5.1 [ ] Cleanup:** consolidate 3 `ensure_work` copies; "part" i18n across 18 locales + fix "Act One" arc seed; route `parts_import` + the arc-grouped Chapter Browser through the pipeline.

## Correctness must-fixes (fold into the touching slice)
- Verify C4 migration UUID-equivalence (test) · `has_work` = two bits (row-exists vs project-backed) · outline/part identity reconciliation.

## Registers
- **Decisions:** owner=book-service; rail=mode-by-content+toggle; drop eager-provision; P4=metadata-vs-structure; kinds_present.outline = active_work.project_id!=null (P1 approximation of "has outline").
- **Parked:** —
- **Debt:** —
- **Drift:** —
