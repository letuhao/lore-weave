# LoreWeave — Architecture

Self-hosted Docker Compose monorepo. **24 application services + infra containers + frontend.** Contract-first API design. Event-driven with the outbox pattern.

---

## System Overview

```
                    ┌─────────────────────────┐
                    │    React + Tiptap        │
                    │  (Vite, Tailwind, shadcn)│
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   NestJS Gateway / BFF   │
                    └────────────┬────────────┘
                                 │
        ┌────────────────────────┼────────────────────────────┐
        │                        │                            │
  ┌─────▼──────┐        ┌────────▼──────────┐        ┌────────▼────────┐
  │ Go Domain  │        │ Python AI / LLM   │        │ Async Workers   │
  │ Services   │        │ Services          │        │ (Go + Python)   │
  │ (9 svcs)   │        │ (incl. knowledge, │        │ outbox · jobs · │
  │            │        │  composition,     │        │ AI extraction   │
  │            │        │  learning, etc.)  │        │                 │
  └─────┬──────┘        └────────┬──────────┘        └────────┬────────┘
        │                        │                            │
  ┌─────▼────────────────────────▼────────────────────────────▼────────┐
  │ Postgres 18 │ Neo4j │ Redis │ RabbitMQ │ MinIO │ LanguageTool │ …  │
  └────────────────────────────────────────────────────────────────────┘
```

---

## Services

| Service | Language | Purpose |
|---------|----------|---------|
| **api-gateway-bff** | TypeScript / NestJS | Single entry point for all external traffic |
| **auth-service** | Go / Chi | Identity, JWT, sessions, profiles, follows |
| **book-service** | Go / Chi | Books, chapters, chunks, lifecycle, editorial (draft/published) |
| **sharing-service** | Go / Chi | Visibility policies, share links |
| **catalog-service** | Go / Chi | Public book discovery, filtering, search |
| **provider-registry-service** | Go / Chi | BYOK credential storage, provider health, model registry |
| **usage-billing-service** | Go / Chi | Token metering, quota enforcement, cost estimation |
| **glossary-service** | Go / Chi | Glossary entities, dynamic attributes, evidence linking, wiki articles/revisions |
| **statistics-service** | Go / Chi | Analytics, usage metrics, dashboard data |
| **notification-service** | Go / Chi | Notifications, email delivery |
| **translation-service** | Python / FastAPI | Translation API + V3 multi-agent pipeline orchestration |
| **translation-worker** | Python | Async RabbitMQ batch translation worker |
| **chat-service** | Python / FastAPI | Streaming AI chat, thinking mode, multi-provider SSE, message feedback |
| **knowledge-service** | Python / FastAPI | Knowledge graph (Postgres SSOT + Neo4j derived), entity extraction, summaries, merge-candidate detection |
| **composition-service** | Python / FastAPI | Canon-aware co-writer — RAG context packing, LLM prose generation, advisory critic, Canon Model editorial lifecycle |
| **lore-enrichment-service** | Python / FastAPI | AI-driven lore enrichment — gap detection, retrieval-grounded generation, canon verification |
| **learning-service** | Python / FastAPI | Production eval + feedback flywheel — quality scores, eval runs, gold labels, online judge |
| **video-gen-service** | Python / FastAPI | Media generation BFF; ComfyUI workloads in sibling repo **local-image-generator-service** |
| **worker-infra** | Go | Outbox relay, cleanup, import processing, Pandoc conversion |
| **worker-ai** | Python | AI-driven async tasks (entity extraction, summary regen, embedding jobs) |
| **game-server** | TypeScript / Node.js + Colyseus | Living Worlds (Phase 6) — real-time multiplayer rooms |
| **tilemap-service** | Rust | Living Worlds (Phase 6+) — tile/spatial layer |
| **travel-service** | Rust | Living Worlds (Phase 6+) — movement/travel mechanics |
| **world-service** | Rust | Living Worlds (Phase 6+) — world state, reality model |

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Frontend** | React 18 + Vite + TypeScript | SPA with premium dark UI |
| **UI** | Tailwind CSS + shadcn/ui + Radix | Component library |
| **Editor** | Tiptap 3.x | Rich text with AI mode, media blocks, drag handles |
| **State** | TanStack React Query | Server state with persistent cache |
| **Forms** | React Hook Form + Zod | Validation |
| **i18n** | i18next | 4-language UI |
| **Charts** | Recharts | Usage analytics visualizations |
| **Gateway** | NestJS | Request routing, auth forwarding |
| **Domain Services** | Go + Chi | High-throughput, low-latency domain logic |
| **AI Services** | Python + FastAPI | LLM streaming, async translation workers |
| **Database** | PostgreSQL 18 + pgvector | Per-service schemas, JSONB storage, vector embeddings (HNSW) |
| **Knowledge Graph** | Neo4j | Derived graph for entity relations, memory, narrative queries |
| **Cache / Streams** | Redis 7 | Sessions, caching, rate limiting, event streams (outbox fan-out) |
| **Message Queue** | RabbitMQ 3.13 | Translation + heavy AI job distribution |
| **Object Storage** | MinIO | S3-compatible — media, exports, uploads |
| **Grammar** | LanguageTool | Spell check, grammar analysis |
| **Doc Conversion** | Pandoc Server | HTML, Markdown, DOCX format conversion |
| **Email (dev)** | Mailhog | SMTP sandbox |
| **Multiplayer** | Colyseus (Node.js) | Real-time game rooms (Phase 6) |

---

## Design Principles

- **Contract-first** — OpenAPI specs frozen before any frontend work begins
- **Gateway invariant** — all external traffic enters through the NestJS BFF
- **Provider gateway** — no direct AI SDK calls; everything through the adapter layer
- **Language rule** — Go for domain services, Python for AI/LLM services, TypeScript for gateway
- **Per-service databases** — each microservice owns its own PostgreSQL schema
- **Event-driven** — outbox pattern with Redis Streams for reliable async processing
- **No hardcoded secrets** — all secrets via env vars; services fail to start if missing
- **No hardcoded model names** — model names resolved from provider-registry

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
  │  pgvector    │───▶│  RAG Context  │───▶│  Chat · Translation  │
  │  HNSW index  │    │  Assembly     │    │  Composition · NPCs* │
  └──────────────┘    └──────────────┘    └─────────────────────┘
                                                       *Phase 6+
```

---

## Infrastructure

- **Cloud target**: AWS (ECS/EC2, RDS, S3, ElastiCache)
- **Local development**: Docker Compose — same services, same architecture
- **Multi-device, multi-user**: designed for simultaneous PC, phone, tablet access
- **Ports (dev)**: Frontend `:5173` · Gateway `:3123` · ContextHub MCP `:3000`

See `infra/` for Docker Compose configuration and `contracts/api/` for OpenAPI specs.
