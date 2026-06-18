# CLAUDE.md — LoreWeave Development Guide

## What This Project Is

LoreWeave is a multi-agent platform for multilingual novel workflows (translation, analysis, knowledge building, assisted creation). Cloud-hosted (AWS) monorepo with Docker Compose for local development. Serves multiple users across multiple devices (PC, mobile, tablet).

Source of truth for current status: `docs/sessions/SESSION_HANDOFF.md`

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
| `translation-service` | Python / FastAPI | Translation pipeline |
| `glossary-service` | Go / Chi | Glossary & lore management. **Also hosts the wiki feature** (`wiki_articles`, `wiki_revisions`, `wiki_suggestions`) — wiki is NOT a separate service. |
| `chat-service` | Python / FastAPI | Chat with LLMs via LiteLLM |
| `knowledge-service` | Python / FastAPI | Knowledge graph + memory (Postgres SSOT + Neo4j derived, via event pipeline) — planned, see `docs/03_planning/101_DATA_RE_ENGINEERING_PLAN.md` and `docs/03_planning/KNOWLEDGE_SERVICE_ARCHITECTURE.md`. **Two-layer pattern with glossary**: glossary-service remains authored SSOT; knowledge-service adds a fuzzy/semantic entity layer that anchors to glossary entries via `glossary_entity_id` FK. Extraction writes canonical entities through to glossary via its existing `/internal/books/{book_id}/extract-entities` bulk API, and wiki stubs via `/v1/glossary/books/{book_id}/wiki/generate`. Pattern validated by Microsoft GraphRAG seed-graph (arXiv:2404.16130) and HippoRAG (arXiv:2405.14831). |
| `video-gen-service` | Python / FastAPI | Media generation gateway; ComfyUI implementation in sibling **local-image-generator-service** (SD 1.5, SDXL, Illustrious, Flux 1/2, Qwen Image, Wan, LTX Video; custom pipelines for game assets, object sheets, animation) |

Data: Postgres (per-service DBs), RabbitMQ (job/event bus — translation & extraction workers, outbox events, via AMQP/aio_pika), Redis (cache / rate-limit / ephemeral state), MinIO (objects).

### Key Rules
- **Contract-first**: API contract frozen before frontend flow
- **Gateway invariant**: all external traffic through `api-gateway-bff` — with ONE sanctioned exception (PRR-20): the `game-server` real-time WebSocket transport (Colyseus) is a second public entry point that inherits the same auth/rate-limit/audit edge controls. See `docs/03_planning/LLM_MMO_RPG/00_foundation/02_invariants.md` I1 amendment.
- **MCP-first invariant (AI agent logic)** — *any* AI **agent** capability (logic where an LLM decides actions, calls tools, or reasons multi-step over tools/data) MUST be exposed and invoked as an **MCP tool-call through `ai-gateway`** — never a bespoke HTTP endpoint driven by a raw prompt. **If the tool doesn't exist, create it** as an MCP tool on the owning domain service (domain owns its tools; `ai-gateway` only federates/routes — see `docs/specs/2026-06-10-glossary-assistant-architecture.md`). Non-agentic LLM *pipelines* (e.g. translation, enrichment) are exempt, but **new** agentic logic is not. Legacy agentic logic still on HTTP/raw-prompt is **tracked for migration in Deferred**, never silently grandfathered.
- **Provider gateway invariant (ENFORCED)** — NO service imports a provider SDK or calls a provider API directly; every LLM/embedding/**rerank**/image/audio/STT call goes through **`provider-registry-service`** (the only place provider SDKs/HTTP live). Verified held across all AI services 2026-06-10. Any new direct provider SDK import is a defect, not a shortcut.
  - **Local/self-hosted model backends are NOT an exception** — a sibling local service (e.g. `local-rerank-service` :28417, `local-stt-service`, `local-tts-service`, ollama/lm_studio) is reached **only** as a **BYOK provider credential through provider-registry** (`user_models` JOIN `provider_credentials`: kind + `endpoint_base_url` + secret), never via direct `*_URL`/`*_MODEL`/`*_SERVICE_TOKEN` platform config in a consuming service. This is the exact mistake `D-RERANK-NOT-BYOK` fixed: rerank was first wired as platform config in knowledge-service (RERANK_URL/MODEL/SERVICE_TOKEN) instead of resolving the user's model via provider-registry like embed. **Adding a new model capability or a new local backend → register it as a provider-registry credential + a `user_models` row (capability flag, pricing), and resolve it via an `/internal/*` provider-registry route. Do NOT add a per-service URL/token env var for a model backend.**
