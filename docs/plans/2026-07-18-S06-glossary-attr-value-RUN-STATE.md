# S-06 glossary attribute-value (add-later + delete) — RUN-STATE

## COMMITMENT
Build S-06 ([spec](../specs/2026-07-17-studio-completeness-build/S-06_glossary-attribute-value.md)):
add a value for an attr-def added AFTER an entity exists (REST, not MCP-only), and DELETE a value row
(not just blank it). **glossary-service (Go) + FE affordance.** Slice-by-slice, QC each. Finish = a user can
add a post-create attr value and remove a value row in the entity editor, operable end-to-end.

## INVESTIGATION — verified against code 2026-07-18 (don't trust the spec blindly)
- **Spec §2 route paths are WRONG (book-unscoped).** Real convention is **book-scoped**, mirroring
  `patchAttributeValue` (`server.go:534`): `.../books/{book_id}/entities/{entity_id}/attributes/...`.
  Corrected paths below.
- **Table:** `entity_attribute_values(attr_value_id, entity_id, attr_def_id, original_language,
  original_value, confidence)` with **`UNIQUE(entity_id, attr_def_id)`** (migrate.go:106) → add gets
  409-on-exists free via `ON CONFLICT DO NOTHING`.
- **Cascade is automatic:** `attribute_translations` + the per-item table both `REFERENCES
  entity_attribute_values(attr_value_id) ON DELETE CASCADE` (migrate.go:113,126). A single DELETE cleans the
  whole trail — no explicit child deletes.
