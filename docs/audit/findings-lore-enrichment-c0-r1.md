# Adversarial Design Review — lore-enrichment-c0 (round 1)

Reviewer: AMAW Phase-3 adversary (cold-start). Verdict: REJECTED (1 BLOCK, 2 WARN). Found exactly 3 problems.

---

## Finding 1 — BLOCK — DB-existence race: `depends_on: postgres healthy` does NOT guarantee `loreweave_lore_enrichment` exists when the service starts

Evidence:
- C0_BOOTSTRAP_PLAN.md:45 — service block uses `depends_on: postgres healthy`; :51 claims "DB must exist before service starts" relying on "(init script + db-ensure + manual create)".
- infra/db-ensure.sh:12-26 — the `DATABASES` list is the ONLY runtime create mechanism (init script infra/postgres-init/01-databases.sql runs ONCE at volume creation; volume is 29h old → will NOT re-run; design acknowledges this at :44). The list currently has no `loreweave_lore_enrichment` line.
- infra/docker-compose.yml:23 — postgres healthcheck runs db-ensure.sh only per tick; infra/docker-compose.yml:7 postgres has been healthy for 29h on the OLD db-ensure that lacks the new DB.

Why it bites: app/db/pool.py mirror (chat pool.py:6-9) calls `asyncpg.create_pool(dsn)` which connects immediately at lifespan startup to `loreweave_lore_enrichment`. The Compose gate `depends_on: postgres: service_healthy` is ALREADY satisfied by the long-running postgres whose last healthcheck used the pre-edit db-ensure — so `docker compose up -d lore-enrichment-service` can launch the service in the window before the next 5s healthcheck re-reads the edited bind-mounted db-ensure.sh and creates the DB. asyncpg then raises InvalidCatalogNameError and the container exits. Design explicitly removed `restart` (:55), so the container stays dead — the /health smoke fails with connection-refused, NOT the intended 200 ok. The "manual create" is a verbal step in the verify plan (:60), not enforced ordering.

Concrete fix: Make ordering deterministic. Either (a) the verify plan must force a postgres healthcheck re-tick before the service starts — e.g. `docker compose exec postgres sh /usr/local/bin/db-ensure.sh` and confirm "Creating database: loreweave_lore_enrichment" in output, THEN `up -d` the service; OR (b) add a one-shot create pre-step before create_pool. Pin the single source of DB creation in the plan and add the line to db-ensure.sh:12-26 regardless. Do not rely on bind-mount tick timing.

---

## Finding 2 — WARN — Fail-fast unit test is a false-green: `env_file=".env"` defeats "clear env → expect ValidationError"

Evidence:
- C0_BOOTSTRAP_PLAN.md:29 — Settings declares `env_file=.env` (mirrors chat config.py:39-40 `class Config: env_file = ".env"`).
- C0_BOOTSTRAP_PLAN.md:38,52 — the fail-fast test "clears env and expects ValidationError."

Why it bites: pydantic-settings resolves env_file relative to process CWD, not the test file. When pytest runs from repo root or the service dir, any committed/local .env supplies database_url/jwt_secret/internal_service_token, so Settings() succeeds and the test asserting ValidationError silently does not exercise the fail-fast path — a green test proving nothing. Same "false-green probe" pattern as the captured lesson, applied to the unit gate.

Concrete fix: In the test, instantiate against a provably empty environment: `Settings(_env_file=None)` after `monkeypatch.delenv(...)` for each required key (and `monkeypatch.chdir(tmp_path)` so no stray .env is found), then assert pydantic.ValidationError. Pin this exact construction in the plan.

---

## Finding 3 — WARN — Live-smoke `curl /health` does not distinguish `200 ok` from a connecting-but-wrong response (false-green); cross-service token over-claims

Evidence:
- C0_BOOTSTRAP_PLAN.md:60 — verify step 3: "curl http://localhost:8221/health → 200 ok. Token: `live smoke: lore-enrichment /health 200 on stack-up`."

Why it bites: A bare `curl URL` exits 0 and prints the body for ANY HTTP response (404/500 from a half-initialized app, or a stray listener on host port 8221); it only fails (exit 7) on connection-refused. The plan asserts "200 ok" but specifies no mechanism that checks status==200 AND body=="ok". A service that boots, fails its DB pool, and returns a FastAPI 500 yields a printed body and exit 0 → recorded as pass. The cross-service token then claims a green call that never happened — the "smoke probe accepting any response = false-green" lesson.

Concrete fix: Pin an assertion checking both status and body, e.g. `curl -fsS -o /tmp/body -w '%{http_code}' http://localhost:8221/health` requiring http_code==200 AND body=="ok"; only then emit the token. State the exact command + expected pair in the verify plan.

---

Captured rules: read pre-loaded (adversary-rejection "pin the mirrored contract"; "smoke probes accepting any non-zero = false-green"; check_guardrails compose-edit pass:true / 6 rules / none matched). Guardrails relevant: none triggered (C0 creates an EMPTY db, no schema migration — the DB-ordering BLOCK is a correctness race, not a guardrail hit).
