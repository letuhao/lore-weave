# LoreWeave Module 05 Acceptance Test Plan

## Document Metadata

- Document ID: LW-M05-78
- Version: 0.1.0
- Status: Approved
- Owner: QA Lead
- Last Updated: 2026-03-23
- Approved By: —
- Approved Date: —
- Summary: Acceptance matrix for Module 05 glossary and lore management covering entity CRUD, chapter linking, attribute values, translations, evidences, filter logic, and RAG export.

## Change History

| Version | Date       | Change                                    | Author    |
| ------- | ---------- | ----------------------------------------- | --------- |
| 0.1.0   | 2026-03-23 | Initial Module 05 acceptance test plan    | Assistant |

---

## 1) Scope

In scope:
- Entity kind enumeration (8 defaults).
- Glossary entity CRUD (create with defaults, read list, read detail, update metadata, delete cascade).
- Chapter-entity link CRUD (link, unlink, update relevance, duplicate prevention).
- Attribute value editing (original language + original value).
- Translation CRUD per attribute value (add, update, remove, duplicate language prevention).
- Evidence CRUD per attribute value (add, update, remove, auto-link suggest).
- Filter logic: by kind, status, chapter_ids, unlinked, search, tags.
- Authorization: only book owner can create/modify/delete entities.
- RAG export: JSON structure, chapter-scoped variant, active-only filter.

Out of scope:
- Custom entity kind creation (not in M05 MVP scope).
- Custom attribute definition management (not in M05 MVP scope).
- RAG context injection into translation pipeline (Module 06).
- Bulk entity operations (Phase 3 wave 2).

---

## 2) Acceptance Matrix

| Scenario ID | Scenario | Expected result | Evidence |
| --- | --- | --- | --- |
| M05-AT-01 | GET entity kinds | Returns 8 default kinds each with `code`, `icon`, `color`, `default_attributes[]` | API |
| M05-AT-02 | Create entity — character kind | Entity created with `draft` status and 8 attribute value rows pre-populated (one per default attribute) | API |
| M05-AT-03 | Create entity — terminology kind | Entity created with 4 attribute value rows: `term`, `category`, `definition`, `usage_note` | API |
| M05-AT-04 | Create entity with invalid kind_id | Returns `GLOSS_KIND_NOT_FOUND` 404 | API negative |
| M05-AT-05 | GET entity list — no filters | Returns all entities for book with correct summary fields (`display_name`, `chapter_link_count`, `translation_count`, `evidence_count`) | API |
| M05-AT-06 | GET entity list — filter by kind | Only entities of specified kind returned | API |
| M05-AT-07 | GET entity list — filter by status=active | Only active entities returned | API |
| M05-AT-08 | GET entity list — filter by chapter_id | Only entities with a chapter link to that chapter_id returned | API |
| M05-AT-09 | GET entity list — filter chapter_ids=unlinked | Only entities with `chapter_link_count = 0` returned | API |
| M05-AT-10 | GET entity list — search query | Returns entities whose `name` attribute original value or any translation contains the search string (ILIKE) | API |
| M05-AT-11 | GET entity list — filter by tags | Returns only entities that have ALL specified tags | API |
| M05-AT-12 | GET entity detail | Returns full entity with `attribute_values[]`, `translations[]`, `evidences[]`, `chapter_links[]` | API |
| M05-AT-13 | PATCH entity status | Status updated; `updated_at` refreshed | API |
| M05-AT-14 | PATCH entity tags | Tags updated | API |
| M05-AT-15 | DELETE entity | Entity and all attribute values, translations, evidences, chapter links deleted (cascade) | API + DB |
| M05-AT-16 | Link entity to chapter | `ChapterLink` created with `relevance` and optional `note` | API |
| M05-AT-17 | Link entity to same chapter twice | Returns `GLOSS_DUPLICATE_CHAPTER_LINK` 409 | API negative |
| M05-AT-18 | Link entity to chapter not in book | Returns `GLOSS_CHAPTER_NOT_IN_BOOK` 422 | API negative |
| M05-AT-19 | PATCH chapter link relevance | Relevance updated; `chapter_links` list reflects change | API |
| M05-AT-20 | DELETE chapter link | Link removed; entity still exists with remaining chapter links | API |
| M05-AT-21 | PATCH attribute value — original value | Value updated; `updated_at` refreshed on entity | API |
| M05-AT-22 | PATCH attribute value — original language | `original_language` updated | API |
| M05-AT-23 | Add translation to attribute value | Translation row created with `language_code`, `value`, `confidence` | API |
| M05-AT-24 | Add duplicate language translation | Returns `GLOSS_DUPLICATE_TRANSLATION_LANGUAGE` 409 | API negative |
| M05-AT-25 | PATCH translation value/confidence | Translation updated | API |
| M05-AT-26 | DELETE translation | Translation removed; other translations unaffected | API |
| M05-AT-27 | Add evidence to attribute value | Evidence created with `chapter_id`, `block_or_line`, `evidence_type`, `original_text` | API |
| M05-AT-28 | PATCH evidence | Evidence text, location, or note updated | API |
| M05-AT-29 | DELETE evidence | Evidence removed; attribute value and entity still exist | API |
| M05-AT-30 | RAG export — all active entities | Returns JSON matching schema in `76` §5, only `active` entities | API |
| M05-AT-31 | RAG export — chapter_id scoped | Returns only entities linked to specified chapter | API |
| M05-AT-32 | Non-owner cannot create entity | Returns `GLOSS_FORBIDDEN` 403 | API negative |
| M05-AT-33 | Non-owner cannot read entities | Returns `GLOSS_FORBIDDEN` 403 | API negative |
| M05-AT-34 | Unauthenticated request rejected | All `/v1/glossary/*` endpoints return 401 | API negative |
| M05-AT-35 | GET entity list — pagination | `offset=50, limit=50` returns correct second page | API |

---

## 3) Pass Criteria

- All P0 scenarios pass:
  - `M05-AT-01` through `M05-AT-05` (kinds + create + list).
  - `M05-AT-12` through `M05-AT-15` (entity detail + CRUD).
  - `M05-AT-16`, `M05-AT-20` (chapter link + unlink).
  - `M05-AT-21` through `M05-AT-23`, `M05-AT-26` (attribute + translation).
  - `M05-AT-27`, `M05-AT-29` (evidence).
  - `M05-AT-30` (RAG export).
  - `M05-AT-32` through `M05-AT-34` (auth).
- Entity deletion cascades completely (AT-15 verified at DB level).
- Duplicate chapter link and duplicate translation language are rejected at API level (AT-17, AT-24).
- Filter combinations (kind + status + chapter) apply AND logic (spot-check via API).

---

## 4) Evidence Pack Requirements

- API response traces for all P0 scenarios.
- DB row count evidence for cascade delete (AT-15): before/after counts for `entity_attribute_values`, `attribute_translations`, `evidences`, `chapter_entity_links`.
- UI recording for full happy-path flow: create character → fill attributes → add translations → add evidence → link chapter → verify RAG export includes entity.
- Filter combination tests: at least 2 combined filter tests (e.g., kind=character AND chapter_id=X).

---

## 5) Test Layer Mapping

| Layer | Required coverage |
| --- | --- |
| Unit | Attribute default population logic (correct defaults per kind), filter query building, ILIKE search construction |
| Integration | All P0 API scenarios, cascade delete, duplicate rejection |
| E2E / UI | Create entity flow, add translation, add evidence, chapter link, filter by chapter |
| Manual spot-check | RAG export JSON structure validation, chapter-scoped export |
