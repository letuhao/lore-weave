# Feature Catalog

> **Status:** Living reference — updated as features are discovered or designed.
> **Purpose:** Bird's-eye view of every feature touching this product. Provides stable IDs for cross-reference across design docs. Use this to answer "what does the product actually include?" without having to read every doc.
> **Created:** 2026-04-23

---

## How to use this file

- **Every feature has a stable ID** (e.g. `NPC-3`). Cross-reference from other docs via ID.
- **Status** tells you where the feature stands:
  - ✅ **Designed** — has a concrete design in one of the numbered docs
  - 🟡 **Partial** — designed in broad strokes, has pending decisions
  - 📦 **Deferred** — known, explicitly pushed to a future design doc (tied to a `DF*` in [OPEN_DECISIONS.md](OPEN_DECISIONS.md))
  - ❓ **Open** — identified but no design yet
  - 🚫 **Out of scope** — considered and rejected
- **Tier** tells you when the feature is needed:
  - `V1` — required for first solo RP prototype
  - `V2` — coop scene (2–4 players in one reality)
  - `V3` — full persistent multiverse MMO
  - `V4+` — future vision, exploratory
  - `INFRA` — infrastructure, no tier (always needed)
  - `PLT` — platform-hosted only (self-hosted can skip)
- **Dep** lists upstream features that must exist for this one to work.
- **Design ref** points to the doc section that owns the design detail.

When adding new features:
1. Assign the next ID in its category
2. Set status + tier + dep
3. Point `Design ref` to where the detail lives (or `TBD`)
4. Mark deferred ones with a `DF` tag from [OPEN_DECISIONS.md](OPEN_DECISIONS.md)

---

## Category map

| Code | Category | What it covers |
|---|---|---|
| **IF** | Infrastructure | Storage, sharding, realtime transport — invisible to users |
| **WA** | World Authoring | Book → glossary → reality pipeline; author-side tools |
| **PO** | Player Onboarding | Account, reality discovery, PC creation |
| **PL** | Play Loop | Session, turn, prompt, LLM inference, event broadcast |
| **NPC** | NPC Systems | NPC persona, memory, behavior, canon-faithfulness |
| **PCS** | PC Systems | PC state, lifecycle, offline behavior |
| **SOC** | Social | Session mechanics, PvP, group chat, moderation |
| **NAR** | Narrative / Canon | Canon layers, canonization, world rules |
| **EM** | Emergent / Advanced | Fork, travel, rebase, reality lifecycle |
| **PLT** | Platform | Tiers, billing, admin, moderation at platform level |
| **CC** | Cross-cutting | UI, i18n, accessibility, observability |
| **DL** | Daily Life | Offline PC/NPC routines (DF1 umbrella) |

---