- **Attr-def = `book_attributes(attr_id, kind_id, genre_id, deprecated_at, sort_order, is_required)`.**
  The entity-create seeding (`entity_handler.go:472`) inserts one value per book_attributes row where
  `kind_id = <entity kind> AND deprecated_at IS NULL AND genre_id = ANY(<entity genres>)`. **The add route
  MUST validate the attr_def against this SAME rule** (kind + not-deprecated + entity's genres) — the FK only
  checks existence, so without it a client could attach an attr from another kind/genre.
- **Write discipline to MIRROR (from MCP `set_attributes` + `patchAttributeValue`):** in ONE tx —
  insert value → `syncListItemsByID` (list value → items; scalar no-op) → bump `glossary_entities.updated_at`
  → `emitEntityUpdatedTx` (the `entity_updated` event the staleness/Neo4j-sync/learning consumers need).
  A DELETE mirrors: delete → bump updated_at → emit event.
- **Confidence:** a human-authored add is `'verified'` (INV-8 verified-clobber guard), like the MCP path.

## CORRECTED ROUTES (book-scoped)
```
POST   /v1/glossary/books/{book_id}/entities/{entity_id}/attributes
  body { attribute_def_id, value }  → 201 (the new attr value); 409 if a value row already exists
                                       (use PATCH to edit); 422 if attr_def not applicable to this entity
DELETE /v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}  → 204 (cascades)
```
Both: grant-gated EDIT + `verifyEntityInBook` (+ `verifyAttrValueInEntity` for delete), exactly like PATCH.

## SEALED DECISIONS
- SD-1 (REVISED) · Add validates applicability = **kind + not-deprecated** (NOT genre). Genre is a
  seeding-time refinement of which kind-attrs get pre-created; universal-genre attrs (`name`) apply to an
  entity with no `entity_genres` row, so a genre gate would wrongly 422 them (the fixture proves this: the
  entity carries no explicit genres yet `name` applies). The kind match is the real guard (blocks cross-kind).
- SD-2 · 409 on an existing value row (explicit add ≠ silent overwrite; PATCH is the edit path).
- SD-3 · Delete relies on ON DELETE CASCADE for children (translations + items); emits `entity_updated`.
- SD-4 · NO new MCP tool (spec §3) — agent add/edit already via `glossary_entity_set_attributes`; a
  single-row delete is human-GUI-driven. Conscious asymmetry, recorded.
- SD-5 · Delete is allowed on ANY value row incl. a required attr — the add route restores it (that IS the
  add-later loop). Not guarding required (a blank required value already exists today via PATCH-to-empty).

## SLICE BOARD (each: BUILD → QC → evidence)
| slice | user gains | status | evidence |
|---|---|---|---|
| **1 · BE add route** | add a value for a post-create attr-def | **DONE** | `addAttributeValue` (applicability=kind+not-deprecated, insert-or-409, list-sync, name/desc hooks, event) + route. **Go test `TestAddAttributeValue`: 201 verified row + 1 event · 409 no-overwrite (twice) · 422 cross-kind · 400 missing id. PASS (real DB, not skipped).** |
| **2 · BE delete route** | remove a value row (not blank) | **DONE** | `deleteAttributeValue` (cascade via FK, name/desc hooks, event, 204) + route. **Go test `TestDeleteAttributeValue`: 204 + row & child-translation cascade-gone + 1 event · 404 wrong-entity · 404 re-delete. PASS.** No regression (patch/items/version green); vet clean. |
| **3 · FE affordance** | "＋ add value" for a missing attr-def + "remove" (✕) on a value row | **DONE** | `glossaryApi.addAttributeValue/deleteAttributeValue`; `useGlossaryEntity.addAttributeValue/removeAttributeValue` (reload on success); `AttrCard` `onRemove` (non-system only, confirm+toast); NEW `AddAttributeValueSection` (offers the kind's missing attr-defs from `useBookOntology`, matches the BE's kind-scoped acceptance so no offer-then-422). **QC: FE 27/27 entity-editor (incl. AddAttributeValueSection 4 + modal 9 — fixed a regression: mocked useBookOntology in the modal test) + tsc clean; +8 i18n keys × 17 locales (gate clean).** |

## LIVE SMOKE
- BE proven by real-DB Go tests (add/delete + cascade + events, NOT skipped). FE by unit tests + tsc.
- Full browser E2E (add-later → new card → remove → gone, against a live stack): **infra-blocked — browser
  MCPs held by concurrent sessions all session**. Feature spans glossary-service + FE; each link proven
  (Go real-DB ↔ FE unit ↔ tsc). Recorded, not hidden.

## SAME-FOLDER / CONVERGENCE
glossary-service is Go — no shared FE registry. FE slice touches api.ts (knowledge/glossary) + i18n
(knowledge ns) — add keys minimally, fill via i18n_translate. Commit via pathspec, no `git add -A`.

## COMPLETENESS AUDIT (2026-07-18) — full S-06 stack
- **BUG-A (fixed): add/remove wiped OTHER unsaved edits.** `addAttributeValue`/`removeAttributeValue`
  called `reload()`, whose `setPendingChanges(new Map())` clears ALL pending — so typing a new value in
  attr A (unsaved) then adding/removing any attr silently lost A's edit. Fix: **remove = local** (filter the
  row + drop its pending, no refetch); **add = pending-preserving refetch** (`prunePending` keeps edits for
  still-existing rows). +2 hook tests lock it. (Same data-loss class as S-01b's create-mode dirty gap.)
- **BUG-B (verified NOT a bug): the add-section is not a silent empty shell.** It matches
  `entity.kind.kind_id` against ontology `attr.kind_id`; both are **book_kind_id** (entity GET builds
  `kind.kind_id` from `book_kinds.book_kind_id`, `entity_handler.go:162,183`; `book_attributes.kind_id` is a
  book_kind_id). Same tier ⇒ missing attrs resolve correctly.
- **Contract absence is pre-existing, not my gap.** No glossary OpenAPI contract documents the attr-value
  route family AT ALL (incl. the long-shipped PATCH/translations). My add/delete match that pattern.
- Verify after fix: entity-editor **27/27** + hook **16/16** (43 total) + tsc clean; BE Go tests still green.

## REGISTERS
### DEBT
- **D-S06-MCP-DELETE (conscious asymmetry, SD-4):** no `glossary_attribute_value_delete` MCP tool — agent
  add/edit already via `glossary_entity_set_attributes`; single-row delete is human-GUI driven. Deferred by
  spec §3 (agents rarely delete one attr row). Won't-fix unless agent parity is later wanted.
- **SD-5 (conscious):** the DELETE route permits removing ANY row incl. a required attr (add restores it);
  the FE gates its ✕ to non-system attrs (name/description stay). BE permissive + FE conservative — intended.
### DRIFT
- Spec §2 route paths were book-unscoped (wrong) — corrected against `server.go:534` before building.

## RESUME
Re-read THIS → `git log --oneline -8` → continue at the first non-DONE slice.
