# T2-M3 — segment coverage rollup + matrix drill-down + per-segment glossary staleness

Spec: `docs/specs/2026-06-15-translation-panel-overhaul.md`. Final T2 milestone, builds on
M2.1 (`segment_translations` + `compute_segment_status`) and M2.2 (dirty-only re-translate).

## Scope (user chose FULL — A+B+C+D)
- **A — segment coverage rollup (BE).** Per (book, language) per-chapter segment counts
  (total / dirty / translated / stale / needs) for the matrix + drill-down.
- **B — matrix drill-down (FE).** Click a TranslationTab cell → per-segment status list +
  a "Re-translate changed (N)" action calling `retranslate-dirty`.
- **C — `limit:200`→100 consumer fix (FE).** TranslationTab loop-fetches all chapters
  (the B0 clamp now caps a single request at 100).
- **D — per-segment glossary staleness (FS).** A segment is stale when a glossary entity it
  uses changed since it was translated — not just chapter-level `is_glossary_stale`.

## Risk-boundary milestones (commit at each)
### M3.1 — A: segment coverage endpoint
`GET /v1/translation/books/{book_id}/segment-coverage?target_language=` (book VIEW). One
query: book chapters (DISTINCT chapter_id from chapter_translations) ⋈ chapter_segments ⋈
segment_translations(lang). Returns per-chapter `{segment_total, dirty_count, translated_count,
stale_count, needs_count}` (stale_count = 0 until M3.2 lands).

### M3.2 — D: per-segment glossary staleness
- `segment_glossary_usage(chapter_id, target_language, segment_index, entity_id)` — which
  entities each segment's SOURCE references; populated best-effort at translate finalize
  (scan each segment_text against the book's glossary terms, reusing glossary_client).
- `segment_translations += is_glossary_stale BOOLEAN` — reset false on (re)record.
- glossary_consumer: on `entity_updated`, also flag the affected SEGMENTS
  (join segment_glossary_usage by entity, scoped to the book's chapters + language match).
- status/coverage expose `stale`; `needs = dirty OR stale`; retranslate-dirty includes stale
  segments in its block range.

### M3.3 — B + C: FE
- `api.ts`: getSegmentCoverage, getSegmentStatus (M2.1 public), retranslateDirty.
- hook `useSegmentDrilldown`; component (per-segment list + status badges + re-translate-N).
- TranslationTab: cell → drill-down; loop-fetch chapters (C). i18n ×4.

## Tests / smoke
- M3.1: coverage query (real-PG: dirty/total/translated counts) + endpoint (fake_pool + grant).
- M3.2: per-segment usage population, consumer per-segment flag, status/coverage stale, retranslate includes stale.
- M3.3: hook + component vitest; tsc.
- Deferred `D-TRANSL-T2M3-LIVE-SMOKE` (matrix → drill-down → re-translate-changed on the stack).
