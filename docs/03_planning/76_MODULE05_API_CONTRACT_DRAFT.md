# LoreWeave Module 05 API Contract Draft (Glossary & Lore Management)

## Document Metadata

- Document ID: LW-M05-76
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect
- Last Updated: 2026-03-23
- Approved By: —
- Approved Date: —
- Summary: Contract-first draft for Module 05 APIs covering glossary entity CRUD, entity kind enumeration, chapter-entity link management, attribute values, translations, evidences, and RAG-ready export.

## Change History

| Version | Date       | Change                              | Author    |
| ------- | ---------- | ----------------------------------- | --------- |
| 0.2.0   | 2026-03-23 | Expand to 12 default kinds: add 4 romance/drama kinds + Character romance attrs + `genre_tags` field on EntityKind; add §9 Genre Profile architecture note | Assistant |
| 0.1.0   | 2026-03-23 | Initial Module 05 contract draft    | Assistant |

---

## 1) Contract Scope

This draft defines gateway-facing behavior for:

- entity kind enumeration (8 system defaults),
- glossary entity CRUD with filter and pagination,
- chapter-entity link management (M:N),
- entity attribute value CRUD,
- translation CRUD per attribute value,
- evidence CRUD per attribute value,
- RAG-ready JSON export per book.

All endpoints are served by `glossary-service` (port 8088) behind `api-gateway-bff` at path prefix `/v1/glossary`.

---

## 2) Proposed OpenAPI Surface

| API surface | Proposed OpenAPI path |
| --- | --- |
| Glossary pipeline | `contracts/api/glossary/v1/openapi.yaml` |

---

## 3) Core Endpoint Set (Draft)

### 3.1 Entity Kinds (read-only in MVP)

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/v1/glossary/kinds` | GET | Bearer | List all entity kinds (8 defaults). Returns `id`, `code`, `name`, `icon`, `color`, `default_attributes[]` |

### 3.2 Glossary Entities

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/v1/glossary/books/{book_id}/entities` | GET | Bearer | List entities for a book with filters (kind, status, chapter_ids, search, tags). Owner only |
| `/v1/glossary/books/{book_id}/entities` | POST | Bearer | Create new glossary entity. Owner only |
| `/v1/glossary/books/{book_id}/entities/{entity_id}` | GET | Bearer | Get single entity with full detail (attributes, translations, evidences, chapter links). Owner only |
| `/v1/glossary/books/{book_id}/entities/{entity_id}` | PATCH | Bearer | Update entity metadata (kind_id, status, tags). Owner only |
| `/v1/glossary/books/{book_id}/entities/{entity_id}` | DELETE | Bearer | Delete entity and all its attributes, translations, evidences, chapter links. Owner only |

### 3.3 Chapter-Entity Links

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/v1/glossary/books/{book_id}/entities/{entity_id}/chapter-links` | GET | Bearer | List all chapter links for an entity |
| `/v1/glossary/books/{book_id}/entities/{entity_id}/chapter-links` | POST | Bearer | Create a chapter link (link entity to a chapter with relevance + optional note) |
| `/v1/glossary/books/{book_id}/entities/{entity_id}/chapter-links/{link_id}` | PATCH | Bearer | Update relevance or note on a chapter link |
| `/v1/glossary/books/{book_id}/entities/{entity_id}/chapter-links/{link_id}` | DELETE | Bearer | Unlink entity from chapter |

### 3.4 Attribute Values

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/v1/glossary/books/{book_id}/entities/{entity_id}/attributes` | GET | Bearer | List all attribute values for an entity |
| `/v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}` | PATCH | Bearer | Update original language or original value of an attribute |

> Note: Attribute values are created automatically when an entity is created (one per default attribute for the entity's kind). They are not individually created via API; they are patched.

### 3.5 Translations

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}/translations` | POST | Bearer | Add a translation to an attribute value |
| `/v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}/translations/{translation_id}` | PATCH | Bearer | Update translation value or confidence |
| `/v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}/translations/{translation_id}` | DELETE | Bearer | Remove a translation |

### 3.6 Evidences

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}/evidences` | POST | Bearer | Add an evidence entry to an attribute value |
| `/v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}/evidences/{evidence_id}` | PATCH | Bearer | Update evidence text, location, or note |
| `/v1/glossary/books/{book_id}/entities/{entity_id}/attributes/{attr_value_id}/evidences/{evidence_id}` | DELETE | Bearer | Remove an evidence entry |

