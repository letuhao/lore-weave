# RUN-STATE — S-02 manuscript parts (acts/volumes) — book-service

> Re-read this FIRST after any compaction, then `git log`, then continue. Do NOT re-litigate sealed decisions from memory.

## Commitment / GOAL
Build spec S-02 (`docs/specs/2026-07-17-studio-completeness-build/S-02_manuscript-parts.md`) to a
**genuinely usable** state — not a view-only hollow shell (the Plan-Hub failure the PO called out).
Done = S-02 built + scoped tests green (real pasted output) + `/review-impl` pass (data-layer/tenancy).

## Invariants I must hold (parallel-session checkout)
- **NO `git add -A`.** Stage only files I authored. book-service is MINE in this fanout (S-01/03/04 = composition).
- **DO NOT stage** `ManuscriptNavigator.tsx` / `StudioSideBar.tsx` — they carry ANOTHER session's
  uncommitted work (studio-first-use-cold-start fix). Editing them would entangle their diff into my commit.
- Studio FE registry (catalog.ts / panel_id enum / frontend-tools.contract.json / i18n) = convergence node → manifest, don't self-edit.
- `git pull --rebase` before any push. Scoped tests during BUILD; full suite = convergence gate.

## Sealed decisions (from 01_DECISIONS.md — do not re-open)
- `path` for a user-created part = **synthesize from title** (slugify), keep NOT NULL. No migration.
- **No OCC on parts** — low-contention rename; `updated_at` + last-write-wins.
- Trashing a part **un-homes** its chapters (`part_id=NULL`), never cascade-deletes. Restore does NOT re-home.
- Move-chapter-to-part must verify target part is in the SAME book (cross-book move = tenancy breach).

## Slices (usability-first ordering)
- [ ] **A — Parts DATA layer (REST + repo).** `parts.go`: create/rename/reorder/archive/restore/move + list;
      7 routes in server.go; expose `part_id` in listChapters + listChaptersKeyset (the FE grouping seam).
      Usability: the load-bearing enabler; consumed by B (agent) and C (FE).
- [ ] **B — MCP tools (agent parity).** `book_part_{create,rename,reorder,archive,restore}` + `book_chapter_set_part`.
      Usability: **operable with NO new GUI** — user drives it through the studio assistant. Anti-hollow-shell insurance.
- [ ] **C — FE two-level tree.** Self-contained parts api + PartsTree + hook + tests. Navigator MOUNT →
      manifest (foreign uncommitted diff blocks a clean stage). Direct-manipulation GUI.

## Evidence log (paste real output here as each slice VERIFYs)
- **Slice A (2026-07-17):** `go test ./internal/api/ -run TestParts_ -v` — 7/7 PASS
  (CRUD, ArchiveUnhomesChaptersNotCascade, MoveChapter, CrossBookMoveBreach, ViewCanReadNotWrite,
  ReorderValidation, ChapterListExposesPartId). Full `internal/api` package `ok 24.672s` (no regression).
  migrate-package deadlock/backfill failures = shared-DB test residue (green on fresh DB), not S-02.
  DB: throwaway `loreweave_book_s02test` on PG18 :5555.

## Registers
### Decisions
- (2026-07-17) Ordered B before C so the feature is human-operable via the assistant even before the drag GUI lands.
### Parked
- Navigator mount (Slice C) blocked on foreign uncommitted diff → deliver component + manifest note, not a stomp.
### Debt / bugs fixed in-flight
- (2026-07-17) FIXED pre-existing latent bug: `listChapters`+`listChaptersKeyset` scanned NULLABLE
  `title` into a non-pointer `string` → a titleless chapter errored the discarded `_ = rows.Scan()`
  and zeroed every column after `title` (sort_order, lifecycle_state, part_id). Surfaced when adding
  part_id. Fix = scan `title *string` + `nullableStringPtr` (matches getChapterByID). In-scope
  (navigator surface), root-cause-clear, one-file → fixed now per defer gate.
- NOTE (not fixed, out of scope): `_ = rows.Scan()` discarding the error is a broader footgun; only
  `title` is a NULLABLE-into-non-pointer dest today, so the pointer fix closes the actual bug.
### Drift / near-misses
- (record as they happen)
