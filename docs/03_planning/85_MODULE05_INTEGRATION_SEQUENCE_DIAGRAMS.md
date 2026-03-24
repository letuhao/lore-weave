# LoreWeave Module 05 Integration Sequence Diagrams

## Document Metadata

- Document ID: LW-M05-85
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect
- Last Updated: 2026-03-23
- Approved By: Decision Authority
- Approved Date: 2026-03-24
- Summary: Cross-service sequence diagrams for M05 glossary service covering entity creation, chapter link validation, list with filters, evidence add with auto-suggest, and RAG export.

## Change History

| Version | Date       | Change                                    | Author    |
| ------- | ---------- | ----------------------------------------- | --------- |
| 0.1.0   | 2026-03-23 | Initial Module 05 sequence diagrams       | Assistant |

---

## 1) Actor Legend

| Actor | Description |
| --- | --- |
| `Browser` | Frontend SPA (React) |
| `Gateway` | api-gateway-bff (Node.js/Express, port 8080) |
| `GlossSvc` | glossary-service (Go/Gin, port 8088) |
| `BookSvc` | book-service (Go, port 8082) |
| `AuthSvc` | auth-service (Go, port 8081) — JWT verify |
| `DB` | loreweave_glossary (Postgres) |

---

## 2) SEQ-01: Load Glossary Page (Parallel Initialization)

```
Browser          Gateway          GlossSvc         BookSvc          DB
  │                │                 │                │               │
  │──── GET /v1/glossary/kinds ────>│                │               │
  │──── GET /v1/glossary/books/{id}/entities ──────>│               │
  │──── GET /v1/books/{id}/chapters (existing M02) ──────────────>  │
  │                │                 │                │               │
  │ (all 3 in parallel)              │                │               │
  │                │ proxy → GlossSvc│                │               │
  │                │────────────────>│ verify JWT     │               │
  │                │                 │─── sub → user_id ──────────── │
  │                │                 │ SELECT * FROM entity_kinds     │
  │                │                 │─────────────────────────────>│
  │                │                 │<─────────────────────────────│ 8 kinds
  │                │<────────────────│ 200 kinds[]    │               │
  │                │                 │                │               │
  │                │ proxy → GlossSvc│                │               │
  │                │────────────────>│                │               │
  │                │                 │ verify book ownership          │
  │                │                 │──────────────>│ GET /internal/books/{id}/projection
  │                │                 │<──────────────│ { owner_user_id }
  │                │                 │ check user_id == owner_user_id │
  │                │                 │ SELECT entities with filters   │
  │                │                 │─────────────────────────────>│
  │                │                 │<─────────────────────────────│ entities[]
  │                │<────────────────│ 200 { items, total }          │
  │<────────────────│                │                │               │
```

---

## 3) SEQ-02: Create Glossary Entity

```
Browser          Gateway          GlossSvc         BookSvc          DB
  │                │                 │                │               │
  │ POST /v1/glossary/books/{id}/entities            │               │
  │ Bearer: <jwt>  │                 │                │               │
  │ body: { kind_id }                │                │               │
  │────────────────>│                │                │               │
  │                 │ proxy          │                │               │
  │                 │────────────────>│                │               │
  │                 │                 │ 1. verify JWT  │               │
  │                 │                 │ 2. GET /internal/books/{id}/projection
  │                 │                 │──────────────>│               │
  │                 │                 │<──────────────│ owner_user_id  │
  │                 │                 │ 3. verify ownership            │
  │                 │                 │ 4. SELECT kind + attr_defs     │
  │                 │                 │─────────────────────────────>│
  │                 │                 │<─────────────────────────────│ kind + N attrs
  │                 │                 │ 5. INSERT glossary_entities    │
  │                 │                 │─────────────────────────────>│
  │                 │                 │<─────────────────────────────│ entity_id
  │                 │                 │ 6. INSERT entity_attribute_values (batch, N rows)
  │                 │                 │─────────────────────────────>│
  │                 │                 │<─────────────────────────────│ ok
  │                 │                 │ 7. SELECT full entity detail   │
  │                 │                 │─────────────────────────────>│
  │                 │                 │<─────────────────────────────│ entity + attrs
  │                 │<────────────────│ 201 entity detail             │
  │<────────────────│                 │                │               │
```

**Failure paths:**
- book-service returns 404 → `GLOSS_BOOK_NOT_FOUND` 404
- book-service `owner_user_id ≠ requester` → `GLOSS_FORBIDDEN` 403
- `kind_id` not found in DB → `GLOSS_KIND_NOT_FOUND` 404

---

## 4) SEQ-03: Link Entity to Chapter (with validation)

