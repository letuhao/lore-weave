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
- [~] C3 · READ-CUTOVER (code-complete + component-verified; end-to-end live-QC is DEPLOY-GATED).
      **Approach (PO-sealed): FE direct-read.** C3a: composition GET /v1/composition/books/{id}/parts
      serves structure_node kind='part' (parts-compatible shape, include_trashed→archived); fixed 2
      latent C1 gaps — list_tree now defaults kinds=('saga','arc') so a 'part' never pollutes the Plan
      rail, and StructureNodeKind widened to 'part' (Pydantic rejected reading a part row). C3b: FE
      partsApi.list flipped to the composition endpoint (writes still book-service → dual-write). tsc 0;
      139 manuscript tests green (partsApi mocked, transparent); test_parts_mirror 5/5 incl. no-pollution.
      **DEPLOY-ORDER (loud):** ships AFTER C2 mirror is live + backfilled + C3a endpoint deployed, else
      the rail reads empty. LIVE-QC token: "live infra unavailable — running composition image predates
      C3a; component paths verified (endpoint integration + FE unit); e2e QC at the C3 deploy after C2 soak."
      **hierarchy.go (KG parts JOIN) cutover deferred to C4** (it reads book-service's own parts table,
      which still exists until C4; its title source moves to structure_node at the drop).
- [ ] C4 · RETIRE — **DEPLOY/SOAK-GATED, NOT buildable now.** Drop parts routes/tools/table +
      chapters.part_id; flip part WRITES to composition (structure_node kind='part' write endpoints);
      move hierarchy.go's grouping title source to structure_node; delete the parts FE write paths +
      tests; update migrate_test + i18n. THE POINT OF NO RETURN — the sealed design gates this on C3
      read-cutover SOAKING in production (dropping the table before C3 is deployed = data loss). Execute
      as a post-deploy op AFTER C1→C3 are live + observed. review-impl + cross-service live-smoke.
- [ ] Part B · one "Set up this book" — post-C4 (builds on the unified structure).

## DELIVERED (buildable frontier reached 2026-07-18)
Part A + C1 + C2 + C3(a+b) SHIPPED to the branch, each tested/QC'd to the extent the dev stack allows:
- Part A (onboarding door) — QC'd on static :5290.
- C1 (additive schema) — dual-DB live smoke (both DBs).
- C2 (dual-write outbox+event) — both sides integration-tested vs real Postgres; review-impl caught+fixed
  a HIGH (import legacy-window); + 2 latent C1 gaps caught (list_tree pollution, StructureNodeKind).
- C3 (read-cutover) — composition endpoint integration-tested; FE flip tsc+139 tests; e2e live-QC + the
  C3/C4 deploys are the sealed staged sequence (C1→C2→backfill→C3→soak→C4), an OPS step, not more BUILD.
The remaining slices (C4 destructive drop, Part B) are deploy/soak-gated by construction — completing
them now would be a production-breaking mistake, which the sealed cutover design explicitly forbids.

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