- **No hardcoded model names (ENFORCED)** — model names *and pricing* resolve from `provider-registry-service`, never literal in service runtime code (exceptions: provider-registry's own preconfig/pricing, and test fixtures). On a violation: fix now if cheap, else add a Deferred migration row — never leave it untracked.
- **Provider-rule gate** — the two ENFORCED rules above are checked programmatically by `scripts/ai-provider-gate.py` (cross-platform; provider-SDK imports for Py/TS/Go + hardcoded model literals, with an allowlist + DEFERRED tracking). Wired as a **pre-commit** hook via `git config core.hooksPath .githooks` (run once per checkout); CI/manual: `python scripts/ai-provider-gate.py`. Known-deferred drift is allowlisted (see DEFERRED 065); a genuinely new legacy case must get a DEFERRED row + an explicit allowlist entry, never an untracked bypass.
- **Language rule** (I3, amended & LOCKED 2026-05-29): **Rust** for kernel-derived services (world/travel/tilemap, the DP-kernel consumers), **Go** for domain + meta services, **Python** for AI/LLM services, **TypeScript** for gateway/BFF + realtime transport. The authoritative service→language map is `contracts/language-rule.yaml`, enforced by `scripts/language-rule-lint.sh` (FAILs on mismatch, on a present service mapped `missing`, and on a present service with no row). See `docs/plans/2026-05-29-foundation-mega-task/I3_INVARIANT_AMENDMENT.md` §5.
- Each microservice owns its own Postgres database
- **No hardcoded secrets** — all secrets via env vars, services fail to start if missing

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

1. **Read** `docs/sessions/SESSION_HANDOFF.md` — read the **▶ NEXT SESSION** block at the top
2. **Check** the relevant planning doc in `docs/03_planning/` for whatever module you're working on
3. For data layer orientation (SSOT, DB ownership, flows), read `docs/DATA_ARCHITECTURE.md`
4. If ContextHub MCP is available, optionally call `search_lessons` and `search_code` for prior context

### Session End

Overwrite the **▶ NEXT SESSION** block in `docs/sessions/SESSION_HANDOFF.md` in place:
- Update header (date, HEAD, session number)
- Replace NEXT items with what's actually next
- Update Deferred list (clear resolved rows, add new ones)
- Keep the file short — append historical detail to `<details>` blocks or archive it

### Session continuity — do NOT suggest restarting

A commit is a **task checkpoint, not a session boundary**. Once code is committed, the next task continues in the *same* session.

- **Do NOT** suggest opening a new session, "starting fresh", pausing, or "wrapping up" based on commit count, number of milestones done, elapsed time, or conversation length. None of these are reasons to stop.
- This matters most during **`/loom`** multi-milestone runs: after each milestone commits, just present the close-out and continue to the next `/loom <…>` — never advise a new session in between.
- Only mention context at all when it is **genuinely near full (>90% used)**. At normal usage (e.g. a 1M window with most of it free) context is a non-issue — say nothing about it.
- If compaction is truly needed, run `/compact`. Do not ask the user to restart.

The legitimate stop points are the workflow's own PO checkpoints (CLARIFY end, POST-REVIEW) and the user explicitly saying they're done — nothing else.

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
- Use `docs/sessions/SESSION_HANDOFF.md` for session continuity
- Use `docs/03_planning/` for module context
- Skip `check_guardrails` — use common sense instead

---

## Phase Checkpoint Protocol

Update `docs/sessions/SESSION_HANDOFF.md` at meaningful phase boundaries:

| Trigger | Action |
|---|---|
| A module backend/frontend completes | Update NEXT block + Deferred list |
| A new blocker is discovered | Add to Deferred with category |
| A blocker is resolved | Move to "Recently cleared" or delete |
| A code review intentionally postpones a fix | Add to **Deferred Items** |

**Rule:** if you complete more than one commit's worth of work, update SESSION_HANDOFF before moving to the next phase.

---

## No Deadline · No Defer Drift

LoreWeave is a hobby project with **no fixed deadline**. This shapes how reviews and planning work:

- **Don't rush past quality issues.** A second-pass code review after every BUILD is mandatory, not optional. If you find a bug or smell, fix it now unless it genuinely belongs in a later phase.
- **"Defer" must mean "tracked", not "forgotten".** Every intentional postponement gets a row in the **Deferred Items** section of `docs/sessions/SESSION_HANDOFF.md` with: ID, origin phase, description, target phase. Categories:
  - **Naturally-next-phase** — implement when its target phase begins
  - **Track 2 planning** — document only, no Track 1 action
  - **Perf items** — fix when profiling shows pain
  - **Won't-fix** — conscious decision, removed from mental backlog
- **At every PLAN phase, read the Deferred Items section.** Any row whose Target phase equals the current phase is a must-do for that phase.
- **Whenever a deferral is cleared, move it to "Recently cleared"** (or delete after a few sessions). The list should shrink as often as it grows.
- **Avoid the "we'll come back to it" trap.** If you find yourself saying "skip if time is tight", that's a yellow flag — there is no time pressure here. Either it's genuinely Track 2, or it's a real bug to fix now.

---

## Task Workflow

**Bundle v2.3** — default v2.2 human-in-loop + opt-in AMAW v3.0. Full prose in [`agentic-workflow/WORKFLOW.md`](agentic-workflow/WORKFLOW.md) and [`docs/amaw-workflow.md`](docs/amaw-workflow.md). This section captures only what the agent must keep loaded at all times.

**Default mode (v2.2):** human-in-loop with PO checkpoints at CLARIFY end + POST-REVIEW.
**Opt-in (AMAW v3.0) — HUMAN-INITIATED ONLY:** AMAW is an automated sub-agent flow that the agent **never** proposes, announces, or invokes on its own. It activates **only** when the human explicitly types `/amaw` (or asks for it) for a task. Do **not** suggest `/amaw` at CLARIFY, before BUILD, or anywhere else — even for L+ / load-bearing work (data migrations, schema changes, security-critical paths). If the human wants the cold-start sub-agent reviews, they will turn it on; otherwise stay in default v2.2. (Token cost ~$1-5/task is the human's call to make.)

### 12 phases

```
CLARIFY → DESIGN → REVIEW → PLAN → BUILD → VERIFY → REVIEW → QC → POST-REVIEW → SESSION → COMMIT → RETRO
```

| Phase | Default v2.2 role | AMAW role (opt-in) |
|---|---|---|
| 1. CLARIFY | Architect + PO | Main + Scribe |
| 2. DESIGN | Lead | Main |
| 3. REVIEW (design) | PO + Lead self-review | Adversary cold-start |
| 4. PLAN | Lead + Developer | Main + Scribe |
| 5. BUILD | Developer (TDD) | Main |
| 6. VERIFY | Developer (evidence gate) | Main |
| 7. REVIEW (code) | Lead self-review | Adversary cold-start |
| 8. QC | QA / PO | Scope Guard |
| 9. POST-REVIEW | Human checkpoint — present + WAIT | Scope Guard |
| 10. SESSION | Developer | Scribe |
| 11. COMMIT | Developer | Main |
| 12. RETRO | All — `add_lesson` to ContextHub | Audit Logger |

**Status markers:** `[ ]` not started · `[C/D/P/B/V/R/Q/PR/S]` in phase · `[x]` done. **Task types:** `[FE]` frontend · `[BE]` backend · `[FS]` full-stack.

### Repo-specific paths (workflow artifacts)

| Artifact | Path |
|---|---|
| Main session notes | `docs/sessions/SESSION_HANDOFF.md` |
| Design-track session notes | `docs/03_planning/<TRACK>/SESSION_HANDOFF.md` |
| New specs (CLARIFY) | `docs/specs/YYYY-MM-DD-<topic>.md` (or `docs/03_planning/<TRACK>/` for legacy tracks) |
| New plans (PLAN) | `docs/plans/YYYY-MM-DD-<feature>.md` (or `docs/03_planning/<TRACK>/`) |
| AMAW audit log | `docs/audit/AUDIT_LOG.jsonl` (append-only, committed) |
| Deferred items | `docs/deferred/DEFERRED.md` |
| ContextHub project_id (RETRO `add_lesson`) | `mmo-rpg-zone-map-design-non-human-in-loop` |

### Task Size Classification (MANDATORY — before work begins)

**Size by COMPLEXITY + RISK, not file count** (2026-06-12 redesign). The old file-count
table over-sized wide-but-shallow changes (one param added across 12 files read as XL),
fragmenting coherent work into needless ceremony on a large-context window. The axes:

- **Logic** = distinct **semantic** changes (new behaviors, contracts, branches) — the **primary** axis.
- **Side effects** = API/DB/config/migration/auth — **risk**; sets a hard **floor** (undersizing can't cross it).
- **Files** = a **breadth** signal only. A mechanical sweep (low logic-per-file) does **NOT** escalate; breadth bumps size **one tier** only when the change is genuinely deep across it (`logic ≳ files`).

| Size | Logic (primary) | Risk floor | Allowed skips |
|------|-----------------|-----------|---------------|
| **XS** | 0-1 | no side effects | CLARIFY + PLAN |
| **S** | 2-3 | ≥1 side effect ⇒ min S | PLAN only |
| **M** | 4-6 | ≥2 side effects ⇒ min M | None |
| **L** | 7-12 | Yes | None — write plan file |
| **XL** | 13+ | Yes | None — write spec + plan; subagent recommended |

**Classify the whole EFFORT, not each sub-task.** A coherent multi-part change (e.g. a
re-arch spanning several services) is ONE classification + ONE continuous run — not N
small tasks each with its own size→build→review→commit cycle. Undersizing on **breadth**
is allowed (the gate warns, you proceed); undersizing below the **risk floor** is blocked.

**Budget-driven checkpoint cadence (the big unlock).** On a large-context model, let the
**context budget** — not file count — drive when to stop. Pass current context % as the
5th arg: `size <S> <files> <logic> <side_effects> <context_pct>`.
- **Ample budget (<~70%):** run continuously. Checkpoint/commit at genuine **risk boundaries**
  (a new contract, a migration, a cross-service seam, a shippable milestone), **not** at
  arbitrary file/sub-task counts.
- **Filling (>~80%):** checkpoint/commit + `/compact` at the next risk boundary.
- **PO checkpoints (CLARIFY end + POST-REVIEW) are BATCHED per-milestone:** one CLARIFY for
  the effort's scope; POST-REVIEW at each shippable risk boundary — not per sub-task.
- **Quality gates stay, applied per-milestone:** VERIFY evidence, 2-stage REVIEW, live-smoke
  (≥2 services), `/review-impl` for load-bearing code. These caught real bugs; keep them.

**ENFORCEMENT** — state machine (`.workflow-state.json`) + pre-commit hook block phase jumps and commits without VERIFY+POST-REVIEW+SESSION evidence:

```bash
./scripts/workflow-gate.sh size M 3 4 0 45      # Classify (files=3 logic=4 se=0, context=45%)
./scripts/workflow-gate.sh phase build          # Enter phase
./scripts/workflow-gate.sh complete build "tests pass"  # Mark done with evidence
./scripts/workflow-gate.sh status               # Check progress
```

The `.sh` is a thin wrapper around `scripts/workflow-gate.py` (cross-platform; sidesteps the Windows pyenv-win shim bug that broke the prior all-bash impl).

### Anti-Skip Rules

- Agent **never** self-authorizes a skip — STOP, announce the skip attempt, ask user.
- If during BUILD you discover the task is larger than classified — STOP, reclassify, announce.
- Common skip patterns and why each is a violation: see [`agentic-workflow/WORKFLOW.md`](agentic-workflow/WORKFLOW.md) "Anti-Skip Rules" table.

### Role Perspectives (default mode)

When playing each role, shift perspective — don't just check boxes:

| Role | Thinks about... |
|------|-----------------|
| **Architect** | System boundaries, dependencies, scoping, impact |
| **PO** | User value, acceptance criteria, design sign-off, final QC |
| **Lead** | Technical design, plan quality, code review (patterns, security, a11y) |
| **Developer** | Correctness, TDD, efficiency, verification, session tracking |
| **QA** | What can break — edge cases, regression, acceptance criteria |

### Phase 6 VERIFY (Evidence Gate)

Run command → Read complete output → Confirm match → THEN claim. No "should work", no trusting prior runs. **Red flags:** "probably passes", "seems fine", about to commit without fresh test run, trusting cached output.

**Cross-service live-smoke evidence (added session 59 cycle B).** When the cycle touches **≥2 services**, unit suite green is insufficient — mock-only coverage repeatedly hid cross-service contract bugs (4 hits sessions 58-59: K21 `execute_tool` timeout, embedding model-ref UUID drift, eval/ docker shipping, chat-service `/record` 401). At VERIFY completion the evidence string MUST include ONE of these tokens, or `workflow-gate.py` emits a soft warning (never blocks):

- `live smoke: <one-liner>` — confirm a real cross-service call ran on a stack-up (the bug surface)
- `LIVE-SMOKE deferred to D-<NAME>-LIVE-SMOKE` — track the deferral row in SESSION_HANDOFF
- `live infra unavailable: <reason>` — legitimate skip when full stack isn't bootable at dev time

`workflow-gate.py` autodetects cross-service via `git diff --name-only HEAD` matching ≥2 distinct `services/<name>/` prefixes. The warning is advisory; the agent decides whether to live-smoke now or defer it explicitly.

### Phase 7 REVIEW (2-Stage Code Review)

| Stage | Focus |
|-------|-------|
| 1. Spec compliance | Does code implement what was designed? Missing requirements? Scope creep? |
| 2. Code quality | Patterns, security, a11y, performance, maintainability |

Both stages must pass. Issues found → fix → re-VERIFY → re-review.

### Phase 9 POST-REVIEW (Human-Interactive Checkpoint) — NEVER skippable

**Why:** forcing-function pause so the human can veto / redirect / request specifics before SESSION+COMMIT burns the diff in. Deep self-review here doesn't work (author blindness → "0 issues found" rubber-stamp).

**Default mode:** present concise summary (files touched, design decisions, verify evidence), **STOP and WAIT** for human reply. Don't pre-write "0 issues found" — that's the rubber-stamp tell. Human approves → SESSION. Human asks deeper → invoke `/review-impl` first.

**Proactively suggest `/review-impl` (without being asked) when:** auth/credential code, tenant isolation boundaries, destructive ops, injection defenses, new service boundaries, or anything user previously flagged as load-bearing.

**AMAW mode:** Scope Guard sub-agent runs the conservative final gate (CLEAR / BLOCKED). See `docs/amaw-workflow.md`.

**Completion evidence:** `"summary presented, human approved: <one-liner>"`. If `/review-impl` ran, fold its findings into the evidence.

### Phases 10 + 11 + 12 — mandatory, do not forget

After QC succeeds, **do not** declare task done. Three more phases:

1. **SESSION (10)** — update `docs/sessions/SESSION_HANDOFF.md` (or `docs/03_planning/<TRACK>/SESSION_HANDOFF.md` for design tracks): overwrite the **▶ NEXT SESSION** block — header (date, HEAD), NEXT items, Deferred list. Move cleared deferrals to "Recently cleared". AMAW mode also updates `docs/deferred/DEFERRED.md`.
2. **COMMIT (11)** — stage only changed files (no `git add -A`); commit message names phase + review fixes + test count; SESSION update lands in the same commit as the code.
3. **RETRO (12)** — non-obvious decisions or workarounds → `add_lesson` to ContextHub MCP (`project_id = mmo-rpg-zone-map-design-non-human-in-loop`). Skip if nothing notable.

**Hard rule:** work not recorded in SESSION_HANDOFF and committed to git **does not exist** for the next session.

### Debugging Protocol

NO FIXES WITHOUT ROOT CAUSE.

```
1. INVEST  — Read errors fully, reproduce, trace data flow backward
2. PATTERN — Find working examples, compare every difference
3. HYPOTHE — State hypothesis, test one variable at a time
4. FIX     — Write failing test → implement single fix → verify
```

**Hard stop:** 3+ fix attempts fail → stop, question architecture, discuss with user.

### Slash commands

| Command | When |
|---|---|
| `/review-impl [task-id]` | On-demand deep adversarial review. Invoke when POST-REVIEW needs deeper look, or after COMMIT when something feels off. Default mode. |
| `/amaw` | **Human-initiated only** — the agent never suggests or invokes this. The human types `/amaw` to enable AMAW v3.0 for the current task (cold-start sub-agent reviews). For data migrations, schema changes, security-critical paths, multi-system contracts — but the decision is always the human's. |

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
frontend_port:   5174 (Vite dev — see frontend/vite.config.ts)
gateway:         api-gateway-bff (NestJS BFF) listens on container :3000, host-mapped :3123 (dev). FE always talks to it via RELATIVE /v1 (vite proxy → :3123 in dev; nginx → gateway:3000 in prod). No :3001 — that was a stale doc value.
mcp_url:         http://localhost:3000/mcp (optional, ContextHub — a DISTINCT service, NOT the gateway)
```

## Test Account
```
email:    claude-test@loreweave.dev
password: Claude@Test2026
name:     Claude Test
```
Use this account for browser smoke tests (Playwright MCP, etc.).
