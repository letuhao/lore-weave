# C0 Bootstrap — Design + Plan (lore-enrichment-service skeleton)

> **Task:** `lore-enrichment-c0` · **Size:** L (≈10 new files, ≈6 modified; side-effects: new service, infra, gateway). **Workflow:** default v2.2 + AMAW.
> **Cycle source:** [CYCLE_DECOMPOSITION.md](CYCLE_DECOMPOSITION.md) C0 row · locked: [OPEN_QUESTIONS_LOCKED.md](OPEN_QUESTIONS_LOCKED.md) · [PRE_FLIGHT_CHECKLIST.md](PRE_FLIGHT_CHECKLIST.md).
> **Why default+AMAW (not /raid):** raid.md — "/raid does NOT execute Cycle 0; C0 bootstrap uses default+AMAW". C0's `/health` smoke gates C0→C1.

## Goal
Minimal FastAPI skeleton `lore-enrichment-service` mirroring chat-service's *skeleton subset only* (config fail-fast, DB pool, deps, `/health`, Dockerfile, compose wiring, gateway route). NO business logic, NO migrations (C2), NO LLM/minio/redis clients (later cycles). Acceptance: `curl /health` → `200 ok` on stack-up.

## Scope IN (C0 deliverables — verbatim from decomposition)
- `config.py` — fail-fast on missing required secrets (`database_url`, `jwt_secret`, `internal_service_token`).
- `/health` endpoint (PlainText `ok`).
- DB pool (`create_pool`/`close_pool`/`get_pool`, asyncpg) created at lifespan startup.
- `deps.py` (`get_db`).
- Dockerfile (python:3.12-slim, healthcheck).
- `infra/docker-compose.yml` wiring (internal **8093** / host **8221**).
- Gateway route `/v1/lore-enrichment/*`.

## Scope OUT (explicit — later cycles)
- DB migrations / tables (`loreweave_lore_enrichment` tables) → **C2**.
- KG/glossary/book read clients → **C1**. API contract/handlers → **C3**.
- Tracing/observability (`loreweave_obs`, OTEL) → **C18** (kept out to stay minimal/low-risk).
- LLM SDK (`sdks/python`/`loreweave_llm`), minio, redis stream consumers → C8+.

