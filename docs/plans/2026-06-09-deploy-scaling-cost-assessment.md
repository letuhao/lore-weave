# Deploy Scalability & Operating-Cost Assessment — Single-Node On-Prem

> **Date:** 2026-06-09 · **Branch:** `feat/on-prem-single-port` · **Scope:** the Docker-Compose deployment (`infra/docker-compose.yml` + `infra/docker-compose.prod.yml`).
> **Question answered:** *Khi deploy, hệ thống có scale up và optimize chi phí vận hành được không? Chỗ nào ảnh hưởng hoặc chưa optimize?*

---

## Tóm tắt (VN)

Đẩy LLM về phía user (BYOK) **đã xử lý đúng cái đắt nhất** — token cost + GPU inference cost biến mất khỏi server. Nhưng **"serve hàng nghìn user / 1 node"** chỉ đúng cho **user đọc/duyệt** (Go service goroutine-based, rất nhẹ). Với **user chạy AI job** (translation / extraction / enrichment), trần thật **không phải LLM** mà là **concurrency**: trần connection Postgres và worker 1-replica. Nghịch lý BYOK: đẩy LLM sang user làm mỗi job server-side **dài hơn** (chờ provider của user) trong khi **vẫn giữ nguyên 1 slot worker + 1 DB connection**.

## Executive summary (EN)

| Axis | Verdict |
|---|---|
| **Vertical scale (1 bigger box)** | ✅ for read/browse load (Go services); ⚠️ hits the **DB-connection ceiling** and **worker-concurrency wall** before CPU/RAM for AI-job load. |
| **Operating cost** | ✅ BYOK removed the dominant variable cost. Remaining waste is **storage growth** (logs + MinIO objects) and **always-on heavy containers** (Neo4j JVM), all addressable. |
| **"Thousands of users / one node"** | ✅ thousands of **concurrent readers**. ❌ thousands of **concurrent AI-job runners** — bottlenecked at worker slots + DB connections, *not* at LLM compute. |

The architecture (microservices, queue-backed workers, BYOK) is fundamentally sound and built to scale **out**. The current single-node Compose deployment has a handful of latent ceilings that only surface under the exact concurrent load it's meant to support.

---

## Topology (what actually runs)

~20 application containers + data tier, all on one Postgres **instance** with per-service logical DBs (NOT per-service instances — good for cost):

- **Go (web class):** auth, book, sharing, catalog, provider-registry, usage-billing, glossary, statistics, notification, worker-infra. Goroutine-based → scale across cores natively.
- **Python (single uvicorn):** translation(+worker), chat, knowledge, composition, video-gen, lore-enrichment(+worker), learning, worker-ai.
- **TS:** api-gateway-bff (single Node process), frontend (nginx).
- **Data/infra:** postgres, redis(valkey), rabbitmq, minio, neo4j (~3.5 GB JVM), languagetool (Java), pandoc.
- **Profile-gated (off in prod):** otel/tempo/grafana, game-server/tilemap/frontend-game, mock-audio, mailhog.

---

## A. Bottlenecks that cap single-node concurrency

### 🔴 A1 — Postgres connection ceiling (most severe, latent)

One Postgres, `max_connections` **default 100** (no override in base compose). Sum of per-service **max** pool sizes:

| Group | Pool max | Subtotal |
|---|---|---|
| 9 Go HTTP services — pgxpool `MaxConns=10` (hardcoded in each `cmd/*/main.go`) | 10 | 90 |
| worker-infra — ~7 pgxpools (events + book + 5 outbox sources) | 10 | ~70 |
| 6 Python asyncpg services (`max_size=10`; knowledge has **2** pools) | 10 | 70 |
| worker-ai (`max_size=5`) / translation-worker (`max_size=10`) | — | 15 |
| **Aggregate burst ceiling** | | **~205–245** |

