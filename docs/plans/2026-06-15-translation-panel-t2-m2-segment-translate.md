# T2-M2 — Per-segment translation status + dirty-only re-translate

Spec: `docs/specs/2026-06-15-translation-panel-overhaul.md` (anchor = `chapter_blocks`/block-range segments).
Builds on T2-M1 (`chapter_segments` + `ensure_chapter_segments`, commit 57206d70).

## Goal
A chapter is a sequence of source-side **segments** (M1). M2 adds, per (chapter, target_language):
1. **Status** — which segments are translated, and whether the source has changed since (dirty).
2. **Dirty-only re-translate** — re-translate ONLY the changed segments, reusing the existing
   translation-job machinery; unchanged segments are copied from the prior LLM version.

## Locked decisions (from CLARIFY)
- Re-translate runs through the **existing job machinery** (`_resolve_and_create_job` → worker →
  LLMClient / glossary / billing / circuit-breaker), NOT a parallel LLM setup. The job carries a
  `block_index_filter` (the dirty blocks) + `seed_version_id` (prior LLM version to copy unchanged
  blocks from). The worker translates only the filtered blocks, overlays them onto the seed body,
  and finalizes a NORMAL new LLM version.
- **LLM never overwrites a human version.** No special handling needed: the existing
  `_PROMOTE_ACTIVE_SQL` human-guard already skips auto-promote when the active version is
  `authored_by='human'`. The re-translate produces an `llm` version; if the active is human, it
  stays the published one (the human can adopt via the T1 AC4 banner / version switcher).
- **Dirty signal** = `chapter_segments.source_content_hash` (current) ≠
  `segment_translations.source_content_hash` (recorded at translate time), or no row.

## Risk-boundary milestones (commit at each)

### M2.1 — status foundation (observability; no pipeline change)
- **Migration** (`migrate.py`): `segment_translations` table
  `(id, chapter_id, target_language, segment_index, source_content_hash, chapter_translation_id,
    translated_at, created_at, updated_at, UNIQUE(chapter_id, target_language, segment_index))`
  + idx on `(chapter_id, target_language)`.
- **`workers/segment_status.py`** (new):
  - `record_segment_translations(conn, chapter_id, target_language, chapter_translation_id)` —
    a full-chapter translation just covered EVERY segment at its current source hash → upsert all
    segment rows from `chapter_segments`.
  - `compute_segment_status(conn, chapter_id, target_language)` — LEFT JOIN current segments to
    recorded; returns per-segment `{segment_index, start/end_block_index, current_hash,
    translated_hash, translated_at, dirty}`.
- **Finalize hook** (`chapter_worker._finalize_chapter`): on a non-duplicate completion, best-effort
  post-commit, `ensure_chapter_segments(...)` then `record_segment_translations(...)`. Non-fatal
  (mirrors the memo/quality emits) — a status bookkeeping failure must never break a translation.
- **Read endpoints**: internal `GET /internal/translation/chapters/{chapter_id}/segments/status`
  + public `GET /v1/translation/chapters/{chapter_id}/segments/status` (book VIEW grant) for the
  M3 FE matrix drill-down.

### M2.2 — dirty-only re-translate (the deep change)
- `CreateJobPayload` + `translation_jobs` + per-chapter message gain optional
  `block_index_filter: list[int]` + `seed_version_id: UUID`.
- New public endpoint `POST /v1/translation/chapters/{chapter_id}/retranslate-dirty`
  (body: target_language) — computes dirty segments, collects their block indices, resolves the
  seed = latest `llm` version, enqueues ONE chapter job with the filter + seed.
- Worker block path (`_process_chapter`): when `block_index_filter` present, translate only those
  blocks; build the new body by copying the seed version's blocks for unchanged indices and
  overlaying the freshly-translated dirty blocks. Finalize normally (existing promote/human-guard).
  Restrict to the synchronous v2 block path for this job kind (skip decouple/v3 branching) to bound
  the blast radius; record dirty segments fresh on finalize (M2.1 hook already does all segments).

## Tests
- M2.1: pure status/record SQL-shape (fake_pool) + a real-PG record→dirty→re-record cycle
  (mirrors `test_promote_active_pg.py`); finalize-hook wiring (best-effort, non-fatal on raise).
- M2.2: endpoint computes dirty filter + seed; worker overlay (unchanged copied, dirty replaced);
  human-active not clobbered (promote-guard regression).

## Deferred / live-smoke
- D-TRANSL-T2M2-LIVE-SMOKE — real stack: edit a chapter block → rebuild segments → status shows
  dirty → retranslate-dirty → only dirty segment re-translated + new version promoted.
- M3 (next cycle): coverage rollup + FE matrix drill-down + glossary-staleness per-segment.
