# LoreWeave Module 05 Backend Detailed Design

## Document Metadata

- Document ID: LW-M05-82
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect + BE Lead
- Last Updated: 2026-03-23
- Approved By: Decision Authority
- Approved Date: 2026-03-24
- Summary: Detailed backend design for glossary-service including domain model, DB schema, seeded kind data, service logic, handler behavior, and failure handling.

## Change History

| Version | Date | Change | Author |
| ------- | ---------- | ----------------------------------------- | --------- |
| 0.2.0   | 2026-03-23 | Add `genre_tags` column to `entity_kinds`; expand seed to 12 kinds (4 romance/drama + updated Character attrs) | Assistant |
| 0.1.0   | 2026-03-23 | Initial Module 05 backend detailed design | Assistant |

---

## 1) Domain Model

### Kind Domain (seed data, read-only in MVP)
- `EntityKind` — one of 8 system defaults with identity and attribute schema
- `AttributeDefinition` — per-kind attribute field definition (code, name, type, required, sort_order)

### Entity Domain
- `GlossaryEntity` — book-level lore object (not chapter-owned)
- `EntityAttributeValue` — one row per entity per attribute definition; holds original language + value
- `ChapterLink` — M:N join between entity and chapter (with relevance + note)

### Translation & Evidence Domain
- `Translation` — target-language translation for one attribute value
- `Evidence` — source quote/summary/reference for one attribute value
- `EvidenceTranslation` — translation of one evidence text

---

## 2) Database Schema

### `entity_kinds`

