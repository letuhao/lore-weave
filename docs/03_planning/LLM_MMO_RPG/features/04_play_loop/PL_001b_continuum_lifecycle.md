# PL_001b — Continuum Lifecycle (Sequences + Bootstrap + Acceptance)

> **Continued from:** [`PL_001_continuum.md`](PL_001_continuum.md). That file holds the contract layer (§1-§10): user story, domain concepts, aggregate inventory, tier table, DP primitives, capability claims, subscribe patterns, pattern choices, failure-mode UX, cross-service handoff. This file holds the dynamic layer (§11-§20): end-to-end sequences, reconnect/idempotency, rejection path, bootstrap, acceptance criteria, deferrals, cross-references, readiness.
>
> **Conversational name:** "Continuum lifecycle" (CON-L). Read [`PL_001_continuum.md`](PL_001_continuum.md) FIRST — this file assumes you know the aggregates and primitives.
>
> **Category:** PL — Play Loop (core runtime)
> **Status:** CANDIDATE-LOCK 2026-04-25 (split from PL_001 to honor 800-line cap)
> **Stable IDs in this file:** none new — all aggregates and primitives are defined in PL_001 (root). This file references them.
> **Builds on:** PL_001 §1-§10. Same DP contracts (DP-A1..A19, DP-T0..T3, DP-R1..R8, DP-K1..K12, DP-Ch1..Ch53).

---

## §11 Sequence: one normal turn (Session 1, Turn 4 — PC says "Tiểu nhị, lấy cho ta một bình trà")

```text
UI: type text + send → gateway POST /v1/turn

gateway → roleplay-service:
  intent = FreeNarrative (Speak)
  PL-4 prompt assembly with NPC=Tiểu Thúy + scene from SceneState read
  PL-5 LLM stream → narrator_text "Tiểu Thúy mỉm cười, gật đầu rồi quay đi pha trà..."
  PL-19/PL-20 sanitize/filter passes
  emit proposal: TurnProposal { actor: pc_id, intent: Speak, narrator_text, fiction_duration: 30s }

world-service (consumer):
  PL-15 classify (cross-check): Speak ✓
  PL-16 oracle: tea-pot exists in scene props ✓
  PL-21 retrieval-isolation: ok ✓
  claim_turn_slot
  advance_turn(turn_data=TurnEvent::Speak { ... })           → T1
  t2_write FictionClock += 30s                                → T2
  release_turn_slot
  return T2 to gateway

UI: subscribe-stream delivers TurnEvent → render narrator_text + advance clock display

NPC react (next turn, automatic):
  world-service schedules NPC turn for Tiểu Thúy
  emit NPC proposal via internal LLM call
  → same flow, ending with another advance_turn
```

Wall-clock budget per turn (DP latency budgets): claim_turn_slot ≤10ms + advance_turn ≤50ms (T2 ack) + t2_write ≤5ms + release ≤5ms = **~70ms DP overhead**. The dominant cost is LLM streaming (1-10s, NOT in DP scope).

---

## §12 Sequence: `/sleep until dawn` (Session 2, Turn 11 — 8h fast-forward, day-boundary crossed)

```text
PC turn 10 ends at 1256-thu-day3-Tý-sơ (~23h00). PC types "/sleep until dawn".

gateway → roleplay-service:
  intent = MetaCommand → Sleep
  args = { until: "dawn" }

world-service:
  resolve dawn = next Mão-sơ from current FictionClock = ~5h00 of day4
  fiction_duration = 6h (Tý-sơ → Mão-sơ across day boundary)
  validate world-rule: PC is in a rented room (scene metadata.private_safe=true) ✓
  validate canon: nothing canonical happens to Lý Minh between 23h-5h that night ✓
  (if siege starts here — see SPIKE_01 obs#15 — world-rule rejects sleep, returns CommandRejected)

  claim_turn_slot
  advance_turn(turn_data = FastForward { fiction_duration: 6h })  → T1 (turn_number incremented by 1)
  t2_write FictionClock += 6h                                       → T2 (day boundary crossed; day=4, sub_day=Mão-sơ)
  release_turn_slot
  return T2

LLM-narration step (decoupled):
  roleplay-service polls for FictionClock projection with wait_for=T2, generates wake-up narration
  emit a follow-up TurnEvent::Narration via internal command (NOT a new turn — same turn_number)

UI: clock advances visually; narrator_text "Lý Minh tỉnh giấc khi gà gáy lần đầu..."
```

