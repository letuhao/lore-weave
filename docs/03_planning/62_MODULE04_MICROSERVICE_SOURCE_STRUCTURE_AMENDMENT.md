# LoreWeave Module 04 Microservice Source Structure Amendment

## Document Metadata

- Document ID: LW-M04-62
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-22
- Summary: Source-structure amendment for Module 04 introducing translation-service (Python/FastAPI) and the associated contract path.

## Change History

| Version | Date       | Change                                         | Author    |
| ------- | ---------- | ---------------------------------------------- | --------- |
| 0.1.0   | 2026-03-22 | Initial Module 04 source structure amendment   | Assistant |

## 1) Purpose

Extend the monorepo with the `translation-service` bounded context and its contract path while preserving all existing service boundaries and contract conventions.

## 2) New Service

| Service | Responsibility | Language / Runtime |
| --- | --- | --- |
| `translation-service` | Per-user/per-book translation settings, async translation job lifecycle, chapter result storage, prompt template management | Python / FastAPI |

Gateway routes composed through `api-gateway-bff` (`/v1/translation/*` → port 8087).

## 3) Proposed Monorepo Layout

```text
services/
  translation-service/           ← NEW
    Dockerfile
    requirements.txt
    app/
      main.py                    — FastAPI app factory, lifespan hooks
      config.py                  — pydantic-settings (env vars)
      database.py                — asyncpg pool management
      migrate.py                 — DDL migration runner (runs on startup)
      auth.py                    — mint_user_jwt() for service-to-gateway auth
      models.py                  — Pydantic request/response models
      routers/
        settings.py              — preferences + book settings endpoints
        jobs.py                  — job CRUD + chapter result endpoints
      services/
        translation_runner.py    — background task: fetch → prompt → invoke → store

contracts/
  api/
    translation/                 ← NEW
      v1/
        openapi.yaml             — OpenAPI spec for /v1/translation/*
        README.md
```

## 4) Data Ownership

`translation-service` owns:
- `user_translation_preferences` table (per-user defaults),
- `book_translation_settings` table (per-book overrides),
- `translation_jobs` table (job lifecycle and settings snapshot),
- `chapter_translations` table (per-chapter results and status).

`translation-service` reads from (does not own):
- `book-service` internal endpoint — chapter draft text (read-only, no writes).
- `provider-registry-service` invoke endpoint — model dispatch (write-through; billing recorded on that service's side).

## 5) Internal Integration Points

| Integration | Direction | Protocol | Notes |
| --- | --- | --- | --- |
| `book-service` `/internal/books/{book_id}/chapters/{chapter_id}` | translation → book | HTTP GET | No auth required on internal route |
| `book-service` `/internal/books/{book_id}/projection` | translation → book | HTTP GET | Used to validate book ownership before job creation |
| `provider-registry-service` `/v1/model-registry/invoke` | translation → registry | HTTP POST (JWT Bearer) | JWT minted by translation-service using JWT_SECRET |
| `api-gateway-bff` | gateway → translation | HTTP proxy | Path prefix `/v1/translation/*` |

## 6) Database

- Database name: `loreweave_translation`
- Created by: `infra/postgres-init/01-databases.sql` (Docker init) and `postgres-db-bootstrap` service.
- Migration: translation-service runs DDL on startup via `migrate.py`.

## 7) Guardrails

- Translation-service must not call provider SDK clients directly — all model invocations through `/v1/model-registry/invoke`.
- Translation-service must not write to `book-service` tables directly — no DB-level coupling.
- JWT minted by translation-service must have TTL ≤ 300 seconds and must be re-minted if within 30 s of expiry.
- `user_prompt_tpl` stored in settings must be validated to contain `{chapter_text}` before persisting.
- All job settings fields (model, prompts, target language) must be snapshotted at job creation — settings changes after job start do not affect the running job.

## 8) Ports

| Service | Port |
| --- | --- |
| translation-service | 8087 |
