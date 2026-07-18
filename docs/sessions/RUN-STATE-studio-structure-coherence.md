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
- [ ] C2 · DUAL-WRITE — **mechanism (PO-sealed): transactional outbox + event** (book-service emits
      `manuscript_part.*` via its existing outbox in the mutation txn; a composition consumer upserts
      the mirror). **Design refinement: structure_node.id == part.id** (1:1 same-UUID mirror) ⇒
      chapters.structure_node_id == chapters.part_id numerically, upsert-by-id is trivially idempotent,
      and C4 becomes a pure column rename. book-service stamps chapters.structure_node_id=part_id in the
      same txn as setChapterPart (nothing reads it till C3). Backfill: synthetic upsert events for
      existing parts. Consistency check. review-impl (cold-start) + cross-service live-smoke.
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