## IF — Infrastructure

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| IF-1 | Event-sourced storage (events as SSOT, projections as derived state) | ✅ | INFRA | — | [02 §4](02_STORAGE_ARCHITECTURE.md) |
| IF-2 | Snapshot-fork semantics (peer realities, cascading read) | ✅ | INFRA | IF-1 | [03 §6–7](03_MULTIVERSE_MODEL.md) |
| IF-3 | Reality registry + DB-per-reality with subtree grouping | ✅ | INFRA | IF-1 | [02 §7](02_STORAGE_ARCHITECTURE.md), [03 §7](03_MULTIVERSE_MODEL.md) |
| IF-4 | Meta registry (cross-reality player index, instance routing) | ✅ | INFRA | IF-3 | [02 §7.2, §12E.2](02_STORAGE_ARCHITECTURE.md) |
| IF-4a | Meta-worker service (dedicated Go, xreality.* event consumer) | ✅ | INFRA | IF-4, IF-5 | [02 §12E.3](02_STORAGE_ARCHITECTURE.md) (R5-L2) |
| IF-4b | Cross-instance event propagation (`xreality.*` topics) | ✅ | INFRA | IF-5 | [02 §12E.3](02_STORAGE_ARCHITECTURE.md) (R5-L2) |
| IF-4c | Cross-instance data access governance policy | ✅ | INFRA | — | [docs/02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md](../../02_governance/CROSS_INSTANCE_DATA_ACCESS_POLICY.md) (R5 anti-pattern) |
| IF-5 | Realtime transport (Redis Streams + WebSocket fanout per region) | 🟡 | INFRA | IF-1 | [02 §9](02_STORAGE_ARCHITECTURE.md); reuse [70_ASYNC_JOB_WEBSOCKET_ARCHITECTURE_PLAN](../70_ASYNC_JOB_WEBSOCKET_ARCHITECTURE_PLAN.md) |
| IF-5a | Session as single-writer command processor (mandatory) | ✅ | V1 | — | [02 §12G.2](02_STORAGE_ARCHITECTURE.md) (R7-L1) |
| IF-5b | Event scope tagging (`session` / `region` / `reality` / `world`) | ✅ | V1 | IF-1 | [02 §12G.3](02_STORAGE_ARCHITECTURE.md) (R7-L2) |
| IF-5c | Cross-session event handler service (dedicated Go) | ✅ | V1 | IF-1 | [02 §12G.5](02_STORAGE_ARCHITECTURE.md) (R7-L3) |
| IF-5d | Session event queue (per session, priority pop before user input) | ✅ | V1 | IF-5a | [02 §12G.4](02_STORAGE_ARCHITECTURE.md) (R7-L4) |
| IF-5e | NPC single-session constraint (V1; multi-presence deferred V2+) | ✅ | V1 | NPC-1 | [02 §12G.7](02_STORAGE_ARCHITECTURE.md) (R7-L6) |
| IF-6 | Outbox pattern (crash-safe publish) | ✅ | INFRA | IF-1, IF-5 | [02 §9.2, §12F.1](02_STORAGE_ARCHITECTURE.md) |
| IF-6a | Publisher service (dedicated Go, leader election, partition-by-reality) | ✅ | INFRA | IF-6 | [02 §12F.2](02_STORAGE_ARCHITECTURE.md) (R6-L2) |
| IF-6b | Per-reality outbox lag monitoring + 3-tier alerts | ✅ | INFRA | IF-6a | [02 §12F.3](02_STORAGE_ARCHITECTURE.md) (R6-L3) |
| IF-6c | Client catchup protocol (WS handshake + REST `/v1/realities/{id}/events?since=`) | ✅ | V1 | IF-6a | [02 §12F.4](02_STORAGE_ARCHITECTURE.md) (R6-L4) |
| IF-6d | Dead-letter queue with retry backoff + admin resolution | ✅ | INFRA | IF-6 | [02 §12F.5](02_STORAGE_ARCHITECTURE.md) (R6-L5) |
| IF-6e | Redis stream MAXLEN + DB fallback (Redis is cache, DB is SSOT) | ✅ | INFRA | IF-6 | [02 §12F.6](02_STORAGE_ARCHITECTURE.md) (R6-L6, resolves R12) |
| IF-6f | Graceful shutdown + handoff | ✅ | INFRA | IF-6a | [02 §12F.7](02_STORAGE_ARCHITECTURE.md) (R6-L7) |
| IF-7 | Event schema versioning + upcaster chain | ✅ | INFRA | IF-1 | [02 §10, §12C.3](02_STORAGE_ARCHITECTURE.md) |
| IF-7a | Additive-first discipline (policy) | ✅ | INFRA | IF-7 | [02 §12C.1](02_STORAGE_ARCHITECTURE.md) (R3-L1 locked) |
| IF-7b | Schema-as-code + registry (Go source + codegen) | ✅ | INFRA | IF-7 | [02 §12C.2](02_STORAGE_ARCHITECTURE.md) (R3-L2 locked) |
| IF-7c | Schema validation on write | ✅ | INFRA | IF-7 | [02 §12C.4](02_STORAGE_ARCHITECTURE.md) (R3-L4 locked) |
| IF-7d | Breaking change via new event_type (90d deprecation cooldown) | ✅ | INFRA | IF-7 | [02 §12C.5](02_STORAGE_ARCHITECTURE.md) (R3-L5 locked) |
| IF-7e | Polyglot type generation (Go → TS + Python) | ✅ | INFRA | IF-7b | [02 §12C.7](02_STORAGE_ARCHITECTURE.md) |
| IF-7f | Archive upgrade (upcast at cold-archive) | 📦 | V2 | IF-10 | [02 §12C.6](02_STORAGE_ARCHITECTURE.md) (R3-L6 deferred V2) |
| IF-8 | Snapshots (per-aggregate periodic checkpoints) | ✅ | INFRA | IF-1 | [02 §6](02_STORAGE_ARCHITECTURE.md) |
| IF-9 | Projection rebuild pipeline | ✅ | INFRA | IF-1, IF-8 | [02 §5.5, §12B](02_STORAGE_ARCHITECTURE.md) |
| IF-9a | Per-aggregate parallel rebuild (8-worker default) | ✅ | INFRA | IF-9 | [02 §12B.2](02_STORAGE_ARCHITECTURE.md) (R2-L2 locked) |
| IF-9b | V1 freeze-rebuild for schema migration | ✅ | V1 | IF-9 | [02 §12B.3](02_STORAGE_ARCHITECTURE.md) (R2-L3 locked) |
| IF-9c | V2 blue-green projection tables (dual-write + atomic swap) | ✅ | V2 | IF-9 | [02 §12B.3](02_STORAGE_ARCHITECTURE.md) (R2-L3 locked) |
| IF-9d | Integrity checker (daily sample + monthly full) | ✅ | V1 | IF-9 | [02 §12B.4](02_STORAGE_ARCHITECTURE.md) (R2-L4 locked) |
| IF-9e | Catastrophic rebuild procedure (freeze-rebuild-thaw, rolling 50 concurrent) | ✅ | V1 | IF-9 | [02 §12B.5](02_STORAGE_ARCHITECTURE.md) (R2-L5 locked) |
| IF-10 | Archive to MinIO (hot/warm/cold tiering of events) | ✅ | INFRA | IF-1 | [02 §11, §12A.4](02_STORAGE_ARCHITECTURE.md) |
| IF-10a | Audit split — separate `event_audit` table from `events` | ✅ | INFRA | IF-1 | [02 §12A.1](02_STORAGE_ARCHITECTURE.md) (R1-L1 locked) |
| IF-10b | Event emission discipline — state events vs derivable, only state events persisted | ✅ | INFRA | IF-1 | [02 §12A.2](02_STORAGE_ARCHITECTURE.md) (R1-L2 locked) |
| IF-10c | Tiered retention per event type (nightly cleanup job) | ✅ | INFRA | IF-10 | [02 §12A.3](02_STORAGE_ARCHITECTURE.md) (R1-L3 locked) |
| IF-10d | Snapshot-then-truncate non-canon aggregates | ✅ | V3 | IF-8 | [02 §12A.5](02_STORAGE_ARCHITECTURE.md) (R1-L5 locked) |
| IF-10e | lz4 compression on JSONB columns + ZSTD for MinIO cold | ✅ | INFRA | IF-1 | [02 §12A.6](02_STORAGE_ARCHITECTURE.md) (R1-L6 locked) |
| IF-11 | Auto-freeze + auto-archive of inactive realities | 🟡 | INFRA | IF-3, IF-10 | [03 §12.1](03_MULTIVERSE_MODEL.md) |
| IF-12 | pgvector-per-reality embedding storage | ✅ | INFRA | IF-3 | Locked S2 |
| IF-13 | Schema migrations across N instance DBs (idempotent, staggered) | ✅ | INFRA | IF-3 | [02 §7.5, §12D.2](02_STORAGE_ARCHITECTURE.md) |
| IF-13a | Automated DB provisioning + deprovisioning | ✅ | INFRA | IF-3 | [02 §12D.1](02_STORAGE_ARCHITECTURE.md) (R4-L1) |
| IF-13b | Migration orchestrator (dedicated Go service) | ✅ | INFRA | IF-13 | [02 §12D.2](02_STORAGE_ARCHITECTURE.md) (R4-L2) |
| IF-13c | Tiered backup strategy (active/frozen/archived → different schedules) | ✅ | INFRA | IF-3, IF-10 | [02 §12D.3](02_STORAGE_ARCHITECTURE.md) (R4-L3) |
| IF-13d | pgbouncer connection pooling (per-shard, transaction mode) | ✅ | INFRA | IF-3 | [02 §12D.4](02_STORAGE_ARCHITECTURE.md) (R4-L4) |
| IF-13e | Metrics aggregation with reality_id labels | ✅ | INFRA | IF-3 | [02 §12D.5](02_STORAGE_ARCHITECTURE.md) (R4-L5) |
| IF-13f | Shared Postgres server sharding (many DBs per server) | ✅ | V2 | IF-3 | [02 §12D.6](02_STORAGE_ARCHITECTURE.md) (R4-L6) |
| IF-13g | Orphan DB detection + cleanup | ✅ | INFRA | IF-3 | [02 §12D.7](02_STORAGE_ARCHITECTURE.md) (R4-L7) |
| IF-14 | Provider-registry integration (BYOK credential resolution) | ✅ | INFRA | — | Reuse [98_CHAT_SERVICE_DESIGN §5.4](../98_CHAT_SERVICE_DESIGN.md) |
| IF-15 | LiteLLM multi-provider inference (with streaming) | ✅ | INFRA | IF-14 | Reuse [98_CHAT_SERVICE_DESIGN §6](../98_CHAT_SERVICE_DESIGN.md) |
| IF-16 | Per-reality locale primitive | ✅ | INFRA | IF-3 | [03 §8.3](03_MULTIVERSE_MODEL.md) (MV5 primitive P1) |
| IF-17 | Analytics ETL → ClickHouse (cross-reality aggregates) | 📦 | V3 | IF-1 | [02 §3 diagram](02_STORAGE_ARCHITECTURE.md) — optional |
| IF-18 | pgvector HNSW tuning + footprint monitoring | ✅ | V1 | IF-12 | [02 §12K](02_STORAGE_ARCHITECTURE.md) (R11) |
| IF-19 | Global event ordering — accepted trade-off (no mitigation; timestamp merge sufficient) | ✅ | INFRA | — | [02 §12J](02_STORAGE_ARCHITECTURE.md) (R10 ACCEPTED) |
| IF-20 | Admin command library (canonical, named, reviewed, versioned; no ad-hoc SQL) | ✅ | V1 | — | [02 §12L.1](02_STORAGE_ARCHITECTURE.md) (R13-L1) |
| IF-21 | Compensating-event pattern for admin changes | ✅ | V1 | IF-1 | [02 §12L.2](02_STORAGE_ARCHITECTURE.md) (R13-L2) |
| IF-22 | Admin action audit log (centralized, 2-year retention) | ✅ | V1 | IF-4 | [02 §12L.3](02_STORAGE_ARCHITECTURE.md) (R13-L3) |
| IF-23 | Destructive action confirmation + double-approval for dangerous commands | ✅ | V1 | IF-20 | [02 §12L.4](02_STORAGE_ARCHITECTURE.md) (R13-L4) |
| IF-24 | Admin UI guardrails (no raw DROP/UPDATE buttons, no free-form SQL in prod) | ✅ | V1 | — | [02 §12L.5](02_STORAGE_ARCHITECTURE.md) (R13-L5) |
| IF-25 | Admin rollback via compensating events | ✅ | V2 | IF-21 | [02 §12L.6](02_STORAGE_ARCHITECTURE.md) (R13-L6) |
| IF-26 | Admin Action Policy governance doc | ✅ | INFRA | — | [docs/02_governance/ADMIN_ACTION_POLICY.md](../../02_governance/ADMIN_ACTION_POLICY.md) (R13-governance) |

