# Cycle 18: Productionize

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Make `lore-enrichment-service` operable in prod: **observability** (structured logging + tracing + Prometheus-style `/metrics`), a **runbook**, a **deploy pipeline**, and a **final secret-scan + prod-isolation lint** across the whole cycle's diff. Also lands **deferred 042 (D-C0-READINESS-PROBE)**: split a DB-touching **readiness** probe `/ready` (`SELECT 1`, 503 on failure) from the existing constant-`ok` liveness `/health`. No new enrichment/pipeline logic.
- **Acceptance gate:** `scripts/raid/verify-cycle-18.sh` exits 0 (metrics scrape returns counters; `/ready` 200 when DB up / 503 when down; secret-scan + prod-isolation lint clean).
- **Top 3 LOCKED decisions consumed:** Q-R1 (own service/DB), Isolation (never touch existing-prod), no-hardcoded-model-names.
- **DPS count:** 3
- **Estimated wall time:** 3–5 h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C14
- Files expected to exist (grep-able paths): `services/lore-enrichment-service/app/` (C0 skeleton — `config.py` fail-fast, `main.py` lifespan `create_pool`, `/health`), the C14 end-to-end job runner (`app/jobs/runner.py`, `app/jobs/events.py`) emitting `lore_enrichment.job.*` Redis Streams events. C18 instruments what C14 already runs; do not re-implement the pipeline.

## Scope (IN)
- **Structured logging:** JSON logs with `job_id`/`request_id`/`stage` correlation across the C14 runner; consistent levels; no secrets/PII in log lines. Match the chat-service/knowledge-service convention.
- **Tracing:** lightweight span/trace-id propagation through job stages (gap-detect → … → write-back) so a single enrichment job is followable end-to-end. Reuse existing platform tracing helper if present; do not add a heavy new framework.
- **Metrics:** a `/metrics` endpoint (Prometheus text format) exposing at minimum: jobs started/completed/failed, proposals created (by `source_type`), per-stage latency, cost-cap pauses, LLM/embed call counts. Counters increment from the live C14 runner, not hardcoded.
- **Readiness probe (deferred 042):** add `/ready` running `SELECT 1` against the pool → 200 when DB reachable, **503** on failure; keep `/health` as the constant-`ok` liveness probe. Wire both into `infra/docker-compose.yml` healthcheck/readiness for THIS service only.
- **Runbook:** `docs/03_planning/lore-enrichment/RUNBOOK.md` — start/stop, env vars, `/health` vs `/ready`, reading metrics, draining/resuming a paused (cost-capped) job, rollback.
- **Deploy pipeline:** CI/build steps for the service (image build, lint, test, secret-scan gate) consistent with platform Docker conventions; no Vercel/Cloudflare lock-in.
- **Final gates:** run `scripts/raid/secret-scan-final.sh` and `scripts/raid/prod-isolation-lint.sh` over the cycle diff; wire both into `scripts/raid/verify-cycle-18.sh`.

## Scope (OUT — explicitly)
- **No new enrichment/pipeline logic** — gap model, strategies (P1/P2/P3), generation, verify, review, orchestration are owned by C6–C17. C18 only instruments and operationalizes.
- **No eval framework changes** — C15 owns the eval suite/gate. C18 may surface eval-cost as a metric but does NOT run or score eval.
- **No edits to** `world-service` / `game-server` / `tilemap` / `infra/existing-prod/`; **no edits to** `tests/quality/` climate/geo eval files (Isolation lock).
- **No new external secrets backend** — keep the C0 env-var fail-fast model; do not introduce a vault/SDK.
- **No direct Neo4j canonical writes** and **no schema migrations to other services'** DBs — observability is read-only on the enrichment service's own state.
- **No hardcoded model names** — any metric/log referencing the model resolves Qwen 3.6 + bge-m3 via provider-registry, never literals.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `services/lore-enrichment-service/tests/test_readiness.py` (`/ready` 200 DB-up, **503** DB-down via injected failing pool; `/health` stays constant-`ok`), `tests/test_metrics.py` (`/metrics` scrape returns Prometheus text + expected counter names; counters move after a simulated job). Run via the service's pytest.
- Lints pass: ruff/mypy for the service.
- **Metrics scrape (primary acceptance):** `curl /metrics` returns parseable Prometheus output with the named counters present.
- **Secret-scan clean:** `scripts/raid/secret-scan-final.sh` exit 0 (no hardcoded secrets / model names / raw provider URLs).
- **Prod-isolation clean:** `scripts/raid/prod-isolation-lint.sh` exit 0 (diff touches no `world-service`/`game-server`/`tilemap`/`infra/existing-prod/`/climate-geo eval files).
- `scripts/raid/verify-cycle-18.sh` exits 0 (runs the suite + asserts `/ready` failure path returns 503 + `/metrics` scrape + both final gates).
- Live-smoke token: **NOT required** — C18 is single-service (instruments the existing enrichment service only; not in the cross-service list 1/4/5/10/13/14).

