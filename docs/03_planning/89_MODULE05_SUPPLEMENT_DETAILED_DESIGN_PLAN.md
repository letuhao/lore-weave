# Module 05 Supplement — Detailed Design & Sub-Phase Plan (M05-S1)

## Document Metadata

- Document ID: LW-M05-89
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect + Tech Lead
- Last Updated: 2026-03-25
- Approved By: Decision Authority
- Approved Date: 2026-03-24
- Summary: Breaks M05-S1 (doc 88) into 7 sequenced sub-phases for implementation. Includes architecture decisions (ADR inline), DB schema additions, API contract sketches, and frontend component inventory per sub-phase. Each sub-phase is scoped to fit a single implementation session.

## Change History

| Version | Date       | Change              | Author    |
| ------- | ---------- | ------------------- | --------- |
| 0.1.0   | 2026-03-25 | Initial design plan | Assistant |

---

## 1) Why This Split

M05-S1 requirement (doc 88) spans 5 features across 3 tiers of kind scope, a new snapshot system, recycle bin extension, and bidirectional sync UI. Implementing this in one prompt would produce ~15 new DB tables, ~30 API endpoints, ~20 frontend components, and ~4 000 lines of code. That is too large a context window and too high a risk of inconsistency.

The 7 sub-phases follow natural dependency layers. Each leaves the system in a deployable, smoke-testable state.

---

## 2) Architecture Decisions (ADR Inline)

These decisions apply across all sub-phases. They are resolved here to prevent rework.

---

### ADR-S1: Polymorphic Kind Reference in `glossary_entities`

**Problem:** `glossary_entities.kind_id` currently has a hard FK to `entity_kinds` (T1). When T2/T3 kinds exist, an entity can belong to any tier.

**Options considered:**

| Option | Description | Verdict |
|---|---|---|
| A | Single column `kind_ref_id` (no FK) + `kind_source TEXT` | Loses referential integrity |
| B | Merge T1/T2/T3 into one `entity_kinds` table with `owner_type/owner_id` | Pollutes system table; complex permission guards |
| C | Separate nullable FK columns: `kind_id`, `user_kind_id`, `book_kind_id` + CHECK exactly-one-non-null | Preserves FK integrity; clear per-tier ownership |

**Decision: Option C.**

```sql
-- Migration on glossary_entities:
ALTER TABLE glossary_entities
  ADD COLUMN user_kind_id  UUID REFERENCES user_kinds(user_kind_id)  ON DELETE SET NULL,
  ADD COLUMN book_kind_id  UUID REFERENCES book_kinds(book_kind_id)  ON DELETE SET NULL,
  -- existing kind_id becomes nullable (was NOT NULL)
  ALTER COLUMN kind_id DROP NOT NULL,
  ADD CONSTRAINT ck_entity_exactly_one_kind CHECK (
    (kind_id IS NOT NULL)::int +
    (user_kind_id IS NOT NULL)::int +
    (book_kind_id IS NOT NULL)::int = 1
  );
```

**Helper function** `effective_kind_source(entity)` → returns `('system', kind_id)` | `('user', user_kind_id)` | `('book', book_kind_id)`. Used in queries and snapshot trigger.

---

### ADR-S2: Polymorphic Attribute Definition Reference in `entity_attribute_values`

**Problem:** `entity_attribute_values.attr_def_id` has a hard FK to `attribute_definitions` (T1). T2/T3 kinds have their own attribute definition tables.

**Decision:** Same pattern as ADR-S1 — three nullable FK columns.

```sql
ALTER TABLE entity_attribute_values
  ADD COLUMN user_attr_def_id  UUID REFERENCES user_kind_attributes(attr_id)  ON DELETE SET NULL,
  ADD COLUMN book_attr_def_id  UUID REFERENCES book_kind_attributes(attr_id)  ON DELETE SET NULL,
  ALTER COLUMN attr_def_id DROP NOT NULL,
  ADD CONSTRAINT ck_attrval_exactly_one_def CHECK (
    (attr_def_id IS NOT NULL)::int +
    (user_attr_def_id IS NOT NULL)::int +
    (book_attr_def_id IS NOT NULL)::int = 1
  );
```

**View `v_attr_def`** unifies T1/T2/T3 attribute definitions for read queries (snapshot trigger, export, detail panel):

```sql
CREATE OR REPLACE VIEW v_attr_def AS
  SELECT attr_def_id AS ref_id, 'system' AS source, kind_id AS kind_ref_id,
         code, name, field_type, is_required, sort_order, options
  FROM attribute_definitions WHERE deleted_at IS NULL
UNION ALL
  SELECT attr_id, 'user', user_kind_id,
         code, name, field_type, is_required, sort_order, options
  FROM user_kind_attributes WHERE deleted_at IS NULL
UNION ALL
  SELECT attr_id, 'book', book_kind_id,
         code, name, field_type, is_required, sort_order, options
  FROM book_kind_attributes WHERE deleted_at IS NULL;
```