### 3.7 RAG Export

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/v1/glossary/books/{book_id}/export` | GET | Bearer | Export all active entities as RAG-ready JSON. Owner only. Optional query param: `chapter_id` to scope export to a specific chapter |

### 3.8 Health

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/health` | GET | None | Service health check |

---

## 4) Query Parameters

### GET `/v1/glossary/books/{book_id}/entities`

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `kind_codes` | `string[]` | all | Filter by entity kind codes (comma-separated: `character,location`) |
| `status` | `string` | `all` | `all` \| `active` \| `inactive` \| `draft` |
| `chapter_ids` | `string[]` | all | Comma-separated chapter UUIDs. Use `unlinked` to show entities with zero chapter links |
| `search` | `string` | — | ILIKE search across entity name attribute values and translations |
| `tags` | `string[]` | — | Comma-separated tags; entities must have ALL listed tags |
| `limit` | `int` | 50 | Max items per page |
| `offset` | `int` | 0 | Pagination offset |
| `sort` | `string` | `updated_at_desc` | `updated_at_desc` \| `updated_at_asc` \| `name_asc` \| `name_desc` |

---

## 5) Core Schemas (Draft)

### EntityKind

```
id               UUID
code             string       "character" | "location" | "item" | "power_system" | "organization" | "event" | "terminology" | "species" | "relationship" | "plot_arc" | "trope" | "social_setting"
name             string
description      string?
icon             string       emoji character
color            string       hex color "#6366f1"
is_default       bool         true for all 12 defaults
is_hidden        bool         default false
sort_order       int
genre_tags       string[]     e.g. ["universal"] | ["fantasy"] | ["romance","drama"] — used by future Genre Profile feature to filter visible kinds
default_attributes  AttributeDefinition[]
```

### AttributeDefinition

```
id               UUID
code             string       "name" | "aliases" | "gender" | "role" | ...
name             string       display label
description      string?
field_type       "text" | "textarea" | "select" | "number" | "date" | "tags" | "url" | "boolean"
is_required      bool
sort_order       int
options          string[]?    only for field_type = "select"
```

### GlossaryEntity (list item)

```
entity_id        UUID
book_id          UUID
kind_id          UUID
kind             EntityKind (embedded, summary only)
display_name     string       resolved from "name" attribute original value
display_name_translation  string?  resolved from "name" attribute translation for viewer's language
status           "active" | "inactive" | "draft"
tags             string[]
chapter_link_count  int
translation_count   int       total translations across all attribute values
evidence_count      int       total evidences across all attribute values
created_at       ISO timestamp
updated_at       ISO timestamp
```

### GlossaryEntity (detail — GET single)

```
entity_id        UUID
book_id          UUID
kind_id          UUID
kind             EntityKind
chapter_links    ChapterLink[]
attribute_values AttributeValue[]
status           "active" | "inactive" | "draft"
tags             string[]
created_at       ISO timestamp
updated_at       ISO timestamp
```

### ChapterLink

```
link_id          UUID
entity_id        UUID
chapter_id       UUID
chapter_title    string?      denormalized
chapter_index    int?         for ordering
relevance        "major" | "appears" | "mentioned"
note             string?
added_at         ISO timestamp
```

### AttributeValue

```
attr_value_id        UUID
entity_id            UUID
attribute_def_id     UUID
attribute_def        AttributeDefinition (embedded)
original_language    string  BCP-47 / ISO 639-1
original_value       string
translations         Translation[]
evidences            Evidence[]
```

### Translation

```
translation_id   UUID
attr_value_id    UUID
language_code    string   BCP-47
value            string
confidence       "verified" | "draft" | "machine"
translator       string?
updated_at       ISO timestamp
```

### Evidence

```
evidence_id          UUID
attr_value_id        UUID
chapter_id           string   UUID or null
chapter_title        string?  denormalized
block_or_line        string   "Line 34" | "Paragraph 12" | "Section 2.3"
evidence_type        "quote" | "summary" | "reference"
original_language    string
original_text        string
note                 string?
translations         EvidenceTranslation[]
created_at           ISO timestamp
```

