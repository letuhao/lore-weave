# Spec — D-GLOSSARY-ST-DEDUP: multi-language entity-name dedup in glossary-service

**Date:** 2026-06-26 · **Status:** ✅ SHIPPED + LIVE-APPLIED (M1–M4; 63 S/T dup groups merged on 万古神帝, cross-service KG sync verified) · **Size:** XL (files≈14, logic≈11, side-effects≈4: DB migration + schema + new SDK module + cross-language table)

> Sibling of the shipped **D-KG-TL-SIMPLIFIED-TRADITIONAL-DUP** (knowledge-service / Neo4j). That fix folded entity names in the **Python** SDK (`loreweave_extraction.name_normalize`) and wiped the disposable KG. This applies the **same equivalence fold** to **glossary-service** (Go / Postgres), which holds **real user-authored data** — so NO wipe; a journaled dedup-merge migration instead.

## Problem

Glossary entity dedup normalizes names with `textnorm.Normalize` = **NFC + trim + collapse-ws + `ToLower`** ([textnorm.go:20](../../services/glossary-service/internal/textnorm/textnorm.go#L20)). It lacks **NFKC** (full-width not folded), **Unicode casefold** (ß etc.), and the **CJK traditional→simplified** fold. So 張若塵 and 张若尘 dedup to different keys → two entities for one character (confirmed live by the KG-TL participant-anchor smoke: 张若尘 and 張若塵 anchored to two different glossary entities, only one carrying the vi translation).

## How glossary dedup actually works (verified in code)

Three points; **the Go normalizer is the primary dedup, the DB column is only the race backstop**:

1. **App resolver (PRIMARY)** — `findEntityByNameOrAlias` ([extraction_handler.go:1166](../../services/glossary-service/internal/api/extraction_handler.go#L1166)) loads candidate (book,kind) name/alias rows and compares **in Go**: `normalizeEntity(e.name) == normalizeEntity(incoming)`. A per-book advisory lock serializes resolver→insert. This is where future dupes are actually prevented.
2. **DB dedup key (BACKSTOP)** — `glossary_entities.normalized_name`, a `GENERATED ALWAYS … STORED` column = `lower(btrim(regexp_replace(normalize(coalesce(cached_name,''),NFC),'\s+',' ','g')))`, with partial unique index `uq_entity_dedup(book_id, kind_id, normalized_name) WHERE deleted_at IS NULL AND normalized_name<>''` ([extraction_concurrency.go:48](../../services/glossary-service/internal/migrate/extraction_concurrency.go#L48)). `cached_name` is itself derived from the `name` EAV value by the `recalculate_entity_snapshot` plpgsql trigger ([migrate.go:1083](../../services/glossary-service/internal/migrate/migrate.go#L1083)). The unique index fires on the **trigger's UPDATE of cached_name** (after the name EAV lands), not on the entity INSERT.
3. **Merge primitive (EXISTS, robust)** — `mergeEntitiesCore`/`mergeOne` ([merge_handler.go:150](../../services/glossary-service/internal/api/merge_handler.go#L150)): per-loser tx, soft-deletes loser, repoints chapter_entity_links / entity_attribute_values / entity_enrichments / extraction_audit_log / wiki_articles, folds loser name+aliases into winner aliases (anti-resurrection), journals for revert, emits the `merged` outbox event that already drives KG `merge_entities` + alias-map K-sync. Same-book + same-kind gated.

## Decisions (locked)

- **DB strategy = app-maintained plain column** (user pick). Drop the `GENERATED` derivation; `normalized_name` becomes a plain column the **app writes via the Go SDK**. The SDK is the **single source of truth** for the fold — no SQL re-implementation of casefold/Han (which Postgres lacks natively), no third copy of the table. Justified because the Go resolver is already the primary dedup and self-consistent; the DB column only needs to agree well enough to backstop races, and app-writing it with the same SDK call the resolver uses makes them *identical by construction*.
- **Go SDK kit** = `sdks/go/loreweave_extraction` mirroring the Python `name_normalize`, alongside the existing kits (grantclient, llmgw, loreweave_llm, loreweave_mcp, metaoutbox, metapg, piikms).
- **Table parity by codegen, not hand-copy.** SoT = the frozen Python `T2S` dict (`_han_simplified_table.py`). A generator emits the Go `t2s_table.go` from it; a Go parity test asserts the two are identical so they can never silently drift.
- **No wipe — journaled dedup-merge migration**, dry-run first. Real user data + the unique-index rebuild *fails loudly* on existing S/T collisions, so resolving them is forced, not optional.

## Build plan (checkpoint at each risk boundary)

### M1 — Go SDK `loreweave_extraction` (PURE, no data) + table codegen
- New module `sdks/go/loreweave_extraction/` (own `go.mod`, like sibling kits):
  - `namenorm.go`: `NfkcCasefold(s) string` (`golang.org/x/text/unicode/norm` NFKC + `golang.org/x/text/cases` casefold), `HasHan(s) bool`, `FoldHanSimplified(s) string` (gated), `NormalizeEntityName(s) string` = `FoldHanSimplified(NfkcCasefold(s))`. Byte-for-byte mirror of [name_normalize.py](../../sdks/python/loreweave_extraction/name_normalize.py).
  - `t2s_table.go`: generated `var T2S = map[rune]rune{…}` from the Python SoT.
  - `gen/` generator (reads the Python table, emits `t2s_table.go`) + `go:generate` directive.
- Tests: the Python Phase-1 test vectors ported to Go (ASCII unchanged, full-width→ascii, ß→ss, composed/decomposed accents fold, **accents preserved** má≠ma, 張若塵→张若尘, kana untouched, has_han gate, guards) **+ a parity test** that the Go `T2S` equals the Python dict (read at test time or a checked-in golden).
- **Risk boundary → checkpoint/commit** (pure, additive).

### M2 — Wire glossary normalize to the SDK
- `textnorm.Normalize` keeps its trim/collapse contract but its case/fold step delegates to `loreweave_extraction.NormalizeEntityName` (i.e. `NormalizeEntityName(s)` then trim + collapse-ws). The existing `ParseList`/`IsList` are untouched.
- This alone fixes the **resolver** (the primary dedup path) for all future extractions.
- Audit every name-write path so the app sets the new `normalized_name` column (M3) at each: `createExtractedEntity`, manual entity create (propose-entity confirm), the name-attribute edit path (`apply_edit_handler`), book-adopt. Centralize via one helper `refreshEntityDedupKey(ctx, q, entityID)` that reads the entity's current `name` EAV and writes `normalized_name = sdk.NormalizeEntityName(name)`. (Merge does NOT change the winner's name → no call needed there.)
- Tests: resolver dedups 張若塵↔张若尘 within one (book,kind); control 八王子 stays distinct; full-width + casefold cases.
- **Risk boundary → checkpoint/commit** (behavior change, no schema yet).

### M3 — Schema migration: GENERATED → app-maintained plain column (forward-only)
New `internal/migrate` chain step (book-service-style forward-only; glossary migrations have no down):
1. Add plain `normalized_name_v2 TEXT NOT NULL DEFAULT ''` (or rename strategy — TBD in PLAN; keep the old column live until cutover).
2. **Backfill** `normalized_name_v2` for every live entity via the Go SDK (the migration runs in Go at startup → it can call `loreweave_extraction.NormalizeEntityName` over `cached_name`). This is where existing 張若塵/张若尘 rows get the SAME key.
3. **Detect collisions**: groups of >1 live entity sharing `(book_id, kind_id, normalized_name_v2)`.
4. **Dedup-merge** each collision group via `mergeEntitiesCore` — winner = anchored/glossary-richer (has translations / higher link+evidence count), losers merged in, journaled. **DRY-RUN by default**: report groups + planned winner/losers + counts, write nothing.
5. After a confirmed run with 0 residual collisions: build `uq_entity_dedup` on the new column, point the snapshot trigger to stop deriving normalized_name, drop the old GENERATED column + old index.
- **HUMAN CHECKPOINT before the destructive merge run** — present the dry-run on 万古神帝 (`019effe4`, ~5705 entities, ~69 S/T groups expected from the KG dry-run) and wait. This is the POST-REVIEW risk boundary.

### M4 — Live-smoke + close-out
- Deploy glossary image; drive a real extraction (or merge) with 張若塵 then 张若尘 → ONE glossary entity, alias-folded; control distinct. Confirm the `merged` outbox event re-synced the KG. Update SESSION_HANDOFF + DEFERRED.

## Risks / guards
- **Name-write-path audit miss** → a path changes the name but not `normalized_name` → stale backstop. Mitigate: single `refreshEntityDedupKey` helper + a grep-checklist in PLAN + a test per path. Because the Go resolver is the real dedup, a stale backstop degrades to "a race might slip a dup," never a wrong merge.
- **Migration aborts on collision** — intended; the dedup-merge step (M3.4) is the conscious resolution. Dry-run-first + journaled + per-(book,kind) scope.
- **Table drift py↔go** — killed by codegen from one SoT + a parity test.
- **casefold≠SQL-lower** — now irrelevant: no SQL fold remains; both resolver and stored key come from the one Go SDK call.
- **Over-merge** — fold equivalence only (no accent strip); group by `(book_id, kind_id, normalized)` so different kinds/books never merge.

## Out of scope
- Full OpenCC table import (the curated Phase-1 `T2S` is extensible; API stable as it grows) — shared follow-up with the Python side.
- Changing entity primary keys (glossary uses opaque UUIDs, not name-derived — no re-key needed, unlike the KG's canonical_id).
- A Rust SDK port (no Rust consumer of this fold today).