---

### ADR-S3: Soft Delete Strategy

**Problem:** Current delete is hard/cascade. Recycle bin requires soft delete + no cascade.

**Decision:** Add `deleted_at TIMESTAMPTZ DEFAULT NULL` to each affected table. Queries filter `WHERE deleted_at IS NULL`. No cascade delete from kind → entities or attribute_def → attribute_values.

**Tables receiving `deleted_at`:**

| Table | Added in SS |
|---|---|
| `glossary_entities` | SS-2 |
| `user_kinds` | SS-4 |
| `book_kinds` | SS-5 |
| `user_kind_attributes` | SS-4 |
| `book_kind_attributes` | SS-5 |

T1 tables (`entity_kinds`, `attribute_definitions`) are system-managed and are NOT soft-deletable by users. They get no `deleted_at` column.

**Orphan display:** When `user_kind_id` or `book_kind_id` is deleted (deleted_at set), the entity still exists. Kind metadata for display comes from `entity_snapshot` (SS-1). Live queries fall back to snapshot when kind row has `deleted_at IS NOT NULL`.

---

### ADR-S4: Entity Snapshot Structure

**Decision:** `entity_snapshot JSONB` on `glossary_entities`, recomputed by PL/pgSQL trigger.

Snapshot schema (TypeScript-style for clarity):

```ts
interface EntitySnapshot {
  schema_version: "1.0";
  entity_id: string;
  book_id: string;
  kind: {
    source: "system" | "user" | "book";
    ref_id: string;
    code: string;
    name: string;
    icon: string;
    color: string;
  };
  status: string;
  tags: string[];
  attributes: Array<{
    attr_def_source: "system" | "user" | "book";
    attr_def_ref_id: string;
    attr_value_id: string;
    name: string;
    field_type: string;
    sort_order: number;
    original_language: string;
    original_value: string;
    translations: Array<{
      translation_id: string;
      language_code: string;
      value: string;
      confidence: string;
    }>;
    evidences: Array<{
      evidence_id: string;
      evidence_type: string;
      original_language: string;
      original_text: string;
      chapter_id: string | null;
      chapter_title: string | null;
      block_or_line: string;
      note: string | null;
    }>;
  }>;
  chapter_links: Array<{
    link_id: string;
    chapter_id: string;
    chapter_title: string;
    chapter_index: number;
    relevance: string;
    note: string | null;
  }>;
  updated_at: string;
  snapshot_at: string;
}
```

Trigger fires on INSERT/UPDATE/DELETE on: `entity_attribute_values`, `attribute_translations`, `evidences`, `chapter_entity_links`. Also fires on UPDATE of `glossary_entities` itself (status/tags).

---

### ADR-S5: Recycle Bin API Design

**Decision:** Single endpoint `GET /v1/recycle-bin` with `?category=` filter. Restore and permanent-delete as separate sub-endpoints. Recycle bin data is assembled from soft-deleted rows across multiple tables/services.

Since recycle bin spans multiple services (book-service, glossary-service), the **BFF layer** aggregates. Each service exposes its own recycle bin sub-endpoint:

- `GET /v1/glossary/recycle-bin` — glossary objects (entities, kinds, attributes)
- `GET /v1/books/recycle-bin` — books + chapters (existing/new)

BFF `GET /v1/recycle-bin` fans out and merges. UI calls BFF.

---

### ADR-S6: Glossary User Settings Storage

**Decision:** Extend existing `user_settings` pattern. If no dedicated settings table exists in a relevant service, create `glossary_user_preferences` table in `glossary-service` (same pattern as `user_translation_preferences` in translation-service).

