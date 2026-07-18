# LoreWeave — Architecture

> **Purpose:** Application + technology architecture entry point — what the services are, what each one does, and how they fit together.
> **Audience:** Developers, architects, and AI agents onboarding to the monorepo.
> **Last updated:** 2026-07-17
>
> **Companion docs:** [`DATA_ARCHITECTURE.md`](DATA_ARCHITECTURE.md) (SSOT layers, DB ownership, data flows) · [`standards/README.md`](standards/README.md) (every cross-cutting rule/law/invariant) · [`FEATURE_INDEX.md`](FEATURE_INDEX.md) (frontend feature → route → backing service)

Cloud-hosted (AWS target) monorepo, Docker Compose for local development. **47 services + infra containers + 3 frontends.** Contract-first API design. Event-driven with the transactional outbox pattern.

---

## Source-of-truth pointers (read these before trusting the tables below)

| Fact | Authoritative source |
|---|---|
| Service → **language** | [`contracts/language-rule.yaml`](../contracts/language-rule.yaml) — enforced by `scripts/language-rule-lint.sh` |
| Service → **purpose** | **this document** (§Services) |
| Service → **port / compose wiring** | [`infra/docker-compose.yml`](../infra/docker-compose.yml) |
| Service → **database** | [`DATA_ARCHITECTURE.md`](DATA_ARCHITECTURE.md) §4 |
| API shape | [`contracts/api/`](../contracts/api/) |
| Cross-cutting rules | [`standards/README.md`](standards/README.md) |

The service tables here are hand-maintained and therefore driftable. `contracts/language-rule.yaml` is machine-enforced (a present service with no row FAILs the lint), so **it** is the count of record. As of 2026-07-17 the yaml holds **52 rows: 47 mapped + 5 declared `missing`** (not yet scaffolded).

---

## System Overview

```
                 ┌──────────────┬──────────────┬──────────────┐
                 │  frontend    │ cms-frontend │ frontend-game│
                 │ (React SPA)  │ (admin CMS)  │  (MMO V0)    │
                 └──────┬───────┴──────┬───────┴──────┬───────┘
                        │              │              │
        ┌───────────────▼──────────────▼──────┐  ┌────▼──────────┐
        │      api-gateway-bff (NestJS)       │  │  game-server  │
        │      the public HTTP edge           │  │  (Colyseus WS)│
        └───┬──────────┬──────────┬───────────┘  └───────────────┘
            │          │          │                 ↑ 2nd public edge
            │          │          │                   (PRR-20 exception)
     ┌──────▼───┐ ┌────▼─────┐ ┌──▼──────────────┐
     │ Go domain│ │Python AI │ │ knowledge-gtwy  │      ┌──────────────────┐
     │ (28 svcs)│ │(10 svcs) │ │ (KAL typed R/W) │      │ mcp-public-gateway│
     └──────┬───┘ └────┬─────┘ └──┬──────────────┘      │  (external agents)│
            │          │          │                     └─────────┬────────┘
            │     ┌────▼──────────▼───┐                           │
            │     │    ai-gateway     │◄──────────────────────────┘
            │     │  (MCP federation) │
            │     └────────┬──────────┘
            │              │
     ┌──────▼──────────────▼───────────────────────────┐
     │   provider-registry-service                      │
     │   THE only home of provider SDKs/keys            │
     │   (LLM · embed · rerank · image · audio · STT)   │
     └──────────────────────┬───────────────────────────┘
                            │
  ┌─────────────────────────▼──────────────────────────────────────────┐
  │ Postgres 18 │ Neo4j │ Valkey/Redis │ RabbitMQ │ MinIO │ LanguageTool│
  └────────────────────────────────────────────────────────────────────┘
```

**Two public entry points, by design:** `api-gateway-bff` (all HTTP) and `game-server` (Colyseus WebSocket, the sanctioned PRR-20 exception — it inherits the same auth/rate-limit/audit edge controls). `mcp-public-gateway` is the external-agent MCP edge and relays inward through `ai-gateway`.

