# D-GLOSSARY-MULTIROW-ATTR-VALUES — per-item provenance for list attributes (DETAIL DESIGN)

Status: **DETAIL DESIGN — ready to build (sliced)** · 2026-06-22 · branch `feat/extraction-knowledge-architecture`
Origin: pre-existing glossary-schema deferral (NOT extraction-created); user asked to build it on this branch.

## Problem

A list-valued glossary attribute (aliases, tags, …) is today stored as a **JSON array inside the
single `entity_attribute_values.original_value` TEXT cell**. Consequences:

- **`confidence` is row-level** — the whole list shares one trust marker. A human-verified alias
  and a machine-guessed one can't be told apart; the verified-clobber guard (INV-8) is all-or-nothing.
- **Tombstones are entity-level** (`ai-rejected` tag), not per-item — you can't reject ONE alias
  while keeping the rest.
- **No per-item provenance** — which chapter/extraction produced a given list element is lost.

The fix: a child table holding one row per list element with its own `confidence`, `status`
(active|tombstoned), and `source_chapter_id`; `original_value` becomes a **write-synced
denormalized cache** of the ACTIVE items so the ~15 existing readers keep working unchanged.

## Current shape (grounded)

- `entity_attribute_values` (EAV): PK `attr_value_id uuid uuidv7()`, `UNIQUE(entity_id, attr_def_id)`,
  cols incl. `original_value TEXT NOT NULL DEFAULT ''` and `confidence TEXT NOT NULL DEFAULT 'machine'`
  (0034). A snapshot trigger `trig_eav_snapshot` fires on any EAV INSERT/UPDATE/DELETE and re-serializes
  `original_value` into the entity snapshot JSONB.
- List handling lives in [extraction_handler.go](../../services/glossary-service/internal/api/extraction_handler.go):
  `serializeValue` (→ JSON array string), `parseListValue` (string → []string), `appendDedupMerge`
  (JSON-array dedup by `normalizeEntity`), `normalizeEntity` (NFC+trim+collapse+lower).
- **Writers of the list value:** extraction `createExtractedEntity`/`mergeExtractedEntity`
  (fill/overwrite/append), editor `attribute_handler.go` PATCH (+`confidence='verified'`),
  `apply_edit_handler.go` (+verified), `entity_revisions_handler.go` restore (+verified),
  `merge_handler.go` aliases-union.
- **Readers of `original_value` (must keep working):** RAG `export_handler.go`, FE
  `resolveDisplayValue.ts`, extraction dedup/profile, `wiki_handler.go` (×several), translation
  `glossary_translate_prompt.py`, the snapshot trigger, `select_for_context`, enrichment, MCP
  `pipeline_read_tools.go`.

## Design

### New table `entity_attribute_value_items` (migration 0035, additive)
```
item_id          uuid PRIMARY KEY DEFAULT uuidv7()
attr_value_id    uuid NOT NULL REFERENCES entity_attribute_values(attr_value_id) ON DELETE CASCADE
item_value       text NOT NULL              -- display element (original form, NFC-normalized for storage)
item_norm        text NOT NULL              -- normalizeEntity(item_value) — dedup key
sort_order       int  NOT NULL DEFAULT 0
confidence       text NOT NULL DEFAULT 'machine'   -- machine|draft|verified (per ITEM now)
status           text NOT NULL DEFAULT 'active'    -- active|tombstoned
source_chapter_id uuid NULL                  -- provenance (the chapter that produced it)
created_at       timestamptz NOT NULL DEFAULT now()
updated_at       timestamptz NOT NULL DEFAULT now()
UNIQUE (attr_value_id, item_norm)            -- per-item idempotent dedup
INDEX (attr_value_id)
```
- **Tenancy:** the table inherits scope transitively via `attr_value_id → entity_id → glossary_entities`
  (owner/book). No new scope key needed; the FK ON DELETE CASCADE keeps it consistent with entity delete.
- **Scalars carry ZERO items** — a non-list attribute keeps `original_value` as the sole authority.
  The child table only materializes when the value is a JSON array (`parseListValue` sees `[`).

### `original_value` = write-synced cache of the ACTIVE list
- **`rebuildItemsCache(ctx, q, attr_value_id)`** — the SINGLE source of truth for the sync:
  `SELECT item_value FROM …_items WHERE attr_value_id=$1 AND status='active' ORDER BY sort_order, item_norm`
  → `json.Marshal` → `UPDATE entity_attribute_values SET original_value=$cache`. Called after EVERY
  item mutation, inside the same writeback tx (so the cache never diverges within a committed tx).
