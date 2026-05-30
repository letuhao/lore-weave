# lore-enrichment-service — Operations Runbook

> RAID C18 (Productionize). Operate the multilingual lore-enrichment service in
> dev (Docker Compose) and prod (AWS ECS/EC2 + RDS + ElastiCache). The service
> proposes culturally-grounded lore for under-described canon entities; **every
> proposal is born quarantined (H0)** and only a human author-promote canonizes
> it. This runbook covers start/stop, env vars, probes, observability, the job
> flow, the eval gate, licensing, and rollback.

---

## 1. What the service does (one paragraph)

Given a project's canon (entities in glossary SSOT + the derived KG), the service
detects **gaps** (missing dimensions on an entity — 历史/地理/文化 + features/
inhabitants), runs an enrichment **job** that grounds + generates makeup lore
(retrieval P1, fabrication P2, re-cook P3), and persists each result as a
**quarantined proposal** (`origin='enrichment'`, `confidence < 1.0`,
`review_status='proposed'`, `pending_validation=true`). A separate **author
promote** is the ONLY path to canon (`source_type='glossary'`, `confidence=1.0`),
and it permanently retains the origin marker. The service NEVER writes canon
autonomously (H0 invariant).

---

## 2. Start / stop

### Dev (Docker Compose)

```bash
# from repo root
docker compose -f infra/docker-compose.yml up -d lore-enrichment-service
docker compose -f infra/docker-compose.yml logs -f lore-enrichment-service
docker compose -f infra/docker-compose.yml restart lore-enrichment-service
docker compose -f infra/docker-compose.yml stop lore-enrichment-service
```

Host port mapping: **`localhost:8221` → container `:8093`**.

Rebuild after a code change (the image installs `sdks/python` for `loreweave_obs`):

```bash
docker compose -f infra/docker-compose.yml build lore-enrichment-service
docker compose -f infra/docker-compose.yml up -d lore-enrichment-service
```

### Prod

Standard container: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. The
lifespan opens the DB pool and runs **idempotent migrations on every startup**
(C2 owns the schema; bare-SQL `run_migrations`, not alembic). A missing required
secret crashes import (fail-fast) — the container will not start.

---

## 3. Environment variables

| Var | Required | Default | Purpose |
|---|---|---|---|
| `LORE_ENRICHMENT_DB_URL` | **yes** | — | Postgres DSN for `loreweave_lore_enrichment` (own DB). Fail-fast if missing. |
| `JWT_SECRET` | **yes** | — | JWT validation. Fail-fast if missing. |
| `INTERNAL_SERVICE_TOKEN` | **yes** | — | Server-to-server token (gates `/internal/*`). Fail-fast if missing. |
| `KNOWLEDGE_SERVICE_URL` | no | `http://knowledge-service:8092` | C1 read port + `/internal/embed`. |
| `GLOSSARY_SERVICE_URL` | no | `http://glossary-service:8088` | Canon SSOT (anchor + write-back on promote). |
| `BOOK_SERVICE_URL` | no | `http://book-service:8082` | Owner verification on promote. |
| `PROVIDER_REGISTRY_INTERNAL_URL` | no | `http://provider-registry-service:8085` | Resolves embed + LLM `model_ref` (BYOK). **No model names in code.** |
| `REDIS_URL` | no | `redis://redis:6379` | Job lifecycle events (best-effort; a down Redis never fails a job). |
| `LORE_ENRICHMENT_GATE_MAX_AGE_SECONDS` | no | `604800` (7d) | A PASSING eval run older than this is treated as STALE → P2/P3 gate LOCKED (fail-closed). `0` disables (not recommended). |
| `LOG_LEVEL` | no | `INFO` | Structured-logging level. `DEBUG` locally. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | no | `` (empty) | OTLP/HTTP collector. **Empty → tracing is a no-op.** Set to enable distributed tracing. |
| `PORT` | no | `8093` | Listen port. |

**No hardcoded secrets, no hardcoded model names** — models resolve via
provider-registry `model_ref` at runtime; logs/metrics carry the ref or call
outcome, never a literal like `qwen`/`bge-m3`.

---

## 4. Health vs readiness (DEFERRED-042 — cleared in C18)

Two distinct probes — do NOT collapse them:

