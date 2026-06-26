# Extraction Attribute Merge Defaults — accumulate knowledge across chapters

**Date:** 2026-06-26
**Service(s):** glossary-service (Go), translation-service (Python), frontend (React)
**Status:** Spec (CLARIFY/DESIGN — not yet built)
**Type:** [FS]

---

## Problem

Glossary extraction never UPDATES an entity's attributes after the **first** extract. When a
recurring entity reappears in a later chapter, only its **evidence** gets appended — every
other attribute (aliases, relationships, current location/status, age, …) is **skipped**. So a
character who gains a new alias, a new relationship, or moves to a new location in chapter 12
keeps exactly the attribute values captured in chapter 1. Evidence quotes pile up while the
knowledge they cite never advances.

This contradicts the intent of extraction as **automation**:

> "extraction is AUTOMATION work, but it almost skips instead of appending new knowledge about
> the glossary when it advances into a new chapter."

The default automated behavior must **accumulate** new knowledge across chapters, not freeze on
the first extract.

---

## Root cause (verified)

The merge engine already supports the *right* behaviors — but **every layer defaults to `fill`**,
and `fill` skips any attribute that already has a value.

### 1. The `fill` branch skips already-filled attributes

`services/glossary-service/internal/api/extraction_handler.go`

- `mergeExtractedEntity` (`:1318`) resolves the effective per-attribute action at `:1336-1348`.
- The `fill` branch (`:1376-1380`):

  ```go
  if action == "fill" {
      if attrValueExists && existingValue != "" {
          skipped = append(skipped, attrSkip{code, "fill_occupied"})
          continue   // ← 2nd+ extraction of a recurring entity dies here
      }
      ...
  }
  ```

  On the second and later extraction of the same entity, the value already exists and is
  non-empty, so the attribute is skipped with reason `fill_occupied`. This is the freeze.

### 2. Every layer defaults to `fill`

- **FE** `frontend/src/features/extraction/StepProfile.tsx` — `:64` (`attr.auto_selected ? 'fill' : 'skip'`),
  `:91`, `:112`, `:130` all author `'fill'` for auto-selected attributes.
- **Worker (HTTP path)** `services/translation-service/app/routers/extraction.py:159-160` —
  when no profile is supplied, builds `{code: "fill"}` for every auto-selected attr.
- **Worker (MCP path)** `services/translation-service/app/mcp/server.py:729` — same
  `{code: "fill"}` default derivation.
- **DB** `services/glossary-service/internal/migrate/merge_policy.go:35-39` —
  `system_attributes`, `user_attributes`, `book_attributes` each get
  `merge_strategy TEXT NOT NULL DEFAULT 'fill_if_empty'`.
- **Mapping** `strategyToAction` (`extraction_handler.go:1100-1111`) maps
  `fill_if_empty → fill`, and the `default:` arm also returns `fill`.

So whether the action arrives from the profile, the worker default, or the authored strategy,
it resolves to `fill` → `fill_occupied` skip.

### 3. The engine ALREADY has the behaviors we want — they just never fire

- **`append`** (`extraction_handler.go:1437-1488`) — true multi-value accumulation: each
  incoming element becomes a child row, deduped by `UNIQUE(attr_value_id, item_norm)` +
  `ON CONFLICT DO NOTHING`, with the cache rebuilt from active items. This is exactly the
  "accumulate across chapters" behavior — but no layer ever sends `append`.
- **`overwrite`** (`extraction_handler.go:1402-1436`) — single-value last-write-wins,
  audit-logged to `extraction_audit_log` before the update. This is the right behavior for
  current-state fields (location, status) — but again, never sent.
- **INV-8 verified-clobber guard** (`extraction_handler.go:1371-1374`) — a human-`verified`
  source value is always skipped (reason `verified`) regardless of action. **This is correct
  and must be KEPT.**

### 4. The FE enum is missing `append` entirely

`frontend/src/features/extraction/types.ts:29`:

```ts
export type AttributeAction = 'fill' | 'overwrite' | 'skip';   // no 'append'
```

The UI cannot express the one strategy that accumulates. The `StepProfile.tsx` `<select>`
(`:328-330`) only offers Fill / Overwrite / Skip.

### 5. Evidence is the reason the symptom looked partial

Evidence is appended **unconditionally** via `ON CONFLICT` (`extraction_handler.go:846`), which
is why evidence grows on every re-extraction while attributes freeze — the contrast that makes
the bug visible.

### Existing tests

`services/glossary-service/internal/api/extraction_writeback_test.go` already has
`TestMergeStrategy_FromOntology` (authored-strategy → action resolution). New tests extend
this file.

---

## Decision (3 user points)