### EvidenceTranslation

```
id               UUID
evidence_id      UUID
language_code    string
value            string
confidence       "verified" | "draft" | "machine"
```

### RAG Export (book-level)

```json
{
  "glossary_version": "1.0",
  "book_id": "...",
  "exported_at": "ISO timestamp",
  "entities": [
    {
      "entity_id": "...",
      "kind": "character",
      "status": "active",
      "chapter_links": [
        { "chapter_id": "...", "chapter_title": "Chapter 1", "relevance": "major" }
      ],
      "tags": ["protagonist"],
      "attributes": {
        "name": {
          "original": { "lang": "zh", "value": "林默" },
          "translations": [
            { "lang": "en", "value": "Lin Mo", "confidence": "verified" }
          ],
          "evidences": [
            {
              "type": "quote",
              "location": { "chapter_id": "...", "block": "Line 34" },
              "original": { "lang": "zh", "text": "少年名叫林默..." },
              "translations": [{ "lang": "en", "text": "The young man was named Lin Mo..." }]
            }
          ]
        }
      }
    }
  ]
}
```

---

## 6) Error Taxonomy

| Code | HTTP | Meaning |
| --- | --- | --- |
| `GLOSS_NOT_FOUND` | 404 | Entity, kind, chapter link, attribute, translation, or evidence not found |
| `GLOSS_FORBIDDEN` | 403 | Requester is not the book owner |
| `GLOSS_BOOK_NOT_FOUND` | 404 | Book does not exist or is not accessible |
| `GLOSS_KIND_NOT_FOUND` | 404 | `kind_id` references a non-existent kind |
| `GLOSS_DUPLICATE_CHAPTER_LINK` | 409 | Entity is already linked to this chapter |
| `GLOSS_DUPLICATE_TRANSLATION_LANGUAGE` | 409 | A translation for this language already exists on this attribute value |
| `GLOSS_INVALID_KIND_CODE` | 422 | `kind_code` not in the 12 allowed defaults |
| `GLOSS_REQUIRED_ATTRIBUTE_EMPTY` | 422 | A required attribute (e.g. `name`) has empty `original_value` on save |
| `GLOSS_CHAPTER_NOT_IN_BOOK` | 422 | Attempted to link entity to a chapter that does not belong to the book |

---

## 7) Default Entity Kind Schema

> **12 default kinds** across three genre groups. All are visible to all users in MVP (genre filtering deferred to the Genre Profile feature — see §9). `genre_tags` field is stored in DB for future use.

---

### Group A — Universal Kinds (all genres)

### Character (`character`, 👤, #6366f1) — `genre_tags: ["universal"]`

> Expanded from fantasy-only to cover romance, drama, and general fiction. Romance-specific attributes (`occupation`, `social_class`, `emotional_wound`, `love_language`) are available for all users; they can be hidden if not needed.

| # | Code | Name | Type | Required | Notes |
|---|---|---|---|---|---|
| 1 | `name` | Name | text | ✓ | Primary character name |
| 2 | `aliases` | Aliases | tags | | Nicknames, titles, pen names |
| 3 | `gender` | Gender | select: Male/Female/Non-binary/Other/Unknown | | |
| 4 | `role` | Role | select: Protagonist/Antagonist/Love Interest/Supporting/Minor/Mentioned | | Added "Love Interest" |
| 5 | `occupation` | Occupation | text | | Job, profession, social role — key for romance/drama |
| 6 | `social_class` | Social Class | select: Royalty/Nobility/Upper Class/Middle Class/Working Class/Lower Class/Outcast/Other | | Essential for romance/historical |
| 7 | `affiliation` | Affiliation / Faction | text | | Group, sect, family, organization |
| 8 | `appearance` | Appearance | textarea | | Physical description |
| 9 | `personality` | Personality | textarea | | Traits, temperament, motivations |
| 10 | `emotional_wound` | Emotional Wound / Backstory | textarea | | Core fear or trauma shaping behavior — critical for romance arcs |
| 11 | `love_language` | Love Language | select: Words of Affirmation/Acts of Service/Receiving Gifts/Quality Time/Physical Touch/Unknown | | Romance-specific; hide if not needed |
| 12 | `relationships` | Key Relationships | textarea | | Connections to other characters |
| 13 | `description` | Description | textarea | | General notes |

