# LoreWeave Module 02 Acceptance Test Plan

## Document Metadata

- Document ID: LW-M02-27
- Version: 1.4.0
- Status: Approved
- Owner: QA Lead
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Acceptance scenarios for Module 02 including **`original_language`**, draft editor, revision history, raw vs draft download.

## Change History

| Version | Date       | Change                                                         | Author    |
| ------- | ---------- | -------------------------------------------------------------- | --------- |
| 1.4.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 1.0.0   | 2026-03-21 | Initial Module 02 acceptance matrix                            | Assistant |
| 1.1.0   | 2026-03-21 | Chapter txt, quota, cover, download, catalog privacy           | Assistant |
| 1.2.0   | 2026-03-21 | **`original_language`**; **draft/revision**; UTF-8 seed; conflict; restore | Assistant |
| 1.3.0   | 2026-03-21 | **M02-AT-33–35** list chapters query filters (`original_language`, `sort_order`) | Assistant |
| 1.4.0   | 2026-03-21 | **M02-AT-36–45** recycle bin, **`lifecycle_state`**, catalog 404 for trashed | Assistant |

## 1) Objective

Validate Module 02 per `25`/`26`: storage, cover, chapters, **`original_language`**, **canonical draft**, **revisions**, sharing, catalog.

## 2) Scope

**In scope:** book CRUD; **logical delete** (trash / restore / purge); **`lifecycle_state`**; **`GET /v1/books/trash`**; **`original_language`** on book and chapter; upload `.txt` with **required** chapter `original_language`; **GET/PATCH draft**; **revision list/get/restore**; **GET content** = original upload only; quota; sharing; catalog; negatives.

**Out of scope:** RAG, AI translate, Gitea, non-txt MIME.

## 3) Scenario Matrix

| Scenario ID | Scenario | Expected result | Evidence |
| ----------- | -------- | --------------- | -------- |
| M02-AT-01 | Create book with valid payload | 201, owner id | API + UI |
| M02-AT-02 | List books — only owner’s | All `owner_user_id` match | API |
| M02-AT-03 | Get book as owner | 200 | API |
| M02-AT-04 | Get other user’s book | 403/404 | API |
| M02-AT-05 | Patch book (incl. summary, **`original_language`**) | 200 | API |
| M02-AT-06 | Patch book as non-owner | 403/404 | API |
| M02-AT-07 | Visibility `public` | Catalog lists | API + UI |
| M02-AT-08 | Visibility `private` | Public GET 404 | API |
| M02-AT-09 | Visibility `unlisted` + token | Unlisted GET 200 | API |
| M02-AT-10 | Unlisted bad token | 404 | API |
| M02-AT-11 | Rotate unlisted token | Old invalid, new works | API |
| M02-AT-12 | Catalog pagination | Stable order | API |
| M02-AT-13 | Unauthenticated catalog list | 200 | API |
| M02-AT-14 | Validation error | 400 + code | API |
| M02-AT-15 | Upload chapter **text/plain** + **`original_language`** | 201; object + draft seeded (UTF-8) | API + DB |
| M02-AT-15b | Create chapter **without** `original_language` | **400** | API |
| M02-AT-16 | Upload non-txt | **415** | API |
| M02-AT-17 | Quota exceeded on upload | **507** | API |
| M02-AT-18 | **Trash** chapter (`DELETE …/chapters/{id}`) | **`lifecycle_state` trashed**; MinIO + draft + revisions **still present** until GC after purge | API + DB |
| M02-AT-19 / 20 | Cover replace / delete | Per contract | API |
| M02-AT-21 | Download **`/content`** | Bytes **match original file**, not edited draft | API |
| M02-AT-22 | Non-owner cannot download content | 403/404 | API |
| M02-AT-23 | Catalog / unlisted — no `storage_key` | Inspect JSON | API |
| M02-AT-24 | Storage usage | Consistent with policy | API |
| M02-AT-25 | **GET draft** after upload | `body` equals decoded upload (UTF-8) | API |
| M02-AT-26 | **PATCH draft** | New revision row; `draft` updated | API + DB |
| M02-AT-27 | **GET revisions** list | Includes new revision | API |
| M02-AT-28 | **GET revision** detail | `body` snapshot matches saved revision | API |
| M02-AT-29 | **POST restore** | Draft matches restored snapshot; **new** revision created for prior draft | API |
| M02-AT-30 | Stale **`expected_draft_version`** | **409** (if implemented) | API |
| M02-AT-31 | Two chapters same `sort_order` **different** `original_language` | Allowed if DB unique allows | API |
| M02-AT-32 | JSON uses **`original_language`** on book/catalog/unlisted | No `primary_language` | API |
| M02-AT-33 | **`GET …/chapters?original_language=en`** | Only chapters with `original_language` en | API |
| M02-AT-34 | **`GET …/chapters?sort_order=2`** | Only chapters with `sort_order` 2 (all locales for that slot) | API |
| M02-AT-35 | **`GET …/chapters?sort_order=1&original_language=vi`** | At most one row if UNIQUE holds; empty if none | API |
| M02-AT-36 | **`DELETE /v1/books/{id}`** | Book **trashed**; absent from **`GET /v1/books`**; present in **`GET /v1/books/trash`** | API |
| M02-AT-37 | **`POST …/books/{id}/restore`** | Book + chapters **active** again | API |
| M02-AT-38 | **`DELETE …/books/{id}/purge`** from trash | **`purge_pending`**; **404** on owner **GET**; gone from trash list | API |
| M02-AT-39 | **`POST …/chapters/{id}/restore`** | Chapter **active** (parent book **active**) | API |
| M02-AT-40 | **`DELETE …/chapters/{id}/purge`** from bin | Chapter **purge_pending** | API |
| M02-AT-41 | **Patch book** while **trashed** | **409** (or policy in OpenAPI) | API |
| M02-AT-42 | **Public catalog** after book **trashed** | **404** on **`GET /v1/catalog/books/{id}`** | API |
| M02-AT-43 | **Unlisted** after book **trashed** | **404** on unlisted resolve | API |
| M02-AT-44 | **`GET …/chapters?lifecycle_state=trashed`** | Only **trashed** chapters when book **active** | API |
| M02-AT-45 | JSON **`lifecycle_state`** on book/chapter | Matches **`active` \| `trashed` \| `purge_pending`** | API |

## 4) Pass Criteria

- M02-AT-01 … 14 required; 15–24 when storage on; **25–45** when draft/revision + list filters + recycle bin implemented.
- No **Critical** leaks, quota bypass, or draft/raw confusion.

## 5) Evidence Checklist

- API captures per group; UI: editor, history, restore, “original download” label.

## 6) References

- `25_MODULE02_API_CONTRACT_DRAFT.md`
- `26_MODULE02_FRONTEND_FLOW_SPEC.md`
- `14_MODULE01_ACCEPTANCE_TEST_PLAN.md`
