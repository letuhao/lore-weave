# LoreWeave Module 04 Backend Detailed Design

## Document Metadata

- Document ID: LW-M04-63
- Version: 0.1.0
- Status: Approved
- Owner: Solution Architect + Backend Lead
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-22
- Summary: Detailed backend design for translation-service including domain model, settings merge, JWT minting, job execution pipeline, provider invocation, and failure handling.

## Change History

| Version | Date       | Change                            | Author    |
| ------- | ---------- | --------------------------------- | --------- |
| 0.1.0   | 2026-03-22 | Initial Module 04 backend design  | Assistant |

## 1) Domain Model

### Settings Domain

- `UserTranslationPreferences` — user-level defaults
- `BookTranslationSettings` — per-book overrides
- `EffectiveSettings` — in-memory resolved struct (not persisted)

### Job Domain

- `TranslationJob` — job record with settings snapshot and chapter list
- `ChapterTranslation` — per-chapter execution record with result

## 2) Database Schema

### `user_translation_preferences`

```sql
CREATE TABLE IF NOT EXISTS user_translation_preferences (
  user_id         UUID PRIMARY KEY,
  target_language TEXT NOT NULL DEFAULT 'en',
  model_source    TEXT NOT NULL DEFAULT 'platform_model',
  model_ref       UUID,
  system_prompt   TEXT NOT NULL DEFAULT '',
  user_prompt_tpl TEXT NOT NULL DEFAULT '',
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `book_translation_settings`

```sql
CREATE TABLE IF NOT EXISTS book_translation_settings (
  book_id         UUID PRIMARY KEY,
  owner_user_id   UUID NOT NULL,
  target_language TEXT NOT NULL DEFAULT 'en',
  model_source    TEXT NOT NULL DEFAULT 'platform_model',
  model_ref       UUID,
  system_prompt   TEXT NOT NULL DEFAULT '',
  user_prompt_tpl TEXT NOT NULL DEFAULT '',
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bts_owner ON book_translation_settings(owner_user_id);
```

### `translation_jobs`

```sql
CREATE TABLE IF NOT EXISTS translation_jobs (
  job_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id            UUID NOT NULL,
  owner_user_id      UUID NOT NULL,
  status             TEXT NOT NULL DEFAULT 'pending',
  target_language    TEXT NOT NULL,
  model_source       TEXT NOT NULL,
  model_ref          UUID NOT NULL,
  system_prompt      TEXT NOT NULL,
  user_prompt_tpl    TEXT NOT NULL,
  chapter_ids        UUID[] NOT NULL,
  total_chapters     INT NOT NULL DEFAULT 0,
  completed_chapters INT NOT NULL DEFAULT 0,
  failed_chapters    INT NOT NULL DEFAULT 0,
  error_message      TEXT,
  started_at         TIMESTAMPTZ,
  finished_at        TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tj_owner ON translation_jobs(owner_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tj_book  ON translation_jobs(book_id, created_at DESC);
```

### `chapter_translations`

```sql
CREATE TABLE IF NOT EXISTS chapter_translations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id          UUID NOT NULL REFERENCES translation_jobs(job_id) ON DELETE CASCADE,
  chapter_id      UUID NOT NULL,
  book_id         UUID NOT NULL,
  owner_user_id   UUID NOT NULL,
  status          TEXT NOT NULL DEFAULT 'pending',
  translated_body TEXT,
  source_language TEXT,
  target_language TEXT NOT NULL,
  input_tokens    INT,
  output_tokens   INT,
  usage_log_id    UUID,
  error_message   TEXT,
  started_at      TIMESTAMPTZ,
  finished_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ct_job     ON chapter_translations(job_id, chapter_id);
CREATE INDEX IF NOT EXISTS idx_ct_chapter ON chapter_translations(chapter_id, created_at DESC);
```

## 3) Configuration (`app/config.py`)

```python
from pydantic_settings import BaseSettings

DEFAULT_SYSTEM_PROMPT = (
    "You are a professional literary translator. "
    "Preserve the style, tone, pacing, and voice of the original text. "
    "Do not add commentary, explanations, or translator notes. "
    "Translate faithfully and naturally."
)
DEFAULT_USER_PROMPT_TPL = (
    "Translate the following {source_language} text into {target_language}. "
    "Output only the translated text, nothing else.\n\n{chapter_text}"
)

class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    book_service_internal_url: str = "http://book-service:8082"
    provider_registry_service_url: str = "http://provider-registry-service:8085"
    port: int = 8087

    class Config:
        env_file = ".env"
```

## 4) Auth Module (`app/auth.py`)

```python
import jwt, time

def mint_user_jwt(user_id: str, jwt_secret: str, ttl_seconds: int = 300) -> str:
    now = int(time.time())
    payload = {"sub": user_id, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, jwt_secret, algorithm="HS256")

def verify_request_jwt(token: str, jwt_secret: str) -> str:
    """Validate incoming Bearer token, return user_id (sub claim)."""
    data = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    return data["sub"]
```

The `verify_request_jwt` function is called in a FastAPI dependency (`get_current_user`) to extract the `user_id` from incoming requests. Returns HTTP 401 on failure.

## 5) Settings Merge Logic

Applied in job creation (`POST /v1/translation/books/{book_id}/jobs`):

```python
async def resolve_effective_settings(user_id, book_id, db, config):
    # 1. Try book-level settings
    row = await db.fetchrow(
        "SELECT * FROM book_translation_settings WHERE book_id=$1 AND owner_user_id=$2",
        book_id, user_id
    )
    if row:
        return dict(row), False  # (settings, is_default)

    # 2. Try user-level preferences
    row = await db.fetchrow(
        "SELECT * FROM user_translation_preferences WHERE user_id=$1", user_id
    )
    if row:
        return dict(row), True

    # 3. Fall back to hard-coded defaults
    return {
        "target_language": "en",
        "model_source": "platform_model",
        "model_ref": None,
        "system_prompt": config.DEFAULT_SYSTEM_PROMPT,
        "user_prompt_tpl": config.DEFAULT_USER_PROMPT_TPL,
    }, True
```

If `model_ref is None` after merge → raise 422 `TRANSL_NO_MODEL_CONFIGURED`.

## 6) Provider Gateway Invariant

- Translation-service has no direct imports of `openai`, `anthropic`, or any provider SDK.
- All model invocations use `httpx.AsyncClient` to call `POST {PROVIDER_REGISTRY_SERVICE_URL}/v1/model-registry/invoke`.
- Request body: `{ "model_source": str, "model_ref": str, "input": { "messages": [...] } }`.
- Authorization: `Bearer <minted_jwt>` where the JWT has `sub == owner_user_id`.
- A unit test must import `translation_runner.py` and assert no provider SDK symbols are present.

## 7) JWT Minting for Service Invocation

Translation-service mints a user-identity JWT to authenticate with `provider-registry-service`:

```python
# At job start:
token = mint_user_jwt(user_id=str(job.owner_user_id), jwt_secret=settings.jwt_secret)
token_exp = time.time() + 300

# Per chapter, before invoke call:
if time.time() > token_exp - 30:
    token = mint_user_jwt(...)
    token_exp = time.time() + 300
```

This ensures the minted token is always fresh enough to complete a single provider invocation.

## 8) Job Execution Flow (`app/services/translation_runner.py`)

```
run_translation_job(job_id: UUID, user_id: str, settings: Settings, db_pool):

1. UPDATE translation_jobs SET status='running', started_at=now() WHERE job_id=?
2. Load job row (settings snapshot, chapter_ids, book_id)
3. Mint user JWT (TTL=300 s)
4. async with httpx.AsyncClient(timeout=60) as client:
     for chapter_id in job.chapter_ids:
       a. UPDATE chapter_translations SET status='running', started_at=now()
          WHERE job_id=? AND chapter_id=?

       b. r = await client.get(
              f"{BOOK_SERVICE_INTERNAL_URL}/internal/books/{job.book_id}/chapters/{chapter_id}"
          )
          if r.status_code == 404:
              mark chapter failed("chapter_not_found"); continue

       c. chapter = r.json()
          user_msg = job.user_prompt_tpl.format_map({
              "source_language": chapter["original_language"],
              "target_language": job.target_language,
              "chapter_text": chapter["body"]
          })

       d. Refresh JWT if expiring soon

       e. r = await client.post(
              f"{PROVIDER_REGISTRY_SERVICE_URL}/v1/model-registry/invoke",
              json={
                  "model_source": job.model_source,
                  "model_ref": str(job.model_ref),
                  "input": {
                      "messages": [
                          {"role": "system", "content": job.system_prompt},
                          {"role": "user", "content": user_msg}
                      ]
                  }
              },
              headers={"Authorization": f"Bearer {token}"}
          )
          if r.status_code == 402:
              mark chapter failed("billing_rejected"); continue
          if r.status_code >= 500:
              mark chapter failed("provider_error"); continue
          if not r.is_success:
              mark chapter failed(f"invoke_error_{r.status_code}"); continue

       f. resp = r.json()
          translated_body = resp["output"]["content"]
          usage_log_id = resp.get("usage_log_id")
          input_tokens = resp.get("usage", {}).get("input_tokens")
          output_tokens = resp.get("usage", {}).get("output_tokens")

       g. UPDATE chapter_translations SET
              status='completed', translated_body=?, source_language=?,
              input_tokens=?, output_tokens=?, usage_log_id=?, finished_at=now()
          UPDATE translation_jobs SET completed_chapters=completed_chapters+1

5. Determine final job status:
     if failed_chapters == 0 → 'completed'
     elif completed_chapters > 0 → 'partial'
     else → 'failed'
6. UPDATE translation_jobs SET status=?, finished_at=now()
```

## 9) Startup Recovery

In `app/main.py` lifespan startup hook:

```python
await db.execute("""
  UPDATE translation_jobs
  SET status = 'failed', error_message = 'server_restart', finished_at = now()
  WHERE status IN ('pending', 'running')
    AND created_at < now() - interval '1 hour'
""")
```

This prevents jobs from appearing permanently `running` after a server restart.

## 10) Endpoint Ownership

| Endpoint | Handler module | Auth dependency |
| --- | --- | --- |
| `GET /v1/translation/preferences` | `routers/settings.py` | `get_current_user` (JWT verify) |
| `PUT /v1/translation/preferences` | `routers/settings.py` | `get_current_user` |
| `GET /v1/translation/books/{book_id}/settings` | `routers/settings.py` | `get_current_user` |
| `PUT /v1/translation/books/{book_id}/settings` | `routers/settings.py` | `get_current_user` + owner check |
| `POST /v1/translation/books/{book_id}/jobs` | `routers/jobs.py` | `get_current_user` + owner check via book-service |
| `GET /v1/translation/books/{book_id}/jobs` | `routers/jobs.py` | `get_current_user` |
| `GET /v1/translation/jobs/{job_id}` | `routers/jobs.py` | `get_current_user` + owner check |
| `GET /v1/translation/jobs/{job_id}/chapters/{chapter_id}` | `routers/jobs.py` | `get_current_user` + owner check |

## 11) Error Response Shape

All errors return `{ "code": "TRANSL_...", "message": "..." }` with appropriate HTTP status. No stack traces in response body. Error code prefix is `TRANSL_` (functional, not module-numbered).

## 12) httpx Response Parsing Note

The `provider-registry-service` invoke response does not include a top-level `usage` key — tokens are embedded in the billing record. The actual response shape from `invokeModel` is:
```json
{
  "request_id": "uuid",
  "usage_log_id": "uuid",
  "output": { "content": "...", ... },
  "billing_cost": 0.0004,
  "billing_mode": "quota",
  "provider_kind": "openai"
}
```
Token counts are exposed via **both** mechanisms:
1. **Direct in API response**: `input_tokens` and `output_tokens` fields in `ChapterTranslation`. Requires provider-registry-service invoke response to include `usage.input_tokens` / `usage.output_tokens`. If not present in invoke response, these fields will be `null` (graceful degradation).
2. **Cross-reference**: `usage_log_id` links to the billing record in `usage-billing-service` where token counts are authoritative.

**Dependency note**: To populate token counts directly, coordinate with provider-registry-service to expose `usage` in the invoke response shape. This is a cross-service contract change tracked as a follow-up if not in initial M04 scope.
