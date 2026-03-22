# LoreWeave Module 04 API Contract Draft (Raw Translation Pipeline)

## Document Metadata

- Document ID: LW-M04-57
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-22
- Summary: Contract-first draft for Module 04 APIs covering per-user translation preferences, per-book translation settings, and async translation job lifecycle with chapter-level result retrieval.

## Change History

| Version | Date       | Change                           | Author    |
| ------- | ---------- | -------------------------------- | --------- |
| 0.1.0   | 2026-03-22 | Initial Module 04 contract draft | Assistant |

## 1) Contract Scope

This draft defines gateway-facing behavior for:

- user translation preference management (model, target language, prompt templates),
- per-book translation settings (override user defaults),
- async translation job creation and status tracking,
- per-chapter translation result retrieval.

All endpoints are served by `translation-service` (port 8087) behind `api-gateway-bff` at path prefix `/v1/translation`.

## 2) Proposed OpenAPI Surface

| API surface | Proposed OpenAPI path |
| --- | --- |
| Translation pipeline | `contracts/api/translation/v1/openapi.yaml` |

## 3) Core Endpoint Set (Draft)

### 3.1 User Translation Preferences

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/v1/translation/preferences` | GET | Bearer | Get current user's translation preferences (or synthesized defaults if no row exists) |
| `/v1/translation/preferences` | PUT | Bearer | Upsert user translation preferences |

### 3.2 Book Translation Settings

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/v1/translation/books/{book_id}/settings` | GET | Bearer | Get effective settings for book (book row if saved, else merged from user prefs + defaults) |
| `/v1/translation/books/{book_id}/settings` | PUT | Bearer | Upsert book-specific translation settings (owner only) |

### 3.3 Translation Jobs

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/v1/translation/books/{book_id}/jobs` | POST | Bearer | Create translation job (async); returns job immediately in `pending` status |
| `/v1/translation/books/{book_id}/jobs` | GET | Bearer | List translation jobs for a book (owner only) |
| `/v1/translation/jobs/{job_id}` | GET | Bearer | Get job detail including embedded `chapter_translations` list (owner only) |
| `/v1/translation/jobs/{job_id}/chapters/{chapter_id}` | GET | Bearer | Get single chapter translation result with `translated_body` (owner only) |
| `/v1/translation/jobs/{job_id}/cancel` | POST | Bearer | Cancel a `pending` or `running` job; sets status to `cancelled` (owner only) |

### 3.4 Health

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/health` | GET | None | Service health check |

## 4) Core Schemas (Draft)

### UserTranslationPreferences

- `user_id` (UUID)
- `target_language` (BCP-47 string, e.g. `"vi"`, `"en"`)
- `model_source` (`"user_model"` | `"platform_model"`)
- `model_ref` (UUID | null — null means no default configured)
- `system_prompt` (text)
- `user_prompt_tpl` (text — supports variables `{source_language}`, `{target_language}`, `{chapter_text}`)
- `updated_at` (ISO timestamp)

### BookTranslationSettings

- `book_id` (UUID)
- `owner_user_id` (UUID)
- `target_language`
- `model_source`
- `model_ref` (UUID | null)
- `system_prompt`
- `user_prompt_tpl`
- `updated_at`
- `is_default` (bool — `true` when response is synthesized from user prefs, not a saved book row; GET-only field, never stored)

### TranslationJob

- `job_id` (UUID)
- `book_id` (UUID)
- `owner_user_id` (UUID)
- `status` (`"pending"` | `"running"` | `"completed"` | `"partial"` | `"failed"` | `"cancelled"`)
- `target_language`
- `model_source`
- `model_ref` (UUID)
- `system_prompt` (snapshot at job creation time)
- `user_prompt_tpl` (snapshot at job creation time)
- `chapter_ids` (UUID array — ordered list of chapters to translate)
- `total_chapters` (int)
- `completed_chapters` (int)
- `failed_chapters` (int)
- `error_message` (text | null)
- `started_at` (timestamp | null)
- `finished_at` (timestamp | null)
- `created_at` (timestamp)
- `chapter_translations` (ChapterTranslation[] — present only in job detail endpoint)

### ChapterTranslation

