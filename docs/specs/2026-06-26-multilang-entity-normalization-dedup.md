# Spec — Multi-language entity-name normalization + variant dedup (D-KG-TL-SIMPLIFIED-TRADITIONAL-DUP, generalized)

**Date:** 2026-06-26 · **Status:** ✅ SHIPPED via **wire-then-wipe** (user decision — the existing KG was disposable test data, so NO merge migration).

> **DECISION (user, 2026-06-26):** the current knowledge graph is just test data → **wipe it and re-extract**, don't build a node-merge migration. So the fix = Phase 1 normalizer + **wire it into `canonicalize_entity_name`/`canonicalize_text`** (done) + **wipe the Neo4j KG**. Future extractions fold variants at the source, producing clean deduped entities (proven by the dry-run: 69 same-source S/T pairs would have been distinct; now they share one `canonical_id`). The Phase-2 dedup-MIGRATION below is retained for reference only — NOT built (would only be needed to preserve real production data).

## Problem
`canonicalize_entity_name` (SDK `loreweave_extraction.canonical`) does lowercase + honorific-strip + whitespace/punctuation only — **no Unicode-equivalence or script folding**. So variant spellings of the SAME entity get DIFFERENT `canonical_id` (the Neo4j `:Entity` primary key) → duplicate nodes. Surfaced by the participant-anchor smoke: 張若塵 (traditional, has vi translation) and 张若尘 (simplified, no vi) are two entities; participant localization anchored to the wrong one. The user asked to fix this **generally (multi-language), not hard-coded CJK**.

## Variant classes (what should fold vs NOT)
| Class | Example | Fold? | Mechanism |
|---|---|---|---|
| Compatibility / width | `Ｋａｉ` (full-width) vs `Kai` | YES | Unicode **NFKC** (stdlib) |
| Composed vs decomposed | `é` (U+00E9) vs `e`+◌́ (U+0065 U+0301) | YES | NFKC |
| Case (all scripts) | `İ`/`ı`, `ß`→`ss` | YES | Unicode **casefold** (stdlib, replaces `.lower()`) |
| CJK simplified ↔ traditional | 張若塵 ↔ 张若尘 | YES | **vendored frozen T→S table** (gated on Han chars) |
| Diacritics / accents | vi `ma` vs `má`, `Müller` vs `Muller` | **NO** | accent-strip would over-merge distinct names |
| Kana / Hangul / Latin base letters | は vs ハ; 가 vs 갸 | NO | distinct phonemes — NFKC already handles compat only |

**Principle:** fold only *equivalence* (same identity, different encoding/script), never *similarity* (distinct names that look close). Accents stay.

