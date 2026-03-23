# LoreWeave Module 05 Microservice Source Structure Amendment

## Document Metadata

- Document ID: LW-M05-81
- Version: 0.1.0
- Status: Draft
- Owner: Solution Architect
- Last Updated: 2026-03-23
- Approved By: —
- Approved Date: —
- Summary: Source-structure amendment for Module 05 introducing glossary-service (Go/Gin) and the associated contract path, plus frontend feature module structure.

## Change History

| Version | Date       | Change                                    | Author    |
| ------- | ---------- | ----------------------------------------- | --------- |
| 0.1.0   | 2026-03-23 | Initial Module 05 source structure amendment | Assistant |

---

## 1) Purpose

Extend the monorepo with the `glossary-service` bounded context and its contract path, plus the `features/glossary` frontend module, while preserving all existing service boundaries and contract conventions.

---

## 2) New Service

| Service | Responsibility | Language / Runtime |
| --- | --- | --- |
| `glossary-service` | Book-level glossary entity CRUD, entity kind enumeration (8 defaults), chapter-entity M:N linking, attribute values, translations, evidences, RAG-ready export | Go / Gin |

Gateway routes composed through `api-gateway-bff` (`/v1/glossary/*` → port 8088).

---

## 3) Proposed Monorepo Backend Layout

```text
services/
  glossary-service/                    ← NEW
    Dockerfile
    go.mod
    go.sum
    cmd/
      server/
        main.go                        — entry point, router setup, DB init
    internal/
      config/
        config.go                      — env vars (port, DB URL, auth-service URL, book-service URL)
      db/
        db.go                          — pgx pool init
        migrate.go                     — DDL migration runner (runs on startup)
      domain/
        kinds.go                       — EntityKind and AttributeDefinition structs + seed data
        entity.go                      — GlossaryEntity, ChapterLink, AttributeValue structs
        translation.go                 — Translation, Evidence structs
      repository/
        kinds_repo.go                  — SELECT kinds + attribute definitions
        entity_repo.go                 — CRUD for entities + filtered list
        chapter_link_repo.go           — M:N chapter link CRUD
        attribute_repo.go              — Attribute value CRUD
        translation_repo.go            — Translation CRUD per attribute value
        evidence_repo.go               — Evidence CRUD per attribute value
        export_repo.go                 — RAG export query (full entity graph)
      service/
        entity_service.go              — business logic: create entity (populate defaults), delete cascade, filter
        export_service.go              — assemble RAG export JSON
      handler/
        kinds_handler.go               — GET /v1/glossary/kinds
        entity_handler.go              — entity CRUD + filter list
        chapter_link_handler.go        — chapter link CRUD
        attribute_handler.go           — attribute value PATCH
        translation_handler.go         — translation CRUD
        evidence_handler.go            — evidence CRUD
        export_handler.go              — GET /v1/glossary/books/{id}/export
        health_handler.go              — GET /health
      middleware/
        auth.go                        — JWT verify via auth-service (reuse pattern from other services)
        book_owner.go                  — verify requester is book owner via book-service internal
      client/
        book_client.go                 — HTTP client for book-service internal endpoints

contracts/
  api/
    glossary/                          ← NEW
      v1/
        openapi.yaml                   — OpenAPI spec for /v1/glossary/*
        README.md
```

---

## 4) Proposed Monorepo Frontend Layout

```text
frontend/src/
  features/
    glossary/                          ← NEW
      api.ts                           — all glossary API calls (GET kinds, entity CRUD, links, translations, evidences, export)
      types.ts                         — TypeScript types: EntityKind, GlossaryEntity, ChapterLink, AttributeValue, Translation, Evidence
      hooks/
        useGlossaryEntities.ts         — paginated entity list with filter state
        useEntityDetail.ts             — single entity detail with mutation helpers
        useEntityKinds.ts              — cached kinds list
      components/
        GlossaryFiltersBar.tsx
        GlossaryEntityCard.tsx
        CreateEntityModal.tsx
        EntityDetailPanel.tsx
        ChapterLinkEditor.tsx
        AttributeRow.tsx
        AttributeValueInput.tsx
        TranslationList.tsx
        AddTranslationModal.tsx
        EvidenceList.tsx
        AddEvidenceModal.tsx
        KindBadge.tsx
        ConfidenceBadge.tsx

  pages/
    GlossaryPage.tsx                   ← NEW   (route: /books/:bookId/glossary)
```

---

## 5) Data Ownership

`glossary-service` owns:
- `entity_kinds` table (8 default kinds, seeded on startup),
- `attribute_definitions` table (per-kind defaults, seeded on startup),
- `glossary_entities` table,
- `entity_attribute_values` table,
- `attribute_translations` table,
- `evidences` table,
- `evidence_translations` table,
- `chapter_entity_links` table.

`glossary-service` reads from (does not own):
- `book-service` internal endpoint — book ownership + chapter list (read-only, no writes).

---

## 6) Internal Integration Points

| Integration | Direction | Protocol | Notes |
| --- | --- | --- | --- |
| `book-service` `/internal/books/{book_id}/projection` | glossary → book | HTTP GET | Validate book exists + requester is owner; called on every entity mutation |
| `book-service` `/internal/books/{book_id}/chapters` | glossary → book | HTTP GET | Validate chapter belongs to book on chapter link creation; also used to build frontend chapter picker |
| `api-gateway-bff` | gateway → glossary | HTTP proxy | Path prefix `/v1/glossary/*` → port 8088 |

---

## 7) Infrastructure Changes

### docker-compose.yml additions

```yaml
  glossary-service:
    build: ./services/glossary-service
    ports:
      - "8088:8088"
    environment:
      - PORT=8088
      - DATABASE_URL=postgres://loreweave:loreweave@postgres:5432/loreweave_glossary
      - AUTH_SERVICE_URL=http://auth-service:8081
      - BOOK_SERVICE_URL=http://book-service:8082
      - JWT_SECRET=${JWT_SECRET}
    depends_on:
      - postgres
      - auth-service
      - book-service
```

### api-gateway-bff route addition

```
GLOSSARY_SERVICE_URL=http://glossary-service:8088
/v1/glossary/* → proxy to GLOSSARY_SERVICE_URL
```

### DB bootstrap

Add to `infra/postgres/init/01-databases.sql`:
```sql
CREATE DATABASE loreweave_glossary;
```