1. **Type-heuristic seed defaults + UI override.** Seed each attribute's authored
   `merge_strategy` *by attribute type* instead of a blanket `fill_if_empty`:
   - **list / alias / multi-valued** (`field_type` `tags`, multi-value) → `append`
   - **narrative / current-state** (location, status, age, and `textarea` narrative fields) → `overwrite`
   - **identity** (canonical `name` / `term`, `is_required` text key) → `fill`

   AND expose **all** strategies in the ontology/extraction UI — including the currently-missing
   `append` — so the user can override any attribute's strategy.

2. **Default automated behavior must ACCUMULATE.** Re-extraction into a new chapter must, by
   default, *add/append* new knowledge (new aliases, new relationships) and *advance*
   current-state fields — not skip. The heuristic's whole job is to make automated
   re-extraction accumulate by default.

3. **Reuse the raw cache to HEAL history.** The extraction raw-output cache
   (`extraction_raw_outputs` in translation-service; replay path
   `services/translation-service/app/workers/extraction_replay.py`,
   `replay_chapter_from_cache`) already re-drives the glossary writeback from a cached parse at
   $0 LLM. The fix must include a path to **re-merge existing entities from cached raw outputs**
   under the new strategies — healing already-extracted (frozen) entities **without re-calling
   the LLM** — not only applying to future extractions.

---

## Design

### (a) `merge_strategy` seed heuristic + migration for existing ontology attributes

The strategy default lives on the ontology attribute rows (`system_attributes`,
`user_attributes`, `book_attributes`), seeded today as a flat `'fill_if_empty'`
(`merge_policy.go:35-39`). Two changes:

**a.1 — New seeded default per attribute type (forward).**
At seed time (the `system_attributes` insert in `migrate.go` around `:1919-1929`, sourced from
`internal/domain/kinds.go` `DefaultKinds`, whose `FieldType` values are `text` / `textarea` /
`tags` / `select`), derive `merge_strategy` from a heuristic rather than relying on the column
DEFAULT:

| Heuristic class | Matches | `merge_strategy` |
|---|---|---|
| **Identity** | `code IN ('name','term')` OR (`is_required` AND `field_type='text'`) | `fill_if_empty` |
| **List / multi-valued** | `field_type IN ('tags')` (e.g. `aliases`, `participants`, `relationships`-as-tags) | `append` |
| **Current-state / narrative** | everything else (`textarea` narrative, `text` state fields like `location`, `status`, `affiliation`, `parent_location`) | `overwrite` |

Implementation: add a small pure mapper (Go) `seedMergeStrategy(code, fieldType string, isRequired bool) string`
co-located with the seed, applied in the `system_attributes` INSERT `SELECT`. Keep the column
DEFAULT `'fill_if_empty'` as the safe fallback for any row a future path inserts without
specifying.

> Note on `relationships`: in `DefaultKinds` the character `relationships` attr is `textarea`
> (`kinds.go:75`), so under the table above it lands in `overwrite`. If product wants
> relationships to *accumulate*, change that attribute's `field_type` to `tags` (a separate,
> deliberate ontology change) — the heuristic then routes it to `append` automatically. Spec
> default keeps the heuristic mechanical; per-attribute intent is the user-override job.

**a.2 — Migration to RE-SEED existing rows (heal authored ontology).**
A new `migrate` step (next chain number after `merge-policy`/`extraction_concurrency`, additive
+ idempotent via `execGuarded`) UPDATEs the strategy on **existing** rows that still carry the
old blanket default, in all three tiers:

- **System tier** (admin-owned, read-only to users): update unconditionally — these are the
  platform defaults, safe to re-seed by the same heuristic.
- **Per-user / per-book tiers:** update **only** rows whose `merge_strategy = 'fill_if_empty'`
  (the untouched seed default) — i.e. never clobber a strategy a user/book author already set.
  This respects the tenancy rule: a migration must not rewrite a user's deliberate choice.

  ```sql
  -- illustrative; one statement per tier, guarded
  UPDATE system_attributes SET merge_strategy = CASE
      WHEN code IN ('name','term') THEN 'fill_if_empty'
      WHEN field_type = 'tags'      THEN 'append'
      ELSE 'overwrite'
  END;
  UPDATE book_attributes SET merge_strategy = CASE ... END
      WHERE merge_strategy = 'fill_if_empty';   -- only untouched defaults
  UPDATE user_attributes SET merge_strategy = CASE ... END
      WHERE merge_strategy = 'fill_if_empty';
  ```

  (`name`/`term` identity stays `fill_if_empty`; `tags` → `append`; everything else →
  `overwrite`.)

### (b) Propagate the default — no-action falls through to the authored strategy

The fall-through **already exists and is correct** at `extraction_handler.go:1336-1348`:

