# Chapter Revision Compare (1-vs-1 diff) — spec + plan

**Task:** standalone diff page comparing TWO chapter revisions. **Size:** XL [FS]. **Workflow:** v2.2.
**Not LOOM-scoped** — general book-editor feature on book-service's existing `chapter_revisions`.

## PO decisions (CLARIFY, 2026-06-04)
1. Compare target = **two chapter revisions** of the same chapter.
2. Placement = **standalone route** `/books/:bookId/chapters/:chapterId/compare`.
3. Backend = **add a compare endpoint + server-computed diff** (Go LCS line-diff).
4. Diff UI = **both side-by-side (word-level) AND inline unified (git-style), with a toggle**.

## Audit verdict (verify-vs-real-code)
- `GET /v1/.../revisions` (`listRevisions`, JWT) — metadata only (no body). `server.go:1724`.
- `GET /v1/.../revisions/{rid}` (`getRevision`, JWT) — full TipTap `body` + `text_content` projection
  (`jsonb_path_query(body,'$.content[*]._text')` agg with `\n\n`). `server.go:1775`.
- Body = TipTap JSON; **no server-side HTML render** (FE renders). text_content = plain-text projection.
- FE already wires `booksApi.listRevisions/getRevision/restoreRevision`; has `PromptDiff.tsx` (git-style
  line-diff renderer, reusable), `RevisionHistory.tsx`, `SplitCompareView.tsx` (layout ref).
- Compare endpoint is **additive** — no change to existing revision routes.

## Backend (book-service, Go)
1. NEW `internal/textdiff/textdiff.go` — pure LCS line-diff:
   `Lines(a, b string) []Line` where `Line{Op: "equal"|"insert"|"delete", Text string}`.
   Split on `\n`; classic DP-LCS + backtrack. **Perf guard:** if `len(aLines)*len(bLines)` exceeds a cap
   (~4M cells), fall back to delete-all-a + insert-all-b (avoids O(n·m) blowup on huge chapters) and the
   response flags `truncated:true`. Pure → comprehensive unit tests.
2. `internal/api/server.go`:
   - route `r.Get("/revisions/compare", s.compareRevisions)` registered **before** `/revisions/{revision_id}`
     (chi static-beats-param, but order + a routing test make it explicit).
   - `compareRevisions(w,r)`: requireUserID→401; parse book_id/chapter_id→400; `left`/`right` query UUIDs→400
     `COMPARE_BAD_PARAM` (missing/invalid); fetch each via a shared `revisionForCompare` helper (the
     getRevision SQL + text_content projection, ownership join)→404 `REVISION_NOT_FOUND` if either missing;
     `diff := textdiff.Lines(leftText, rightText)`; 200 `{left, right, diff, truncated}`.
     Each side = `{revision_id, created_at, message, body, body_format, text_content}`.
3. Contract: if `contracts/api/book*/openapi*.yaml` exists, add the compare path (additive).

## Frontend
4. `features/books/api.ts` — `compareRevisions(bookId, chapterId, left, right, token)`.
5. `features/books/types.ts` (or local) — `RevisionSide`, `RevisionCompare = {left, right, diff, truncated}`,
   `DiffLine = {op, text}`.
6. Router config — add `/books/:bookId/chapters/:chapterId/compare` → `ChapterComparePage` (lazy).
7. `features/books/components/RevisionCompareView.tsx` (logic-light view) + hook
   `features/books/hooks/useRevisionCompare.ts` (controller: listRevisions for the pickers + compare query).
   - two revision `<select>` pickers (left/right) from `listRevisions`.
   - view-mode toggle `side-by-side` | `inline`.
   - `RevisionDiff.tsx` — renders from the server line-diff:
     - **inline**: single column, equal/insert(+green)/delete(−red) — git-style.
     - **side-by-side**: two columns; equal lines aligned; changed runs show deletes left / inserts right;
       **word-level** highlight within paired delete/insert lines via a small FE `wordDiff` util (presentation
       refinement; the server diff stays line-level).
8. i18n — new keys (en populated; vi/ja/zh-TW follow). Reuse the editor ns or a `compare` ns.
9. Entry point — a "Compare" affordance from `RevisionHistory` (or the chapter editor) linking to the route.

## Test plan
- **Go unit** (`internal/textdiff/textdiff_test.go`): identical→all-equal; a empty→all-insert; b empty→all-delete;
  common prefix+changed middle+common suffix; full replace; trailing-newline; perf-guard truncation.
- **Go handler unit** (`internal/api/*_test.go`): `&Server{secret}` + minted JWT — 401 no-token; 400 missing
  `left`/`right`; 400 invalid-UUID. (DB paths → live smoke; mirrors book-service's no-DB handler-test style.)
- **Go routing test**: `/revisions/compare` resolves to compareRevisions, NOT getRevision(revision_id="compare").
- **FE unit**: `useRevisionCompare` (compare query enabled only when both picked); `RevisionDiff` renders inline
  (insert/delete classes) + side-by-side (word-level highlight on a changed line); api method shape.
- **VERIFY (cross-service live smoke):** create a chapter, save 2 distinct revisions, `GET …/revisions/compare?left=&right=`
  through the gateway (JWT) → 200 with correct diff ops; cross-book revision → 404; `left==right` → all-equal diff.

## Out of scope (V1 / deferred)
- Structural TipTap-tree diff (V0 diffs `text_content` plain-text; rich formatted-HTML diff is a follow-up).
- 3-way / merge. Diffing the rendered HTML DOM. Per-character diff (word-level is the floor).
