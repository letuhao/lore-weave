# Module 05 — Implementation Sub-Phase Plan

## Document Metadata

- Document ID: LW-IMPL-M05-PLAN-01
- Version: 1.0.0
- Status: Approved
- Owner: PM + Tech Lead
- Last Updated: 2026-03-23
- Approved By: Pending
- Approved Date: N/A
- Summary: Module 05 (Glossary & Lore Management) is split into 5 sequential sub-phases, each delivering a complete vertical slice (BE + FE + unit tests). Each sub-phase maps to a focused implementation prompt, closes a named set of AT scenarios, and produces a working, smoke-testable increment.

## Change History

| Version | Date       | Change                                    | Author    |
| ------- | ---------- | ----------------------------------------- | --------- |
| 1.0.0   | 2026-03-23 | Initial sub-phase plan                    | Assistant |

## Why This Split

Module 05 has 8 DB tables, 12 entity kinds with ~100 total attribute definitions, 25+ API endpoints across 7 handler groups, 14 frontend components, and 35 acceptance test scenarios. Implementing everything in one prompt creates too large a context window and high risk of inconsistency. The split follows natural feature layers: each phase builds on the previous one and leaves the system in a consistently deployable state.

## Sub-Phase Overview

| Sub-Phase | Name                                   | Key deliverable                                               | AT scenarios closed    |
| --------- | -------------------------------------- | ------------------------------------------------------------- | ---------------------- |
| SP-1      | Service skeleton + Kind enumeration    | New `glossary-service` boots, returns 12 kinds + FE kind picker | AT-01, AT-34         |
| SP-2      | Entity CRUD + filters                  | Create / list / detail / patch / delete entities + full filters | AT-02 to AT-15, AT-32 to AT-35 |
| SP-3      | Chapter link management                | M:N entity–chapter link CRUD                                  | AT-16 to AT-20         |
| SP-4      | Attribute values + Translations        | Edit original values; full translation CRUD                   | AT-21 to AT-26         |
| SP-5      | Evidences + RAG Export + smoke test    | Evidence CRUD; `GET /export`; E2E smoke script                | AT-27 to AT-31         |

---

## SP-1 — Service Skeleton + Kind Enumeration

### Goal

Stand up the entire `glossary-service` infrastructure (Go/Gin, Postgres, gateway route, docker-compose) and deliver the single read-only endpoint `GET /v1/glossary/kinds`. Frontend gains navigation tab and kind picker view.

### Backend deliverables

| Area | What to build |
| ---- | ------------- |
| Project setup | `services/glossary-service/` directory, `go.mod` / `go.sum`, `Dockerfile`, `cmd/server/main.go` |
| Config | `internal/config/config.go` — `PORT`, `DATABASE_URL`, `AUTH_SERVICE_URL`, `BOOK_SERVICE_URL`, `JWT_SECRET` |
| DB pool | `internal/db/db.go` — `pgx/v5` pool init; `internal/db/migrate.go` — run all 8 DDL tables + indexes on startup |
| Domain structs | `internal/domain/kinds.go` — `EntityKind`, `AttributeDefinition` structs; full 12-kind + ~100 attribute seed data |
| Seed | Idempotent startup seed: if `entity_kinds` is empty, insert all 12 kinds + attribute definitions |
| Repository | `internal/repository/kinds_repo.go` — `ListKinds()` with preloaded attribute definitions |
| Handler | `internal/handler/kinds_handler.go` — `GET /v1/glossary/kinds` |
| Health | `internal/handler/health_handler.go` — `GET /health` returns 200 |
| Middleware | `internal/middleware/auth.go` — verify Bearer JWT via auth-service |
| Middleware | `internal/middleware/book_owner.go` — verify book ownership via book-service projection endpoint |
| Book client | `internal/client/book_client.go` — `GetProjection(book_id)` and `ListChapters(book_id)` HTTP helpers |
| Infrastructure | `docker-compose.yml` — add `glossary-service` block (port 8088, env vars, depends_on) |
| Infrastructure | `infra/postgres/init/01-databases.sql` — add `CREATE DATABASE loreweave_glossary` |
| Infrastructure | `api-gateway-bff` env / config — add `GLOSSARY_SERVICE_URL` + `/v1/glossary/*` proxy route |
| Tests | Unit tests: seed correctness (12 kinds, correct attribute counts per kind), `GET /kinds` handler returns correct shape, 401 without token |

