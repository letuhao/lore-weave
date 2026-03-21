# Module 02 Microservice Source Structure Amendment

## Document Metadata

- Document ID: LW-M02-30
- Version: 1.3.0
- Status: Approved
- Owner: Solution Architect
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Amends monorepo layout for Module 02; MinIO/S3 for **raw** blobs; **Postgres** for chapter **draft + revisions** (book-service); **one database per microservice** (book / sharing / catalog).

## Change History

| Version | Date       | Change                                                         | Author    |
| ------- | ---------- | -------------------------------------------------------------- | --------- |
| 1.3.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 1.0.0   | 2026-03-21 | Initial M02 structure amendment                                | Assistant |
| 1.1.0   | 2026-03-21 | MinIO bucket/env, book-service owns S3 client, infra notes     | Assistant |
| 1.2.0   | 2026-03-21 | DB ownership: chapter_draft + chapter_revision; no Gitea in MVP path | Assistant |
| 1.3.0   | 2026-03-21 | **Database baseline:** dedicated **Postgres database per service** (book / sharing / catalog), not shared-schema multi-tenant in one DB | Assistant |

## 0) Authority Relationship

- **`17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md`** remains authoritative for **root** layout, branch/CI policy, and “no direct FE to service” rule.
- **This document** adds **Module 02** service roots, contract folders, **gateway route expectations**, and **object storage** touchpoints. If conflict, update this amendment — do not silently contradict `17`.

## 1) Recommended Service Roots (Target Architecture)

Aligned with `04_TECHSTACK_SERVICE_MATRIX.md`:

```text
services/
  api-gateway-bff/     # existing — proxy /v1/books, /v1/sharing, /v1/catalog
  auth-service/        # Module 01
  book-service/        # Module 02 — book CRUD, chapters, cover, MinIO client, chapter draft+revision persistence
  sharing-service/     # Module 02 — visibility + unlisted token issue/validate
  catalog-service/     # Module 02 — public projection / query
```

**Storage service split:** MVP assumes **`book-service` owns the S3-compatible client** (upload/delete/get for cover and chapter blobs, presign if used). A dedicated `storage-service` is **optional** and out of scope unless Decision Authority splits boundaries later.

**Implementation phasing note:** Execution may start with a **single Go module** combining domains behind one process for speed, as long as **OpenAPI boundaries** stay split and migration path to three binaries is documented in implementation PRs.

## 2) Object Storage (MinIO / S3-Compatible)

- **Dev (Docker Compose):** **MinIO** per `04_TECHSTACK_SERVICE_MATRIX.md`; typical console port **9001**, API **9000** (exact values fixed in `infra` / Compose at implementation time).
- **Bucket (draft name):** `loreweave-dev-books` (or env `BOOKS_STORAGE_BUCKET`); **one bucket** for covers and chapters with key prefixes (e.g. `covers/{book_id}/...`, `chapters/{book_id}/{chapter_id}`).
- **Environment variables (book-service, draft):**
  - `S3_ENDPOINT` / `MINIO_ENDPOINT` — internal URL (not exposed to browser)
  - `S3_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` — from secrets manager in prod; **never** logged or returned in API JSON
  - `BOOKS_STORAGE_BUCKET`
- **Flow:** `Frontend` → `ApiGatewayBff` → `book-service` → MinIO/S3. Gateway does not hold object-store credentials.

## 3) Contract Paths (Authoritative)

| Domain | Path |
| ------ | ---- |
| Books | `contracts/api/books/v1/openapi.yaml` |
| Sharing | `contracts/api/sharing/v1/openapi.yaml` |
| Catalog | `contracts/api/catalog/v1/openapi.yaml` |

## 4) Gateway External Route Table (Draft)

| Client path prefix | Upstream (logical) | Notes |
| ------------------ | ------------------ | ----- |
| `/v1/books` | `book-service` | JWT required; multipart for uploads; JSON for draft/revision routes per OpenAPI |
| `/v1/sharing` | `sharing-service` | JWT except `GET .../unlisted/...` |
| `/v1/catalog` | `catalog-service` | Anonymous allowed |

## 5) Database Ownership (Planning)

**Baseline (LoreWeave V1 planning):** each microservice has its **own Postgres database** — **`book-service`**, **`sharing-service`**, and **`catalog-service`** each use a **separate connection URL, migration history, and data store**. No cross-service foreign keys or shared tables; integration stays at the **API / projection** layer (e.g. catalog reads public fields from an app-level source of truth, not by joining `book-service` tables).

- **Blast radius:** failure or migration in one DB does not require touching the others; backup/restore and scaling can be per service.
- **Ops note:** in **local Compose**, that often means **three databases** on one Postgres **server** (three `DATABASE` names) or three DB containers — still **one logical DB per service** from an ownership perspective. Production may use separate instances per team policy; the contract is **per-service DB**, not “one monolithic schema for all domains.”
- **Book-service DB** additionally persists: `chapters` (incl. **`original_language`**); **`chapter_drafts`** (or columns on `chapters`: `draft_body`, `draft_format`, `draft_updated_at`, optional `draft_version`); **`chapter_revisions`** (snapshot rows: `revision_id`, `chapter_id`, `body`, `message`, `author_user_id`, `created_at`); cover metadata / `book_cover_assets`; **per-user storage usage** counter.
- **Sharing-service** and **catalog-service** DBs hold only their bounded tables (visibility, tokens, public projections, etc.) — exact ERD in implementation; must not depend on direct access to `book-service` tables.
- **Revision storage** for chapter text lives in **book-service Postgres** for MVP; **Gitea** is not part of this layout until an ADR adds it.
- Any departure (e.g. temporary single-server dev shortcut that blurs boundaries) needs an explicit **ADR or implementation note**; default for planning and `35` GO is **individual DB per microservice** with **one documented migration owner** per service.

## 6) CI / Path Ownership (Planning-Level)

- Contract changes under `contracts/api/books|sharing|catalog/v1/` require PCL review and Spectral lint (extend CI to lint all three files).
- Service code under `services/book-service/`, `sharing-service/`, `catalog-service/` should map to CODEOWNERS when introduced.

## 7) References

- `17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md`
- `25_MODULE02_API_CONTRACT_DRAFT.md`
- `28_MODULE02_RISK_DEPENDENCY_ROLLOUT.md`
- `04_TECHSTACK_SERVICE_MATRIX.md`
