# CLAUDE.md — LoreWeave Development Guide

## What This Project Is

LoreWeave is a multi-agent platform for multilingual novel workflows (translation, analysis, knowledge building, assisted creation). Cloud-hosted (AWS) monorepo with Docker Compose for local development. Serves multiple users across multiple devices (PC, mobile, tablet).

Source of truth for current status: `docs/sessions/SESSION_PATCH.md`

---

## Architecture

Monorepo layout:
- `services/` — microservices (Go/Chi, Python/FastAPI, TypeScript/NestJS)
- `frontend/` — Vite + React + Tailwind + shadcn/ui
- `contracts/api/` — OpenAPI specs per service domain
- `docs/` — governance, planning, and session docs
- `infra/` — docker-compose and infra config

### Services
| Service | Language | Purpose |
|---|---|---|
| `api-gateway-bff` | TypeScript / NestJS | External traffic entry point |
| `auth-service` | Go / Chi | Identity & JWT auth |
| `book-service` | Go / Chi | Books, chapters, chunks |
| `sharing-service` | Go / Chi | Visibility & sharing |
| `catalog-service` | Go / Chi | Public catalog |
| `provider-registry-service` | Go / Chi | BYOK AI provider credentials |
| `usage-billing-service` | Go / Chi | Usage metering & billing |
| `translation-service` | Go / Chi | Translation pipeline |
| `glossary-service` | Go / Chi | Glossary & lore management. **Also hosts the wiki feature** (`wiki_articles`, `wiki_revisions`, `wiki_suggestions`) — wiki is NOT a separate service. |
| `chat-service` | Python / FastAPI | Chat with LLMs via LiteLLM |
| `knowledge-service` | Python / FastAPI | Knowledge graph + memory (Postgres SSOT + Neo4j derived, via event pipeline) — planned, see `docs/03_planning/101_DATA_RE_ENGINEERING_PLAN.md` and `docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md`. **Two-layer pattern with glossary**: glossary-service remains authored SSOT; knowledge-service adds a fuzzy/semantic entity layer that anchors to glossary entries via `glossary_entity_id` FK. Extraction writes canonical entities through to glossary via its existing `/internal/books/{book_id}/extract-entities` bulk API, and wiki stubs via `/v1/glossary/books/{book_id}/wiki/generate`. Pattern validated by Microsoft GraphRAG seed-graph (arXiv:2404.16130) and HippoRAG (arXiv:2405.14831). |
| `video-gen-service` | Python / FastAPI | Video generation (skeleton — provider TBD) |

Data: Postgres (per-service DBs), Redis Streams (jobs), MinIO (objects).

