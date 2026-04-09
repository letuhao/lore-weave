# LoreWeave

**AI-native novel writing platform. You bring the imagination — AI handles the craft.**

LoreWeave is a self-hosted platform where AI and humans co-author multilingual novels. It's not a writing tool with AI bolted on — it's an **AI-first, human-in-the-loop** system where translation, worldbuilding, continuity tracking, and style coaching are foundational, not features.

Built for **anyone with a story to tell** — not just professional writers. The richer your worldbuilding, the smarter your AI collaborator becomes. Your glossary entities, chapter chunks, and world facts feed the RAG pipeline, so when you ask *"what would Kael do here?"*, the AI knows Kael's personality, backstory, and last scene appearance.

BYOK (Bring Your Own Key) — works with OpenAI, Anthropic, LM Studio, Ollama, and any OpenAI-compatible provider. Self-hosted. Your keys, your data, your stories.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Open Source](https://img.shields.io/badge/Open%20Source-Community-blue.svg)](https://github.com/)

---

## Why LoreWeave?

Most writing platforms treat AI as a sidebar autocomplete. LoreWeave flips the model:

- **AI-first architecture** — every feature assumes an AI collaborator is in the room
- **Human-in-the-loop** — AI drafts, suggests, translates, and checks continuity; you decide what stays
- **RAG-powered worldbuilding** — your lore database *is* the AI's context. Characters, locations, relationships, and plot events ground every AI response in your canon
- **Multilingual from day one** — write in one language, translate to many, keep glossary terms consistent across all of them
- **No vendor lock-in** — bring keys from any provider, run local models, switch anytime

This isn't a tool for writers who already know the craft. It's for **the dreamer who has a world in their head and needs a partner to get it on paper**.

---

## Screenshots

### AI Chat with Thinking Mode
Chat with any LLM. System prompts, generation parameters, thinking mode with real-time reasoning display, message branching, prompt templates.

![Chat with Session Settings](docs/screenshots/chat-enhanced.png)

### Rich Editor with AI Assistant Mode
Mixed media editor with text, images, audio narration, AI prompts, grammar checking, and source view. Visual/Source toggle, chapter sidebar, and grammar panel.

![AI Editor Mode](docs/screenshots/editor-ai-mode.png)

### Chapter Editor
Paragraph-level editing with revision history, chunk selection, inline translation, and AI context tools.

![Chapter Editor](docs/screenshots/chapter-editor.png)

### Immersive Reader
Clean reading mode with table of contents, multi-language support, and chapter navigation.

![Reader](docs/screenshots/reader.png)

### Translation Matrix
Batch translate chapters across multiple languages. Track progress, manage translation jobs, review status per chapter.

![Translation Matrix](docs/screenshots/translation.png)

### Browse & Discover
Public catalog with genre filtering, language chips, search, and book cards.

![Browse Catalog](docs/screenshots/browse-catalog.png)

### Glossary & Lore Management
Entity kinds (Character, Location, Item, etc.), custom attributes, system vs user fields, cross-reference tracking.

![Glossary Management](docs/screenshots/glossary.png)

### Entity Editor
Card-based attribute editing with system/user separation, tags, evidence linking, and relationship tracking.

![Entity Editor](docs/screenshots/entity-editor.png)

### AI Usage Monitor
Track token usage, costs, and performance across all AI operations. Per-model and per-purpose breakdowns.

![Usage Monitor](docs/screenshots/usage-monitor.png)

---

## Features

### Writing & Editing
- Tiptap-based rich text editor with AI and Classic modes
- Paragraph-level chunk editing and selection
- Revision history with restore, version comparison
- Media blocks: images, video, code (AI mode)
- Source view (block JSON inspector)
- Integrated grammar and spell checking via LanguageTool

### AI Chat
- Multi-provider streaming (OpenAI, Anthropic, LM Studio, Ollama)
- Thinking mode — real-time reasoning display (Qwen3, DeepSeek-R1)
- System prompts with presets (Novelist, Translator, Worldbuilder, Editor)
- Generation parameters (temperature, top_p, max_tokens)
- Message branching — edit creates a branch, never overwrites history
- Prompt template library (type "/" to search)
- Response format pills (Concise, Detailed, Bullets, Table)
- Token usage and timing metrics per message (TTFT, response time)
- Context attachment (books, chapters, glossary entities)
- Auto-title generation from first exchange

### Translation
- Batch translation pipeline with async RabbitMQ workers
- Translation matrix — status per chapter per language
- Per-chunk inline translation from editor
- Multi-language support (any language pair)
- Stale job recovery on startup

### Worldbuilding & Lore (RAG Foundation)
- Customizable entity kinds (Character, Location, Item, Organization, etc.)
- Dynamic attributes — add any field type (text, number, list, relationships)
- Evidence linking — tie lore entries to specific chapter paragraphs
- System + User attribute separation with versioned snapshots
- Genre groups for entity categorization
- Soft delete with full restore

### Community
- Public book catalog with search, genre, and language filters
- Sharing — public, unlisted (link-only), private visibility
- User profiles with follow system, favorites, and translator stats

### Platform
- BYOK — bring your own API keys from any provider
- Dynamic model discovery from provider APIs (58+ LM Studio models auto-detected)
- AI usage monitoring with cost estimates and daily/monthly breakdowns
- Quota enforcement and token tracking per model, per user
- Recycle bin with restore
- Settings: Account, Providers, Translation, Reading, Language
- i18n UI (4 languages)

---

## Architecture

Self-hosted Docker Compose monorepo. 14 containers. Contract-first API design. Event-driven.

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
        ┌────────────────────────┼──────────────────────────┐
        │                        │                          │
  ┌─────▼───────┐       ┌───────▼────────┐       ┌─────────▼─────────┐
  │ Go Domain   │       │  Python AI/LLM │       │   Worker Infra    │
  │ Services    │       │   Services     │       │  (outbox, jobs,   │
  │ (7 svcs)    │       │  (3 svcs)      │       │   import, Pandoc) │
  └─────┬───────┘       └───────┬────────┘       └─────────┬─────────┘
        │                        │                          │
  ┌─────▼────────────────────────▼──────────────────────────▼─────────┐
  │  PostgreSQL  │  Redis  │  RabbitMQ  │  MinIO  │  LanguageTool     │
  └───────────────────────────────────────────────────────────────────┘
```

### Services

| Service | Language | Purpose |
|---------|----------|---------|
| **api-gateway-bff** | TypeScript / NestJS | Single entry point for all external traffic |
| **auth-service** | Go / Chi | Identity, JWT, sessions, profiles, follows |
| **book-service** | Go / Chi | Books, chapters, chunks, lifecycle management |
| **sharing-service** | Go / Chi | Visibility policies, share links |
| **catalog-service** | Go / Chi | Public book discovery, filtering, search |
| **provider-registry** | Go / Chi | BYOK credential storage, provider health, model registry |
| **usage-billing** | Go / Chi | Token metering, quota enforcement, cost estimation |
| **glossary-service** | Go / Chi | Glossary entities, dynamic attributes, evidence linking |
| **statistics-service** | Go / Chi | Analytics, usage metrics, dashboard data |
| **notification-service** | Go / Chi | Notifications, email delivery |
| **translation-service** | Python / FastAPI | Batch translation pipeline with async workers |
| **chat-service** | Python / FastAPI | Streaming AI chat, thinking mode, multi-provider SSE |
| **video-gen-service** | Python / FastAPI | Text-to-video generation |
| **worker-infra** | Go | Outbox relay, cleanup, import processing, Pandoc conversion |

### Tech Stack

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
| **Database** | PostgreSQL 18 | Per-service schemas, JSONB flexible storage |
| **Cache** | Redis 7 | Sessions, caching, rate limiting |
| **Message Queue** | RabbitMQ 3.13 | Translation job distribution, async tasks |
| **Object Storage** | MinIO | S3-compatible — media, exports, uploads |
| **Grammar** | LanguageTool | Spell check, grammar analysis |
| **Doc Conversion** | Pandoc Server | HTML, Markdown, DOCX format conversion |
| **Email (dev)** | Mailhog | SMTP sandbox |

### Design Principles

- **Contract-first** — OpenAPI specs frozen before any frontend work begins
- **Gateway invariant** — all external traffic enters through the NestJS BFF
- **Provider gateway** — no direct AI SDK calls; everything through the adapter layer
- **Language rule** — Go for domain services, Python for AI/LLM services, TypeScript for gateway
- **Per-service databases** — each microservice owns its own PostgreSQL schema
- **Event-driven** — outbox pattern with Redis Streams for reliable async processing

---

## The RAG Pipeline

This is what makes LoreWeave different. Your worldbuilding feeds your AI:

```
  You write a chapter
        │
        ▼
  ┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
  │  Glossary    │────▶│  Evidence     │────▶│  Entity Graph    │
  │  Extraction  │     │  Linking      │     │  (Knowledge DB)  │
  └─────────────┘     └──────────────┘     └────────┬────────┘
                                                     │
        ┌────────────────────────────────────────────┘
        ▼
  ┌──────────────┐     ┌──────────────┐     ┌─────────────────┐
  │  Vector Index │────▶│  RAG Context  │────▶│  AI Chat /       │
  │  (HNSW)      │     │  Assembly     │     │  Continuation    │
  └──────────────┘     └──────────────┘     └─────────────────┘
```

Every character trait, location detail, and plot event you define becomes context the AI can draw on. The more you worldbuild, the more canon-aware your AI collaborator becomes — catching contradictions, maintaining voice consistency, and suggesting plot developments grounded in *your* story's logic.

---

## Quick Start

### Docker (recommended)
```bash
cd infra
docker compose up --build
```
Access the UI at [http://localhost:5173](http://localhost:5173)

### Manual / Hybrid
1. **Infra**: `cd infra && docker compose up -d postgres minio redis mailhog`
2. **Services**: Start individual services (see each service's README)
3. **Frontend**: `cd frontend && npm install && npm run dev`

---

## AI Models (BYOK)

LoreWeave is model-agnostic. Connect any provider:

| Provider | Setup | Dynamic Model Fetch |
|----------|-------|-------------------|
| **OpenAI** | API key | 110+ models auto-discovered |
| **Anthropic** | API key | 8+ models with rich capabilities |
| **LM Studio** | Local URL | 58+ models with context length, type detection |
| **Ollama** | Local URL | Local models auto-listed |
| **Custom** | Any OpenAI-compatible endpoint | Dynamic fetch supported |

### Recommended Models

| Use Case | Cloud | Self-Hosted |
|----------|-------|-------------|
| Novel writing | GPT-5, Claude Sonnet 4.6 | Qwen3-32B, Llama 3 70B |
| Translation | Claude Opus 4.6, GPT-4.1 | Qwen3-14B |
| Quick tasks | GPT-5-nano, Claude Haiku 4.5 | Qwen3-1.7B, Gemma 3 4B |

---

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| **Phase 1** | Platform Core — Auth, Books, Sharing, Providers, Translation, Glossary | Done |
| **Phase 2** | Workflow & RAG — Event streams, knowledge graph, vector indexing | In Progress |
| **Phase 3** | Knowledge Services — Wiki builder, Q&A extraction, timeline | Planned |
| **Phase 4** | Continuation & Canon Safety — AI story continuation grounded in canon | Planned |
| **Phase 5** | Hardening & Scale — Performance, multi-tenancy, cloud deployment | Planned |

**Planned services:** RAG Index (vector search), Story Wiki (auto-generated wikis), QA Extraction (grounded Q&A), Continuation (canon-aware drafting), Orchestrator (LangGraph multi-agent workflows).

**Planned infrastructure:** Neo4j for native vector search + knowledge graph, PostgreSQL 18 advanced features (JSON_TABLE, virtual columns, UUIDv7).

---

## Documentation

- `docs/03_planning/` — Module planning docs, execution packs, acceptance criteria
- `docs/sessions/` — Session logs and handoff docs
- `design-drafts/` — 30+ interactive HTML design mockups
- `contracts/api/` — OpenAPI specs per service domain

---

## Contributing

LoreWeave is for everyone. Developers, artists, translators, and authors welcome.

- **License**: [MIT](LICENSE)
- **Architecture**: Contract-first microservices
- **Docs**: See [docs/](docs/) folder

---

*Built for the dreamer who has a world in their head and just needs a partner to get it on paper.*
