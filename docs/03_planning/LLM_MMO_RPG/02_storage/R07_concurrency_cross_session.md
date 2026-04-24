<!-- CHUNK-META
source: 02_STORAGE_ARCHITECTURE.md
chunk: R07_concurrency_cross_session.md
byte_range: 90615-103908
sha256: f9232c96050c1c91b13ffed7479458307a7994aa513f30aa65322564264c1d5c
generated_by: scripts/chunk_doc.py
-->

## 12G. Session as Concurrency Boundary + Cross-Session Event Handler (R7 mitigation)

R7 initially framed as "multi-aggregate transaction deadlocks." Re-examination: **game is turn-based, session is the concurrency unit**. Intra-session writes are sequential by design — no deadlocks possible. The real R7 is cross-session effect propagation when an event's scope exceeds the originating session (e.g., spell destroys tavern → affects all 5 sessions in the tavern).

This reframes R7 from a locking problem into an event-routing problem. Supersedes the multi-aggregate concurrency framing in §8.

### 12G.1 Core insight — session is the concurrency unit

Every event lives in exactly one session while player-active. Within a session, turns are strictly sequential:

```
Session turn sequence (example):
  T=0: Alice speaks
  T=1: Elena (LLM) responds
  T=2: Bob speaks
  T=3: Bartender (LLM) responds
  ...
```

At any moment, **exactly one command is being processed** per session. No concurrent writes → no deadlocks → no lock contention.

Multiple sessions can run in parallel within a reality — but they touch different aggregates (different PCs, different NPCs if disjoint, or same NPC only if NPC is in multiple sessions simultaneously — see §12G.7).

**Superseded concerns from §8:**
- §8.2 multi-aggregate lock order discipline → unnecessary within session (serial by design)
- §8.3 hot NPC contention → solved at session level (NPC in 1 session at a time via busy-lock, see §8.3 unchanged)
- §8.4 per-reality single writer → replaced by per-session single writer (finer grain, higher throughput)

Optimistic concurrency (§8.1) still valid as defense-in-depth for cross-session collisions.

### 12G.2 Pillar A — Session as single-writer command processor

**Mandatory architecture.** Every session has exactly one command processor (goroutine or dedicated worker) that processes commands in strict FIFO order:

```go
// Pseudocode — session command loop
func sessionProcessor(sessionID UUID) {
    for cmd := range sessionCommandQueue(sessionID) {
        // 1. Load state (short read, no locks persist after)
        state := loadSessionState(sessionID)

        // 2. LLM + retrieval OUTSIDE tx (can be seconds)
        response := llmProcess(state, cmd)

        // 3. Write tx — short, serial per session
        tx := db.Begin()
        appendEvents(tx, response)          // scoped to session by default
        updateProjections(tx)
        insertOutbox(tx)
        tx.Commit()
    }
}
```

**Properties:**
- No DB-level locks needed within session — serial commits don't contend
- LLM call happens between commits (async), but each session has ≤1 LLM call in flight
- Throughput per session = 1 / (LLM latency + commit latency) ≈ 1 turn / 5s
- Sessions in parallel scale horizontally — N sessions = N processors

**Schema cleanup:**
```sql
-- Remove opt-in single-writer mode — now mandatory at session level
ALTER TABLE reality_registry
  DROP COLUMN command_processor_mode;  -- no longer configurable
```

### 12G.3 Pillar B — Cross-session event propagation (DF13)

Events emitted within a session may have **wider scope**. Handler routes them to other affected sessions.

**Scope tagging on events:**
```sql
ALTER TABLE events
  ADD COLUMN scope TEXT NOT NULL DEFAULT 'session';
-- 'session' | 'region' | 'reality' | 'world'
```

**Scope semantics:**

| Scope | Propagation | Example |
|---|---|---|
| `session` | None — default, intra-session only | PC speaks to NPC in same session |
| `region` | Fan out to all sessions in same region | Spell destroys tavern, weather shifts |
| `reality` | Fan out to all active sessions in reality | World clock tick, reality-wide event |
| `world` | Routed via `xreality.*` (§12E) | Canon update from book, cross-reality |

### 12G.4 Session event queue

Each session has an inbox for cross-session events:

