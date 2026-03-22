# LoreWeave Module 04 Integration Sequence Diagrams

## Document Metadata

- Document ID: LW-M04-66
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-22
- Summary: Cross-service sequence diagrams for M04 translation pipeline covering settings flows, job creation, job execution, and failure paths.

## Change History

| Version | Date       | Change                                    | Author    |
| ------- | ---------- | ----------------------------------------- | --------- |
| 0.1.0   | 2026-03-22 | Initial Module 04 sequence diagrams       | Assistant |

## 1) Actor Legend

| Actor | Description |
| --- | --- |
| `Browser` | Frontend SPA (React) |
| `Gateway` | api-gateway-bff (Node.js/Express, port 8080) |
| `TranslSvc` | translation-service (Python/FastAPI, port 8087) |
| `BookSvc` | book-service (Go, port 8082) |
| `ProvReg` | provider-registry-service (Go, port 8085) |
| `DB` | loreweave_translation (Postgres) |

---

## 2) SEQ-01: Save User Translation Preferences

```
Browser          Gateway          TranslSvc        DB
  │                │                 │              │
  │ PUT /v1/translation/preferences  │              │
  │ Bearer: <user_jwt>               │              │
  │────────────────>│                │              │
  │                 │ proxy (verify JWT in gateway) │
  │                 │────────────────>│              │
  │                 │                 │ verify JWT sub
  │                 │                 │──────────────
  │                 │                 │ UPSERT user_translation_preferences
  │                 │                 │─────────────>│
  │                 │                 │<─────────────│
  │                 │<────────────────│ 200 + prefs  │
  │<────────────────│                 │              │
```

**Validation enforced by TranslSvc before DB write:**
- `user_prompt_tpl` must contain `{chapter_text}` → 422 `TRANSL_INVALID_PROMPT_TEMPLATE` if missing
- `model_ref` allowed to be null (user may save preferences without a model)

---

## 3) SEQ-02: Load Book Translation Settings (with is_default detection)

```
Browser          Gateway          TranslSvc        DB
  │                │                 │              │
  │ GET /v1/translation/books/{id}/settings         │
  │────────────────>│                │              │
  │                 │────────────────>│              │
  │                 │                 │ SELECT book_translation_settings WHERE book_id=?
  │                 │                 │─────────────>│
  │                 │                 │<─────────────│  (no row found)
  │                 │                 │ SELECT user_translation_preferences WHERE user_id=?
  │                 │                 │─────────────>│
  │                 │                 │<─────────────│  (row found)
  │                 │                 │ Return user prefs + is_default: true
  │                 │<────────────────│              │
  │<────────────────│                 │              │
```

If book row exists: returns book settings + `is_default: false`.
If neither exists: returns hard-coded defaults + `is_default: true`.

---

## 4) SEQ-03: Create Translation Job (Happy Path)

```
Browser       Gateway       TranslSvc     BookSvc       DB
  │             │              │             │            │
  │ POST /v1/translation/books/{book_id}/jobs             │
  │ { chapter_ids: [c1, c2] }  │             │            │
  │─────────────>│             │             │            │
  │              │─────────────>│             │            │
  │              │              │ GET /internal/books/{book_id}/projection
  │              │              │─────────────>│           │
  │              │              │<─────────────│ {owner_user_id, status}
  │              │              │ verify caller == owner   │
  │              │              │             │            │
  │              │              │ resolve_effective_settings()
  │              │              │─────────────────────────>│ SELECT book settings
  │              │              │<─────────────────────────│ (is_default=false: book row exists)
  │              │              │             │            │
  │              │              │ INSERT translation_jobs (pending, settings snapshot)
  │              │              │─────────────────────────>│
  │              │              │ INSERT chapter_translations × N (pending)
  │              │              │─────────────────────────>│
  │              │              │<─────────────────────────│ job_id
  │              │<─────────────│ 201 { job_id, status:'pending', ... }
  │<─────────────│              │             │            │
  │              │              │ [BackgroundTask enqueued]│
```

**Return 201 immediately** — client does not wait for translation to complete.

---

## 5) SEQ-04: Translation Job Execution (Background Task)

```
TranslSvc                   BookSvc         ProvReg          DB
  │                            │               │              │
  │ UPDATE jobs SET status='running'           │              │
  │────────────────────────────────────────────────────────>  │
  │                            │               │              │
  │ mint_user_jwt(owner_user_id, JWT_SECRET, ttl=300)         │
  │──────────────────                          │              │
  │                            │               │              │
  │──── for each chapter_id ──────────────────────────────── │
  │                            │               │              │
  │ UPDATE chapter_translations SET status='running'          │
  │────────────────────────────────────────────────────────>  │
  │                            │               │              │
  │ GET /internal/books/{book_id}/chapters/{chapter_id}       │
  │────────────────────────────>│              │              │
  │<────────────────────────────│ { original_language, body } │
  │                            │               │              │
  │ build user_msg = user_prompt_tpl.format_map(...)          │
  │─────────────────────                       │              │
  │                            │               │              │
  │ [refresh JWT if expiry < 30s]              │              │
  │                            │               │              │
  │ POST /v1/model-registry/invoke             │              │
  │ Authorization: Bearer <minted_jwt>         │              │
  │────────────────────────────────────────────>│             │
  │<────────────────────────────────────────────│ { output.content, usage_log_id }
  │                            │               │              │
  │ UPDATE chapter_translations SET status='completed', translated_body=...
  │────────────────────────────────────────────────────────>  │
  │ UPDATE translation_jobs SET completed_chapters += 1       │
  │────────────────────────────────────────────────────────>  │
  │──── end for ──────────────────────────────────────────── │
  │                            │               │              │
  │ UPDATE translation_jobs SET status='completed'/'partial'/'failed', finished_at
  │────────────────────────────────────────────────────────>  │
```