```go
action, specified := actions[code]
if action == "skip" { ... continue }
if !specified || action == "" {
    strat := strategyMap[kindID.String()+":"+code]   // loadAttrStrategyMap (:1069)
    if strat == "manual" { skip "manual"; continue }
    action = strategyToAction(strat)                 // fill_if_empty→fill, append→append, …
}
```

So once (a) seeds the right strategies, an extraction profile that sends **no explicit action**
for an attribute correctly falls through to the authored `append` / `overwrite` / `fill`.

**The required code change for (b) is to STOP forcing `fill` upstream** so the fall-through is
actually reached:

- **Worker defaults** — `translation-service/app/routers/extraction.py:159-160` and
  `app/mcp/server.py:729`: when the profile is omitted, build the auto-selected kind/attr set
  **without** an explicit per-attr action (omit the attr from the action map, or send a sentinel
  meaning "use authored default") so the resolver hits the strategy branch instead of `"fill"`.
  Keep `skip` available for deselected attrs.
- **FE default** — `StepProfile.tsx:64,91,112,130`: the auto-initialized profile should select
  an attribute (so it participates) but carry an action of **"default"** (authored-strategy)
  rather than a hardcoded `'fill'`. See (c) for the enum/value.

  Concretely: the FE/worker contract gains a `"default"` (or omission) meaning "defer to the
  attribute's authored `merge_strategy`". The glossary resolver already treats
  `!specified || action == ""` as "use the strategy", so the worker can simply **omit** the attr
  from `attribute_actions` to mean default — the simplest wire change. Whichever encoding is
  chosen, document it once and use it on both FE and worker.

> Net: (a) makes the *authored default* correct; (b) makes the pipeline *actually use* the
> authored default instead of overriding it with `fill`.

### (c) FE — add `append`, surface "default", expose all strategies

- **`frontend/src/features/extraction/types.ts:29`** — extend the enum:

  ```ts
  // 'default' = defer to the attribute's authored merge_strategy (the accumulate-by-default path)
  export type AttributeAction = 'default' | 'fill' | 'append' | 'overwrite' | 'skip';
  ```

- **`StepProfile.tsx`**
  - Per-attr `<select>` (`:317-331`) gains options for **Append** and **Default**
    (alongside Fill / Overwrite / Skip), with i18n keys `profile.actionAppend`,
    `profile.actionDefault`.
  - Auto-init (`:64`) and the `toggleKind` / `buildKindProfile` / `bulkAction` helpers
    (`:91,112,130`) author `'default'` for selected attrs instead of `'fill'` (so the seeded
    heuristic governs). `is_required` identity attrs may stay pinned to `'fill'` as today.
  - Add a bulk **"All Append"** button next to the existing All-Fill / All-Overwrite
    (`:266-277`), and optionally an **"All Default"**.
  - Optionally surface each attribute's *authored* strategy as a hint next to `attr.field_type`
    (`:315`) so the user sees what "Default" will do. Requires the extraction-profile response
    to include `merge_strategy` per attribute (additive field; see below).
- **Ontology attribute editor** — wherever a book/user author edits an attribute's
  `merge_strategy` (the per-attribute ontology form), expose the full set
  (`fill_if_empty` / `append` / `overwrite` / `replace` / `manual`) so authors can override the
  seeded heuristic. If no such control exists yet, this is the place it is added; the value
  round-trips through the existing attribute-def update path
  (`glossary-service/internal/api/attribute_def_handler.go`).
- **Profile response (additive, optional but recommended):** include `merge_strategy` on each
  `ExtractionProfileAttribute` (`types.ts:3-11` + the glossary profile endpoint) so the FE can
  show the effective default. Purely additive; no behavior change if unread.

### (d) Raw-cache re-merge job/endpoint — heal existing entities

Reuse the **existing** replay machinery (`extraction_replay.py::replay_chapter_from_cache`),
which already:
- re-fetches the chapter, verifies `chapter_content_hash` **and** `profile_hash` still match the
  cached generation (faithful-by-construction),
- re-drives the glossary whole-chapter writeback from the cached parse at $0 LLM,
- is grant-gated (caller holds EDIT) and tenancy-scoped (`owner_user_id = caller`, INV-9),
- supports `confirm=False` dry-run preview.

**What changes for healing:** replay today reconstructs the **original** job's
`attribute_actions` from the source profile. To heal under the *new* strategies, the re-merge
must let the **authored merge_strategy govern** rather than re-applying the original (frozen,
`fill`) actions — i.e. send the cached entities to the glossary writeback **with no explicit
per-attr action**, so the resolver's strategy fall-through (b) routes each attribute to
`append` / `overwrite` / `fill` under the freshly-seeded defaults.

