# Phase 5e-α Design — video-gen-service Migration to Unified Gateway

> **Status**: REVIEWED — `/review-impl` round 1 caught 0 HIGH + 2 MED + 3 LOW + 1 COSMETIC. ALL 5 actionable findings folded inline (MED#1 record_usage signature widening; MED#2 drop dead `provider_registry_url`; LOW#3 `_aspect_to_size` unit test added to plan; LOW#4 "presumably broken" → "untestable today" wording; LOW#5 deferred as `D-PHASE5E-JWT-VERIFY-DEFENSE-IN-DEPTH`). COSMETIC#6 skip.
> **Cycle**: C-LLM-PHASE-5E-ALPHA
> **Size**: XL (files ≈13 · logic ≈6 · side-effects: 1 compose context bump + 1 Dockerfile SDK install + remove provider-registry /internal/credentials direct call)
> **Plan ref**: [LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md §5](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md)
> **Predecessor**: Phase 5d (video_gen adapter shipped) at HEAD `b3f046ab`
> **CLARIFY answers locked**: (1) per-call SDK `Client` instantiation (mirrors Phase 5b chat-service voice migration + sibling stream_service.py pattern); (2) SDK→HTTP error mapping EXTRACTED to a helper (`app/llm_errors.py::map_llm_error_to_http_exception`) so future video-gen-service endpoints can reuse.
> **Strategic context (Path B step 3)**: 5c-α + 5d shipped the gateway adapters; this cycle migrates the FIRST caller (video-gen-service — Python). Phase 5e-β will follow with book-service (Go; needs Go SDK decision). After 5e-β + 5f (BFF deletion), the unified gateway invariant is fully realized.

---

## 1. Goals

1. **video-gen-service `/v1/video-gen/generate` route** stops calling provider-registry `/internal/credentials/...` + direct httpx POST to `/v1/video/generations`. Replaced with `loreweave_llm.Client.generate_video()` calling through the unified gateway (Phase 5d `operation=video_gen`).
2. **First test suite** for video-gen-service. The service has NO `tests/` directory today. This cycle adds:
   - `tests/conftest.py` (shared fixtures, env defaults)
   - `tests/test_generate.py` (happy path + 4-6 error mappings + img2vid future-proof)
   - `tests/test_no_dead_resolution.py` (grep-lock: `provider.resolve` / `internal/credentials` banned from `routers/generate.py`)
3. **SDK install** in video-gen-service Docker image (mirror translation-service Phase 4c-α + chat-service patterns: COPY sdks/python + pip install).
4. **Caller-side download + MinIO storage + billing** STAYS in video-gen-service. Matches chat-service voice precedent — gateway forwards URL/bytes, caller owns storage + billing per [LLM_PIPELINE_PHASE5C_DESIGN.md §3.3](LLM_PIPELINE_PHASE5C_DESIGN.md) + Phase 5b voice migration.

### Non-goals

- **book-service migration** (Go). Phase 5e-β; needs Go SDK vs shim decision.
- **video-gen-service deletion**. Phase 5f.
- **api-gateway-bff `/v1/video-gen/*` route deprecation**. Phase 5f.
- **FE migration**. Phase 5f; FE keeps calling `/v1/video-gen/generate` until video-gen-service is replaced or facaded.
- **Backfill of existing direct-httpx-call telemetry**. Pre-5e metrics from `Phase 5d` row in usage-billing remain as-is; 5e-α just changes the future telemetry source.

---

## 2. Migration surface

### 2.1 Existing flow (legacy — to be replaced)

`services/video-gen-service/app/routers/generate.py:109-222`:

```
POST /v1/video-gen/generate
  → extract user_id from JWT (header forwarded by api-gateway-bff)
  → 1. resolve_credentials(model_source, model_ref, user_id)
       → GET {PROVIDER_REGISTRY_URL}/internal/credentials/.../...?user_id=...
       → response: {provider_kind, provider_model_name, base_url, api_key}
  → 2. httpx POST {base_url}/v1/video/generations
       → body: {model, prompt, size, duration, n, style?}
       → response: {created, data: [{url}]}
  → 3. httpx GET {data[0].url}
       → download video bytes
       → upload to MinIO bucket loreweave-media
  → 4. record_usage(...)  (best-effort)
  → 5. return GenerateResponse (with MinIO-presigned URL)
```

Steps 1-2 hit upstream directly. Step 2 today goes to `/v1/video/generations` (singular) which doesn't exist in `local-image-generator-service` (see Phase 5d HIGH#1). The service has NO tests today (per `ls services/video-gen-service/tests/` — directory absent), so the actual run-state against the real backend is **untestable today** rather than "verified broken". 5e-α's test additions provide the first coverage; the path migration via the SDK fixes the underlying drift either way. /review-impl(DESIGN) LOW#4.

### 2.2 Target flow (5e-α)

```
POST /v1/video-gen/generate
  → extract user_id from JWT
  → 1+2 (merged): Client.generate_video(
       prompt=body.prompt,
       model_source=body.model_source,
       model_ref=body.model_ref,
       size=_aspect_to_size(body.aspect_ratio),
       duration=body.duration_seconds,
       style=body.style,
       init_image=None,  # 5e-α stays txt2vid only
       user_id=user_id,
     )
       → SDK handles: credential resolve + upstream POST + polling + retries
       → returns VideoGenResult(created=..., data=[VideoGenDataItem(url=...)])
  → 3. httpx GET {result.data[0].url}  (unchanged — caller-side download)
  → 4. upload to MinIO  (unchanged)
  → 5. record_usage(...)  (unchanged)
  → 6. return GenerateResponse  (unchanged shape — backward-compat with FE)
```

Lines deleted: ~50 (`resolve_credentials` + direct httpx call + manual error handling). Lines added: ~30 (Client construction + error mapping helper). Net: smaller + cleaner.

### 2.3 Error mapping helper (Fix CLARIFY-Q2)

New file `services/video-gen-service/app/llm_errors.py`:

```python
"""Map loreweave_llm exceptions → FastAPI HTTPException with the right status.

Centralized so any future video-gen-service endpoint using the SDK
(e.g., image_gen via generate_image, image variations, etc.) gets
consistent caller-facing error semantics.
"""
from fastapi import HTTPException
from loreweave_llm import (
    LLMAuthFailed,
    LLMError,
    LLMInvalidRequest,
    LLMJobTerminal,
    LLMModelNotFound,
    LLMQuotaExceeded,
    LLMRateLimited,
    LLMUpstreamError,
    LLMVideoContentPolicy,
    LLMVideoGenerationFailed,
)


def map_llm_error_to_http_exception(exc: LLMError) -> HTTPException:
    """Map a loreweave_llm exception to a FastAPI HTTPException.

    Status code conventions:
      - 400 LLM_INVALID_REQUEST → caller-side input issue
      - 400 LLM_VIDEO_CONTENT_POLICY_VIOLATION → caller's prompt rejected
            by upstream safety; FE should surface as "rephrase your prompt"
      - 402 LLM_QUOTA_EXCEEDED → billing
      - 404 LLM_MODEL_NOT_FOUND → user_model doesn't exist
      - 409 LLM_JOB_TERMINAL → job was cancelled
      - 429 LLM_RATE_LIMITED → caller should back off
      - 502 LLM_UPSTREAM_ERROR / LLM_VIDEO_GENERATION_FAILED → backend failed
      - 504 LLM_AUTH_FAILED → upstream rejected our BYOK key (rare;
            usually rotated key — UI should prompt re-register)
    """
    if isinstance(exc, LLMInvalidRequest):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, LLMVideoContentPolicy):
        return HTTPException(status_code=400, detail=f"Content policy: {exc}")
    if isinstance(exc, LLMQuotaExceeded):
        return HTTPException(status_code=402, detail=str(exc))
    if isinstance(exc, LLMModelNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, LLMJobTerminal):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, LLMRateLimited):
        return HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, LLMVideoGenerationFailed):
        return HTTPException(status_code=502, detail=f"Video generation failed: {exc}")
    if isinstance(exc, LLMUpstreamError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, LLMAuthFailed):
        return HTTPException(status_code=502, detail=f"Provider auth failed: {exc}")
    # Generic LLMError fallback
    return HTTPException(status_code=502, detail=str(exc))
```

**Order matters**: more-specific subclasses BEFORE generic `LLMError`. Follows the Phase 4c-β lesson saved as memory `feedback_specific_sdk_exception_catches_before_generic`.

### 2.4 Migrated `generate.py` (sketch)

```python
from loreweave_llm import Client, LLMError, VideoGenResult

from app.config import settings
from app.llm_errors import map_llm_error_to_http_exception

# ... extract_user_id helper unchanged ...

@router.post("/generate", response_model=GenerateResponse, status_code=201)
async def generate_video(
    body: GenerateRequest,
    authorization: str = Header(default=""),
):
    user_id = extract_user_id(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authorization required")
    if not body.model_ref:
        raise HTTPException(status_code=400, detail="model_ref is required")

    # 1+2 (merged): call gateway via SDK
    client = Client(
        base_url=settings.provider_registry_internal_url,
        auth_mode="internal",
        internal_token=settings.internal_service_token,
        user_id=user_id,
    )
    try:
        result: VideoGenResult = await client.generate_video(
            prompt=body.prompt,
            model_source=body.model_source,
            model_ref=body.model_ref,
            size=_aspect_to_size(body.aspect_ratio),
            duration=body.duration_seconds,
            style=body.style,
        )
    except LLMError as exc:
        raise map_llm_error_to_http_exception(exc)
    finally:
        await client.aclose()

    if not result.data or not result.data[0].url:
        raise HTTPException(status_code=502, detail="Gateway returned no video URL")
    video_url_remote = result.data[0].url

    # 3. Download and store in MinIO (unchanged from legacy)
    # ... same try/except block as today ...

    # 4. Best-effort usage billing.
    # /review-impl(DESIGN) MED#1 — gateway's generate_video() doesn't
    # return provider_kind (it's resolved internally). record_usage
    # signature widened to `provider_kind: str | None = None` so the
    # None pass-through is type-checker-clean. usage-billing-service
    # decodes JSON `null` as empty string (Go non-pointer string at
    # server.go:216) which is acceptable for analytics partitioning
    # (video_gen rows have empty provider_kind; chat rows have the
    # real value). If analytics dashboards need video provider_kind
    # later, add a separate lookup call to provider-registry's
    # /internal/credentials at billing time.
    await record_usage(user_id, None, body.model_source, body.model_ref, len(body.prompt))

    # 5. Return (unchanged shape)
    return GenerateResponse(
        status="completed",
        video_url=local_url,
        thumbnail_url=None,
        message=None,
        model=body.model_ref,  # gateway doesn't return provider_model_name; use ref
        duration_seconds=body.duration_seconds,
        size_bytes=video_size,
        content_type=content_type,
    )
```

Key deletions:
- `resolve_credentials()` function (lines ~46-65) — DROP
- imports for direct httpx provider call (kept httpx ONLY for the download step at line 184-186)
- `provider_kind` extraction + base_url-fallback logic
- Direct upstream timeout/error handling — now via SDK + helper

### 2.5 Config

New file `services/video-gen-service/app/config.py` (mirror translation-service Phase 4c-α pattern):

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # /review-impl(DESIGN) MED#2 — `provider_registry_url` (the legacy
    # /internal/credentials reader) is DROPPED in 5e-α. After this
    # migration no code in video-gen-service reads it; keeping it would
    # invite config drift before 5f deletes the whole service.
    # Phase 5b's chat-service migration set the precedent (dropped its
    # legacy provider_registry_service_url at migration time).
    provider_registry_internal_url: str = "http://provider-registry-service:8085"  # SDK uses this
    internal_service_token: str
    usage_billing_service_url: str = "http://usage-billing-service:8088"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str
    minio_secret_key: str
    minio_external_url: str = "http://localhost:9123"


settings = Settings()
```

Single source-of-truth env: `PROVIDER_REGISTRY_INTERNAL_URL`. The compose entry's existing `PROVIDER_REGISTRY_URL` env var becomes dead and should be removed in T7 (compose update) for consistency. Existing `internal_service_token` retained because the SDK auth_mode='internal' constructor requires it (same X-Internal-Token used everywhere).

### 2.6 Dockerfile

Mirror translation-service Phase 4c-α SDK install pattern. Build context bumps to repo root in compose.

```dockerfile
FROM python:3.13-slim
WORKDIR /app

# SDK install — Phase 5e-α. Copy from repo-root context.
COPY sdks/python /tmp/loreweave_llm
RUN pip install --no-cache-dir /tmp/loreweave_llm

COPY services/video-gen-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/video-gen-service/app ./app
EXPOSE 8088
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]
```

### 2.7 docker-compose.yml

Bump `video-gen-service.build.context` from `../services/video-gen-service` to `..` (repo root). Add `dockerfile: services/video-gen-service/Dockerfile` for clarity.

### 2.8 Tests (NEW — first tests for this service)

`tests/conftest.py` — async/httpx-mock infrastructure (mirror chat-service test pattern):

```python
from collections.abc import AsyncIterator
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client() -> TestClient:
    return TestClient(app)