## WA — World Authoring

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| WA-1 | Book → glossary entity derivation (NPC pool, item pool, location pool) | 🟡 | V1 | — | Relies on glossary-service / knowledge-service (in progress) |
| WA-2 | Reality creation by author (first-reality-of-book = fresh seed) | 🟡 | V1 | IF-3 | [03 §5](03_MULTIVERSE_MODEL.md) |
| WA-3 | Canon lock level per attribute (L1 axiomatic vs L2 seeded) | ✅ | V1 | — | [03 §3](03_MULTIVERSE_MODEL.md), MV1 locked |
| WA-4 | Category-based L1 auto-assignment (magic-system, species → L1) | 🟡 | V1 | WA-3 | MV1 locked, heuristic details TBD |
| WA-5 | Per-reality world rules (death behavior, paradox tolerance, PvP) | 📦 | V2+ | IF-1 | **DF4 — World Rule feature** |
| WA-6 | Author dashboard — canonization nominations, reality overview | 📦 | V3+ | WA-2 | Related to DF3 |
| WA-7 | Import/export books (portable format) | 📦 | V4+ | — | Marker: [100_FUTURE_FEATURE_STRUCTURED_IMPORT_EXPORT_MEDIA](../100_FUTURE_FEATURE_STRUCTURED_IMPORT_EXPORT_MEDIA.md) |

