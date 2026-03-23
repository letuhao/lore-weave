# LoreWeave Phase 3 Module 05 Glossary & Lore Management — Execution Pack

## Document Metadata

- Document ID: LW-M05-75
- Version: 0.1.0
- Status: Draft
- Owner: Product Manager + Solution Architect
- Last Updated: 2026-03-23
- Approved By: —
- Approved Date: —
- Summary: Execution governance pack for Module 05: book-level glossary and lore entity management with multilingual attribute values, evidence tracking, chapter-linking, and RAG-ready export.

## Change History

| Version | Date       | Change                                    | Author    |
| ------- | ---------- | ----------------------------------------- | --------- |
| 0.2.0   | 2026-03-23 | Expand default kinds from 8 to 12 (add romance/drama kinds: Relationship, Plot Arc, Trope, Social Setting); update Character attrs; add `genre_tags` foundation; add ADR ref `87` | Assistant |
| 0.1.0   | 2026-03-23 | Initial Module 05 execution charter       | Assistant |

---

## 1) Module Charter

### Module Name

Module 05 — Glossary & Lore Management (Phase 3: Knowledge Services entry point)

### Objective

Deliver the first Knowledge Services vertical for LoreWeave:

- users can create and manage glossary entities (characters, locations, items, power systems, organizations, events, terminology, species) scoped to a book,
- each entity holds typed attribute values with original-language text and per-language translations,
- users can attach evidence (quotes or summaries from specific chapter locations) to any attribute value,
- entities are linked to chapters via a many-to-many `ChapterLink` join (entity is book-level, not chapter-owned),
- entities can be filtered by chapter, entity kind, status, and free-text search,
- the glossary can be exported as a RAG-ready JSON payload for injection into translation prompts.

### Positioning in Roadmap

Module 05 is the **Phase 3 entry point** (Knowledge Services). It intentionally omits:
- Custom entity kind creation (users work with 12 system-defined default kinds in MVP),
- Custom attribute definition management per kind (defaults only in MVP),
- RAG context injection into translation pipeline (planned for Module 06),
- Full-text search indexing (filter uses `ILIKE` on Postgres in MVP).

These are planned for later modules in Phase 3 and Phase 4.

### MVP Policy Lock

- Glossary engine: `glossary-service` (Go/Gin), new service at port 8088.
- Data model: **entities are book-level objects** — not owned by chapters. Chapter links are M:N via `chapter_entity_links` table.
- Auth: all `/v1/glossary/*` endpoints require Bearer JWT from auth-service. Entity and kind operations are owner-gated (book owner only can create/modify/delete).
- Entity kinds: **12 system-defined default kinds** seeded at startup across 3 genre groups — Universal (character, location, item, event, terminology), Fantasy (power_system, organization, species), Romance/Drama (relationship, plot_arc, trope, social_setting). All 12 are visible to all users in MVP regardless of genre. Custom kinds deferred to Phase 3 wave 2.
- Genre Profile: `genre_tags` field is stored on each kind as a forward-compatibility field. Genre Profile feature (admin/user-configurable genre presets that control kind visibility) is **explicitly out of scope** for Module 05 — see ADR `87` for architecture.
- Attribute definitions: per-kind defaults defined in code. Custom attribute definitions per kind deferred to Phase 3 wave 2.
- Translations: attribute values hold `original_language` + `translations[]` with `confidence` level (`verified` | `draft` | `machine`).
- Evidence: each attribute value can hold evidences (quote/summary/reference) pointing to a chapter + block/line location.
- Export: `GET /v1/glossary/books/{book_id}/export` produces a RAG-ready JSON payload.

---

## 2) Scope Definition

### In Scope (MVP)

- `glossary-service`: new Go/Gin service at port 8088.
  - Glossary entity CRUD (create, read, update, delete, status toggle).
  - Entity kind list (8 defaults, read-only in MVP).
  - Chapter-entity link management (link, unlink, update relevance/note).
  - Attribute value CRUD per entity (original language + value).
  - Translation CRUD per attribute value (add, update, remove; with confidence level).
  - Evidence CRUD per attribute value (add, update, remove; quote/summary/reference types).
  - Entity list with filter: by chapter IDs, kind codes, status, search query, tags.
  - RAG-ready JSON export per book.
