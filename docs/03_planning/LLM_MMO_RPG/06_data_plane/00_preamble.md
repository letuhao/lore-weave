# 00 — Preamble: Why 06_data_plane Exists

> **Status:** LOCKED (foundation). Do not edit substance without reopening decision in `99_open_questions.md` first.
> **Scope:** Context, motivation, and relation to neighboring folders. No new requirements live here — only framing.

---

## 1. The two data problems this layer solves

Event-sourcing is the right authoritative storage model for a persistent-world LLM MMO — every change is an immutable, replayable, auditable fact, and canon integrity is enforceable at the log level. But event-sourcing alone cannot serve the gameplay hot path. Two concrete problems surface as soon as the system is under real play load:

### Problem 1 — Read-path cost

Reading the current state of an aggregate (player position, NPC mood, region inventory) by replaying events from the last snapshot is **O(events since snapshot)**. At MMO-scale gameplay, this is a per-request cost of dozens of milliseconds that scales with both player activity and snapshot age. Every NPC turn, every player action, every broadcast needs to read projection state, and the read-path dominates tail latency.

**The kernel in [02_storage/](../02_storage/) already solves the offline version of this** via projection tables and snapshot-anchored rebuild (see [R02](../02_storage/R02_projection_rebuild.md), [00_overview_and_schema](../02_storage/00_overview_and_schema.md)). What it does not solve is the runtime read-path cache — the layer that sits in front of those projection tables and serves hot reads at sub-50ms p99 without hitting Postgres.

### Problem 2 — Write-path frequency

Gameplay interactions are high-frequency and many are not durability-critical. Typing indicators, emote cues, cursor hovers, combat tick ticks, presence pings — writing each of these to the event log is both wasteful (event log bloat) and slow (synchronous Postgres write per tick is incompatible with MMO tick rates). But some writes — currency changes, item trades, canon writes — are the opposite: losing them is unacceptable even across node crashes.

**The existing kernel treats all writes the same: go through the event log.** This is correct for correctness, incorrect for performance. The data plane layer defines a **tier taxonomy** (DP-T0..T3 in [03_tier_taxonomy.md](03_tier_taxonomy.md)) so each write-path can pick its durability and performance characteristics explicitly, with the tier choice being a locked decision per feature rather than an ad-hoc runtime optimization.

---

## 2. Why a separate folder and not an extension of 02_storage

Three reasons:

1. **Separation of concerns.** `02_storage/` answers "how is durable state represented, evolved, and rebuilt?" This folder answers "how does game-layer code touch kernel state without breaking invariants?" They are different questions at different abstraction levels. Conflating them made `02_STORAGE_ARCHITECTURE.md` grow to 10k lines.

2. **Kernel contract visibility.** Every gameplay feature must conform to the access pattern defined here. Burying it as one more chunk among 36 R/S/C/SR entries in `02_storage/` makes it invisible as a contract layer. A dedicated folder with its own `_index.md` makes it discoverable and referenceable.

3. **Parallel agent work.** Multiple agents designing different gameplay features will reference this folder concurrently. Keeping it small and scoped (one subfolder, locked content) prevents contention with `02_storage/` where storage engineering changes happen.

---

## 3. What this folder is NOT

- **Not a storage redesign.** The durable tier (DP-T3) delegates entirely to [02_storage/](../02_storage/)'s event log + projection model. Nothing in 02 changes.
- **Not a feature catalog.** This folder defines a contract; [catalog/](../catalog/) lists features that conform to it.
- **Not a Python/LLM concern.** The Python roleplay-service is an event producer, not a kernel writer. Its integration protocol is deferred (see [99_open_questions.md](99_open_questions.md)) and does not gate foundation design.
- **Not a V1 requirement.** V1 (solo RP) may run entirely against direct Postgres projections without cache. The contract defined here anchors V2 (coop) and V3 (MMO-lite). V1 services are still expected to use the SDK — they just hit the durable path more often.

---

## 4. Relation to neighboring folders

| Folder | How this folder depends on it | How this folder constrains it |
|---|---|---|
| [02_storage/](../02_storage/) | Durable tier (DP-T3) writes into the event log + reads from projection tables per R01–R13 design. Snapshot/rebuild algorithms (R02) are the truth for durable-tier rebuild. | 02's write and read APIs are reached only through the DP SDK — no service connects to the kernel Postgres directly. |
| [03_multiverse/](../03_multiverse/) | Canon layers L1–L4 and per-reality DB isolation are preserved in cache keying: cache keys are `{reality_id}:{aggregate_type}:{aggregate_id}`. Cross-reality reads go through the same cross-instance policy (R5). | DP does not introduce new cross-reality coordination; it respects the existing boundary. |
| [04_player_character/](../04_player_character/) | PC aggregates pick a tier per field (e.g. currency = T3, position = T1). DF items coming from PC designs plug into DP through the tier they pick. | PC designs must declare tier choice per field in their own doc; DP does not pre-classify PC fields. |
| [05_llm_safety/](../05_llm_safety/) | LLM-produced commands enter the write path as events, routed by the intent classifier + command dispatch. | DP validates that all LLM-originated writes go through the T3 path (canon-affecting) or T2 path (session-scoped), never T0/T1. |
| [catalog/](../catalog/) | Every feature gets a tier assignment when it graduates from "catalog row" to "detailed design". | DP is the constraint that forces feature designers to answer the tier question explicitly. |

---

## 5. Conversation trail that produced this folder

Captured here so future sessions see why the decisions below are locked, not as things to revisit by default.

- **User flagged two data problems** — event-sourcing read cost and hot-path write frequency — and proposed a data layer above the kernel. Gap analysis against 02_storage (R02 projection rebuild, S01_03 session memory, R07 concurrency) confirmed the hot-path runtime cache and tier taxonomy were genuinely not designed.
- **Scope choice: Option C.** User chose maximum scope — this folder owns the kernel access contract; `02_storage/` is implementation detail behind the SDK. This makes "no service bypasses the contract" achievable.
- **Architecture model: Control Plane / Data Plane split.** Rejected the single-gateway-service model on hot-path latency grounds. Accepted the library-first pattern where the SDK is embedded in game services and enforces policy at the call site; the control plane is a thin service owning policy, schema, and invalidation.
- **Language: Rust for game layer.** Initial recommendation of Go was revised after the user clarified that AI (not human) is the coder, which invalidates human-learning-curve arguments and reframes compile-time contract enforcement as high-value (not high-cost). Platform Go services and LLM Python services stay as they are.
- **Cache technology: Redis.** Standard, already in LoreWeave's stack, adequate pub/sub for invalidation broadcast.
- **Scale anchor: V3 = 200–500 CCU per reality, 10k total across realities**, with 50ms p99 own-client ack and 200ms p99 broadcast to other players.
- **Tier count: four.** T0 ephemeral, T1 volatile, T2 durable-async, T3 durable-sync. Covered in detail in [03_tier_taxonomy.md](03_tier_taxonomy.md).

These decisions are locked. The axioms in [02_invariants.md](02_invariants.md) encode them as referenceable items (DP-A1..A9). Changes require an entry in [99_open_questions.md](99_open_questions.md) and a superseding decision in [../decisions/](../decisions/).