### Location (`location`, 📍, #f59e0b) — `genre_tags: ["universal"]`

| Code | Name | Type | Required |
|---|---|---|---|
| `name` | Name | text | ✓ |
| `aliases` | Aliases | tags | |
| `type` | Location Type | select: City/Region/Building/Realm/Dimension/Landmark/Workplace/Home/Other | |
| `parent_location` | Parent Location | text | |
| `atmosphere` | Atmosphere / Mood | textarea | Emotional tone — important for romance settings |
| `description` | Description | textarea | |
| `significance` | Significance | textarea | |

### Item / Prop (`item`, 🎁, #ef4444) — `genre_tags: ["universal"]`

> Renamed "Item / Prop" to cover romance/drama props (love letters, gifts, heirlooms) as well as fantasy weapons.

| Code | Name | Type | Required |
|---|---|---|---|
| `name` | Name | text | ✓ |
| `aliases` | Aliases | tags | |
| `type` | Type | select: Weapon/Armor/Tool/Consumable/Treasure/Document/Gift/Memento/Heirloom/Other | |
| `owner` | Owner / Holder | text | |
| `symbolic_meaning` | Symbolic Meaning | textarea | What it represents emotionally or thematically |
| `description` | Description | textarea | |

### Event (`event`, 📅, #10b981) — `genre_tags: ["universal"]`

| Code | Name | Type | Required |
|---|---|---|---|
| `name` | Name | text | ✓ |
| `type` | Event Type | select: Battle/Ceremony/Disaster/Discovery/First Meeting/Breakup/Reconciliation/Confession/Betrayal/Political/Other | |
| `date_in_story` | Date (In-Story) | text | |
| `location` | Location | text | |
| `participants` | Participants | textarea | |
| `emotional_impact` | Emotional Impact | textarea | How this event affects characters emotionally |
| `outcome` | Outcome | textarea | |
| `description` | Description | textarea | |

### Terminology (`terminology`, 📖, #f97316) — `genre_tags: ["universal"]`

| Code | Name | Type | Required |
|---|---|---|---|
| `term` | Term | text | ✓ |
| `category` | Category | select: Cultural/Technical/Magical/Political/Religious/Social/Emotional/Other | |
| `definition` | Definition | textarea | ✓ |
| `usage_note` | Usage Notes | textarea | |

---

### Group B — Fantasy Kinds

### Power System (`power_system`, ✨, #a855f7) — `genre_tags: ["fantasy"]`

| Code | Name | Type | Required |
|---|---|---|---|
| `name` | Name | text | ✓ |
| `aliases` | Aliases | tags | |
| `type` | Category | select: Martial Art/Spell/Skill/Passive/Bloodline/Other | |
| `rank` | Rank / Tier | text | |
| `user` | Known Users | text | |
| `effects` | Effects | textarea | |
| `description` | Description | textarea | |

### Organization (`organization`, 🏛, #0ea5e9) — `genre_tags: ["fantasy", "drama"]`

| Code | Name | Type | Required |
|---|---|---|---|
| `name` | Name | text | ✓ |
| `aliases` | Aliases | tags | |
| `type` | Type | select: Sect/Kingdom/Company/Guild/Family/Military/School/Corporation/Other | |
| `leader` | Leader | text | |
| `headquarters` | Headquarters | text | |
| `members` | Notable Members | textarea | |
| `description` | Description | textarea | |

### Species / Race (`species`, 🧬, #ec4899) — `genre_tags: ["fantasy"]`

| Code | Name | Type | Required |
|---|---|---|---|
| `name` | Name | text | ✓ |
| `aliases` | Aliases | tags | |
| `traits` | Physical Traits | textarea | |
| `abilities` | Innate Abilities | textarea | |
| `habitat` | Habitat | text | |
| `culture` | Culture | textarea | |
| `description` | Description | textarea | |

---

### Group C — Romance / Drama Kinds

### Relationship (`relationship`, 💕, #e879f9) — `genre_tags: ["romance", "drama"]`

> Tracks the dynamic between two or more characters: its type, status, evolving tension, and applicable tropes. This is the backbone of romance novels.

