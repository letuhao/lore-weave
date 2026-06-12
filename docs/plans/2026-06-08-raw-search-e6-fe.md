# Plan — E6 FE: expose granularity / relevance / K in the raw-search UI

Branch `raw-search/foundation` · **L** · FE-only (no cross-service smoke). MVC: logic in hook, render in components.
PO: **Navigate/Mine** labels · **thin score bar** for relevance · **K dropdown** 10/20/50/100.

## BUILD
1. **types.ts** — `RawSearchHit + relevance?: number`; `RawSearchParams + granularity?: 'chapter'|'block'`.
2. **api.ts** — `lexicalSearch` + `hybridSearch` forward `granularity`; the hybrid→lexical **fallback passes `granularity`** (clears the E5 deferred). (`rerank` stays backend-default-on; no FE toggle.)
3. **hooks/useRawSearch.ts** — `RawSearchGranularity`; opts `+granularity` (default `chapter`); `limit` already an opt; both into `queryKey` + the api calls.
4. **components/RawSearchPanel.tsx** — options row: existing mode toggle + **granularity toggle** (Navigate/Mine, `aria-pressed`, title=hint) + **K `<select>`** (10/20/50/100). State `granularity` (`chapter`) + `limit` (20) → `useRawSearch`.
5. **components/RawSearchResultCard.tsx** — **thin score bar** when `hit.relevance != null` (fill = `relevance*100%`, `title` = `NN%`), right of the snippet header. Reuses surface/matchtype badges.
6. **i18n** en/vi/ja/zh-TW `rawSearch.json` — `+granularity_label, granularity_chapter, granularity_block, granularity_chapter_hint, granularity_block_hint, limit_label, relevance_label`.
7. **tests** (vitest) — granularity toggle → api called with `granularity:'block'`; K select → `limit` flows to api; relevance bar renders with width; defaults (chapter, 20). Existing tests keep passing.

## VERIFY
- `vitest run` (raw-search) green; `tsc --noEmit` clean (via `docker compose build frontend` per the multi-worktree note — host pnpm excluded); i18n key parity across 4 locales.

## REVIEW(code) 2-stage → QC → POST-REVIEW (STOP) → SESSION → COMMIT → RETRO.
Clears D-RAWSEARCH-E6-FE + D-RAWSEARCH-FE-MINOR (score now displayed). Defer: per-hit "reranked" indicator, mobile layout polish.
