# Adversarial Code Review — lore-enrichment-c0 (round 2)

Reviewer: AMAW Phase-7 code adversary (cold-start). Verdict: **REJECTED** (1 BLOCK, 2 WARN). Found exactly 3 problems. Reviewed the built diff + new files; verified r1 design fixes landed in code.

---

## Finding 1 — BLOCK — Gateway now hard-couples startup on the C0 skeleton: `api-gateway-bff depends_on lore-enrichment-service condition: service_healthy` wedges the entire stack if the new service is unhealthy

Evidence:
- infra/docker-compose.yml (diff @@ -742,+772) — the api-gateway-bff `depends_on` block gained `lore-enrichment-service: condition: service_healthy`.
- infra/docker-compose.yml (new block, diff @@ +557) — lore-enrichment-service uses `restart: unless-stopped` and a `/health` healthcheck.
- services/lore-enrichment-service/app/main.py:18 — lifespan calls `await create_pool(settings.database_url)` BEFORE serving; asyncpg `create_pool` connects immediately (app/db/pool.py:8, `min_size=2`).

Why it bites: C0 is an explicit skeleton (C0_BOOTSTRAP_PLAN.md:8), yet the diff makes the gateway — the documented sole external entry point ("Gateway invariant") — refuse to start until this business-logic-free service reports healthy. If `loreweave_lore_enrichment` is missing or the DB is briefly unreachable, `create_pool` raises, the container exits, and with `restart: unless-stopped` it crash-loops and NEVER reaches healthy, so `depends_on: service_healthy` blocks the gateway indefinitely (`docker compose up` hangs). A C0 bootstrap that only returns a static `ok` has become a single point of failure for auth, books, chat, glossary. The green tests don't cover this: `jest proxy-routing` mocks upstreams and never exercises compose `depends_on`; the live `/health` smoke brings up only the one service, not the gateway-blocked-on-it path. This contradicts the plan's own risk note (C0_BOOTSTRAP_PLAN.md:55 "No `restart: unless-stopped` at C0 to avoid crash-loop masking") — the shipped compose adds BOTH `restart: unless-stopped` AND the gateway hard-dep.

Concrete fix: Drop the gateway->lore-enrichment hard dependency or downgrade to `condition: service_started` for the skeleton; reconsider `restart: unless-stopped` on a fail-fast-pool service with no schema yet. Do not gate the gateway on it until it carries real depended-upon routes.

---

## Finding 2 — WARN — `/health` returns `200 ok` unconditionally and is the Docker healthcheck — a dead DB pool reports "healthy", masking the exact failure C0 is meant to prove

Evidence:
- services/lore-enrichment-service/app/main.py:36-38 — `/health` returns constant `"ok"`; never touches the pool / `SELECT 1`.
- services/lore-enrichment-service/Dockerfile:16-17 and infra/docker-compose.yml healthcheck both probe this `/health`.
- app/db/pool.py:19-22 — `get_pool()` would raise if uninit, but `/health` doesn't call it.

Why it bites: r1 WARN#3 "false-green" re-emerging one layer down. The live smoke and the `service_healthy` condition Finding 1 relies on treat `/health` as proof the service is functional, but the only way `/health` returns non-200 is a dead process — so the smoke tests "is uvicorn up", not C0's acceptance ("DB pool connected to loreweave_lore_enrichment"). A future change making `create_pool` lazy, or moving `/health` before lifespan, yields green 200 `ok` with a broken pool. The r1 fix hardened the curl command; the endpoint it asserts is content-free.

Concrete fix: Make `/health` a real readiness probe (`await get_pool().fetchval("SELECT 1")`, 503 on failure) so the healthcheck/smoke exercise the DB connection that is C0's point — or document it liveness-only and add a DB-touching `/ready` for the compose healthcheck.

---

## Finding 3 — WARN — `conftest.py` `os.environ.setdefault` + the test re-constructing a fresh `Settings` mean the unit suite never executes the module-level `settings = Settings()` that production fail-fast actually depends on

Evidence:
- services/lore-enrichment-service/tests/conftest.py:6-8 — sets the three required vars via `os.environ.setdefault` before any `import app.*`.
- services/lore-enrichment-service/app/config.py:29 — fail-fast is the module-level `settings = Settings()`.
- services/lore-enrichment-service/tests/test_health.py:31-44 — fail-fast test instantiates a FRESH `Settings(_env_file=None)`, NOT the module-level object.

Why it bites: r1 WARN#2 (isolate the negative test env) landed correctly — delenv + chdir + `_env_file=None`. But the actual contract (C0_BOOTSTRAP_PLAN.md:29,52 "module-level `settings = Settings()` => container crashes on missing secret") is never exercised: conftest pre-populates env so `import app.config` always succeeds, and the test re-constructs a new `Settings`. The suite green-lights even if someone later gives `database_url` a default or moves instantiation behind a function. 2/2 pytest green does not cover the production import-time fail-fast path that makes Finding 1/2 scenarios possible.

Concrete fix: Add a subprocess test with the three vars cleared + empty CWD running `python -c "import app.config"` asserting non-zero exit. That exercises the real `settings = Settings()` line. Optionally narrow conftest setdefault to only what `test_health` needs.

---

Captured rules: read pre-loaded (adversary-rejection "mirror must PIN X's contract" — config.py correctly upgrades chat-service pydantic-v1 `class Config` to v2 `SettingsConfigDict`, mirror sound there; "smoke probes accepting any non-zero exit = false-green" — drives Findings 2+3; check_guardrails compose-edit pass:true/6 rules/none matched). r1 fixes landed: BLOCK#1 = yes (db-ensure.sh:26 + 01-databases.sql:56-58, durable); WARN#2 = yes (test_health.py:31-44 env-isolated); WARN#3 = yes (plan verify step 4 pins curl status+body assert). Guardrails relevant: none triggered (empty db; the BLOCK is a startup-coupling regression, not destructive/migration).