```sql
CREATE TABLE IF NOT EXISTS glossary_user_preferences (
  user_id                         UUID PRIMARY KEY,
  default_chapter_link_relevance  TEXT NOT NULL DEFAULT 'mentioned',
  updated_at                      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Endpoint: `GET/PUT /v1/glossary/preferences` (mirrors translation-service pattern).

---

## 3) Sub-Phase Overview

| Sub-Phase | Name | Feature(s) | Size | Key deliverable |
|---|---|---|---|---|
| **SS-1** | Snapshot Foundation | D | M | `entity_snapshot` JSONB column, PL/pgSQL trigger, backfill, export refactor |
| **SS-2** | Soft Delete + Recycle Bin | C | M | `deleted_at` on glossary objects, recycle bin API, recycle bin UI extended |
| **SS-3** | Glossary Settings + Auto-suggest | E + A | S | Glossary preferences endpoint + settings UI section + auto-suggest toast |
| **SS-4** | T2 User Kind CRUD | B (tier 2) | L | `user_kinds` + `user_kind_attributes` tables, CRUD API, kind management page |
| **SS-5** | T3 Book Kind CRUD | B (tier 3) | M | `book_kinds` + `book_kind_attributes` tables, CRUD API, book kind management UI |
| **SS-6** | Kind Sync + Compare | B (sync) | L | Diff logic, sync apply API, `KindCompareModal` frontend component |
| **SS-7** | Kind Integration | B (wiring) | M | Entity create picker + filter bar shows T1+T2+T3, polymorphic kind ref migration |

**Dependency order:**

```
SS-1 (snapshot)
  └── SS-2 (soft delete — orphan display uses snapshot)
        └── SS-4 (user kinds — delete uses recycle bin)
              └── SS-5 (book kinds — same pattern as SS-4)
                    └── SS-6 (sync — needs both T2 and T3 to exist)
                          └── SS-7 (integration — wires all tiers into UI)

SS-3 (settings + toast)  ← independent after SS-1, can run in parallel with SS-4
```

---

## 4) SS-1 — Snapshot Foundation

### Goal

Add the `entity_snapshot` JSONB column to `glossary_entities`, implement the PL/pgSQL recalculation function and triggers, backfill all existing entities, and refactor `GET /export` to read from snapshot instead of 5-query join. No user-visible feature change — this is a pure infrastructure upgrade.

### Backend Deliverables

| Area | What to build |
|---|---|
| Migration | `ALTER TABLE glossary_entities ADD COLUMN entity_snapshot JSONB` |
| PL/pgSQL function | `recalculate_entity_snapshot(p_entity_id UUID)` — aggregates entity + kind + attrs + translations + evidences + chapter_links into JSON matching ADR-S4 schema |
| Triggers | `AFTER INSERT OR UPDATE OR DELETE` on `entity_attribute_values`, `attribute_translations`, `evidences`, `chapter_entity_links`; `AFTER UPDATE` on `glossary_entities` — each calls `recalculate_entity_snapshot(entity_id)` |
| Backfill | `SELECT recalculate_entity_snapshot(entity_id) FROM glossary_entities` run once in migration; idempotent |
| Export refactor | `internal/api/export_handler.go` — replace 5-query bulk join with single `SELECT entity_snapshot FROM glossary_entities WHERE book_id=$1 AND status='active' AND deleted_at IS NULL` |
| Tests | Unit: snapshot JSON structure (kind fields, attribute fields, evidence fields); trigger fires on sub-table change; backfill idempotency; export output unchanged after refactor |

### Frontend Deliverables

None. Export output is semantically identical.

### Key Risk

Trigger performance on books with many entities (large write amplification). Mitigate: benchmark with 500-entity book before SS-2.

### Exit Criteria

- `entity_snapshot` populated for all existing entities after migration.
- Trigger fires correctly on any sub-table mutation.
- `GET /export` returns identical JSON before and after refactor (verified by test).
- `go test ./...` passes.

---

## 5) SS-2 — Soft Delete + Recycle Bin

### Goal

Replace permanent/cascade delete on glossary entities with soft delete. Extend the recycle bin UI to filter by category. No kind deletion yet (kinds added in SS-4/SS-5), but entity soft delete is foundational.

### DB Changes

```sql
-- glossary_entities
ALTER TABLE glossary_entities ADD COLUMN deleted_at TIMESTAMPTZ DEFAULT NULL;
CREATE INDEX idx_ge_deleted ON glossary_entities(book_id) WHERE deleted_at IS NULL;
-- (existing index already filters on book_id; add partial index for non-deleted)