| Probe | Path | DB? | Meaning | Use |
|---|---|---|---|---|
| **Liveness** | `GET /health` | NO | Constant `ok` (200). Process is alive. | Container/orchestrator liveness check; a DB blip must NOT trip this (no crash-loop). The compose healthcheck uses `/health`. |
| **Readiness** | `GET /ready` | YES | `SELECT 1` against the pool. **200** = DB reachable; **503** = pool unavailable / query failed. | Orchestrator traffic gate (ECS/ALB target group, k8s readinessProbe). A DB that drops AFTER startup → 503 → drains traffic without killing the pod. |

Quick check:

```bash
curl -s -w '\n%{http_code}\n' http://localhost:8221/health   # ok / 200
curl -s -w '\n%{http_code}\n' http://localhost:8221/ready    # {"status":"ready"} / 200
```

Prod wiring recommendation: liveness → `/health`, readiness → `/ready`. On a DB
outage, `/ready` returns 503 (drained) while `/health` stays 200 (not
restarted) — the service recovers automatically when the DB returns.

---

## 5. Observability

### Structured logging
JSON logs on stdout (`app/logging_config.py`), one object per line, with
`service`, `trace_id`, `job_id`, `stage`, `level`, `name`, `message`. A
`RedactFilter` scrubs secret shapes (`sk-…`, `Bearer …`, `api_key=…`). Grep a
job: filter on `job_id`. Grep a request: filter on `trace_id` (also echoed on the
`X-Trace-Id` response header and in the 500 body).

### Tracing (OpenTelemetry)
`loreweave_obs.setup_tracing("lore-enrichment-service", app=app)` instruments the
FastAPI app (SERVER spans) + httpx clients (CLIENT spans to provider-registry /
knowledge-service). **No-op until `OTEL_EXPORTER_OTLP_ENDPOINT` is set.** On a
500, the response body carries both `trace_id` (log grep) and `otel_trace_id`
(paste into Grafana Tempo).

### Metrics (`GET /metrics`, Prometheus text)
Internal-only (no JWT); the scraper hits the service directly. **Does NOT depend
on the DB** — a scrape succeeds during a DB outage. Counters move from the LIVE
C14 job runner (not hardcoded):

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `lore_enrichment_jobs_started_total` | counter | — | Jobs that entered running. |
| `lore_enrichment_jobs_completed_total` | counter | — | Jobs that completed. |
| `lore_enrichment_jobs_failed_total` | counter | — | Jobs that failed. |
| `lore_enrichment_jobs_paused_total` | counter | — | Jobs paused (cost cap). |
| `lore_enrichment_cost_cap_pauses_total` | counter | — | Cost-cap pause events. |
| `lore_enrichment_proposals_created_total` | counter | `source_type` | Quarantined proposals by origin marker (`enriched:retrieval`/`:fabrication`/`:recook`). |
| `lore_enrichment_stage_duration_seconds` | histogram | `technique` | Per-gap stage wall-time. |
| `lore_enrichment_llm_calls_total` | counter | `outcome` | LLM completion calls (ok/error). No model name. |
| `lore_enrichment_embed_calls_total` | counter | `outcome` | Embedding calls (ok/error). No model name. |

Scrape: `curl -s http://localhost:8221/metrics`.

---

## 6. The enrichment job flow

1. **Gap detect** — derive missing dimensions for the target entities (read-only over the KG via the C1 port; empty/down graph → no gaps, never raises).
2. **Estimate** (`pending → estimating`) — sum per-gap cost + the reserved eval line (M5).
3. **Run** (`estimating → running`) — per gap, in order:
   - **cost-cap check BEFORE the gap** — breach → **pause** (`running → paused`), eval reserve protected, re-runnable safely.
   - **stage pipeline** — retrieval (C10) → schema-governed generation (C11, H0 chokepoint) → canon-verify (C12 annotation only). An ungroundable/unrepairable gap is **skipped**, never failed (H0: no unprovenanced fact).
   - **persist** one quarantined proposal (`origin='enrichment'`, `confidence<1.0`, `review_status='proposed'`). Idempotent per `gap_ref` (`UNIQUE(job_id, gap_ref)` → re-run reloads, never duplicates).
   - emit `stage_completed` + `proposal_created` (idempotent; best-effort Redis).
4. **Complete** (`running → completed`) or **fail** (`→ failed`) — emit terminal event.

### Draining / resuming a paused (cost-capped) job
A cost-cap pause is **resumable + budget-safe** (NOT yet skip-prior-work). Re-run
via a runner seeded with prior spend so the cap accounts for it and does not
double-charge:

