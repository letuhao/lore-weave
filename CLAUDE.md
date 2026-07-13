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

The repo has **~46 services**. This file does **not** enumerate them — the old inlined table went stale and misled agents. **Authoritative service→language map: [`contracts/language-rule.yaml`](contracts/language-rule.yaml); purposes: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).** Language rule: Go = domain/meta · Python = AI/LLM · TS = gateway/realtime · Rust = kernel-derived. Do not assume a service is absent because it's not named here.

Load-bearing facts an agent needs regardless:
- **`provider-registry-service`** is the ONLY home of provider SDKs/keys (Provider-gateway invariant below).
- **`glossary-service`** = authored SSOT for lore AND hosts the **wiki** (`wiki_*` tables — wiki is NOT a separate service). **`knowledge-service`** = derived fuzzy/semantic layer (Postgres SSOT + Neo4j) anchored to glossary via `glossary_entity_id` FK (two-layer pattern; see [scope-separation](docs/standards/scope-separation.md)).
- **`api-gateway-bff`** (TS/NestJS) = external entry point; **`chat`/`translation`/`knowledge`** = Python AI services; **`auth`/`book`/`sharing`/`catalog`/`usage-billing`** = Go domain.
- Data: Postgres (per-service DBs), RabbitMQ (job/event bus + outbox), Redis (cache/rate-limit), MinIO (objects).