```sql
CREATE TABLE session_event_queue (
  queue_id            BIGSERIAL,
  session_id          UUID NOT NULL,
  source_event_id     BIGINT NOT NULL,
  source_session_id   UUID,                      -- NULL if from system/world tick
  scope               TEXT NOT NULL,
  payload             JSONB NOT NULL,
  status              TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'applied' | 'skipped' | 'failed'
  enqueued_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  applied_at          TIMESTAMPTZ,
  PRIMARY KEY (session_id, queue_id)
);
CREATE INDEX session_event_queue_pending_idx
  ON session_event_queue (session_id, enqueued_at)
  WHERE status = 'pending';
```

Lives in each reality DB (scoped to reality).

### 12G.5 Event-handler service (`services/event-handler/`)

Dedicated Go service. Separate from `publisher` (different concern, different scale).

**Architecture:**
```
event-handler process:
  - Tracks cursor per reality (last processed event_id)
  - Polls events table: WHERE event_id > cursor AND scope != 'session'
  - For each:
     a. Determine affected sessions based on scope:
        - 'region' → query active sessions WHERE region_id = event.region_id
        - 'reality' → query all active sessions in reality
        - 'world' → defer to xreality.* handler (§12E, out of scope for this service)
     b. Insert session_event_queue rows for each affected session
     c. Advance cursor
```

**Cursor table** (per reality DB):
```sql
CREATE TABLE event_handler_cursor (
  cursor_name           TEXT PRIMARY KEY,        -- 'primary' (could have replayers)
  last_routed_event_id  BIGINT NOT NULL DEFAULT 0,
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Consumer — session processor updated:**
```go
func sessionProcessor(sessionID UUID) {
    for {
        // Priority 1: pending queue items (cross-session events)
        if qItem := popQueueItem(sessionID); qItem != nil {
            processQueueItem(sessionID, qItem)  // LLM reacts, commits
            continue
        }

        // Priority 2: user turn input
        if cmd := waitForUserInput(sessionID, timeout); cmd != nil {
            processUserTurn(sessionID, cmd)
            continue
        }
    }
}
```

Queue items processed **before** user input — environmental effects feel immediate.

### 12G.6 Propagation semantics

**Async (default, V1):**
- Originating session commits, moves on
- Affected sessions pick up at their next processor tick
- Latency: seconds (bounded by active session's next idle moment)
- No coordination between sessions

**Sync (deferred, V2+ if specific feature demands):**
- Originator blocks until affected sessions acknowledge
- Adds cross-session coordination complexity
- Only for rare consistency-critical effects

**Ordering guarantees:**
- Within a target session: queue items processed FIFO by `enqueued_at`
- Cross-session: no ordering — session A and session B may see related events in different orders at different times
- Single-writer per session + FIFO queue ensures within-session consistency

**Conflict handling:**
- If session B has a pending user turn AND an incoming queue item, queue item runs first
- If session B's own events contradict incoming event (e.g., both sessions try to destroy the tavern) → both events apply in order; LLM narrates second one appropriately ("the rubble collapses further...")
- No rollback of player actions based on cross-session events

**Idempotency:**
- Queue item has `source_event_id` — if event-handler retries insertion, unique constraint ensures deduplication
- Session processor marks `status='applied'` in same tx as event commit → crash recovery safe

### 12G.7 NPC in multiple sessions simultaneously

Edge case: a key NPC (quest giver) is in sessions 1 and 2 simultaneously. How?

**V1 answer:** NPCs CANNOT be in multiple sessions simultaneously. Each NPC has a `current_session_id` field; attempting to join a second session fails or forces context switch (NPC leaves session 1, joins session 2).

```sql
ALTER TABLE npc_projection
  ADD COLUMN current_session_id UUID;
