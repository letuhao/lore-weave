# RUN-STATE — S-07 build (world-maps OCC + missing agent verbs)

> Backend-only (book-service, Go). Three narrow consistency/parity gaps the world/book audit named.
> Spec: S-07_world-occ-and-agent-verbs.md. Decisions: 01_DECISIONS.md (4 S-07 rows).

## THE COMMITMENT
Build S-07 §1 (world_map OCC on MCP update + decouple image upload from rename), §2 (world_update +
world_delete MCP verbs), §3 (book_chapter_reorder MCP tool). DONE = built + DB-proven tests + committed.

## INVESTIGATE (verified vs code 2026-07-18 — the spec's line-refs held)
- §1: `patchMapREST` gates `AND version=$3` (412). `toolWorldMapUpdate` bumped `version` with NO predicate
  (blind LWW). Image upload bumped the metadata `version` deliberately (so a rename saw a stale version) —
  which is exactly the collision the decision kills. `world_maps.version` exists; NO `image_version` → migration.
- §2: MCP registered only world_list/get/create/move (`registerWorldTools`). REST had patchWorld/deleteWorld.
  `books.world_id` is ON DELETE SET NULL → a world delete ORPHANS member books (informs the delete guard).
- §3: reorder was REST-only + monolithic in the handler. `book_chapter_set_part` (S-02) already exists as
  the pairing tool. The two-phase negate/rewrite dodges the partial UNIQUE(book_id, sort_order, orig_lang).

## SLICE BOARD (done = evidence)
- [x] Slice A §1 — image_version migration (CREATE literal + ALTER) · image upload → `recordMapImage` bumps
      image_version ONLY · MCP world_map_update `expected_version` OCC (conflict names current version, 404 vs
      412 disambiguated) · FE type renamed. EVID: TestWorldMapUpdate_OCC + TestMapImageUpload_DecouplesFromRename
      PASS (real PG); all Map/World tests green. Commit 66020b719.
- [x] Slice B §2 — world_update (TierA, owner-scoped, undo hint) + world_delete (TierA, owner-scoped hard
      delete, guarded to refuse non-bible member books) + registered. EVID: TestWorldUpdate_RoundTrip +
      TestWorldDelete_GuardAndScope PASS (real PG). Commit d1b811ce6.
- [x] Slice C §3 — extract `lockActiveChapterTrack`+`writeChapterTrackOrder` (REST refactored to use them,
      behaviour-preserving) + `book_chapter_reorder` MCP tool (full-permutation validated) + registered.
      EVID: TestChapterReorder_MCP{,_RejectsBadLists,_RequiresEdit} PASS; REST reorder suite still green.
      Commit 58863d092.

## VERIFY (evidence)
- `go build ./...` clean. `go vet ./internal/api/` exit 0.
- **book-service `internal/api` FULL suite (real Postgres, BOOK_TEST_DATABASE_URL) = `ok` 24.3s** — every
  S-07 change lives here; green includes the 7 new S-07 tests + no regression in the existing Map/World/
  reorder suites.
- FE `tsc --noEmit` whole-project = 0 errors (the WorldMapImageResponse field rename). Provider gate OK.
  Pre-commit tool-tier gate: every write-named tool carries a non-R tier (my 3 new tools are TierA).
- KNOWN-FLAKY (NOT S-07): `internal/migrate/backfill_scenes_db_test.go` (TestBackfillScenesBookID_*) fails
  under the shared dev DB — `deadlock 40P01` in parallel, "wrong book_id" serially. Scenes-backfill code,
  untouched by S-07; documented shared-dev-DB-dirty + parallel-migration-deadlock flakies. `live infra:
  shared dev DB carries other sessions' scene rows`.

## DECISIONS (sealed — 01_DECISIONS.md)
- image upload → own `image_version`, never metadata `version` (pre-sealed).
- world_map_update: OPTIONAL expected_version (present ⇒ OCC; absent ⇒ LWW).
- **D-S07-world-delete-guard**: world_delete refuses while non-bible member books remain (delete SET-NULLs
  → would orphan them). Direct TierA + guard, not the TierW confirm spine.
- book_chapter_reorder: complete ordered list, exact-permutation validated; shares the two-phase engine.

## DRIFT LOG (near-misses)
- The very first migrate build broke: a SQL comment used backticks (`` `version` ``) INSIDE the Go
  raw-string literal → prematurely closed the string. Caught by `go build`; the IDE's earlier "false
  positive" diagnostic on that line was actually real. Fixed (removed backticks).
- Slice A's image_upload change removed the `version` return var but a response field still read it →
  caught by build; renamed to image_version end-to-end (incl. FE type).

## ═══ COMPLETENESS AUDIT (goal, 2026-07-18) — clear all debts/defers/bugs of S-07 ═══
Fresh adversarial pass vs code (not trusting this RUN-STATE). Three probes:
- AUD-A (reorder downstream sync): CLEAN. book-service emits only `chapter.scenes_linked` + import
  job events — NO chapter-order event. REST reorder emits nothing (comment: "caller's mirror must be
  rebuilt"). So the MCP reorder tool is at EXACT parity with the REST route; an agent reorder is no
  more stale than a human one. Not a gap.
- AUD-B (world_delete orphaned the bible): REAL LEAK, FIXED. `deleteWorld` did a raw `DELETE FROM
  worlds`; `books.world_id` is ON DELETE SET NULL, so the hidden bible book survived as an ACTIVE,
  world-less book that NO purge sweeper collects (its KG/glossary anchors stranded). A normal book
  delete instead flips book+chapters to `purge_pending` (mcp_actions.go). FIX: a shared
  `deleteWorldWithBiblePurge` helper (used by BOTH the MCP world_delete tool AND REST deleteWorld)
  routes the bible through purge_pending atomically, owner-scoped; member (non-bible) books still
  SET-NULL back to standalone. Test asserts the bible book + its chapters are purge_pending after a
  delete. Pre-existing REST behaviour, fixed at the source for both surfaces.
- AUD-C (image_version write-only?): NO — it's read + returned on the upload response (RETURNING).
  Surfacing it in world_map_get/list is speculative (no image-OCC consumer exists yet; the upload has
  no expected_image_version) and costs a 5-SELECT worldMapDetail change for zero current reader.
  Conscious not-now (add it when an image-OCC path lands), not a debt.
Audit VERIFY: full `internal/api` suite green (real PG, 24.9s) incl. the extended world_delete test;
build clean. No open S-07 debts/defers/bugs remain.

## RESULT: S-07 COMPLETE + AUDITED — all three gaps closed, the bible-orphan leak cleared, backend-only,
## DB-proven. Commits: 66020b719 (§1) · d1b811ce6 (§2) · 58863d092 (§3) · 7b4ca76d8 (docs) · +audit fix.
