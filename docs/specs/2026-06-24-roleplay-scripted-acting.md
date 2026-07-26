# Spec — roleplay-service (lean Rust foundation; scripted acting → NPC memory)

- **Date:** 2026-06-24
- **What:** Stand up **`roleplay-service`** (Rust) — the deliberate seed of the planned MMO roleplay-service — **lean**, serving **book users** (roleplay/interview *practice*) on the platform plane now, designed to scale to **millions of NPCs** later. It owns the **script** + **actor memory** domain and **delegates** the turn loop / voice / debrief to existing services.
- **Owner surfaces:** **`roleplay-service`** (NEW, Rust: scripts, actor-memory store, start-orchestration), `chat-service` (live turn loop + voice + seed-anchoring + M6 debrief — **reused, unchanged**), `api-gateway-bff` (`/v1/roleplay` proxy), `frontend` (Roleplay destination). knowledge-service/glossary/KG/ES/provider-registry are **deferred** dependencies.
- **Builds on:** [2026-06-23-interview-roleplay.md](2026-06-23-interview-roleplay.md) (M1–M7) and [2026-06-24-roleplay-scripted-acting earlier revisions]. Interview practice becomes preset genre `interview`.

## 0. Decisions locked (this design thread)

1. **Roleplay supersedes interview** (interview = a preset genre).
2. **New `roleplay-service`**, built **now**, **lean** — scale up later.
3. **Rust** — it's a game-tier service; `language-rule.yaml:78` already reserves `roleplay-service: rust` (was `missing`, "L4 cycle 17+"). We pull it forward.
4. **NPC/actor memory stored like chat (operational), NOT event-sourced.** Only **major world events** are promoted to the reality/ES. NPC chatter stays in roleplay-service's store to avoid ES overhead.
5. **The bounded `charter`+`state` block is the durable per-actor memory** (fixed cost per actor → scales to millions); the raw transcript is ephemeral/archivable.
6. **Two storage planes:** *Platform* (book users, per-service owner-scoped DB, **general reality** = `reality_id NULL`) **now**; *Game* (per-reality DBs) **later**.
7. **database-per-reality is a game rule** — book-user roleplay is platform data, so the lean build uses a **single `loreweave_roleplay` pool**, owner-scoped. No violation.
8. **Multi-reality DB SDK = `crates/reality-db`** (extract world-service's `db_pool` + reuse `meta-rs` routing + a **net-new** live `pool-per-shard + search_path-per-reality` client) — **deferred** to when roleplay-service joins the game plane. Tracked foundation item, not v1.
9. **Build it RIGHT in Rust now — NOT a tradeoff.** M1–M7 (Python, in chat-service/knowledge-service) was the **spike**: it de-risked the anti-drift design and browser-proved the UX. The real implementation is **Rust**, built now, with seams correct so game-scale (per-reality, world-model, NPC fan-out) lands **additively — no refactor**. Building more Python to rewrite at game-time is the waste being avoided. "Lean" constrains **scope** (no world-model/sharding/millions-NPC infra yet), never **architecture** (Rust + correct seams from day one).

## 1. Concept — "script & acting" = the actor-memory seed

A **script** is an authored base (premise, setting, cast, opening, soft beats). **Acting** is the live session where the AI plays a role and improvises. No new engine — the anti-drift split reused from M1–M7:

| Script | → | Behavior |
|---|---|---|
| premise/objective | `charter.goal` (**frozen**) | the durable anchor — keeps the scene/role coherent |
| beats | `charter.checklist` (**advisory**) | reached-markers in `state`, never required |
| persona / role | `system_prompt` | who the AI plays |

**The reframe:** `{charter, state}` *is* an actor's memory — `charter` = persona + standing goal (frozen), `state` = disposition + what it remembers (bounded). M1–M7 isn't "the interview feature"; it's the **NPC-memory seed**. The human book-user practicing is just the **first single-actor consumer**.

## 2. Architecture — planes, owns vs delegates

```
FE features/roleplay/ ─/v1/roleplay─► roleplay-service (Rust)   scripts + actor-memory + start
        │                                   │ seed charter (working_memory_seed)
        └── reused ChatView (/v1/chat) ─► chat-service          turn loop, voice,
                                            anchoring-from-seed (M3), M6 debrief
```

| Plane | Who | DB model | When |
|---|---|---|---|
| **Platform** | book users (practice) | single `loreweave_roleplay`, `owner_user_id`-scoped, `reality_id NULL`=general | **now** |
| **Game** | NPCs in a world | per-reality DBs via `crates/reality-db` (deferred) | later |

**roleplay-service OWNS:** `roleplay_scripts` + CRUD, `rp_sessions`, `rp_memory` (the actor-memory store), **start-orchestration**.
**DELEGATES (reused, unchanged):** live turns + voice + **anchoring from the frozen seed** (chat-service M3 fallback path — needs no knowledge-service) → chat-service; the **debrief scorecard** → chat-service M6 (`/evaluate`) for v1.

**Start** (`POST /v1/roleplay/scripts/{id}/start`): roleplay-service is the **goal authority** — freeze the charter from the script, store it in `rp_memory`, and create a chat-service `chat_sessions` row carrying `working_memory_seed` (= the frozen charter; the column already exists from M1) + `system_prompt` + `model_ref`. The FE opens that session in `ChatView`; anchoring runs from the seed.

## 3. Data model (`loreweave_roleplay`, Rust/sqlx)

```
roleplay_scripts(
  script_id UUID PK, owner_user_id UUID NULL (System), tier, code, name, description,
  system_prompt, model_source, model_ref, rubric JSONB, scenario JSONB, genre,
  book_id UUID NULL, reality_id UUID NULL /*=general*/, attachment_key NULL,
  is_active, created_at, updated_at)
rp_sessions(session_id /*= the chat_sessions id*/ PK, script_id FK, owner_user_id,
  reality_id NULL, created_at, debrief_output_id NULL)
rp_memory(session_id PK, charter JSONB /*frozen*/, state JSONB /*bounded, mutable*/, updated_at)
```
- **Tenancy:** System = `UNIQUE(code) WHERE owner_user_id IS NULL`; Per-user/Per-book = **`UNIQUE(owner_user_id, book_id, code)`** (NULLS NOT DISTINCT on book_id) — *fixes the prior single-index gap*. Tier CHECK: `system⇒owner NULL`; `user⇒owner NOT NULL,book_id NULL`; `book⇒owner+book_id NOT NULL` + E0 grant on the book.
- **`scenario`** schema (superset of the interview scenario): `premise`(→goal), `setting`, `ai_role`, `cast[]`, `user_role`, `opening`, `beats[]`(→checklist), `phases[]`, `tone`, `improv_freedom`(tight|balanced|loose, carried into the charter), `time_budget_min`, `language`. Interview maps `goal→premise`, `checklist→beats` (charter schema unchanged → M3 anchoring untouched).
- **`reality_id`** present but everything is NULL (general reality) in v1; the routing seam is a trait so swapping in `reality-db` later is localized.

## 4. Lean v1 scope vs deferred

**IN (v1):** roleplay-service (Rust) scripts CRUD + start-orchestration + `rp_memory` (charter authoritative); single platform pool; FE Roleplay destination + gallery + **paste**-a-scenario (manual structured form) + reused ChatView acting (anchored from the seed) + debrief via chat-service M6; migrate the 3 interview presets → System scripts (genre `interview`).

**DEFERRED (scale-up, explicitly):**
- `roleplay_draft_script` **AI MCP tool** (agentic, LLM, Python/AI-tier) — paste is manual-structured in v1.
- **File attach** (MinIO) — paste-only in v1.
- The **executive** (live `state` evolution) — v1 is **charter-anchor only**; dynamic memory is the executive scale-up.
- **Genre-aware debrief** — interview STAR stays in chat M6; freeform-roleplay rubric later.
- **`crates/reality-db`** + per-reality routing + sharding/archival — game plane.
- **ES major-event** emission to the reality — stubbed seam (v1 has no world events by definition).
- **World-model goal authority**, multi-character/multi-voice, semantic/KG recall.

## 5. The deferred multi-reality DB SDK (`crates/reality-db`)

When roleplay-service goes multi-reality: **reuse, don't reinvent.** Three parts (per the code audit):
- routing/registry/status — **`meta-rs`** (shared crate, ready).
- shard/pool **capacity registry** — **extract** world-service's [`db_pool.rs`](../../services/world-service/src/db_pool.rs) (well-bounded pure logic; only coupling is its error type) into the crate.
- live **`pool-per-shard-host + SET search_path=lw_reality_<id>`** client (pgbouncer transaction-pooling, 5000 virtual/500 real) — **net-new**; `db_pool` is config/caps only, not a live pool.
roleplay-service v1 hides DB access behind a trait so this swaps in without touching call sites. **No "one pool per reality DB" scheme — ever.**

## 6. Memory model

- **Durable per-actor memory = the bounded `rp_memory` block** (`charter` + `state`), fixed-shape JSONB → O(1) per actor, the property that makes millions tractable. Transcript (`chat_messages`, chat-service) is hot-but-archivable.
- **v1 = charter-anchor only** (frozen premise/persona anchors the role; that *is* M3's value). `state` evolution (the executive) is deferred — so v1 actors don't "learn" new facts mid-session beyond the charter; acceptable for the practice feature.
- **ES boundary:** only **major** world events promote to the reality/ES; everything else stays operational here. v1 emits none (no game), via a stubbed `emit_major_event` seam.

## 7. Invariant compliance

- **Language rule:** roleplay-service = **Rust** — flip `language-rule.yaml:78` `missing`→`rust` (the lint then enforces it; a Python impl would FAIL).
- **Tenancy:** platform plane owner-scoped; Per-book grant-gated; `UNIQUE(owner_user_id, book_id, code)`; System read-only to users.
- **Gateway:** `/v1/roleplay` added to api-gateway-bff (a normal domain REST proxy — invariant holds).
- **Provider-gateway / MCP-first:** v1 makes **no LLM calls from roleplay-service** (acting + debrief stay in chat-service), so neither invariant is touched yet. The deferred AI-draft tool, when built, is an MCP tool through ai-gateway via provider-registry (no vendor SDK).

## 8. Migration

1. Scaffold `roleplay-service` (Rust/axum/sqlx, cargo-workspace member, `loreweave_roleplay` DB, Dockerfile, compose, `/healthz /readyz /metrics`, JWT + internal-token, `/v1/roleplay` proxy).
2. **Re-home M1/M2** (scripts table + CRUD + start) from chat-service (Python) to roleplay-service (Rust) — data migration `session_templates`→`roleplay_scripts` + the 3 System seeds. **chat-service keeps** `chat_sessions(working_memory_seed)`, the turn loop, M3 anchoring, and M6 `/evaluate`; it gains an internal session-create that accepts a seed from roleplay-service. **Sequencing safety:** keep the chat-service endpoints live until roleplay-service is proven, then re-point the FE + re-run the M7 browser smoke.
3. FE `features/interview/`→`features/roleplay/`; scripts/start → `/v1/roleplay`; acting + debrief stay `/v1/chat`.

## 9. Edge-case evaluation

| # | Case | Sev | Handling |
|---|---|---|---|
| EC-1 | A regular user writes a **System** / another user's script. | 🔴 | Write `WHERE owner_user_id=caller`→404; identity from the JWT, never the body. |
| EC-2 | **Per-book** script for a book the user can't access. | 🔴 | `book` tier requires an E0 grant on `book_id`, checked at write; `UNIQUE(owner,book_id,code)`. |
| EC-3 | **Start partial failure** (chat session created, charter store fails, or vice-versa). | 🟠 | Create the chat session FIRST (it owns the session id) → write `rp_memory`+`rp_sessions` → seed is also on `chat_sessions` (so even if `rp_memory` write fails, M3 anchors from the seed; reconcile job backfills `rp_memory`). Idempotent by session id. Never a charter without a session. |
| EC-4 | **Language-rule lint** fails / someone scaffolds it in Python. | 🟠 | Flip `language-rule.yaml` `missing`→`rust`; the lint enforces Rust. A non-Rust impl is a hard CI fail. |
| EC-5 | **reality_id** discipline — a later query forgets the reality scope and mixes realities. | 🟡 | All v1 rows are `reality_id NULL`; every query filters `owner_user_id` (and `reality_id` once non-NULL exists). The DB-access trait centralizes scoping so the game-plane swap can't leak cross-reality. |
| EC-6 | **Charter-anchor only** (executive deferred) → actor doesn't remember new facts mid-session. | 🟡 | Accepted for v1 (the practice feature); the frozen premise still prevents drift (M3). `state` evolution = the executive scale-up; the column exists so it's additive. |
| EC-7 | **Bounded memory** grows unbounded. | 🟡 | `rp_memory` is fixed-shape JSONB (`charter`+`state`), not an append log; transcript lives in chat-service and is archivable. Per-actor cost stays O(1) — the million-NPC property. |
| EC-8 | **ES stub** silently drops events that should reach the reality. | 🟢 | v1 has **no** major world events (platform plane, no game) → the no-op stub is correct by definition. Wiring `emit_major_event` is gated with the game plane; documented so it isn't forgotten. |
| EC-9 | **reality-db deferral** leaks into v1 (premature shard infra). | 🟢 | v1 = one plain `loreweave_roleplay` pool. The trait seam means adopting `reality-db` later touches one module, not call sites. No pgbouncer/shard config in v1. |
| EC-10 | **Migration breaks the working interview feature** (M1–M7). | 🔴 | Re-home behind a transition: keep chat-service `/templates*`+`/evaluate` live until roleplay-service passes its own tests + a re-run of the **M7 browser smoke**; only then re-point the FE and retire the old endpoints. Charter schema unchanged → anchoring untouched. |
| EC-11 | **Cross-service auth** (roleplay→chat internal session-create). | 🔴 | `X-Internal-Token` on the internal create path; the seed is data, the owner is the JWT-resolved caller passed through. **`/review-impl` the new boundary.** |
| EC-12 | **FE spans 3 surfaces** (roleplay scripts/start, chat acting, chat debrief) — partial outage. | 🟠 | Each is independent + degrades: scripts/gallery down → can't start (clear error); acting is chat-service (already resilient); debrief down → "try again," session intact. |
| EC-13 | **Debrief** still interview-shaped for a freeform script. | 🟠 | v1 keeps chat M6 STAR for `genre=interview`; freeform scripts get a minimal beats-reached recap or no score until the genre-aware debrief scale-up. Don't show STAR nonsense. |
| EC-14 | **Scope creep** — foundation (SDK, ES, world-model) built before the feature ships. | 🟠 | v1 milestones front-load the shippable book-user feature; every foundation item (§4 deferred) is gated behind the game plane. The lint for "did we ship the feature" = the M7 browser smoke green on roleplay-service. |
| EC-15 | **Rust LLM temptation** — someone adds a debrief/draft LLM call in roleplay-service. | 🟡 | v1 roleplay-service makes **no** LLM calls (keeps it a clean store+orchestrator). Any future LLM call → provider-registry via reqwest (no vendor SDK), and agentic ones → an MCP tool through ai-gateway. |

## 10. Open decisions

1. ~~Migration timing~~ — **RESOLVED: re-home to Rust in v1.** M1–M7 was the spike; the Rust roleplay-service is the real build. Safety transition per §8/EC-10 (keep chat-service endpoints live until the Rust service passes its tests + the re-run M7 browser smoke, then re-point the FE + retire them).
2. **Memory-tier boundary (clarify before PLAN):** roleplay-service (Rust) owns the **actor working-memory** (`charter`+`state`, hot/operational, scales) — this is where M4/M5's design lands, in Rust. knowledge-service (Python) stays the **semantic/KG recall** tier (general memory). roleplay sessions no longer use the knowledge-service working_memory block; the M4/M5 block was part of the spike.
3. **`improv_freedom` defaults** — `interview=tight`, freeform `roleplay=balanced`?
4. **Debrief for freeform genre** — minimal beats recap now, or no score until the genre-aware scale-up?
5. **Script sharing** between users (E0 grants on `roleplay_scripts`) — v1 or deferred? (Gallery works on System + own without it.)
6. **`rp_memory` reader in v1** — accept it as forward-foundation (written now, read by the Rust executive added additively later), or give it a cheap reader now (M3 anchoring reads the charter from `rp_memory`) so the schema is exercised/validated in v1? *Either is no-refactor; the second validates the store under real use.*

## 11. Milestones (refine at PLAN)

- **R0** — Rust service scaffold + `loreweave_roleplay` + gateway proxy + auth + health (infra gate; lint flips to `rust`).
- **R1** — `roleplay_scripts` + CRUD + tenancy + start-orchestration (seed → chat session) + `rp_memory` (charter); interview presets migrated; chat-service internal session-create-with-seed. **`/review-impl`** (new boundary + tenant isolation).
- **R2** — FE Roleplay destination: gallery + paste-new-scenario (manual structured) + reused ChatView acting (seed-anchored) + debrief via chat M6; re-point off chat-service; **re-run M7 browser smoke**.
- **R3** — POST-REVIEW; flip the FE fully; retire chat-service `/templates*`.
- **(Deferred tracks)** — `crates/reality-db`, the AI-draft MCP tool, executive/state, genre-aware debrief, ES wiring, world-model — each its own later effort.
```
