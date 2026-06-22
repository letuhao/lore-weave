# Plan — Extraction MERGE policy (M5 / P4): verified-clobber + skip-reason + merge_strategy

**Status:** PLAN. Branch `feat/extraction-knowledge-architecture`. Lane MERGE, the last hot-file
(`extraction_handler.go`) work — sequence FND✅ → PROV✅ → **MERGE** (never concurrent on the file).
Design refs: architecture rev 2 §8.6 (merge integrity), detailed-design §2.5 (merge_strategy DDL),
§4 INV-8 (verified-clobber supersedes merge_strategy).

## The gaps (architecture §8.6 / threats T2, F-append, C6)
1. **No verified-clobber guard (T2 / INV-8).** `mergeExtractedEntity` with `action='overwrite'`
   blindly overwrites a SOURCE attribute value even if a human authored it. Source
   `entity_attribute_values` has **no per-value trust marker** today (only `attribute_translations`
   has `confidence`, and extraction already respects `confidence <> 'verified'` there). So a
   re-extraction silently clobbers human-curated source values.
2. **Silent skips (F-append).** `fill` on an occupied value is skipped with NO reason; the caller
   can't tell "already had a value" from "verified" from "tombstoned" from "no action".
3. **No `append` (C6).** List attributes (aliases, members…) can only be filled/overwritten, never
   appended — a re-extraction either skips or clobbers the list instead of dedup-merging new items.
4. **`merge_strategy` not authored.** The per-extraction directive comes from the runtime extraction
   profile (`fill`/`overwrite`/`skip`); the ontology has no authored default (§2.5).

## Slices

### Slice 1 — verified-clobber integrity + skip-reason taxonomy (THIS run)
The integrity core; closes INV-8 / T2 end-to-end with a real producer so the guard protects data.

- **Migration** (glossary chain `0034_merge_policy`):
  - `ALTER entity_attribute_values ADD confidence TEXT NOT NULL DEFAULT 'machine'` — the per-source-
    value trust marker (`machine` | `draft` | `verified`). Backfill stays `machine` (extraction-written).
  - `ALTER system_attributes / user_attributes / book_attributes ADD merge_strategy TEXT NOT NULL
    (post-G4 live tiered tables; the design's `system_kind_attributes` is the dropped legacy name)
    DEFAULT 'fill_if_empty'` (§2.5; values `replace|fill_if_empty|append|overwrite|manual`). Provisioned
    now (System-tier safe default, admin-only writes), consumed in Slice 2.
- **Producer** (the editor marks human edits): the user-facing source-value writes —
  `attribute_handler.go` PATCH (`original_value = …`) and `apply_edit_handler.go` apply — set
  `confidence = 'verified'` (a human authored this value). Machine extraction writes `confidence='machine'`.
- **Guard** (`mergeExtractedEntity`, the hot file): before a `fill`/`overwrite` write, read the existing
  value's `confidence`; if `verified`, SKIP with reason `verified` (the verified-clobber guard
  supersedes the action — INV-8). A machine write sets `confidence='machine'` explicitly.
- **Skip-reason taxonomy:** replace bare `skippedAttrs []string` with `(code, reason)` pairs surfaced
  on the entity result. Reasons: `no_action` (action empty/skip), `fill_occupied` (fill, value present),
  `verified` (verified-clobber guard), `tombstoned` (reserved for Slice 2 append). Backward-compatible
  JSON (additive field).
- **Tests:** verified source value is NOT overwritten (skip-reason `verified`); a machine value IS
  overwritten; fill-occupied → `fill_occupied`; editor PATCH sets `confidence='verified'`; the new
  columns exist + default correctly. Live on real PG.

### Slice 2 — append + merge_strategy-from-ontology (TRACKED, next)
- `D-MERGE-APPEND` — `append` action: atomic server-side JSON-array dedup-merge for list attributes,
  idempotent by normalized value, under the row lock; tombstone-checked (an `ai-rejected` item never
  re-appends). Interim JSON-array (multi-row = `D-GLOSSARY-MULTIROW-ATTR-VALUES`).
- `D-MERGE-STRATEGY-ONTOLOGY` — resolve the authored `merge_strategy` default from the attribute
  definition (tier-merged System→user→book) when the extraction profile doesn't override; the
  trust-tier × merge-strategy matrix (§8.6).

## Invariants honored
INV-8 (verified-clobber supersedes strategy, checked at write time), INV-6/tenancy (writes stay inside
the per-book writeback tx + grant gate — unchanged), INV-C (the merge runs inside the M1 whole-chapter
transaction; all writes hard-fail, never warn-and-poison). System-tier `merge_strategy` admin-only.

## Size
L (migration + cross-file producer + hot-file guard + taxonomy). Own plan (this doc). Build Slice 1 as
one cohesive run; Slice 2 deferred + tracked.