## Converter decision — VENDOR a frozen table (not opencc/hanziconv)
`entity_canonical_id` must be **deterministic forever** (it's the node key; re-running extraction on the same source must yield the same id). An external lib (opencc C-ext, hanziconv) could change its mapping between versions → silent mass re-keying. So the CJK simplified/traditional fold uses a **table vendored into the SDK** (`loreweave_extraction/_han_simplified_table.py`), frozen + tested. NFKC + casefold are stdlib (`unicodedata.normalize('NFKC', …)`, `str.casefold()`) — already deterministic. Phase 1 ships a curated common-character table (covers frequent names); a follow-up can import a complete OpenCC-derived set without changing the API. Zero new runtime deps; Python ≥3.11.

## Phase 1 — normalization primitive (PURE, no data touched) — BUILD NOW
New SDK module `loreweave_extraction/name_normalize.py`:
- `nfkc_casefold(s) -> str` — `unicodedata.normalize("NFKC", s)` then `.casefold()`.
- `fold_han_simplified(s) -> str` — map each char via the vendored T→S table; no-op when no Han present (cheap guard).
- `normalize_entity_name(name) -> str` — the **v2** pipeline: `nfkc_casefold` → `fold_han_simplified` → honorific-strip (reuse `HONORIFICS`) → whitespace-collapse → punctuation-strip. Mirrors the current `canonicalize_entity_name` step order but with the two new leading folds + casefold replacing lower.
- Pure functions, fully unit-tested. **Not yet wired into `canonicalize_entity_name`'s live id derivation** (wiring changes ids → must land WITH the migration, Phase 2). This phase de-risks the hard logic + the table behind tests.

**Tests (Phase 1):** English/ASCII unchanged vs the current canonicalize (no accidental re-key of Latin names); full-width `Ｋａｉ`→`kai`; decomposed accent NFKC-folds but vi `má`≠`ma` (accent preserved); 張若塵→张若尘 and 萬→万, 龍→龙, 瑤→瑶 fold; Japanese kana / Korean unaffected; honorific + whitespace still stripped; empty/non-str guards.

## Phase 2 — cutover + dedup migration (DRY-RUN first, then go) — NOT in Phase 1
1. **Wire** `canonicalize_entity_name` → `normalize_entity_name` (SDK). Do NOT bump `canonical_version` (keeps ASCII/unchanged ids stable → only entities whose normalized string actually changes are affected — surgical blast radius). Resolution (`entity_resolver._fold`, `find_entities_by_name`) automatically uses the new fold.
2. **Per-(user, project) dedup migration** (`app/db/migrations/canonicalization_normalize.py` + internal endpoint, mirrors backfill-participant-anchors):
   - Load all `:Entity (id, name, kind, canonical_name, glossary_entity_id, mention_count)`.
   - Group by `(kind, normalize_entity_name(name))`. Groups with >1 = variant duplicates.
   - Winner = anchored (glossary_entity_id) first, then higher mention_count/relation-degree.
   - For each loser: `merge_entities(session, user_id, source_id=loser, target_id=winner)` (rewires `:RELATES_TO`/`:ABOUT`/`:EVIDENCED_BY`, folds aliases/source_types, deletes loser) **+ the two gaps the existing primitive doesn't cover yet:**
     - **`participant_entity_ids`** on `:Event` — repoint loser id → winner id in the parallel arrays (added after `merge_entities` was written). Extend `merge_entities` or a follow-up Cypher pass.
     - **`entity_alias_map`** (Postgres) — `record_merge` a redirect row for the loser's canonical_name + each alias → winner id, so any straggler resolves forward.
   - Update the winner's `canonical_name` to the new normalized form (so `find_entities_by_name` matches future extractions); the winner's `id` stays (changing it = a second re-key; deferred — `canonical_name`-match in resolution is sufficient).
   - Journal each merge for reversibility (mirror glossary's merge journal).
3. **DRY-RUN mode** (default): report duplicate groups + planned merges + counts, write NOTHING. Present the dry-run on a real CJK book (万古神帝 `019effe4`) before any destructive run.
4. **Live-smoke:** after a confirmed run, re-check that 张若尘/張若塵 collapse to one anchored entity and the timeline localizes 张若尘.

## Risks / guards
- **Re-keying the entity primary key** is the core risk — mitigated by NOT bumping `canonical_version` (surgical), reusing the tested `merge_entities` primitive, dry-run-first, per-(user,project) scoping, and the merge journal.
- **Table incompleteness** (Phase 1 curated subset) → a rare char doesn't fold → a residual duplicate (no worse than today; additive). Full-table import is a clean follow-up.
- **Over-merge** — guarded by folding equivalence only (no accent strip) + grouping by `(kind, normalized)` (different kinds never merge).
- **participant_entity_ids gap** — explicitly handled in Phase 2 (the primitive predates that feature).

## Out of scope
- Full OpenCC table import (follow-up; Phase 1 table is extensible).
- Changing the winner's node `id` to the new canonical_id (resolution matches on `canonical_name`; id-rename is a separate, larger re-key deferred unless needed).
- Glossary-service entity dedup (its own `mergeEntitiesCore` + EAV model; separate track).