- `id` (UUID)
- `job_id` (UUID)
- `chapter_id` (UUID)
- `book_id` (UUID)
- `status` (`"pending"` | `"running"` | `"completed"` | `"failed"`)
- `translated_body` (text | null)
- `source_language` (text | null — populated from chapter's `original_language`)
- `target_language` (text)
- `input_tokens` (int | null)
- `output_tokens` (int | null)
- `usage_log_id` (UUID | null — reference to billing record in `usage-billing-service`)
- `error_message` (text | null)
- `started_at` (timestamp | null)
- `finished_at` (timestamp | null)
- `created_at` (timestamp)

## 5) Request/Response Contracts

### POST `/v1/translation/books/{book_id}/jobs`

Request body:
```json
{
  "chapter_ids": ["uuid", "uuid"]
}
```
- `chapter_ids` is **required and must be non-empty**. Returns 422 if empty or missing.
- UI responsibility: pre-select all active chapters that have no completed translation in any existing job for this book. User can adjust before submitting.

Response `201 Created`:
```json
{
  "job_id": "uuid",
  "book_id": "uuid",
  "status": "pending",
  "total_chapters": 3,
  "completed_chapters": 0,
  "failed_chapters": 0,
  "created_at": "2026-03-22T00:00:00Z"
}
```

Error `422` if no model is configured:
```json
{ "code": "TRANSL_NO_MODEL_CONFIGURED", "message": "No model configured. Set a model in translation settings before translating." }
```

### PUT `/v1/translation/preferences`

Request body:
```json
{
  "target_language": "vi",
  "model_source": "user_model",
  "model_ref": "uuid",
  "system_prompt": "...",
  "user_prompt_tpl": "..."
}
```
All fields required. Response `200` with saved `UserTranslationPreferences`.

### GET `/v1/translation/books/{book_id}/settings`

Response `200` with `BookTranslationSettings`. If no book row exists, returns synthesized object with `is_default: true` (settings merged from user prefs or hard-coded defaults). Does **not** create a DB row.

## 6) Settings Merge Rules

Applied when resolving effective settings for a job:

1. Load `book_translation_settings` WHERE `book_id = ?` AND `owner_user_id = ?`.
2. If found → use as effective settings.
3. If not found:
   a. Load `user_translation_preferences` WHERE `user_id = ?`.
   b. If not found → use platform defaults from `config.py`.
4. If `effective.model_ref IS NULL` → reject job creation with `TRANSL_NO_MODEL_CONFIGURED`.
5. Snapshot all effective fields onto the `translation_jobs` row at creation time (immutable after that).

## 7) Default Prompt Text

These are the hard-coded platform defaults served when neither user preferences nor book settings exist:

**System prompt:**
```
You are a professional literary translator. Preserve the style, tone, pacing, and voice of the original text. Do not add commentary, explanations, or translator notes. Translate faithfully and naturally.
```

**User prompt template:**
```
Translate the following {source_language} text into {target_language}. Output only the translated text, nothing else.

{chapter_text}
```

Supported template variables: `{source_language}`, `{target_language}`, `{chapter_text}`.

## 8) Pagination

`GET /v1/translation/books/{book_id}/jobs` supports query parameters:
- `limit` (int, default 20, max 100)
- `offset` (int, default 0)

Response includes `{ items: TranslationJob[], total: int, limit: int, offset: int }`.

## 9) Error Taxonomy (Draft)

| Code | HTTP | Meaning |
| --- | --- | --- |
| `TRANSL_VALIDATION_ERROR` | 400 | Invalid input |
| `TRANSL_UNAUTHORIZED` | 401 | Missing or invalid Bearer token |
| `TRANSL_FORBIDDEN` | 403 | Caller does not own this resource |
| `TRANSL_NOT_FOUND` | 404 | Resource not found |
| `TRANSL_NO_MODEL_CONFIGURED` | 422 | Job creation rejected because no model is set in effective settings |
| `TRANSL_BOOK_NOT_FOUND` | 404 | Book not found or not owned by caller |
| `TRANSL_PROVIDER_INVOKE_FAILED` | 502 | Provider invocation failed (propagated from provider-registry-service) |
| `TRANSL_BILLING_REJECTED` | 402 | Quota and credits exhausted (propagated from invoke) |
| `TRANSL_INTERNAL_ERROR` | 500 | Unexpected server error |

## 10) Open Questions

| ID | Topic | Owner | Target |
| --- | --- | --- | --- |
| OQ-M04-01 | Should `chapter_ids` default to "all active chapters" or require explicit selection? | PM | Before contract freeze |
| OQ-M04-02 | Should `DELETE /v1/translation/jobs/{job_id}` (cancel) be in scope for MVP? | PM + SA | Before contract freeze |
| OQ-M04-03 | Should translated results be promotable to `book-service` chapters (new language variant) in MVP or deferred? | PM | Before implementation |
| OQ-M04-04 | Polling interval recommendation for frontend — 3 s vs 5 s for chapter-level granularity? | FE lead | Before frontend freeze |
