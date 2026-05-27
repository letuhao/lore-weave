# LLM Pipeline Phase 5f — video-gen-service hardening

> **Status**: SHIPPED — `/review-impl` round 1 on DESIGN (1 HIGH + 3 MED +
> 3 LOW + 1 COSMETIC, all folded before BUILD) + round 2 on BUILD (0 HIGH +
> 1 MED + 4 LOW + 2 COSMETIC, ALL fixed inline). BUILD verified: 25 tests
> pass.

### `/review-impl` round 2 (on BUILD delta)

| # | Sev | Fix |
|---|-----|-----|
| 1 | 🟡 MED | `ensure_bucket_ready` (the function the DESIGN-round HIGH#1 fix introduced) had no direct test — the `_bucket_ready` short-circuit was unlocked. Added `test_ensure_bucket_ready_short_circuits_when_ready` + `test_ensure_bucket_ready_self_heals_when_not_ready`. |
| 2 | 🟢 LOW | `_PUBLIC_READ_POLICY` JSON validity unasserted (substring checks pass on malformed JSON). Added `json.loads` + structural asserts to `test_ensure_bucket_sets_public_read_policy`. |
| 3 | 🟢 LOW | `PyJWT>=2.8` was unpinned vs the file's `==` convention. Pinned `PyJWT==2.10.1`. |
| 4 | 🟢 LOW | `/models` grep-lock was double-quote-specific. Now checks both `"/models"` and `'/models'`. |
| 5 | 🟢 LOW | `_bucket_ready` reset fixture was local to `test_bucket_bootstrap.py`. Moved to a service-wide autouse fixture in `conftest.py`. |
| 6 | 🔵 COSMETIC | `test_generate.py` docstring said "Phase 5e-α tests" → "Phase 5e-α + 5f". |
| 7 | 🔵 COSMETIC | `ensure_bucket_ready()` failure surfaced as "Failed to store video" though storage wasn't attempted. Moved out of the download/store try-block with its own accurate `Media storage unavailable` message. |
> **Created**: 2026-05-15 (session 57, cycle C-LLM-PHASE-5F)
> **Supersedes**: the original Phase 5f scope ("video-gen-service deletion + FE
> migration"). See §1.

---

## 1. Why Phase 5f was redefined

The refactor plan ([LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md](./LLM_PIPELINE_UNIFIED_REFACTOR_PLAN.md) §5f)
listed Phase 5f as *"video-gen-service deletion + api-gateway-bff `/v1/video-gen/*`
retirement + FE migration to call unified gateway directly."*

CLARIFY surfaced that this is **not viable as stated**:

- video-gen-service is **not a pure proxy**. Its `/generate` route does
  caller-side work that nothing else does: it downloads the generated video
  and persists it to MinIO (`loreweave-media`), and it records usage billing.
- The gateway's `video_gen` result is the **raw upstream provider URL**
  (Phase 5d — url-only, no gateway-side staging). For a local ComfyUI backend
  (`local-image-generator-service`) that URL is internal-network-only — a
  browser cannot fetch it.
- "FE calls the gateway directly" would therefore lose MinIO persistence +
  billing and break entirely for local video backends. It also contradicts
  the plan's own Q2 recommendation (domain service mediates).

**Decision (user, session 57):** keep video-gen-service as a permanent thin
domain BFF — the same role book-service plays for chapter-block image/audio
media. Phase 5f is redefined as a **hardening cycle**: treat video-gen-service
as a first-class permanent service and close the gaps an audit found.

The unified-gateway program is otherwise complete — every service's LLM/audio/
image/video calls go through `provider-registry`. video-gen-service already
calls the gateway via the SDK (Phase 5e-α). It is a domain wrapper, not a
violation.

---

## 2. Audit gaps addressed this cycle

| ID | Gap | Severity |
|----|-----|----------|
| **G1** | `/models` endpoint is dead code: zero FE callers (FE uses `aiModelsApi.listUserModels`), always returns empty, and has a wrong-kwarg bug (`ModelsResponse(models=[])` — schema field is `items`). | Cleanup |
| **G2** | MinIO bucket bootstrap (`bucket_exists` + `make_bucket`) runs lazily on the **first request's hot path** (`get_minio()`). Deferred item `D-PHASE5E-MINIO-ASYNC-OFFLOAD`. | Cosmetic |
| **G3** | JWT signature is **not verified** — `extract_user_id` base64-decodes the payload with no verification, blindly trusting api-gateway-bff. Deferred item `D-PHASE5E-JWT-VERIFY-DEFENSE-IN-DEPTH`. | Security (defense-in-depth) |
| **G4** | video-gen-service's `get_minio()` does `make_bucket` but **never sets a public-read policy** on `loreweave-media`. book-service `media.go` does. If video-gen-service wins the bucket-create race, the bucket is private → every generated video's static URL 403s in the browser. | **Real bug** |

Out of scope (intentional, stays deferred): replacing usage-billing
`input_tokens=prompt_len` semantics; CORS config (service is internal-only).

---

## 3. Design

### 3.1 G4 + G2 — MinIO public-read policy + lifespan bootstrap

**Move bucket bootstrap off the request hot path into a FastAPI `lifespan`
startup handler, set the public-read policy there, and keep a per-request
self-heal so a startup-time MinIO blip cannot permanently break the service.**

> **/review-impl(DESIGN) HIGH#1 — folded.** An earlier draft made
> `bootstrap_minio()` a one-shot best-effort with no retry and `get_minio()`
> doing no bucket ops. If MinIO is not ready at app boot (common in
> docker-compose), the startup attempt fails, is never retried, and the bucket
> stays missing/private — i.e. the cycle's mechanism reproduces the exact G4
> failure it exists to fix. The corrected design below mirrors book-service's
> `ensureMediaBucket` `mediaBucketReady`-flag pattern: cheap per-request
> short-circuit + self-heal.

`app/routers/generate.py`:

- New module constant `_PUBLIC_READ_POLICY` — the standard anonymous-GET
  bucket policy for `{MINIO_BUCKET}/*`, mirroring book-service
  `setBucketPublicRead` (`media.go`) and provider-registry `audio_cache.go`.
  The bucket name is **interpolated from `MINIO_BUCKET`** (f-string / `.format`),
  not hardcoded, so a future bucket rename can't drift the `Resource` ARN
  (/review-impl(DESIGN) LOW#5).
- New module-level flag `_bucket_ready: bool = False`.
- New function `_ensure_bucket() -> None` — the actual idempotent work:
  - `if not bucket_exists(MINIO_BUCKET):` → `make_bucket(MINIO_BUCKET)`.
    On `S3Error` from `make_bucket`, **re-check** `bucket_exists`; if it now
    exists, a concurrent creator (book-service) won the race — proceed; else
    re-raise. A blanket `except S3Error: pass` is **not** used — it would mask
    access-denied / invalid-name / outage errors and then run
    `set_bucket_policy` against a nonexistent bucket (/review-impl(DESIGN) MED#2).
  - `set_bucket_policy(MINIO_BUCKET, _PUBLIC_READ_POLICY)` — **always**, so
    whoever creates the bucket, the policy ends up public. Idempotent;
    book-service sets the identical policy.
  - On full success, set `_bucket_ready = True`.
- New function `bootstrap_minio() -> None` — the startup entry point:
  calls `_ensure_bucket()` inside `try/except Exception → logger.error(...)`.
  Best-effort at startup: a MinIO outage logs an error and does **not** crash
  the process.
- New function `ensure_bucket_ready() -> None` — the per-request self-heal:
  returns immediately if `_bucket_ready` is `True`; otherwise calls
  `_ensure_bucket()` (errors propagate to the caller's existing
  `except Exception → 500` handler). `generate_video` calls this once, right
  before `put_object`. Happy-path cost after the first success = one bool
  check.
- `get_minio()` simplified: creates + caches the `Minio` client only — **no
  bucket operations**. The lazy `bucket_exists`/`make_bucket` block is removed.

`app/main.py`:

- Add an `@asynccontextmanager` `lifespan(app)` that calls `bootstrap_minio()`
  on startup (nothing on shutdown). Wire it via `FastAPI(lifespan=lifespan)`.
- The existing `from .config import settings` fail-fast import is preserved.

Rationale for "always set policy": the bug (G4) is a *race*, not a missing
call. Setting the policy unconditionally closes the race regardless of which
service creates the bucket. `set_bucket_policy` is idempotent.

### 3.2 G1 — remove the dead `/models` endpoint

- `app/routers/generate.py`: delete the `list_models()` route and drop
  `ModelsResponse` from the `..models` import.
- `app/models.py`: delete the `ModelInfo` and `ModelsResponse` classes.
  `GenerateRequest` / `GenerateResponse` stay.
- `frontend/src/features/video-gen/api.ts`: delete the `listModels` method and
  the `VideoModel` type. `VideoModel` is referenced **only** inside this file
  (verified — `ReadingTab.tsx` uses the unrelated `UserModel` type). The
  `generate` method and `GenerateVideoResponse` type stay.
- `README.md`: drop the "models" mention from the routes description, and
  correct the opening line — it claims "image/video generation" but
  video-gen-service only does video (book-service owns chapter-block image
  generation). (/review-impl(DESIGN) COSMETIC#8.)

No test currently exercises `/models`; a grep-lock in `test_no_dead_resolution.py`
asserts the route is gone (see §4).

### 3.3 G3 — JWT signature verification

auth-service signs access tokens with **HS256 + a shared secret**
(`authjwt/jwt.go`: `SigningMethodHS256`; `JWT_SECRET` ≥ 32 chars). chat-service
already verifies them (`app/middleware/auth.py`:
`jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])`). video-gen-service
mirrors that — **no JWKS, no public-key fetch, no auth-service call.**

**Caller assumption (/review-impl(DESIGN) LOW#6):** the only caller of
`/v1/video-gen/generate` is the frontend via api-gateway-bff, which forwards
the **end-user's** auth-service-issued `Bearer` JWT (audit confirmed — FE
`videoGenApi.generate`, proxied transparently by `gateway-setup.ts`
`videoGenProxy`). There is **no** svc-to-svc caller sending only an
`X-Internal-Token`. Switching from unverified decode to HS256 verification is
therefore safe: it cannot break an internal caller because none exists. The
service's own *outbound* call to the gateway still uses `auth_mode="internal"`
+ `INTERNAL_SERVICE_TOKEN` — unchanged.

- `requirements.txt`: add `PyJWT>=2.8` (the pin chat-service uses).
- `app/config.py`: add `jwt_secret: str` (required, **no default** — matches
  chat-service `Settings.jwt_secret`; the service fails fast at startup if
  `JWT_SECRET` is unset). docker-compose **already** passes `JWT_SECRET` to
  video-gen-service (line 366) — no infra change needed.
- `app/routers/generate.py` — rewrite `extract_user_id(authorization: str)`:
  ```python
  token = authorization.removeprefix("Bearer ").strip()
  if not token:
      raise HTTPException(401, "Authorization required")
  try:
      payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
  except jwt.ExpiredSignatureError:
      raise HTTPException(401, "Token expired")
  except jwt.InvalidTokenError:          # bad signature, malformed, alg
      raise HTTPException(401, "Invalid token")
  sub = payload.get("sub", "")
  if not sub:
      raise HTTPException(401, "Invalid token")
  return sub
  ```
  - `algorithms=["HS256"]` is an allow-list — blocks the `alg:none` downgrade
    attack (the old code accepted exactly that).
  - PyJWT guarantees `payload` is a dict on success (it rejects non-object
    claims as `DecodeError ⊂ InvalidTokenError`), so the old "non-dict payload"
    edge case collapses into the `InvalidTokenError` branch.
  - The function keeps its name and `(authorization: str) -> str` signature —
    the route call site (`extract_user_id(authorization)`) is unchanged.
- The `D-PHASE5E-JWT-VERIFY-DEFENSE-IN-DEPTH` note in the docstring is removed;
  the deferral is cleared in SESSION_PATCH.

### 3.4 No change to `/generate` business logic

The download→MinIO→billing flow in `generate_video` is correct and stays.
Only `extract_user_id` (its first call) and `get_minio` (its MinIO accessor)
change, both transparently.

---

## 4. Test plan

`tests/conftest.py`:
- `os.environ.setdefault("JWT_SECRET", "<32+ char test secret>")` before app
  import.
- `jwt_for_user` rewritten: instead of an `alg:none` unsigned token, sign a
  real HS256 token with PyJWT and the test `JWT_SECRET`. Accept an optional
  `exp` override so an expired-token test can be driven.
- **The `client` fixture must neutralize the lifespan's MinIO call**
  (/review-impl(DESIGN) MED#3). `with TestClient(app)` runs the FastAPI
  lifespan, so `bootstrap_minio()` would fire on every test and attempt a real
  connection to the bogus `minio.test:9000` host — slow/flaky. The fixture
  wraps `TestClient` construction in `patch("app.main.bootstrap_minio")` (a
  no-op) so startup is inert. Tests that exercise the bucket logic call
  `_ensure_bucket` / `bootstrap_minio` directly with a `MagicMock` Minio
  (see below) rather than relying on the lifespan.

`tests/test_generate.py`:
- Existing happy-path + 5 error-mapping + non-default-aspect-ratio tests keep
  passing once `jwt_for_user` produces valid signed tokens.
- `test_extract_user_id_non_dict_payload_returns_401` → **repurpose** to
  `test_bad_signature_returns_401` (token signed with a *different* secret →
  401 "Invalid token").
- NEW `test_expired_token_returns_401` (token with `exp` in the past → 401
  "Token expired").
- NEW `test_missing_authorization_returns_401`.
- NEW `test_alg_none_token_rejected` — a hand-crafted `alg:none` token (the
  exact attack the old code allowed) → 401. Regression-lock on the allow-list.

`tests/test_bucket_bootstrap.py` (NEW — G4 behavioral coverage,
/review-impl(DESIGN) MED#4):
- The bucket logic is pure orchestration — fully testable with a `MagicMock`
  Minio, **no real MinIO instance** (unlike the gateway audio-cache's deferred
  `D-PHASE5E-BETA2-STORAGE-UNIT-TESTS`).
- `test_ensure_bucket_sets_public_read_policy` — `bucket_exists` → `False`;
  assert `make_bucket` called once AND `set_bucket_policy` called with a policy
  string containing `s3:GetObject` and the `MINIO_BUCKET` ARN; assert
  `_bucket_ready` flipped `True`.
- `test_ensure_bucket_existing_bucket_still_sets_policy` — `bucket_exists` →
  `True`; assert `make_bucket` **not** called but `set_bucket_policy` still
  called (closes the G4 race-where-book-service-created-it-private path).
- `test_ensure_bucket_tolerates_make_bucket_race` — `bucket_exists` → `False`
  then (after a `make_bucket` `S3Error`) → `True`; assert no exception,
  `set_bucket_policy` still called, `_bucket_ready` `True`.
- `test_ensure_bucket_propagates_genuine_make_bucket_failure` — `make_bucket`
  raises `S3Error` and the re-check `bucket_exists` stays `False`; assert the
  error propagates and `_bucket_ready` stays `False` (regression-lock on
  MED#2 — proves the failure is not blanket-swallowed).
- `test_bootstrap_minio_swallows_errors` — `_ensure_bucket` raises; assert
  `bootstrap_minio()` does not raise (best-effort startup contract).
- Each test resets the module-level `_bucket_ready` flag in a fixture/teardown
  so cases don't leak state.

`tests/test_no_dead_resolution.py`:
- NEW `test_models_endpoint_removed` — assert `"/models"` and `def list_models`
  absent from `generate.py` source (grep-lock for G1).
- NEW `test_jwt_decode_verifies_signature` — assert `generate.py` source
  contains `jwt.decode(` and (separately) `HS256` and does **not** contain
  `urlsafe_b64decode` (positive + negative lock for G3 — proves the unverified
  base64 path is gone). The two positive substrings are checked
  **independently** (not as one `algorithms=["HS256"]` literal) so quote-style
  or whitespace changes don't false-fail the lock (/review-impl(DESIGN) LOW#7).
- The "no signature verification" wording in `extract_user_id`'s docstring is
  removed.

FE: no FE test harness change — `listModels` had no callers and no test.

### 4.1 Verify commands

```
cd services/video-gen-service && python -m pytest -q      # expect all green
cd frontend && npx tsc --noEmit                            # FE type-check after VideoModel delete
grep -rn "list_models\|ModelsResponse" services/video-gen-service/app   # expect 0
grep -n "urlsafe_b64decode" services/video-gen-service/app/routers/generate.py  # expect 0
```

---

## 5. Files (13 — 2 NEW + 11 MOD)

> QC found a 13th file: `infra/test-video-gen.sh` — its T08/T09 smoke
> checks curl the removed `/models` endpoint (and a stale pre-existing
> T00c checks a `/health` field the service never returns). Both were
> removed.


| File | Change |
|------|--------|
| `docs/03_planning/LLM_PIPELINE_PHASE5F_DESIGN.md` | NEW (this doc) |
| `services/video-gen-service/app/main.py` | + `lifespan` calling `bootstrap_minio()` |
| `services/video-gen-service/app/routers/generate.py` | `bootstrap_minio()` + `_ensure_bucket()` + `ensure_bucket_ready()` + `_PUBLIC_READ_POLICY` + `_bucket_ready` flag; `get_minio()` drops bucket ops; `extract_user_id` verifies JWT; delete `list_models` route |
| `services/video-gen-service/app/models.py` | delete `ModelInfo` + `ModelsResponse` |
| `services/video-gen-service/app/config.py` | + `jwt_secret: str` |
| `services/video-gen-service/requirements.txt` | + `PyJWT>=2.8` |
| `services/video-gen-service/tests/conftest.py` | sign real HS256 JWTs; set `JWT_SECRET`; patch `bootstrap_minio` in the `client` fixture |
| `services/video-gen-service/tests/test_generate.py` | repurpose non-dict test; + 3 JWT tests |
| `services/video-gen-service/tests/test_bucket_bootstrap.py` | NEW — 5 G4 behavioral tests (MagicMock Minio) |
| `services/video-gen-service/tests/test_no_dead_resolution.py` | + `/models` + JWT-verify grep-locks |
| `services/video-gen-service/README.md` | drop "models" route mention; fix "image/video" → "video" |
| `frontend/src/features/video-gen/api.ts` | delete `listModels` + `VideoModel` |
| `infra/test-video-gen.sh` | remove T08/T09 (`/models`) + stale T00c (`provider_connected`) — QC-found |

No `infra/docker-compose.yml` change — `JWT_SECRET` is already wired.

---

## 6. Deferrals cleared / opened

**Cleared:** `D-PHASE5E-MINIO-ASYNC-OFFLOAD` (G2), `D-PHASE5E-JWT-VERIFY-DEFENSE-IN-DEPTH` (G3).

**Opened:** none expected. Billing-semantics and CORS remain untracked-by-design
(conscious won't-fix for an internal-only service).

---

## 7. Build order (PLAN)

Bite-sized, each 2–5 min. `generate.py` is touched by G1+G2+G3 — do it as one
coherent pass (steps 3–5), not three racing edits.

1. `config.py` — add `jwt_secret: str` (required, no default).
2. `requirements.txt` — add `PyJWT>=2.8`.
3. `generate.py` G3 — rewrite `extract_user_id` to HS256-verify; `import jwt`;
   drop the in-function `base64`/`json` imports + the no-verify docstring.
4. `generate.py` G2+G4 — `_PUBLIC_READ_POLICY` + `_bucket_ready` +
   `_ensure_bucket()` + `bootstrap_minio()` + `ensure_bucket_ready()`;
   simplify `get_minio()`; call `ensure_bucket_ready()` in `generate_video`
   before `put_object`.
5. `generate.py` G1 — delete `list_models` route; drop `ModelsResponse` import.
6. `models.py` — delete `ModelInfo` + `ModelsResponse`.
7. `main.py` — add `lifespan` calling `bootstrap_minio()`.
8. `frontend/src/features/video-gen/api.ts` — delete `listModels` + `VideoModel`.
9. `README.md` — fix routes line + "image/video" → "video".
10. `tests/conftest.py` — sign HS256 JWTs; set `JWT_SECRET`; patch
    `bootstrap_minio` in the `client` fixture.
11. `tests/test_generate.py` — repurpose non-dict test → bad-signature; add
    expired / missing-auth / alg-none tests.
12. `tests/test_bucket_bootstrap.py` — NEW, 5 G4 tests.
13. `tests/test_no_dead_resolution.py` — add `/models`-removed + JWT-verify
    grep-locks.
14. VERIFY — run §4.1 commands.