### Frontend deliverables

| Area | What to build |
| ---- | ------------- |
| Types | `frontend/src/features/glossary/types.ts` — `EntityKind`, `AttributeDefinition`, `LangEntry` and all other M05 types mirroring contract |
| API client | `frontend/src/features/glossary/api.ts` — `glossaryApi.getKinds()` |
| Hook | `frontend/src/features/glossary/hooks/useEntityKinds.ts` — cached kinds list |
| Component | `frontend/src/features/glossary/components/KindBadge.tsx` — icon + color chip |
| Component | `frontend/src/features/glossary/components/CreateEntityModal.tsx` — kind picker grid (12 kinds, optionally grouped by genre_tags); submit disabled (no entity endpoint yet, shows "coming soon" or disabled state) |
| Page | `frontend/src/pages/GlossaryPage.tsx` — skeleton: loads kinds, shows `CreateEntityModal` trigger, empty entity list area |
| Navigation | `BookDetailPage.tsx` or book detail layout — add "Glossary" tab linking to `/books/:bookId/glossary` |
| Route | App router — register `/books/:bookId/glossary` → `GlossaryPage` (protected) |
| Tests | `KindBadge.test.tsx`, `CreateEntityModal.test.tsx` (renders 12 kind options) |

### AT scenarios closed

- **M05-AT-01** — GET entity kinds returns 12 defaults with code, icon, color, `default_attributes[]`
- **M05-AT-34** — Unauthenticated request to `/kinds` returns 401

### Exit criteria

`docker compose up glossary-service` boots cleanly; `GET /health` returns 200; `GET /v1/glossary/kinds` returns 12 items; frontend `/books/:bookId/glossary` route renders without crash; kind picker grid shows all 12 icons.

---

## SP-2 — Entity CRUD + Filters

### Goal

Full entity lifecycle: create (with auto-populated attribute value rows), list with all 5 filter types + pagination, detail view, patch (status + tags), delete with cascade. Frontend delivers working entity list page and basic detail panel header/footer.

### Backend deliverables

| Area | What to build |
| ---- | ------------- |
| Domain | `internal/domain/entity.go` — `GlossaryEntity` (list summary + full detail), `GlossaryEntityFilter` |
| Repository | `internal/repository/entity_repo.go` — `CreateEntity`, `CreateAttributeValueRows`, `ListEntities` (5 filter combos + pagination), `GetEntityDetail`, `PatchEntity`, `DeleteEntity` |
| Service | `internal/service/entity_service.go` — orchestrate create (validate kind → insert entity → bulk-insert attribute value rows), delete cascade, filter query builder |
| Handler | `internal/handler/entity_handler.go` — `POST /books/:id/entities`, `GET /books/:id/entities`, `GET /books/:id/entities/:eid`, `PATCH /books/:id/entities/:eid`, `DELETE /books/:id/entities/:eid` |
| Filters | kind_codes (multi), status (active/inactive/draft/all), chapter_ids (multi + `unlinked` special case), search (ILIKE on name attribute original_value + translations), tags (AND logic), limit/offset/sort |
| Ownership | All mutation endpoints call `book_owner` middleware; `GET` endpoints call auth middleware + verify ownership in service layer |
| Error codes | `GLOSS_KIND_NOT_FOUND` 404, `GLOSS_NOT_FOUND` 404, `GLOSS_FORBIDDEN` 403 |
| Tests | Unit: attribute value row auto-population (count per kind), filter query building, cascade delete SQL, ownership guard, pagination math; handler tests for all 5 endpoints |

