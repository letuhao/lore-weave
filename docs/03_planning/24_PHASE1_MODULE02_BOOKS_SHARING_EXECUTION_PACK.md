# LoreWeave Phase 1 Module 02 Books & Sharing Execution Pack

## Document Metadata

- Document ID: LW-M02-24
- Version: 1.4.0
- Status: Approved
- Owner: Product Manager + Solution Architect
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Execution governance pack for Module 02: books with `original_language`, summary, cover, chapter `.txt` uploads, **canonical draft + revision history** in DB, object storage + quota, sharing/catalog—after Module 01.

## Change History


| Version | Date       | Change                                                                 | Author    |
| ------- | ---------- | ---------------------------------------------------------------------- | --------- |
| 1.4.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 1.0.0   | 2026-03-21 | Initial Module 02 charter                                              | Assistant |
| 1.1.0   | 2026-03-21 | In scope: chapters (txt), cover, summary, MinIO quota; AI/MIME deferred | Assistant |
| 1.2.0   | 2026-03-21 | `original_language` book+chapter; chapter **draft editor** + **Postgres revisions**; raw vs draft; Gitea out of MVP | Assistant |
| 1.3.0   | 2026-03-21 | Multilingual: **`GET …/chapters`** optional `original_language` / `sort_order`; review notes in `25` §7 | Assistant |
| 1.4.0   | 2026-03-21 | **Recycle bin:** logical delete book/chapter (**`trashed`**); **`purge_pending`** after delete from bin; **`GET /v1/books/trash`**; GC physical delete roadmap | Assistant |


## 1) Module Charter

### Module Name

Module 02 - Books & Sharing (Platform Core)

### Objective

Deliver the second vertical slice of Phase 1 platform core: authenticated users can create and manage books they own (including **`original_language`**, **summary**, **cover image**, and **multiple chapters** with **plain-text** file upload), **edit chapter drafts** (UTF-8 canonical text in the app DB) with **revision history**, stay within a **per-user storage quota**, **download** **original uploaded** chapter bytes separately from the edited draft, control visibility (`private` / `unlisted` / `public`), use share-link semantics for unlisted access, and browse books that policy allows in the public catalog—building on Module 01 identity tokens.

### Business Outcome

- Users can onboard books with stable identifiers, synopsis, visual cover, ordered chapter content, and **managed drafts** (import from `.txt`, then edit with history) suitable for later workflow/RAG and **future AI translate** (manual multi-language uploads per chapter row until then).
- Ownership and visibility rules prevent cross-tenant data leaks at the API boundary; **object keys** are not exposed in public or unlisted surfaces.
- Discoverability via catalog aligns with `03_V1_BOUNDARIES.md` (public browse; unlisted via token).

## 2) Scope Definition

### In Scope (MVP for this module)

- **Books (owned):** create book shell; **list active books**; **`GET /v1/books/trash`** for recycle bin; get/patch metadata (**patch** only when **active**); **`DELETE`** book → **trashed** (cascade chapters **trashed**); **`POST …/restore`**, **`DELETE …/purge`** (stage 2 **`purge_pending`**, await GC); including **title**, **description**, **`original_language`** (BCP-47, optional), **summary**. Field name **`original_language`** replaces former `primary_language` in OpenAPI (**breaking** for early clients).
- **Cover (MVP):** upload/replace/remove cover image; stored in **S3-compatible object storage** (MinIO in dev per `04_TECHSTACK_SERVICE_MATRIX.md`); metadata on book (`content_type`, `byte_size`, owner-facing download URL policy).
- **Chapters (MVP):** multiple chapters per book; upload content **only** as **`text/plain`** (`.txt`); each chapter has required **`original_language`** (BCP-47) for the uploaded/edited content; metadata: **sort order**, optional **title**, `original_filename`, `byte_size`, internal `storage_key` (server-side only); **list** supports optional **`lifecycle_state`**, **`original_language`**, **`sort_order`**; **`DELETE`** chapter → **trashed** (retains storage + draft + revisions until GC after **purge**); **`POST …/restore`**, **`DELETE …/purge`**; list/get/patch per `25` when **active**; **GET** **original upload** bytes for **owner** (unchanged file in object storage—**not** the edited draft).
- **Chapter draft + revisions (MVP):** after upload, server **seeds** canonical **draft** text (UTF-8) from file content; owner uses **GET/PATCH …/draft** to edit; each meaningful save creates an app-managed **revision** snapshot in Postgres (`GET …/revisions`, `GET …/revisions/{id}`, `POST …/restore`). **MVP versioning = revision table**, not Git.
- **Storage quota (MVP):** per-user byte limit (free tier); enforce on uploads; error `STORAGE_QUOTA_EXCEEDED` (see `25`); **usage** endpoint for UI (`GET` storage-usage).
- **Sharing / visibility:** set and read visibility enum; issue/rotate opaque **share token** for `unlisted`; enforce that `private` is never returned to non-owners via catalog; **trashed** / **`purge_pending`** books are **not** readable on public/unlisted/catalog (**404**).
- **Catalog:** list/query books visible as `public` and **lifecycle active**; optional **summary excerpt**, **has_cover** / **cover_url** policy; pagination; consistent error shape with Module 01 (`code` + `message`).