---

## Services

47 service directories, grouped by tier. **Language is not editorial — it follows the LOCKED language rule (I3):** Rust = kernel-derived · Go = domain/meta · Python = AI/LLM · TypeScript = gateway/BFF + realtime.

"Compose" = host port in [`infra/docker-compose.yml`](../infra/docker-compose.yml); **`—` means the service is not in the local dev stack at all** (see §Not in the local stack).

### Edge & gateway (TypeScript · 5)

| Service | Purpose | Compose |
|---|---|---|
| **api-gateway-bff** | The public HTTP edge / BFF for the web frontend. All external traffic enters here. | `3123` |
| **ai-gateway** | Internal AI/**MCP federation** gateway — one MCP face federating the domain MCP tool servers. | `8218` |
| **mcp-public-gateway** | Public MCP security edge — external agent creds → auth/scope/spend/audit → internal envelope → `ai-gateway`. | `8219` |
| **knowledge-gateway** | KAL — single typed read/write boundary federating glossary (Go) + knowledge (Python) per `kal.v1.yaml`. | `3210` |
| **game-server** | MMORPG realtime server (Node + Colyseus). V0 = single EchoRoom. Second public edge. | `2567` |

### Go domain services (10)

| Service | Purpose | Compose |
|---|---|---|
| **auth-service** | Identity, JWT, passwords, email tokens, admin-JWT issuance, diary DEK-under-KEK wrapping. | `8204` |
| **book-service** | Books/chapters/diary domain; MinIO storage, textdiff, diary encryption-at-rest. | `8205` |
| **sharing-service** | Share links / visibility permissions over book-service. | `8206` |
| **catalog-service** | Public catalog/discovery over book + sharing + translation. | `8207` |
| **provider-registry-service** | **The unified LLM gateway** — BYOK provider/model registry, job queue, governor/breaker, usage outbox relay, embed/rerank/web-search. | `8208` |
| **usage-billing-service** | Spend guardrails, platform balances, free tier, `usage_logs` audit consumer. | `8209` |
| **glossary-service** | Glossary/entity domain **+ the wiki** (`wiki_*` tables), entity revisions, deep-research. | `8211` |
| **statistics-service** | Stats projection + read API (event consumer). | `8214` |
| **notification-service** | Notifications — categories, prefs, push, redaction, event consumer. | `8215` |
| **agent-registry-service** | Agent Extensibility Registry — plugin/skill/MCP-server registrations, AES-GCM secret vault. | `8230` |

### Python AI / LLM services (10)

| Service | Purpose | Compose |
|---|---|---|
| **chat-service** | Chat sessions/messages, voice, tool permissions, AI settings, evaluate/feedback. | `8212` |
| **knowledge-service** | Project-scoped memory/KG context — the derived fuzzy/semantic layer (Postgres SSOT + Neo4j). | `8216` |
| **translation-service** | Translation domain — v2 text/block + V3 verify/correct; decoupled LLM path, P5 WFQ. | `8210` |
| **composition-service** | LOOM co-writer — RAG-packs canon, motif/arc conformance, PlanForge. | `8217` |
| **lore-enrichment-service** | Lore enrichment — retrieval/generation/verify/gaps/compose + MCP surface. | `8221` |
| **learning-service** | Correction capture — consumes the glossary/knowledge correction spine → `corrections` log. | `8222` |
| **campaign-service** | Auto-Draft Factory — saga orchestrator + per-chapter projection. | `8223` |
| **jobs-service** | Unified Job Control Plane — consumes `loreweave:events:jobs` → `job_projection`; `/v1/jobs` + SSE. | `8224` |
| **video-gen-service** | Thin domain BFF for video generation → LLM gateway → MinIO + billing. | `8213` |
| **worker-ai** | Async poll loop processing running extraction jobs (worker, not a web server). | `8226` |

### Rust — kernel-derived / MMO substrate (4)

| Service | Purpose | Compose |
|---|---|---|
| **roleplay-service** | First user-facing Rust service — scripts + actor-memory + start-orchestration (axum + Postgres). | `8225` |
| **tilemap-service** | Procedural tilemap generation (continent/country/district/town). Uses the `loreweave_llm` crate. | `8220` |
| **world-service** | Geography substrate — `world_geometry` + POL/SET/ROUTE activation generators. | — |
| **travel-service** | Travel mechanics — 5 aggregates (actor travel state, composite journey, mount, encounter, party). | — |

### Workers & meta (Go · 4)

| Service | Purpose | Compose |
|---|---|---|
| **worker-infra** | Infra task worker (registry + tasks); outbox-relays `loreweave:events:jobs`. | (no port) |
| **meta-outbox-relay** | Drains the meta DB `meta_outbox` → Redis Streams. | — |
| **meta-worker** | The **only** consumer of `xreality.*` Redis Streams (I7 invariant). | — |
| **scheduler-service** | Per-user tick driver; claims due `scheduled_agent_runs` → posts to chat. | `8228` |

### SRE / reality-ops tier (Go · 14) — none in the local stack

Built for the Living Worlds multi-reality operating model. All 14 are absent from `docker-compose.yml`.

| Service | Purpose |
|---|---|
| **admin-cli** | Single-binary admin CLI; registry from `contracts/admin/registry/*.yaml`. |
| **alert-recorder** | Alertmanager webhook sink → `alert_outcomes`/`alert_silences` audit. |
| **incident-bot** | Incident decide + emit. |
| **postmortem-bot** | On `IncidentClosedV1` → generates `docs/sre/postmortems/<id>.md`; validates the 12-enum root-cause taxonomy. |
| **statuspage-updater** | Listens to incident events → updates the status page. |
| **breach-notifier** | Consumes `lw.incidents.breach` → GDPR Art.33 DPO notice + durable marker. |
| **canary-controller** | Canary rollout executor + auto-abort. |
| **slo-budget-calculator** | Reads `contracts/slo/*.yaml`; JSON read API for alertmanager rule evaluation. |
| **integrity-checker** | Daily-sampling + monthly-full projection integrity checks. |
| **migration-orchestrator** | Drives schema migrations across N per-reality DBs. |
| **backup-scheduler** | Tiered backup orchestrator; reads `reality_registry.status` per tick. |
| **archive-worker** | Per-reality cron: archive old `events_p_YYYY_MM` partitions → MinIO Parquet+ZSTD, then drop. |
| **retention-worker** | Per-reality cron enforcing the R1–L3 retention rules. |
| **publisher** | Cold-path outbox publisher: per-reality `events_outbox` → Redis Streams; heartbeats meta. |

### Worker sidecars (not service directories)

Same image as their parent, no port, `command` override in compose: `composition-worker`, `translation-worker`, `video-gen-worker`, `lore-enrichment-worker`.

### Declared-`missing` in language-rule.yaml (5)

Rows that exist in the contract but have **no directory yet** — this is the expected state; the lint only FAILs if a declared-missing directory *appears*: `embedding-worker`, `event-handler`, `chaos-engine`, `oncall-bot`, `session-cost-rollup-worker`.

### Not in the local stack (18)

The 14 SRE/reality-ops services above, plus `world-service`, `travel-service`, `meta-outbox-relay`, `meta-worker`. Running `docker compose up` gives you the novel platform, not the reality-ops tier.

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| **Frontend** | React 18 + Vite + TypeScript | 3 SPAs: `frontend` (main), `cms-frontend` (admin), `frontend-game` (MMO V0) |
| **UI** | Tailwind CSS + shadcn/ui + Radix | |
| **Editor** | Tiptap 3.x | AI mode, media blocks, drag handles |
| **Panels** | Dockview | Dockable/pop-out studio panels |
| **State** | TanStack React Query | Server state with persistent cache |
| **Forms** | React Hook Form + Zod | |
| **i18n** | i18next | **18 locales** |
| **Gateway** | NestJS | `api-gateway-bff`, `knowledge-gateway` |
| **Domain** | Go + Chi | |
| **AI** | Python + FastAPI | |
| **Kernel/MMO** | Rust + axum | |
| **Database** | PostgreSQL 18 + pgvector | Database-per-service |
| **Knowledge Graph** | Neo4j 2026.03 | Derived graph + native vectors |
| **Cache / Streams** | Valkey 8 (Redis-compatible) | Cache, rate limits, outbox stream fan-out |
| **Message Queue** | RabbitMQ 3.13 | Heavy async jobs |
| **Object Storage** | MinIO | S3-compatible |
| **Grammar** | LanguageTool | |
| **Doc Conversion** | Pandoc Server | |
| **Email (dev)** | Mailhog | |
| **Observability** | OpenTelemetry Collector + Tempo + Grafana | `observability` compose profile |
| **Multiplayer** | Colyseus | |

---

## Design Principles

Full catalogue — every rule, its authoritative home, and how it's enforced: **[`standards/README.md`](standards/README.md)**. The load-bearing subset:

- **Contract-first** — OpenAPI frozen before frontend work.
- **Gateway invariant** — all external traffic through `api-gateway-bff`; the ONE sanctioned exception is `game-server`'s Colyseus WebSocket (PRR-20).
- **Provider gateway invariant (ENFORCED)** — no service imports a provider SDK; every LLM/embedding/rerank/image/audio/STT call goes through `provider-registry-service`. **Local/self-hosted backends are not an exception** — they integrate as BYOK provider credentials, never per-service `*_URL` config.
- **MCP-first for agent logic** — any capability where an LLM decides actions/calls tools is an MCP tool through `ai-gateway`, not a bespoke prompt+HTTP endpoint. Non-agentic LLM pipelines (translation, enrichment) are exempt.
- **No hardcoded model names (ENFORCED)** — models *and pricing* resolve from `provider-registry-service`.
- **Language rule (I3, LOCKED)** — see `contracts/language-rule.yaml`.
- **Database-per-service** — no cross-service FKs or direct table access.
- **Event-driven** — transactional outbox → relay → Redis Streams.
- **User boundaries / tenancy** — self-hosted ≠ single-user. Every user-facing resource declares a scope tier (System / per-user / per-book); a shared row that any authenticated user can mutate is a tenancy defect.
- **Settings boundary** — a per-user choice is a user setting, not an env flag. Env/global config is for platform infra and deploy-time ceilings.
- **No hardcoded secrets** — env vars only; services fail to start if missing.

The two ENFORCED provider rules are checked mechanically by `scripts/ai-provider-gate.py` (pre-commit hook via `git config core.hooksPath .githooks`).

---

## The Knowledge Pipeline

How your writing becomes the AI's context:

```
  You write a chapter
        │
        ▼
  ┌──────────────┐    ┌──────────────┐    ┌─────────────────────┐
  │  Entity      │───▶│  Evidence     │───▶│  Knowledge Graph     │
  │  Extraction  │    │  Linking      │    │  (Postgres + Neo4j)  │
  └──────────────┘    └──────────────┘    └─────────┬───────────┘
                                                     │
        ┌────────────────────────────────────────────┘
        ▼
  ┌──────────────┐    ┌──────────────┐    ┌─────────────────────┐
  │  pgvector /  │───▶│  RAG Context  │───▶│  Chat · Translation  │
  │  Neo4j vec   │    │  Assembly     │    │  Composition · NPCs* │
  └──────────────┘    └──────────────┘    └─────────────────────┘
                                                       *Living Worlds
```

**Two-layer lore model** — `glossary-service` is the **authored SSOT** (and hosts the wiki); `knowledge-service` is the **derived** fuzzy/semantic layer, anchored to glossary via `glossary_entity_id`. Extraction writes canonical entities *through* glossary; it never writes canonical content straight to Neo4j. See [`standards/scope-separation.md`](standards/scope-separation.md).

Full data flows: [`DATA_ARCHITECTURE.md`](DATA_ARCHITECTURE.md) §6.

---

## Infrastructure

- **Cloud target**: AWS (ECS/EC2, RDS, S3, ElastiCache)
- **Local development**: Docker Compose — same services, same architecture
- **Multi-device, multi-user**: designed for simultaneous PC, phone, tablet access
- **Self-hosted ≠ local-only** — it means the user controls the infrastructure

### Infra containers (dev)

| Container | Image | Host port(s) |
|---|---|---|
| postgres | `postgres:18-alpine` | `5555` |
| redis | `valkey/valkey:8-alpine` | `6399` |
| minio | `minio/minio` | `9123` (API), `9124` (console) |
| rabbitmq | `rabbitmq:3.13-management-alpine` | `5795`, `15795` (UI) |
| neo4j | `neo4j:2026.03-community` | `7475` (HTTP), `7688` (Bolt) |
| mailhog | `mailhog/mailhog` | `1148` (SMTP), `8148` (UI) |
| languagetool | `erikvl87/languagetool` | `8875` |
| pandoc-server | `pandoc/core` | `3030` |
| grafana | `grafana/grafana:11.4.0` | `3200` — `observability` profile |
| tempo | `grafana/tempo:2.6.1` | — |
| otel-collector | `otel/opentelemetry-collector-contrib` | `4317`/`4318` — `observability` profile |
| mock-audio-service | local build | `8600` — `audio` profile |

### Key dev ports

```
frontend       :5174   the BAKED nginx prod build — rebuild the image for FE changes.
                       A host `vite dev` can SHADOW it. Robust FE smoke = built image
                       on a free port, or `vite dev` on :5199.
cms-frontend   :5175   admin CMS (System-tier glossary standards)
frontend-game  :5176   Living Worlds V0 demo SPA — profiles `game`/`full` only
gateway        :3123   api-gateway-bff (container :3000)
ContextHub MCP :3000   a DISTINCT optional service, NOT the gateway
```

The frontend talks to the gateway via **relative `/v1`** — vite proxies to `:3123` in dev, nginx proxies to `gateway:3000` in prod. A non-empty `VITE_API_BASE` bakes a fixed host into the bundle and breaks any other origin.

> **The three SPAs must hold distinct host ports.** `frontend-game` was `5174:5174` and collided with `frontend` (`5174:80`, no profile ⇒ always up), so `docker compose --profile game up` failed to bind; it moved to `5176:5174` on 2026-07-17. Its container port is still 5174 (nginx + `/livez` healthcheck are internal). **`frontend-game`'s host port is also its browser origin**, so the `LOREWEAVE_CORS_ORIGINS` defaults on `tilemap-service`, `roleplay-service`, and `game-server` must track it — all three now default to `http://localhost:5176`. Move the port without moving those and the game gets CORS-blocked.

`postgres` runs `infra/db-ensure.sh` on a healthcheck, creating any missing per-service DBs on every start. Every first-party build stamps `org.loreweave.git_sha` / `build_time` labels (the F-LIVE-1 stale-image guard, via `scripts/build-stack.sh`) — **rebuild before an E2E smoke; stale images produce false greens.**

---

## Drift prevention

### When to update this doc

- A service is added, removed, or renamed
- A service's purpose materially changes
- A public entry point or invariant changes
- A tech-stack component is swapped (e.g. Redis → Valkey)

### How to check this doc against reality

```bash
ls services/                          # directory truth
./scripts/language-rule-lint.sh       # FAILs on any unmapped/mismapped service
python scripts/ai-provider-gate.py    # FAILs on provider-SDK / hardcoded-model drift
```

If `ls services/ | wc -l` disagrees with the count at the top of this file, this document is stale — fix it in the same commit as the service change.

---

*Application + technology architecture entry point. For the data domain, see [`DATA_ARCHITECTURE.md`](DATA_ARCHITECTURE.md). For the frontend feature map, see [`FEATURE_INDEX.md`](FEATURE_INDEX.md).*