### Frontend deliverables

| Area | What to build |
| ---- | ------------- |
| API client | `api.ts` — add `listEntities`, `createEntity`, `getEntityDetail`, `patchEntity`, `deleteEntity` |
| Hook | `useGlossaryEntities.ts` — paginated entity list with `FilterState`, `loadMore`, optimistic delete |
| Hook | `useEntityDetail.ts` — fetch + patch entity; loading / saving states |
| Component | `GlossaryFiltersBar.tsx` — kind multi-select, status select, chapter multi-select / unlinked toggle, search input (debounced 300 ms), tags multi-select; active filter chips with remove |
| Component | `GlossaryEntityCard.tsx` — kind badge, display_name, chapter link count chip, translation count, evidence count, status badge; `⋯` menu (Duplicate stub, Set Inactive, Delete with confirmation) |
| Component | `EntityDetailPanel.tsx` — slide-over (600 px): header (kind badge, status toggle, close), footer (tags editor, timestamps, Save); body sections stubbed (Chapter Links, Attributes as placeholder) |
| Page | `GlossaryPage.tsx` — wire up filters + entity list + load more + create button → `CreateEntityModal` (now calls `createEntity`) → opens `EntityDetailPanel` |
| Tests | `GlossaryEntityCard.test.tsx`, `GlossaryFiltersBar.test.tsx` (filter state changes), `EntityDetailPanel.test.tsx` (renders header + footer) |

### AT scenarios closed

- **M05-AT-02** — Create character entity → `draft` status, 13 attribute value rows
- **M05-AT-03** — Create terminology entity → 4 attribute value rows
- **M05-AT-04** — Create with invalid `kind_id` → `GLOSS_KIND_NOT_FOUND` 404
- **M05-AT-05** — GET entity list no filters → all entities, correct summary fields
- **M05-AT-06** — Filter by kind → only that kind
- **M05-AT-07** — Filter by status=active → only active
- **M05-AT-08** — Filter by chapter_id → only entities linked to that chapter
- **M05-AT-09** — Filter chapter_ids=unlinked → entities with no chapter links
- **M05-AT-10** — Search query → ILIKE on name + translations
- **M05-AT-11** — Filter by tags → AND logic
- **M05-AT-12** — GET entity detail → full entity with attributes[], chapter_links[], translations[], evidences[]
- **M05-AT-13** — PATCH status → updated, `updated_at` refreshed
- **M05-AT-14** — PATCH tags → updated
- **M05-AT-15** — DELETE entity → cascade removes all related rows
- **M05-AT-32** — Non-owner cannot create → 403
- **M05-AT-33** — Non-owner cannot read → 403
- **M05-AT-35** — Pagination → offset=50 returns correct second page

### Exit criteria

Full entity lifecycle works end-to-end; filter bar drives list updates; detail panel opens on card click; delete removes entity from list; non-owner API calls return 403.

---

## SP-3 — Chapter Link Management

### Goal

Full M:N chapter–entity link CRUD: link with relevance + note, update relevance/note, unlink. Frontend delivers `ChapterLinkEditor` inside the detail panel.

### Backend deliverables

| Area | What to build |
| ---- | ------------- |
| Domain | `internal/domain/entity.go` — `ChapterLink` struct |
| Repository | `internal/repository/chapter_link_repo.go` — `CreateLink`, `ListLinksForEntity`, `UpdateLink`, `DeleteLink`; enforce `UNIQUE(entity_id, chapter_id)` |
| Handler | `internal/handler/chapter_link_handler.go` — `POST /entities/:eid/chapter-links`, `PATCH /entities/:eid/chapter-links/:lid`, `DELETE /entities/:eid/chapter-links/:lid` |
| Validation | Validate chapter belongs to book via `book_client.ListChapters`; return `GLOSS_CHAPTER_NOT_IN_BOOK` 422 if not found |
| Error codes | `GLOSS_DUPLICATE_CHAPTER_LINK` 409, `GLOSS_CHAPTER_NOT_IN_BOOK` 422 |
| Tests | Unit: duplicate link rejection, chapter-not-in-book guard, link count in entity list query |

