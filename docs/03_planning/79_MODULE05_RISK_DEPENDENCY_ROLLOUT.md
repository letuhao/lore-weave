# LoreWeave Module 05 Risk, Dependency, and Rollout Plan

## Document Metadata

- Document ID: LW-M05-79
- Version: 0.1.0
- Status: Draft
- Owner: SRE + Solution Architect
- Last Updated: 2026-03-23
- Approved By: —
- Approved Date: —
- Summary: Risk register, dependency map, and rollout/rollback controls for Module 05 glossary and lore management.

## Change History

| Version | Date       | Change                                    | Author    |
| ------- | ---------- | ----------------------------------------- | --------- |
| 0.1.0   | 2026-03-23 | Initial Module 05 risk and rollout doc    | Assistant |

---

## 1) Dependency Map

### Hard Prerequisites

| Dependency | Required state | Risk if unavailable |
| --- | --- | --- |
| M01 auth-service | Operational (JWT issue + verify) | All `/v1/glossary/*` endpoints return 401 |
| M02 book-service | `/internal/books/{book_id}/projection` available (book ownership + lifecycle validation) | glossary-service cannot validate book ownership; entity creation blocked |
| M02 book-service | `/internal/books/{book_id}/chapters` available (chapter list) | Chapter link validation (`GLOSS_CHAPTER_NOT_IN_BOOK`) cannot be enforced; frontend chapter pickers empty |
| api-gateway-bff | `/v1/glossary/*` route registered | Glossary API unreachable from frontend |

### Soft Dependencies

| Dependency | Impact if missing |
| --- | --- |
| M04 translation-service | No impact on glossary MVP; RAG export will exist but not be consumed by translation pipeline until Module 06 |
| MinIO (book-service asset storage) | No impact; glossary-service stores data in its own Postgres DB only |

---

## 2) Risk Register

| ID | Risk | Severity | Likelihood | Mitigation |
| --- | --- | --- | --- | --- |
| R-M05-01 | book-service internal endpoint schema changes break ownership/chapter validation | Medium | Low | Integration test verifies endpoint contracts before M05 deployment; coordinate with M02 owner on any breaking changes |
| R-M05-02 | Large glossaries (1000+ entities) with complex filters cause slow list queries | Medium | Medium | Add composite index on `(book_id, kind_id, status)` and `(book_id, updated_at)`; ILIKE search is known to be slow at scale — acceptable for MVP; full-text search planned for Phase 3 wave 2 |
| R-M05-03 | Cascade delete on entity takes too long for entities with many attribute values/evidences | Low | Low | Postgres FK cascade delete is efficient; monitor query time; add timeout guard at service layer if > 5s |
| R-M05-04 | Attribute value auto-population on entity creation fails silently for new kind with missing attribute definitions | High | Low | Service-level validation: if kind has no default attributes defined (e.g., data corruption), return `GLOSS_INVALID_KIND_CODE` and log error; fail loudly |
| R-M05-05 | Frontend EntityDetailPanel accumulates stale state when navigating between entities quickly | Medium | Medium | Always refetch entity detail on panel open; do not reuse cached entity for different `entity_id` |
| R-M05-06 | RAG export for large book (500+ entities) is slow or times out | Medium | Low | Add pagination to export (default limit=500); for Phase 3 wave 2 consider streaming export; current timeout: 30s |
| R-M05-07 | loreweave_glossary DB not created on first boot | Low | Low | DB bootstrap script (`01-databases.sql`) must include `loreweave_glossary`; service startup migration will fail loudly if DB missing |
| R-M05-08 | Duplicate translation language enforcement is only at DB level (no application-level check) | Medium | Low | Application-level check before INSERT in service handler; DB unique constraint as final guard |
| R-M05-09 | M06 (RAG injection) assumes specific JSON structure from export endpoint | Medium | Medium | Export schema is versioned (`glossary_version: "1.0"`); do not break schema without bumping version; document schema stability guarantee |

---

## 3) Rollout Plan

### Rollout Sequence

1. Apply DB migration: `loreweave_glossary` database created via bootstrap; tables created via migration runner on service start.
2. Seed default entity kinds: 8 default kinds inserted if not present (idempotent seed on startup).
3. Deploy `glossary-service` (Docker Compose `docker compose up glossary-service --build`).
4. Apply gateway config: `api-gateway-bff` restart with `GLOSSARY_SERVICE_URL` env set.
5. Verify health: `GET http://localhost:8088/health` returns 200.
6. Smoke test kinds: `GET /v1/glossary/kinds` returns 8 items.
7. Smoke test entity creation: create one character entity, verify attribute values populated.
8. Full frontend deployment after backend smoke passes.

### Feature Flag / Dark Launch

No feature flag mechanism in MVP. Glossary feature gated by:
- Navigation link in `BookDetailPage` (can be commented out for dark launch).
- Route `/books/:bookId/glossary` not advertised until backend smoke passes.

### Phased Rollout (if needed)

- Phase A: Backend only — smoke test via API before adding frontend nav link.
- Phase B: Add nav link and test with internal users.
- Phase C: General availability.

---

## 4) Rollback Plan

| Scenario | Rollback action |
| --- | --- |
| glossary-service fails to start | Remove from docker-compose; gateway loses route; other services unaffected |
| DB migration fails on startup | Fix migration script; restart service; no data loss (migration is additive) |
| Critical bug in entity CRUD | Remove nav link from BookDetailPage; service remains up but unreachable from UI |
| book-service internal endpoint breaking change | Pin book-service to last compatible version; coordinate fix before re-enabling |

---

## 5) Post-Rollout Monitoring

| Signal | Threshold | Action |
| --- | --- | --- |
| glossary-service 5xx rate | > 1% over 5 min | Alert SRE; investigate logs |
| Entity list query P95 latency | > 2s | Review slow query log; add index if needed |
| RAG export latency | > 10s | Alert; check entity count; consider adding limit |
| DB connection pool exhaustion | > 80% | Scale pool size or add read replica |