| # | Code | Name | Type | Required | Notes |
|---|---|---|---|---|---|
| 1 | `name` | Relationship Label | text | ✓ | e.g., "Lin Mo & Yun Ji — Main Romance Arc" |
| 2 | `parties` | Parties Involved | tags | | Character names in this relationship |
| 3 | `relationship_type` | Type | select: Romantic/Friendship/Family/Rivalry/Mentor-Student/Unrequited/Professional/Other | | |
| 4 | `status` | Status | select: Developing/Established/Strained/Broken/Complicated/Resolved/Ended | | |
| 5 | `tropes` | Story Tropes | tags | | enemies-to-lovers, slow-burn, second-chance, fake-dating, forced-proximity, etc. |
| 6 | `dynamic` | Relationship Dynamic | textarea | | Power balance, chemistry, tension, how they interact |
| 7 | `key_conflict` | Key Conflict | textarea | | Primary obstacle to this relationship |
| 8 | `turning_points` | Turning Points | textarea | | Key moments that shifted the relationship |
| 9 | `resolution` | Resolution / Ending | textarea | | HEA / HFN / tragic / open |
| 10 | `description` | Description | textarea | | |

### Plot Arc (`plot_arc`, 📈, #f43f5e) — `genre_tags: ["romance", "drama"]`

> Tracks a narrative arc or subplot — especially the emotional beats of a romance or drama story.

| # | Code | Name | Type | Required | Notes |
|---|---|---|---|---|---|
| 1 | `name` | Arc Name | text | ✓ | |
| 2 | `arc_type` | Arc Type | select: Main Romance Arc/Subplot Romance/Family Drama/Internal Conflict/External Obstacle/Social Pressure/Redemption Arc/Coming-of-Age/Revenge/Mystery/Other | | |
| 3 | `parties` | Key Characters | tags | | Who is central to this arc |
| 4 | `trigger` | Trigger / Inciting Incident | textarea | | What started this arc |
| 5 | `stakes` | Stakes | textarea | | What is at risk if arc fails |
| 6 | `chapters_span` | Chapter Span | text | | e.g., "Ch.1–15", "Ch.20–end" |
| 7 | `emotional_beats` | Key Emotional Beats | textarea | | Meet-cute → tension → dark moment → breakthrough → resolution |
| 8 | `resolution` | Resolution | textarea | | |
| 9 | `description` | Description | textarea | | |

### Trope (`trope`, 🎭, #7c3aed) — `genre_tags: ["romance", "drama"]`

> Documents the narrative tropes used in the story — how they are employed and whether they are subverted.

| # | Code | Name | Type | Required | Notes |
|---|---|---|---|---|---|
| 1 | `name` | Trope Name | text | ✓ | e.g., "Enemies to Lovers", "Second Chance Romance" |
| 2 | `category` | Category | select: Romance Trope/Character Trope/Plot Trope/Setting Trope/Family Trope/Other | | |
| 3 | `definition` | Definition | textarea | ✓ | Standard meaning of this trope |
| 4 | `how_manifested` | How It Manifests | textarea | | How this specific novel uses the trope |
| 5 | `subverted` | Subverted? | select: No — Played Straight/Yes — Fully Subverted/Partially Subverted | | |
| 6 | `related_characters` | Related Characters | tags | | Who embodies or triggers this trope |
| 7 | `usage_note` | Notes | textarea | | |

### Social Setting (`social_setting`, 🏫, #0891b2) — `genre_tags: ["romance", "drama", "historical"]`

> The social environment, class system, and norms that create constraints and conflict for characters — especially in romance and historical drama.

| # | Code | Name | Type | Required | Notes |
|---|---|---|---|---|---|
| 1 | `name` | Setting Name | text | ✓ | e.g., "1920s Shanghai High Society", "Contemporary Corporate World" |
| 2 | `era` | Era / Time Period | select: Contemporary/Historical — Ancient/Historical — Imperial/Historical — Regency/Historical — Victorian/Historical — 20th Century/Future/Fantasy/Other | | |
| 3 | `location` | Geographic Setting | text | | Country, city, region |
| 4 | `class_hierarchy` | Class / Hierarchy System | textarea | | Social strata, power structure |
| 5 | `rules_norms` | Social Rules & Norms | textarea | | Expectations, taboos, what is forbidden or required |
| 6 | `romance_obstacles` | Romance Obstacles | textarea | | How this setting creates barriers to love (class gaps, family pressure, societal taboos) |
| 7 | `significance` | Plot Significance | textarea | | Why this setting matters to the story's conflict |
| 8 | `description` | Description | textarea | | |