### Frontend deliverables

| Area | What to build |
| ---- | ------------- |
| API client | `api.ts` — add `createChapterLink`, `updateChapterLink`, `deleteChapterLink` |
| Component | `ChapterLinkEditor.tsx` — embedded in `EntityDetailPanel` chapter links section: list of linked chapters (relevance badge, note, unlink ✕); inline "Link" form (chapter dropdown filtered to not-yet-linked, relevance picker, note input); auto-sorted by `chapter_index` |
| Component | Inline unlink confirmation dialog when entity has evidences referencing the chapter |
| Detail panel | Wire `ChapterLinkEditor` into `EntityDetailPanel` body replacing chapter links placeholder |
| Tests | `ChapterLinkEditor.test.tsx` — renders link list, add form, unlink button; duplicate link error display |

### AT scenarios closed

- **M05-AT-16** — Link entity to chapter → `ChapterLink` created with relevance + note
- **M05-AT-17** — Link same chapter twice → `GLOSS_DUPLICATE_CHAPTER_LINK` 409
- **M05-AT-18** — Link chapter not in book → `GLOSS_CHAPTER_NOT_IN_BOOK` 422
- **M05-AT-19** — PATCH chapter link relevance → updated
- **M05-AT-20** — DELETE chapter link → removed; entity remains

### Exit criteria

Chapter links appear in detail panel; can add/update/remove links; duplicate and out-of-book errors surface to the user.

---

## SP-4 — Attribute Values + Translations

### Goal

Edit original language and value for any attribute row; full translation CRUD (add, update, delete) with duplicate language prevention. Frontend delivers `AttributeRow`, inline attribute editing, and `TranslationList` with `AddTranslationModal`.

### Backend deliverables

| Area | What to build |
| ---- | ------------- |
| Domain | `internal/domain/translation.go` — `Translation` struct |
| Repository | `internal/repository/attribute_repo.go` — `UpdateAttributeValue` (patch `original_language`, `original_value`); updates parent `glossary_entities.updated_at` |
| Repository | `internal/repository/translation_repo.go` — `CreateTranslation`, `UpdateTranslation`, `DeleteTranslation`; enforce `UNIQUE(attr_value_id, language_code)` |
| Handler | `internal/handler/attribute_handler.go` — `PATCH /entities/:eid/attributes/:avid` |
| Handler | `internal/handler/translation_handler.go` — `POST /attributes/:avid/translations`, `PATCH /attributes/:avid/translations/:tid`, `DELETE /attributes/:avid/translations/:tid` |
| Error codes | `GLOSS_DUPLICATE_TRANSLATION_LANGUAGE` 409 |
| Tests | Unit: attribute update refreshes entity `updated_at`, duplicate language guard, translation CRUD, language filter in list query |

### Frontend deliverables

| Area | What to build |
| ---- | ------------- |
| API client | `api.ts` — add `patchAttributeValue`, `createTranslation`, `updateTranslation`, `deleteTranslation` |
| Component | `AttributeValueInput.tsx` — field-type-aware input (text, textarea, select, number, date, tags, url, boolean) |
| Component | `ConfidenceBadge.tsx` — verified / draft / machine badge |
| Component | `TranslationList.tsx` — list of translation rows (language code, value, confidence badge, delete button); `+ Add` trigger |
| Component | `AddTranslationModal.tsx` — language picker (filtered to unused languages), value input, confidence select |
| Component | `AttributeRow.tsx` — collapsible row: collapsed shows attr name + original value preview + translation count badge; expanded shows: original language BCP-47 picker + `AttributeValueInput` (auto-saves on blur via `PATCH`), `TranslationList`, evidences section placeholder (next phase) |
| Detail panel | Wire `AttributeRow` list into `EntityDetailPanel` attributes section replacing placeholder |
| Tests | `AttributeRow.test.tsx` — collapse/expand, edit field triggers save, translation count badge; `AddTranslationModal.test.tsx` — duplicate language filtering; `TranslationList.test.tsx` |

