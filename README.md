# LoreWeave

**The AI co-author that knows your world.**

Write a character once. LoreWeave remembers them — their personality, their history, their relationships — across every chapter, every translation, every draft.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Open Source](https://img.shields.io/badge/Open%20Source-Community-blue.svg)](https://github.com/)

---

## The frustration every writer knows

You've spent hours building a world. Now you open your AI assistant — and spend the next twenty minutes re-explaining it. Your protagonist's name, her backstory, the magic system, the faction that fell in chapter 2. You paste in notes. The AI still gets things wrong.

Or you finish a novel and run it through translation. Chapter 1: "Kael". Chapter 7: "Kyle". Your invented term for magic comes back as a dictionary definition. The gender of a side character flips halfway through. The mental glossary you've maintained for months didn't survive the pipeline.

And if you write in more than one language, you're already juggling: a writing tool, a translation service, a worldbuilding wiki, a glossary spreadsheet, and a chat window with an AI that forgets everything the moment you close the tab.

**These aren't workflow problems. They're structural problems. LoreWeave fixes the structure.**

---

## How LoreWeave is different

### Your lore becomes the AI's long-term memory

Every chapter you write, LoreWeave automatically extracts every character, location, event, and relationship into a knowledge graph. From that point on — every AI chat, every translation, every co-writing suggestion — is grounded in what you actually wrote. Ask *"what would Kael do here?"* and the AI knows Kael's arc, his last scene, his allegiances. Not because you just pasted in the context. Because it read your book.

### Translation that respects your invented world

Standard AI translators treat your novel like a news article. LoreWeave's translation pipeline knows your glossary, knows your character names, and checks its own work: a multi-agent verifier catches name drift, dropped sentences, pronoun flips, and script contamination before results ever reach you. Your invented terminology survives the language crossing intact — in every target language, every chapter.

### A co-writer that can't contradict your canon

The composition engine assembles your published chapters, character relationships, and lore context before drafting a single word. An advisory critic cross-checks every suggestion against your established canon. You still decide what goes in — but the AI can no longer confidently write things that never happened in your story.

### A workspace that holds your whole novel at once

Writing a long novel is not a text-editor problem. You need the chapter, the outline, the character who appeared 40 chapters ago, the rule you set for your magic system, and the AI — all at the same time, without losing your place.

The **Writing Studio** is a dockable workspace built for exactly that. Manuscript, plan, story bible, search, and quality live on one rail; every panel can be split, stacked, floated, or **popped out into its own window** — put the canon on your second monitor and write on your first. A command palette (`⌘P`) jumps to any chapter, scene, or arc. The AI co-writer is a panel like any other, so it sees the same book you do — and the status bar keeps your live token spend in view while you work.

### One platform — write, translate, worldbuild, and collaborate, all connected

The knowledge graph that grounds your AI chat also grounds your translations. The glossary you maintain for worldbuilding also enforces consistency in every translated chapter. The lore you extract today becomes the AI's context tomorrow. Nothing stays siloed — every part of LoreWeave feeds every other part.

### Your keys, your data, your infrastructure

LoreWeave is self-hosted and model-agnostic. Bring your own API keys from OpenAI, Anthropic, or any provider. Run entirely on local models via LM Studio or Ollama. Your manuscripts live on your infrastructure — not on a subscription service with its own retention policy.

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
- Rich text editor with AI-assist mode and Classic mode
- Paragraph-level editing with revision history and version comparison
- Chapter revision compare with LCS diff view (CJK-aware)
- Grammar and spell checking
- Media blocks: images, video, code

### AI Chat
- Chat with any model, grounded in your book's lore
- Thinking mode — real-time reasoning display (Qwen3, DeepSeek-R1, and compatible models)
- Message branching — edits create branches, never overwrite history
- Context attachment: bring specific chapters, characters, or glossary entries into any conversation
- Prompt template library, system prompt presets, response format shortcuts
- Token usage and latency metrics per message
- Thumbs up/down feedback — your preferences improve the system over time

### Translation
- Batch translate chapters across multiple languages simultaneously
- Multi-agent quality pipeline: rule-tier verifier (name consistency, sentence count, script integrity) + LLM semantic verifier
- Knowledge-grounded context: character bios, pronouns, and relationship briefs injected per chapter
- Cross-chapter name continuity: established translations carry forward automatically
- Glossary-staleness detection: translations are flagged when your lore changes
- "Needs review" badge and publish gate for flagged chapters — you stay in control

### Worldbuilding & Lore
- Entity library with fully customizable kinds (Character, Location, Item, Organization — or anything you define)
- Dynamic attributes — add any field, any type
- Evidence linking — tie every lore entry to the exact paragraph that establishes it
- Automatic entity and relationship extraction from chapters

### The Writing Studio
- Dockable, pop-out-able panel workspace — arrange the editor, canon, plan, and AI panels the way you work
- **PlanForge** — plan a novel's structure from your premise, in rules mode (deterministic) or LLM mode
- **Plan Hub** — a lane-based plan canvas for arcs and beats
- **Steering rules** — per-book author rules injected into every book-scoped AI turn ("story-bible-as-steering")
- Motif and arc libraries with conformance checking against what you actually wrote

### AI Co-Writing
- Lore-grounded prose suggestions anchored to your published canon
- Spoiler-safe context assembly — the AI sees only what's relevant to the current scene
- Advisory prose critic flags potential canon contradictions before you accept a suggestion
- Auto Reasoning Mode: thinking-capable models switch in automatically when it helps
- **Auto-Draft Factory** — run a whole drafting campaign across chapters with a budget ceiling and per-chapter progress

### Worlds & Automation
- **Worlds** — group books under one shared canon container, with an auto-provisioned world bible
- **Agent extensibility** — register skills, plugins, and MCP servers; bind which ones auto-seed per mode (ask / write / plan)
- **Workflow rack** — saved multi-step agent recipes ("set up my world", "check my story for contradictions")
- **Public MCP gateway** — let external AI agents reach your lore over MCP, with OAuth consent, scope limits, and spend caps

### Lore Enrichment
- AI-powered gap detection in your worldbuilding
- Structured lore proposals generated from what you've already written — not invented from scratch
- Canon verification before anything reaches your glossary

### Wiki & Knowledge Graph
- Auto-generated wiki articles per entity, with revision history and community suggestions
- Two-layer model: your authored glossary is always the source of truth; the AI layer adds semantic depth
- Continuous quality evaluation — the system measures its own extraction accuracy over time

### Community
- Public catalog with genre, language, and search filters
- Sharing controls: public, unlisted (link-only), private
- User profiles, follows, favorites

### Platform
- BYOK: OpenAI, Anthropic, LM Studio, Ollama, any OpenAI-compatible endpoint
- Every LLM, embedding, rerank, image, audio, and STT call routes through one provider gateway — no service holds a provider key
- Dynamic model discovery (110+ OpenAI models, 58+ LM Studio models auto-detected)
- AI usage monitoring — cost estimates, token breakdowns per model and per operation
- Unified job control plane — every async job (translation, extraction, drafting, media) in one queue view with live progress
- Multilingual UI — **18 languages**
- Recycle bin with restore

---

## Quick Start

### Docker (recommended)
```bash
cd infra
docker compose up --build
```
Access the UI at **[http://localhost:5174](http://localhost:5174)** · gateway on `:3123` · admin CMS on `:5175`.

> `:5174` serves the **baked** nginx production build. Rebuild the image to see frontend changes — a host `vite dev` can shadow it.

### Manual / Hybrid
1. **Infra**: `cd infra && docker compose up -d postgres minio redis mailhog`
2. **Services**: Start individual services (see each service's README)
3. **Frontend**: `cd frontend && npm install && npm run dev`

`docker compose up` starts the **novel platform**. The Living Worlds reality-ops tier (14 SRE services, the Rust world/travel services, and the meta Patroni cluster) is not in the default stack.

---

## AI Models (BYOK)

LoreWeave is model-agnostic. Connect any provider:

| Provider | Setup | Dynamic Model Fetch |
|----------|-------|-------------------|
| **OpenAI** | API key | 110+ models auto-discovered |
| **Anthropic** | API key | 8+ models |
| **LM Studio** | Local URL | 58+ models with context length and type detection |
| **Ollama** | Local URL | Local models auto-listed |
| **Custom** | Any OpenAI-compatible endpoint | Dynamic fetch supported |

### Recommended Models

| Use Case | Cloud | Self-Hosted |
|----------|-------|-------------|
| Novel writing | GPT-5, Claude Sonnet 4.6 | Qwen3-32B, Llama 3 70B |
| Translation | Claude Opus 4.6, GPT-4.1 | Qwen3-14B |
| Quick tasks | GPT-5-nano, Claude Haiku 4.5 | Qwen3-1.7B, Gemma 3 4B |

---

## 🎮 Living Worlds — The Future of LoreWeave

> *Your book is not a reality — it is the origin of many.*
>
> *You wrote a novel where the hero betrayed the merchant guild in chapter 12. A month later, one reader joins **R_α** and finds the guild fractured, still whispering about the traitor. Another joins **R_β** — a reality where the betrayal never happened, and the guild captain invites her to dinner. A third player forks a new reality at event 49 to explore "what if the hero had killed the guildmaster instead?" All three are real. All three persist. The NPCs remember only what happened in their own timeline.*

**Living Worlds** is the moment your knowledge graph stops being a reference and starts being a **multiverse**. The characters, locations, and rules that lived as glossary entries become LLM-driven inhabitants of shared persistent realities. A narrator grounded in your canon runs the scene. Other players can step in — or fork off and build their own.

This is not a chatbot with a roleplay prompt. It is a text-based **LLM MMO RPG** with a full multiverse model — designed from the ground up with the hard problems taken seriously.

### 🌌 The Multiverse — One Book, Infinite Realities

- **A book is NOT a reality.** It is canon source material — characters, axioms, the lore's physics. The *origin point*, not a universe.
- **A book has MANY realities.** Each one is a complete, independent timeline. None is "main." They are peer universes that share an origin — like SCP's alternate canons.
- **Realities can fork from other realities.** Fork at any event — capacity overflow, narrative what-ifs, private sessions. Forking is a first-class mechanic.
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

| Layer | Where it lives | Drifts? | Example |
|---|---|---|---|
| **L1 — Axiomatic** | Author-locked in book | **Never** | "Magic exists" · "Elves are a species" |
| **L2 — Seeded canon** | Book's initial state | Per-reality (overridable) | "Alice is a princess" — may become "blacksmith" in R_γ |
| **L3 — Reality-local** | Events that happened *here* | Immutable within reality | "In R_β, Alice died at T=50" |
| **L4 — Flexible state** | Runtime / LLM drift | Freely within reality | NPC's current mood |

**Canonization — the reverse direction.** An exciting moment from a player's reality can be promoted back to seeded canon, under author review. *A reader's emergent narrative can become part of the book.* Your audience contributes back to your canon, and you decide what sticks.

### 🧠 The Experience

- **NPCs driven by LLMs, grounded in your lore.** They remember the scenes you wrote, the scenes players just played, and each other — per-reality, not globally.
- **The narrator respects canon.** World rules live in a per-reality rule engine; the narrator cannot overturn your book's physics without your say-so.
- **You are a player character, not just the author.** Create a character, join a session, roleplay inside the lore you built — alone, with friends, or in a shared persistent world with strangers.
- **Readers become players.** Invite anyone who loved your book to step into it — into whichever reality they prefer, or fork their own.
- **Fork anywhere, anytime.** "What if Alice never died?" — fork at that event and play out your version.

### Scope — Staged Rollout

| Version | Scope |
|---|---|
| **V1** — Solo RP | One player, one reality, core loop |
| **V2** — Coop Scene | Multiple players in the same session, shared NPCs |
| **V3** — Full MMO | Shared persistent worlds, realities that live between sessions |

### Gated on Quality, Not Calendar

Implementation is gated on novel-platform maturity and prototype data on LLM cost per user-hour, retrieval quality on real books, and IP/canon ownership rules. **The novel platform ships first. The game builds on the same substrate — glossary, knowledge graph, book canon — without re-engineering.**

The complete design lives in [`docs/03_planning/LLM_MMO_RPG/`](docs/03_planning/LLM_MMO_RPG/) — **474 features catalogued** across 12 categories, ~150 decisions locked with reasoning, architecture fully specified. Start at the [feature catalog](docs/03_planning/LLM_MMO_RPG/catalog/_index.md) or the [feature-design tree](docs/03_planning/LLM_MMO_RPG/features/_index.md).

---

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| **Phase 1** | Platform Core — writing, translation, glossary, sharing | ✅ Done |
| **Phase 2** | Knowledge Graph & RAG — automatic extraction, semantic search | ✅ Done |
| **Phase 3** | Intelligence Layer — canon co-writing, lore enrichment, translation quality | 🔄 In Progress |
| **Phase 4** | Continuation & Canon Safety — the Writing Studio, PlanForge, canon rules, Auto-Draft Factory | 🔄 In Progress |
| **Phase 5** | Hardening & Scale — performance, multi-tenancy, cloud deployment | Planned |
| **Phase 6+** | **Living Worlds** — LLM-driven NPCs, shared persistent realities, the MMO | Foundation building |

---

## Documentation

- [Architecture & Services](docs/ARCHITECTURE.md) — all 47 services, tech stack, infrastructure, ports
- [Data Architecture](docs/DATA_ARCHITECTURE.md) — SSOT layers, the 22 databases, event flows
- [Frontend Feature Index](docs/FEATURE_INDEX.md) — every UI feature → route → backing service
- [Standards index](docs/standards/README.md) — every cross-cutting rule, where it lives, how it's enforced
- [Planning docs](docs/03_planning/) — module-level design and execution packs
- [API contracts](contracts/api/) — OpenAPI specs per service
- [Design mockups](design-drafts/) — 116 interactive HTML mockups

---

## Contributing

LoreWeave is open to everyone — developers, writers, translators, and artists.

- **License**: [AGPL-3.0-or-later](LICENSE)
- **Issues**: bug reports, feature requests, and discussions welcome

---

*Built for the dreamer who has a world in their head — and wants to get it on paper, then step inside.*
