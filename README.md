# LoreWeave

**Write novels. Play inside them. An AI-native platform where your lore becomes a living, LLM-driven world.**

LoreWeave is a self-hosted AI-native platform with two connected ambitions — write the books, then step inside them:

🎮 **Living Worlds** — *The headline long-term vision.* A text-based LLM MMO RPG where each book you write becomes a shared persistent reality: NPCs driven by LLMs and grounded in your lore, a narrator that respects your canon, scenes other players can join. You (or readers you invite) step in as a player character. *Phase 6+ — [design locked](docs/03_planning/LLM_MMO_RPG/), implementation gated on MVP maturity.*

✍️ **AI-native novel writing** — *The MVP, shipping today.* Co-author multilingual novels with an AI-first, human-in-the-loop system where translation, worldbuilding, continuity tracking, and style coaching are foundational, not features. The richer your worldbuilding, the smarter your AI collaborator — ask *"what would Kael do here?"* and the AI knows Kael's personality, backstory, and last scene appearance.

Both pillars share **one foundation: your knowledge graph, your glossary, your book canon.** Write once, play twice — the same lore that grounds your novel will animate your world.

Built for **anyone with a story to tell — or a world to step into.** BYOK (Bring Your Own Key) — works with OpenAI, Anthropic, LM Studio, Ollama, and any OpenAI-compatible provider. Self-hosted. Your keys, your data, your stories, your worlds.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Open Source](https://img.shields.io/badge/Open%20Source-Community-blue.svg)](https://github.com/)

---

## Why LoreWeave?

Most platforms treat AI as a sidebar autocomplete, and treat "writing" and "play" as separate products. LoreWeave flips both:

- **AI-first architecture** — every feature assumes an AI collaborator is in the room
- **Human-in-the-loop** — AI drafts, suggests, translates, and checks continuity; you decide what stays
- **RAG-powered worldbuilding** — your lore database *is* the AI's context today, and tomorrow it will be the LLM's mind when your NPCs speak
- **One canon, two products** — the same knowledge graph that grounds your novel will animate your world. Write, then play — no re-engineering
- **Multilingual from day one** — write in one language, translate to many, keep glossary terms consistent across all of them
- **No vendor lock-in** — bring keys from any provider, run local models, switch anytime

This isn't a tool for writers who already know the craft. It's for **the dreamer who has a world in their head — and wants to get it on paper, then step inside it.**

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

### Knowledge Graph & Wiki (Phase 2 — Complete)
- Two-layer model: glossary (authored SSOT) + knowledge-service (fuzzy/semantic layer) anchored via `glossary_entity_id`
- Automated entity extraction from chapters into a structured knowledge graph
- **Postgres SSOT + Neo4j** derived graph via outbox → publisher → projections pipeline
- 3-pass hierarchical extraction: structural decompose → per-op cache-wrap → hierarchical reduce + per-level summaries
- Relation merge with conflict resolution (MAX confidence, UNION evidence, earliest `valid_from`)
- Wiki articles + revisions + suggestions hosted inside glossary-service (not a separate service)
- Pattern validated by Microsoft GraphRAG (arXiv:2404.16130) and HippoRAG (arXiv:2405.14831)
- **Baseline locked: F1 = 0.869** (95% CI [0.842, 0.895]) via independent-judge evaluation across 9 golden chapters
- Merge-candidate detection with coreference resolution and UI review surface

### Composition & Canon-Aware Co-Writing (Phase 3 — Live)
- **Lore-grounded co-writer**: RAG-packs canon context (knowledge graph + glossary + prose) into the LLM's window
- Editorial lifecycle with canon model — draft → review → published, spoiler-safe context assembly
- Advisory prose critic (`judge_prose`) flags canon inconsistencies before you accept a suggestion
- Dual-order (narrative + canonical) provenance tracking for every generated block

### Lore Enrichment (Phase 3 — Live)
- AI-driven enrichment pipeline: gap detection, structured lore generation, canon verification
- Retrieval-grounded generation anchored to the knowledge graph — suggestions grounded in what you already wrote
- Eval loop with structural completeness and LLM-as-judge scoring

### Translation Pipeline V3 (Phase 2 → 3)
- **Multi-agent pipeline**: rule-tier verifier (glossary names, script leak, number preservation, sentence-count, loops) + LLM semantic verifier
- **Knowledge-grounded context**: character relationships + honorifics brief injected per chapter via wiki-neighborhood
- **Cross-chapter memo**: established name records carry forward across chapters (cold-start consistency)
- **Semantic chunking**: dialogue runs and scene blocks tend to land in a single LLM call
- **Quality gate**: "needs review" badge + publish hold for verifier-flagged versions
- **Glossary staleness**: Redis-Streams consumer flags translations stale when glossary entities change

### Production Eval & Feedback Flywheel (Phase 3 — Live)
- `learning-service` — persistent quality scoring, eval runs, gold labels from corrections
- Online eval on every production extraction (structural completeness + optional LLM-as-judge precision)
- Chat feedback (thumbs up/down, implicit regenerate-as-negative) wired into the quality pipeline
- Judge calibration (Cohen's κ, balanced accuracy) with anti-self-reinforcement panel safety

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

Self-hosted Docker Compose monorepo. **24 application services + infra containers + frontend.** Contract-first API design. Event-driven with the outbox pattern.

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
  │ (9 svcs)   │        │ (4 svcs, incl.    │        │ outbox · jobs · │
  │            │        │  knowledge-svc)   │        │ AI extraction   │
  └─────┬──────┘        └────────┬──────────┘        └────────┬────────┘
        │                        │                            │
  ┌─────▼────────────────────────▼────────────────────────────▼────────┐
  │ Postgres 18 │ Neo4j │ Redis │ RabbitMQ │ MinIO │ LanguageTool │ …  │
  └────────────────────────────────────────────────────────────────────┘
```

### Services

| Service | Language | Purpose |
|---------|----------|---------|
| **api-gateway-bff** | TypeScript / NestJS | Single entry point for all external traffic |
| **auth-service** | Go / Chi | Identity, JWT, sessions, profiles, follows |
| **book-service** | Go / Chi | Books, chapters, chunks, lifecycle |
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
| **composition-service** | Python / FastAPI | Canon-aware co-writer — RAG context packing, LLM prose generation, advisory critic, editorial lifecycle |
| **lore-enrichment-service** | Python / FastAPI | AI-driven lore enrichment — gap detection, retrieval-grounded generation, canon verification |
| **learning-service** | Python / FastAPI | Production eval + feedback flywheel — quality scores, eval runs, gold labels, online judge |
| **video-gen-service** | Python / FastAPI | Media generation BFF; ComfyUI workloads live in sibling repo **local-image-generator-service** (SD 1.5 / SDXL / Illustrious / Flux 1–2 / Qwen Image / Wan / LTX Video + custom game-asset, object-sheet, and animation pipelines) |
| **worker-infra** | Go | Outbox relay, cleanup, import processing, Pandoc conversion |
| **worker-ai** | Python | AI-driven async tasks (entity extraction, summary regen, embedding jobs) |
| **game-server** | TypeScript / Node.js + Colyseus | Living Worlds (Phase 6) — real-time multiplayer rooms, zone/combat/chat rooms |
| **tilemap-service** | Rust | Living Worlds (Phase 6+) — tile/spatial layer |
| **travel-service** | Rust | Living Worlds (Phase 6+) — movement/travel mechanics |
| **world-service** | Rust | Living Worlds (Phase 6+) — world state, reality model |

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
| **Database** | PostgreSQL 18 + pgvector | Per-service schemas, JSONB storage, vector embeddings (HNSW) |
| **Knowledge Graph** | Neo4j | Derived graph for entity relations, memory, narrative queries |
| **Cache / Streams** | Redis 7 | Sessions, caching, rate limiting, event streams (outbox fan-out) |
| **Message Queue** | RabbitMQ 3.13 | Translation + heavy AI job distribution |
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
  ┌──────────────┐    ┌──────────────┐    ┌─────────────────────┐
  │  Glossary    │───▶│  Evidence     │───▶│  Knowledge Graph     │
  │  Extraction  │    │  Linking      │    │  (Postgres + Neo4j)  │
  └──────────────┘    └──────────────┘    └─────────┬───────────┘
                                                     │
        ┌────────────────────────────────────────────┘
        ▼
  ┌──────────────┐    ┌──────────────┐    ┌─────────────────────┐
  │  pgvector    │───▶│  RAG Context  │───▶│  AI Chat · Continu-  │
  │  HNSW index  │    │  Assembly     │    │  ation · NPC Mind*   │
  └──────────────┘    └──────────────┘    └─────────────────────┘
                                                       *Phase 6+
```

Every character trait, location detail, and plot event you define becomes context the AI can draw on. The more you worldbuild, the more canon-aware your AI collaborator becomes — catching contradictions, maintaining voice consistency, and suggesting plot developments grounded in *your* story's logic.

**Today** the pipeline grounds chat answers, translation terminology, and canon-safe continuations. **Tomorrow** the same pipeline becomes the LLM's memory when your NPCs speak, the narrator's canon when a scene runs, and the continuity layer of a Living World.

---

## 🎮 Living Worlds — The Future of LoreWeave

> *Your book is not a reality — it is the origin of many.*
>
> *You wrote a novel where the hero betrayed the merchant guild in chapter 12. A month later, one reader joins **R_α** and finds the guild fractured, still whispering about the traitor. Another joins **R_β** — a reality where the betrayal never happened, and the guild captain invites her to dinner. A third player forks a new reality at event 49 to explore "what if the hero had killed the guildmaster instead?" All three are real. All three persist. The NPCs remember only what happened in their own timeline.*

**Living Worlds** is the moment your knowledge graph stops being a reference and starts being a **multiverse**. The characters, locations, and rules that lived as glossary entries become LLM-driven inhabitants of **shared persistent realities**. A narrator grounded in your canon runs the scene. Other players can step in — or fork off and build their own.

This is not a chatbot with a roleplay prompt. It is a text-based **LLM MMO RPG** with a full multiverse model inspired by SCP Foundation canon structure — designed from the ground up with the hard problems taken seriously.

### 🌌 The Multiverse — One Book, Infinite Realities

The defining design decision of Living Worlds:

- **A book is NOT a reality.** It is canon source material — characters, axioms, the lore's physics. The *origin point* (khởi nguyên), not a universe.
- **A book has MANY realities.** Each one is a complete, independent timeline. **None is "main."** They are peer universes that happen to share an origin — like SCP's alternate canons, not like a canonical server and its copies.
- **Realities can fork from other realities.** A reality's history can be **inherited** (snapshot fork at a specific event) — so a reality can be a child of another, a grandchild, and so on. Forking is a first-class gameplay mechanic: capacity overflow, narrative what-ifs, private sessions.
- **Logic can diverge between peers.** Alice alive in R_α, dead in R_β, a pirate queen in R_γ — all valid. The book defines what is *possible*; each reality defines what *happened*.

```
                    📖 BOOK  (canon source — axioms + seeded facts)
                              │
                              │ seeds each reality's initial state
      ┌───────────┬───────────┼───────────┬───────────┐
      ▼           ▼           ▼           ▼           ▼
    R_α          R_β          R_γ         R_δ         R_ε
  (alive)    (dead@T50)     (queen)    (pirate)  (librarian)
                 │                        │
                 ▼                        ▼
              R_β.1                    R_δ.1
         (snapshot fork              (what-if fork
          @event 48)                  @event 120)
```

### 📜 Four-Layer Canon — What Drifts, What Doesn't

Not every fact drifts the same way. The model distinguishes four layers:

| Layer | Where it lives | Drifts? | Example |
|---|---|---|---|
| **L1 — Axiomatic** | Author-locked in book | **Never, any reality** | "Magic exists" · "Elves are a species" |
| **L2 — Seeded canon** | Book's initial state | Per-reality (overridable) | "Alice is a princess" — may become "blacksmith" in R_γ |
| **L3 — Reality-local** | Events that happened *here* | Immutable within reality | "In R_β, Alice died at T=50" |
| **L4 — Flexible state** | Runtime / LLM drift | Freely within reality | NPC's current mood |

**Canonization — the reverse direction.** An exciting L3 event from a player's reality can be promoted back to L2 seeded canon, under author review. *A reader's emergent narrative can become part of the book.* That is the real long-term vision: your audience contributes back to your canon, and you decide what sticks.

### 🧠 The Experience

- **NPCs driven by LLMs, grounded in your lore.** They remember the scenes you wrote, the scenes players just played, and each other — per-reality, not globally.
- **The narrator respects canon.** World rules live in a per-reality rule engine; the narrator cannot overturn your book's physics without your say-so.
- **You are a player character, not just the author.** Create a PC, join a session, roleplay inside the lore you built — alone, with friends, or in a shared persistent world with strangers.
- **Readers become players.** Invite anyone who loved your book to step into it — into whichever reality they prefer, or fork their own.
- **Fork anywhere, anytime.** "What if Alice never died?" → fork R_β at event 49, diverge into R_β.1, play out your version. No re-engineering. No permission needed (V1 default).

### The Architecture

| Layer | What it does |
|---|---|
| **Multiverse model** | Peer realities (no privileged root), book-as-origin seeding, parent→child snapshot fork with inherited event chain, 4-layer canon (L1 axiomatic → L4 runtime) |
| **Storage** | Full event sourcing, DB-per-reality, NPC memory split into core + per-pair aggregates for bounded cost |
| **Player Characters** | Identity layering (*User / PC / Session*), lifecycle, social mechanics, PC → NPC conversion |
| **Services (planned)** | `world-service` · `roleplay-service` · `publisher` · `meta-worker` · `event-handler` · `migration-orchestrator` · `admin-cli` |

### Scope Tiers — Staged De-Risking

| Version | Scope | Why this order |
|---|---|---|
| **V1** — Solo RP | One player, one reality, core loop | Prove retrieval quality + cost-per-user-hour without concurrency hazards |
| **V2** — Coop Scene | Multiple PCs in the same session, shared NPCs | Prove turn arbitration + shared NPC memory |
| **V3** — Full MMO | Shared persistent worlds, realities that live between sessions | Only attempted after V1/V2 data validates the economics |

### The Design Dossier

Not a sketch — a locked design track. The complete work lives in [`docs/03_planning/LLM_MMO_RPG/`](docs/03_planning/LLM_MMO_RPG/):

- **179 features** cataloged across 12 categories — 92 Designed, 39 Partial, 43 Deferred, 3 Open (all gated on prototype data)
- **13 storage risks** identified and resolved across §12A–§12L (event volume, projection rebuild, schema evolution, fleet ops, cross-instance isolation, publisher failure, NPC memory scaling, safe reality closure, and more)
- **~150 individual decisions** locked in [`decisions/locked_decisions.md`](docs/03_planning/LLM_MMO_RPG/decisions/locked_decisions.md) with reasoning preserved
- **12 deferred big features** (DF1–DF13) tracked in a registry — each promotes to its own implementation doc when work begins
- **2 governance policies** (`CROSS_INSTANCE_DATA_ACCESS_POLICY`, `ADMIN_ACTION_POLICY`) already codified

### Gated on Quality, Not Calendar

Implementation is gated on **V1 novel-platform maturity** + prototype-level data on:

1. **LLM cost per user-hour** — can a session be economically viable?
2. **Retrieval quality on real books** — do the NPCs actually stay in character?
3. **IP / canon ownership rules** — what belongs to the author vs. the platform vs. the players?

No calendar milestone. When the data is there, the design is ready. **The novel platform ships first; the game builds on the same substrate — glossary, knowledge graph, book canon — without re-engineering.**

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
| **Phase 1** | Platform Core — Auth, Books, Sharing, Providers, Translation, Glossary | ✅ Done |
| **Phase 2** | Knowledge Graph & RAG — entity extraction, Postgres+Neo4j, hierarchical summaries, eval baseline | ✅ Done |
| **Phase 3** | Intelligence Layer — Canon co-writing, Lore enrichment, Translation V3, Production eval flywheel | 🔄 In Progress |
| **Phase 4** | Continuation & Canon Safety — AI story continuation grounded in canon | Planned |
| **Phase 5** | Hardening & Scale — Performance, multi-tenancy, cloud deployment | Planned |
| **Phase 6+** | **Living Worlds** — LLM-driven NPCs, shared persistent realities, player characters, multiverse model ([design track](docs/03_planning/LLM_MMO_RPG/)) | Foundation building |

**Phase 2 complete:** 3-pass hierarchical extraction shipped. Independent-judge eval baseline locked at **F1 = 0.869** (95% CI [0.842, 0.895]) across 9 golden chapters. Merge-candidate detection + wiki stub generation live.

**Phase 3 (active):** `composition-service` and `lore-enrichment-service` live. Translation Pipeline V3 (multi-agent + knowledge-grounded) M0–M5 shipped, M6 (human-fix flywheel) remaining. Production eval flywheel Q0–Q4 live (`learning-service`). Translation M6 + eval flywheel Q5+ are the current active tracks.

**Phase 6 foundation:** `game-server` V0 live (Node.js + Colyseus, WS path validation). `world-service`, `tilemap-service`, `travel-service` (Rust, skeletons live). Design track locked at 179 features across 12 categories — see [LLM_MMO_RPG/](docs/03_planning/LLM_MMO_RPG/).

---

## Documentation

- `docs/03_planning/` — Module planning docs, execution packs, acceptance criteria
- `docs/sessions/` — Session logs and handoff docs
- `design-drafts/` — 30+ interactive HTML design mockups
- `contracts/api/` — OpenAPI specs per service domain

---

## Contributing

LoreWeave is for everyone. Developers, artists, translators, and authors welcome.

- **License**: [AGPL-3.0-or-later](LICENSE)
- **Architecture**: Contract-first microservices
- **Docs**: See [docs/](docs/) folder

---

*Built for the dreamer who has a world in their head — and wants to get it on paper, then step inside.*