## PO — Player Onboarding

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PO-1 | User account (reuse existing auth-service + JWT) | ✅ | V1 | — | Existing M01 identity |
| PO-2 | Reality discovery UI (flat list, metadata: locale, population, canonicality) | 🟡 | V1 | IF-3 | [03 §9.1](03_MULTIVERSE_MODEL.md) |
| PO-3 | Canonicality hint badges (canon_attempt / divergent / pure_what_if) | ✅ | V1 | PO-2 | MV3 locked |
| PO-4 | PC creation — fully custom | ✅ | V1 | IF-3 | [04 §3.1](04_PLAYER_CHARACTER_DESIGN.md), PC-A1 locked |
| PO-5 | PC creation — template-assisted | ✅ | V1 | PO-4 | [04 §3.1](04_PLAYER_CHARACTER_DESIGN.md) |
| PO-6 | PC creation — play-as-glossary-entity | ✅ | V1 | PO-4, WA-1 | [04 §3.2](04_PLAYER_CHARACTER_DESIGN.md), PC-A2 locked |
| PO-7 | PC slot quota (5 per user, configurable) | ✅ | V1 | PO-1 | [04 §5.1](04_PLAYER_CHARACTER_DESIGN.md), PC-C1 locked |
| PO-8 | PC slot purchase (buy more than 5) | 📦 | PLT | PO-7 | **DF2 — Monetization** |
| PO-9 | Reality switcher UI (one user navigates across their PCs in different realities) | 🟡 | V3 | PO-2 | Related to IF-4 |

## PL — Play Loop (core runtime)

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PL-1 | Session lifecycle (create, join, leave, dissolve) | 📦 | V1 | IF-1, IF-5 | **DF5 — Session feature** |
| PL-2 | Player command grammar (`/say`, `/do`, `/take`, `/look`, ...) | 🟡 | V1 | PL-1 | Inspired by SillyTavern slash-commands |
| PL-3 | Turn submission + validation | 🟡 | V1 | PL-1 | Depends on DF5 |
| PL-4 | Prompt assembly (system + canon + retrieval + persona + history + user input) | 🟡 | V1 | NPC-2, NPC-4 | SillyTavern PromptManager inspired |
| PL-5 | LLM streaming inference | ✅ | V1 | IF-15 | Reuse [98 §6](../98_CHAT_SERVICE_DESIGN.md) |
| PL-6 | Tool calling (player action → world state change via LLM-emitted tool call) | 🟡 | V1 | PL-5 | See A5 in [01](01_OPEN_PROBLEMS.md) |
| PL-7 | Event emission + outbox publish | ✅ | V1 | IF-1, IF-6 | [02 §4.4](02_STORAGE_ARCHITECTURE.md) |
| PL-8 | Projection update (in-transaction sync) | ✅ | V1 | IF-1 | [02 §4.6](02_STORAGE_ARCHITECTURE.md) |
| PL-9 | Realtime broadcast (region subscribers see event) | 🟡 | V1 | IF-5, PL-7 | [02 §9](02_STORAGE_ARCHITECTURE.md) |
| PL-10 | Session history load (initial + pagination) | 🟡 | V1 | IF-1 | [02 §5](02_STORAGE_ARCHITECTURE.md) |
| PL-11 | Session replay (re-render past events) | 📦 | V2 | IF-1 | Available via event log; UI TBD |
| PL-12 | Swipe / regenerate variants (SillyTavern pattern) | 📦 | V2 | PL-5 | Feature comparison doc |
| PL-13 | Bookmarks / branch a session (SillyTavern pattern) | 📦 | V3 | PL-1 | Feature comparison doc |
| PL-14 | Reasoning pass-through (Claude extended thinking etc.) | 📦 | V2 | PL-5 | Feature comparison doc |

