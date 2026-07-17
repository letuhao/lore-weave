# Derivative Manuscript Fork — BUILD plan (D-S5-DERIVATIVE-MANUSCRIPT-FORK)

> PRODUCT DECISION MADE 2026-07-17: **fork the manuscript** (the user chose §3 over
> keep-spec-branch). This plan turns `docs/specs/2026-07-17-derivative-manuscript-fork.md` §3
> into concrete, committable milestones. Approach = spec's recommended **(b) composition-side
> work-scoped chapter drafts** — keeps the COW/source-clobber guard, avoids a book-service
> schema change touching every reader. Size L. Owner: S5 (this session).

## The model

A dị bản gains its OWN manuscript per chapter, keyed by `(derivative project_id, chapter_id)`,
stored **composition-side**. Chapter-level copy-on-write:
- A derivative chapter with **no** work-scoped row **inherits** canon (read-through to book-service).
- It **forks on first edit** (the first PATCH seeds the row from canon, then applies the edit).
- Canon's `chapter_drafts` row (book-service) is **byte-unchanged** by any derivative edit.
- A **merge-to-canon** path promotes a forked chapter back into canon (grant-gated).

Tenancy: the work-scoped draft is per-book + per-work (the derivative Work's own scope) — same E0
grant model as the Work; no new cross-tenant surface. The canonical Work keeps using the
book-service draft directly (no work-scoping needed for canon).

## Milestones (each = its own commit with evidence)

### M1 · BE — work-scoped chapter-draft store (read-through + fork-on-write + OCC)
- **Table** (`migrate.py`, idempotent `CREATE TABLE IF NOT EXISTS`):
  `work_chapter_draft(project_id UUID, chapter_id UUID, book_id UUID, body JSONB NOT NULL,
   draft_format TEXT NOT NULL DEFAULT 'json', draft_version INT NOT NULL DEFAULT 1,
   created_by UUID, updated_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY(project_id, chapter_id))`.
  Scope key = `project_id` (the derivative Work's own project) — the tenancy boundary.
- **Repo** `WorkChapterDraftsRepo`: `get(project_id, chapter_id)`; `upsert(project_id, chapter_id,
  book_id, body, created_by, expected_version)` with OCC (mismatch → VersionMismatchError, mirrors
  WorksRepo.update); `exists(project_id, chapter_id)`.
- **Routes** (`works.py`, gated on the Work's book):
  - `GET /works/{project_id}/chapters/{chapter_id}/work-draft` — VIEW. If a work row exists, return
    it (`forked: true`). Else read-through to canon (`BookClient.get_draft`) and return it with
    `forked: false, inherited: true` (so the FE knows this chapter hasn't forked yet).
  - `PATCH /works/{project_id}/chapters/{chapter_id}/work-draft` — EDIT. Fork-on-write: if no work
    row, seed from canon (`get_draft`) then apply the edit as version 1; else OCC-bump. **Rejects a
    non-derivative** (a canonical Work must edit the book draft, not a phantom work draft).
- **Tests**: repo (fork-on-write seeds from canon; OCC conflict) + router (read-through inherits;
  first-PATCH forks; canonical rejected; grant deny).

### M2 · BE — merge-to-canon
- **Route** `POST /works/{project_id}/chapters/{chapter_id}/merge-to-canon` — EDIT on the book.
  Read the work-scoped draft → `BookClient.patch_draft(book_id, chapter_id, body,
  expected_draft_version=<canon's current>)` → on success mark the work row `merged_at` (or delete
  it so the chapter re-inherits canon). Anti-clobber: pass the CANON draft_version (a concurrent
  canon edit → 409, surfaced as applied_conflict). Reuse the `approve.py` derivative seam shape.
- **Tests**: merge writes canon + clears the fork; stale canon version → conflict; non-derivative /
  no-fork → 4xx.

### M3 · FE — editor work-scoping (replace the guard with real isolation)
- **api.ts**: `getWorkChapterDraft`, `patchWorkChapterDraft(opts{version})`, `mergeWorkChapterToCanon`.
- **hook** `useWorkChapterDraft(projectId, chapterId, token)` — self-contained (load + save + merge +
  the `forked/inherited` flag).
- **EditorPanel**: when `composeWork?.source_work_id` (on a derivative), read/write the **work-scoped
  draft** instead of `booksApi.getDraft/patchDraft`. Replace the amber `studio-editor-derivative-guard`
  banner with a real state indicator: *"on branch «name» — this chapter is isolated from canon
  (inherited / forked)"* + a **Merge to canon** button (confirm). Canon Work path unchanged.
- **Tests**: EditorPanel routes to the work-draft on a derivative; merge affordance shows; canon Work
  still uses the book draft.

### M4 · VERIFY — live derivative-work smoke + e2e
- **Live** (real stack): on a derivative, edit a chapter + Save → the work-scoped draft holds the
  edit AND canon's `chapter_drafts` body is **byte-unchanged** (the spec's headline acceptance);
  a not-yet-forked chapter reads canon (inherit); switching canon↔derivative shows canon vs the fork;
  Merge-to-canon writes canon.
- **e2e**: extend `s5-blackbox-journey` (or a new `studio-derivative-fork.spec.ts`) — branch → edit on
  the branch → assert isolation → merge.

## Parallel-session safety
- All BE lands in composition-service (my domain); the new table is an **additive idempotent** block
  in migrate.py (no migration-number collision). EditorPanel.tsx is shared — edit only the derivative
  branch of its draft-resolution; commit with explicit pathspec; never `git add -A`.
- The edit-guard banner (v1 mitigation) is **replaced** by M3's real isolation — so
  D-S5-DERIVATIVE-EDIT-GUARD stays cleared (superseded, not regressed).

## Definition of done
All 4 milestones committed with evidence; the live smoke proves canon-byte-unchanged + inherit→fork
+ merge; `s5` e2e green. Then D-S5-DERIVATIVE-MANUSCRIPT-FORK is **CLOSED** and S5 is fully closed
except the 2 consciously-gated MCP writes (create-confirm, switch-cross-service).
