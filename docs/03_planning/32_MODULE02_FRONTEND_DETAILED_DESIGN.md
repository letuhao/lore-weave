# LoreWeave Module 02 Frontend Detailed Design

## Document Metadata

- Document ID: LW-M02-32
- Version: 1.4.0
- Status: Approved
- Owner: Product Manager + Platform Core Lead
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Routes and components for book tabs, chapter list (**`original_language`**), **recycle bin**, **chapter editor**, **revision history**, raw download.

## Change History

| Version | Date       | Change                                                         | Author    |
| ------- | ---------- | -------------------------------------------------------------- | --------- |
| 1.4.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 1.0.0   | 2026-03-21 | Initial M02 FE design                                          | Assistant |
| 1.1.0   | 2026-03-21 | Tabs for summary/cover/chapters, upload + download patterns    | Assistant |
| 1.2.0   | 2026-03-21 | **`ChapterEditor`**, **history**, **`original_language`**; draft vs raw | Assistant |
| 1.3.0   | 2026-03-21 | Chapter list may call **`GET …/chapters?original_language=`** (per-locale table) or full list | Assistant |
| 1.4.0   | 2026-03-21 | Route **`/books/trash`**; **`BookTrashList`**, confirm **purge**; chapter trash/restore | Assistant |

## 0) Context

- `frontend/`; `apiJson` + Bearer; `FormData` for multipart.
- **Large draft bodies:** avoid blocking UI; debounced save optional (product); always show save state.

## 1) Route Map (Draft)

| Path | Auth | Purpose |
| ---- | ---- | ------- |
| `/books` | Required | My books (**active** only) |
| `/books/trash` | Required | Recycle bin — **`GET /v1/books/trash`** |
| `/books/new` | Required | Create book |
| `/books/:bookId` | Required | Owner detail: Summary · Cover · Chapters |
| `/books/:bookId/chapters/:chapterId/edit` | Required | **Chapter editor** + optional side panel **History** |
| `/books/:bookId/sharing` | Required | Sharing |
| `/browse` | Optional | Catalog |
| `/browse/:bookId` | Optional | Public detail |
| `/s/:accessToken` | None | Unlisted |

Alternative: editor as **modal** from book detail without dedicated route — document choice in implementation PR.

## 2) Book Detail (Owner)

- **Summary tab:** `title`, `description`, **`original_language`**, `summary` → `PATCH /v1/books/{id}`.
- **Cover tab:** unchanged.
- **Chapters tab:** columns **Order**, **Title**, **`original_language`**, **Size (raw)**, **Updated (draft)**; actions: **Edit draft**, **Download original**, **Move to trash** (`DELETE` chapter), reorder (`sort_order`). Optional **language filter** (dropdown) maps to **`GET …/chapters?original_language=`**; optional **trashed-only** list via **`?lifecycle_state=trashed`**. Book detail header: **Delete book** → trash; link **Open recycle bin**.
- **Add chapter:** file + **language** selector (required) + optional title/sort → `POST …/chapters`.

## 3) Chapter Editor Screen

- Load `GET …/draft`; show **`Textarea`** (MVP **plain**); if `draft_format === markdown`, use markdown editor component when available.
- Toolbar: **Save** (`PATCH …/draft` with `body`, optional `commit_message`, `expected_draft_version`).
- **409:** toast + offer reload draft.
- Link **History** → list `GET …/revisions`; drill-in snapshot; **Restore** with confirm → `POST …/restore`.

## 4) Component Layers

- `ChapterUpload` — includes **`original_language`** field in `FormData`.
- `ChapterEditor` — draft load/save, dirty state, conflict handling.
- `ChapterRevisionList` / `RevisionDetail` — read-only snapshot.
- `BookTrashList` / `TrashBookRow` — restore vs **Delete permanently** (`purge`) with strong confirm.
- Reuse `Tabs`, `Button`, `Alert`, `Dialog`.

## 5) State

- Invalidate chapter list after draft save, restore, trash, restore-from-bin, purge.
- Keep `draft_version` in memory after GET draft for next PATCH.

## 6) Navigation

- `AppNav`: My books, **Recycle bin**, Browse; unlisted minimal chrome per `33`.

## 7) References

- `26_MODULE02_FRONTEND_FLOW_SPEC.md`
- `19_MODULE01_FRONTEND_DETAILED_DESIGN.md`
- `33_MODULE02_UI_UX_WIREFRAME_SPEC.md`