# Async fixture mocking the loreweave_llm Client.
# Use respx or httpx.MockTransport in individual tests.
```

`tests/test_generate.py` — 7 cases:
1. `test_generate_happy_path_uses_sdk_not_direct_httpx` — submits to /generate; mock SDK's submit + poll; verify the wire shape (operation=video_gen, model_source, etc.); verify result MinIO upload + presigned URL returned
2. `test_generate_quota_exceeded_returns_402` — mock SDK raises LLMQuotaExceeded; assert HTTP 402
3. `test_generate_content_policy_returns_400` — mock SDK raises LLMVideoContentPolicy; assert HTTP 400 with "Content policy" prefix
4. `test_generate_model_not_found_returns_404` — mock SDK raises LLMModelNotFound; assert HTTP 404
5. `test_generate_video_generation_failed_returns_502` — mock SDK raises LLMVideoGenerationFailed; assert HTTP 502
6. `test_generate_rate_limited_returns_429` — mock SDK raises LLMRateLimited; assert HTTP 429
7. `test_aspect_to_size_mapping` — pure-function unit test for `_aspect_to_size("16:9"|"9:16"|"1:1"|"4:3"|"3:4"|"unknown")` per /review-impl(DESIGN) LOW#3. Regression-lock against accidental mapping drift.

`tests/test_no_dead_resolution.py` — grep-lock (mirror chat-service Phase 5b regression-lock):
- `provider.resolve` MUST NOT appear in `routers/generate.py`
- `/internal/credentials` MUST NOT appear in `routers/generate.py`
- `loreweave_llm` import MUST appear in `routers/generate.py`
- `Client` reference MUST appear in `routers/generate.py`

Note: cannot fully ban httpx from `routers/generate.py` because the download step (Step 3) still uses httpx. The lock targets the GATEWAY call drift, not all httpx use.

---

## 3. Build plan (PLAN phase)

| # | Task | Files | Size |
|---|------|-------|------|
| T1 | Create `services/video-gen-service/app/config.py` with pydantic Settings (provider_registry_internal_url, internal_service_token, MinIO, usage-billing URLs) | NEW config.py | XS |
| T2 | Create `services/video-gen-service/app/llm_errors.py` with `map_llm_error_to_http_exception` helper (specific-before-generic ordering per memory) | NEW llm_errors.py | XS |
| T3 | Migrate `services/video-gen-service/app/routers/generate.py`: drop `resolve_credentials` + drop direct httpx POST; use SDK `Client.generate_video()` + helper; preserve download + MinIO + billing flow. **Also widen `record_usage` signature** to `provider_kind: str \| None = None` per /review-impl(DESIGN) MED#1 (gateway doesn't return provider_kind). | MOD generate.py | M |
| T4 | Update `services/video-gen-service/app/main.py`: import settings; ensure config validation at startup; (no lifespan changes needed — per-call Client) | MOD main.py | XS |
| T5 | Update `services/video-gen-service/Dockerfile`: SDK install via COPY sdks/python + pip install (context = repo root); adjust WORKDIR paths | MOD Dockerfile | XS |
| T6 | Update `services/video-gen-service/requirements.txt`: SDK install path note (matches translation-service convention) | MOD requirements.txt | XS |
| T7 | Update `infra/docker-compose.yml`: bump video-gen-service `build.context` to `..` (repo root) + add `dockerfile: services/video-gen-service/Dockerfile`; ensure `PROVIDER_REGISTRY_INTERNAL_URL` + `INTERNAL_SERVICE_TOKEN` env are wired; **REMOVE legacy `PROVIDER_REGISTRY_URL` env entry** per /review-impl(DESIGN) MED#2 (dead config after migration). | MOD docker-compose.yml | XS |
| T8 | NEW `services/video-gen-service/tests/__init__.py` + `tests/conftest.py` (TestClient + env defaults; mirror chat-service pattern) | NEW 2 files | S |
| T9 | NEW `services/video-gen-service/tests/test_generate.py` — 6 cases (happy path + 5 error mappings) | NEW test file | M |
| T10 | NEW `services/video-gen-service/tests/test_no_dead_resolution.py` — 4 grep-lock assertions | NEW test file | S |
| T11 | Doc updates: `LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md` 5e-α row ✅; design status flip; SESSION_PATCH inline at commit time | MOD plan + this design | XS |

Total: ~13 files (4 NEW + 7 MOD + 2 NEW test files). Build order: T1-T2 (config + helper); T3-T4 (router migration); T5-T7 (Docker + compose); T8-T10 (tests); T11 (docs).

---

## 4. Open questions / risks

| # | Question | Answer / mitigation |
|---|---|---|
| Q1 | The gateway's adapter dispatches text-to-video vs image-to-video based on `init_image`. video-gen-service today only does txt2vid. Should 5e-α expose img2vid via the FE? | NO. 5e-α preserves the existing `/v1/video-gen/generate` contract (txt2vid only). Img2vid is a future cycle — the FE doesn't have an init_image upload yet. Defer as `D-PHASE5E-IMG2VID-FE-INTEGRATION`. |
| Q2 | The SDK's `generate_video()` doesn't return `provider_kind` or `provider_model_name`. The existing response shape includes `model` field. What goes there? | Use `body.model_ref` (the UUID). Caller-side display logic can resolve to human-readable name via the existing user-models list endpoint. Slight contract drift; acceptable. |
| Q3 | Billing today passes `provider_kind`. SDK doesn't return it. | `record_usage(provider_kind=None, ...)`. usage-billing-service tolerates None per its existing schema. Accept. |
| Q4 | What happens to the existing `provider_registry_url` config field after this cycle? | Retained alongside `provider_registry_internal_url` (same value). Both deleted in Phase 5f. |
| Q5 | Live smoke against local-image-generator-service? | Deferred to `D-PHASE5E-LIVE-SMOKE`. Cross-validates 5d's path dispatch too. |
| Q6 | `extract_user_id` decodes the JWT without signature verification, trusting that api-gateway-bff validated upstream. Defense-in-depth? | (/review-impl(DESIGN) LOW#5) Pre-existing risk (not introduced by 5e-α). 5e-α preserves the behavior; if a future mesh-call path bypasses bff, this caller would trust arbitrary tokens. Deferred as `D-PHASE5E-JWT-VERIFY-DEFENSE-IN-DEPTH` — adds local JWT signature verification (matching auth-service's public key) as belt-and-suspenders. Track for hardening when service-mesh changes land. |
| Q7 | After migration, `provider_kind` is None for video_gen rows in usage-billing. Dashboards grouping by provider_kind see empty-string category for video_gen vs. populated for chat. | (/review-impl(QC) LOW#6) Pre-existing if billing tolerated empty values; new analytics-partitioning behavior introduced by 5e-α. Deferred as `D-PHASE5E-BILLING-PROVIDER-KIND-ANALYTICS` — if a real dashboard breaks, add a separate post-job lookup to provider-registry to backfill `provider_kind` at billing time. No FE breakage observed yet. |
| Q8 | `get_minio().bucket_exists()` + `make_bucket()` run synchronously inside the async route's `/generate` handler (first call only — cached afterward via the `_minio` global). | (/review-impl(QC) COSMETIC#7) Pre-existing pattern (original code had it); context-switch hazard only on first request post-cold-start. Deferred as `D-PHASE5E-MINIO-ASYNC-OFFLOAD` — move bucket bootstrap to lifespan startup (already-async) if first-request latency surfaces as a real concern. |

---

## 5. Acceptance criteria (QC phase)

- [ ] `pytest services/video-gen-service/tests/` ALL GREEN (~10 tests new)
- [ ] No regression in existing services (no other tests touch video-gen-service today)
- [ ] `grep -rn "/internal/credentials" services/video-gen-service/app/` returns no matches in router code
- [ ] `grep -rn "loreweave_llm" services/video-gen-service/app/routers/generate.py` returns the import
- [ ] Compose builds clean: `docker compose -f infra/docker-compose.yml build video-gen-service`
- [ ] `/review-impl` on design returns no HIGH-severity findings
- [ ] `/review-impl` on post-BUILD returns no HIGH; MEDs fixed inline before commit
- [ ] LIVE smoke deferred to `D-PHASE5E-LIVE-SMOKE`

---

## 6. Phase 5e-β / 5f preview

- **5e-β (TBD-L-XL)** — book-service (Go) migration. Needs Go SDK decision:
  - Option A: build `sdks/go/loreweave_llm` parallel to Python (future-proofs auth-service / sharing-service / glossary-service migrations to SDK)
  - Option B: inline thin HTTP shim in book-service media handler (60-100 LOC, throwaway)
  - Recommend: revisit AFTER 5e-α ships and we've observed the Python SDK actually working in production.
- **5f (M)** — Delete `services/video-gen-service/`. Remove compose entry. Retire `/v1/video-gen/*` routes in api-gateway-bff. FE migrates to calling unified gateway via SDK-equivalent (or facade). After 5f: unified gateway invariant fully realized.