**Provider gateway invariant**: TranslSvc has no import of openai/anthropic/etc. All model invocations go through ProvReg `/v1/model-registry/invoke`.

---

## 6) SEQ-05: Frontend Polling for Job Status

```
Browser          Gateway          TranslSvc        DB
  │                │                 │              │
  │ [TranslateButton: submitting]    │              │
  │ POST /v1/translation/books/{id}/jobs            │
  │────────────────>│────────────────>│              │
  │<────────────────│<────────────────│ 201 {job_id} │
  │                 │                 │              │
  │ [phase: polling, setInterval 3s] │              │
  │                 │                 │              │
  │ GET /v1/translation/jobs/{job_id}│              │
  │────────────────>│────────────────>│              │
  │                 │                 │ SELECT + completed/total counts
  │                 │                 │─────────────>│
  │<────────────────│<────────────────│ {status:'running', completed:1, total:3}
  │ [progress bar: 1/3]              │              │
  │                 │                 │              │
  │ [3s later]      │                 │              │
  │ GET /v1/translation/jobs/{job_id}│              │
  │────────────────>│────────────────>│              │
  │<────────────────│<────────────────│ {status:'completed', completed:3, total:3}
  │ [phase: done — clearInterval]    │              │
  │ [onJobCreated() callback fires → Section 3 prepend]
```

---

## 7) SEQ-06: Chapter Translation Result Viewer

```
Browser (accordion expanded)   Gateway          TranslSvc        DB
  │                               │                 │              │
  │ GET /v1/translation/jobs/{job_id}/chapters/{chapter_id}        │
  │───────────────────────────────>│────────────────>│              │
  │                               │                 │ SELECT chapter_translations
  │                               │                 │─────────────>│
  │                               │                 │<─────────────│ {status:'completed', translated_body}
  │<───────────────────────────────│<────────────────│              │
  │ [ChapterTranslationPanel: render translated text]
```

---

## 8) SEQ-07: Failure — No Model Configured

```
Browser          Gateway          TranslSvc        DB
  │                │                 │              │
  │ POST /v1/translation/books/{id}/jobs            │
  │────────────────>│────────────────>│              │
  │                 │                 │ resolve_effective_settings()
  │                 │                 │─────────────>│ (model_ref IS NULL)
  │                 │                 │<─────────────│
  │                 │                 │ model_ref is None → 422
  │<────────────────│<────────────────│ 422 {code: 'TRANSL_NO_MODEL_CONFIGURED'}
  │ [TranslateButton: error state]   │              │
```

---

## 9) SEQ-08: Failure — Chapter Not Found During Execution

```
TranslSvc                   BookSvc          DB
  │                            │              │
  │ GET /internal/books/{book_id}/chapters/{bad_chapter_id}
  │────────────────────────────>│             │
  │<────────────────────────────│ 404         │
  │                            │              │
  │ UPDATE chapter_translations SET status='failed', error_message='chapter_not_found'
  │────────────────────────────────────────────>│
  │ UPDATE translation_jobs SET failed_chapters += 1
  │────────────────────────────────────────────>│
  │ [continue to next chapter_id]              │
```

---

## 10) SEQ-09: Failure — Provider Billing Rejected

```
TranslSvc                              ProvReg          DB
  │                                       │              │
  │ POST /v1/model-registry/invoke        │              │
  │───────────────────────────────────────>│             │
  │<───────────────────────────────────────│ 402 Payment Required
  │                                       │              │
  │ UPDATE chapter_translations SET status='failed', error_message='billing_rejected'
  │────────────────────────────────────────────────────>  │
  │ UPDATE translation_jobs SET failed_chapters += 1      │
  │────────────────────────────────────────────────────>  │
  │ [continue to next chapter]            │              │
```

---

## 11) SEQ-10: Startup Recovery Sweep

```
TranslSvc (startup)                         DB
  │                                          │
  │ [lifespan startup hook]                  │
  │                                          │
  │ UPDATE translation_jobs                  │
  │   SET status='failed', error_message='server_restart', finished_at=now()
  │   WHERE status IN ('pending','running')  │
  │     AND created_at < now() - interval '1 hour'
  │──────────────────────────────────────────>│
  │<──────────────────────────────────────────│ N rows updated
  │                                          │
  │ [HTTP server starts accepting requests]  │
```

Prevents jobs stuck in `running` state from server restarts appearing permanently active to polling clients.