## Files to CREATE (`services/lore-enrichment-service/`)
| File | Content |
|---|---|
| `app/__init__.py` | empty package marker |
| `app/config.py` | `Settings(BaseSettings)`: required `database_url` (alias `LORE_ENRICHMENT_DB_URL`), `jwt_secret`, `internal_service_token`; defaulted read-dep URLs (knowledge/glossary/book/provider-registry), `redis_url`, `port=8093`. `env_file=.env`. Module-level `settings = Settings()` ⇒ **fail-fast** (pydantic raises if required env missing). |
| `app/db/__init__.py` | empty |
| `app/db/pool.py` | mirror chat: `create_pool(dsn)` (min 2/max 10), `close_pool`, `get_pool` (raises if uninit) |
| `app/deps.py` | `get_db() -> asyncpg.Pool` returning `get_pool()` |
| `app/main.py` | `FastAPI(title="lore-enrichment-service", lifespan=...)`; lifespan: `create_pool(settings.database_url)` on enter, `close_pool()` on exit (NO migrations); CORS middleware; `GET /health` → PlainText `ok` |
| `requirements.txt` | fastapi, uvicorn[standard], asyncpg, pydantic, pydantic-settings, httpx, PyJWT, python-dotenv (minimal — no boto3/redis/litellm) |
| `Dockerfile` | python:3.12-slim; context = **repo root** (compose), `dockerfile: services/lore-enrichment-service/Dockerfile`; COPY requirements → pip install → COPY app; `ENV PORT=8093`, `EXPOSE 8093`; HEALTHCHECK urlopen `/health`; CMD uvicorn |
| `pytest.ini` | minimal pytest config (asyncio mode) |
| `tests/__init__.py` | empty |
| `tests/test_health.py` | TDD: ASGI httpx/TestClient → `GET /health` == 200 `ok`; fail-fast test **must** isolate env: `monkeypatch.delenv(...)` for each required var + `monkeypatch.chdir(tmp_path)` + `Settings(_env_file=None)` then assert `ValidationError` (adversary r1 WARN#2 — `.env` from CWD = false-green otherwise) |

## Files to MODIFY
| File | Change |
|---|---|
| `infra/postgres-init/01-databases.sql` | add `loreweave_lore_enrichment` (idempotent `\gexec`) |
| `infra/db-ensure.sh` | add `loreweave_lore_enrichment` to `DATABASES` (runtime idempotent create — needed because postgres volume already initialized) |
| `infra/docker-compose.yml` | add `lore-enrichment-service` block (build repo-root context, env incl. `LORE_ENRICHMENT_DB_URL`, `JWT_SECRET`, `INTERNAL_SERVICE_TOKEN`, read-dep URLs; `depends_on: postgres healthy`; `ports: "8221:8093"`; healthcheck). Add `LORE_ENRICHMENT_SERVICE_URL: http://lore-enrichment-service:8093` to `api-gateway-bff` env |
| `services/api-gateway-bff/src/gateway-setup.ts` | add `loreEnrichmentUrl` to urls type + `loreEnrichmentProxy` (pathFilter `/v1/lore-enrichment`) + dispatch branch |
| `services/api-gateway-bff/src/main.ts` | `const loreEnrichmentUrl = requireEnv('LORE_ENRICHMENT_SERVICE_URL');` + pass to `configureGatewayApp` |
| `services/api-gateway-bff/test/proxy-routing.spec.ts` | add `lore-enrichment` upstream server + `loreEnrichmentUrl` wiring + route assertion |

## Design decisions / risks
- **DB must exist for pool**: asyncpg `create_pool` connects immediately → `loreweave_lore_enrichment` must exist before service starts. Created empty at C0 (init script + db-ensure + manual create against the already-running postgres for the live smoke). Tables come in C2.
- **Fail-fast**: module-level `settings = Settings()` makes the container crash on missing required secret (CLAUDE.md "services fail to start if missing"). Verified by a unit test that clears env and expects `ValidationError`.
- **Port**: internal 8093 (free), host 8221 (8217-19 reserved, 8220 tilemap) — per pre-flight.
- **Env name**: locked `LORE_ENRICHMENT_DB_URL` honored via pydantic `validation_alias`.
- **`restart: unless-stopped`** kept (platform convention, mirrors knowledge-service). Safe at C0 because the gateway's `depends_on` on this service is `service_started` (not `service_healthy`, per adversary r2 BLOCK#1), so a crash-looping skeleton cannot wedge the stack. (Verified RestartCount=0 in the live smoke — no masking occurred.)

## Verify plan (evidence gate) — adversary r1 fixes baked in
1. `pytest services/lore-enrichment-service` green (health + **env-isolated** fail-fast per the test row above).
2. (gateway) `tsc --noEmit` + `npm test` proxy-routing spec green (new route in BOTH proxy list AND dispatch chain).
3. **DB-exists FIRST (adversary r1 BLOCK#1):** add `loreweave_lore_enrichment` to `db-ensure.sh`, then create it in the ALREADY-RUNNING postgres BEFORE bringing the service up — `docker compose exec -T postgres psql -U loreweave -d postgres -c "CREATE DATABASE loreweave_lore_enrichment"` (or `bash /db-ensure.sh` if mounted) and confirm via `psql -tAc "SELECT 1 FROM pg_database WHERE datname='loreweave_lore_enrichment'"` == 1. Do NOT rely on `depends_on`/init-SQL/volume-tick.
4. **Live smoke (cross-service token), hardened (adversary r1 WARN#3):** `docker compose build lore-enrichment-service && docker compose up -d lore-enrichment-service`; wait for healthy; then `code=$(curl -fsS -o /tmp/h -w '%{http_code}' http://localhost:8221/health); test "$code" = 200 && grep -qx ok /tmp/h`. Emit token ONLY if both pass: `live smoke: lore-enrichment /health 200 ok on stack-up`. (`-f` makes curl exit non-zero on >=400; explicit status+body assert kills false-green.)
5. secret-scan + prod-isolation lint clean.

## Adversary r1 disposition (pragmatic stop on design review)
REJECTED (1 BLOCK + 2 WARN), all 3 incorporated above. Design-doc fixes are procedure/test-level (DB ordering, env-isolated fail-fast test, hardened curl) — no architectural change. Per AMAW L-calibration + stop-condition, NOT re-spawning a design round on a now-correct doc; the **Phase 7 code adversary verifies these landed in the real diff** (where they bite). Logged as pragmatic_stop in AUDIT_LOG. **r1 fixes confirmed landed by the r2 code adversary** (BLOCK#1=y, WARN#2=y, WARN#3=y).

## Adversary r2 disposition (code review)
REJECTED (1 BLOCK + 2 WARN).
- **BLOCK#1 — FIXED.** Gateway `depends_on: lore-enrichment-service` downgraded `service_healthy → service_started` (compose) so the C0 skeleton cannot wedge the whole stack on `compose up`. Re-verified: `docker compose config` valid; live smoke still 200 ok.
- **WARN#3 — FIXED.** Added `test_config_fail_fast_crashes_import` (subprocess `python -c "import app.config"` with secrets cleared → asserts non-zero exit + "validation error"). This exercises the real module-level `settings = Settings()` crash, not just an in-process `Settings()`.
- **WARN#2 — DEFERRED (tracked, not drift).** `/health` is a constant-`ok` **liveness** probe, matching the platform convention (chat-service/knowledge-service `/health` are also constant). The live smoke is still honest about *DB-connected-at-startup*: `main.py` lifespan `await create_pool()` runs BEFORE `yield`, so uvicorn only serves `/health` if the pool connected — a 200 ⟹ DB reachable at boot. A DB-touching **readiness** probe (`/ready` `SELECT 1`, 503 on failure) catches DB-down-AFTER-startup; that is later-cycle scope (observability C18 / when real routes land). Deferred row: **D-C0-READINESS-PROBE** → target C18.

## AMAW gates
- Phase 3 design adversary (this doc) — find 3 problems.
- Phase 7 code adversary (built diff) — find 3 problems; run `tsc --noEmit` (gateway) + `ruff`/`pytest` before.
- Phase 9 Scope Guard — CLEAR/BLOCKED on the riskiest action (infra/compose edit to a shared file).
