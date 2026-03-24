# Module 05 Supplement — Requirements Document (M05-S1)

## Document Metadata

- Document ID: LW-M05-88
- Version: 0.2.0
- Status: Approved
- Owner: Product Manager + BA
- Last Updated: 2026-03-25
- Approved By: Decision Authority
- Approved Date: 2026-03-24
- Summary: Requirements for features deferred from Module 05 MVP: (A) Auto-suggest chapter link toast; (B) Three-tier kind management with per-user and per-book scoping + bidirectional sync; (C) Recycle bin expansion for glossary objects; (D) Entity JSON snapshot column; (E) Glossary user settings section. All open questions from v0.1 are resolved.

## Change History

| Version | Date       | Change                              | Author    |
| ------- | ---------- | ----------------------------------- | --------- |
| 0.2.0   | 2026-03-25 | Resolve all OQ-1 to OQ-5; expand into 5 features; recycle bin, snapshot column, kind sync, glossary settings | Assistant |
| 0.1.0   | 2026-03-25 | Initial supplement requirements     | Assistant |

---

## 1) Context & Motivation

Module 05 (SP-1–SP-5) delivered the core glossary engine: 12 system-defined read-only kinds, full entity/attribute/translation/evidence/chapter-link CRUD, and RAG export. The following items were deferred from MVP and are now scoped in this supplement.

| Feature | Why deferred |
|---|---|
| **A — Auto-suggest toast** | Nice-to-have UX; not blocking SP-5 AT scenarios |
| **B — Kind management (three-tier)** | MVP locked to 12 system kinds |
| **C — Recycle bin expansion** | Current recycle bin only covers books; delete is permanent/cascade |
| **D — Entity JSON snapshot** | Needed to support display after kind/attribute deletion; required by future RAG injection |
| **E — Glossary user settings** | Default relevance for auto-suggest, and other per-user glossary preferences |

These five features are treated as a coordinated supplement ("M05-S1"). They have **inter-dependencies** — particularly D must be designed before C, and B depends on D for the "orphaned attribute" problem.

---

## 2) Feature A — Auto-suggest Chapter Link Toast

### Problem

When a user adds an evidence referencing a chapter that is not yet in the entity's `chapter_links`, the system saves silently. The entity's chapter link remains incomplete without the user noticing.

### Behavior & Rules