### Key Rules
- **Contract-first**: API contract frozen before frontend flow
- **Gateway invariant**: all external traffic through `api-gateway-bff`
- **Provider gateway invariant**: NO direct provider SDK calls — all AI calls go through adapter layer
- **Language rule**: Go for domain services, Python for AI/LLM services, TypeScript for gateway/BFF
- Each microservice owns its own Postgres database
- **No hardcoded secrets** — all secrets via env vars, services fail to start if missing
- **No hardcoded model names** — model names resolved from provider-registry (user's registered config)

### Frontend Architecture Rules (React MVC)

React merges logic and view — we impose MVC separation ourselves:

**File structure per feature:**
```
features/<name>/
  hooks/        ← "controllers" — own logic + state, no JSX
  context/      ← "services" — shared state across components
  components/   ← "views" — render only, receive data from context/props
  api.ts        ← API layer
  types.ts      ← TypeScript types
```

**Rules:**
- **Separation of concerns** — components render, hooks own logic, context shares state. No API calls or business logic inside components.
- **Never conditionally unmount stateful components** — use CSS `hidden` or internal branching. Ternary rendering (`{cond ? <A/> : <B/>}`) destroys hook state, AudioContext, WebSocket connections, etc.
- **No useEffect for event handling** — useEffect is for synchronization (subscriptions, timers), NOT for reacting to user actions or state changes. Use explicit callback handlers instead. The pattern `useEffect(() => { if (prev && !current) doSomething() }, [current])` is always wrong — call `doSomething()` directly where the state change originates.
- **Split context by update frequency** — separate stable context (session, config — changes rarely) from volatile context (streaming text — changes every frame). Putting both in one context forces all consumers to re-render on every SSE chunk.
- **No prop-drilling middlemen** — if a component exists only to pass props through to children, replace it with context or flatten the tree.
- **Hooks must be self-contained** — a custom hook should own its state, effects, and cleanup. It should not require the parent component to manage its lifecycle via useEffect.
- **Max ~100 lines per component, ~200 per hook** — if larger, split. A component with 12+ concerns is a code smell.

### Data Persistence Rules
- **Server is the source of truth** — all user data in Postgres, all files in S3/MinIO
- **No localStorage for user data** — localStorage is ONLY a fast cache for preferences that are also synced to server via `/v1/me/preferences`
- **Multi-device support** — user logs in on any device, sees the same data. Nothing stored only locally.
- **UI state that must persist** — save to DB (e.g., last active session, reading position). NOT localStorage.
- **UI state that is per-device** — OK in localStorage (e.g., sidebar collapsed, editor panel widths)
- **Preferences** — read from server on login, write-through to server on change, localStorage as cache only

### Hosting Model
- **Cloud-hosted on AWS** (ECS/EC2, RDS, S3, ElastiCache) — NOT local-machine-only
- **Docker Compose for development** — same services, same architecture, local ports
- **Self-hosted does NOT mean local PC** — it means user controls the infrastructure (could be AWS, GCP, VPS, homelab)
- **Multi-device, multi-user** — design for users accessing from PC, phone, tablet simultaneously
- **No platform lock-in** — no Vercel, no Cloudflare-specific APIs. Standard Docker + Postgres + S3

---

## Session Protocol

### Session Start (every session)

1. **Read** `docs/sessions/SESSION_PATCH.md` — orient to current state, active work, blockers
2. **Check** the relevant planning doc in `docs/03_planning/` for whatever module you're working on
3. If ContextHub MCP is available, optionally call `search_lessons` and `search_code` for prior context

### Session End

Update `docs/sessions/SESSION_PATCH.md` with:
- What was completed
- What is next
- Any new open blockers

---

## MCP Integration (ContextHub)

ContextHub MCP server (`http://localhost:3000/mcp`) is an **optional tool** for persistent memory and semantic code search. Use it when available, skip when it's not running.

### When to use MCP tools

| Tool | When | Why |
|---|---|---|
| `search_code` | Before grepping for code | Semantic search finds by intent |
| `search_lessons` | Starting a task | Load prior decisions/preferences |
| `add_lesson` | After significant decisions | Persist knowledge for future sessions |
| `check_guardrails` | Before risky actions (push, deploy, migration) | Enforce captured team rules |
| `index_project` | After major code changes | Keep search results current |

### MCP is optional — not a blocker

If MCP server is down or unavailable:
- Use standard tools (Glob, Grep, Read) to find code
- Use `docs/sessions/SESSION_PATCH.md` for session continuity
- Use `docs/03_planning/` for module context
- Skip `check_guardrails` — use common sense instead

---

## Phase Checkpoint Protocol

Update `docs/sessions/SESSION_PATCH.md` at meaningful phase boundaries:

| Trigger | Action |
|---|---|
| A module backend/frontend completes | Update Module Status Matrix |
| A new blocker is discovered | Add to Open Blockers |
| A blocker is resolved | Remove from Open Blockers |
| A commit batch closes a work item | Update Session History + Current Active Work |
| A code review intentionally postpones a fix | Add to **Deferred Items** in SESSION_PATCH |

**Rule:** if you complete more than one commit's worth of work, update SESSION_PATCH before moving to the next phase.

---

## No Deadline · No Defer Drift

LoreWeave is a hobby project with **no fixed deadline**. This shapes how reviews and planning work:

- **Don't rush past quality issues.** A second-pass code review after every BUILD is mandatory, not optional. If you find a bug or smell, fix it now unless it genuinely belongs in a later phase.
- **"Defer" must mean "tracked", not "forgotten".** Every intentional postponement gets a row in the **Deferred Items** section of `docs/sessions/SESSION_PATCH.md` with: ID, origin phase, description, target phase. Categories:
  - **Naturally-next-phase** — implement when its target phase begins
  - **Track 2 planning** — document only, no Track 1 action
  - **Perf items** — fix when profiling shows pain
  - **Won't-fix** — conscious decision, removed from mental backlog
- **At every PLAN phase, read the Deferred Items section.** Any row whose Target phase equals the current phase is a must-do for that phase.
- **Whenever a deferral is cleared, move it to "Recently cleared"** (or delete after a few sessions). The list should shrink as often as it grows.
- **Avoid the "we'll come back to it" trap.** If you find yourself saying "skip if time is tight", that's a yellow flag — there is no time pressure here. Either it's genuinely Track 2, or it's a real bug to fix now.

---

## Task Workflow (9 phases per task)

Every task follows this workflow. The agent plays all roles sequentially.

```
Phase     │ Role              │ What Happens
──────────┼───────────────────┼──────────────────────────────────────
1. PLAN   │ Architect + PO    │ Define scope, acceptance criteria, deps
2. DESIGN │ Lead              │ API contract / component API / data flow
3. REVIEW │ PO + Lead         │ Review design before coding
4. BUILD  │ Developer         │ Write code (backend then frontend)
5. TEST   │ Developer         │ Run locally, fix bugs, write unit tests
6. REVIEW │ Lead              │ Code review (patterns, security, a11y)
7. QC     │ QA / PO           │ Test against acceptance criteria
8. SESSION│ Developer         │ Update SESSION_PATCH.md + task status
9. COMMIT │ Developer         │ Git commit + push
```

**Status tracking:** `[ ]` not started · `[P]` plan · `[D]` design · `[B]` build · `[R]` review · `[Q]` QC · `[S]` session · `[✓]` done

**Task types:** `[FE]` frontend only · `[BE]` backend only · `[FS]` full-stack (backend + frontend)

**Role perspectives:**
- **Architect** — scoping, dependencies, system-level impact
- **PO (Product Owner)** — acceptance criteria, design sign-off, final QC
- **Lead** — technical design, code review (patterns, security, a11y)
- **Developer** — implementation, testing, session tracking, commits
- **QA** — test against acceptance criteria, edge cases, regression

When playing each role, shift perspective accordingly. Architect thinks about system boundaries. PO thinks about user value and acceptance. Lead thinks about code quality and maintainability. Developer thinks about correctness and efficiency. QA thinks about what can break.

---

## Module Progression

Modules are implemented in order. Each module has a full doc set in `docs/03_planning/`:
- Execution pack, API contract, frontend flow spec, backend/frontend detailed design
- UI/UX wireframe spec, integration sequence diagrams, acceptance test plan
- Implementation readiness gate, governance review checklist

Read only the docs for the module you're actively working on.

---

## Project Constants
```
project_id:      loreweave
frontend_port:   5173 (Vite dev)
gateway_port:    3001 (NestJS BFF)
mcp_url:         http://localhost:3000/mcp (optional, ContextHub)
```

## Test Account
```
email:    claude-test@loreweave.dev
password: Claude@Test2026
name:     Claude Test
```
Use this account for browser smoke tests (Playwright MCP, etc.).