### Object storage & quota (architecture note)

- **MinIO** (or S3) bucket naming, env vars, and gateway-to-service routing are specified in **`30`** and runbook (`implementation` / Compose when implemented).
- Gateway must not expose storage secrets; presigned URLs (if used) are short-lived and issued server-side.

### Out of Scope

- **AI-generated** cover or summary (roadmap after RAG/workflow stabilizes); optional reserved hooks described in `33`/`34` only as placeholders.
- **AI translate** of chapters into other locales (roadmap); until then users add **another chapter row** per language (same or different `sort_order` per UX; uniqueness in `31`).
- **Integrated Git server** (e.g. self-host **Gitea**) as backing store for chapter history—**roadmap / ADR**; MVP uses **Postgres revision snapshots** only.
- **Non-text** chapter formats: PDF, DOCX, HTML, images—**roadmap** (MIME allow-list table in `25`/`31`).
- **Paid storage tiers / billing**—roadmap; MVP is one free quota per user.
- Workflow jobs, RAG ingest, embeddings (Phase 2).
- Rich collaboration (co-authors, org libraries), comments, reviews.
- Full design-system polish beyond reuse of existing `frontend/` shell (separate UI plan if needed).
- Production CDN, multi-region, advanced search ranking.
- **Garbage collector** worker that physically deletes **`purge_pending`** rows and MinIO objects (batch job; **API only marks eligibility** in MVP contract).

### Architecture decision (recorded for implementation)

- **Three bounded OpenAPI documents** under `contracts/api/books/v1/`, `contracts/api/sharing/v1/`, `contracts/api/catalog/v1/` (see `25_MODULE02_API_CONTRACT_DRAFT.md`). Backend may still be one or three deployable services; contract split matches `04_TECHSTACK_SERVICE_MATRIX.md` intent. **Book service** may own the S3/MinIO client unless a separate storage service is introduced (document choice in `30`).

### Share link (MVP)

- API exposes **opaque unlisted access token** (and optional human slug); browser URL shape is a **frontend routing** concern documented in `26`/`32`, not required in OpenAPI literal path unless gateway exposes a dedicated resolve endpoint (see `25`).

## 3) Role and Accountability Map


| Work Item                    | Responsible         | Accountable        | Consulted             | Informed           |
| ---------------------------- | ------------------- | ------------------ | --------------------- | ------------------ |
| Module scope and acceptance  | BA, SA              | PM                 | QAL, SRE, SCO         | Decision Authority |
| API contract draft           | SA, PCL             | SA                 | QAL, SRE, SCO         | PM                 |
| Frontend flow spec           | BA, PCL             | PM                 | SA, QAL               | Decision Authority |
| Acceptance and gate evidence | QAL                 | QAL                | SA, PCL, SRE          | PM                 |
| Rollout/rollback planning    | SRE                 | SRE                | SA, QAL, SCO          | PM                 |
| Final module sign-off        | Execution Authority | Decision Authority | PM, SA, QAL, SRE, SCO | Governance Board   |