## DPS parallelism plan
- **DPS 1 — Observability core** (`app/observability/`, logging + tracing config, `/metrics` endpoint, counter instrumentation hooked into the C14 runner): JSON logs with job/request correlation; Prometheus text endpoint; counters increment from live job stages. (return budget: 1500 tokens)
- **DPS 2 — Readiness probe + deploy wiring** (`/ready` `SELECT 1` route, `app/main.py`/router, `infra/docker-compose.yml` healthcheck for THIS service, CI/deploy steps): split readiness from liveness; 503 on pool failure. (return budget: 1500 tokens)
- **DPS 3 — Runbook + verify script + gates + tests** (`docs/03_planning/lore-enrichment/RUNBOOK.md`, `scripts/raid/verify-cycle-18.sh`, `tests/test_readiness.py`, `tests/test_metrics.py`; wire `secret-scan-final.sh` + `prod-isolation-lint.sh`). (return budget: 1500 tokens)

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Readiness vs liveness correctness (042):** confirm `/ready` actually executes `SELECT 1` against the real pool and returns **503** (not 200, not 500) when the DB is down — inject a failing pool in the test, not just mock the route. `/health` must stay constant-`ok` liveness; do not collapse the two.
- **Observability leaking secrets/PII:** scan structured logs and metric labels for hardcoded provider keys, raw URLs, or model names (`qwen`, `bge-m3`) — these must resolve via provider-registry / env, never appear as literals in log lines or label values. High-cardinality labels (per-job-id) on counters are a smell.
- **Metric honesty:** counters must increment from the LIVE C14 runner, not be hardcoded/stubbed — a `/metrics` endpoint returning fixed numbers is a false-green. Verify a simulated job moves the counters.
- **Prod-isolation escape:** confirm the diff (incl. compose/CI changes) touches nothing under `world-service`/`game-server`/`tilemap`/`infra/existing-prod/` and no climate/geo eval files; deploy wiring must stay scoped to the enrichment service.
- **Scope creep:** any NEW enrichment/eval logic added under cover of "observability" is a violation — C18 instruments C6–C17, it does not extend them.
- **Down-path / idempotency:** healthcheck wiring must not crash the service when DB is briefly down (readiness 503, not process exit); metrics endpoint must not depend on DB being up.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All Scope (IN) present: structured logging, tracing, `/metrics`, `/ready` readiness probe (042), runbook, deploy pipeline, final secret-scan + prod-isolation lint, verify-cycle-18.sh.
- No Scope (OUT) touched: no new pipeline/eval logic, no other-service migrations, no new secrets backend, no world-service/game-server/tilemap/infra/existing-prod or climate/geo eval edits.
- Acceptance met: metrics scrape parseable, `/ready` 503-on-DB-down proven, secret-scan + prod-isolation lint exit 0.
- Invariant intact: no hardcoded model names; observability read-only on the service's own state.

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle decomposition (C18 row + parallelism note "C18 alongside C15+"): [CYCLE_DECOMPOSITION.md](../../plans/2026-05-30-lore-enrichment/CYCLE_DECOMPOSITION.md)
- LOCKED decisions (full): [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-05-30-lore-enrichment/OPEN_QUESTIONS_LOCKED.md) — Q-R1, Isolation, no-hardcoded-model-names, H0 origin markers
- Deferred 042 origin (D-C0-READINESS-PROBE → C18): [C0_BOOTSTRAP_PLAN.md](../../plans/2026-05-30-lore-enrichment/C0_BOOTSTRAP_PLAN.md) WARN#2; [DEFERRED.md](../../deferred/DEFERRED.md) row 042
- Plan + ground truth: [PLAN.md](../../03_planning/lore-enrichment/PLAN.md), [CLARIFY_GROUND_TRUTH.md](../../03_planning/lore-enrichment/CLARIFY_GROUND_TRUTH.md)
- LOCKED decisions consumed (full list): Q-R1, Isolation, no-hardcoded-model-names

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Deferred 042 = primary deliverable:** add `/ready` running `SELECT 1` → **503** on DB failure, split from the constant-`ok` `/health` liveness probe. Prove the 503 path with an injected failing pool, not a mock. Liveness must stay constant.
- 🔴 **Acceptance gate:** `scripts/raid/verify-cycle-18.sh` exits 0 — metrics scrape parseable + counters move on a simulated job + `secret-scan-final.sh` clean + `prod-isolation-lint.sh` clean. No live-smoke token required (single-service cycle).
- 🔴 **No hardcoded model names / secrets:** logs and metric labels must NEVER contain literal `qwen`/`bge-m3`/provider keys/raw URLs — resolve via provider-registry / env. Secret-scan-final is a hard gate.
- 🔴 **Do NOT touch:** no NEW enrichment/eval logic (instrument C6–C17 only); no world-service/game-server/tilemap/infra/existing-prod; no `tests/quality/` climate/geo eval files; no other-service DB migrations; no new secrets backend.
- 🔴 **Fresh session reminder:** this is a new `/raid 18` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + OPEN_QUESTIONS_LOCKED.md ONLY.
