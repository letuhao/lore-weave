# CLAUDE.md — LoreWeave Development Guide

## What This Project Is

LoreWeave is a multi-agent platform for multilingual novel workflows (translation, analysis, knowledge building, assisted creation). Self-hosted, Docker Compose-based monorepo.

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
| `glossary-service` | Go / Chi | Glossary & lore management |
| `chat-service` | Python / FastAPI | Chat with LLMs via LiteLLM |

Data: Postgres (per-service DBs), Redis Streams (jobs), MinIO (objects).

### Key Rules
- **Contract-first**: API contract frozen before frontend flow
- **Gateway invariant**: all external traffic through `api-gateway-bff`
- **Provider gateway invariant**: NO direct provider SDK calls — all AI calls go through adapter layer
- **Language rule**: Go for domain services, Python for AI/LLM services, TypeScript for gateway/BFF
- Each microservice owns its own Postgres database

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

**Rule:** if you complete more than one commit's worth of work, update SESSION_PATCH before moving to the next phase.

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
