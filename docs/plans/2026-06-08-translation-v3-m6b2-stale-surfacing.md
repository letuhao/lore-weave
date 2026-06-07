# M6b-2 — book-level stale surfacing + user-triggered re-translate [FS]

**Date:** 2026-06-08 · **Branch:** `feat/translation-pipeline-v3` · **Size:** L · **Mode:** v2.2 + `/review-impl`
**Follows:** M6b-1 (per-chapter `is_glossary_stale`). Closes the M6 "targeted re-translate + propagate" remainder (the user-consent half).

## PO decisions (CLARIFY 2026-06-08)
1. **Select affected → existing `TranslateModal`** (consent-first; no new write path, no auto-spend).
2. **Active version's staleness** per cell (fallback latest) — matches what the reader sees.

## Steps
1. **BE `models.py`** — `CoverageCell + is_glossary_stale: bool` (default False).
2. **BE `coverage.py`** — `COALESCE((active version's is_glossary_stale), (latest version's))` subselect → cell.
3. **BE `test_coverage.py`** — assert a stale active version surfaces `is_glossary_stale=true` in the cell; clean version stays false.
4. **FE `api.ts`** — `CoverageCell + is_glossary_stale: boolean`.
5. **FE `TranslationTab.tsx`** —
   - pure `staleChapterIds(coverage, visibleLangs)` → `{ ids: Set<string>, count }` (exported, unit-tested).
   - per-cell stale marker (sky `History` icon, matching M5c-2's viewer badge).
   - legend stale count (`matrix.legend_stale`).
   - "Select affected" button (shown when count > 0) → `setSelectedChapters(staleIds)` → existing FloatingActionBar → TranslateModal.
6. **FE i18n** — `matrix.legend_stale`, `matrix.select_affected`, `matrix.cell_stale_title` × en/vi/ja/zh-TW.
7. **FE vitest** — `staleChapterIds` over a coverage fixture (stale-in-visible-lang counted; filtered-out lang ignored; no-stale → empty).

## Parity / safety
Additive coverage field (rolling-safe; old FE ignores it, new FE defaults false on legacy rows). Re-translate reuses the proven job-creation flow → no new side effects.

## Deferred (anticipated)
- **D-TRANSL-M6B2-PERLANG-JOB** — "Select affected" selects chapters across visible langs; the per-language precision of *which* language to re-translate is the user's choice in the modal. A per-language one-click ("re-translate vi: N") is a later refinement.
