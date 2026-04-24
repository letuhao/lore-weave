<!-- CHUNK-META
source: 01_OPEN_PROBLEMS.ARCHIVED.md
chunk: B_distributed_systems.md
byte_range: 9939-14106
sha256: 76a29d7a293acf8aec6331db7e996bb0bcec291120e85c64f729abcb3f3b1354
generated_by: scripts/chunk_doc.py
-->

## B. Distributed systems

### B1. World state concurrency — **KNOWN PATTERN**

**Problem:** Two players simultaneously `/take map`. Race condition.

**Why tractable:** Standard MMO/DB problem. Optimistic concurrency (version column), deterministic first-write-wins, narrate loser's failure ("the map is gone — someone grabbed it before you").

### B2. Real-time transport (WebSocket) — **KNOWN PATTERN**

**Problem:** Players need sub-second updates when other players act or NPCs speak. Scales to thousands of concurrent connections.

**Why tractable:** Standard pattern. LoreWeave already has a plan (`70_ASYNC_JOB_WEBSOCKET_ARCHITECTURE_PLAN.md`). Reuse.

### B3. World simulation tick — **PARTIAL**

**Problem:** Does the world do anything when no one is playing? If yes: NPCs age, events happen, rumors spread — compute cost grows unboundedly. If no: world is frozen in time between sessions, breaks immersion.

**Why hard:** Genuine product trade-off with cost implications. No universally right answer.

**Resolved by:** 3-mode tiered framework, per-reality configurable via World Rules (DF4):

- **V1 default = frozen** (B3-D1) — no between-session activity; NPCs resume where last session ended. Cheapest; matches V1 solo RP scope.
- **V2+ opt-in lazy-when-visited** (B3-D2) — cheap LLM summary on first player entering region after gap > 24h (default). 1 LLM call per region visit = bounded cost.
- **V3+ opt-in scheduled tick** (B3-D3) — nightly/weekly cron per reality with daily cost budget cap (`multiverse.simulation.daily_budget_usd`). Advances: NPC relationship drift (within R8-L4 decay), plotline beats, rumor propagation. Skip if idle > N days.
- **Reality clock** (B3-D4) — `reality_registry.reality_time` advances during active sessions; between-session advancement depends on mode.
- **Platform-mode tier-aware budget** (B3-D5) — free tier = frozen only; paid tiers opt-in to tick.

Decisions B3-D1..D5 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN`:**
- Tick pacing (NPC drift rate, rumor frequency) — V2+ playtest
- Real-sec → in-world-sec ratio default — V1 UX feedback
- Generative plotline beat quality — V3 prototype

### B4. Multi-user turn arbitration — **PARTIAL**

**Problem:** Three players in a tavern all talk to Elena at once. Elena responds to whom, in what order?

**Known approaches:**
- Round-robin with merge ("Elena looks between you three and says...")
- Priority by speech-act type (question > statement > aside)
- Per-PC streams (Elena responds to each privately, world events broadcast separately)

**Notes:** Probably solvable by UX convention rather than algorithm.

### B5. Rollback / point-in-time recovery — **PARTIAL**

**Problem (original):** Bug corrupts world state across instances with N active players. How to revert without losing hours of player progress?

**Resolved by:** Full event sourcing ([02 §4](02_STORAGE_ARCHITECTURE.md)) + snapshot fork ([03 §6](03_MULTIVERSE_MODEL.md)) + DB-per-reality ([02 §7](02_STORAGE_ARCHITECTURE.md)). Rollback = replay events to chosen point; blast radius = one reality. Snapshot-fork semantics means rollback of parent does not affect forked children — each reality is its own recovery domain.

**Residual `OPEN` bits:** event schema evolution during replay (R3 in 02), projection rebuild time at scale (R2 in 02), and "did the bug write events that shouldn't exist" — compensating events pattern needed for logical rollback without history mutation.

**Why hard:** Standard DB backup isn't enough — player perception of "what happened" now diverges from DB state. Need event-sourced architecture from day one, or accept data loss as SLA.

**Notes:** Event sourcing (every change as an append-only event) allows replay to any point. Overkill for V1; mandatory for any real V3.

### B6. Sharding at scale — **KNOWN PATTERN**

**Problem:** 10K+ users on one world instance overwhelms any single DB.

**Why tractable:** Classic MMO sharding: split by instance/region, federate queries only where needed. Not a V1 problem.

---