### Key Rules
- **📇 Standards index (start here)** — every cross-cutting rule/law/invariant/machine-contract in the repo is catalogued in [`docs/standards/README.md`](docs/standards/README.md): what it governs · where the authoritative source lives · how it's enforced · status. It has a *quick-nav by concern* (building an MCP tool? a dockable panel? a new table? an LLM call?) + a *Known gaps* list, and it **links out — never duplicates**. **Adding/retiring a standard? Update its row there.** The rules below are the always-loaded subset.
- **Agent Extensibility Standard** — adding a user/agent-authorable capability (skill, slash command, hook, subagent, MCP-server registration, plugin bundle)? Follow [`docs/standards/agent-extensibility.md`](docs/standards/agent-extensibility.md): the storage→resolver→degrade-safe-consumer→live-E2E shape, validate-parity on import paths, no-silent-no-op (API advertises only what the engine wires), quarantine+scan+SSRF for every external source (verification ≠ safety), and enum-closed-set capability args. Each rule caught a real bug across P0→P5.
- **Settings & Configuration Boundary** — adding *any* configurable behavior (a toggle, mode, threshold, model choice, persona, limit)? Follow [`docs/standards/settings-and-config.md`](docs/standards/settings-and-config.md) (SET-1..8). **Do not abuse a global setting / env var for what is really a per-user choice.** Ask "would two users want different values?" → **yes ⇒ user setting** (a tenancy tier + scope key + the resolution cascade, per User Boundaries), **not** an env flag. Env/global config is reserved for platform-wide, load-bearing infra + **deploy-time ceilings/kill-switches** — and a ceiling is a *max* the user narrows within (`effective = AND(deploy_allows, user_enables)`), **never a per-user knob**. A user setting must: expose its **effective value + source tier** (no silent hidden default — the "grounding always-on / reasoning silently-off" bug class); be **CONSUMED, proven by effect** (a stored-but-unread settings blob is a bug, not a feature — the write-only-behavior bug); enum-validate **closed-set values** on write (Frontend-Tool-Contract discipline); live **server-side** (not localStorage); and have **one home/one name** (consumers inherit, they don't re-store — the model-picked-in-8-places bug). Adding a new global `*_ENABLED`/`*_MODE` env flag that gates *user-facing* behavior is a `/review-impl` finding.
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

### Frontend-Tool Contract (agent→GUI tools — LOCKED)

Full standard: [`docs/standards/mcp-tool-io.md`](docs/standards/mcp-tool-io.md) (inputs IN-1..8 + outputs OUT-1..6). Essentials: a frontend tool (`ui_open_studio_panel`, `propose_edit`, `confirm_action`, …) spans **2 services / 2 languages** joined only by the LLM — BE schema `chat-service/app/services/frontend_tools.py` ↔ FE resolver `frontend/src/features/**`. So a drift/free-string/silent-no-op passes unit tests yet kills the live loop (shipped once: `panel_id` had no enum → gemma sent `panel:"editor"` → silent no-op → hallucinated success). Rules: **closed-set arg ⇒ `enum`** (register in `CLOSED_SET_ARGS`); **resolver never silently no-ops** (return `result.error`); **one name for one concept**; **machine-checked both sides** via `contracts/frontend-tools.contract.json` (change a schema → `WRITE_FRONTEND_CONTRACT=1 pytest` + update the resolver, or a test reds); **verify by EFFECT** (live browser smoke, not raw-stream).

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

### User Boundaries & Tenancy (LOCKED — read before designing ANY feature)

**Root-cause note:** early in this project the agent conflated "self-hosted" with "single-user" and designed features with **no user boundary** — shared rows any user could mutate for everyone (the canonical bug: `glossary_entities`'s `entity_kinds` were *globally unique + user-mutable*, so one user editing a "kind" changed it for all users). **Self-hosted ≠ single-user.** Every deployment is **multi-tenant**: many users, each with private data, sharing one DB and one set of system defaults.

**The scoping tiers — every user-facing resource MUST declare which tier it belongs to:**

| Tier | Owner | Who may WRITE | Visible to | Example |
|---|---|---|---|---|
| **System** | the platform | **admin only** (never a regular user) | everyone (read-only) | default entity-kinds, the 12 seeded glossary kinds, pricing presets |
| **Per-user** | a `user_id` | that user | that user (+ collaborators they grant) | a user's custom glossary kinds, BYOK credentials, preferences |
| **Per-book** (or per-project/per-resource) | a `book_id`/`project_id` | the owner + grantees (E0 grants) | the owner + grantees | book-specific kinds, glossary entities, campaigns |

**Hard rules:**
- **A regular user MUST NOT mutate a System-tier (shared/global) row.** System defaults are seeded + admin-managed; users *clone* or *override* them into their own per-user/per-book tier, never edit the shared original. A write endpoint on a shared resource that any authenticated user can call is a **tenancy defect**, not a feature.
- **Every table holding user-customizable data carries a scope key** — `owner_user_id` and/or `book_id` — and **every query filters by it**. A `UNIQUE(code)` on a shared table (no scope column) is the smell that produced the kinds bug; the correct constraint is `UNIQUE(owner_user_id, code)` / `UNIQUE(book_id, code)`.
- **Cross-tenant access is grant-gated, never implicit** — sharing happens only through the E0 collaboration grants (see the Gateway/grants invariants), never by a global row everyone can see/edit.
- **Resolution merges tiers, lowest-precedence first:** System (defaults) → Per-user (the user's overrides/additions) → Per-book (book-specific). Higher tiers shadow lower by `code`.

**Design checklist (apply to every new feature before building):** Who owns each row? What is its scope key? Can user A's action affect user B's data or view? If a "shared" or "global" resource is user-editable, STOP — it almost certainly needs a per-user/per-book tier instead, with System read-only + admin-only writes.

---

## Test Parallelization (dev speed — adopted 2026-07-03)

Python suites run under **pytest-xdist**: `python -m pytest tests -q -n auto --dist loadgroup`
(install once per machine: `python -m pip install pytest-xdist`). Measured: composition
1472 tests 418s→55s; translation full suite 37s. Rules:
- **Always pass `--dist loadgroup`** — tests hitting the shared dev Postgres carry
  `pytestmark = pytest.mark.xdist_group("pg")` (serialized onto one worker). A NEW test file
  that touches a real DB/port MUST add that mark, or parallel workers interleave and counts lie.
- Iterating during BUILD: run `-k` subsets serially; the full `-n auto` suite is the VERIFY gate.
- Cross-service: run each service's suite as a parallel background task; ONE combined verify
  before commit when multiple services changed.

---

## Sub-agent Fan-out — the cost discipline (LOCKED — adopted 2026-07-13)

**The incident this exists to prevent.** A planning run fanned out **605 sub-agents** and burned
**~45M tokens** adjudicating 580 open questions — **one agent per question**. It hit the session limit
and died, and the answers it did produce were **no better than ~10 agents grouped by file** would have
given. A later run doing the same *class* of work with **4 agents grouped by file** cost **864k tokens**
— **~52× cheaper, same quality**. The waste was **not** the volume of work. It was the **shape of the
fan-out**.

### Why a sub-agent is expensive in a way that is easy to miss

The main session has a **1M context with prompt caching** (1-hour TTL): once a file is read, re-reasoning
over it is nearly free, and every subsequent turn re-uses the cache. **A sub-agent starts COLD.** It
shares none of that cache. It pays **full price** to re-read the same specs, the same plan, the same
source files — and then it pays again to write its result back into the parent.

⇒ **N sub-agents over the same corpus = N × full-price reads, with zero cache re-use.** This is why
per-item fan-out explodes: 580 agents each re-read the same 5 plan documents to answer one question about
them. Grouping by file reads each document **once**.

### The rule

**Solo-in-the-1M-context is the DEFAULT.** Fan out only when the work clears a bar — and say the estimate
out loud before you do.

**Fan out when:**
- The slices are over **genuinely disjoint inputs** (different services, different files) — each agent
  reads *different* bytes, so there is no cache to have re-used anyway.
- You need **independent judgement** (adversarial verify, a judge panel, a cold-start review). Here the
  isolation *is* the product — a fresh agent that cannot see your reasoning is the point.
- The corpus **genuinely exceeds** what one context can hold.
- Parallel **wall-clock** actually matters and the work is long-running.

**Do NOT fan out when:**
- 🔴 **The unit is an ITEM, not a FILE.** One agent per question / per finding / per gap / per row is the
  anti-pattern. **Group by file, by domain, or by disjoint slice — never by list element.**
- The answer is **greppable**. If `grep`/`Read` settles it, just do it. Spawning an agent to run a grep
  you could run yourself costs ~1000× the grep.
- All the agents would **read the same files** to answer different questions about them. That is one
  agent's job, done once.
- It is a **conversational or trivial** turn.

### Before every fan-out, state this

> *"N agents, each reading ⟨what⟩, because ⟨why one agent can't⟩."*

If you cannot fill in *"why one agent can't"*, **don't fan out**.

### Under `ultracode`

`ultracode` removes **cost** as a constraint. It does **not** license **waste**. 605 agents producing what
10 would produce is not thoroughness — it is a broken fan-out shape, and it *lowers* quality by dying
mid-run. Exhaustive means **cover everything once**, not **read everything N times**. The granularity
rule above holds regardless.

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

### Long autonomous runs — the GOAL COMMITMENT (anti-drift) — MANDATORY

Before any long / multi-phase / unattended run (`/loom` across milestones, a build track, an autonomous
implementation), **establish an explicit GOAL first — it is a commitment between the human and the agent, and
the agent must ASK for it, never invent it.** A run with no agreed finish line drifts by construction.

**1 · Ask, then set `/goal`** (Claude Code ≥ v2.1.139 — condition-based; the session keeps working across
turns until a fast evaluator says the condition holds). The agent asks the human what "done" means, proposes
a precise condition, and the human sets it. One goal per session; `/goal` = status, `/goal clear` = stop.
(`/loop` is a *time-interval* re-run — the wrong tool for "until done".)

**2 · Know the evaluator's blind spot — this is the whole reason for the rest of this section.** The `/goal`
evaluator **reads the transcript only. It cannot run commands or read files.** So it is satisfied by the agent
*claiming* a check passed. **`/goal` enforces persistence, not honesty.** Therefore:

- **Write the condition so it forces the proof INTO the transcript** ("the transcript contains the actual
  pasted output of X"; "claiming a check passed without pasting its output does NOT satisfy this condition").
- **Bound it** (`or stop after N turns`).

**3 · Layer the enforcement — a goal alone is not enough.** Drift in a long run is rarely "forgot the task";
it is **silently lowering the bar** (skipping `/review-impl`, treating a green unit test as proof of a
behavior it never exercised, marking a slice done whose live-smoke never ran). Use all three:

| Layer | Enforces | Can the agent talk past it? |
|---|---|---|
| `/goal` condition | persistence + a fresh-model completion check | **yes** (transcript-only evaluator) |
| **A RUN-STATE file on disk** (the commitment, the invariants, the slice board where *done* = an evidence string, + registers for decisions/parked/debt/drift) | memory across compaction | no — it is a file |
| **Rule-based scripts** — the pre-commit hook (`git config core.hooksPath .githooks`) + `scripts/workflow-gate.py` | phase order, VERIFY/POST-REVIEW evidence, the repo invariants | **no** — mechanical |

**4 · Re-read the commitment, don't remember it.** Context is lossy (compaction summarizes; anything living
only in the conversation can evaporate). **After every compaction: re-read the RUN-STATE file first**, then
`git log`, then continue. Keep the RUN-STATE path in the TODO list — the harness re-surfaces todos, so it is
the anchor that survives. **Never re-litigate a sealed decision from memory; re-read it.**

**5 · Blocked ≠ stopped.** If the human has granted an autonomous run: park an unsolvable problem in the
RUN-STATE register, move to other work, and keep going. Stop and ask **only** when an action is
destructive/irreversible or a sealed decision turns out to be wrong.

**6 · The registers make the final audit a byproduct.** Append decisions · parked · debt · drift as you go.
**A run that ends with an empty drift log is not clean — it is dishonest.** Record the near-misses.

---

## MCP Integration (ContextHub)

ContextHub MCP (`http://localhost:3000/mcp` — a DISTINCT service, NOT the gateway) is an **optional** tool for persistent memory + semantic code search: `search_code` (before grepping), `search_lessons` (task start), `add_lesson` (after decisions), `check_guardrails` (before risky ops), `index_project` (after big changes). If it's down/absent, use Glob/Grep/Read + `docs/sessions/SESSION_HANDOFF.md` + `docs/03_planning/` and skip guardrails.

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

- **FIX-NOW is the default; deferral is the exception that must EARN its row.** The Deferred
  list is not a parking lot for every finding — it exists only for work that genuinely cannot be
  resolved in the current run. Tracking is mandatory (a deferral must never be silently dropped),
  but tracking is *not* a licence to defer. A defer row carries ongoing cost: it's re-read at
  every PLAN and re-evaluated every session. **If fixing the bug is cheaper than writing +
  carrying its defer row, just fix it.** Small, in-scope, root-cause-clear bugs (a wrong
  condition, a misleading message, a missing guard, a one-file logic error) are fix-now — even if
  found late in a run. Writing a defer row for a one-line fix is the anti-pattern this rule kills.

- **Defer-eligibility gate — a finding may be deferred ONLY if it meets at least one of:**
  1. **Out of scope** — belongs to a different branch/module/track than the one in flight (fixing it here would scope-creep the current effort).
  2. **Large / structural** — the correct fix needs a refactor, a schema/DB migration, a new feature, or touches a cross-service contract — i.e. it needs a *serious plan*, not a quick edit.
  3. **Naturally-next-phase** — it is genuinely implementable only when a later phase begins (its prerequisites don't exist yet).
  4. **Blocked / unresolvable now** — waiting on a *genuinely external* dependency (another team's
     unreleased work, an upstream API that doesn't exist), a product decision, or profiling
     evidence (perf items: fix when profiling shows pain).
  5. **Conscious won't-fix** — a deliberate decision to not fix, recorded so it stops re-surfacing.

  If a finding fits **none** of these, it is NOT eligible to defer — fix it this run. When in
  doubt between "small enough to fix now" and "large enough to defer", **fix it now**; only the
  things that clearly clear the gate above earn a row.

- **"Missing infrastructure" is NOT "blocked" — it is unbuilt work to implement (LOCKED — the
  anti-laziness rule).** Gate #4 is the one most often abused. A feature that needs a new module,
  extractor, schema, or service-side piece that *you could write in this repo* is **buildable**, not
  blocked — it just hasn't been built yet. Before you ever label something "blocked" or defer it as
  "needs X that doesn't exist":
  1. **Verify the claim against code**, don't trust a handoff/doc note (those go stale — a "blocked
     on the missing route" item this project shipped twice turned out to *already exist*).
  2. **Check for the signal/seam** the build needs (e.g. does the row carry a `summary` field an LLM
     could classify from? does a sibling extractor/pattern already exist to mirror?). If the signal
     exists and the pattern exists, it is buildable — **scope it and implement it.**
  3. **Decompose** a "blocked" item into the buildable slice + the genuinely-external remainder. Most
     "blocked" items are mostly buildable now with a small truly-external tail (or no tail at all).
  Only a dependency that is *external to this repo and you cannot write* clears gate #4. "It's a big
  new track" is gate #2 (large/structural — write a plan), **not** "blocked". Saying "blocked" when
  you mean "I'd have to build it" is the lazy tell this rule exists to kill.

- **A deferral that passes the gate gets a tracked row** in the **Deferred Items** section of
  `docs/sessions/SESSION_HANDOFF.md` (and `docs/deferred/DEFERRED.md` in AMAW mode): ID, origin
  phase, description, the gate reason (which of 1–5), and target phase/trigger.
- **At every PLAN phase, read the Deferred Items section.** Any row whose Target phase equals the current phase is a must-do for that phase.
- **Whenever a deferral is cleared, move it to "Recently cleared"** (or delete after a few sessions). The list should shrink as often as it grows — if it's only growing, the gate above is being applied too loosely.
- **Avoid the "we'll come back to it" trap.** "Skip if time is tight" is a yellow flag — there is no time pressure here. Either it clears the defer gate, or it's a real bug to fix now.

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
frontend:        :5174 = the BAKED nginx prod build (rebuild the image for FE changes; a host `vite dev` can SHADOW it). Robust FE smoke = built image on a free port, or `vite dev` :5199. FE talks to the gateway via RELATIVE /v1.
gateway:         api-gateway-bff (NestJS BFF) — container :3000, host-mapped :3123 (dev). vite proxy → :3123 (dev); nginx → gateway:3000 (prod). No :3001 (stale).
mcp_url:         http://localhost:3000/mcp (optional, ContextHub — a DISTINCT service, NOT the gateway)
```

## Test Account
```
email:    claude-test@loreweave.dev
password: Claude@Test2026
name:     Claude Test
auth id:  019d5e3c-7cc5-7e6a-8b27-1344e148bf7c   (loreweave_auth.users.id)
```
Use this account for browser smoke tests (Playwright MCP, etc.).

**It also has ~15 active BYOK `user_models`** (in `loreweave_provider_registry`),
so it can drive **real LLM smokes**, not just browser tests. Chat-capable models
include **gpt-4o** (OpenAI — real cost) and several **local lm_studio** chat
models (e.g. *Qwen2.5 7B Instruct*, *Gemma-4 26B*, *Qwen3 35B*) plus *bge-m3*
(embedding), *bge-reranker-v2-m3* (rerank), *Kokoro* (tts). Prefer a **local**
chat model for $0 spend (needs lm_studio running). The `model_ref` to pass is the
`user_model_id` UUID — resolve live:
`SELECT user_model_id, alias, capability_flags FROM user_models WHERE owner_user_id='019d5e3c-…' AND is_active;`
Caveat: `user_default_models` is **empty** for this account — anything resolving
a "default model for capability X" gets nothing; pass an explicit `model_ref`.
