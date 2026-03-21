# LoreWeave Module 02 API Contract Draft (Books, Sharing, Catalog)

## Document Metadata

- Document ID: LW-M02-25
- Version: 1.4.0
- Status: Approved
- Owner: Solution Architect
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Draft API for Module 02: multilingual-friendly **`original_language`**, optional **`GET …/chapters`** filters, **two-stage logical delete** (recycle bin + **`purge_pending`** for future GC), summary, cover, chapter `.txt`, draft/revisions, MinIO, quota, sharing/catalog. OpenAPI `contracts/api/{books,sharing,catalog}/v1/`.

## Change History


| Version | Date       | Change                                                                 | Author    |
| ------- | ---------- | ---------------------------------------------------------------------- | --------- |
| 1.4.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 1.0.0   | 2026-03-21 | Initial Module 02 contract draft                                       | Assistant |
| 1.1.0   | 2026-03-21 | Chapters (txt MVP), cover, summary, storage usage, catalog/share payloads | Assistant |
| 1.2.0   | 2026-03-21 | **`original_language`** (book + chapter); **draft/revision** endpoints; **`primary_language` removed** (breaking) | Assistant |
| 1.3.0   | 2026-03-21 | Multilingual review: **`GET …/chapters`** optional `original_language` + `sort_order` query; §7 model notes + OQ grouping/catalog languages | Assistant |
| 1.4.0   | 2026-03-21 | **Recycle bin:** `lifecycle_state` on book/chapter; **`DELETE`** book/chapter → **trashed**; **`POST …/restore`**, **`DELETE …/purge`**; **`GET /v1/books/trash`**; list chapters optional **`lifecycle_state`**; catalog/unlisted hide trashed/**`purge_pending`** (**404**); books OpenAPI **1.4.0** | Assistant |


## 1) Contract Scope

This draft defines gateway-exposed behavior for:

- **Books:** create, list (owner, **active only**), **list recycle bin** (`GET /v1/books/trash` — **`trashed`** only), get by id (owner may read **active** or **trashed**; **`purge_pending`** → **404** until GC removes the row), patch metadata (**409** if book not **active**); **`DELETE /v1/books/{id}`** → **logical stage 1** (move to recycle bin, **cascade** all chapters to **`trashed`**); **`POST …/restore`**, **`DELETE …/purge`** (stage 2 → **`purge_pending`**, still logical; **physical delete** by future garbage collector only); **`original_language`** (BCP-47, optional); **summary**; **cover**; **chapters** as sub-resources; **per-user quota** and **storage usage**; **download original upload** vs **edit canonical draft** (see below).
- **Chapter draft & revisions:** **UTF-8** working copy stored in the **application database**; **GET/PATCH …/draft**; **revision history** via **GET …/revisions**, **GET …/revisions/{revision_id}**, **POST …/revisions/{revision_id}/restore**. Raw bytes in MinIO/S3 remain the **imported file**, not overwritten by editor saves (unless product later changes policy—default **no**).
- **Sharing:** read/update visibility; **unlisted** resolve by opaque token.
- **Catalog:** list/get **`public`** books.

**Out of scope (implementation):** AI-generated cover/summary; **AI chapter translate** (users add another `Chapter` row per language until then); **Gitea/Git** as revision backend; non-text chapter MIME; paid tiers; **garbage collector job** that removes **`purge_pending`** rows and MinIO objects (specified as roadmap; API only marks eligibility).

**Breaking (1.2.0):** JSON field **`primary_language`** renamed to **`original_language`** on book and on sharing/catalog payloads—align clients.

**Breaking (1.4.0):** **`DELETE …/chapters/{id}`** is **soft delete** (recycle bin), not immediate physical removal; responses include **`lifecycle_state`**, **`trashed_at`**, **`purge_eligible_at`** on **`Book`** and **`Chapter`**. Clients must use **`POST …/restore`** and **`DELETE …/purge`** for chapter lifecycle; **`operationId`** for chapter delete is **`trashChapter`** (was **`deleteChapter`**).

**Auth:** Bearer JWT from Module 01 for owner paths; unlisted path uses opaque token.

**Monorepo sources of truth:**


| API surface | OpenAPI path                            |
| ----------- | --------------------------------------- |
| Books       | `contracts/api/books/v1/openapi.yaml`   |
| Sharing     | `contracts/api/sharing/v1/openapi.yaml` |
| Catalog     | `contracts/api/catalog/v1/openapi.yaml` |


OpenAPI files are **authoritative** for names and HTTP details.

## 2) Endpoint Set (Draft)

### 2.1 Books (`books` spec)


| Endpoint                                                 | Method | Auth   | Purpose                                                                 |
| -------------------------------------------------------- | ------ | ------ | ----------------------------------------------------------------------- |
| `/v1/books/storage-usage`                                | GET    | Bearer | `used_bytes` / `quota_bytes`                                            |
| `/v1/books`                                              | POST   | Bearer | Create book shell (`original_language`, summary, …)                     |
| `/v1/books`                                              | GET    | Bearer | List owned books (**`active`** only)                                    |
| `/v1/books/trash`                                        | GET    | Bearer | List books in recycle bin (**`lifecycle_state` = `trashed`**)           |
| `/v1/books/{book_id}`                                    | GET    | Bearer | Get book (owner); **`purge_pending`** → **404**                         |
| `/v1/books/{book_id}`                                    | PATCH  | Bearer | Patch metadata (**409** if not **active**)                            |
| `/v1/books/{book_id}`                                    | DELETE | Bearer | Move book to recycle bin (**trashed**); cascade chapters **trashed**   |
| `/v1/books/{book_id}/restore`                            | POST   | Bearer | Restore book + chapters to **active**                                   |
| `/v1/books/{book_id}/purge`                             | DELETE | Bearer | Stage 2: **`purge_pending`** (await GC); hidden from trash list       |
| `/v1/books/{book_id}/cover`                              | POST   | Bearer | Upload/replace cover                                                    |
| `/v1/books/{book_id}/cover`                              | DELETE | Bearer | Remove cover                                                            |
| `/v1/books/{book_id}/chapters`                           | GET    | Bearer | List chapters; optional **`lifecycle_state`**, **`original_language`**, **`sort_order`** (defaults described in OpenAPI) |
| `/v1/books/{book_id}/chapters`                           | POST   | Bearer | Create chapter + **multipart** file + **required `original_language`** |
| `/v1/books/{book_id}/chapters/{chapter_id}`              | GET    | Bearer | Chapter metadata                                                        |
| `/v1/books/{book_id}/chapters/{chapter_id}`              | PATCH  | Bearer | title, `sort_order`, `original_language`                                |
| `/v1/books/{book_id}/chapters/{chapter_id}`              | DELETE | Bearer | Move chapter to recycle bin (**trashed**); retains MinIO + draft + revisions until GC after **purge** |
| `/v1/books/{book_id}/chapters/{chapter_id}/restore`      | POST   | Bearer | Restore chapter from bin (parent book must be **active**)             |
| `/v1/books/{book_id}/chapters/{chapter_id}/purge`        | DELETE | Bearer | Stage 2: chapter **`purge_pending`** (await GC)                        |
| `/v1/books/{book_id}/chapters/{chapter_id}/content`      | GET    | Bearer | **Original uploaded** file bytes (not draft)                            |
| `/v1/books/{book_id}/chapters/{chapter_id}/draft`       | GET    | Bearer | Canonical draft for editor (`body`, `draft_format`, …)                  |
| `/v1/books/{book_id}/chapters/{chapter_id}/draft`       | PATCH  | Bearer | Replace draft + append revision; optional `commit_message`, concurrency |
| `/v1/books/{book_id}/chapters/{chapter_id}/revisions`    | GET    | Bearer | List revision metadata                                                  |
| `/v1/books/{book_id}/chapters/{chapter_id}/revisions/{revision_id}` | GET | Bearer | Revision snapshot including `body`                                      |
| `/v1/books/{book_id}/chapters/{chapter_id}/revisions/{revision_id}/restore` | POST | Bearer | Restore draft from snapshot; adds new revision                        |


### 2.2 Sharing (`sharing` spec)


| Endpoint                              | Method | Auth   | Purpose                                                                                       |
| ------------------------------------- | ------ | ------ | --------------------------------------------------------------------------------------------- |
| `/v1/sharing/books/{book_id}`         | GET    | Bearer | Read policy                                                                                   |
| `/v1/sharing/books/{book_id}`         | PATCH  | Bearer | Set visibility / rotate token                                                                 |
| `/v1/sharing/unlisted/{access_token}` | GET    | None   | Minimal payload; includes **`original_language`** (not `primary_language`)                     |


### 2.3 Catalog (`catalog` spec)


| Endpoint                      | Method | Auth            | Purpose                |
| ----------------------------- | ------ | --------------- | ---------------------- |
| `/v1/catalog/books`           | GET    | Optional Bearer | List public books      |
| `/v1/catalog/books/{book_id}` | GET    | Optional Bearer | Get public book        |


`PublicBook` / `UnlistedBookPayload` use **`original_language`** plus optional excerpt/cover fields per OpenAPI.

**Catalog / unlisted / public:** Books with **`lifecycle_state`** **`trashed`** or **`purge_pending`** are **not** discoverable — list/get behave as **unknown** (**404**). Sharing policy endpoints should treat the same (see sharing OpenAPI description).

## 3) Core Schemas (Draft)

### Book

- `book_id`, `owner_user_id`, `title`, optional `description`, **`original_language`** (BCP-47), `summary`, `cover`, `chapter_count`, **`lifecycle_state`** (`active` \| `trashed` \| `purge_pending`), optional **`trashed_at`**, optional **`purge_eligible_at`** (set when user purges from bin), timestamps.

### Chapter (metadata)

- `chapter_id`, `book_id`, optional `title`, `original_filename`, **`original_language`**, `content_type`, `byte_size` (uploaded object), `sort_order`, optional `draft_updated_at`, optional `draft_revision_count`, **`lifecycle_state`**, **`trashed_at`**, **`purge_eligible_at`**, timestamps.

### Lifecycle (recycle bin)

- **Stage 1:** **`DELETE`** book or chapter → **`trashed`** + **`trashed_at`**; data remains in Postgres and MinIO; editors and uploads that require an **active** parent return **409** as specified in OpenAPI.
- **Stage 2:** **`DELETE …/purge`** while **`trashed`** → **`purge_pending`** + **`purge_eligible_at`**; owner **GET** returns **404**; **GC** (future) deletes rows and blobs.
- **Trash book** → all chapters set **`trashed`** together; **restore book** → all chapters **`active`** together (MVP; see **`31`** if finer-grained rules are needed later).

### Draft / revision (API shapes)

- **Draft response:** `body` (string, UTF-8), `draft_format` (`plain` \| `markdown`), `draft_updated_at`, optional `draft_version` for optimistic concurrency.
- **Patch draft:** `body` (required), optional `commit_message`, optional `expected_draft_version` → **409** if stale.
- **Revision summary:** `revision_id`, `created_at`, optional `author_user_id`, optional `message`, optional `body_byte_length`.
- **Revision detail:** includes full `body` snapshot.

### Future translate (documentation only)

- Entity **`ChapterTranslation`** or query-param **`locale`** on content endpoints—**Open Questions**; not in MVP OpenAPI.

### Multilingual usage (how to fetch EN vs VI)

- **MVP:** each locale is a **separate `chapter_id`** with its own **`original_language`**. To get “chapter 1 in English”, call **`GET /v1/books/{book_id}/chapters?sort_order=1&original_language=en`** (or list all for `sort_order=1` and pick `en`). To list all chapters in Vietnamese only: **`?original_language=vi`**.
- **Not supported in MVP:** a single `chapter_id` with multiple locales inside one draft body.
- **Catalog / unlisted:** book-level **`original_language`** only; per-chapter language discovery for anonymous readers is **out of MVP** unless extended (see §7).

## 4) Error Taxonomy (Draft)

Envelope: `{ "code", "message" }`.


| Code                         | HTTP | Meaning                                                                 |
| ---------------------------- | ---- | ----------------------------------------------------------------------- |
| `BOOK_VALIDATION_ERROR`      | 400  | Invalid body                                                            |
| `BOOK_NOT_FOUND`             | 404  | Unknown / invisible                                                     |
| `BOOK_FORBIDDEN`             | 403  | Not owner                                                               |
| `BOOK_CONFLICT`              | 409  | Generic conflict                                                        |
| `BOOK_INVALID_LIFECYCLE`     | 409  | e.g. trash when already **trashed** / **purge_pending**, or patch while not **active** (optional code; may reuse `BOOK_CONFLICT`) |
| `CHAPTER_INVALID_LIFECYCLE`  | 409  | e.g. **trash** when parent book not **active**, **purge** when not **trashed** (optional code) |
| `CHAPTER_DRAFT_CONFLICT`     | 409  | Stale `expected_draft_version` (optional code; may reuse `BOOK_CONFLICT`) |
| `UNSUPPORTED_MEDIA_TYPE`     | 415  | Chapter not `text/plain` or bad cover type                              |
| `STORAGE_QUOTA_EXCEEDED`     | 507  | Quota on upload                                                         |
| `STORAGE_BACKEND_ERROR`      | 502  | Object store down                                                       |
| `CHAPTER_NOT_FOUND`          | 404  | Missing chapter                                                         |
| `REVISION_NOT_FOUND`         | 404  | Missing revision                                                        |
| `SHARE_POLICY_INVALID`       | 400  | Bad visibility transition                                               |
| `CATALOG_INVALID_QUERY`      | 400  | Bad query                                                               |


## 5) Versioning and Governance

- OpenAPI **books** **info.version** **1.4.0** (recycle bin + **`lifecycle_state`**); **sharing** / **catalog** **1.2.1** (descriptive: hide **trashed** / **purge_pending** from readers).
- Gateway-only external entry.

## 6) Open Questions


| ID        | Topic                                                                 | Owner   | Target                |
| --------- | --------------------------------------------------------------------- | ------- | --------------------- |
| OQ-M02-01 | Multipart vs presigned PUT for large uploads                          | SA / BE | Before implementation |
| OQ-M02-02 | Max sizes, timeouts                                                   | SA / BE | Before implementation |
| OQ-M02-03 | Pagination (`limit`/`cursor`)                                        | SA      | Before implementation |
| OQ-M02-04 | Catalog/unlisted cover URL policy                                     | PM / SA | Before `33` freeze    |
| OQ-M02-05 | Catalog: owner display name                                           | PM      | Before `33` freeze    |
| OQ-M02-06 | Malware scanning                                                      | Sec     | Before rollout        |
| OQ-M02-07 | **Quota:** count draft + revision bytes vs object storage only        | SA / PM | Before implementation |
| OQ-M02-08 | Max revisions per chapter; retention / prune                        | SA      | Before implementation |
| OQ-M02-09 | **Gitea** vs Postgres-only revisions (ADR timing)                    | SA      | Roadmap               |
| OQ-M02-10 | Future **translated** chapter download API shape (`locale` vs path) | SA      | After RAG slice       |
| OQ-M02-11 | Optional **`translation_group_id`** (or `logical_sequence`) to tie chapter rows across languages without relying only on `sort_order` | SA / PM | Before heavy multilingual UX |
| OQ-M02-12 | **`available_languages`** (or per-locale `chapter_count`) on **PublicBook** for catalog browse | PM / SA | Before public multi-locale story |
| OQ-M02-13 | **Garbage collector:** schedule, batch size, MinIO delete ordering vs DB txn; **retention** minimum before physical delete (compliance) | SA / Sec | Before GC implementation |
| OQ-M02-14 | **Quota:** do **trashed** / **`purge_pending`** bytes still count until GC? (default assumption: **yes** until physical delete) | SA / PM | Before implementation |
| OQ-M02-15 | **Sharing/catalog sync:** how **catalog-service** / **sharing-service** learn **`lifecycle_state`** (poll book API, replicated field, outbox/event) | SA | Before implementation |


## 7) Multilingual model review (pass / gaps / follow-up)

| Criterion | Assessment |
| --------- | ---------- |
| Identity (`original_language` book + chapter, BCP-47) | **Pass** — aligned across books/sharing/catalog OpenAPI and planning. |
| Draft / revision per `chapter_id` (one locale per row) | **Pass** — matches multilingual authoring; no multi-locale single draft. |
| Logical grouping of variants (same “chapter 1”, many languages) | **Partial** — MVP uses **`sort_order` + `original_language`** + recommended **`UNIQUE (book_id, sort_order, original_language)`** in `31`; optional shared **`translation_group_id`** deferred to OQ-M02-11. |
| List / filter API | **Addressed (1.3.0)** — `GET …/chapters` supports optional **`original_language`**, **`sort_order`** (both optional; combine for precise lookup). Pagination for long lists: still OQ-M02-03. |
| Catalog / unlisted chapter language discovery | **Gap (MVP)** — payloads are book-centric; **`available_languages`** / chapter language list for readers is follow-up (OQ-M02-12). |
| Quota with many language rows | **Pass with OQ** — OQ-M02-07; each row consumes storage like any other chapter. |

**Architecture alternative (explicit non-choice for MVP):** one `chapter_id` with multiple locales inside one resource would require a different schema; not adopted without Decision Authority.

## 8) References

- `03_V1_BOUNDARIES.md`
- `12_MODULE01_API_CONTRACT_DRAFT.md`
- `24_PHASE1_MODULE02_BOOKS_SHARING_EXECUTION_PACK.md`
- `04_TECHSTACK_SERVICE_MATRIX.md`