```
Browser          Gateway          GlossSvc         BookSvc          DB
  │                │                 │                │               │
  │ POST /v1/glossary/books/{id}/entities/{eid}/chapter-links        │
  │ body: { chapter_id, relevance }  │                │               │
  │────────────────>│                │                │               │
  │                 │────────────────>│                │               │
  │                 │                 │ 1. verify JWT + ownership      │
  │                 │                 │ 2. GET /internal/books/{id}/chapters
  │                 │                 │──────────────>│               │
  │                 │                 │<──────────────│ chapter_ids[]  │
  │                 │                 │ 3. check chapter_id ∈ chapter_ids
  │                 │                 │    (if not → GLOSS_CHAPTER_NOT_IN_BOOK)
  │                 │                 │ 4. INSERT chapter_entity_links │
  │                 │                 │─────────────────────────────>│
  │                 │                 │<─────────────────────────────│ ok / unique violation
  │                 │                 │    (if unique violation → GLOSS_DUPLICATE_CHAPTER_LINK)
  │                 │<────────────────│ 201 ChapterLink               │
  │<────────────────│                 │                │               │
```

---

## 5) SEQ-04: Add Evidence with Auto-Link Suggest

```
Browser          Gateway          GlossSvc         DB
  │                │                 │               │
  │ POST .../attributes/{avid}/evidences             │
  │ body: { chapter_id, block_or_line, type, text }  │
  │────────────────>│                │               │
  │                 │────────────────>│               │
  │                 │                 │ 1. verify JWT + ownership
  │                 │                 │ 2. INSERT evidences           │
  │                 │                 │──────────────────────────────>│
  │                 │                 │<──────────────────────────────│ evidence_id
  │                 │                 │ 3. check if chapter_id is linked to entity
  │                 │                 │    SELECT chapter_entity_links WHERE entity_id=? AND chapter_id=?
  │                 │                 │──────────────────────────────>│
  │                 │                 │<──────────────────────────────│ (no row)
  │                 │                 │ 4. set response.suggest_chapter_link = true
  │                 │<────────────────│ 201 Evidence + { suggest_chapter_link: true }
  │<────────────────│                 │
  │
  │ (Frontend receives suggest_chapter_link: true)
  │ → shows toast: "Link this entity to Ch.X? [Yes] [Dismiss]"
  │
  │ User clicks [Yes]:
  │ POST .../chapter-links (SEQ-03)
```

---

## 6) SEQ-05: RAG Export (chapter-scoped)

```
Browser          Gateway          GlossSvc         DB
  │                │                 │               │
  │ GET /v1/glossary/books/{id}/export?chapter_id={cid}
  │────────────────>│                │               │
  │                 │────────────────>│               │
  │                 │                 │ 1. verify JWT + ownership
  │                 │                 │ 2. SELECT entities WHERE book_id=?
  │                 │                 │    AND status='active'
  │                 │                 │    AND entity_id IN (
  │                 │                 │      SELECT entity_id FROM chapter_entity_links
  │                 │                 │      WHERE chapter_id=cid)
  │                 │                 │──────────────────────────────>│
  │                 │                 │<──────────────────────────────│ entity_ids[]
  │                 │                 │ 3. For each entity: SELECT attrs + translations + evidences
  │                 │                 │    (batched JOIN query)
  │                 │                 │──────────────────────────────>│
  │                 │                 │<──────────────────────────────│ full graphs
  │                 │                 │ 4. Assemble RAG JSON
  │                 │<────────────────│ 200 RAG JSON
  │<────────────────│                 │
```

---

## 7) SEQ-06: Delete Entity (Cascade)

```
Browser          Gateway          GlossSvc         BookSvc          DB
  │                │                 │                │               │
  │ DELETE /v1/glossary/books/{id}/entities/{eid}    │               │
  │────────────────>│                │                │               │
  │                 │────────────────>│                │               │
  │                 │                 │ 1. verify JWT + ownership      │
  │                 │                 │ 2. DELETE FROM glossary_entities WHERE entity_id=?
  │                 │                 │    (FK CASCADE deletes:)       │
  │                 │                 │    → chapter_entity_links      │
  │                 │                 │    → entity_attribute_values   │
  │                 │                 │      → attribute_translations  │
  │                 │                 │      → evidences               │
  │                 │                 │        → evidence_translations │
  │                 │                 │──────────────────────────────>│
  │                 │                 │<──────────────────────────────│ ok
  │                 │<────────────────│ 204 No Content                │
  │<────────────────│                 │                │               │
```

---

## 8) SEQ-07: Filter Entities by Chapter (unlinked)

```
Browser          Gateway          GlossSvc         DB
  │                │                 │               │
  │ GET /v1/glossary/books/{id}/entities?chapter_ids=unlinked
  │────────────────>│                │               │
  │                 │────────────────>│               │
  │                 │                 │ verify JWT + ownership
  │                 │                 │ SELECT e.* FROM glossary_entities e
  │                 │                 │   WHERE e.book_id = ?
  │                 │                 │     AND NOT EXISTS (
  │                 │                 │       SELECT 1 FROM chapter_entity_links
  │                 │                 │       WHERE entity_id = e.entity_id)
  │                 │                 │──────────────────────────────>│
  │                 │                 │<──────────────────────────────│ unlinked entities
  │                 │<────────────────│ 200 { items: [...], total: N }│
  │<────────────────│                 │                               │
```
