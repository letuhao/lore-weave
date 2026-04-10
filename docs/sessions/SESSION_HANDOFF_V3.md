# Session Handoff — Session 30

> **Purpose:** Give the next agent complete context to continue.
> **Date:** 2026-04-10 (session 30 end)
> **Last commit:** `0a07766` — fix: post-review fixes for GEP extraction pipeline (10 issues)
> **Uncommitted work:** None
> **Previous focus:** Translation Pipeline V2 (session 29), GEP design (session 30 start)
> **Current focus:** Glossary Extraction Pipeline — BACKEND COMPLETE + REVIEWED

---

## 1. What Happened This Session (10 commits)

| Commit | What |
|--------|------|
| `7231988` | GEP-BE-01 — alive flag + extraction_audit_log migration (glossary-service) |
| `b1d31e7` | GEP-BE-06 — extraction_profile JSONB on books (book-service) |
| `587ea4b` | GEP-BE-02 — extraction profile endpoint (glossary-service) |
| `92ae237` | GEP-BE-04 + BE-05 — known entities endpoint + alive toggle (glossary-service) |
| `1d29359` | GEP-BE-03 — bulk upsert endpoint for extracted entities (glossary-service) |
| `431ca1d` | GEP-BE-07+08+11 — extraction preprocessor, prompt builder, glossary client (translation-service) |
| `e666605` | GEP-BE-09+10 — extraction worker + job endpoints (translation-service) |
| `f531a19` | GEP-BE-12 — extraction proxy routes (api-gateway-bff) |
| `a081665` | Session 30 start — design complete, UI draft, task plan |
| `0a07766` | Post-review fixes — 10 issues (3 critical, 4 high, 3 medium) |

**Services touched:** glossary-service, book-service, translation-service, api-gateway-bff

---

## 2. Glossary Extraction Pipeline — What Was Built

### Task Status (GEP-BE)

| Task | Description | Service | Status |
|------|-------------|---------|--------|
| BE-01 | alive flag + extraction_audit_log migration | glossary-service | ✅ |
| BE-02 | Extraction profile endpoint (public + internal) | glossary-service | ✅ |
| BE-03 | Bulk upsert extracted entities | glossary-service | ✅ |
| BE-04 | Known entities endpoint (3-layer filtering) | glossary-service | ✅ |
| BE-05 | Alive toggle on entity PATCH | glossary-service | ✅ |
| BE-06 | extraction_profile JSONB on books table | book-service | ✅ |
| BE-07 | Tiptap→text preprocessor | translation-service | ✅ |
| BE-08 | Prompt builder + auto-batching | translation-service | ✅ |
| BE-09 | Extraction worker (sequential chapters) | translation-service | ✅ |
| BE-10 | Job creation + cancellation endpoints | translation-service | ✅ |
| BE-11 | Glossary client (3 new functions) | translation-service | ✅ |
| BE-12 | Gateway proxy for /v1/extraction | api-gateway-bff | ✅ |
| BE-13 | Integration test | — | ⏳ Deferred (needs Docker) |

### Key Files

**glossary-service (Go):**
- `internal/api/extraction_handler.go` — **NEW** — extraction profile, known entities, bulk upsert with dedup/merge
- `internal/api/entity_handler.go` — MODIFIED — alive field in PATCH
- `internal/api/server.go` — MODIFIED — 3 internal + 1 public extraction routes
- `internal/migrate/migrate.go` — MODIFIED — alive column, extraction_audit_log table

**book-service (Go):**
- `internal/api/server.go` — MODIFIED — extraction_profile JSONB (PATCH + GET + projection)
- `internal/migrate/migrate.go` — MODIFIED — extraction_profile column

**translation-service (Python):**
- `app/workers/extraction_preprocessor.py` — **NEW** — Tiptap JSON → structured text
- `app/workers/extraction_prompt.py` — **NEW** — prompt templates, auto-batching, parse+validate, cost estimation
- `app/workers/extraction_worker.py` — **NEW** — sequential chapter processing, cooperative cancellation
- `app/workers/glossary_client.py` — MODIFIED — 3 new async client functions
- `app/routers/extraction.py` — **NEW** — job creation (202), cancel, status endpoints
- `app/migrate.py` — MODIFIED — extraction_jobs + extraction_chapter_results tables
- `app/broker.py` — MODIFIED — extraction.jobs queue
- `app/main.py` — MODIFIED — extraction router registration

