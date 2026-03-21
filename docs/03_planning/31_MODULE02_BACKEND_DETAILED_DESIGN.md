# LoreWeave Module 02 Backend Detailed Design

## Document Metadata

- Document ID: LW-M02-31
- Version: 1.4.0
- Status: Approved
- Owner: Solution Architect + Platform Core Lead
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Backend domain model, Postgres draft/revisions, MinIO raw objects, **`lifecycle_state`** (recycle bin + **`purge_pending`**), `original_language`, and endpoint-to-usecase mapping for Module 02.

## Change History


| Version | Date       | Change                                                                                                                   | Author    |
| ------- | ---------- | ------------------------------------------------------------------------------------------------------------------------ | --------- |
| 1.4.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 1.0.0   | 2026-03-21 | Initial M02 backend design                                                                                               | Assistant |
| 1.1.0   | 2026-03-21 | Chapter, BookCoverAsset, quota, MinIO, new usecases + errors                                                             | Assistant |
| 1.2.0   | 2026-03-21 | `**original_language**`; **ChapterDraft** / **ChapterRevision**; seed from upload; Gitea out of MVP                      | Assistant |
| 1.3.0   | 2026-03-21 | `**ListChapters`** optional query `**original_language**`, `**sort_order**` (exact match); align books OpenAPI **1.3.0** | Assistant |
| 1.4.0   | 2026-03-21 | Recycle bin usecases, cascade trash/restore, **`purge_pending`** + GC note; books OpenAPI **1.4.0** | Assistant |


## 0) Placement

- Logical services: `book-service`, `sharing-service`, `catalog-service` (see `30`).
- Contracts: `contracts/api/{books,sharing,catalog}/v1/`.
- Identity: JWT `sub` = `owner_user_id`.
- **Object storage:** raw cover + **original chapter file** only.
- **Canonical draft + revision snapshots:** **Postgres** in `book-service`.

## 1) Domain Model

### Book

- `book_id`, `owner_user_id`, `title`, `description`, **`original_language`** (BCP-47, optional), `summary`, timestamps.
- **`lifecycle_state`**, **`trashed_at`**, **`purge_eligible_at`** (nullable).
- Derived **`chapter_count`** (active chapters for normal list; align with `25`).

### BookCoverAsset

- Unchanged: `storage_key` internal, MIME, `byte_size`, presigned/proxied URL in owner DTOs.

### Chapter

- `chapter_id`, `book_id`, **`original_language`** (required, BCP-47)
- `sort_order` (integer)
- `title` (optional), `original_filename`, `content_type` (MVP `text/plain`), `byte_size` (uploaded object)
- `storage_key` (MinIO; **immutable** after upload for MVP — raw download)
- **`lifecycle_state`**, **`trashed_at`**, **`purge_eligible_at`** (same semantics as book)
- Optional denormalized: `draft_updated_at`, `draft_revision_count` for list API
- Timestamps
- **Uniqueness (recommended):** `UNIQUE (book_id, sort_order, original_language)` **among active rows** (partial unique index) or enforce in app when lifecycle is active-only — see implementation.

### ChapterDraft (logical — may be columns on `chapters`)

- `body` (text, UTF-8)
- `draft_format`: `plain` | `markdown`
- `draft_updated_at`
- Optional `draft_version` (integer, optimistic locking)

### ChapterRevision

- `revision_id` (UUID)
- `chapter_id` (FK)
- `body` (text snapshot — full text MVP)
- `message` (optional)
- `author_user_id` (from JWT)
- `created_at`
- On **restore:** copy snapshot into draft and **insert new revision** capturing previous draft (audit trail).

### UserStorageQuota

- `used_bytes` / `quota_bytes` — policy whether **draft + revision** bytes count toward quota (see `25` OQ-M02-07); default recommendation: **object storage bytes only** for MVP quota; cap revision count/size separately.

### SharingPolicy / CatalogProjection / Unlisted DTO

- Use **`original_language`** on book in public/unlisted payloads (not `primary_language`).
- No chapter draft bodies in catalog/unlisted.
- Exclude **`trashed`** / **`purge_pending`** books from reader surfaces (**404**); sync: **`25`** OQ-M02-15.

### ChapterTranslation (future)

- Out of MVP; see `25` for AI/manual translate roadmap.

### Recycle bin & garbage collection (MVP contract / future job)

- **TrashBook:** set book **`trashed`**, **`trashed_at`**; **cascade** all chapters to **`trashed`** (MVP simplification: restore book sets **all** chapters **`active`**).
- **RestoreBook:** book **`active`**; cascade chapters **`active`**.
- **PurgeBook:** from **`trashed`** only → **`purge_pending`**, **`purge_eligible_at`**; cascade chapters **`purge_pending`**; owner **GET** **404**; **omit** from **`GET /v1/books/trash`**.
- **TrashChapter:** only when parent book **`active`** → chapter **`trashed`** (retain MinIO + draft + revisions).
- **RestoreChapter** / **PurgeChapter:** mirror book rules.
- **GarbageCollector (future):** scan **`purge_eligible_at`** / **`purge_pending`**, delete MinIO keys, revision rows, chapter rows, book row, sharing projection; transactional boundaries per **`25`** OQ-M02-13.