**MV12-D5 validation (date-boundary):** SPIKE_01 observed that day boundary is "atomic" — no events occur between 23h and 5h that PC sees, because the only writer (PC's own cell) is in fast-forward mode. Other realities at the parent tavern level may have events, but bubble-up is filtered by `paused_until`-equivalent semantic at the cell (cell is in fast-forward = effectively unsubscribed from ambient).

V1 implementation: cell does NOT pause on fast-forward; instead, world-service's bubble-up consumer drops events with `arrived_at_cell_after_fast_forward_completes` flag set. Detail in PL_002 (gossip aggregator).

---

## §13 Sequence: `/travel` (Session 2, Turn 16-17 — 23-day fiction-time + cross-cell move)

The most multi-step sequence. PC at `cell:yen_vu_lau` types `/travel to Tương Dương`. Five DP ops execute in order, each producing a CausalityToken. The LAST token (T5) is what UI passes to its post-travel reads.

```text
                                     ┌─────────────────┐
PC types "/travel..." ──► gateway ──►│ roleplay-service│  intent=MetaCommand→Travel
                                     │   (Python LLM)  │  args={dest: tương_dương, days: ~23}
                                     └────────┬────────┘
                                              │ proposal event
                                              ▼
                                     ┌─────────────────┐
                                     │  world-service  │  consumes proposal
                                     │     (Rust)      │
                                     └────────┬────────┘
                                              │
   ① claim_turn_slot(cell, pc_id, 15s)        │
   ─ WRITER NODE BIND ────────────────────────┤
                                              │
   ② advance_turn(old_cell, FastForward 23d) ─┼─► T1 (channel_event_id=N)
                                              │   turn_number incremented
                                              │
   ③ t2_write::<FictionClock>(+23d) ──────────┼─► T2 (reality outbox)
                                              │   day=26, season=thu still
                                              │
   ④ resolve target cell:                     │
       existing_cell = query_scoped_reality<  │
         ChannelMetadata>(level=cell,         │
         place_canon_ref="tương_dương_west")  │
       IF none:                               │
         new_cell = create_channel(           │
           parent=town_tương_dương,           │
           level_name="cell",                 │
           metadata={place_canon_ref:..,      │
                     created_at_turn: T1.turn_number+1})
                                              │
   ⑤ move_session_to_channel(target_cell) ────┼─► T3 + emits 2 canonical events:
                                              │     MemberLeft(old_cell, pc_id, Move)
                                              │     MemberJoined(new_cell, pc_id, Move)
                                              │
   ⑥ t2_write::<ActorBinding>(pc_id,          ┼─► T4
        MoveTo{ target_cell, T1.turn_number}) │
                                              │
   ⑦ t2_write::<SceneState>(target_cell,      ┼─► T5 (LAST — return this to gateway)
        Initialize{primary_actor: pc_id,      │
                   ambient: <derived from canon at fiction-time day 26>})
                                              │
   release_turn_slot(target_cell)             │
                                     ┌────────┴────────┐
                                     │     gateway     │
                                     └────────┬────────┘
                                              │ 200 OK { causality_token: T5,
                                              │           new_session_ctx,
                                              │           new_cell, new_fiction_time }
                                              ▼
                                     ┌─────────────────┐
                                     │       UI        │  re-bind multiplex stream
                                     │                 │  read FictionClock + SceneState
                                     │                 │    with wait_for=Some(T5),
                                     │                 │    causality_timeout=20s
                                     └─────────────────┘
```

**Why T5 is sufficient:** all 5 acks come from the same writer node within one turn-slot session, so the projection-applier's `last_applied_event_id` advances monotonically. Reading with `wait_for=T5` implicitly satisfies T1..T4 because T5 was the last commit.

**Edge cases:**

- **Target cell already exists** (e.g., another PC was there): step ④ skips `create_channel`; both PCs may now share the cell as long as cardinality < 32 (PL_001 §3.7 limit).
- **`MemberLeft`/`MemberJoined` ordering across the move:** DP guarantees the pair is atomic per DP-A18 §c — both are emitted as a single channel-event-pair on the source/target cell respectively, ordered by `move_session_to_channel`'s implementation.
- **Failure between ④ and ⑤:** new cell created, session not moved → cell goes Dormant per DP-Ch32 if no session ever joins; world-service GC sweeps Dormant cells with no membership history after 24h wall-clock.
- **Failure between ⑤ and ⑥/⑦:** session moved, ActorBinding/SceneState not committed → next read of `actor_binding` returns the OLD cell, but the session's `current_channel_id` says new cell. Inconsistency window ≤5s. world-service replays from outbox on writer-node restart — pending writes complete or compensate. UI sees "đường đi đang dệt..." per PL_001 §9 `CausalityWaitTimeout`.
- **Target cell at max capacity:** step ④ rejects with `WorldRuleViolation { rule_id: "cell_capacity" }`; entire chain aborted; turn-slot released; `fiction_clock` UNCHANGED (per §15 rejection path); UI shows "quán đông quá, chọn nơi khác?".

---

## §14 Sequence: reconnect / resume + idempotency (UX-critical)

UI loses connection between `submit /verbatim` and `200 OK`. UI's reconnect logic + server's idempotency cache prevents duplicate turn commits.

### 14.1 Client side

```text
ON UI submit:
  let key = uuid::v4()                 // generate fresh per turn
  POST /v1/turn { session_id, turn_text, idempotency_key: key }
  store key in localStorage as "pending_turn:<session_id>:<key>"
  await response with 30s timeout

ON timeout / network failure:
  IF session reconnects:
    GET /v1/turn/status { session_id, idempotency_key: key }
    response branches:
      (a) Committed { event_id, causality_token } → resume normally with token
      (b) InFlight                                  → wait + poll every 2s, max 30s
      (c) NotFound                                  → first attempt was lost; retry POST with SAME key
      (d) Rejected { reason }                       → render reject UX (§15)
    on success or terminal: clear localStorage entry
```

### 14.2 Server side (gateway)

```text
on POST /v1/turn:
  cache_key = (session_id, idempotency_key)
  IF cache_key in cache:
    return cached_response                            # exact-once guarantee within 60s
  ELSE:
    cache[cache_key] = InFlight { started_at = now }
    forward to roleplay-service / world-service chain
    on chain complete:
      cache[cache_key] = response                     # Committed | Rejected
      schedule cache eviction at now + 60s

on GET /v1/turn/status:
  IF cache_key in cache: return cache[cache_key]
  ELSE: return NotFound  (interpreted as "first attempt never reached us")
```

### 14.3 Lost-server-state recovery

If gateway crashes mid-turn (cache lost), client's retry with same key gets `NotFound` and re-submits. Server-side double-commit is prevented because:

- `advance_turn` itself is **NOT** idempotent on key alone (DP doesn't see the key). But:
- world-service stores `(idempotency_key → channel_event_id)` mapping in a per-reality T2 aggregate `turn_idempotency_log` (RealityScoped, 60s TTL via background sweeper) BEFORE calling `advance_turn`. Second invocation finds the existing event_id and short-circuits.
- This pushes the idempotency boundary into world-service rather than gateway alone — **defense in depth**.

```rust
#[derive(Aggregate)]
#[dp(type_name = "turn_idempotency_log", tier = "T2", scope = "reality")]
pub struct TurnIdempotencyLog {
    #[dp(indexed)] pub idempotency_key: Uuid,
    pub channel_event_id: u64,
    pub committed_at: Timestamp,                 // for sweeper TTL
}
```

**Why T2 + Reality:** the lookup is hot-path-adjacent (one extra indexed read per turn) but the data must survive a gateway restart. RealityScoped because keys are per-reality (a key collision across realities is fine — separate streams).

**Eviction:** background task sweeps `committed_at < now - 60s`. Sweep cadence 30s. Worst case: extra ~120s before key is reusable, which exceeds the PL_001 §3.7 60s TTL — that's intentional safety margin.

### 14.4 Limits

- One in-flight turn per session at a time (per PL_001 §8.1 Strict turn-slot). A second submit with a DIFFERENT key while one is in-flight → reject with `RejectReason::WorldRuleViolation { rule_id: "concurrent_turn" }`.
- Idempotency key is a 128-bit UUID v4; collision probability negligible.
- Cache size bound: `max_concurrent_sessions × 2` in gateway memory. At V1 scale (10k concurrent sessions) that's ~20k entries, ~3 MB.

---

## §15 Sequence: rejection path (world-rule rejects turn)

PC at `cell:yen_vu_lau` types `/sleep until dawn` while a tavern brawl event has just bubbled up (cell is in active-combat state). World-rule says no.

**Key mechanism:** rejected turns commit a `TurnEvent` channel event via the standard `dp::t2_write::<TurnEvent>` primitive — **NOT** via `dp::advance_turn`. Per DP-A17 §c, only `advance_turn` increments `turn_number`; every other channel-event commit (including this `t2_write`) tags with the CURRENT (un-incremented) `turn_number`. This honors MV12-D11 ("fiction_clock and turn_number advance only on accepted turns") without requiring any new DP primitive.

```text
gateway: POST /v1/turn { idempotency_key=K, turn_text="/sleep" }

roleplay-service:
  intent=MetaCommand → Sleep
  proposal emitted

world-service consumer:
  validator pipeline (Strict turn-slot, claim slot first):
    ① claim_turn_slot(cell, pc_id, 5s, reason="validation")
    ② schema validate: ok
    ③ capability check: ok
    ④ A5 intent classify: ok
    ⑤ A3 oracle: pc.in_combat? → TRUE  ─► REJECTION POINT
    ⑥ stop pipeline
    ⑦ build TurnEvent {
         outcome: Rejected { reason: WorldRuleViolation {
                              rule_id: "no_sleep_during_combat",
                              detail: "tửu lâu đang loạn, không ngủ được" } },
         narrator_text: None,
         fiction_duration_proposed: 0,
         idempotency_key: K, ...
       }
    ⑧ dp.t2_write::<TurnEvent>(ctx, channel, event_id, payload)
         → commits at turn_number = N (current — NOT N+1)
         → t2_ack returns CausalityToken
    ⑨ release_turn_slot
    ⑩ return ack to gateway
```

Then gateway:
```text
HTTP 200 OK with body {
  outcome: Rejected,
  reason: { kind: "world_rule_violation",
            rule_id: "no_sleep_during_combat",
            detail: "tửu lâu đang loạn, không ngủ được" },
  causality_token: T (from t2_write ack),
  turn_number: N (unchanged),
  fiction_time: <unchanged>,
  retry_allowed_in_seconds: 0
}
```

UI renders:
> ⚠ Lý Minh không thể ngủ — tửu lâu đang loạn, không ngủ được. (Thử /run hoặc /fight?)

**Audit query** (operator debugging "why is PC bouncing?"):

```sql
SELECT * FROM channel_events
WHERE channel_id = $cell
  AND payload->>'event_type' = 'TurnEvent'
  AND payload->>'outcome' = 'Rejected'
  AND committed_at > now() - interval '1 hour'
ORDER BY channel_event_id DESC;
```

Backed by indexed projection in world-service.

**MV12-D11 honored:** `fiction_clock` not advanced. `turn_number` not advanced. PC may immediately retry with a different command (no penalty turn-slot). Idempotency key for THIS submit is still consumed (§14 cache holds the Rejected response for 60s — preventing accidental double-submit + UX showing the same reject toast twice).

---

## §16 Bootstrap: book → reality init (hybrid model — Q2 decision)

Reality creation is when a book becomes a playable world. PL_001 locks the **hybrid model** (decision Q2 = option (c)): book manifest declares root channels + initial fiction_clock; cells are created lazily as players arrive.

### 16.1 Book manifest (declared at book ingestion, NOT a PL_001 aggregate)

The book → reality pipeline (owned by knowledge-service, not PL_001) emits a `RealityManifest` to the world-service before reality activation:

```rust
// Owned by knowledge-service / book-ingestion pipeline.
// PL_001 only consumes this contract.
pub struct RealityManifest {
    pub reality_id: RealityId,
    pub book_canon_ref: BookCanonRef,
    pub starting_fiction_time: FictionTimeTuple,        // e.g. (1256, Thu, 3, ThânSơ)
    pub root_channel_tree: RootChannelDecl,             // continent → country → district → town hierarchy
    pub canonical_actors: Vec<CanonicalActorDecl>,      // book-canon NPCs and their initial cells
    pub schema_version: u32,
}

pub struct RootChannelDecl {
    pub level_name: String,                             // "reality_root"
    pub display_name: Option<String>,
    pub metadata: serde_json::Value,
    pub children: Vec<RootChannelDecl>,                 // recursive
}

pub struct CanonicalActorDecl {
    pub actor_id: ActorId,
    pub display_name: String,
    pub initial_cell_path: Vec<String>,                 // ["southern_song", "gia_hung", "yen_vu_lau"]
                                                        // path resolves to a cell; cell is lazy-created on first use
    pub binding_kind: BindingKind,                      // NPC_OwnerNode_<deterministic>
}
```

### 16.2 Reality activation (world-service responsibility)

```text
on RealityManifest received:
  ① t3_write_multi atomic:
       a. write fiction_clock SINGLETON with starting_fiction_time
       b. create_channel for every node in root_channel_tree (DFS, parents first)
       c. write actor_binding for each canonical_actor (binding to the cell-path
          BEFORE that cell exists — actor_binding stores the path; cell row is
          created lazily on first PC entry)
  ② emit ChannelEvent::RealityActivated on the reality root channel
  ③ subscribe ready: PCs may now `bind_session` and `move_session_to_channel`
```

### 16.3 Lazy cell creation

When a PC `/travel`s to a town that has no cell yet, world-service §13 step ④ uses `place_canon_ref` resolution:

```text
on /travel to "tương_dương":
  resolved_path = ["southern_song", "tương_dương", "tương_dương_west_gate"]
  walk down resolved_path; if leaf cell does NOT exist:
    cell = create_channel(parent=district_or_town_at_path[-2],
                          level_name="cell",
                          metadata={ place_canon_ref: leaf_path,
                                     created_for_actor: pc_id,
                                     created_from: "lazy_travel" })
  move_session_to_channel(cell)
```

**Why hybrid:**
- Authors only declare *static* canon (root continents, countries, big towns, anchored NPCs) — small cognitive load
- *Dynamic* spaces (cells representing specific scenes inside a town) only exist when needed — saves storage on dead realities
- Per-reality channel cardinality grows organically with active gameplay rather than upfront

### 16.4 Initial scenes

When the FIRST PC of a reality binds session to a freshly created cell:

```text
on bind_session into newly-created cell:
  ① t2_write::<SceneState>(cell, Initialize {
        primary_actor: first_pc,
        ambient: <derived from canon: book passage referencing this place at this fiction-time>,
      })
  ② for each canonical_actor with actor_binding pointing to this cell:
       emit MemberJoined({actor: canonical_actor, join_method: CanonicalSeed})
  ③ scene is live
```

The "derived from canon" lookup is owned by knowledge-service (Oracle PL-16); world-service issues a query and uses the response. If the book has no specific passage describing this exact place at this exact fiction-time, ambient defaults to season-and-region-derived (e.g., "thu, miền nam, ban ngày, mưa nhỏ").

### 16.5 Failure to bootstrap

If `t3_write_multi` in 16.2 fails partway: outbox rollbacks per DP-T3 atomicity → reality remains in `Initializing` state → no PC can bind. Operator-driven retry from RealityManifest (manifest is idempotent — re-running with same `reality_id` short-circuits if already `Active`).

---

## §17 Acceptance criteria (LOCK gate)

The design is implementation-ready when world-service + roleplay-service + gateway can pass these scenarios. Each scenario is one row in the integration test suite.

### 17.1 Happy-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-1 NORMAL TURN** | PC says "Tiểu nhị, lấy cho ta một bình trà" in `cell:yen_vu_lau`. | `TurnEvent` committed with `outcome=Accepted`; `turn_number=N+1`; `fiction_clock` advanced by ~30s; UI receives narrator_text within 2s wall-clock excluding LLM streaming time. |
| **AC-2 SLEEP CROSSES DAY** | Turn 11 of SPIKE_01: `/sleep until dawn` at 23h crosses midnight. | `fiction_clock.day` increments by 1; `fiction_clock.sub_day = MãoSơ`; one `TurnEvent::FastForward` event; bubble-up events from tavern dropped per §12 fast-forward rule. |
| **AC-3 TRAVEL CHAIN** | Turn 16-17: `/travel to Tương Dương`. | All 5 ops (§13 ① through ⑦) commit; UI's post-travel reads with `wait_for=T5` return new cell + new fiction_time; old cell not auto-dissolved (Dormant within 30min if no other session). |
| **AC-4 LAZY CELL CREATE** | First PC ever to visit "Tương Dương West Gate". | Cell channel created; `SceneState` initialized; canonical NPCs at this cell `MemberJoined`; PC sees them in presence list. |
| **AC-5 CANONICAL NPC LOAD** | At reality activation, Lão Ngũ + Tiểu Thúy `actor_binding` populated; first PC into `cell:yen_vu_lau` sees `MemberJoined` for both NPCs. | Presence list shows both NPCs `state=Active`. |

### 17.2 Failure-path scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-6 REJECTION** | PC `/sleep` during active combat. | `TurnEvent` committed with `outcome=Rejected{ reason }`; `turn_number` UNCHANGED; `fiction_clock` UNCHANGED; UI shows reject copy from §15. |
| **AC-7 IDEMPOTENT RETRY** | UI submits turn with key K, server commits but ACK lost; UI reconnects and retries with same K. | Second submit returns cached response without re-running LLM/validator chain; no second `TurnEvent` in event log. Verified by `query_scoped_channel<TurnEvent>` count = 1. |
| **AC-8 IDEMPOTENT FRESH** | UI submits turn, gets 200; submits ANOTHER turn with new key. | Both commit; `turn_number` advances by 2; both events findable. |
| **AC-9 CONCURRENT TURN REJECTED** | Two HTTP requests for the same session arrive 50ms apart with different keys. | Second request rejects with `RejectReason::WorldRuleViolation{ "concurrent_turn" }`; first commits normally. |
| **AC-10 CELL CAPACITY** | Cell at 32 actors; 33rd PC tries `/travel` in. | `/travel` rejects with `WorldRuleViolation{ "cell_capacity" }`; PC stays in old cell; `fiction_clock` UNCHANGED. |
| **AC-11 PRESENCE REBUILD** | Writer-node crash; T1 lost; new node takes over cell. | `participant_presence` rebuilds from `MemberJoined`/`MemberLeft` log; presence list matches pre-crash within 1s of new-node-bind. |
| **AC-12 CAUSALITY TIMEOUT** | UI passes `wait_for=token` but projection-applier is wedged for 25s. | After 20s default, UI receives `CausalityWaitTimeout`; UI surfaces retry banner; no silent stale read. |

### 17.3 Boundary scenarios

| ID | Scenario | Pass criteria |
|---|---|---|
| **AC-13 RECONNECT MID-TURN** | UI loses WebSocket between submit and ack; reconnects 10s later. | `GET /v1/turn/status` returns `Committed` (or `InFlight` if still running); UI resumes from `causality_token`; multiplex stream replays missed events from resume token. No duplicate render. |
| **AC-14 BOOKEND DISCONNECT** | UI submits turn; client closes browser; never returns. | Server commits the turn (no client cancellation). On a NEW session bind by the same user later, `actor_binding` reflects post-turn state. |
| **AC-15 BOOTSTRAP IDEMPOTENT** | Operator re-runs reality activation with same `reality_id`. | No second `RealityActivated` event; no duplicate channels; no duplicate canonical actor bindings. |
| **AC-16 SCHEMA EVOLUTION** | RealityManifest with `schema_version=2` ingested; world-service running on `schema_version=1` codebase. | Bind rejects with `SchemaVersionMismatch`; operator alerted; world-service deploys v2 → bind succeeds without manifest edit. |

**Lock criterion:** all 16 scenarios have a corresponding integration test that passes. Until then, status is `CANDIDATE-LOCK` (post-this-edit) → `LOCKED` (after tests).

---

## §18 Open questions deferred + their landing point

| ID | Question | Defer to |
|---|---|---|
| MV12-D8 | Narration taxonomy — what kinds of TurnEvent payloads exist beyond Speak/Action/MetaCommand/FastForward? | PL_003 (multi-NPC turn) |
| MV12-D9 | Scope of `command_args` schema per command kind (sleep, travel, verbatim, prose, ...) | PL_002 (command grammar) — already cataloged as PL-2 |
| MV12-D10 | NPC-only routine scenes happening in the cell while PC is asleep — do they emit TurnEvents tagged with future turn_numbers? | DL_001 (NPC routine foundations) |
| MV12-D11 | Drift tolerance: does `fiction_clock` advance even when world-rule rejects the turn? | PL_002 (rejection path) — current answer in PL_001/PL_001b: NO, advance only on accepted advance_turn. |
| Cell auto-dormant policy | What inactivity window (DP-Ch32 default 30min) is right for our cells? | Operational tuning (Phase 5 ops) |
| Cross-reality clock | Multiverse extensions — does fiction_clock vary per-reality independently? Yes per DP-A14 reality-scope. Cross-reality time queries via R5. | DF12 cross-reality (already withdrawn) |

---

## §19 Cross-references

- [`PL_001_continuum.md`](PL_001_continuum.md) — root file (§1-§10): contract layer
- [00_foundation/02_invariants.md](../../00_foundation/02_invariants.md) — I1..I19 invariants
- [00_foundation/05_vocabulary.md](../../00_foundation/05_vocabulary.md) — TurnState 8-state, PresenceState 6-state, fiction-time vocab
- [03_multiverse/01_four_layer_canon.md](../../03_multiverse/) — canon layer this feature respects
- [05_llm_safety/](../../05_llm_safety/) — A3 World Oracle, A5 intent classifier, A6 injection defense — all run BEFORE world-service writes
- [06_data_plane/02_invariants.md](../../06_data_plane/02_invariants.md) DP-A1..A19
- [06_data_plane/03_tier_taxonomy.md](../../06_data_plane/03_tier_taxonomy.md) DP-T0..T3
- [06_data_plane/11_access_pattern_rules.md](../../06_data_plane/11_access_pattern_rules.md) DP-R1..R8
- [06_data_plane/04a..04d_*.md](../../06_data_plane/) DP-K1..K12 SDK surface
- [06_data_plane/12_channel_primitives.md](../../06_data_plane/12_channel_primitives.md) DP-Ch1..Ch10 channel CRUD
- [06_data_plane/15_turn_boundary.md](../../06_data_plane/15_turn_boundary.md) DP-Ch21..Ch24 advance_turn
- [06_data_plane/18_causality_and_routing.md](../../06_data_plane/18_causality_and_routing.md) DP-Ch38..Ch40 CausalityToken
- [06_data_plane/21_llm_turn_slot.md](../../06_data_plane/21_llm_turn_slot.md) DP-Ch51..Ch53 turn-slot patterns
- [06_data_plane/22_feature_design_quickstart.md](../../06_data_plane/22_feature_design_quickstart.md) — design template this doc follows
- [features/_spikes/SPIKE_01_two_sessions_reality_time.md](../_spikes/SPIKE_01_two_sessions_reality_time.md) — narrative validation source

---

## §20 Implementation readiness checklist

Combined check across PL_001 (root) + PL_001b (this file). Both files together satisfy every required item per DP-R2 + 22_feature_design_quickstart.md §"Required feature doc contents":

PL_001 (root):

- [x] **§3** Aggregate inventory with `#[derive(Aggregate)]` declarations (incl. §3.3 rebuild algorithm, §3.5 outcome + idempotency_key, §3.7 hard limits)
- [x] **§4** Tier+scope table per aggregate (DP-R2)
- [x] **§5** DP primitives by name
- [x] **§6** Capability JWT claim requirements
- [x] **§7** Subscribe pattern
- [x] **§8** Pattern choices (turn-slot Strict, redaction Transparent, causality timeout 5s/20s)
- [x] **§9** Failure-mode UX (every DpError variant has user copy)
- [x] **§10** Cross-service handoff with CausalityToken chain

PL_001b (this file):

- [x] **§11** Sequence: normal turn
- [x] **§12** Sequence: /sleep (fast-forward across day boundary)
- [x] **§13** Sequence: /travel (5-op chain, ASCII flow, 5 edge cases)
- [x] **§14** Reconnect/resume + idempotency (UUID key, 60s cache, world-service `turn_idempotency_log`)
- [x] **§15** Rejection path (Q1=option-b: Rejected event committed via plain `t2_write` (NOT `advance_turn`), turn_number stays at N, MV12-D11 honored)
- [x] **§16** Bootstrap (Q2=hybrid: book manifest declares root tree + fiction_clock; cells lazy-create)
- [x] **§17** Acceptance criteria (16 scenarios across happy-path / failure-path / boundary)
- [x] **§18** Deferrals named with landing point

**Status transition:** DRAFT (2026-04-25 first commit `b4ea611`) → renamed (`1364487`) → **CANDIDATE-LOCK** (2026-04-25 after this extension + 800-line split into root + lifecycle). LOCK granted after all 16 §17 acceptance scenarios have a passing integration test.

**Next** (when this doc locks): world-service + roleplay-service can be scaffolded against this contract. The first vertical-slice implementation target is the SPIKE_01 turn 1-4 path (PC enters Yên Vũ Lâu → orders tea → Tiểu Thúy responds), wall-clock target ≤2s end-to-end excluding LLM streaming. AC-1, AC-7, AC-9 are minimum for vertical-slice green light; AC-3, AC-4, AC-11 are required for full-feature green light.
