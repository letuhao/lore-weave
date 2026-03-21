# LoreWeave Service Contracts (V1)

**Module 02 governed OpenAPI (authoritative for gateway paths `/v1/books`, `/v1/sharing`, `/v1/catalog`):** `contracts/api/books/v1/openapi.yaml` (**info.version 1.4.0** — **`lifecycle_state`**, recycle bin **`GET /v1/books/trash`**, **`DELETE`** trash / **`POST …/restore`** / **`DELETE …/purge`**, list chapters optional **`lifecycle_state`** / **`original_language`** / **`sort_order`**), `contracts/api/sharing/v1/openapi.yaml`, `contracts/api/catalog/v1/openapi.yaml` (**info.version 1.2.1** — trashed/**purge_pending** books invisible to readers). Books: **`original_language`**, **summary**, **cover**, **chapters** (`.txt` MVP), **canonical draft**, **revisions**, **`GET …/content`** (raw upload), **quota**. Sharing/catalog: **`original_language`**, excerpts/cover policy; reader surfaces exclude non-**active** lifecycles.

**Module 03 planned contract domains (draft planning baseline):** `contracts/api/model-registry/v1/openapi.yaml` and `contracts/api/model-billing/v1/openapi.yaml` (to be authored from `docs/03_planning/45_MODULE03_API_CONTRACT_DRAFT.md`; policy lock: tier quota plus credits overage, encrypted server-side key storage).

Narrative JSON below is historical; align with OpenAPI and `docs/03_planning/25_MODULE02_API_CONTRACT_DRAFT.md`.

## 1) Shared Data Types

### User
```json
{
  "user_id": "usr_123",
  "email": "user@example.com",
  "display_name": "User",
  "role": "user",
  "created_at": "2026-03-21T10:00:00Z"
}
```

### Book
```json
{
  "book_id": "book_123",
  "owner_user_id": "usr_123",
  "title": "Novel Name",
  "source_language": "zh",
  "target_languages": ["vi"],
  "visibility": "private",
  "status": "draft",
  "tags": ["fantasy"],
  "created_at": "2026-03-21T10:00:00Z",
  "updated_at": "2026-03-21T10:05:00Z"
}
```

### Workflow Job
```json
{
  "job_id": "job_123",
  "book_id": "book_123",
  "job_type": "index_book",
  "status": "queued",
  "payload": {},
  "result": null,
  "error": null,
  "created_at": "2026-03-21T10:00:00Z",
  "updated_at": "2026-03-21T10:00:00Z"
}
```

### Retrieval Evidence
```json
{
  "evidence_id": "ev_123",
  "book_id": "book_123",
  "source_type": "chapter_chunk",
  "source_ref": "chapter_2:line_50_88",
  "language": "zh",
  "text": "Evidence text",
  "score": 0.89
}
```

## 2) Auth Service API

Base path: `/auth`

- `POST /auth/register`
  - request: `{ email, password, display_name }`
  - response: `{ user, access_token }`
- `POST /auth/login`
  - request: `{ email, password }`
  - response: `{ user, access_token }`
- `GET /auth/me`
  - header: `Authorization: Bearer <token>`
  - response: `{ user }`

## 3) Book Service API

Base path: `/books`

- `POST /books`
  - request: `{ title, source_language, target_languages, tags }`
  - auth required
  - response: `Book`
- `GET /books`
  - auth required
  - response: `{ items: Book[] }` (owned + collaborator scope in future)
- `GET /books/{book_id}`
  - auth required (owner or visibility allows)
  - response: `Book`
- `PATCH /books/{book_id}/visibility`
  - request: `{ visibility }`
  - auth required (owner)
  - response: `Book`
- `GET /books/public`
  - response: `{ items: Book[] }`

## 4) Sharing Service API

Base path: `/sharing`

- `POST /sharing/books/{book_id}/publish`
  - request: `{ visibility }`
  - auth required (owner)
  - response: `{ book_id, visibility, share_url }`
- `GET /sharing/books/{book_id}`
  - auth optional
  - response: `{ book_id, visibility, share_url }`

## 5) Browsing Catalog Service API

Base path: `/catalog`

- `GET /catalog/books`
  - query: `language`, `tag`, `q`
  - response: `{ items: Book[] }`

## 6) Job + Orchestrator APIs

### Workflow Job Service (`/jobs`)
- `POST /jobs`
  - request: `{ book_id, job_type, payload }`
  - response: `WorkflowJob`
- `GET /jobs/{job_id}`
  - response: `WorkflowJob`
- `POST /jobs/{job_id}/transition`
  - request: `{ status, result?, error? }`
  - response: `WorkflowJob`

Allowed status transitions:
- `queued -> running`
- `running -> retrying | completed | failed | canceled`
- `retrying -> running | failed | canceled`

### Orchestrator Service (`/orchestrator`)
- `POST /orchestrator/jobs/{job_id}/start`
- `POST /orchestrator/jobs/{job_id}/complete`
- `POST /orchestrator/jobs/{job_id}/fail`

## 7) RAG + Knowledge APIs

### RAG Index Service (`/rag`)
- `POST /rag/index`
  - request: `{ book_id, chunks: [{ source_ref, language, text }] }`
  - response: `{ indexed_count }`
- `POST /rag/retrieve`
  - request: `{ book_id, query, top_k }`
  - response: `{ items: RetrievalEvidence[] }`

### Story Wiki Service (`/wiki`)
- `POST /wiki/build`
  - request: `{ book_id, entity_ids? }`
  - response: `{ pages: [{ title, summary, evidence_ids[] }] }`

### QA + Extraction Service (`/qa`)
- `POST /qa/answer`
  - request: `{ book_id, question, top_k }`
  - response: `{ answer, evidences: RetrievalEvidence[] }`
- `POST /qa/extract`
  - request: `{ book_id, task, top_k }`
  - response: `{ result, evidences: RetrievalEvidence[] }`

### Continuation Service (`/continuation`)
- `POST /continuation/generate`
  - request: `{ book_id, prompt, mode }`
  - `mode`: `strict_canon | balanced_creative | free_creative`
  - response: `{ continuation, mode, safety_report, evidences[] }`

## 8) Event Contracts (Queue Topics)

- `BookRegistered`
- `BookContentUploaded`
- `IndexRequested`
- `IndexCompleted`
- `WikiBuildRequested`
- `ContinuationRequested`

Minimum event envelope:
```json
{
  "event_id": "evt_123",
  "event_type": "BookRegistered",
  "occurred_at": "2026-03-21T10:00:00Z",
  "producer": "book-service",
  "payload": {}
}
```
