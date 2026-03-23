# LoreWeave Module 05 — Genre Profile Architecture ADR

## Document Metadata

- Document ID: LW-M05-87
- Version: 0.1.0
- Status: Approved (Informational — feature is OUT OF SCOPE for Module 05)
- Owner: Solution Architect + Product Manager
- Last Updated: 2026-03-23
- Approved By: —
- Summary: Architecture Decision Record for the Genre Profile feature — a configurable system that lets admin or users define genre presets controlling which glossary entity kinds and attributes are visible for a book. This feature is intentionally deferred from Module 05 but the data model foundation is included in the MVP.

## Change History

| Version | Date       | Change                              | Author    |
| ------- | ---------- | ----------------------------------- | --------- |
| 0.1.0   | 2026-03-23 | Initial Genre Profile ADR           | Assistant |

---

## 1) Context & Problem

The Module 05 glossary system ships with **12 default entity kinds** across 3 genre groups:

| Group | Kinds |
|---|---|
| Universal | Character, Location, Item/Prop, Event, Terminology |
| Fantasy | Power System, Organization, Species |
| Romance / Drama | Relationship, Plot Arc, Trope, Social Setting |

**Problem:** Without genre filtering, all 12 kinds appear in the "New Entity" picker for every user regardless of their novel's genre. A romance author sees Power System and Species; a xianxia fantasy author sees Relationship and Plot Arc. This creates noise and reduces perceived relevance.

**Goal:** Allow the glossary to present only the most relevant kinds for a book's genre — auto-suggested on book creation, configurable later.

---

## 2) Decision

**Decision**: Defer Genre Profile feature to a later module (Phase 3 wave 2 or Phase 4). In the Module 05 MVP:

1. Store `genre_tags TEXT[]` on `entity_kinds` (already in the MVP schema).
2. Return `genre_tags` in `GET /v1/glossary/kinds` response.
3. Frontend can optionally **group** kinds by genre in the kind picker (cosmetic grouping, no filtering).
4. No `GenreProfile` DB tables, no book-to-genre assignment API, no kind filtering logic in MVP.

**Rationale:**
- Genre Profile involves book-service schema changes (add `genre_profile_id` to books), a new admin UI, and user-facing book settings flow — these exceed the Module 05 scope boundary.
- Storing `genre_tags` now costs nothing and prevents a future data migration.
- Visual grouping in the kind picker (Group A / Group B / Group C) provides immediate UX benefit without the backend complexity.

---

## 3) Genre Profile — Full Architecture (for future module)

### 3.1 Core Concept

A `GenreProfile` is a named preset tied to a book that controls:
- Which entity kinds appear in the kind picker (visible vs hidden).
- Which kinds are "recommended" (surfaced prominently).
- Per-kind: which attributes are visible by default, which are required.

### 3.2 Data Model

```
genre_profiles
  profile_id         UUID PK
  code               TEXT UNIQUE       "romance" | "fantasy_xianxia" | "drama" | "historical_romance" | ...
  name               TEXT              "Romance / Love Story"
  description        TEXT?
  is_system_default  BOOL              true = admin-managed platform default
  is_hidden          BOOL              hidden from picker
  sort_order         INT
  created_by         TEXT              "system" | user_id
  created_at         TIMESTAMPTZ

genre_kind_configs
  config_id          UUID PK
  profile_id         UUID FK → genre_profiles
  kind_code          TEXT              references entity_kinds.code
  is_visible         BOOL              show this kind for this genre
  is_recommended     BOOL              surface as top-pick in kind picker
  visible_attr_codes TEXT[]            override default attribute visibility
  required_attr_codes TEXT[]           override required attributes

-- In book-service (separate migration):
books (existing table)
  + genre_profile_id  UUID? FK → genre_profiles
```

### 3.3 Proposed System Default Genre Profiles

| Code | Name | Recommended kinds | Hidden kinds |
|---|---|---|---|
| `fantasy_cultivation` | Fantasy / Xianxia | Character, Location, Power System, Organization, Species, Item, Terminology | Relationship, Plot Arc, Trope, Social Setting |
| `romance_contemporary` | Romance — Contemporary | Character, Relationship, Plot Arc, Trope, Social Setting, Location, Event | Power System, Species |
| `romance_historical` | Romance — Historical | Character, Relationship, Plot Arc, Social Setting, Event, Organization, Location | Power System, Species |
| `drama_family` | Family Drama | Character, Relationship, Plot Arc, Organization, Event, Location | Power System, Species, Trope |
| `general` | General Fiction | Character, Location, Event, Terminology, Item | Power System, Species (hidden by default, can be shown) |

### 3.4 Character Attributes Per Genre Profile

The `genre_kind_configs.visible_attr_codes` for Character kind:

