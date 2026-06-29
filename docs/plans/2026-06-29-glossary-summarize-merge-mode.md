# Plan — Glossary `summarize` (merge-rewrite) merge mode (bugs #26 / #7)

**Date:** 2026-06-29 · **Branch:** `fix/critical-ux-bugs` · **Size:** L (new merge action +
migration + 2 glossary internal endpoints + a decoupled end-of-job LLM pass + FE).

## Problem (verified in code)

A character's descriptive attributes change slightly each chapter. The three existing merge
actions ([extraction_handler.go:1438](../../services/glossary-service/internal/api/extraction_handler.go#L1438))
all fail this case:
- `fill_if_empty` → writes chapter 1, then **frozen** (never grows).
- `overwrite` → keeps only the **latest** chapter (earlier detail **lost**).
- `append` → accumulates every raw phrasing as a child item, deduped only by **exact normalized
  text**, so paraphrases ("a warrior" / "a skilled warrior" / "a powerful swordsman") pile up as
  near-duplicate bloat. (The user's exact complaint.)

No mode synthesizes the accumulated raw mentions into one clean canonical description.

## Decision (user, 2026-06-29)

A **new mode**, distinct from append. Two locked choices:
- **Trigger:** end-of-extraction-job, **batched** (one re-summarize pass per touched entity per
  job, regardless of chapter count) + a manual "Re-summarize" button (M3, follow-up).
- **Storage/UI:** **keep both** — raw items stay as lossless provenance; a NEW `canonical_value`
  is the synthesized headline; raw collapses under "sources / history".

## Design — lossless RAW layer + synthesized CANONICAL layer

```
extraction writeback (synchronous, NO LLM — stays fast for 100-entity batches)
  └─ action "summarize":
       1. append incoming items to the RAW layer   ← identical to the append branch today
                                                       (per-item rows, chapter provenance, idempotent)
       2. if the raw set changed → set canonical_dirty=true on the EAV

end-of-extraction-job, in the SAME worker (reuses its llm_client + model_ref — NO new queue)
  └─ resummarize pass:
       3. GET dirty work items from glossary (entity_id, attr_code, label, raw_values[], lang)
       4. ONE LLM rewrite per (entity, attr) via provider-registry   ← model from the job, never hardcoded
          "merge these raw mentions into one deduped canonical {label}, in {source_language}"
       5. POST canonical_value back → glossary stores it, clears dirty, stamps synced_at

FE: headline = canonical_value; raw items under "sources / history"; manual "Re-summarize" (M3)
```

Why this shape:
- **Lossless** — raw provenance never destroyed (unlike overwrite); re-synthesizable + auditable.
- **No LLM in the writeback tx** — extraction writeback stays deterministic + fast.
- **Provider invariant** — the rewrite goes through `provider-registry` from the Python worker;
  model resolved from the job message, never a literal. `usage_purpose="glossary_resummarize"`.
- **Lowest surface** — the LLM pass runs inline at job-end in the EXISTING extraction worker
  ([extraction_worker.py:623](../../services/translation-service/app/workers/extraction_worker.py#L623)),
  which already holds `llm_client`/`model_source`/`model_ref`. No new queue/consumer.
- **Source-language summaries** — keep the canonical text in the source language
  ([[reference]] bug #10: KG/summary stay in source language, not English).

## Milestones

### M1 — schema + writeback (glossary-service, Go)  ·  risk boundary: migration
- Migration `0043_canonical_summary`: `ALTER TABLE entity_attribute_values ADD COLUMN
  canonical_value TEXT, canonical_dirty BOOLEAN NOT NULL DEFAULT false, canonical_synced_at
  TIMESTAMPTZ`. Idempotent (IF NOT EXISTS).
- `strategyToAction("summarize") → "summarize"`; `seedMergeStrategy` leaves identity/tags alone
  (summarize is opt-in per attribute, never auto-seeded onto name/term).
- `mergeExtractedEntity`: new `else if action == "summarize"` branch — runs the **same append
  logic** (refactor the append body into `appendRawItems(...)` so both branches share it), then
  on a real change sets `canonical_dirty=true` (same tx). Counts as `written`.
- Tests: summarize appends raw like append + sets dirty; no-op re-append leaves dirty unchanged;
  verified-clobber + manual guards still win over summarize.

### M2 — dirty-fetch + canonical-writeback endpoints + end-of-job LLM pass
- glossary internal endpoints (book-scoped, `X-Internal-Token`):
  - `GET  /internal/books/{book_id}/canonical-dirty` → `[{entity_id, attr_code, attr_label,
    raw_values[], source_language}]` (only `canonical_dirty=true` summarize attrs).
  - `POST /internal/books/{book_id}/entities/{entity_id}/canonical` `{attr_code, canonical_value}`
    → store `canonical_value`, `canonical_dirty=false`, `canonical_synced_at=now()`. Emits the
    existing `glossary.entity_updated` (pipeline actor) so KG anchor + staleness refresh.
- translation-service `resummarize.py`: after `_run_extraction_job` reaches a non-cancelled
  terminal status, fetch dirty → per item, build a rewrite prompt → `llm_client.submit_and_wait`
  (`usage_purpose="glossary_resummarize"`, same model_source/model_ref) → POST canonical back.
  **Best-effort** — a resummarize failure is logged, NEVER fails the extraction job (it already
  committed). Bounded fan-out (reuse the extraction concurrency cap).
- Tests: dirty-fetch returns only dirty summarize attrs; writeback clears dirty + stamps;
  resummarize pass posts canonical for a stubbed LLM; an LLM error doesn't raise.
- VERIFY: cross-service live smoke (translation worker ↔ glossary) — drive a real 2-chapter
  summarize extraction, confirm canonical_value lands.

### M3 — FE: canonical display + manual "Re-summarize" button  (follow-up)
- Entity editor: render `canonical_value` as the headline for summarize attrs; raw items under a
  "sources / history" disclosure.
- Manual "Re-summarize" button → a single-entity resummarize trigger (a tiny job message on the
  existing queue, scoped to one entity; reuses the M2 pass). Defer if it grows past S.

## Security / invariants (must hold)
- **Tenancy:** the new column is on the per-book EAV; every query stays book-scoped. No shared row.
- **Provider gateway:** LLM only via provider-registry (worker `llm_client`), model from the job.
- **No hardcoded model:** the rewrite uses the job's resolved `model_ref`.
- **Verified-clobber (INV-8):** a human-verified value still supersedes summarize (skip 'verified').
- **Internal auth:** the two new endpoints require `X-Internal-Token` (mirror extract-entities).

## Out of scope (tracked)
- Vector/semantic dedup of raw items (string-exact dedup stays; the LLM rewrite handles paraphrase
  collapse) → fine as-is.
- Back-summarizing existing append-mode attrs (only new summarize-tagged attrs synthesize) →
  D-GLOSSARY-SUMMARIZE-BACKFILL if wanted.
