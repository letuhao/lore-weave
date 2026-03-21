# LoreWeave Module 02 Frontend Flow Specification

## Document Metadata

- Document ID: LW-M02-26
- Version: 1.4.0
- Status: Approved
- Owner: Product Manager + Platform Core Lead
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Frontend journeys and API mapping for Module 02: `original_language`, summary, cover, chapter upload, **draft editor**, **revision history**, **recycle bin** (trash / restore / purge), quota, sharing, catalog.

## Change History

| Version | Date       | Change                                                         | Author    |
| ------- | ---------- | -------------------------------------------------------------- | --------- |
| 1.4.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 1.0.0   | 2026-03-21 | Initial Module 02 FE flows                                     | Assistant |
| 1.1.0   | 2026-03-21 | Chapters, cover, summary, storage usage, upload/error states   | Assistant |
| 1.2.0   | 2026-03-21 | **`original_language`**; **draft GET/PATCH**; **revisions** UI; clarify raw vs draft | Assistant |
| 1.3.0   | 2026-03-21 | Chapter list **`?original_language=`** / **`?sort_order=`** for multilingual views | Assistant |
| 1.4.0   | 2026-03-21 | **Recycle bin:** `GET /v1/books/trash`, **`DELETE`** → trashed, **`POST …/restore`**, **`DELETE …/purge`**; chapter same | Assistant |

## 1) UX Scope

**Screens / flows (MVP):**

- **My books** — list **active** books only; optional **has cover** / **chapter count**; show **`original_language`** when present.
- **Recycle bin** — `GET /v1/books/trash`; open trashed book → list chapters (see `25`); **Restore** book or **Delete permanently** → `DELETE …/purge` (confirm); chapter-level trash/restore/purge when book is **active**.
- **Create book** — title required; **description**, **`original_language`** (BCP-47), **summary** optional; success → book detail.
- **Book detail (owner)** — **Summary** (incl. `original_language`), **Cover**, **Chapters** (list with **language** column); **storage usage**; link to sharing.
- **Chapter row** — **Edit draft** opens **chapter editor** screen/modal: load `GET …/draft` (MVP **plain text** textarea; **markdown** optional per product); **Save** → `PATCH …/draft` with optional **commit message**; show **409** conflict if `expected_draft_version` stale.
- **Revision history** — `GET …/revisions` list; open snapshot `GET …/revisions/{id}`; **Restore** → `POST …/restore` with confirm.
- **Download original upload** — separate from draft: `GET …/content` (label clearly “Original file”).
- **Sharing / catalog / unlisted** — unchanged pattern; catalog/unlisted show **`original_language`** from API.

**Future:** AI summary/cover/translate — disabled placeholders (`33`).

**Monorepo:** `frontend/`; contracts `contracts/api/{books,sharing,catalog}/v1/`.

## 2) User Journeys

### 2.1 Create book

1. User opens “New book”.
2. Validate title; optional **`original_language`**, description, summary.
3. `POST /v1/books` with Bearer token.
4. Navigate to book detail.

### 2.2 List my books

1. `GET /v1/books?limit&offset`.
2. Render list + pagination + errors.

### 2.3 Edit book metadata

1. Edit title / description / **`original_language`** / summary.
2. `PATCH /v1/books/{book_id}`.

### 2.4 Cover upload / remove

1. `POST /v1/books/{book_id}/cover` (multipart); handle **507**.
2. `DELETE …/cover` to remove.

### 2.5 Chapters — add, reorder, download original

1. `GET /v1/books/{book_id}/chapters` — optional **`?original_language=vi`** (only VI rows) and/or **`?sort_order=1`** (all locales for slot 1); combine both to target one variant (e.g. chapter 1 English).
2. **Add:** `.txt` only; multipart includes **required `original_language`** field; progress UI.
3. **415** / **507** messaging.
4. **Reorder / title / language:** `PATCH …/chapters/{id}` (`sort_order`, `title`, `original_language`).
5. **Delete** with confirm → `DELETE …/chapters/{id}` (**trashed**, not immediate wipe); from bin **Restore** or **Purge** per `25`.
6. **Download original file:** `GET …/content` (not draft).

### 2.6 Chapter draft editor and revisions

