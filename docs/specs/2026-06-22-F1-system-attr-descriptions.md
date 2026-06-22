# Spec — F1: System-tier attribute descriptions (build-ready)

**Date:** 2026-06-22 · **Branch:** `feat/knowledge-graph-ontology` · **Status:** DESIGN COMPLETE → ready to BUILD next session
**Parent:** [`2026-06-22-glossary-kg-extraction-quality-fixes.md`](2026-06-22-glossary-kg-extraction-quality-fixes.md) §F1 · `D-GLOSSARY-SYSTEM-ATTR-DESCRIPTIONS`

## Why
`book_attributes.description` is fed to the extraction LLM as the per-attribute
instruction ([extraction_prompt.py](../../services/translation-service/app/workers/extraction_prompt.py#L176-L185)).
All 93 seeded **System** attributes have an empty description, and books clone
System at adopt time, so the gap is platform-wide → extraction has no guidance.

## Verified mechanics (no schema change needed)
1. **`content_hash` already includes `description`.** `attrContentHash =
   md5(code|name|description|field_type|is_required|options)`
   ([attribute_def_handler.go:35](../../services/glossary-service/internal/api/attribute_def_handler.go#L35-L43)).
   So editing a System attribute's description **changes its hash**.
2. **Adopt copies `sa.description` + `sa.content_hash`** into the book row's
   `description` + `source_hash` ([book_adopt_handler.go:238-253](../../services/glossary-service/internal/api/book_adopt_handler.go#L238-L253)).
3. **G5 Sync detects drift by hash.** A changed System `content_hash` ≠ the book
   row's stored `source_hash` → `glossary_book_sync_available` lists the attribute
   as "source updated" → `glossary_book_sync_apply` `take_theirs` pulls the new
   description (`keep_mine` preserves any local edit).

⇒ A seed migration that sets `system_attributes.description` **and recomputes
`content_hash` with the same formula** makes: new books get descriptions at adopt;
existing books pull them via Sync (decision: **sync-only, no backfill**).

## Build plan (next session)

### M1 — seed migration (Go, idempotent, non-clobbering)
New `internal/migrate/system_attr_descriptions.go` (registered in the migration
chain). For each `(kind_code, attr_code)` in the **authored table** below:
```
UPDATE system_attributes sa
SET description = $desc,
    content_hash = <attrContentHash(code,name,$desc,field_type,is_required,options)>
FROM system_kinds sk
WHERE sa.kind_id = sk.kind_id AND sk.code = $kind AND sa.code = $attr
  AND COALESCE(TRIM(sa.description),'') = '';   -- never clobber an admin-authored one
```
- Recompute the hash **in Go** by reading each row and calling `attrContentHash`
  (exact-match guaranteed) — OR inline `md5(code||'|'||name||'|'||coalesce(description,'')||'|'||field_type||'|'||is_required::text||'|'||array_to_string(coalesce(options,'{}'),','))`
  (PG `boolean::text` = lowercase `true/false`, matches Go `strconv.FormatBool`;
  `array_to_string` of empty = `''`, matches `strings.Join`). Prefer the Go path.
- Idempotent: the `description=''` guard means a re-run is a no-op; running it after
  an admin already wrote a description leaves theirs intact.
- **Skip `name`/`term`** attributes (the display key — no extraction value); the
  table below omits them.

### M2 — verify (real-PG, throwaway DB — the `GLOSSARY_TEST_DB_URL` harness)
1. Run the migration → assert `system_attributes.description` set for a sample +
   `content_hash` changed from the pre-migration value.
2. **Adopt-before-edit propagation:** adopt a book (copies the OLD empty desc +
   old hash) → run the migration → `glossary_book_sync_available` lists those
   attrs as updated → `sync_apply take_theirs` → the book row now has the
   description; `keep_mine` on a locally-edited row preserves it.
3. **New-adopt:** adopt AFTER the migration → book rows carry descriptions
   immediately.
4. Idempotency: run the migration twice → second run updates 0 rows.

### M3 — (optional, same session) extraction smoke
Confirm a book whose `character` kind now carries descriptions produces an
extraction prompt with the per-attribute instructions present (the original bug).

## Authored description table (the content — 93 attrs, `name`/`term` omitted)

Descriptions are written as **extraction instructions**: what to capture, concretely.

### character
- `aliases` — Other names, titles, epithets, or nicknames the character is known by.
- `gender` — The character's gender or how the text presents it.
- `role` — The character's narrative role (protagonist, antagonist, mentor, foil, …).
- `occupation` — The character's job, profession, or primary activity in the story.
- `social_class` — The character's social standing or rank (noble, commoner, outcast, …).
- `affiliation` — The faction, house, organization, or side the character belongs to.
- `appearance` — Physical appearance: build, face, clothing, and any distinguishing or supernatural features described in the text.
- `personality` — Temperament, core traits, virtues and flaws as shown through actions and speech.
- `emotional_wound` — The past hurt, loss, or trauma that drives the character's behavior.
- `love_language` — How the character expresses or receives affection (if relevant to the story).
- `relationships` — Key relationships to other characters and how they connect.
- `description` — A concise overview of who the character is and their significance in the story.

### event
- `type` — The kind of event (battle, betrayal, wedding, death, revelation, …).
- `date_in_story` — When the event occurs in the story's timeline (in-world date or chapter).
- `location` — Where the event takes place.
- `participants` — The characters or groups involved in the event.
- `emotional_impact` — The emotional weight or fallout the event carries for those involved.
- `outcome` — What results or changes because of the event.
- `description` — What happens in the event, concisely.

### item
- `aliases` — Other names or titles the item is known by.
- `type` — The kind of item (weapon, artifact, relic, document, tool, …).
- `owner` — Who currently holds or is associated with the item.
- `symbolic_meaning` — What the item represents thematically or symbolically in the story.
- `description` — What the item is, its properties, and its role.

### location
- `aliases` — Other names the place is known by.
- `type` — The kind of place (city, castle, region, realm, building, …).
- `parent_location` — The larger place this one belongs to (region, country, world).
- `atmosphere` — The mood, tone, or sensory feel of the place as the text describes it.
- `significance` — Why the place matters to the story or its characters.
- `description` — What the place is and its notable features.

### organization
- `aliases` — Other names the organization is known by.
- `type` — The kind of organization (guild, house, cult, government, army, …).
- `leader` — Who leads or heads the organization.
- `headquarters` — The organization's base, seat, or primary location.
- `members` — Notable members or the makeup of the organization.
- `description` — What the organization is, its purpose, and its role in the story.

### plot_arc
- `arc_type` — The kind of arc (redemption, revenge, coming-of-age, mystery, …).
- `parties` — The characters or groups the arc centers on.
- `trigger` — The event or condition that sets the arc in motion.
- `stakes` — What is at risk or to be gained in the arc.
- `chapters_span` — The chapter range the arc covers.
- `emotional_beats` — The key emotional turning points along the arc.
- `resolution` — How the arc concludes or is left.
- `description` — A concise summary of the arc.

### power_system
- `aliases` — Other names the power/system is known by.
- `type` — The kind of power system (magic, cultivation, technology, psionics, …).
- `rank` — The tier, rank, or level scheme within the system.
- `user` — Who wields or has access to this power.
- `effects` — What the power does and its capabilities or limits.
- `description` — How the power system works, concisely.

### relationship
- `parties` — The characters or groups in the relationship.
- `relationship_type` — The kind of relationship (rivals, lovers, family, allies, …).
- `status` — The current state of the relationship (estranged, growing, broken, …).
- `tropes` — Romance/relationship tropes that characterize it (if any).
- `dynamic` — How the parties interact and the push-pull between them.
- `key_conflict` — The central tension or obstacle in the relationship.
- `turning_points` — Moments that shift the relationship.
- `resolution` — How the relationship resolves or is left.
- `description` — A concise summary of the relationship.

### social_setting
- `era` — The time period or era of the setting.
- `location` — The place or region the social setting covers.
- `class_hierarchy` — The social classes or hierarchy and how they relate.
- `rules_norms` — The customs, laws, and social norms that govern behavior.
- `romance_obstacles` — Social barriers to romance the setting imposes (if relevant).
- `significance` — Why this social setting matters to the story.
- `description` — A concise overview of the social setting.

### species
- `aliases` — Other names the species or race is known by.
- `traits` — Defining physical or innate traits of the species.
- `abilities` — Special abilities or powers the species possesses.
- `habitat` — Where the species lives.
- `culture` — The species' culture, customs, or social organization.
- `description` — What the species is, concisely.

### terminology
- `category` — The category the term belongs to (magic, politics, technology, …).
- `definition` — What the term means in this story's world.
- `usage_note` — How and when the term is used, and any nuance.

### trope
- `category` — The category of trope (character, plot, romance, setting, …).
- `definition` — What the trope is.
- `how_manifested` — How this trope shows up in the story specifically.
- `subverted` — Whether and how the story subverts or plays against the trope.
- `related_characters` — Characters who embody or are involved with the trope.
- `usage_note` — Notes on how the trope functions in the story.

> NOTE: a 14th/extra seeded kind beyond these may exist; the migration is keyed by
> `(kind_code, attr_code)` so any kind not in this table is simply left untouched —
> re-run after extending the table. Re-query `system_attributes` at build time to
> confirm the full set still matches (the merge from main may have touched seeds).

## Risks / notes
- The seed migration runs in the shared-DB test suite → mind the known parallel
  `migrate.Up` DDL deadlock (serialize via `pg_advisory_xact_lock`, per
  `shared-db-parallel-test-migration-deadlock`). This migration is **DML only**
  (UPDATE), so the DDL-lock risk is lower, but run own-package green + full suite
  `-p1` to be safe.
- `auto_fill_prompt` is left untouched (extraction reads `description`; a future
  pass could set `auto_fill_prompt` where it should differ from the human label).
- Admin-authored descriptions are never clobbered (the `description=''` guard).