## 2) Usecases


| Usecase                                                       | Description                                                                                                                                                               |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CreateBook`                                                  | Insert book; default `private`; **`lifecycle_state` active**; sharing row                                                                                                 |
| `ListBooksForOwner`                                           | **`active`** books only                                                                                                                                                   |
| `ListTrashedBooks`                                            | Books **`trashed`** only                                                                                                                                                  |
| `GetBookForOwner` / `PatchBookMetadata`                       | Get **active** or **trashed**; **patch** only **active**; **`purge_pending`** → **404**; patch includes **`original_language`**                                              |
| `TrashBook` / `RestoreBook` / `PurgeBook`                     | Lifecycle transitions + cascade chapters (see model above)                                                                                                                |
| `GetStorageUsage`                                             | Quota (see **`25`** OQ-M02-14 for trashed bytes)                                                                                                                           |
| `UploadBookCover` / `DeleteBookCover`                         | Only when book **active** (or as policy in OpenAPI)                                                                                                                        |
| `ListChapters`                                                | Ordered by `sort_order`; optional **`lifecycle_state`**, **`original_language`**, **`sort_order`**                                                                         |
| `CreateChapterFromTxtUpload`                                  | Parent book **active**; Validate MIME + **`original_language`**; PUT raw to MinIO; insert **`Chapter`** **active**; seed draft + optional initial revision                  |
| `GetChapterMetadata` / `PatchChapter`                         | **Active** book + **active** chapter for patch; includes `original_language`                                                                                                |
| `TrashChapter` / `RestoreChapter` / `PurgeChapter`             | Soft delete / restore / **purge_pending**; no physical delete until GC                                                                                                     |
| `DownloadChapterContent`                                      | Stream **raw upload** from MinIO only                                                                                                                                     |
| `GetChapterDraft`                                             | Load draft for editor                                                                                                                                                     |
| `PatchChapterDraft`                                           | Validate UTF-8; optional version check → **409**; persist body; **append revision**                                                                                       |
| `ListChapterRevisions` / `GetChapterRevision`                 | History                                                                                                                                                                   |
| `RestoreChapterRevision`                                      | Set draft from snapshot; append revision for prior draft                                                                                                                  |
| Sharing/catalog usecases                                      | Filter **`lifecycle active`** for readers; payloads use **`original_language`**                                                                                            |


## 3) Endpoint-to-Usecase Mapping


| HTTP                                   | Usecase                                                                                        |
| -------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `GET /v1/books/storage-usage`          | `GetStorageUsage`                                                                              |
| `POST /v1/books`                       | `CreateBook`                                                                                   |
| `GET /v1/books`                        | `ListBooksForOwner` (**active**)                                                               |
| `GET /v1/books/trash`                  | `ListTrashedBooks`                                                                              |
| `GET /v1/books/{id}`                   | `GetBookForOwner`                                                                               |
| `PATCH /v1/books/{id}`                 | `PatchBookMetadata`                                                                             |
| `DELETE /v1/books/{id}`                | `TrashBook`                                                                                     |
| `POST /v1/books/{id}/restore`          | `RestoreBook`                                                                                   |
| `DELETE /v1/books/{id}/purge`         | `PurgeBook`                                                                                     |
| `POST/DELETE …/cover`                  | Cover upload/delete                                                                             |
| `GET/POST …/chapters`                  | `ListChapters` / `CreateChapterFromTxtUpload`                                                    |
| `GET/PATCH/DELETE …/chapters/{cid}`    | Metadata / patch / **`TrashChapter`**                                                           |
| `POST …/chapters/{cid}/restore`        | `RestoreChapter`                                                                                |
| `DELETE …/chapters/{cid}/purge`        | `PurgeChapter`                                                                                  |
| `GET …/chapters/{cid}/content`         | `DownloadChapterContent`                                                                       |
| `GET/PATCH …/chapters/{cid}/draft`     | `GetChapterDraft` / `PatchChapterDraft`                                                        |
| `GET …/chapters/{cid}/revisions`       | `ListChapterRevisions`                                                                         |
| `GET …/chapters/{cid}/revisions/{rid}` | `GetChapterRevision`                                                                           |
| `POST …/revisions/{rid}/restore`       | `RestoreChapterRevision`                                                                       |
| Sharing / catalog                      | (as before)                                                                                    |


## 4) Error Mapping

Add: `**REVISION_NOT_FOUND**` (404), draft conflict `**CHAPTER_DRAFT_CONFLICT**` or `**BOOK_CONFLICT**` (409).

## 5) Security

- Owner checks on all chapter draft/revision routes.
- Never expose `storage_key`; catalog/unlisted unchanged.

## 6) References

- `25_MODULE02_API_CONTRACT_DRAFT.md`
- `30_MODULE02_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md`
- `18_MODULE01_BACKEND_DETAILED_DESIGN.md`