```sql
CREATE TABLE IF NOT EXISTS entity_kinds (
  kind_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code         TEXT NOT NULL UNIQUE,
  name         TEXT NOT NULL,
  description  TEXT,
  icon         TEXT NOT NULL,
  color        TEXT NOT NULL DEFAULT '#6366f1',
  is_default   BOOLEAN NOT NULL DEFAULT true,
  is_hidden    BOOLEAN NOT NULL DEFAULT false,
  sort_order   INT NOT NULL DEFAULT 0,
  genre_tags   TEXT[] NOT NULL DEFAULT '{universal}',  -- ["universal"] | ["fantasy"] | ["romance","drama"] etc.
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `attribute_definitions`

```sql
CREATE TABLE IF NOT EXISTS attribute_definitions (
  attr_def_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind_id      UUID NOT NULL REFERENCES entity_kinds(kind_id) ON DELETE CASCADE,
  code         TEXT NOT NULL,
  name         TEXT NOT NULL,
  description  TEXT,
  field_type   TEXT NOT NULL DEFAULT 'text',
  is_required  BOOLEAN NOT NULL DEFAULT false,
  sort_order   INT NOT NULL DEFAULT 0,
  options      TEXT[],                -- for select type
  UNIQUE(kind_id, code)
);
CREATE INDEX IF NOT EXISTS idx_attr_def_kind ON attribute_definitions(kind_id);
```

### `glossary_entities`

```sql
CREATE TABLE IF NOT EXISTS glossary_entities (
  entity_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id      UUID NOT NULL,
  kind_id      UUID NOT NULL REFERENCES entity_kinds(kind_id),
  status       TEXT NOT NULL DEFAULT 'draft',   -- active | inactive | draft
  tags         TEXT[] NOT NULL DEFAULT '{}',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ge_book ON glossary_entities(book_id);
CREATE INDEX IF NOT EXISTS idx_ge_book_kind ON glossary_entities(book_id, kind_id);
CREATE INDEX IF NOT EXISTS idx_ge_book_status ON glossary_entities(book_id, status);
CREATE INDEX IF NOT EXISTS idx_ge_book_updated ON glossary_entities(book_id, updated_at DESC);
```

### `chapter_entity_links`

```sql
CREATE TABLE IF NOT EXISTS chapter_entity_links (
  link_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id      UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  chapter_id     UUID NOT NULL,
  chapter_title  TEXT,                         -- denormalized for display
  chapter_index  INT,                          -- denormalized for ordering
  relevance      TEXT NOT NULL DEFAULT 'appears',   -- major | appears | mentioned
  note           TEXT,
  added_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(entity_id, chapter_id)
);
CREATE INDEX IF NOT EXISTS idx_cel_entity ON chapter_entity_links(entity_id);
CREATE INDEX IF NOT EXISTS idx_cel_chapter ON chapter_entity_links(chapter_id);
```

### `entity_attribute_values`

```sql
CREATE TABLE IF NOT EXISTS entity_attribute_values (
  attr_value_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id          UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  attr_def_id        UUID NOT NULL REFERENCES attribute_definitions(attr_def_id),
  original_language  TEXT NOT NULL DEFAULT 'zh',
  original_value     TEXT NOT NULL DEFAULT '',
  UNIQUE(entity_id, attr_def_id)
);
CREATE INDEX IF NOT EXISTS idx_eav_entity ON entity_attribute_values(entity_id);
```

### `attribute_translations`

```sql
CREATE TABLE IF NOT EXISTS attribute_translations (
  translation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  attr_value_id  UUID NOT NULL REFERENCES entity_attribute_values(attr_value_id) ON DELETE CASCADE,
  language_code  TEXT NOT NULL,
  value          TEXT NOT NULL DEFAULT '',
  confidence     TEXT NOT NULL DEFAULT 'draft',   -- verified | draft | machine
  translator     TEXT,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(attr_value_id, language_code)
);
CREATE INDEX IF NOT EXISTS idx_at_attr_value ON attribute_translations(attr_value_id);
```

### `evidences`

```sql
CREATE TABLE IF NOT EXISTS evidences (
  evidence_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  attr_value_id     UUID NOT NULL REFERENCES entity_attribute_values(attr_value_id) ON DELETE CASCADE,
  chapter_id        UUID,
  chapter_title     TEXT,                          -- denormalized
  block_or_line     TEXT NOT NULL DEFAULT '',
  evidence_type     TEXT NOT NULL DEFAULT 'quote', -- quote | summary | reference
  original_language TEXT NOT NULL DEFAULT 'zh',
  original_text     TEXT NOT NULL DEFAULT '',
  note              TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ev_attr_value ON evidences(attr_value_id);
CREATE INDEX IF NOT EXISTS idx_ev_chapter ON evidences(chapter_id);
```

### `evidence_translations`

```sql
CREATE TABLE IF NOT EXISTS evidence_translations (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  evidence_id   UUID NOT NULL REFERENCES evidences(evidence_id) ON DELETE CASCADE,
  language_code TEXT NOT NULL,
  value         TEXT NOT NULL DEFAULT '',
  confidence    TEXT NOT NULL DEFAULT 'draft',
  UNIQUE(evidence_id, language_code)
);
CREATE INDEX IF NOT EXISTS idx_evtr_evidence ON evidence_translations(evidence_id);
```

---

## 3) Startup Seed Data

On service startup, if `entity_kinds` table is empty, seed the **12 default kinds** and their attribute definitions. Seed is idempotent (check by `code` before inserting).

**Group A — Universal**

| # | Code | Name | Icon | Color | genre_tags | Required Attrs |
|---|---|---|---|---|---|---|
| 1 | `character` | Character | 👤 | #6366f1 | `{universal}` | `name` |
| 2 | `location` | Location | 📍 | #f59e0b | `{universal}` | `name` |
| 3 | `item` | Item / Prop | 🎁 | #ef4444 | `{universal}` | `name` |
| 4 | `event` | Event | 📅 | #10b981 | `{universal}` | `name` |
| 5 | `terminology` | Terminology | 📖 | #f97316 | `{universal}` | `term,definition` |

**Group B — Fantasy**

| # | Code | Name | Icon | Color | genre_tags | Required Attrs |
|---|---|---|---|---|---|---|
| 6 | `power_system` | Power System | ✨ | #a855f7 | `{fantasy}` | `name` |
| 7 | `organization` | Organization | 🏛 | #0ea5e9 | `{fantasy,drama}` | `name` |
| 8 | `species` | Species | 🧬 | #ec4899 | `{fantasy}` | `name` |

**Group C — Romance / Drama**

| # | Code | Name | Icon | Color | genre_tags | Required Attrs |
|---|---|---|---|---|---|---|
| 9 | `relationship` | Relationship | 💕 | #e879f9 | `{romance,drama}` | `name` |
| 10 | `plot_arc` | Plot Arc | 📈 | #f43f5e | `{romance,drama}` | `name` |
| 11 | `trope` | Trope | 🎭 | #7c3aed | `{romance,drama}` | `name,definition` |
| 12 | `social_setting` | Social Setting | 🏫 | #0891b2 | `{romance,drama,historical}` | `name` |

> Full attribute definitions per kind (all 12) are defined in `domain/kinds.go` as constant structs. See `76_MODULE05_API_CONTRACT_DRAFT.md` §7 for the complete attribute list per kind.
| `terminology` | Terminology | 📖 | #f97316 | `term`, `definition` |
| `species` | Species | 🧬 | #ec4899 | `name` |

Full attribute definitions per kind defined in `domain/kinds.go` as constant structs.

---

## 4) Service Logic

### 4.1 Create Entity (`entity_service.CreateEntity`)

1. Validate `book_id` exists and requester is owner via `book_client.GetProjection(book_id)`.
2. Validate `kind_id` exists in `entity_kinds`.
3. `INSERT` into `glossary_entities` with `status=draft`.
4. Load `attribute_definitions` for the kind (ordered by `sort_order`).
5. Batch `INSERT` into `entity_attribute_values` — one row per attribute definition with `original_value=''`.
6. Return created entity with full attribute values embedded.

### 4.2 List Entities with Filter (`entity_repo.ListEntities`)

Dynamic query builder:
```
SELECT e.*, ... FROM glossary_entities e
  LEFT JOIN chapter_entity_links cel ON cel.entity_id = e.entity_id
WHERE e.book_id = $1
  [AND e.kind_id = ANY($kindIds)]
  [AND e.status = $status]
  [AND cel.chapter_id = ANY($chapterIds)] OR [e not in any link]  -- for unlinked
  [AND e.tags @> $tags]
  [AND ... ILIKE %search%]  -- applied to name attr value
ORDER BY [sort field]
LIMIT $limit OFFSET $offset
```

- `display_name` resolved by joining `entity_attribute_values` where `attr_def.code IN ('name', 'term')`.
- Counts (`chapter_link_count`, `translation_count`, `evidence_count`) computed as subquery aggregates.

### 4.3 Delete Entity (`entity_service.DeleteEntity`)

- Postgres FK `ON DELETE CASCADE` handles attribute values → translations, evidences → evidence_translations, chapter_entity_links.
- Single `DELETE FROM glossary_entities WHERE entity_id = $1 AND book_id = $2` is sufficient.
- Service verifies ownership before delete.

### 4.4 RAG Export (`export_service.BuildExport`)

1. `SELECT` all active entities for `book_id`.
2. For each entity, load: kind, chapter_links, attribute_values (with translations + evidences + evidence_translations).
3. Assemble JSON per `76` §5 export schema.
4. If `chapter_id` query param provided: filter to entities where `chapter_entity_links` contains that `chapter_id`.

---

## 5) Handler Behavior

### POST `/v1/glossary/books/{book_id}/entities`

- Auth: Bearer required.
- Ownership: verify book owner via book-service.
- Body: `{ "kind_id": "uuid" }`.
- Returns: `201 Created` with full entity detail.
- Errors: `GLOSS_BOOK_NOT_FOUND`, `GLOSS_FORBIDDEN`, `GLOSS_KIND_NOT_FOUND`.

### GET `/v1/glossary/books/{book_id}/entities`

- Auth: Bearer required.
- Ownership: verify book owner.
- Returns: `200` with `{ items: GlossaryEntitySummary[], total: int, limit: int, offset: int }`.
- Errors: `GLOSS_BOOK_NOT_FOUND`, `GLOSS_FORBIDDEN`.

### DELETE `/v1/glossary/books/{book_id}/entities/{entity_id}`

- Auth: Bearer required.
- Ownership: verify book owner.
- Returns: `204 No Content`.
- Cascade: all related rows deleted by DB FK cascade.

### POST `.../chapter-links`

- Body: `{ "chapter_id": "uuid", "relevance": "major|appears|mentioned", "note": "?" }`.
- Validates: chapter belongs to the book via `book_client.GetChapters(book_id)`.
- Errors: `GLOSS_DUPLICATE_CHAPTER_LINK`, `GLOSS_CHAPTER_NOT_IN_BOOK`.

### POST `.../translations`

- Body: `{ "language_code": "en", "value": "...", "confidence": "draft", "translator": "?" }`.
- Validates: language not already in `attribute_translations` for this `attr_value_id`.
- Errors: `GLOSS_DUPLICATE_TRANSLATION_LANGUAGE`.

---

## 6) Authentication Middleware

Reuse same JWT verification pattern as other Go services:
- Extract `Authorization: Bearer <token>`.
- Verify JWT signature with `JWT_SECRET`.
- Extract `sub` (user_id) from claims.
- Attach `user_id` to request context.

---

## 7) book-service Client

```go
// GetProjection returns book_id + owner_user_id
func (c *BookClient) GetProjection(ctx context.Context, bookID string) (*BookProjection, error)

// GetChapters returns chapter_id list for a book
func (c *BookClient) GetChapters(ctx context.Context, bookID string) ([]ChapterSummary, error)
```

Both use `GET /internal/books/{book_id}/...` — no auth header required on internal routes.

Timeout: 5s per call. Cache `GetChapters` per request (not across requests) to avoid duplicate calls within a single handler.

---

## 8) Failure Handling

| Failure | Behavior |
| --- | --- |
| book-service unreachable on entity create/mutate | Return 503 with `GLOSS_UPSTREAM_UNAVAILABLE` |
| book-service returns 404 for book | Return 404 `GLOSS_BOOK_NOT_FOUND` |
| book-service returns 403 (requester not owner) | Return 403 `GLOSS_FORBIDDEN` |
| DB unique constraint violation on chapter link | Return 409 `GLOSS_DUPLICATE_CHAPTER_LINK` |
| DB unique constraint violation on translation language | Return 409 `GLOSS_DUPLICATE_TRANSLATION_LANGUAGE` |
| entity_id not found for mutation | Return 404 `GLOSS_NOT_FOUND` |
| invalid kind_id on create | Return 404 `GLOSS_KIND_NOT_FOUND` |