```python
bundle = await build_live_runner(..., spent_so_far=<job.actual_cost_usd>, ...)
await bundle.runner.run_job(job_id=..., gaps=..., context=...)
```

Re-running re-processes from gap 0 but never double-charges and never duplicates
proposals (it reloads already-persisted gaps as no-op `deduped`). Full
skip-prior-work resume is tracked as **DEFERRED-051**. Investigate a paused job:
check `enrichment_job.actual_cost_usd` vs the cap, raise the cap if intentional,
then re-run.

---

## 7. The eval gate (P2/P3 unlock) + licensing

- **P1** (retrieval) is always active.
- **P2** (fabrication) and **P3** (re-cook) are **gated**: they activate ONLY when
  the latest **passing** `enrichment_eval_runs` row for the project's suite is
  fresh (within `gate_max_age_seconds`). The `GateAwareStrategyFactory` is the
  SOLE selection path — a locked/stale gate forces non-P1 OFF
  (`InactiveStrategyError`), overriding any caller override (read-error fails
  CLOSED).
- Check the gate: `GET /internal/eval/{project_id}/gate-status` (internal token).
  `has_run=false` → locked (no eval yet).
- **Licensing (P3 only):** re-cook admits ONLY `public_domain` / `licensed`
  sources (default-deny). An unlicensed/copyrighted/unknown source →
  `UnlicensedSourceError`, job refused. Enforced at corpus-admission AND fact-emit.

### How to run the eval
```bash
# from repo root — score the demo fixture, baseline-diff, write a scorecard;
# exits non-zero on a gate-fail (the bad fixture BLOCKS).
python scripts/enrichment_eval.py --fixture eval/fixtures/enrichment_demo.json
python scripts/enrichment_eval.py --fixture eval/fixtures/enrichment_bad.json   # expect BLOCK
```
A live judge-ensemble run persists a real scorecard to `enrichment_eval_runs`,
which unlocks P2/P3 for that project (until stale). Climate/geo eval is a SEPARATE
namespace — C18 / enrichment eval never touches it.

---

## 8. The H0 invariant + author-promote

**H0 (LOCKED):** the service never writes canon autonomously. Every proposal is
quarantined; promotion is a human, author-only action.

- Proposal: `origin='enrichment'`, `0 < confidence < 1.0`, `review_status='proposed'`, `pending_validation=true`. Enforced in-app AND by DB CHECK/trigger (defense-in-depth: confidence CHECK, immutable origin, lifecycle-DAG trigger).
- **Promote** (`POST` author-only): verified against book-service projection `owner_user_id` (NOT a client claim). Flips KG facts + glossary canon to `source_type='glossary'`, `confidence=1.0`, `pending_validation=false`, while **permanently retaining** the origin marker (`origin='enrichment'`, `promoted_by`, `original_technique`, `promoted_from_proposal_id`). Idempotent (re-promote = no-op, no duplicate canon).
- **Retract** (M6): glossary recycle-bin soft-delete + KG `valid_until` (reversible).
- Lifecycle: `proposed → author_reviewing → approved → promoted | rejected`. Illegal jumps → 409.

---

## 9. Rollback

- **Service rollback:** redeploy the prior image tag; migrations are
  forward-idempotent and additive (each cycle's DDL guards on existence) — a
  rollback of code does not require a DB down-migration. If a specific migration
  must be reverted, use the matching down-migration (C2 ships up/down, tested
  idempotent).
- **Bad proposals:** they are quarantined — they never reached canon, so there is
  nothing to roll back in glossary/KG. Reject or delete the proposal rows.
- **Bad promote:** use **retract** (reversible soft-delete + KG `valid_until`),
  then re-review.
- **Disable P2/P3 immediately:** set `LORE_ENRICHMENT_GATE_MAX_AGE_SECONDS=1` (or
  delete/expire the passing `enrichment_eval_runs` row) → the gate locks → only
  P1 runs.

---

## 10. Verification

CI gate: `scripts/raid/verify-cycle-18.sh` (exit 0 = pass) — runs the readiness +
metrics tests, the full suite, ruff, a no-hardcoded-model-name grep, a live
`/health` + `/ready` + `/metrics` scrape when the stack is up, and the final
`secret-scan-final.sh` + `prod-isolation-lint.sh` gates.
