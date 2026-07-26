# LoreWeave — Frontend Feature Index

> **Purpose:** The centralized map of `frontend/src/features/*` — every feature folder, where it mounts, what it does, and which backing service it talks to.
> **Audience:** Developers and AI agents who need to find the code behind a screen (or the screen behind a service).
> **Last updated:** 2026-07-17
>
> **Companion docs:** [`ARCHITECTURE.md`](ARCHITECTURE.md) (services + tech stack) · [`DATA_ARCHITECTURE.md`](DATA_ARCHITECTURE.md) (where the data lives) · [`03_planning/LLM_MMO_RPG/features/_index.md`](03_planning/LLM_MMO_RPG/features/_index.md) (the **design-track** feature folders — a different tree, don't confuse them)

**41 feature folders** as of 2026-07-17. Routes are from [`frontend/src/App.tsx`](../frontend/src/App.tsx); service targets are the **actual gateway proxy targets** from `services/api-gateway-bff/src/gateway-setup.ts`, not inferred from the path name.

---

## The two "features" trees — read this first

This repo has two unrelated things called *features*. They are not the same tree and neither indexes the other:

| Tree | What it is | Index |
|---|---|---|
| `frontend/src/features/*` | **Shipped UI code** — 41 folders | **this document** |
| `docs/03_planning/LLM_MMO_RPG/features/*` | **Design docs** for the unbuilt MMO track — 34 folders | [`features/_index.md`](03_planning/LLM_MMO_RPG/features/_index.md) |

---

## Per-feature structure (the MVC convention)

Every feature folder follows the same internal shape (see [`CLAUDE.md`](../CLAUDE.md)):

```
features/<name>/
  hooks/        ← "controllers" — own logic + state, no JSX
  context/      ← "services" — shared state across components
  components/   ← "views" — render only, receive data from context/props
  api.ts        ← API layer
  types.ts      ← TypeScript types
```

---

## Feature map

`Route` = the URL that reaches it. **`(embedded)`** = no route of its own; it mounts inside another feature (the consumer is named). Sizes are `.ts`/`.tsx` file counts — a rough weight, not a quality signal.

### Core writing & content

| Feature | Route | Purpose | Backing service |
|---|---|---|---|
| **studio** (330) | `/books/:bookId/studio`, `/studio/popout` | Writing Studio v2 — the dockable panel workspace (Dockview). Hosts most authoring panels. | knowledge-service + many |
| **composition** (358) | `/composition/popout`, studio panels | LOOM co-writer — canon-grounded prose generation, arcs, motifs, conformance. | composition-service |
| **books** (28) | `/books`, `/books/:bookId`, `/books/:bookId/chapters/:id/*` | Books, chapters, drafts, revision compare (1-vs-1 LCS diff). | book-service, catalog-service, sharing-service |
| **plan-forge** (29) | studio panel | PlanForge (Studio M5) — the novel-system planner (`rules` / `llm` run modes). | composition-service |
| **plan-hub** (50) | studio panel | Plan Hub v2 — the plan canvas (lane layout, arc shells). Prose never reaches the canvas. | composition-service |
| **steering** (9) | studio panel | Per-book author steering rules ("story-bible-as-steering"). Rendered as a `<steering>` system part on book-scoped turns. | book-service |
| **grammar** (2) | editor plugin | LanguageTool client (spell/grammar). Has a circuit breaker — a 502 disables checking for 60s. | LanguageTool (via frontend nginx) |
| **pdf-import** (10) | (embedded) studio `BookImportPanel`, chapters tab | PDF → book import wizard. | book-service |
| **trash** (4) | `/trash` | Recycle bin — restore/purge. | book-service, glossary-service |

### AI chat & agents

| Feature | Route | Purpose | Backing service |
|---|---|---|---|
| **chat** (176) | `/chat`, `/chat/:sessionId` | Chat V2 — streaming, thinking mode, branching, tools. | chat-service, knowledge-service, agent-registry-service, provider-registry-service |
| **assistant** (60) | `/assistant` | Work Assistant — reuses the chat surface bound to the user's private diary book + assistant knowledge project. Adds provision/consent/end-of-day control plane. | api-gateway-bff (assistant controller), chat-service, knowledge-service |
| **roleplay** (14) | `/roleplay` (`/interview` redirects here) | Roleplay practice — scripted turn loop + `/evaluate` scorecard. | roleplay-service (Rust), chat-service |
| **chat-ai-settings** (14) | settings tab | Chat & AI settings surface. | chat-service |
| **extensions** (36) | `/extensions` | Agent Extensibility Registry — skills, plugins, MCP-server registrations, proposals. | agent-registry-service |
| **workflows** (6) | (embedded) `ExtensionsPage` | The workflow rack — saved multi-step agent recipes ("set up my world"). | agent-registry-service |
| **modeBindings** (6) | (embedded) `ExtensionsPage` | Mode→capability bindings — which workflows/skills auto-seed per mode (ask/write/plan). 3-tier resolved; shows effective value **+ source tier**. | agent-registry-service |

### Knowledge, lore & glossary

| Feature | Route | Purpose | Backing service |
|---|---|---|---|
| **knowledge** (231) | `/knowledge/*` | Knowledge graph — projects, entities, ontology (`/v1/kg`), summaries. | knowledge-service, glossary-service, learning-service |
| **knowledge-temporal** (17) | (embedded) knowledge `EntityDetailPanel` → "Temporal" tab | Time-travel reads (`as_of`) over the KAL surface. Degrades on sparse reads. | **knowledge-gateway** (KAL) |
| **glossary** (78) | `/books/:bookId/glossary` | Glossary entities, kinds, attributes, evidence, confirm-cards. | glossary-service |
| **glossary-translate** (14) | (embedded) `GlossaryEntityList` | Glossary term translation. ⚠️ Routes to **translation-service**, not glossary. | **translation-service** |
| **extraction** (12) | (embedded) glossary / enrichment / pdf-import | Extraction profile + batch wizard. ⚠️ `/v1/extraction` routes to **translation-service**. | translation-service, glossary-service |
| **enrichment** (77) | `/books/:bookId/enrichment` | Lore enrichment — gap detection, proposal review, promote-to-glossary. | lore-enrichment-service |
| **wiki** (30) | `/books/:bookId/wiki`, `/books/:bookId/wiki/:articleId/edit` | Auto-generated wiki articles + revisions. The wiki lives in **glossary-service**, not a separate service. | glossary-service |
| **raw-search** (13) | `/books/:bookId/search` | Raw / hybrid search (lexical + semantic + RRF fusion + rerank). | book-service, knowledge-service |
| **world** (43) | `/worlds`, `/worlds/:worldId` | World container (prose-less worldbuilding) — groups books, auto-provisions a hidden bible book. | book-service, glossary-service |

### Translation

| Feature | Route | Purpose | Backing service |
|---|---|---|---|
| **translation** (25) | `/books/:bookId/translation`, `/books/:id/chapters/:cid/translations`, `/…/review/:versionId` | Translation matrix, job tracking, review/publish gate. | translation-service |

### Platform & operations

| Feature | Route | Purpose | Backing service |
|---|---|---|---|
| **jobs** (47) | `/jobs`, `/jobs/:service/:jobId` | Unified Jobs GUI + SSE. Mirrors the `loreweave_jobs` SDK contract. | jobs-service |
| **campaigns** (39) | `/campaigns`, `/campaigns/new`, `/campaigns/:id` | Auto-Draft Factory — campaign saga, budget, model matrix, estimates. | campaign-service |
| **usage** (11) | `/usage` | AI usage/cost monitor. USD spend guardrails (token-quota deduction retired). | usage-billing-service |
| **ai-models** (1) | (embedded) `components/model-picker` | Shared user-model data layer for every model picker. | provider-registry-service |
| **settings** (32) | `/settings/:tab` | User settings — account, models, preferences. | auth-service, provider-registry-service |
| **standards** (20) | `/standards/:tab` | System-tier standards browser (genres etc.). | — (see `pages/`) |
| **video-gen** (2) | (embedded) editor `VideoBlockNode` | Video generation blocks. | video-gen-service |

### Identity, social & shell

| Feature | Route | Purpose | Backing service |
|---|---|---|---|
| **home** (15) | `/home`, `/activity`, `/you` | Platform home + activity feed. | api-gateway-bff (home controller), auth-service |
| **onboarding** (8) | `/onboarding`, `/onboarding/new` | Intent-branching first-run fork ("What do you want to do?"). | — |
| **oauth** (4) | `/oauth/consent` | Public-MCP OAuth 2.1 consent screen. | auth-service |
| **profile** (8) | `/users/:userId` | User profiles, follows, favorites. | auth-service, book-service, catalog-service, statistics-service |
| **browse** (2) | `/browse`, `/browse/:bookId` | Public catalog cards + filter bar. | catalog-service |
| **leaderboard** (12) | `/leaderboard` | Rankings. | **statistics-service** |
| **notifications** (9) | `/notifications` | Notification center. `/v1/notifications/stream` is served **locally by the BFF**, not proxied. | notification-service |
| **push** (7) | (embedded) `YouPage` | Web Push subscription client. Owner derived from JWT — the client never sends an id. | notification-service (via gateway proxy) |

---

## Non-obvious routing (things that bite)

The gateway path does **not** always name the owning service. Verified against `gateway-setup.ts`:

| FE path | Actually proxies to | Why it surprises |
|---|---|---|
| `/v1/glossary-translate` | **translation-service** | Reads as a glossary route |
| `/v1/extraction` | **translation-service** | Reads as a knowledge/glossary route |
| `/v1/worlds` | **book-service** | No `world-service` involvement (that's the Rust MMO one) |
| `/v1/leaderboard`, `/v1/stats` | **statistics-service** | — |
| `/v1/kg` **and** `/v1/knowledge` | knowledge-service | The BFF once proxied only `/v1/knowledge`, so every `/v1/kg` call 404'd (D-KG-ONTOLOGY-FE-WIRING) |
| `/v1/kal` | **knowledge-gateway** | The typed KAL boundary, not knowledge-service directly |
| `/v1/notifications/stream` | **served locally by the BFF** | Every other `/v1/notifications/*` path is proxied |

---

## Conventions & gotchas

- **`:5174` is the BAKED nginx prod build.** Rebuild the image for FE changes; a host `vite dev` can **shadow** it. Robust smoke = built image on a free port, or `vite dev` on `:5199`.
- **The FE talks to the gateway via relative `/v1`.** A non-empty `VITE_API_BASE` bakes a fixed host into the bundle and breaks every other origin.
- **Never conditionally unmount stateful components** — ternary rendering destroys hook state, AudioContext, and WebSocket connections. Use CSS `hidden` or internal branching.
- **Agent→GUI tools span 2 services / 2 languages** joined only by the LLM. A closed-set arg needs an `enum`, and the resolver must never silently no-op. See [`standards/mcp-tool-io.md`](standards/mcp-tool-io.md).
- **Server is SSOT.** No localStorage for user data — it's a cache for per-device UI prefs only.

---

## Drift check

This index is hand-maintained. Before trusting it:

```bash
ls frontend/src/features/ | wc -l                    # must equal the count at the top
grep -c 'path="' frontend/src/App.tsx                # route count
grep -nE "pathFilter.*'/v1/" services/api-gateway-bff/src/gateway-setup.ts   # real proxy targets
```

**Adding a feature folder? Add its row here in the same commit.** A folder with no row is invisible to the next agent — and a feature that is built, mounted, and green can still be unreachable if nothing routes to it.