| Genre Profile | Visible attributes (default) | Hidden by default |
|---|---|---|
| `fantasy_cultivation` | name, aliases, gender, role, affiliation, appearance, personality, relationships, description | occupation, social_class, emotional_wound, love_language |
| `romance_contemporary` | name, aliases, gender, role, occupation, social_class, appearance, personality, emotional_wound, love_language, relationships, description | affiliation |
| `romance_historical` | name, aliases, gender, role, occupation, social_class, appearance, personality, emotional_wound, relationships, description | love_language, affiliation |
| `drama_family` | name, aliases, gender, role, occupation, social_class, appearance, personality, emotional_wound, relationships, description | love_language, affiliation |
| `general` | name, aliases, gender, role, appearance, personality, description | occupation, social_class, emotional_wound, love_language, affiliation |

### 3.5 Admin vs User Profiles

| Level | Created by | UI | Can edit | Can delete | Visible to |
|---|---|---|---|---|---|
| System default | Admin | Admin panel (separate feature) | Admin only | Admin only (if no books use it) | All users |
| User custom | Any user | Book settings page | Creator | Creator | Creator only |

**Admin UI** — a separate admin panel route (`/admin/genre-profiles`) for:
- Creating, editing, hiding system defaults.
- Configuring kind visibility and attribute overrides per kind per profile.
- Drag-and-drop reorder (controls sort order in book creation picker).

**User custom profiles** — accessible from book settings:
- User can fork an existing system default and customize it.
- User can create from scratch.
- Custom profiles only apply to books the user owns.

### 3.6 UX Flow (Future)

**Book creation:**
```
Create Book
  ├── Title, language, description (existing)
  └── Genre (optional, can skip)
      ├── [Fantasy / Xianxia]
      ├── [Romance — Contemporary]
      ├── [Romance — Historical]
      ├── [Family Drama]
      ├── [General Fiction]
      └── [Skip — show all kinds]
```

**Glossary page with genre applied:**
- Kind picker shows only recommended kinds prominently.
- "Show all kinds" link reveals hidden kinds.
- Filter bar shows only relevant kinds.
- Character attribute rows default to genre-relevant subset; other attrs accessible via "Show more fields".

### 3.7 API Surface (Future)

```
GET  /v1/glossary/genre-profiles               — list all available profiles
POST /v1/glossary/genre-profiles               — create user custom profile
GET  /v1/glossary/genre-profiles/{profile_id}  — get profile detail + kind configs
PUT  /v1/glossary/genre-profiles/{profile_id}  — update custom profile (owner only)
DEL  /v1/glossary/genre-profiles/{profile_id}  — delete custom profile (owner, 0 books using it)

-- Within existing endpoints (new optional param):
GET  /v1/glossary/kinds?genre_profile_id={id}  — filtered/sorted kinds for a genre
GET  /v1/glossary/books/{id}/entities          — respects kind visibility from book's genre profile
```

### 3.8 Migration Path from MVP

No data migration needed. The `genre_tags` column already categorizes all 12 kinds. When Genre Profile is built:

1. Add `genre_profiles` + `genre_kind_configs` tables to `loreweave_glossary` DB.
2. Seed default genre profiles referencing existing `entity_kinds.code` values.
3. Add `genre_profile_id UUID?` to `books` table in `book-service` (nullable — no breaking change).
4. `GET /v1/glossary/kinds` gains optional `genre_profile_id` query param; existing callers unaffected (no param = return all kinds as before).

---

## 4) Consequences

**Positive:**
- Romance/drama authors get a relevant, uncluttered glossary from day one.
- Fantasy authors are not confused by Relationship and Trope kinds.
- Admin can add new system default genres without code changes.
- Users can tailor their own genre presets for niche novel types.

**Negative / Risks:**
- Adds complexity to the glossary architecture (another entity, another config system).
- Admin UI is a separate feature with its own design and governance needs.
- Per-kind attribute visibility overrides may conflict with user's manual attribute show/hide settings — needs conflict resolution policy (user's manual setting overrides genre default).

**Decision deferred until:** Phase 3 wave 2 or Phase 4, after Module 05 MVP is validated with real users.

---

## 5) Open Questions for Future Module

| # | Question | Notes |
|---|---|---|
| Q-1 | Can a single book have multiple genre profiles (e.g., "fantasy romance")? Or one only? | Simpler to allow one; "multi-genre" via a combined preset |
| Q-2 | If user changes genre profile on an existing book, what happens to entities of now-hidden kinds? | They remain in DB but are hidden from picker and filter; user can reveal via "Show all kinds" |
| Q-3 | Should system default profiles be version-controlled and upgradable (e.g., new attribute added to profile v2)? | Yes — need versioning strategy to not override user customizations |
| Q-4 | User custom profiles: can they be shared with other users? | Out of scope for first wave; possible future "shared templates" feature |
