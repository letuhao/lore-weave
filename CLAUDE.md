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

## Task Workflow (12 phases)

**ENFORCEMENT: State machine (`.workflow-state.json`) + hooks block commits without verification.**

Every task follows this workflow. The agent plays all roles sequentially.

```
Phase          | Role              | What Happens
---------------|-------------------|----------------------------------------------
1. CLARIFY     | Architect + PO    | Brainstorm, ask questions, define scope
2. DESIGN      | Lead              | API contract / component API / data flow
3. REVIEW      | PO + Lead         | Review design spec before coding
4. PLAN        | Lead + Developer  | Decompose into bite-sized tasks (2-5 min)
5. BUILD       | Developer         | Write code (TDD: red -> green -> refactor)
6. VERIFY      | Developer         | Evidence-based verification gate
7. REVIEW      | Lead              | Code review (spec compliance + quality)
8. QC          | QA / PO           | Test against acceptance criteria
9. POST-REVIEW | Human + Developer | Human-interactive review (context reset)
10. SESSION    | Developer         | Update session notes + task status
11. COMMIT     | Developer         | Git commit (+ push if approved)
12. RETRO      | All               | Record decision/workaround if learned
```

**Status tracking:** `[ ]` not started · `[C]` clarify · `[D]` design · `[P]` plan · `[B]` build · `[V]` verify · `[R]` review · `[Q]` QC · `[PR]` post-review · `[S]` session · `[x]` done

**Task types:** `[FE]` frontend · `[BE]` backend · `[FS]` full-stack

### Task Size Classification (MANDATORY — do this BEFORE any work)

Count 3 things before starting:

| Metric | How to count |
|--------|-------------|
| **Files touched** | How many files will be created or modified? |
| **Logic changes** | How many functions/methods/handlers will change behavior? (not formatting) |
| **Side effects** | Does it change: API contract, DB schema, config, external behavior, types used by other files? |

| Size | Files | Logic | Side effects | Allowed skips |
|------|-------|-------|--------------|---------------|
| **XS** | 1 | 0-1 | None | CLARIFY + PLAN |
| **S** | 1-2 | 2-3 | None | PLAN only |
| **M** | 3-5 | 4+ | Maybe | None |
| **L** | 6+ | Any | Yes | None. Write plan file. |
| **XL** | 10+ | Any | Yes | None. Write spec + plan. Subagent recommended. |

```bash
./scripts/workflow-gate.sh size XS 1 1 0     # Classify task
./scripts/workflow-gate.sh phase build        # Enter phase
./scripts/workflow-gate.sh complete build "tests pass" # Complete with evidence
./scripts/workflow-gate.sh status             # Check progress
```

Script blocks: undersizing, phase jumps, commits without VERIFY+POST-REVIEW+SESSION.

### Anti-Skip Rules (MANDATORY)

- Agent must NEVER self-authorize skips — ask user
- If you catch yourself about to skip — STOP, announce the skip attempt, ask the user
- If during BUILD you discover the task is larger than classified — STOP, reclassify, announce to user
- User can authorize skips explicitly — agent must never self-authorize

**Phase transition protocol:**
1. State task size classification before starting (XS/S/M/L/XL with counts)
2. Before starting any phase, run `./scripts/workflow-gate.sh phase <name>`
3. Before leaving any phase, run `./scripts/workflow-gate.sh complete <name> "<evidence>"`
4. If during work you discover the task is larger than classified — STOP, reclassify

### Role Perspectives

| Role | Thinks about... |
|------|-----------------|
| **Architect** | System boundaries, dependencies, scoping, impact analysis |
| **PO (Product Owner)** | User value, acceptance criteria, design sign-off, final QC |
| **Lead** | Technical design, plan quality, code review (patterns, security, a11y) |
| **Developer** | Correctness, TDD, efficiency, verification, session tracking |
| **QA** | What can break — edge cases, regression, acceptance criteria |

When playing each role, shift perspective accordingly. Don't just check boxes — think from that role's viewpoint.

### Phase 6: VERIFY (Evidence Gate)

5-step gate before ANY completion claim:

| Step | Action |
|------|--------|
| 1. Identify | What command proves the claim? (test, build, lint, curl...) |
| 2. Run | Execute it fresh — not from memory or cache |
| 3. Read | Complete output including exit codes |
| 4. Confirm | Does output actually match the claim? |
| 5. Claim | Only now state the result, with evidence |

**Red flags — stop immediately if you catch yourself:**
- Using "should work", "probably passes", "seems fine"
- About to commit/push without fresh test run
- Trusting prior output without re-running

### Phase 7: REVIEW (2-Stage Code Review)

| Stage | Focus |
|-------|-------|
| **1. Spec compliance** | Does code implement what was designed? Missing requirements? Scope creep? |
| **2. Code quality** | Patterns, security, a11y, performance, maintainability |

Both stages must pass. If issues found: fix → re-verify (Phase 6) → re-review.

### Phase 9: POST-REVIEW (Human-Interactive Context Reset) — NEVER skippable

**Why:** AI agents suffer from author blindness — they can't objectively review code they just wrote because the reasoning is still in context. Human interaction forces a context reset.

**Step 1 — Present summary to human (MANDATORY STOP):**
- List all files created/modified with one-line descriptions
- Summarize what was built and key design decisions
- Report verification evidence (build, tests, type-check)
- **STOP and WAIT for human response.** Do NOT proceed until the human replies.

**Step 2 — After human responds, adversarial review:**
- **Re-read ALL changed files from disk** — do NOT rely on memory or prior context
- Review with adversarial mindset: actively try to break the code
- Check: logic errors, null handling, API mismatches, state bugs, integration breakage, security

**Step 3 — Report findings:**
- If issues found: list with severity, fix → loop back to Phase 6 VERIFY
- If clean: state "Post-review: 0 issues found" with evidence of what was checked

### Phases 10 + 11 are mandatory — do not skip

AI agents declare tasks "done" after QC and forget SESSION + COMMIT. **That is a bug, not a shortcut.** Work that isn't recorded in `docs/sessions/SESSION_PATCH.md` and committed to git does not exist for the next session.

Checklist at the end of **every** cycle:

1. **Phase 10 — SESSION**:
   - Update `docs/sessions/SESSION_PATCH.md` header metadata (Last Updated, Updated By, HEAD)
   - Add a "Current Active Work" entry with files touched, review issues found/fixed, test count delta
   - Move cleared deferrals to "Recently cleared", add new ones
2. **Phase 11 — COMMIT**:
   - Stage only the files you actually changed (no `git add -A`)
   - Write a commit message that names the phase + review fixes + test count
   - Include SESSION_PATCH update **in the same commit** as the code

### Phase 12: RETRO

- If a non-obvious decision was made → record it (decision log, ADR, lesson)
- If a workaround was needed → record it with context
- If nothing notable → skip this phase

### Debugging Protocol

Activated whenever a bug is encountered during any phase. **NO FIXES WITHOUT ROOT CAUSE.**

```
1. INVEST  — Read errors fully, reproduce, trace data flow backward
2. PATTERN — Find working examples, compare every difference
3. HYPOTHE — State hypothesis, test one variable at a time
4. FIX     — Write failing test -> implement single fix -> verify
```

**Hard stop:** If 3+ fix attempts fail → stop, question the architecture, discuss with user.

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
