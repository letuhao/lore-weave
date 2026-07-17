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

## STATUS: S-02 COMPLETE (backend + agent path shipped; GUI render → CONVERGENCE-S02.md)
Commits: b56725e05 (A) · 4cc462f36 (B) · 190795cb1 (C) · dfbf3392b (review fix). On feat/context-budget-law (not pushed).

## Slices (usability-first ordering)
- [x] **A — Parts DATA layer (REST + repo).** `parts.go`: create/rename/reorder/archive/restore/move + list;
      7 routes in server.go; expose `part_id` in listChapters + listChaptersKeyset (the FE grouping seam).
      Usability: the load-bearing enabler; consumed by B (agent) and C (FE).
- [x] **B — MCP tools (agent parity).** `book_part_{create,rename,reorder,archive,restore}` + `book_chapter_set_part`.
      DONE 2026-07-17 (commit pending). Shared store methods (no REST/MCP drift); Undo hints per tool.
      Usability: **operable with NO new GUI** — user drives it through the studio assistant. Anti-hollow-shell insurance.
- [~] **C — FE building blocks DONE; navigator render handed to convergence.** Shipped: `partsApi.ts`
      (typed client + pure `groupChaptersByParts`, 8 unit tests) + `Chapter.part_id`. The render/affordances/
      drag edit the FOREIGN `ManuscriptNavigator.tsx`/`useManuscriptTree.ts` → speced in
      [`CONVERGENCE-S02.md`](CONVERGENCE-S02.md), not stomped. Human-usable GUI lands at convergence;
      human-usable ASSISTANT path is live now (Slice B).

## Evidence log (paste real output here as each slice VERIFYs)
- **Slice A (2026-07-17):** `go test ./internal/api/ -run TestParts_ -v` — 7/7 PASS
  (CRUD, ArchiveUnhomesChaptersNotCascade, MoveChapter, CrossBookMoveBreach, ViewCanReadNotWrite,
  ReorderValidation, ChapterListExposesPartId). Full `internal/api` package `ok 24.672s` (no regression).
  migrate-package deadlock/backfill failures = shared-DB test residue (green on fresh DB), not S-02.
  DB: throwaway `loreweave_book_s02test` on PG18 :5555.
- **Slice B (2026-07-17):** `go test ./internal/api/ -run TestMCPParts -v` — 4/4 PASS
  (CreateRenameArchiveRestore + undo hints, Reorder + prior-order undo, SetPart round-trip + cross-book
  breach → errPartNotInBook, TenancyDenied → errBookNotAccessible). Refactored REST → shared store methods,
  TestParts_ still 7/7. Full `internal/api` `ok 23.1s`. Single-service ⇒ no cross-service live-smoke token;
  DB tests ARE the live proof (real PG18 + real router + real MCP handlers; tools boot-validated by MustValidateToolMeta).
- **Slice C (2026-07-17):** `npx vitest run partsApi.test.ts` — 8/8 PASS (grouping: sort order, within-group
  order, Unassigned bucket for null/trashed/unknown-act, empty act renders, empty-bucket hide/show, flat book,
  no-mutate). `npx tsc --noEmit` exit 0 (clean full FE typecheck — my additions don't break the build).
  Navigator render → CONVERGENCE-S02.md (foreign-file constraint).

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
### /review-impl (2026-07-18) — findings
- **MED [parity] FIXED (commit dfbf3392b):** `toolPartCreate` skipped the book-lifecycle gate that REST
  `createPart` + sibling create tools enforce → could add an act to a trashed book. Mirrored + tested.
- **LOW [race] accept+document:** `moveChapterToPart` = 2 reads + 1 write, not one tx → a concurrent
  part-trash can leave a chapter homed in a now-trashed part. Benign: `groupChaptersByParts` treats a
  chapter pointing at a trashed/unknown act as Unassigned, so no visible corruption. Low-contention.
- **LOW [repo-wide] documented:** the `_ = rows.Scan()` discarded-error pattern remains in
  listChapters/keyset; `title` was the only NULLABLE-into-non-pointer dest today (now fixed via *string),
  so the actual bug is closed, but the footgun persists for any future nullable column added there.
- **LOW [robustness] accept:** `activePartOrder` (reorder undo-hint helper) returns [] on query error →
  a rare error path yields a weak/empty undo hint. Best-effort by design.
- **Standards: COMPLIANT.** Tenancy — parts are book_id-scoped, gated via authBook/mcpRequireGrant, every
  query book-scoped, cross-book move blocked, `UNIQUE(book_id,sort_order)` is correctly scoped (no
  shared-row/`UNIQUE(code)` smell). Language rule (Go domain) ✓. MCP-first agent-parity ✓ (domain tools,
  tier-tag-gate passed). No provider SDK / model literal / secret. FE tools contract N/A (these are
  book-service domain tools, not FE GUI tools).

### Drift / near-misses
- Near-miss ×2: the git INDEX carried ANOTHER session's staged files (knowledge S-05, then S-01 templates
  + frontend-tools.contract.json) at commit time. Caught both via `git diff --cached --name-only`; used
  `git reset -q` + re-add of my exact paths. The "index may carry prestaged unrelated changes" trap is
  LIVE on this shared checkout — always inspect the cached name-list before every commit.
- Near-miss: NULL-title chapters silently zeroed part_id/sort_order in the chapter lists — my part_id
  addition surfaced a pre-existing discarded-Scan bug. Fixed rather than worked-around.