### AT scenarios closed

- **M05-AT-21** — PATCH attribute value (original value) → updated; entity `updated_at` refreshed
- **M05-AT-22** — PATCH attribute value (original language) → `original_language` updated
- **M05-AT-23** — Add translation → translation row created
- **M05-AT-24** — Add duplicate language translation → `GLOSS_DUPLICATE_TRANSLATION_LANGUAGE` 409
- **M05-AT-25** — PATCH translation → translation updated
- **M05-AT-26** — DELETE translation → translation removed

### Exit criteria

Attribute values are editable inline; translation list renders inside each attribute row; add/edit/delete translations work; duplicate language error shown.

---

## SP-5 — Evidences + RAG Export + Smoke Test

### Goal

Full evidence CRUD (with optional evidence translations); `GET /export` RAG-ready JSON; auto-suggest chapter link when evidence references an unlinked chapter; M05 E2E smoke test script.

### Backend deliverables

| Area | What to build |
| ---- | ------------- |
| Domain | `internal/domain/translation.go` — add `Evidence`, `EvidenceTranslation` structs |
| Repository | `internal/repository/evidence_repo.go` — `CreateEvidence`, `UpdateEvidence`, `DeleteEvidence`; cascades to `evidence_translations` |
| Repository | `internal/repository/export_repo.go` — single query joining all 8 tables, filtered to `status=active` (default), optionally scoped to one `chapter_id` |
| Service | `internal/service/export_service.go` — assemble hierarchical RAG export JSON matching schema version `1.0` |
| Handler | `internal/handler/evidence_handler.go` — `POST /attributes/:avid/evidences`, `PATCH /attributes/:avid/evidences/:evid`, `DELETE /attributes/:avid/evidences/:evid` |
| Handler | `internal/handler/export_handler.go` — `GET /books/:id/export` (optional `?chapter_id=`, optional `?include_drafts=true`) |
| Tests | Unit: export JSON structure (entities → attributes → translations + evidences), chapter-scoped export filter, evidence cascade delete |

### Frontend deliverables

| Area | What to build |
| ---- | ------------- |
| API client | `api.ts` — add `createEvidence`, `updateEvidence`, `deleteEvidence`, `exportGlossary` |
| Component | `AddEvidenceModal.tsx` — chapter select, block/line input, evidence type (quote/summary/reference), original language, text textarea, optional note |
| Component | `EvidenceList.tsx` — list of evidence cards (type badge, chapter ref, text preview, edit/delete); `+ Add` trigger |
| Component | Auto-suggest toast in `AttributeRow` and `EntityDetailPanel`: if added evidence references a chapter not yet linked → "Link to Chapter X? [Yes] [Dismiss]" |
| Component | Wire `EvidenceList` + `AddEvidenceModal` into `AttributeRow` evidences section (replacing placeholder from SP-4) |
| Smoke script | `scripts/smoke-module05.ps1` (or `.sh`) — full E2E: GET kinds → create character entity → fill name attribute → add translation → add evidence → link chapter → GET entity detail → verify RAG export JSON structure |
| Tests | `EvidenceList.test.tsx`, `AddEvidenceModal.test.tsx`, export API call test |

### AT scenarios closed

- **M05-AT-27** — Add evidence → evidence created
- **M05-AT-28** — PATCH evidence → text/location/note updated
- **M05-AT-29** — DELETE evidence → evidence removed
- **M05-AT-30** — RAG export (all active entities) → JSON matches schema, only active entities
- **M05-AT-31** — RAG export (chapter_id scoped) → only entities linked to that chapter

### Exit criteria

Evidence CRUD works inside attribute rows; auto-suggest chapter link toast fires; `GET /export` returns valid RAG JSON; smoke script runs end-to-end without errors; all 35 AT scenarios passing.

---