- Gateway registration: `/v1/glossary/*` routed through `api-gateway-bff`.
- Frontend:
  - `/books/:bookId/glossary` — main glossary page (filter bar + entity list + slide-over detail panel).
  - `GlossaryPage`, `GlossaryFiltersBar`, `GlossaryEntityCard`, `EntityDetailPanel`.
  - `ChapterLinkEditor` within `EntityDetailPanel`.
  - `AttributeRow` with inline `TranslationList` and `EvidenceList`.
  - `AddTranslationModal`, `AddEvidenceModal`.
  - Navigation entry added to `BookDetailPage`.

### Out of Scope (this wave)

- Custom entity kind creation, editing, hiding, deleting (KindManager full CRUD).
- Custom attribute definition management per kind (add/remove/reorder fields per kind).
- Drag-and-drop attribute reorder (keyboard reorder deferred to Phase 3 wave 2).
- Full-text search index (Postgres/Elasticsearch) — MVP uses `ILIKE`.
- RAG context injection into Module 04 translation pipeline (Module 06).
- Import from external sources (Module 06+).
- Bulk entity operations (select multiple, mass-status-change, bulk delete).
- Public/shared glossary visibility (private-only in MVP).

---

## 3) Accountability Map

| Work item | Responsible | Accountable | Consulted | Informed |
| --- | --- | --- | --- | --- |
| Service design and contract | SA | SA | BE lead | PM |
| Glossary UX flow and entity kind defaults | PM | PM | SA, FE lead | Decision Authority |
| Backend implementation | BE lead | Execution Authority | SA | PM |
| Frontend implementation | FE lead | Execution Authority | PM, SA | QA lead |
| Acceptance test definition | QA lead | QA lead | PM, SA | Decision Authority |
| Rollout and risk controls | SRE | SRE | SA, QA | PM |
| Final readiness decision | Execution Authority | Decision Authority | PM, SA, QA, SRE | Governance Board |

---

## 4) DoR and DoD

### Definition of Ready (DoR)

- Module 05 contract draft is published and reviewed.
- Frontend flow spec is complete and aligned with contract.
- Risk and dependency doc identifies M01 and book-service dependency constraints.
- Service ownership and source structure are documented.
- Default entity kind schema (12 kinds across 3 genre groups + their attribute definitions) is finalized in contract.

### Definition of Done (DoD)

- Planning pack `75`–`86` is internally consistent.
- Catalog and roadmap include Module 05 references.
- MVP policy lock (12 default kinds across 3 genre groups, no custom kinds, `genre_tags` stored for future Genre Profile, ILIKE search, owner-gated) is reflected in all M05 docs.
- Readiness gate `86` is complete and decision-ready.

---

## 5) Governance Gates

| Gate | Trigger | Required evidence | Approver |
| --- | --- | --- | --- |
| Gate A — Contract freeze | `76` complete | Endpoint set, schema set, error taxonomy, default kinds schema | SA |
| Gate B — UX flow freeze | `77`, `83`, `84` complete | User journeys, states, component map, validation rules | PM |
| Gate C — Acceptance freeze | `78` complete | AT matrix, pass criteria, evidence format | QA lead |
| Gate D — Risk and rollout freeze | `79` complete | Risk controls, rollback, escalation, book-service dependency | SRE |
| Gate E — Integration freeze | `85` complete | Cross-service sequence and failure paths | SA + BE lead |
| Gate F — Implementation readiness | `86` complete | GO/NO-GO record | Decision Authority |

---

## 6) Dependencies

- **M01**: auth-service JWT (bearer auth for all `/v1/glossary/*` endpoints).
- **M02**: book-service book ownership validation (`GET /internal/books/{book_id}/projection`) and chapter list (`GET /internal/books/{book_id}/chapters`).
- `api-gateway-bff`: new route registration for `/v1/glossary/*`.

---

## 7) Downstream Pack (required before coding)

- `76_MODULE05_API_CONTRACT_DRAFT.md`
- `77_MODULE05_FRONTEND_FLOW_SPEC.md`
- `78_MODULE05_ACCEPTANCE_TEST_PLAN.md`
- `79_MODULE05_RISK_DEPENDENCY_ROLLOUT.md`
- `80_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE05.md`
- `81_MODULE05_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md`
- `82_MODULE05_BACKEND_DETAILED_DESIGN.md`
- `83_MODULE05_FRONTEND_DETAILED_DESIGN.md`
- `84_MODULE05_UI_UX_WIREFRAME_SPEC.md`
- `85_MODULE05_INTEGRATION_SEQUENCE_DIAGRAMS.md`
- `86_MODULE05_IMPLEMENTATION_READINESS_GATE.md`
- `87_MODULE05_GENRE_PROFILE_ARCHITECTURE_ADR.md` ← ADR: Genre Profile forward design (out of scope for M05, for reference only)