## NPC — NPC Systems

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| NPC-1 | NPC proxy derivation from glossary entity (per reality) | 🟡 | V1 | IF-3, WA-1 | [02 §5.2](02_STORAGE_ARCHITECTURE.md), [03 §2](03_MULTIVERSE_MODEL.md) |
| NPC-2 | NPC persona assembly (core_beliefs + flexible_state + per-PC memory) | 🟡 | V1 | NPC-1 | [02 §5.2](02_STORAGE_ARCHITECTURE.md); full prompt design in PL-4 |
| NPC-3 | Per-PC memory storage + retrieval | 🟡 | V1 | NPC-1, IF-12 | [01 A1](01_OPEN_PROBLEMS.md#a1-npc-memory-at-scale--partial) — infrastructure resolved by R8 ([02 §12H](02_STORAGE_ARCHITECTURE.md)); semantic layer partial |
| NPC-3a | NPC aggregate split (core + per-pair memory aggregates) | ✅ | V1 | IF-1 | [02 §12H.2](02_STORAGE_ARCHITECTURE.md) (R8-L1 locked) |
| NPC-3b | Bounded memory per pair (LRU facts + rolling summary) | ✅ | V1 | NPC-3a | [02 §12H.3](02_STORAGE_ARCHITECTURE.md) (R8-L2 locked) |
| NPC-3c | Snapshot size enforcement + auto-compaction | ✅ | V1 | NPC-3a | [02 §12H.4](02_STORAGE_ARCHITECTURE.md) (R8-L3 locked) |
| NPC-3d | Cold memory decay (30d/90d/365d) + archive/restore | ✅ | V2 | NPC-3a, IF-10 | [02 §12H.5](02_STORAGE_ARCHITECTURE.md) (R8-L4 locked) |
| NPC-3e | Lazy memory loading (session-scoped) | ✅ | V1 | NPC-3a, IF-5a | [02 §12H.6](02_STORAGE_ARCHITECTURE.md) (R8-L5 locked) |
| NPC-3f | Embedding storage separation (pgvector dedicated table) | ✅ | V1 | IF-12 | [02 §12H.7](02_STORAGE_ARCHITECTURE.md) (R8-L6 locked) |
| NPC-3g | Semantic retrieval quality (which facts to surface) | 🟡 | V1 | NPC-3a, NPC-4 | Needs V1 prototype measurement ([01 A1 semantic layer](01_OPEN_PROBLEMS.md#a1-npc-memory-at-scale--partial)) |
| NPC-3h | LLM summary rewrite prompt quality | 🟡 | V1 | NPC-3b | Needs V1 prototype measurement |
| NPC-4 | Retrieval from knowledge-service (timeline-scoped, canon-faithful) | ❓ | V1 | — | [01 A4](01_OPEN_PROBLEMS.md#a4-retrieval-quality-from-knowledge-service--partial) — needs measurement |
| NPC-5 | NPC mood / flexible_state drift (LLM output updates per-reality) | 🟡 | V1 | NPC-2 | [02 §5.2](02_STORAGE_ARCHITECTURE.md) |
| NPC-6 | Canon-drift linter (post-response check vs L1/L2) | 🟡 | V1 | NPC-4, WA-3 | [01 G3](01_OPEN_PROBLEMS.md#g3-canon-drift-detection-in-production--open) |
| NPC-7 | Multi-NPC conversation turn arbitration | 🟡 | V2 | PL-1 | [01 B4](01_OPEN_PROBLEMS.md#b4-multi-user-turn-arbitration--partial), DF5 |
| NPC-8 | NPC daily routines when no player around | 📦 | V3 | NPC-1 | **DF1 — Daily Life** |
| NPC-9 | NPC memory decay / summarization (prevent unbounded growth) | 🟡 | V1 | NPC-3 | Part of A1 solution |
| NPC-10 | NPC tool calling (trigger world-state change via LLM) | 🟡 | V1 | PL-6 | [01 A5](01_OPEN_PROBLEMS.md#a5-tool-use-reliability-for-world-actions--partial) |
| NPC-11 | Classification (SillyTavern pattern — mood from last message) | 📦 | V3 | — | Feature comparison doc |

## PCS — PC Systems

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PCS-1 | PC state projection (location, status, stats, inventory) | ✅ | V1 | IF-1 | [02 §5.1](02_STORAGE_ARCHITECTURE.md), [04 §8](04_PLAYER_CHARACTER_DESIGN.md) |
| PCS-2 | PC inventory + item origin reality | ✅ | V1 | PCS-1 | [02 §5.1](02_STORAGE_ARCHITECTURE.md) (MV5 primitive P5) |
| PCS-3 | PC ↔ NPC relationship tracking | 🟡 | V1 | PCS-1 | [02 §5.1](02_STORAGE_ARCHITECTURE.md) |
| PCS-4 | PC stats model (simple state-based, no RPG mechanics) | 🟡 | V1 | PCS-1 | [04 §5.3](04_PLAYER_CHARACTER_DESIGN.md), PC-C3 locked, **DF7** concrete schema |
| PCS-5 | PC offline mode (visible + vulnerable) | 🟡 | V1 | PCS-1 | [04 §4.2](04_PLAYER_CHARACTER_DESIGN.md), PC-B2 locked |
| PCS-6 | PC `/hide` command + hidden status | 🟡 | V1 | PCS-5 | [04 §4.2](04_PLAYER_CHARACTER_DESIGN.md) |
| PCS-7 | PC-as-NPC conversion after prolonged hiding | 📦 | V2 | PCS-6, NPC-8 | **DF1 — Daily Life** |
| PCS-8 | PC death (event emission, per-reality outcome) | 🟡 | V1 | PCS-1, WA-5 | [04 §4.1](04_PLAYER_CHARACTER_DESIGN.md), PC-B1 locked; outcomes in **DF4** |
| PCS-9 | PC reclaim from NPC mode | 📦 | V2 | PCS-7 | **DF1** |
| PCS-10 | PC persona generation (LLM persona for NPC mode) | 📦 | V2 | PCS-7 | **DF8 — NPC persona from PC history** |

## SOC — Social

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| SOC-1 | Session as social unit (N PCs + M NPCs in one context) | 📦 | V1 | PL-1 | **DF5 — Session feature** |
| SOC-2 | Public session (in-region, all co-located participants join) | 📦 | V1 | SOC-1 | DF5 |
| SOC-3 | Private session (invite-only) | 📦 | V2 | SOC-1 | DF5 |
| SOC-4 | Whisper (1-to-1 private within session or across) | 📦 | V2 | SOC-1 | DF5 |
| SOC-5 | PvP within session | 📦 | V2 | SOC-1, WA-5 | DF5 + DF4 consent |
| SOC-6 | Multi-PC parties / raids / guilds | 🚫 | — | — | Explicitly rejected — sessions replace parties (PC-D1) |
| SOC-7 | Global chat | 🚫 | — | — | Explicitly rejected — session only (PC-D3) |
| SOC-8 | User reporting / content moderation UI | 📦 | PLT | SOC-1 | Standard platform feature |
| SOC-9 | Shadow-ban / sanctions | 📦 | PLT | SOC-8 | Standard |
| SOC-10 | NSFW opt-in / age verification | 📦 | PLT | — | [01 E2](01_OPEN_PROBLEMS.md) |

## NAR — Narrative / Canon

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| NAR-1 | Four-layer canon model (L1 axiomatic / L2 seeded / L3 local / L4 flexible) | ✅ | V1 | WA-3 | [03 §3](03_MULTIVERSE_MODEL.md) |
| NAR-2 | L3 event logging (every play emits durable events) | ✅ | V1 | IF-1 | [02 §4](02_STORAGE_ARCHITECTURE.md) |
| NAR-3 | L1 runtime enforcement (reject or lint output violating axiomatic canon) | 🟡 | V1 | NPC-6 | Part of NPC-6; may need DF4 integration |
| NAR-4 | L3 → L2 canonization flow (author-gated) | 📦 | V3 | NAR-2, WA-6 | **DF3 — Canonization** |
| NAR-5 | Canon-worthy action detection (flag interesting L3 events) | 📦 | V3 | NAR-2 | DF3 |
| NAR-6 | Canon-diff UI for author review | 📦 | V3 | NAR-4 | DF3 |
| NAR-7 | IP attribution for canonized content | 📦 | V3 | NAR-4 | DF3 + [01 E3](01_OPEN_PROBLEMS.md) |
| NAR-8 | L1/L2 author edit propagation (when book updates mid-lifetime) | ❓ | V3 | NAR-1 | [01 M4](01_OPEN_PROBLEMS.md#m4-inconsistent-l1l2-updates-across-reality-lifetimes--open) |

## EM — Emergent / Advanced (fork, travel, reality lifecycle)

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| EM-1 | Auto-fork on capacity (system-initiated, fresh seed) | ✅ | V1 | IF-3 | [03 §12.2](03_MULTIVERSE_MODEL.md), MV4-a locked |
| EM-2 | User-initiated fork (player creates alternate timeline) | ✅ | V1 | IF-3 | [03 §12.2](03_MULTIVERSE_MODEL.md), MV4-b locked |
| EM-3 | Auto-rebase at depth limit (flatten chain into fresh-seed) | ✅ | V1 | EM-2 | [03 §12.3](03_MULTIVERSE_MODEL.md), MV9 locked N=5 |
| EM-4 | DB subtree split at threshold (50M events or 500 players) | ✅ | V3 | IF-3 | MV8 locked |
| EM-5 | Reality freeze (no writes, reads OK) | ✅ | V2 | IF-11 | MV10 locked 30d |
| EM-6 | Reality archive (drop DB, events to MinIO) | ✅ | V2 | IF-11 | MV11 locked 90d |
| EM-7 | Reality close — safe multi-stage flow | ✅ | V1 | EM-6 | [02 §12I](02_STORAGE_ARCHITECTURE.md) (R9 locked) |
| EM-7a | 6-state close machine (active → pending_close → frozen → archived → archived_verified → soft_deleted → dropped) | ✅ | V1 | EM-7 | [02 §12I.1](02_STORAGE_ARCHITECTURE.md) (R9-L1) |
| EM-7b | Archive verification drill (checksum + sample decode + sample restore + diff) | ✅ | V1 | EM-6 | [02 §12I.3](02_STORAGE_ARCHITECTURE.md) (R9-L2) |
| EM-7c | Double-approval workflow for irreversible drop | ✅ | V1 | PO-1 | [02 §12I.4](02_STORAGE_ARCHITECTURE.md) (R9-L3) |
| EM-7d | 30-day cooling period with owner cancel | ✅ | V1 | EM-7a | [02 §12I.5](02_STORAGE_ARCHITECTURE.md) (R9-L4) |
| EM-7e | Player notification cascade (30/7/1 day) | ✅ | V2 | EM-7a | [02 §12I.6](02_STORAGE_ARCHITECTURE.md) (R9-L5) |
| EM-7f | Soft-delete via DB rename (not drop) + 90d hold | ✅ | V1 | EM-7a | [02 §12I.7](02_STORAGE_ARCHITECTURE.md) (R9-L6) |
| EM-7g | Emergency cancel at any pre-drop state | ✅ | V1 | EM-7a | [02 §12I.8](02_STORAGE_ARCHITECTURE.md) (R9-L7) |
| EM-7h | Full audit log of close state transitions | ✅ | V1 | EM-7a | [02 §12I.9](02_STORAGE_ARCHITECTURE.md) (R9-L8) |
| EM-8 | World travel — cross-reality PC movement | 📦 | V4 | IF-16, many primitives | **DF6 — World Travel** |
| EM-9 | Echo visit (read-only observation of another reality) | 📦 | V4 | IF-3 | DF6 sub-feature |
| EM-10 | Dimensional rift narrative events | 📦 | V4+ | EM-8 | DF6 |
| EM-11 | Reality "pin/protect" (prevent auto-freeze/archive) | 📦 | PLT | EM-5, EM-6 | Discussed but not locked |
| EM-12 | Freeze/archive warning notifications | 📦 | V2 | EM-5 | Discussed but not locked |

## PLT — Platform / Business

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PLT-1 | Tier system (Free / Pro / Enterprise) | 🟡 | PLT | PO-1 | Reuse [103_PLATFORM_MODE_PLAN](../103_PLATFORM_MODE_PLAN.md) |
| PLT-2 | Usage metering (LLM tokens, cost tracking per user) | 🟡 | PLT | IF-15 | Reuse usage-billing-service |
| PLT-3 | PC slot purchase | 📦 | PLT | PO-8 | **DF2** |
| PLT-4 | Fork quota + cost calculation | 📦 | PLT | EM-2 | Related to DF2 |
| PLT-5 | Admin panel (users, realities, content) | 📦 | PLT | — | [103_PLATFORM_MODE_PLAN §7](../103_PLATFORM_MODE_PLAN.md) |
| PLT-6 | Billing integration (Stripe) | 📦 | PLT | PLT-1 | [103_PLATFORM_MODE_PLAN §5](../103_PLATFORM_MODE_PLAN.md) |
| PLT-7 | IP / ToS / DMCA workflow | ❓ | PLT | — | [01 E3/E4](01_OPEN_PROBLEMS.md) |
| PLT-8 | Self-hosted mode (BYOK only, no platform features) | ✅ | INFRA | IF-14 | [103 §1](../103_PLATFORM_MODE_PLAN.md) |

## CC — Cross-cutting

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| CC-1 | Chat GUI extension — region sidebar, player list, NPC panel, action bar, dual stream | 🟡 | V1 | PL-1 | [03 §9.1, feature comparison doc](03_MULTIVERSE_MODEL.md) |
| CC-2 | Multi-language support per reality (display + input) | 🟡 | V1 | IF-16 | Locale per reality; reuse translation-service |
| CC-3 | In-reality cross-language translation (user types Vietnamese, NPC replies English then auto-translates) | 📦 | V2 | CC-2 | Reuse translation-service |
| CC-4 | Reality browser / map view | 📦 | V2 | PO-2 | UI detail TBD |
| CC-5 | Observability — per-reality health dashboard, event lag metrics | 🟡 | INFRA | IF-3 | Standard ops |
| CC-6 | Accessibility (screen reader, keyboard nav) | ❓ | V1 | — | Must not be afterthought |
| CC-7 | Author dashboard (cross-reality view of their book's play) | 📦 | V3 | WA-6 | DF3 |
| CC-8 | Macros / variables in prompts (`{{pc}}`, `{{scene}}`, `{{entity.alice}}`) | 🟡 | V1 | PL-4 | SillyTavern pattern |
| CC-9 | User preferences / settings (per-device + per-account) | 🟡 | V1 | PO-1 | Reuse existing pattern |

## DL — Daily Life (DF1 umbrella)

Scoped for clarity. Everything here is `📦 Deferred` under DF1.

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| DL-1 | NPC daily routines (sleep, work, travel, socialize) | 📦 | V3 | NPC-1 | DF1 |
| DL-2 | Converted PC behavior (when PC becomes NPC) | 📦 | V2 | PCS-7 | DF1 |
| DL-3 | NPC memory decay / periodic summarization | 📦 | V1/V2 | NPC-3 | Partially required for V1 (bounded memory) — design in DF1 |
| DL-4 | PC reclaim UX | 📦 | V2 | PCS-7 | DF1 |
| DL-5 | World simulation tick strategy (lazy-on-entry vs scheduled vs frozen) | ❓ | V3 | — | [01 B3](01_OPEN_PROBLEMS.md#b3-world-simulation-tick--open), DF1 |
| DL-6 | NPC persona generation from PC history | 📦 | V2 | PCS-10 | DF8, part of DF1 |

---

## Status summary

| Category | ✅ Designed | 🟡 Partial | 📦 Deferred | ❓ Open | 🚫 OOS | Total |
|---|---|---|---|---|---|---|
| IF | 56 | 4 | 2 | 0 | 0 | 62 |
| WA | 1 | 3 | 3 | 0 | 0 | 7 |
| PO | 6 | 2 | 1 | 0 | 0 | 9 |
| PL | 4 | 7 | 3 | 0 | 0 | 14 |
| NPC | 6 | 10 | 2 | 0 | 0 | 18 |
| PCS | 2 | 5 | 3 | 0 | 0 | 10 |
| SOC | 0 | 0 | 8 | 0 | 2 | 10 |
| NAR | 2 | 1 | 4 | 1 | 0 | 8 |
| EM | 14 | 0 | 5 | 0 | 0 | 19 |
| PLT | 1 | 2 | 4 | 1 | 0 | 8 |
| CC | 0 | 5 | 3 | 1 | 0 | 9 |
| DL | 0 | 0 | 5 | 1 | 0 | 6 |
| **Total** | **92** | **39** | **43** | **3** | **2** | **179** |

### Interpretation

- **92 Designed** (green): concrete decisions in locked docs — storage, fork, canon model, PC mechanics, R1 volume (6 layers), R2 rebuild (5 layers), R3 schema evolution (6 layers), R4 fleet ops (7 layers), R5 cross-instance (3 layers + anti-pattern), R6 publisher reliability (7 layers, resolves R12), R7 session concurrency + event handler (7 layers, reframed), R8 NPC memory aggregate split (7 layers, A1 foundation), R9 safe reality closure (8 layers, 6-state machine + 120d floor), R10 global ordering (ACCEPTED), R11 pgvector footprint (4 layers), R13 admin discipline (6 layers + governance policy).

**All 13 storage risks (R1–R13) resolved.**
- **40 Partial** (yellow): broad strokes designed, concrete detail pending (prompt assembly, retrieval quality, realtime).
- **43 Deferred** (blue): explicitly pushed to DF1–DF13 (DF12 withdrawn) future design docs or platform mode. Known but not gating V1.
- **3 Open** (red): identified but no approach — NPC-4 (retrieval quality), NAR-8 (L1/L2 propagation), CC-6 (a11y). A1 moved to PARTIAL with R8 infrastructure resolution.
- **2 Out of scope**: no parties (SOC-6), no global chat (SOC-7) — deliberate anti-MMO choices.

## V1 scope (solo RP, single reality)

Features marked `V1` (33 items) + required `INFRA` (17 items) = 50 total features to build for a working solo RP prototype.

Critical-path `❓ Open` blocking V1:
- **NPC-3** (per-PC memory) — needs [01 A1](01_OPEN_PROBLEMS.md#a1-npc-memory-at-scale--open) solution
- **NPC-4** (retrieval quality) — needs [01 A4](01_OPEN_PROBLEMS.md#a4-retrieval-quality-from-knowledge-service--partial) measurement

Non-blocking but must address:
- **PL-4** (prompt assembly) — concrete recipe needed
- **CC-6** (accessibility) — must not be afterthought

## V2 scope (coop, 2–4 players per reality)

Add `V2` items (18 items): session features (DF5), PvP, PC-as-NPC conversion (DF1 core), reality freeze/archive, swipe/regenerate, session replay, cross-language, freeze warnings.

## V3 scope (persistent multiverse)

Add `V3` items (14 items): DB subtree split, reality resurrect, author dashboard, canonization (DF3), L1/L2 propagation, NPC daily routines (DF1 full), world simulation tick, cross-reality browser.

## V4+ scope (vision, far-future)

Add `V4` items (4 items): world travel (DF6), echo visit, dimensional rifts, rich media (book import/export).

---

## Relationships visualized

```
                     FEATURE DEPENDENCY CLUSTERS

    ┌─────────────── INFRA (IF-*) ───────────────┐
    │ Storage → Registry → Realtime → LLM gateway │
    └───────────────────────┬─────────────────────┘
                            │
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
    ┌─────────────┐  ┌────────────┐  ┌──────────┐
    │ WORLD AUTH  │  │ PLAY LOOP  │  │ PLATFORM │
    │ (WA)        │  │ (PL)       │  │ (PLT)    │
    └──────┬──────┘  └──────┬─────┘  └────┬─────┘
           │                │             │
           ▼                ▼             ▼
    ┌──────────┐     ┌──────────┐    ┌──────────┐
    │ PO + PCS │     │ NPC      │    │ SOC      │
    │ (players)│     │ (AI chars)│   │ (groups) │
    └─────┬────┘     └────┬─────┘    └────┬─────┘
          │               │               │
          └───────┬───────┴───────────────┘
                  ▼
          ┌───────────────┐
          │ NAR (canon)   │
          │ EM (advanced) │
          │ DL (daily life│
          │ CC (UI/i18n)  │
          └───────────────┘
```

## References

- [00_VISION.md](00_VISION.md) — why this exists
- [01_OPEN_PROBLEMS.md](01_OPEN_PROBLEMS.md) — risks indexed by category
- [02_STORAGE_ARCHITECTURE.md](02_STORAGE_ARCHITECTURE.md) — IF-* detail
- [03_MULTIVERSE_MODEL.md](03_MULTIVERSE_MODEL.md) — WA-3, EM-1 to EM-6 detail
- [04_PLAYER_CHARACTER_DESIGN.md](04_PLAYER_CHARACTER_DESIGN.md) — PO, PCS, SOC detail; DF1–DF8 registry
- [OPEN_DECISIONS.md](OPEN_DECISIONS.md) — all locked + pending decisions
- [../References/SillyTavern_Feature_Comparison.md](../References/SillyTavern_Feature_Comparison.md) — inspirations for PL-*, NPC-*, CC-8