Because `append` is idempotent (dedup by `UNIQUE(attr_value_id, item_norm)` →
`unchanged`) and `overwrite` is audit-logged + last-write-wins, re-merging an
already-extracted chapter is **safe to run repeatedly**: list attrs gain any
cached-but-dropped items, state attrs settle to the cached value, identity stays put, and
`verified` attrs remain untouched (INV-8).

**Surface:**
- A **re-merge endpoint** (translation-service `internal_dispatch` / extraction router) e.g.
  `POST /internal/extraction/books/{book_id}/rerun-merge` (or a flag on the existing replay
  endpoint, `mode=heal`), iterating the book's cached chapters and calling
  `replay_chapter_from_cache(..., use_authored_strategy=True)` per chapter.
- Honors the same `confirm` dry-run semantics (preview counts of would-append /
  would-overwrite / would-skip before writing).
- Returns per-chapter status (`replayed` / `no_cache` / `profile_unavailable` / `empty`), so a
  chapter whose content or profile drifted is reported (run a fresh extraction there) rather
  than silently healed wrong.

A chapter with **no faithful cache** (`no_cache` / `profile_unavailable`) cannot be healed
offline — it needs a fresh extraction. That is expected and surfaced, not an error.

---

## Phasing

- **M1 — Strategy defaults + migration (BE, glossary-service).**
  Seed heuristic mapper + migration to re-seed existing System/per-book/per-user ontology
  attributes (a). No new wire contract; the resolver fall-through (b, resolver side) already
  exists. Tests extend `extraction_writeback_test.go` (`TestMergeStrategy_FromOntology`):
  prove a recurring entity now appends list attrs / overwrites state attrs / keeps identity
  when the profile sends no explicit action.

- **M2 — Pipeline default + FE `append`/`default` exposure (FS).**
  Worker stops forcing `fill` (b, worker side); FE adds `append` + `default` to the enum,
  surfaces them in `StepProfile` and the ontology attribute editor (c). Live-smoke: run a
  2-chapter extraction of a recurring entity through the real stack and confirm accumulation.

- **M3 — Raw-cache re-merge heal (FS).**
  Re-merge endpoint/job over `extraction_raw_outputs` using authored strategies (d), with
  dry-run preview. Live-smoke: heal a pre-existing frozen entity from cache at $0 LLM and
  confirm its list attrs grow without an LLM call.

---

## Acceptance criteria

1. **Accumulation across chapters (the core fix).** A recurring entity extracted across N
   chapters (no explicit per-attr action in the profile):
   - **List/alias attrs ACCUMULATE** — a new alias in chapter K is present after merge;
     re-running is idempotent (`unchanged`, no duplicate child row).
   - **Current-state attrs UPDATE** — a new location/status in chapter K replaces the prior
     value, with the prior value written to `extraction_audit_log`.
   - **Identity stays stable** — the canonical `name`/`term` is not churned by re-extraction.
2. **Verified values untouched.** A human-`verified` source value is never overwritten or
   appended-over (skip reason `verified`, INV-8) regardless of strategy.
3. **No-action falls through to authored strategy.** An extraction profile that omits the
   per-attr action resolves to the attribute's seeded `merge_strategy` (proven via the existing
   resolver path at `extraction_handler.go:1336-1348`), not to `fill`.
4. **Migration heals existing ontology.** After M1, existing System attributes carry
   type-appropriate strategies; per-user/per-book rows are updated only where still at the
   untouched `fill_if_empty` default (no author override clobbered).
5. **FE exposes every strategy.** `StepProfile` and the ontology attribute editor offer
   Fill / Append / Overwrite / Skip / Default (authored). `AttributeAction` includes `append`.
6. **Raw-cache heal works offline.** Re-merging a previously-frozen entity from
   `extraction_raw_outputs` under the new strategies grows its list attrs / advances its state
   attrs **without an LLM call**, is idempotent on re-run, and reports `no_cache` /
   `profile_unavailable` for chapters that can't be faithfully replayed.

---

## Out of scope

- **Glossary version-control FE wiring** — the entity history/version UI is a separate task and
  is not touched here. (`overwrite` already audit-logs to `extraction_audit_log`; surfacing
  that history in the FE is its own effort.)
- **Re-homing `extraction_raw_outputs` to knowledge-service** (`D-EXTRACTION-REHOME-KNOWLEDGE`)
  — the cache stays in translation-service; this spec uses it through the existing interface
  seam only.
- **Changing any attribute's `field_type`** (e.g. making `relationships` a `tags` list so it
  appends) — a deliberate ontology change, not part of the merge-defaults fix; the heuristic
  simply follows whatever `field_type` an attribute already has.
- **Model-keyed cache invalidation** (`D-CACHE-MODEL-KEY`) — re-merge reuses whatever parse the
  cache holds; switching models is not a re-merge trigger here.