-- NULL = not in any session (available)
```

If player in session B wants to talk to NPC already in session A: UI says "Elena is currently with [Alice's group] — wait for them to finish."

This avoids the hardest concurrency: same NPC responding to 2 conversations at once.

**V2+ alternative (REJECTED 2026-04-24):** "multi-presence NPC" was previously framed as deferred V2+ alternative. **Upgraded to permanent rejection** per H3 review — realistic world semantics preferred over MMO cloning. NPC single-session is design intent, not scaling workaround. Popular-NPC bottleneck solved by session caps + queue UX (see [§12R.1](#12r1-session-size-caps--queue-ux-h3-revised)).

### 12G.8 Worked example — spell destroys tavern

```
T=0: Session 1 (Alice's table): Alice casts destroy-tavern spell
T=1: Session 1 processor:
       LLM resolves → emits events:
         pc.cast_spell (scope='session')
         spell.triggered (scope='session')
         region.destroyed (scope='region', region_id=tavern)   ← wider scope
       Commit to session 1 + outbox + events table

T=2: event-handler tails events, sees scope='region':
       Queries active sessions where region_id=tavern → finds sessions 2, 3, 4, 5
       Inserts session_event_queue rows for each:
         { scope='region', payload={type:'tavern_destroyed', source_session:1, ...} }

T=3-7: Sessions 2, 3, 4, 5 at next processor tick each:
       Pop queue item
       LLM narrates: "The walls collapse around you!"
       Emit events in own session (scope='session')
       Commit

Final state:
  - Session 1: destroyed_by_alice event recorded
  - Sessions 2-5: each has own reaction events
  - Region state: tavern marked destroyed
  - Players in all 5 sessions see consistent destruction
```

No locks. No deadlocks. No retries. Async propagation ~seconds.

### 12G.9 Accepted trade-offs

| Layer | Cost |
|---|---|
| L1 single-writer per session | Throughput per session bounded by LLM latency — matches turn-based design |
| L2 scope tagging | Every event has scope column; design discipline for producers |
| L3 event-handler service | New dedicated service to operate; cursor lag monitoring |
| L4 session event queue | Extra table per reality DB; small, short-lived rows |
| L5 priority (queue before user input) | User may see environmental event before their own turn commits — design feature, not bug |
| L6 NPC single-session constraint (V1) | UX gate when NPC busy; simpler than multi-presence |
| L7 observability | Standard metric overhead |

**Removed from original R7:** lock-order helper, optimistic-retry loops, pre-check reads, multi-aggregate deadlock handling. All unnecessary with session-as-concurrency-unit.

### 12G.10 Key interactions

- **R7 ↔ DF5 (Session feature)**: DF5 owns session lifecycle (create, join, leave); §12G owns concurrency semantics. DF5 design MUST implement single-writer pattern from §12G.2.
- **R7 ↔ DF13 (Event Handler)**: DF13 is the admin + operational UX over event-handler service. Mechanisms locked here, admin UI deferred.
- **R7 ↔ R6 (publisher)**: publisher broadcasts events to connected clients (UX); event-handler routes to other sessions (game state). Both tail events table but track independent cursors. No overlap.
- **R7 ↔ A1 (NPC memory)**: NPC memory updates happen within the session NPC is currently in. No cross-session memory contention.

### 12G.11 Config keys

```
event_handler.poll_interval_ms = 100
event_handler.batch_size = 100
event_handler.cursor_lag_warn_seconds = 30
event_handler.cursor_lag_page_seconds = 120
session.queue_priority = "queue_before_user_input"  # V1 default
session.npc_busy_policy = "single_session"          # V1: NPC in 1 session at a time
session.event_queue_retention_days = 30              # keep applied queue items for audit
```

### 12G.12 Implementation ordering

- **V1 launch**: L1 (session single-writer — part of DF5 Session feature), L2 (scope column + event tagging discipline), L3 (event-handler service MVP), L4 (session_event_queue table + consumer logic), L5 (priority rules), L6 (NPC single-session constraint), L7 (metrics)
- **V1 + 30 days**: DF13 admin UX mature (queue inspection, propagation lag dashboard)
- **V2**: evaluate sync propagation if specific feature demands; evaluate NPC multi-presence
- **V3+**: Advanced scope semantics (e.g., delayed scope, conditional propagation)

### 12G.13 Tooling surface (DF13)

Dedicated admin + dev tooling for cross-session effects:
- Event handler health dashboard (cursor lag per reality)
- Session event queue inspector (pending, applied, failed per session)
- Scope distribution analytics (how often region/reality events fire)
- Manual event propagation trigger (admin tool for debugging / fixup)
- Queue replay after bug fix (re-enqueue failed items after root cause resolved)

Deferred to **DF13 — Cross-Session Event Handler**. Mechanisms (L1–L7) locked here in §12G; admin UX + dev tooling scope of DF13.