1. Open editor → `GET …/draft`; bind `body`, `draft_format`, `draft_version` if returned.
2. User edits; **Save** → `PATCH …/draft` with `{ body, commit_message?, expected_draft_version? }`.
3. On **409**, show conflict: reload draft or force strategy per product.
4. **History** tab → list revisions → view snapshot → **Restore** → `POST …/revisions/{revision_id}/restore`.

### 2.7 Storage usage

1. `GET /v1/books/storage-usage`; refresh after uploads/deletes.

### 2.8 Sharing / visibility

1. `GET` / `PATCH` sharing policy; rotate unlisted token; confirm when setting **public**.

### 2.9 Public catalog

1. `GET /v1/catalog/books` → detail `GET …/{book_id}`.

### 2.10 Unlisted link

1. `GET /v1/sharing/unlisted/{access_token}`; handle 404.

### 2.11 Recycle bin (books & chapters)

1. **Trash book** from detail: `DELETE /v1/books/{book_id}` → disappears from **My books**; appears in **Recycle bin** (`GET /v1/books/trash`).
2. **Restore:** `POST /v1/books/{book_id}/restore` → back to **My books**; chapters cascade **active** per `31`.
3. **Delete permanently (stage 2):** `DELETE /v1/books/{book_id}/purge` → removed from bin UI (**purge_pending** server-side); no physical GC in FE scope.
4. **Trash chapter** (book **active**): `DELETE …/chapters/{id}`; optional **Trashed chapters** view via `GET …/chapters?lifecycle_state=trashed` (see OpenAPI).
5. Trashed / purge-pending books **404** on catalog/unlisted/public.

## 3) State Model

| State | Description |
| ----- | ----------- |
| `authenticated_owner` | Owner flows |
| `guest_catalog` | Catalog only |
| `unlisted_reader` | Valid unlisted token |
| `error_forbidden` / `error_not_found` | 403 / 404 |
| `upload_progress` | Chapter or cover upload |
| `quota_exceeded` | 507 |
| `draft_saving` | PATCH draft in flight |
| `draft_conflict` | 409 optimistic concurrency |

## 4) Validation Matrix (Frontend)

| Field | Rule | Error surface |
| ----- | ---- | ------------- |
| Book title | Required, max length | Inline |
| Book / chapter `original_language` | BCP-47 pattern or select | Inline |
| Chapter file | `.txt` / `text/plain` MVP | Before upload |
| Cover | Allowed images | Before upload |
| Draft body | UTF-8; max length per policy | Inline / API |
| Visibility | Enum | Standard |

## 5) API Mapping Summary

| UI action | Method + path |
| --------- | ------------- |
| Storage usage | `GET /v1/books/storage-usage` |
| Create book | `POST /v1/books` |
| List / get / patch book | `GET`/`PATCH /v1/books` … |
| Cover POST/DELETE | `POST`/`DELETE /v1/books/{book_id}/cover` |
| List / create chapter | `GET`/`POST /v1/books/{book_id}/chapters` (list: optional `lifecycle_state`, `original_language`, `sort_order`) |
| Patch / trash chapter | `PATCH`/`DELETE …/chapters/{chapter_id}` (**DELETE** = move to bin) |
| Restore / purge chapter | `POST …/chapters/{chapter_id}/restore`, `DELETE …/chapters/{chapter_id}/purge` |
| Recycle bin (books) | `GET /v1/books/trash`; `POST …/books/{id}/restore`; `DELETE …/books/{id}/purge` |
| Trash book | `DELETE /v1/books/{book_id}` |
| Download **original** | `GET …/chapters/{chapter_id}/content` |
| Get / patch **draft** | `GET`/`PATCH …/chapters/{chapter_id}/draft` |
| List / get revision | `GET …/revisions`, `GET …/revisions/{revision_id}` |
| Restore revision | `POST …/revisions/{revision_id}/restore` |
| Sharing / catalog | unchanged paths |

## 6) References

- `25_MODULE02_API_CONTRACT_DRAFT.md`
- `13_MODULE01_FRONTEND_FLOW_SPEC.md`
- `32_MODULE02_FRONTEND_DETAILED_DESIGN.md`