- **Trigger:** after `POST .../evidences` succeeds, frontend checks if the returned evidence's `chapter_id` exists in the current entity's `chapter_links[].chapter_id`.
- **Condition:** only if `chapter_id` is non-null on the saved evidence.
- **Presentation:** inline banner inside `AttributeRow` expanded body, below the evidence list. Non-modal, non-blocking.
- **Actions:** "Link chapter" (creates `ChapterLink` with user's configured default relevance — see Feature E) and "Dismiss".
- **Dismiss scope:** session-level only; reappears on next page load if chapter is still unlinked.
- **Auto-link failure:** show inline error, do not block UI.
- **No duplicate trigger:** if a chapter link already exists (added by another route), no suggestion.

### User Stories

**US-A1** — After adding evidence referencing an unlinked chapter, I see a prompt to link it without navigating away.
**US-A2** — I can dismiss the suggestion and continue working.
**US-A3** — Clicking "Link chapter" creates the link immediately with my configured default relevance.

### Out of Scope

- Suggestion for `chapter_title`-only evidences (no `chapter_id`).
- Bulk auto-link of multiple chapters from multiple evidences.
- Persistent dismiss (server-side "don't show again").

### Acceptance Criteria

- AC-A1: Evidence saved with `chapter_id` not in chapter links → banner appears.
- AC-A2: "Link chapter" → `ChapterLink` created with default relevance from user settings; banner disappears.
- AC-A3: "Dismiss" → banner disappears; no link created.
- AC-A4: Evidence has no `chapter_id` → no banner.
- AC-A5: Chapter already linked → no banner.

---

## 3) Feature B — Three-Tier Kind Management with Bidirectional Sync

### Problem

The MVP has one tier: 12 system kinds, read-only for users. Users cannot customize the kind/attribute structure for their own needs, nor tune it per book (different genres per book may need different attribute emphasis).

### Three-Tier Architecture

| Tier | Scope | Owner | Mutability |
|---|---|---|---|
| **T1 — System kinds** | Global | Admin (code seed) | Read-only for users |
| **T2 — User kinds** | Per-user (all books) | User | Full CRUD |
| **T3 — Book kinds** | Per-book | User (book owner) | Full CRUD |

A kind at T3 (book scope) overrides T2 for that book. A kind at T2 overrides T1 for that user.
When creating an entity in a book, the picker shows: active T3 kinds for that book, then active T2 kinds of the user, then T1 kinds — grouped and labeled.

### How Kinds Are Created

- **T2 (user kind):** clone from T1 (copies metadata + all attribute definitions) OR create from scratch.
- **T3 (book kind):** clone from T1, T2, or another T3 of the same book; OR create from scratch.
- Clones are fully independent snapshots — changes to the source do not propagate automatically.

### Bidirectional Sync (Kind Scope Promotion/Demotion)

Users can sync kinds and their attribute definitions across tiers in either direction. This is the mechanism for:
- Promoting a book-specific change to user level (e.g. "I added 'Sexual orientation' to Character in Book A, now I want it on all my books").
- Re-syncing with a system kind update (admin added a new attribute to Character T1).

**Sync is always explicit and user-driven — never automatic.**

#### Sync Entry Points

| Action | Direction |
|---|---|
| "Push to my kinds" (from T3) | T3 → T2: promote book-scope changes to user-scope |
| "Push to this book" (from T2) | T2 → T3: push user-scope to a specific book scope |
| "Re-sync from system" (from T2 or T3) | T1 → T2 or T1 → T3: pull system updates |

#### Sync Preview / Compare Component

Before any sync is applied, a **compare modal** is shown. Requirements:
- Left panel: source kind (with all attributes listed).
- Right panel: target kind (with all attributes listed).
- Differences are highlighted: new attributes, renamed attributes, removed attributes, changed field_type or is_required.
- Each difference row has a **checkbox** — user selects which changes to apply.
- "Apply selected" button — writes only the checked changes to the target tier.
- Attributes in the target that do not exist in the source are shown as "only in target" — user can check them for deletion or leave untouched.
- If an attribute selected for deletion has existing data in entities, a warning is shown per attribute: "N entities have data for this attribute. Deleting will hide it." (data is not deleted — see Feature D).

### Kind CRUD (T2 and T3)

| Operation | Behavior |
|---|---|
| **Create** | From scratch or clone; requires name + field_type for at least one attribute |
| **Edit metadata** | Name, icon, color, description; does not affect existing entities |
| **Add attribute** | New attribute definition added to kind; existing entities get a new empty attribute value row |
| **Remove attribute** | Attribute definition soft-deleted on kind; existing attribute value rows retained in DB, hidden in UI (see Feature D) |
| **Reorder attributes** | `sort_order` updated; cosmetic only |
| **Deactivate** | Kind hidden from "Create entity" picker; existing entities unaffected |
| **Delete** | Moves kind to recycle bin (see Feature C); NOT cascade; see Feature D for orphan handling |

### Kind List Management

Kind lists at T2 and T3 support **pagination, sort, and filter** to handle unlimited custom kinds:
- Filter: by `is_active`, by `source` (cloned from T1 / cloned from T2 / created from scratch).
- Sort: by name, by created_at, by last_modified.
- Pagination: server-side, default page size 20.

### User Stories

**US-B1** — Clone a system kind into my user kind catalog.
**US-B2** — Create a custom user kind from scratch.
**US-B3** — Override a user kind at book scope (clone T2 → T3).
**US-B4** — Add / remove / reorder attributes on a custom kind (T2 or T3).
**US-B5** — Promote a book-scope change to user scope via sync preview.
**US-B6** — Re-sync a user kind with a system kind update via sync preview, choosing which fields to overwrite.
**US-B7** — Deactivate a kind → removed from picker; existing entities unchanged.
**US-B8** — Delete a kind → moved to recycle bin; existing entities retain a JSON snapshot for display.
**US-B9** — See system + user + book kinds grouped in entity create picker and filter bar.
**US-B10** — Browse my user kinds with pagination, sort, filter.

### Out of Scope

- Admin CRUD UI for T1 (admin edits code directly in this version).
- Sharing custom kinds between users.
- Auto-propagation of T1 changes to T2/T3 without user action.
- Merging or re-assigning entities from one kind to another.
- Custom `field_type` values beyond the existing enum.

### Acceptance Criteria

- AC-B1: Clone T1 → creates T2 kind with all attributes copied.
- AC-B2: Create T2 from scratch → visible in picker and filter bar.
- AC-B3: Clone T2 → T3 → book picker shows T3 kind, T2 kind no longer shown as separate (T3 takes precedence).
- AC-B4: Add attribute to T2/T3 → existing entities of that kind get a new empty attribute value row.
- AC-B5: Sync T3 → T2 via compare modal → only checked diffs applied.
- AC-B6: Re-sync T1 → T2 via compare modal → only checked diffs applied; unchecked fields unchanged.
- AC-B7: Deactivate kind → kind absent from picker; existing entities visible and editable.
- AC-B8: Delete kind → kind in recycle bin; entities of that kind display via JSON snapshot.
- AC-B9: Kind list (T2/T3) supports pagination, sort, and is_active filter.
- AC-B10: System kinds remain unmodifiable by users.

---

## 4) Feature C — Recycle Bin Expansion for Glossary Objects

### Problem

Currently the recycle bin only covers books. Delete operations on glossary objects (entities, kinds, attributes) are permanent and cascade — a destructive and irreversible action. Users need a safety net.

### Design Decision — Soft Delete + Logical Recycle Bin

All deletable glossary objects use **soft delete**: a `deleted_at` timestamp (or `is_deleted` flag) is set; the physical row is retained. A background garbage collector does physical deletion on a scheduled basis (out of scope for this wave).

**No cascade delete.** Deleting a kind or attribute does not delete the entities or attribute values beneath it. Orphaned data is handled via JSON snapshot (Feature D).

### Recycle Bin Object Types

The recycle bin is extended to support the following categories, filterable independently:

| Category | Object |
|---|---|
| Books | `books` (existing) |
| Chapters | `chapters` (new) |
| Glossary entities | `glossary_entities` |
| Glossary kinds | `user_kinds` (T2), `book_kinds` (T3) — T1 system kinds are not deletable |
| Glossary attributes | `user_kind_attributes` — attribute definitions soft-deleted from a kind |

### Recycle Bin UI Requirements

- Filter bar with category multi-select (Book, Chapter, Glossary Entity, Glossary Kind, Glossary Attribute).
- Each row shows: object name, type, book context (if applicable), deleted_at date.
- Actions: **Restore** (reverses soft delete; re-activates object) and **Permanent delete** (marks `permanently_deleted = true`; GC will physical-delete later — out of scope for this wave).
- Pagination on the recycle bin list.

### Restore Behavior per Object Type

| Object | Restore action |
|---|---|
| Glossary entity | Clears `deleted_at`; entity reappears in glossary list |
| Glossary kind | Clears `deleted_at`; kind reappears in kind picker (as inactive by default — user must re-activate) |
| Glossary attribute | Clears `deleted_at` on attribute definition; attribute reappears in entity detail rows |
| Chapter | Clears `deleted_at`; chapter reappears in book chapter list |
| Book | Existing behavior retained |

### Acceptance Criteria

- AC-C1: Deleting a glossary entity moves it to recycle bin; entity no longer appears in glossary list.
- AC-C2: Deleting a kind (T2/T3) moves it to recycle bin; kind no longer appears in picker; entities of that kind display via JSON snapshot.
- AC-C3: Deleting an attribute definition moves it to recycle bin; attribute hidden in entity UI; data row retained.
- AC-C4: Recycle bin filters by category; shows all deleted objects across categories.
- AC-C5: Restore reverses soft delete for all supported types.
- AC-C6: No cascade delete — deleting a kind does not delete its entities.

---

## 5) Feature D — Entity JSON Snapshot Column

### Problem

If a kind or attribute definition is soft-deleted (moved to recycle bin), entities that referenced that kind/attribute lose context for display and future RAG export. The attribute rows still exist in the DB, but the kind name, attribute name, and field type metadata are gone from live tables.

### Design Decision — Denormalized `entity_snapshot` JSON Column

A computed JSON column `entity_snapshot JSONB` is added to `glossary_entities`. It stores the full, self-contained representation of the entity:
- Kind metadata (name, icon, color, code) — snapshot at time of last update.
- All attribute definitions (name, field_type) — snapshot.
- All attribute values (original_value, original_language).
- All translations per attribute.
- All evidences per attribute.
- All chapter links.

This snapshot is used for:
1. **Display fallback**: when kind or attribute definition is soft-deleted, UI reads from `entity_snapshot` for the entity card and detail panel.
2. **RAG export**: `GET /export` reads from `entity_snapshot` directly for performance, eliminating the 5-query join.

### Recalculation Trigger

A **PostgreSQL trigger** on the following tables recalculates `entity_snapshot` on the parent `glossary_entities` row:
- `INSERT/UPDATE/DELETE` on `entity_attribute_values`
- `INSERT/UPDATE/DELETE` on `attribute_translations`
- `INSERT/UPDATE/DELETE` on `evidences`
- `INSERT/UPDATE/DELETE` on `chapter_entity_links`

Trigger calls a PL/pgSQL function `recalculate_entity_snapshot(entity_id UUID)` that rebuilds the JSON in-DB using a single aggregation query.

Initial backfill: a one-time migration function runs `recalculate_entity_snapshot` for all existing entities on service startup (idempotent).

### Implications for Export Endpoint

`GET /v1/glossary/books/{book_id}/export` is updated to read from `entity_snapshot` instead of the 5-query bulk join. This simplifies the handler and improves performance for large books.

### Acceptance Criteria

- AC-D1: After creating/updating an attribute value, `entity_snapshot` on the parent entity is updated within the same transaction.
- AC-D2: Entity with a soft-deleted kind or attribute still renders correctly in the glossary list and detail panel using snapshot data.
- AC-D3: `GET /export` returns the same logical content before and after snapshot migration.
- AC-D4: Backfill runs once on startup; subsequent runs are no-ops.

---

## 6) Feature E — Glossary User Settings Section

### Problem

Several glossary behaviors need user-level configuration that does not exist yet. Currently there is no "Glossary" section in user settings.

### Settings Defined in This Supplement

| Setting | Description | Default |
|---|---|---|
| `default_chapter_link_relevance` | Relevance used when auto-suggest (Feature A) creates a chapter link | `mentioned` |

Additional glossary settings may be added in future waves.

### UI Requirements

- New "Glossary" section added to the existing user settings page (below existing sections).
- Single field for this wave: "Default chapter link relevance" — dropdown with values `mentioned`, `minor`, `major`, `pivotal`.
- Save button (or auto-save on change, consistent with existing settings UX pattern).

### Acceptance Criteria

- AC-E1: User can set default chapter link relevance in settings.
- AC-E2: Auto-suggest (Feature A) uses the saved preference when creating the chapter link.
- AC-E3: Default value is `mentioned` if not configured.

---

## 7) Cross-Feature Dependencies

```
Feature D (snapshot)
  └── required by Feature C (recycle bin — orphan display after kind delete)
  └── required by Feature B (kind delete — entities must survive without live kind row)
  └── simplifies Feature B sync (compare modal can diff against snapshot)

Feature E (settings)
  └── required by Feature A (auto-suggest uses configured default relevance)

Feature B (kind management)
  └── requires Feature C (delete → recycle bin, not cascade)
  └── requires Feature D (snapshot so deleted-kind entities still display)
```

Recommended implementation order: **D → C → E → A → B**

---

## 8) Resolved Open Questions

| # | Question | Decision |
|---|---|---|
| OQ-1 | User-level or book-level scope for custom kinds? | **Both.** Three tiers: system (T1), user (T2), book (T3). Bidirectional sync via preview/compare component with per-field checkboxes. |
| OQ-2 | Auto-update user clones when system kind changes? | **No auto-update.** User-driven re-sync via compare modal choosing which fields to pull from T1. Notification feature deferred. |
| OQ-3 | Max custom kinds per user? | **Unlimited.** Kind list redesigned with server-side pagination, sort, and filter. |
| OQ-4 | Default relevance for auto-suggest — configurable or hardcoded? | **Configurable per user** in a new Glossary section of user settings. |
| OQ-5 | Delete-with-entities — re-assign flow or hard delete? | **Recycle bin (soft delete).** No cascade. Orphaned entities preserved via JSON snapshot column (Feature D). Background GC for physical delete is out of scope. |

---

## 9) Out of Scope (This Wave)

- Admin CRUD UI for T1 system kinds.
- Cross-user kind sharing or kind marketplace.
- Notification system for T1 kind updates.
- Background garbage collector for physically deleted rows.
- Persistent dismiss for auto-suggest (server-side "don't show again").
- Entity re-assignment when a kind is deleted.
- Custom `field_type` values beyond the existing enum.

---

## 10) Dependencies on Existing Systems

| Dependency | Feature | Note |
|---|---|---|
| SP-1–SP-5 complete | All | Foundation in place |
| `POST .../chapter-links` endpoint | Feature A | Auto-link call |
| `entity_kinds` table + seed | Feature B | T2/T3 kinds extend the same pattern |
| Existing recycle bin (books) | Feature C | Extend, do not replace |
| `glossary_entities` table | Feature D | Add `entity_snapshot` column + trigger |
| User settings page | Feature E | Add new section |

---

## 11) References

- `docs/implementation/MODULE05_IMPLEMENTATION_SUBPHASE_PLAN.md`
- `docs/03_planning/75_PHASE3_MODULE05_GLOSSARY_LORE_EXECUTION_PACK.md`
- `docs/03_planning/87_MODULE05_GENRE_PROFILE_ARCHITECTURE_ADR.md`
- `services/glossary-service/internal/domain/kinds.go`
- `services/glossary-service/internal/migrate/migrate.go`