---

## 8) Open Questions

| # | Question | Owner | Status |
| --- | --- | --- | --- |
| OQ-1 | Pagination strategy: offset-based (simpler) vs cursor-based (better for large glossaries)? Default: offset-based for MVP | SA | Open |
| OQ-2 | When entity is deleted, should evidences pointing to that entity's chapter be soft-deleted or hard-deleted? Default: hard-delete cascade | SA + PM | Open |
| OQ-3 | Should `GET entities` return full attribute values or only the `display_name`? Default: list returns summary (display_name + counts), detail returns full | SA + FE lead | Open |
| OQ-4 | Auto-suggest chapter link when evidence references an unlinked chapter — server-side hint or client-side only? | FE lead | Open |
| OQ-5 | RAG export: include `draft` entities or only `active`? Default: only `active` | PM | Open |
| OQ-6 | Should `genre_tags` be exposed in `GET /v1/glossary/kinds` response so frontend can group kinds by genre? Default: yes | FE lead | Open |

---

## 9) Genre Profile Architecture — Forward Design (Out of Scope for MVP)

> **This section is informational only.** Genre Profile feature is explicitly out of scope for Module 05. However, the `genre_tags` field on `entity_kinds` is included in the MVP DB schema as a foundation. This section documents the intended future architecture so that the current data model does not block it.

### Concept

A **Genre Profile** is a named preset that controls:
1. Which entity kinds are visible/suggested for a book.
2. Which attributes within each kind are visible by default.
3. Which kinds appear in the "New Entity" picker.

When a user (or admin) assigns a genre profile to a book, the glossary UI automatically shows the most relevant kinds and hides the rest — reducing noise. A fantasy author sees Power System, Species, Organization prominently; a romance author sees Relationship, Plot Arc, Trope, Social Setting instead.

### Proposed Future Data Model

```
GenreProfile {
  profile_id:        UUID
  code:              string         "romance" | "fantasy_xianxia" | "drama" | "mystery" | "historical_romance" | ...
  name:              string         "Romance / Love Story"
  description:       string?
  is_system_default: bool           true = admin-managed; false = user-created
  is_hidden:         bool
  sort_order:        int
  created_by:        "system" | user_id

  kind_configs: KindConfig[]
}

KindConfig {
  kind_code:                string     references entity_kinds.code
  is_visible:               bool       show this kind in the picker for this genre
  is_recommended:           bool       highlight as "recommended for this genre"
  visible_attribute_codes:  string[]   which attributes are shown by default
  required_attribute_codes: string[]   which attributes are required for this genre
}
```

### Admin vs User Genre Profiles

| Type | Created by | Editable by | Visible to |
|---|---|---|---|
| System default | Admin (platform) | Admin only | All users |
| User custom | Any user | Creator only | Creator only |

Admin configures system defaults via a dedicated admin UI (separate from glossary module). Users can create custom profiles but cannot modify system defaults.

### UI Flow (future)

1. When creating a book (or in book settings), user picks a **Genre** from a list.
2. The selected Genre Profile is applied: glossary kind picker shows recommended kinds first; others hidden by default but accessible via "Show all kinds".
3. Character attributes auto-show the genre-relevant subset (e.g., romance profile shows `occupation`, `social_class`, `emotional_wound`, `love_language` by default; fantasy profile shows `affiliation`, `cultivation_level`).

### MVP Bridge

In MVP, `genre_tags` is stored on each kind but not used by the API or UI. When Genre Profile feature is built, the migration is:
1. Add `genre_profiles` + `genre_kind_configs` tables.
2. Add `genre_profile_id` to `books` table (in book-service).
3. `GET /v1/glossary/books/{id}/entities` and kinds list accept optional `genre_profile_id` filter.
4. No existing data migration needed — `genre_tags` on kinds already categorizes them correctly.