- Because the cache holds only `active` items, **tombstoning an item drops it from the cache → every
  reader excludes it for free** (readers stay on `original_value`). The product win (per-item reject)
  needs no reader change.

### Migration 0035 backfill (Go — reuse `parseListValue`/`normalizeEntity`)
SQL can't reproduce NFC + collapse + lowercase, so backfill is a Go pass routed through `execGuarded`:
for each EAV whose `original_value` parses as a **multi-element JSON array**, INSERT one item per
element (`item_value`=element, `item_norm`=normalizeEntity, `sort_order`=index, `confidence`=the EAV's
row `confidence`, `status='active'`). Scalars / single non-array values → zero items (the cache stays
authoritative). Idempotent via `ON CONFLICT (attr_value_id, item_norm) DO NOTHING` so a re-run is safe.
After backfill the cache already equals the active-item projection (no rewrite of `original_value`).

### Writeback cutover (writers-first; readers untouched)
- **Append** (`mergeExtractedEntity` action=`append`) → per-item INSERT:
  for each incoming element, `INSERT … (attr_value_id,item_value,item_norm,confidence,status,source_chapter_id,sort_order)
  VALUES (…,'machine','active',…, next) ON CONFLICT (attr_value_id, item_norm) DO NOTHING`; if 0 rows
  inserted → skip-reason `unchanged` (idempotent, same contract as today); else `rebuildItemsCache`.
  Replaces the `appendDedupMerge` string-merge. Runs under the existing per-book writeback lock.
- **Overwrite / fill / merge-aliases / editor PATCH / apply-edit / restore** → replace the item set:
  delete-or-tombstone the prior items, INSERT the new set (editor/apply-edit/restore stamp
  `confidence='verified'` PER ITEM), `rebuildItemsCache`. The **verified-clobber guard becomes
  per-item**: a machine overwrite skips items whose existing row is `confidence='verified'`.
- **Per-item verify/tombstone**: new internal endpoints (`POST …/attribute-items/{id}/verify`,
  `…/tombstone`) flip a single item's `confidence`/`status` + `rebuildItemsCache`.

## Slices (each its own VERIFY + /review-impl + commit)

1. **Slice 1 — additive core (safe, reversible).** Migration 0035 (child table + indexes) + Go
   backfill + `rebuildItemsCache` + rewire the **append** path to the item model. `original_value`
   stays byte-compatible for every reader. This is the load-bearing migration risk boundary.
2. **Slice 2 — the replace-writers + per-item guard.** Overwrite/fill/merge-aliases/editor/apply-edit/
   restore sync the item set; verified-clobber + tombstone become per-item; merge-entity unions items.
3. **Slice 3 — per-item verify/tombstone endpoints** (+ MCP/REST surface for "reject this one alias").
   Readers need nothing (cache already excludes tombstoned) unless a surface wants to SHOW provenance.

## Invariants
- **INV-MR1 cache parity:** after any committed writeback, `original_value` == JSON array of active
  items ordered by `(sort_order, item_norm)` (or the untouched scalar when zero items). `rebuildItemsCache`
  is the only writer of the list cache.
- **INV-MR2 idempotent items:** `UNIQUE(attr_value_id, item_norm)` + `ON CONFLICT DO NOTHING` → a
  re-append is a no-op (preserves the `unchanged` skip contract).
- **INV-MR3 per-item verified-clobber:** a machine write never overwrites/tombstones an item whose
  row is `confidence='verified'` (the per-item lift of INV-8/T2).
- **INV-MR4 tenancy:** items reach scope only through `attr_value_id`; every item query joins/filters
  through the owning entity; no global item access.

## Risks
- **Cache divergence** → single `rebuildItemsCache` helper; consider a trigger backstop only if a
  writer is ever missed (slice 2 audits all writers).
- **Normalize parity** → reuse `normalizeEntity` everywhere (already the shared dedup fn).
- **Online cutover ordering** → writers-first; readers stay on the cache the whole time, so there is
  no flag-day. Backfill is idempotent + additive (old code keeps writing `original_value`; new append
  code writes items + rebuilds the same cache).
- **Scalar vs list branching** → the array-prefix heuristic (`parseListValue`) decides; a scalar never
  gets items, so the verified-guard scalar path (0034 row-level `confidence`) is unchanged.