## Dependency Order + Notes

```
SP-1  ──►  SP-2  ──►  SP-3  ──►  SP-4  ──►  SP-5
(infra)   (entities) (chapter    (attrs +   (evidences
                      links)      transl.)   + export)
```

- **SP-2 requires SP-1** — needs DB tables, auth middleware, book_client, and `entity_kinds` seed data.
- **SP-3 requires SP-2** — chapter links reference `glossary_entities`.
- **SP-4 requires SP-2** — attribute values reference `entity_attribute_values` rows created by SP-2 entity creation.
- **SP-5 requires SP-4** — evidences reference `entity_attribute_values`; export query joins all prior tables.

## Shared infrastructure (build in SP-1, used by all sub-phases)

| Component | Used by |
| --------- | ------- |
| `migrate.go` — all 8 tables | SP-1 to SP-5 (tables created on first boot) |
| `auth.go` middleware | All handlers |
| `book_owner.go` middleware | SP-2 mutations and all subsequent |
| `book_client.go` | SP-2 (ownership), SP-3 (chapter validation) |
| `glossary/types.ts` | All frontend phases |
| `glossary/api.ts` | Extended each phase |

## Files to Create (cumulative across all sub-phases)

### Backend (new service)

```
services/glossary-service/
  Dockerfile
  go.mod, go.sum
  cmd/server/main.go
  internal/
    config/config.go
    db/db.go, migrate.go
    domain/kinds.go, entity.go, translation.go
    repository/kinds_repo.go, entity_repo.go, chapter_link_repo.go,
               attribute_repo.go, translation_repo.go, evidence_repo.go, export_repo.go
    service/entity_service.go, export_service.go
    handler/health_handler.go, kinds_handler.go, entity_handler.go,
            chapter_link_handler.go, attribute_handler.go,
            translation_handler.go, evidence_handler.go, export_handler.go
    middleware/auth.go, book_owner.go
    client/book_client.go
  tests/
    (one test file per handler / service)
```

### Frontend (new feature module)

```
frontend/src/features/glossary/
  types.ts, api.ts
  hooks/useEntityKinds.ts, useGlossaryEntities.ts, useEntityDetail.ts
  components/
    KindBadge.tsx, ConfidenceBadge.tsx
    CreateEntityModal.tsx
    GlossaryFiltersBar.tsx, GlossaryEntityCard.tsx
    EntityDetailPanel.tsx
    ChapterLinkEditor.tsx
    AttributeRow.tsx, AttributeValueInput.tsx
    TranslationList.tsx, AddTranslationModal.tsx
    EvidenceList.tsx, AddEvidenceModal.tsx

frontend/src/pages/GlossaryPage.tsx
```

### Infrastructure

```
infra/postgres/init/01-databases.sql      (add loreweave_glossary)
scripts/smoke-module05.ps1
```

## References

- `docs/03_planning/75_PHASE3_MODULE05_GLOSSARY_LORE_EXECUTION_PACK.md`
- `docs/03_planning/76_MODULE05_API_CONTRACT_DRAFT.md`
- `docs/03_planning/77_MODULE05_FRONTEND_FLOW_SPEC.md`
- `docs/03_planning/78_MODULE05_ACCEPTANCE_TEST_PLAN.md`
- `docs/03_planning/79_MODULE05_RISK_DEPENDENCY_ROLLOUT.md`
- `docs/03_planning/80_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE05.md`
- `docs/03_planning/81_MODULE05_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md`
- `docs/03_planning/82_MODULE05_BACKEND_DETAILED_DESIGN.md`
- `docs/03_planning/83_MODULE05_FRONTEND_DETAILED_DESIGN.md`
- `docs/03_planning/84_MODULE05_UI_UX_WIREFRAME_SPEC.md`
- `docs/03_planning/85_MODULE05_INTEGRATION_SEQUENCE_DIAGRAMS.md`
- `docs/03_planning/86_MODULE05_IMPLEMENTATION_READINESS_GATE.md`
