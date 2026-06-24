# Epic (DEFERRED) — Shared `<ChapterListBrowser>` + chapter-list `limit` bug

- **Date:** 2026-06-14 · **Status:** DEFERRED (documented now, build later) — deferred to avoid conflict with a concurrent RAID touching `frontend/src/features/composition/*` + `ChapterEditorPage`. The **chapter-import** upgrade is being done now separately (it's outside RAID's surface and uses a client-side file list, not the server chapter browser).
- **Why:** many modals/screens each roll their own chapter list → fragmented, buggy, and broken at scale (4000+ chapters).

## 🔴 Confirmed bug — `limit > 100` silently returns 20 chapters

`services/book-service/internal/api/server.go:344-358` (`parseLimitOffset`):
```go
limit = 20
if v := r.URL.Query().Get("limit"); v != "" {
    if n, err := strconv.Atoi(v); err == nil && n > 0 && n <= 100 {  // n>100 ⇒ condition false
        limit = n                                                     // ⇒ limit STAYS 20 (no clamp!)
    }
}
```
Any caller passing `limit > 100` does **not** get clamped to 100 — it falls back to the **default 20**. The list endpoint already returns `total`, so pagination is possible; callers just don't use it.

**Affected call sites (all silently capped at 20):**
| Call site | limit passed | gets |
|---|---|---|
| `pages/book-tabs/TranslateModal.tsx:48` | 200 | **20** |
| `pages/book-tabs/TranslationTab.tsx:132` | 200 | **20** |
| `features/extraction/ExtractionWizard.tsx:85` | 500 | **20** |
| `pages/ChapterEditorPage.tsx:307` | 200 | **20** |
| `features/campaigns/.../ChapterRangeStep.tsx:21` | 5000 | **20** (then filters `editorial_status='published'`) |
| `features/enrichment/.../ChapterSelectionPicker.tsx:41` | 100 | 100 ✓ (requests exactly the max — its comment is the correct guidance) |
| `pages/ReaderPage.tsx`, `ChapterTranslationsPage.tsx`, `ContextPicker.tsx`, `useTrashItems.ts` | 100 | 100 ✓ |

**The "translator only shows 20 chapters" report = this bug** (TranslateModal requests 200 → 20). The campaign wizard additionally filters to published, so it shows ≤20 published.

### Quick fix (B0) — safe 1-liner, NOT in RAID's path (book-service)
Change the fallback to a **clamp**:
```go
if v := r.URL.Query().Get("limit"); v != "" {
    if n, err := strconv.Atoi(v); err == nil && n > 0 {
        if n > 100 { n = 100 }
        limit = n
    }
}
```
Immediate relief (consumers see 100 instead of 20). Does NOT solve 4000+ (that needs pagination via the shared component). Cheap + low-risk; can be shipped independently when RAID isn't mid-edit on shared files.

## Shared component plan (B1) — `frontend/src/components/shared/ChapterListBrowser.tsx`

A single paginated chapter browser to replace the fragmented lists.

**Requirements (synthesized from the call sites):**
- **Paging:** page-through (Prev/Next + jump-to-page), one server page (`limit ≤ 100` + `offset`) at a time; header "X–Y of N" from `total`. (PO chose page-through over virtualization.)
- **Selection modes:** `none` (reader TOC) · `single` · `multi` (checkboxes) · `range` (from–to `sort_order`, campaigns) · `select-all-N matching` (loop-fetch ids across pages, like the glossary bulk-activate pattern in `GlossaryTab`).
- **Filters:** `lifecycle_state` (active/trashed) · `editorial_status` (draft/published/all) · text search (title/filename) · `original_language`.
- **Sort:** `sort_order` ASC (backend default).
- **Selection persists across pages** (a `Set<chapter_id>`), not URL.
- Backend already returns `{items, total, limit, offset}` — needs B0 (clamp) so page size 100 works.

**Migration targets (deferred):** TranslateModal, TranslationTab (matrix selection), ExtractionWizard (all/range/pick), ChaptersTab, campaign ChapterRangeStep, ContextPicker (multi-book), Reader TOC. Each currently full-loads (capped at 20/100). Replace with the browser in `multi`/`range`/`none` mode.

**Sequencing when un-deferred:** B0 (clamp) → B1 (component) → migrate TranslateModal + ExtractionWizard + ChaptersTab first (highest pain) → campaign/context/reader.

## Note
The chapter-**import** review screen (built 2026-06-14, separate) lists *client-side parsed files in memory*, not server chapters — a different data source — so it does not reuse this component and does not block this epic.
