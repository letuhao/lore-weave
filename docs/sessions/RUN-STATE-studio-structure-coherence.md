# RUN-STATE — Studio Onboarding Door & Structure Coherence (C-merge)

> Re-read this FIRST after any compaction, then `git log`, then continue. The commitment + slice board.

## GOAL (PO-sealed 2026-07-18)
Clear the "one shared door" + F6/C deferrals **completely**. Spec:
`docs/specs/2026-07-18-studio-onboarding-and-structure-coherence/{spec,c-merge-design}.md`.
PO signed off the C-merge design: **arcs-win SSOT**, `structure_node` absorbs `parts`, boundary reframe
(book-service = prose containers · composition = structure), grouping = new `kind='part'`, staged
C1→C4 cutover, `/review-impl` + cross-service live-smoke on every C-slice.

## HARD CONSTRAINTS (invariants — do not violate)
1. **DESTRUCTIVE MIGRATION — additive-first, reversible until C4.** Never big-bang. C4 (drop parts) only
   after C3 read-cutover soaks. Each slice independently shippable + reversible.
2. **Cross-service:** touches book-service (Go) + composition (Python) + gateway (TS) + frontend. I3
   language rule is LOCKED — structure→composition is the accepted reframe, not a violation.
3. **Every C-slice:** `/review-impl` (cold-start adversarial) + cross-service live-smoke (≥2 services) +
   contract-first for composition arc-route additions.
4. **QC on the isolated static FE build :5290** (never vite dev) for FE-visible slices.
5. **Shared checkout:** commit only THIS track's files by explicit pathspec; foreign changes abound.
6. **Two chapter models hazard** (`chapters.part_id` vs `outline_node.structure_node_id`): C2 dual-write
   + a consistency check gate the strand risk. This is the deepest danger — treat with care.

## SLICE BOARD (done = an evidence string)
- [x] SPEC + C-merge DESIGN + PO sign-off — commits ce…, 6fd4e5e35 (+ sign-off edit).
- [x] Part A · shared <BookNotReadyDoor> across studio dock panels — committed. tsc 0, 797 tests,
      QC :5290 (Places redirect→door, WhatIf dead-text→door, Ref/Style consolidated).
- [ ] Part B · one "Set up this book" (useBookReadiness + usePlanOrigin) — **RESEQUENCED to after C4**
      (gate: naturally-next-phase). It creates a *plan*, the exact structure C-merge reshapes; building
      it on the unified post-merge model avoids rework. Part A already removed the dead ends, so nothing
      user-facing regresses by waiting. FE-only when it lands.
- [x] C1 · ADDITIVE — `structure_node.kind='part'` (composition migrate.py: inline + idempotent
      DROP/ADD structure_node_kind_check) + `chapters.structure_node_id` UUID nullable, no-FK cross-DB
      id + `idx_chapters_structure_node` (book-service migrate.go, alongside part_id). migrate_test
      asserts extended both. Go schema tests green; composition migrate.py valid. LIVE-SMOKE (dual-DB):
      loreweave_composition accepts kind='part' (depth auto-0) + still rejects bogus; loreweave_book
      has structure_node_id (nullable, coexists w/ part_id) + the index. Review: additive-only, focused
      inline (idempotent, auto-constraint-name verified live, no-FK correct); cold-start review-impl
      reserved for C2+ (data/logic slices). Reversible: nothing reads/writes the new fields.
- [~] C2 · DUAL-WRITE (built + tested both sides; review-impl next; full stack-up smoke deferred).
      **book-service**: all 6 part mutations emit `manuscript_part.changed {book_id}` (aggregate_type
      'book') ATOMICALLY (3 pool-direct methods tx-wrapped); moveChapterToPart stamps
      chapters.structure_node_id=part_id (== value), archive nulls it; GET /internal/books/{id}/
      parts-mirror + POST /internal/parts-mirror/backfill. Tests: TestParts_C2_EmitsAndMirrors (4 events
      + structure_node_id assert) + InternalPartsMirror — green vs dev DB.
      **composition**: PartsMirrorConsumer (own group, BOOK_STREAM) → book_client.list_parts_mirror
      (raises on fail → retry, never blank) → reconcile_book_parts (upsert kind='part' by id==part.id
      depth0, archive absent). Test: test_parts_mirror 4/4 vs throwaway Postgres (upsert/rename/reorder/
      archive/reactivate). Transport reuses the proven written-verdict relay+BaseProjectionConsumer path.
      LIVE-SMOKE (full emit→relay→consume) deferred: running images predate C2; each half live-verified
      + transport is proven infra → token "live infra unavailable: stack images predate C2".
- [ ] C3 · READ-CUTOVER — Manuscript rail + hierarchy read structure_node via gateway; partsMode
      collapses; two rails unify click contract. FE flips. review-impl + live-smoke + QC :5290.
- [ ] C4 · RETIRE — drop parts routes/tools/table + chapters.part_id; delete parts FE + tests; update
      migrate_test + i18n. THE POINT OF NO RETURN — only after C3 soaks. review-impl + live-smoke.
Build order: Part B → C1 → C2 → C3 → C4.

## DELIVERED
- Part A (onboarding door) — see commit log. useBookReadiness deferred to Part B (was write-only in A).

## REGISTERS (append as you go — an empty drift log at the end is dishonest)
### Decisions
- SSOT arcs-win: a part = a trivial depth-0 structure_node; reverse would rewrite composition's engine.
  book-service parts have NO OpenAPI contract + NO events (nothing downstream to migrate) — the small side.
- grouping `kind='part'` (not overloaded depth-0 arc) so a drafter's grouping carries no generation semantics.
### Parked / blocked
- (none yet)
### Debt
- (none yet)
### Drift / near-misses
- Part A: PlaceGraphPanel.test asserted the old Compose-redirect CTA → updated to assert the shared door
  (mocked BookNotReadyDoor at the consumer boundary; the door's own behavior tested separately).
- Part A: removed useBookReadiness.ts before commit — it had no consumer yet (write-only) → moved to Part B.
- **C2 review-impl HIGH (caught + fixed):** `parse.go` (the IMPORT decomposer — the commonest source of
  parts) wrote parts + chapters.part_id WITHOUT structure_node_id or the emit → imported books would
  diverge from the C1/C2 mirror invariant. Classic close-legacy-window-in-writer. Fix: (a) import INSERT
  now sets structure_node_id=part_id inline; (b) import emits manuscript_part.changed post-loop
  (best-effort, backfill is recovery); (c) the /internal backfill endpoint now ALSO repairs existing
  chapters (structure_node_id=part_id WHERE NULL). Test: TestParts_C2_BackfillRepairsLegacyStructureNodeID.
- C2 review-impl LOW (accepted): reconcile ON CONFLICT WHERE kind='part' silently skips an id-collision
  with a real arc (impossible under uuidv7) — documented, not guarded. Backfill re-run appends outbox
  rows (no dedup) — fine, it's a manual one-time/drift-resync endpoint.
- C2 review-impl standards check: I3 OK (structure→composition is the sealed reframe); tenancy OK
  (/internal parts-mirror is X-Internal-Token, book_id-scoped, mirrors the sibling /internal/chapters
  pattern); INV-O12 honored (emit err → return-before-commit → rollback). No provider/model/secret touched.