- Verified `min_size=2` (asyncpg) / `MinConns=0` (pgxpool) → **idle ≈ 18–25 connections**, so dev/test never sees it. The ceiling is reached **under concurrent load** → `too many connections` / pool-acquire timeouts → cross-service cascade.
- Evidence: [services/chat-service/app/db/pool.py:8](services/chat-service/app/db/pool.py#L8), [services/knowledge-service/app/db/pool.py:10](services/knowledge-service/app/db/pool.py#L10) (×2 pools), [services/worker-ai/app/main.py:48](services/worker-ai/app/main.py#L48); Go pools in `services/*/cmd/*/main.go`. No PgBouncer anywhere in the repo.
- **Interim fix shipped (this pass):** `max_connections=200` + `shared_buffers=256MB` on Postgres in the prod overlay (2× headroom for realistic peaks).
- **Real fix (deferred → `D-DEPLOY-PGBOUNCER`):** PgBouncer in transaction-pooling mode; then per-service pools can stay small while many services multiplex onto few backends. **Prerequisite for any horizontal replica scaling** — SR08's design proposes `db_pool_size: 30–60` *per replica*, which without a pooler would blow past 100 instantly.

### 🟠 A2 — Single-replica workers, `prefetch=1` (caps AI-job throughput) — *accepted trade-off*

- [services/translation-service/worker.py:107](services/translation-service/worker.py#L107) — RabbitMQ `prefetch_count=1` → 1 chapter at a time.
- [services/worker-ai/app/config.py](services/worker-ai/app/config.py) — `poll_interval_s=5.0`, `items_per_status_check=1`.
- lore-enrichment-worker — `count=1` per `XREADGROUP`.
- All three are **single replica** (no `replicas:` in compose). Effective throughput ≈ **1 job / 30–90 s per worker type**; concurrent AI users → queue grows.

**Stance (PO 2026-06-09):** this is a **deliberate, accepted design**, not a defect. Single-replica queue-backed background workers give back-pressure, fault isolation, and BYOK cost-control (a slow user provider can't fan out and exhaust the box). Every large system has this shape. **The scaling lever is documented, not pulled:** when AI-job concurrency becomes the real constraint, raise `deploy.replicas` (each replica = one independent consumer, `prefetch=1` stays safe) and/or `prefetch_count`. **This depends on A1 being fixed first** (more worker replicas = more DB connections).

### 🟠 A3 — Single-process gateway & Python services

- **api-gateway-bff:** one Node process, no clustering ([services/api-gateway-bff/Dockerfile](services/api-gateway-bff/Dockerfile)). All external traffic flows through one core.
- **Python services:** single uvicorn, no `--workers`. Excellent for I/O-concurrency (awaiting the user's LLM) but **one core for CPU-bound work** (parsing large chapters, embedding prep).
- **BFF rate limit:** 120 req/min/IP, **in-memory** ([services/api-gateway-bff/src/rate-limit.ts](services/api-gateway-bff/src/rate-limit.ts)). Correct per-user after ngrok/ALB (`TRUST_PROXY=true`), but **cannot scale to multiple gateway replicas** without a shared (Redis) store. → scale-out blocker, see §C.

---

## B. Operating-cost / 24×7 stability — not yet optimized

| # | Issue | Evidence | Bite | Status |
|---|---|---|---|---|
| B1 | **No restart policy** on infra + core API | base compose: postgres/redis/rabbitmq/minio/gateway/Go services lacked `restart:` | one OOM/segfault = downtime until manual `docker compose up`; postgres down = whole stack down | ✅ **Fixed this pass** — `restart: unless-stopped` added to 20 always-on services in the prod overlay (29 total in merged config) |
| B2 | **No CPU/mem limits** (only Neo4j) | [infra/docker-compose.yml:1142](infra/docker-compose.yml#L1142) | one runaway service (knowledge extraction, languagetool JVM) can OOM-kill the node | ⏳ `D-DEPLOY-RESOURCE-LIMITS` |
| B3 | **Logs unbounded** (33/35 services) | only knowledge-service + worker-ai have rotation | disk fills in weeks → node dies | ✅ **Addressed** — committed [infra/daemon.json](infra/daemon.json) (host-wide 50m×5); install step documented below |
| B4 | **MinIO no lifecycle** | no `mc ilm` for `lw-chat`, `loreweave-audio-cache`, books, video | objects accumulate to TB | ⏳ `D-DEPLOY-MINIO-LIFECYCLE` (reaper today only covers lore-enrichment) |
| B5 | **Neo4j ~3.5 GB always-on** | [infra/docker-compose.yml:1113](infra/docker-compose.yml#L1113) | biggest RAM line-item; small box swaps | ⏳ run `NEO4J_URI=` for Track-1-only, else size the box for it |
| B6 | **Healthcheck churn** | 9 services spawn `python -c` every 5 s; db-ensure runs 15× `psql` every 5 s ([infra/db-ensure.sh](infra/db-ensure.sh)) | ~180 psql spawns/min + subprocess churn (idempotent — `SELECT 1`, only `CREATE DATABASE` when missing) | ⏳ `D-DEPLOY-HEALTHCHECK` — switch to `curl`, widen to 10–15 s, move db-ensure to init-only |
| B7 | Observability always-on? | otel/tempo/grafana | — | ✅ already `--profile observability` gated |

---

## C. Scale-OUT blockers (for later, when one node isn't enough)

The microservice split is built for horizontal scale; these single points must be externalized first:

- **In-memory BFF rate limiter** → Redis-backed (Redis already in stack).
- **No connection pooler** → PgBouncer (also fixes A1).
- **Single RabbitMQ / Redis / Postgres / MinIO** → managed/externalized on AWS (RDS, ElastiCache, Amazon MQ, S3) — matches the CLAUDE.md hosting model.
- **No replicas/HPA in compose** → the full design already exists at [docs/03_planning/LLM_MMO_RPG/02_storage/SR08_capacity_scaling.md](docs/03_planning/LLM_MMO_RPG/02_storage/SR08_capacity_scaling.md) (class taxonomy, HPA/KEDA, `contracts/capacity/budgets.yaml`). ⚠️ SR08's proposed `db_pool_size 30–60/replica` is **incompatible with today's no-pooler Postgres** — PgBouncer is a hard prerequisite before implementing it.

---

## What changed in this pass (2026-06-09)

Low-risk quick-wins only (config; no app-logic change). Merged config validated with `docker compose config` (EXIT 0).

1. **`infra/docker-compose.prod.yml`** — `restart: unless-stopped` on 20 always-on services (infra + Go core + gateway + Python API services + frontend); Postgres `command:` raising `max_connections=200` + `shared_buffers=256MB` (interim A1 headroom).
2. **`infra/daemon.json`** (new) — host-wide json-file log rotation (50m × 5 files). **Manual host step** (not auto-applied by compose):
   - **Linux:** `sudo cp infra/daemon.json /etc/docker/daemon.json && sudo systemctl restart docker`, then recreate the stack.
   - **Docker Desktop:** Settings → Docker Engine → merge `log-driver`/`log-opts` → Apply & Restart.
   - Existing containers must be recreated to pick up the new default.

## Recommended next steps (priority order)

1. **`D-DEPLOY-PGBOUNCER`** (unblocks everything) — PgBouncer transaction pooling in front of Postgres; shrink per-service pools.
2. **`D-DEPLOY-MINIO-LIFECYCLE`** — bucket expiry: audio-cache 48 h (doc already specifies the TTL, not enforced), chat 90 d, video 30 d; extend the orphan reaper beyond lore-enrichment.
3. **`D-DEPLOY-RESOURCE-LIMITS`** — `deploy.resources.limits` on the heavy services (knowledge, worker-ai, languagetool, neo4j) so one can't OOM the node.
4. **`D-DEPLOY-HEALTHCHECK`** — cheaper/less-frequent healthchecks; db-ensure init-only.
5. **Worker throughput (A2)** — *only when AI-job concurrency is the measured constraint*: `replicas:` + `prefetch` tuning (after PgBouncer).
6. **Measure before scaling out** — k6/locust load test against the prod overlay to find the real breakpoint (validates the A1/A2 ceilings with numbers, per SR08's load-test gate).