## 4) DoR and DoD

### 4.1 Definition of Ready (DoR)

- Module charter (this document) approved for execution planning.
- API contract draft exists for all in-scope flows (`25` + OpenAPI folders), including chapters, cover, storage usage, **draft**, **revisions**.
- Frontend flow spec exists and maps journeys to endpoints (`26`).
- Dependency and risk owners are named (`28`).
- Acceptance scenarios and evidence expectations exist (`27`).

### 4.2 Definition of Done (DoD)

- Contract, frontend flow, acceptance, risk, deep-design (`30`–`34`), and readiness gate (`35`) are internally consistent.
- Governance checklist (`29`) satisfied or waived with Decision Authority record.
- Catalog and roadmap reference Module 02 pack.
- Decision Authority records outcome on `35` before implementation start.

## 5) Weekly Scrumban Cadence (Module 02)

- Planning Gate: confirm in-scope stories align with `24`–`28`.
- Execution Flow: progress contracts and UX artifacts under WIP limits.
- Review Gate: traceability to `03_V1_BOUNDARIES.md` and M01 identity dependencies.
- Decision Gate: close, carry over, or re-scope.

## 6) Governance Gates


| Gate                              | Trigger                         | Required Evidence                                     | Approver                 |
| --------------------------------- | ------------------------------- | ----------------------------------------------------- | ------------------------ |
| Gate A - Contract freeze          | `25` + OpenAPI complete for MVP | Endpoint list, schemas, error taxonomy                | SA                       |
| Gate B - UI flow freeze           | `26` complete                   | Journeys + API mapping                                | PM                       |
| Gate C - Acceptance               | `27` complete                   | Scenario matrix + pass criteria                       | QAL                      |
| Gate D - Rollout                  | `28` complete                   | Risks, rollback, Compose notes                        | SRE + Decision Authority |
| Gate E - Deep-design              | `30`–`34` complete              | Source amendment, BE/FE design, wireframes, sequences | PM + SA                  |
| Gate F - Implementation readiness | `35` GO                         | Completed readiness gate                              | Decision Authority       |


## 7) Dependencies

- **Module 01:** Valid access tokens and identity; contract `contracts/api/identity/v1/`.
- `03_V1_BOUNDARIES.md`, `04_TECHSTACK_SERVICE_MATRIX.md`, `17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md` (extended by `30`).
- **Object storage:** MinIO (dev) or S3-compatible backend; bucket and credentials via env (see `30`, implementation runbook).
- `05_WORKING_MODEL_SCRUMBAN.md`, `06_OPERATING_RACI.md`.

## 8) Module Closure Sign-Off


| Field                      | Value                        |
| -------------------------- | ---------------------------- |
| Module ID                  | Phase1-Module02-BooksSharing |
| Closure Date               |                              |
| PM Recommendation          |                              |
| SA Recommendation          |                              |
| QAL Readiness Statement    |                              |
| SRE Readiness Statement    |                              |
| Decision Authority Outcome |                              |


## 9) Downstream Pack (Pre-Implementation)

Required before code start:

- `25_MODULE02_API_CONTRACT_DRAFT.md` and governed OpenAPI under `contracts/api/{books,sharing,catalog}/v1/`.
- `26_MODULE02_FRONTEND_FLOW_SPEC.md`
- `27_MODULE02_ACCEPTANCE_TEST_PLAN.md`
- `28_MODULE02_RISK_DEPENDENCY_ROLLOUT.md`
- `29_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE02.md`
- `30_MODULE02_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md`
- `31_MODULE02_BACKEND_DETAILED_DESIGN.md`
- `32_MODULE02_FRONTEND_DETAILED_DESIGN.md`
- `33_MODULE02_UI_UX_WIREFRAME_SPEC.md`
- `34_MODULE02_INTEGRATION_SEQUENCE_DIAGRAMS.md`
- `35_MODULE02_IMPLEMENTATION_READINESS_GATE.md`

## 10) Notes

- Planning-only; no implementation code in this pack.
- Downstream of Module 01: **no anonymous book mutations** except where explicitly public catalog read-only.