-- Remove CASCADE from chapter_entity_links, entity_attribute_values:
-- These already have ON DELETE CASCADE from entity_id FK.
-- We keep the FK but entity delete no longer triggers cascade because we
-- soft-delete the entity (never DELETE the row). Physical cascade is moot
-- until GC runs (out of scope).
```

### Backend Deliverables

| Area | What to build |
|---|---|
| Entity delete | `deleteEntity` handler — change from `DELETE FROM glossary_entities` to `UPDATE ... SET deleted_at = now()`. Bump entity `updated_at`. |
| Entity list/detail | All queries add `AND deleted_at IS NULL` filter. |
| Recycle bin endpoint | `GET /v1/glossary/recycle-bin` — query glossary_entities WHERE `deleted_at IS NOT NULL` AND `book_id` in user's books. Params: `?book_id=`, `?category=entity` (only category for now; kinds added in SS-4/SS-5). Returns paginated list. |
| Restore endpoint | `POST /v1/glossary/recycle-bin/entities/{entity_id}/restore` — sets `deleted_at = NULL`. Verifies book ownership. |
| Permanent delete endpoint | `DELETE /v1/glossary/recycle-bin/entities/{entity_id}` — sets a `permanently_deleted_at` flag (actual physical row deletion deferred to GC). |
| Tests | Soft delete hides entity from list/detail; recycle bin shows it; restore makes it visible again; permanent delete flags it. |

### Frontend Deliverables

| Area | What to build |
|---|---|
| Recycle bin page | Extend existing recycle bin (books) to add "Glossary Entities" category tab. Filter bar with category multi-select: Book, Glossary Entity (more categories added in SS-4/SS-5). |
| Entity row | Show: entity display_name (from `entity_snapshot.attributes[name].original_value`), kind name (from `entity_snapshot.kind.name`), book name, deleted_at date. |
| Actions | Restore button → calls restore endpoint → removes from list. Permanent delete button → confirmation dialog → calls permanent delete endpoint. |
| GlossaryPage delete | Entity card "Delete" action now moves to recycle bin (no cascade warning needed). Show brief toast "Moved to recycle bin". |

### Exit Criteria

- Deleting entity from glossary moves it to recycle bin; entity absent from glossary list.
- Recycle bin shows deleted entity with correct name from snapshot.
- Restore returns entity to glossary list.
- All existing entity list/detail queries unaffected (`deleted_at IS NULL` filter).

---

## 6) SS-3 — Glossary Settings + Auto-suggest Toast

### Goal

Add user-configurable glossary preferences (starting with default chapter-link relevance) and implement the auto-suggest chapter link banner in `AttributeRow`.

### DB Changes

```sql
CREATE TABLE IF NOT EXISTS glossary_user_preferences (
  user_id                         UUID PRIMARY KEY,
  default_chapter_link_relevance  TEXT NOT NULL DEFAULT 'mentioned'
    CHECK (default_chapter_link_relevance IN ('mentioned','minor','major','pivotal')),
  updated_at                      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Backend Deliverables

| Area | What to build |
|---|---|
| Preferences endpoint | `GET /v1/glossary/preferences` → returns row or defaults. `PUT /v1/glossary/preferences` → upsert. |
| Tests | GET returns defaults for new user; PUT persists; invalid relevance value → 422. |

### Frontend Deliverables

| Area | What to build |
|---|---|
| `glossaryApi.ts` | Add `getPreferences()`, `putPreferences(body)` |
| Settings page | New "Glossary" section in user settings page. Single field: "Default chapter-link relevance" (`<select>` with 4 options). Auto-save on change (consistent with existing settings UX). |
| `useGlossaryPreferences` hook | Fetch preferences once, cache in context or component state. |
| Auto-suggest banner | In `AttributeRow` expanded body, after evidence list: if last-added evidence has `chapter_id` AND that `chapter_id` is not in `entity.chapter_links[].chapter_id` → show inline banner. Banner: "This evidence references [chapter_title]. Link this chapter to the entity?" → "Link" button + "Dismiss" (×). |
| "Link" action | Calls `glossaryApi.createChapterLink(...)` with `relevance = userPreferences.default_chapter_link_relevance`. On success: calls `onRefresh()`, dismisses banner. On error: inline error text. |
| Dismiss | Sets local state `dismissedChapterSuggestFor: Set<chapterId>`. Session-only. |

### Exit Criteria

- Settings page shows Glossary section; save persists preference.
- After adding evidence with unlinked `chapter_id` → banner appears.
- "Link" creates chapter link with user's configured relevance.
- "Dismiss" hides banner; no link created.
- Evidence with no `chapter_id` → no banner.

---

## 7) SS-4 — T2 User Kind CRUD

### Goal

Full CRUD for user-level (T2) custom kinds and their attribute definitions. Kind management page in user settings. No entity creation with T2 kinds yet (wired in SS-7). SS-4 is the largest sub-phase.

### DB Schema

```sql
CREATE TABLE user_kinds (
  user_kind_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id UUID NOT NULL,
  code          TEXT NOT NULL,
  name          TEXT NOT NULL,
  description   TEXT,
  icon          TEXT NOT NULL DEFAULT 'box',
  color         TEXT NOT NULL DEFAULT '#6366f1',
  genre_tags    TEXT[] NOT NULL DEFAULT '{}',
  is_active     BOOLEAN NOT NULL DEFAULT true,
  cloned_from_kind_id UUID REFERENCES entity_kinds(kind_id) ON DELETE SET NULL,
  -- null if created from scratch or source T1 kind was never stored
  deleted_at    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(owner_user_id, code)
);
CREATE INDEX idx_uk_owner ON user_kinds(owner_user_id) WHERE deleted_at IS NULL;

CREATE TABLE user_kind_attributes (
  attr_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_kind_id  UUID NOT NULL REFERENCES user_kinds(user_kind_id) ON DELETE CASCADE,
  code          TEXT NOT NULL,
  name          TEXT NOT NULL,
  description   TEXT,
  field_type    TEXT NOT NULL DEFAULT 'text',
  is_required   BOOLEAN NOT NULL DEFAULT false,
  sort_order    INT NOT NULL DEFAULT 0,
  options       JSONB,
  deleted_at    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_kind_id, code)
);
```

### Backend Deliverables

| Endpoint | Description |
|---|---|
| `GET /v1/glossary/user-kinds` | List T2 kinds for current user. Params: `?is_active=`, `?cloned_from=system/scratch`, `?sort=name/created_at`, `?limit&offset`. |
| `POST /v1/glossary/user-kinds` | Create kind from scratch OR clone from T1 (`body.clone_from_kind_id`). Clone copies name/icon/color/genre_tags + all T1 attribute definitions into `user_kind_attributes`. |
| `GET /v1/glossary/user-kinds/{user_kind_id}` | Full detail: kind metadata + all attribute definitions (non-deleted). |
| `PATCH /v1/glossary/user-kinds/{user_kind_id}` | Update metadata fields (name, icon, color, description, genre_tags, is_active). |
| `DELETE /v1/glossary/user-kinds/{user_kind_id}` | Soft delete (recycle bin). Rejects if entities exist with this kind AND permanently_deleted_at is null → returns `GLOSS_KIND_HAS_ENTITIES 409`. |
| `POST /v1/glossary/user-kinds/{user_kind_id}/attributes` | Add attribute definition. |
| `PATCH /v1/glossary/user-kinds/{user_kind_id}/attributes/{attr_id}` | Update attribute (name, field_type, is_required, sort_order, options). |
| `DELETE /v1/glossary/user-kinds/{user_kind_id}/attributes/{attr_id}` | Soft delete attribute. Rejects if any `entity_attribute_values` row has non-empty `original_value` for this attr → returns warning `GLOSS_ATTR_HAS_DATA 409` with count; client must confirm and re-send with `?force=true`. |
| Recycle bin | Extend `GET /v1/glossary/recycle-bin` to include `user_kinds` and `user_kind_attributes` rows. Add `POST .../user-kinds/{id}/restore` and `DELETE .../user-kinds/{id}`. |
| Tests | Clone copies all attrs; pagination on list; soft delete rejects with entities; attribute soft delete with force; restore; recycle bin category filter. |

### Frontend Deliverables

| Component / Page | Description |
|---|---|
| `glossaryApi.ts` additions | `listUserKinds`, `createUserKind`, `getUserKind`, `patchUserKind`, `deleteUserKind`, `createUserKindAttr`, `patchUserKindAttr`, `deleteUserKindAttr` |
| `UserKindsPage.tsx` | New route `/settings/glossary/kinds`. Table/card list of T2 kinds with pagination, sort, is_active filter. "New kind" button → `CreateKindModal`. Row actions: Edit, Deactivate/Activate, Clone, Delete (→ recycle bin confirm). |
| `CreateKindModal.tsx` | Two modes: "From scratch" (name/icon/color/description fields) and "Clone from system" (searchable kind picker showing 12 T1 kinds + preview of attributes to be copied). |
| `KindDetailPage.tsx` | Route `/settings/glossary/kinds/{user_kind_id}`. Edit metadata form + attribute definition list. Attribute list: each row shows name/field_type/is_required; inline "Add attribute" form at bottom; per-row edit/soft-delete. |
| `AttributeDeleteConfirmModal.tsx` | Shows "N entities have data for this attribute. Deleting will hide it from their detail view but data is preserved." with Confirm/Cancel. |
| Recycle bin update | Add "Glossary Kinds" and "Glossary Attributes" category tabs to recycle bin page. |
| Settings nav | Add "Kind management" link under Glossary section in settings sidebar. |

### Exit Criteria

- User can create, clone, edit, deactivate, and soft-delete T2 kinds.
- Clone from T1 copies all attributes.
- Attribute soft delete works with/without force confirmation.
- T2 kinds and their deleted attributes appear in recycle bin; restore works.
- `go test ./...` + `npx tsc --noEmit` pass.

---

## 8) SS-5 — T3 Book Kind CRUD

### Goal

Same pattern as SS-4 but scoped to a single book. T3 kinds override T2/T1 for that book. Book owner manages T3 kinds from within the book's glossary settings.

### DB Schema

```sql
CREATE TABLE book_kinds (
  book_kind_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id       UUID NOT NULL,
  owner_user_id UUID NOT NULL,
  code          TEXT NOT NULL,
  name          TEXT NOT NULL,
  description   TEXT,
  icon          TEXT NOT NULL DEFAULT 'box',
  color         TEXT NOT NULL DEFAULT '#6366f1',
  genre_tags    TEXT[] NOT NULL DEFAULT '{}',
  is_active     BOOLEAN NOT NULL DEFAULT true,
  cloned_from_kind_id      UUID REFERENCES entity_kinds(kind_id) ON DELETE SET NULL,
  cloned_from_user_kind_id UUID REFERENCES user_kinds(user_kind_id) ON DELETE SET NULL,
  -- at most one clone source
  deleted_at    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(book_id, code)
);
CREATE INDEX idx_bk_book ON book_kinds(book_id) WHERE deleted_at IS NULL;

CREATE TABLE book_kind_attributes (
  attr_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_kind_id  UUID NOT NULL REFERENCES book_kinds(book_kind_id) ON DELETE CASCADE,
  code          TEXT NOT NULL,
  name          TEXT NOT NULL,
  description   TEXT,
  field_type    TEXT NOT NULL DEFAULT 'text',
  is_required   BOOLEAN NOT NULL DEFAULT false,
  sort_order    INT NOT NULL DEFAULT 0,
  options       JSONB,
  deleted_at    TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(book_kind_id, code)
);
```

### Backend Deliverables

Mirrors SS-4 endpoints but scoped under `/v1/glossary/books/{book_id}/kinds`:

| Endpoint | Description |
|---|---|
| `GET /v1/glossary/books/{book_id}/kinds` | List T3 kinds for book. Same filter params as SS-4. |
| `POST /v1/glossary/books/{book_id}/kinds` | Create/clone. Clone sources: T1 kind OR T2 user kind (`clone_from_user_kind_id`). |
| `GET/PATCH/DELETE /v1/glossary/books/{book_id}/kinds/{book_kind_id}` | Same as SS-4 counterparts. |
| `POST/PATCH/DELETE /v1/glossary/books/{book_id}/kinds/{book_kind_id}/attributes/{attr_id}` | Attribute CRUD. |
| Recycle bin | Extend `GET /v1/glossary/recycle-bin` to include `book_kinds` and `book_kind_attributes`. Add restore/permanent-delete endpoints. |
| `v_attr_def` view update | Add `book_kind_attributes` UNION branch (established in ADR-S2). |
| Tests | Same coverage as SS-4; clone from T2 user kind copies all attrs. |

### Frontend Deliverables

| Component / Page | Description |
|---|---|
| `glossaryApi.ts` additions | `listBookKinds`, `createBookKind`, `getBookKind`, `patchBookKind`, `deleteBookKind`, `createBookKindAttr`, `patchBookKindAttr`, `deleteBookKindAttr` |
| Book glossary settings tab | New "Kinds" tab inside book's glossary page (or `BookGlossarySettingsPage.tsx` at `/books/:bookId/glossary/settings`). Layout mirrors `KindDetailPage` from SS-4 but scoped to book. |
| `CreateBookKindModal.tsx` | Clone source picker: T1 (system) OR T2 (user kinds — filtered list). |
| Recycle bin update | Add "Book Kinds" category tab. |

### Exit Criteria

- Book owner can manage T3 kinds scoped to their book.
- Clone from T1 and T2 works.
- T3 recycle bin and restore work.
- T1 and T2 kinds unaffected.

---

## 9) SS-6 — Kind Sync + Compare

### Goal

Implement the bidirectional sync mechanism between kind tiers. Core UI is `KindCompareModal` — a diff viewer with per-attribute checkboxes to select which changes to apply.

### Backend Deliverables

| Endpoint | Description |
|---|---|
| `POST /v1/glossary/kinds/compare` | Compute diff between two kinds (any tier). Body: `{ source: { tier, id }, target: { tier, id } }`. Returns structured diff: `added_attrs[]`, `removed_attrs[]`, `modified_attrs[]`, `unchanged_attrs[]`. Each entry has checkbox-friendly `diff_key`. |
| `POST /v1/glossary/kinds/sync` | Apply selected diff items. Body: `{ source: {tier, id}, target: {tier, id}, apply: diff_key[] }`. Validates ownership of target. Returns updated target kind. |

**Sync semantics per direction:**

| Source → Target | Effect |
|---|---|
| T1 → T2 | Add/modify/remove attributes on T2 user kind as selected. Updates `user_kind_attributes`. |
| T1 → T3 | Add/modify/remove attributes on T3 book kind. Updates `book_kind_attributes`. |
| T2 → T3 | Promote user kind changes to book kind scope. |
| T3 → T2 | Promote book-specific changes to user level (most common use case). |
| T3 → T1 | **Not allowed.** Users cannot modify T1. Returns 403. |
| T2 → T1 | **Not allowed.** Returns 403. |

**Diff algorithm:**
- Match attributes by `code` field (stable identifier).
- `added`: code exists in source but not in (non-deleted) target.
- `removed`: code exists in (non-deleted) target but not in source.
- `modified`: code exists in both but `name`, `field_type`, `is_required`, `sort_order`, or `options` differ.
- `unchanged`: code + all fields identical.

**Sync apply rules:**
- Applying `added` attr: INSERT into target's attribute table.
- Applying `modified` attr: UPDATE target attribute row.
- Applying `removed` attr: soft-delete target attribute (`deleted_at = now()`). If attr has data → return per-attr warning in response (client shows `AttributeDeleteConfirmModal` from SS-4).
- Applying `unchanged`: no-op.

### Frontend Deliverables

| Component | Description |
|---|---|
| `KindCompareModal.tsx` | Triggered from: (a) "Re-sync from system" button on T2/T3 kind detail page; (b) "Push to my kinds" on T3; (c) "Push to this book" on T2. Modal layout: two-column diff table (source left, target right). Rows: one per attribute, with diff status icon (➕ added / ✏️ modified / ➖ removed / ✓ unchanged). Checkbox column on left. "Select all" / "Deselect all". "Apply selected" → POST `/kinds/sync` → closes modal → triggers kind detail refresh. |
| Sync entry points | SS-4 `KindDetailPage`: "Re-sync from system" button (opens compare against source T1 kind if `cloned_from_kind_id` exists). SS-5 book kind page: "Push to my kinds" button; "Re-sync from system" button. |
| Conflict warning | If sync would soft-delete an attribute with data → modal shows per-attribute warning with entity count before Apply. |

### Exit Criteria

- Compare endpoint returns correct diff for all four combinations of tiers.
- Sync apply correctly adds/modifies/soft-deletes attributes.
- T1 → T2/T3 sync works; T2/T3 → T1 returns 403.
- `KindCompareModal` shows all diff rows with correct icons; only checked diffs applied.
- Attribute-with-data warning appears before apply.

---

## 10) SS-7 — Kind Integration (Entity Picker + Filter Bar)

### Goal

Wire T1, T2, and T3 kinds into the entity creation flow and glossary filter bar. Apply ADR-S1 schema migration to `glossary_entities`. After this sub-phase, users can create entities using any active kind from any tier.

### DB Migration

Apply ADR-S1 and ADR-S2 changes to `glossary_entities` and `entity_attribute_values`:

```sql
-- glossary_entities: add user_kind_id, book_kind_id (nullable), make kind_id nullable
-- entity_attribute_values: add user_attr_def_id, book_attr_def_id (nullable), make attr_def_id nullable
-- Add CHECK constraints (see ADR-S1, ADR-S2)
-- Create v_attr_def view (see ADR-S2)
```

Backfill: all existing entities have `kind_id` set → `kind_source` is implicitly `system`. No data migration needed beyond constraint addition.

### Backend Deliverables

| Area | What to build |
|---|---|
| `GET /v1/glossary/kinds` (extended) | Now returns T1 kinds PLUS user's T2 kinds PLUS T3 kinds for the requested book. New query param `?book_id=` (optional). Response groups into `{ system: [...], user: [...], book: [...] }`. |
| Entity create | `createEntity` handler accepts `kind_tier: 'system'|'user'|'book'` + `kind_ref_id`. Validates kind exists and is active in correct tier. Inserts `user_kind_id` or `book_kind_id` on `glossary_entities`. Auto-populates `entity_attribute_values` from the correct tier's attribute definitions (`user_kind_attributes` or `book_kind_attributes`). |
| Entity list/detail | `listEntities` and `getEntityDetail` join against `v_attr_def` for attribute metadata. Kind metadata for display: join `entity_kinds` OR `user_kinds` OR `book_kinds` based on which FK is set. |
| Kind filter param | `GET .../entities?kind_codes=` now accepts codes from T1/T2/T3. Query resolves code against all three tables. |
| Snapshot trigger update | `recalculate_entity_snapshot` updated to resolve kind metadata from correct tier table. |
| Tests | Create entity with T2 kind; create with T3 kind; list filter by T2 kind code; detail shows T2/T3 kind metadata; snapshot correct for T2/T3 entity. |

### Frontend Deliverables

| Component | Description |
|---|---|
| `CreateEntityModal.tsx` update | Kind picker grid now shows three groups: "System kinds" (T1, always shown), "My kinds" (T2, shown if any active exist), "Book kinds" (T3, shown if any active exist for this book). Groups collapsed by default if empty. |
| `GlossaryFiltersBar.tsx` update | Kind multi-select populated from extended `GET /kinds?book_id=` response. T2/T3 kinds shown in separate optgroups. |
| `KindBadge.tsx` update | Accepts `source: 'system'|'user'|'book'` — adds small tier indicator icon (e.g. person icon for user, book icon for book). |
| `glossaryApi.ts` | Update `getKinds(bookId?)` signature; update `createEntity` to pass `kind_tier` + `kind_ref_id`. |

### Exit Criteria

- User can create entity with T2 kind → entity appears in list with correct kind badge.
- User can create entity with T3 book kind → same.
- Filter bar shows T1/T2/T3 kinds grouped correctly.
- Existing entities with T1 kinds unaffected.
- `entity_snapshot` correctly populated for T2/T3 entities.
- All existing SP-1 to SP-5 tests still pass.

---

## 11) New Files Summary

### Backend (glossary-service)

```
internal/migrate/migrate.go            — extend with SS-1 to SS-7 migrations
internal/api/
  snapshot_handler.go                  — (internal helpers; trigger handles most)
  preferences_handler.go               — SS-3: GET/PUT /v1/glossary/preferences
  user_kind_handler.go                 — SS-4: T2 kind CRUD
  book_kind_handler.go                 — SS-5: T3 kind CRUD
  kind_sync_handler.go                 — SS-6: compare + sync
  recycle_bin_handler.go               — SS-2 + SS-4 + SS-5: recycle bin API
```

### Frontend

```
frontend/src/features/glossary/
  api.ts                               — extend each SS
  hooks/
    useGlossaryPreferences.ts          — SS-3
    useUserKinds.ts                    — SS-4
    useBookKinds.ts                    — SS-5
  components/
    ChapterSuggestBanner.tsx           — SS-3 (auto-suggest toast)
    CreateKindModal.tsx                — SS-4
    KindDetailPage.tsx                 — SS-4 (also used by SS-5)
    AttributeDeleteConfirmModal.tsx    — SS-4 (reused in SS-6)
    CreateBookKindModal.tsx            — SS-5
    KindCompareModal.tsx               — SS-6

frontend/src/pages/
  UserKindsPage.tsx                    — SS-4
  BookGlossarySettingsPage.tsx         — SS-5
```

### Modified Files

```
services/glossary-service/internal/api/
  export_handler.go       — SS-1 (snapshot-based export)
  entity_handler.go       — SS-7 (T2/T3 create, polymorphic kind ref)
  kinds_handler.go        — SS-7 (extend to return T2/T3)
  server.go               — each SS (new routes)

frontend/src/features/glossary/
  components/
    GlossaryFiltersBar.tsx   — SS-7
    CreateEntityModal.tsx    — SS-7
    KindBadge.tsx            — SS-7
    AttributeRow.tsx         — SS-3 (add ChapterSuggestBanner)
```

---

## 12) Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Trigger write amplification on large books | Medium | High | Benchmark in SS-1 before proceeding; add async queue option if needed |
| ADR-S1 polymorphic FK + CHECK constraint migration fails on existing data | Low | High | Run in transaction; validate before altering; backfill before adding NOT NULL |
| `v_attr_def` UNION view slow for large books | Medium | Medium | Add covering indexes on `user_kind_attributes(user_kind_id)` and `book_kind_attributes(book_kind_id)` |
| SS-6 sync apply breaks existing entity attribute values (wrong ref after attr soft-delete) | Medium | High | Snapshot ensures display fallback; test entity detail render after sync |
| SS-7 filter-by-kind across 3 tables slow | Low | Medium | Code-based kind list → pass IDs to SQL; avoid dynamic UNION in filter path |

---

## 13) References

- `docs/03_planning/88_MODULE05_SUPPLEMENT_REQUIREMENTS.md` — source requirements
- `docs/implementation/MODULE05_IMPLEMENTATION_SUBPHASE_PLAN.md` — base M05 sub-phase plan
- `services/glossary-service/internal/migrate/migrate.go` — current 9-table schema
- `services/glossary-service/internal/domain/kinds.go` — T1 kind structs
- `services/glossary-service/internal/api/server.go` — current route map