**api-gateway-bff (TypeScript):**
- `src/gateway-setup.ts` — MODIFIED — extraction proxy route

### Architecture Highlights

- **Sequential processing:** Unlike translation (parallel chapters), extraction processes chapters sequentially to accumulate known entities cross-chapter
- **Auto-batching:** Groups entity kinds by schema token budget (2000 tokens) to determine LLM calls per chapter
- **3-layer filtering for known entities:** alive flag + frequency (chapter_entity_links COUNT) + recency window
- **Normalized dedup:** NFC Unicode + trim + collapse whitespace + lowercase, app-layer alias JSON parsing
- **Fill/overwrite semantics:** Per-attribute action (skip/fill/overwrite) with audit trail
- **Cooperative cancellation:** Worker checks job status in DB between chapters
- **Cost estimation:** Token-based pre-job estimate returned in 202 response (approximate per design §6.7.1)

---

## 3. Post-Review Fixes Applied

3 parallel review agents examined all new code. 10 real issues found and fixed:

| ID | Severity | Issue | Fix |
|----|----------|-------|-----|
| C1 | Critical | Wrong config: `provider_registry_url` | → `provider_registry_service_url` |
| C2 | Critical | Silent `_, _` on 4 DB inserts | → `slog.Warn` on all 4 |
| C3 | Critical | Missing `json.RawMessage` cast | → Cast in both book-service GET responses |
| H1 | High | No top-level try/except in worker | → Split into handler + inner runner |
| H2 | High | Silent batch failure | → Log with batch index + kind codes |
| H3 | High | Unbounded known_entities growth | → Capped at 200 |
| H4 | High | `import json` inside function | → Moved to top-level |
| M1 | Medium | Hardcoded cost without context | → Added design reference comment |
| M2 | Medium | `ent.pop()` mutates parsed dict | → Changed to `ent.get()` |
| M3 | Medium | No upper bound on query params | → Clamp recency≤1000, limit≤500 |

---

## 4. What's Next

### Immediate candidates

| Priority | Item | Notes |
|----------|------|-------|
| **P0** | **GEP-BE-13: Integration test** | Requires Docker Compose stack. Test full flow: create job → worker processes → entities in glossary |
| **P1** | **GEP-FE-01..07: Frontend** | 7 FE tasks for extraction UI (profile editor, job launcher, progress, results). Design doc + UI draft HTML exist |
| **P2** | **Translation quality review** | Read actual translated chapters, check glossary name accuracy |
| **P3** | **Quality dashboard** | validation_errors, retry_count, glossary_corrections data now in DB |

### GEP Frontend Tasks (not started)

| Task | Description |
|------|-------------|
| FE-01 | Extraction profile editor (kind/attribute matrix) |
| FE-02 | Chapter selection for extraction |
| FE-03 | Job launcher with cost estimate preview |
| FE-04 | Job progress (SSE events) |
| FE-05 | Results review (entities found per chapter) |
| FE-06 | Entity merge/edit from extraction results |
| FE-07 | Extraction history |

### Known issues

1. **GEP-BE-13 deferred:** Integration test needs running services (book-service, glossary-service, translation-service, provider-registry, Redis, Postgres)
2. **Pre-existing test failures:** 5 `test_chapter_worker.py` tests fail due to `db.transaction()` async mock issue — not GEP-related
3. **Glossary entry status:** New entities default to `draft` status. Must be set to `active` to appear in translation glossary

---

## 5. Design Doc Reference

Full GEP design: `docs/03_planning/M05_glossary/GLOSSARY_EXTRACTION_PIPELINE.md` (1500+ lines)
- §4.2: Extraction profile auto-resolve by genre
- §5.2-5.3: API endpoints
- §6.6: Worker architecture
- §7: Prompt engineering (system/user separation, known entities context)
- §6.7.1: Cost estimation approach

UI draft: `docs/03_planning/M05_glossary/ui-draft-extraction.html`

---

## 6. Project Constants (unchanged)

```
frontend_port:   5173
gateway_port:    3123 (mapped from 3000)
glossary_port:   8211 (mapped from 8088)
translation_port: 8210 (mapped from 8087)
```
