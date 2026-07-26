# 14 — `sim-core` Specification (POC → production)

> **Status:** SPEC — 2026-07-26. The **buildable** specification for `crates/sim-core`: the island
> scheduler, its ingress queue, the ordering model, and the chaos harness that proves it.
> Implements [`13_simulation_loop.md`](13_simulation_loop.md) (SL-A1..A13 / SL-D1..D18).
> **Design intent:** this crate is the **POC and the production module** — built pure and WASM-ready
> from the first commit (SL-A8) so integration into `game-server` is a wiring change, never a rewrite.
> **Prefix** `SC-*`. Axioms `SC-A1..A10`; decisions `SC-D1..D3`. Pending `_boundaries/` lock alongside `SL-*`.
> **Revision 3 — 2026-07-26 (failure-mode sweep):** two gaps closed that CS-A5 (native host) made urgent —
> **§10.4 panic containment** (`SC-A8` poison-not-resume, `SC-A9` quarantine the poison-pill input) and
> **§10.5 crash recovery** (`SC-A10` the event log *is* the recovery source; Class B needs no separate
> checkpoint). Both change `sim-core`'s structure, so they land **before S1**.
> **Revision 2 — 2026-07-26 (pre-build clarity sweep):** resolved a **contradiction** — `apply()` mutated
> island state while `drain_proposals()` claimed sim-core never writes. **PO decision: the island is the
> writer** (SC-A4); only effects *leaving* the island remain Proposals (SC-A5). Also closed five
> under-specified items: the `Domain` trait (§4.0), aggregate identity (§5.1), `dt` semantics for
> event-driven islands (SC-A6, §5.2), buffered-intent `Seq` (§5.3), and island creation (SC-A7, §10.0).
> **Revision 2026-07-26 (open-question sweep):** **all five `SC-Q` items resolved** — two ingress lanes
> (SC-D1, §6.1), `Payload` as a domain enum (SC-D2, §4.1), windowed idempotency (SC-D3, §4.2), host
> threading via SL-D20, and prefetch policy via SL-D25. §9 updated: cross-island transport is **IPC
> (≈1 ms)**, not shared memory. Two measurement questions inherited (SL-Q9, SL-Q10); **neither blocks
> S1–S4**.

---

## 1. Purpose

One sentence: **`sim-core` turns an unpredictable stream of concurrent inputs into a totally-ordered,
replayable, order-independent-correct simulation.**

The properties it must deliver, in priority order:

1. **Order-independent safety** — any interleaving produces a *valid* state (outcomes may differ).
2. **Replay determinism** — the recorded input order reproduces byte-identical state.
3. **Non-blocking** — no slow producer delays a fast one (SL-A2).
4. **Parallel across islands** — scale by island count, not by core clock (SL-A9).
5. **Purity** — no I/O, no ambient clock, no ambient randomness (SL-A8).

## 2. Non-goals (V1)

Combat rules, damage formulas, ability catalogues, world generation, networking, persistence, LLM
prompting. `sim-core` is the **scheduler and queue**; domain rules plug in as handlers. It owns *when
and in what order*, never *what*.

---

## 3. Crate layout

```
crates/sim-core/
  src/
    clock.rs        Tick, Dt, logical clock — no wall-clock access
    ids.rs          IslandId, EntityId, InputId, Seq, Gen
    ingress.rs      queue + stamping + OrderingPolicy trait
    precond.rs      Precondition, validation, Fallback
    island.rs       Island: state + step() + tick()
    scheduler.rs    eligibility, priority queue, deadlines, timers
    intent.rs       pending-intent buffer (Gate-2 miss)
    driver.rs       Driver trait; Script / Engine real, Llm behind a dispatch port
    message.rs      cross-island envelope, exactly-once delivery
    lifecycle.rs    entity + island lifecycle, generational invalidation
    load.rs         per-island load accounting — F17; input to SL-A13 dilation
    invariants.rs   I1–I8, checked every step under `cfg(debug_assertions)` or `sim` feature
    lib.rs
  tests/
    scenarios/      named regression scenarios (incl. `meteor.rs`)
  sim/              deterministic chaos harness (separate bin)

crates/sim-rtsim/   Class C background world simulation — SEPARATE crate (F15)
  src/rule/         one module per background rule. V1 set raised by AUD-F13
                    (full daily life in V1): npc_schedule · ambient_activity ·
                    replenish_resources · ambient_economy · pc_to_npc · cleanup
  src/data/         persistent background state (Veloren rtsim `data/` shape)
  src/sync.rs       the explicit seam back into sim-core (dispatch/ingest, SL-A4)
```

**Library/binary split (F14):** `sim-core` is a **library** with no `main`. The host — game-server via
WASM, or a native test binary — owns the process. Veloren uses exactly this shape (`server` lib +
`server-cli` bin).

**Dependency rule:** `sim-core` may depend on `serde`, `smallvec`, `rand_chacha`. It may **not** depend
on `tokio`, `std::time`, `sqlx`, or any I/O crate. Enforced by a CI check on `Cargo.toml`.

**Profile rule (SC-A8):** the `commit-service` build profile **must not** set `panic = "abort"` —
`catch_unwind` cannot catch an aborting panic, so the §10.4 containment boundary would silently become a
no-op. Also CI-checked, because that failure mode is invisible until a panic happens in production. (The
neighbouring Veloren workspace sets `panic = "abort"` in its dev profile — an easy pattern to copy by
accident.)

---

## 4. Core types

```rust
pub struct IslandId(pub u64);
pub struct EntityId(pub u64);
pub struct InputId(pub u128);      // idempotency key (I2)
pub struct Tick(pub u64);          // logical time, per island
pub struct Seq(pub u64);           // ingress stamp, monotonic per island
pub struct Gen(pub u32);           // generation — bumped on lifecycle change

pub enum Class { A, B, C }         // SL-A2 execution classes

pub enum Producer {                // all treated as UNPREDICTABLE
    PlayerInput, LlmDecision, ScriptDecision, Timer, Generator,
    CrossIsland, WorkerResult, WorldEvent, Admin, SessionLifecycle,
}

pub struct QueuedInput {
    pub seq:           Seq,
    pub input_id:      InputId,
    pub class:         Class,
    pub source:        Producer,
    pub payload:       Payload,
    pub preconditions: SmallVec<[Precondition; 4]>,
    pub on_invalid:    Fallback,
}

pub enum Precondition {
    EntityAlive     { id: EntityId,   gen: Gen },
    EncounterActive { id: EntityId,   gen: Gen },
    ActorEligible   { id: EntityId,   turn: Tick },
    ResourceAtLeast { id: EntityId, kind: ResKind, amount: i64 },
    IslandOwns      { id: EntityId },
}

pub enum Fallback { Drop, Substitute(Payload), Notify(EntityId, Reason), Buffer }

pub enum Outcome {
    Applied   { events: Vec<Event> },
    Discarded { reason: DiscardReason },
    Buffered,
}
```

**`Payload` is generic over the domain** (`Island<D: Domain>`), so `sim-core` never imports combat.

### 4.0 The `Domain` trait (was undefined — closed 2026-07-26)

`sim-core` owns *scheduling*; the domain owns *rules*. The seam:

```rust
pub trait Domain: Sized {
    type Payload:  Clone + Serialize + DeserializeOwned;   // SC-D2: an enum
    type State;                                            // island-local world state
    type Event:    Clone + Serialize;
    type ResKind:  Copy + Eq;

    type Rules;   // immutable, digest-pinned ruleset — see RLS-A12/A13, §4.0.1

    /// sim-core evaluates STRUCTURAL preconditions (EntityAlive, EncounterActive,
    /// IslandOwns, ActorEligible) from generations it already tracks.
    /// The domain evaluates only SEMANTIC ones (ResourceAtLeast, and its own).
    fn check(state: &Self::State, rules: &Self::Rules, p: &Precondition<Self>)
        -> Result<(), Violation>;

    /// Apply a VALIDATED input. MUST be deterministic and total —
    /// no I/O, no ambient clock; randomness only via the seeded `DetRng`.
    fn apply(state: &mut Self::State, rules: &Self::Rules,
             input: &QueuedInput<Self>, rng: &mut DetRng) -> Vec<Self::Event>;

    /// Which effects LEAVE this island and therefore need commit-service
    /// authorization (SC-A4 §5.1) — loot→inventory, xp→progression, cross-island.
    fn externals(events: &[Self::Event]) -> Vec<External>;
}
```

`apply` is only reachable through `check` (§5), so a domain handler can never see unvalidated input.

#### 4.0.1 `Rules` is a fourth replay input — I5 amended (2026-07-26)

`&Self::Rules` was **added after** the peer session's [`16_ruleset_loader_and_registry.md`](16_ruleset_loader_and_registry.md)
(**RLS-A12**) and its use in [`17` §R2](17_game_data_architecture.md) step 4. It is not cosmetic:

> ⚠️ **I5 as first written was incomplete.** It said *"replay of the recorded `Seq` order → byte-identical
> state"*. With rules as an `apply` input, replaying the same input order under a **different ruleset**
> reproduces a different state. **The replay tuple is `(input order, ruleset digest, RNG seed)`**, and
> the digest must therefore be **recorded alongside the event stream** and asserted on replay. §12 and
> §13 updated.

Two upstream tensions are **RLS-owned, not `sim-core`'s to resolve** — doc 16 flags both against itself,
which is why they are cited rather than assumed:

- **RLS-A12 vs EVT-A9** — *"generation rules … only DP-readable projection state"*; `&D::Rules` is
  neither, so it needs an explicit carve-out justified by immutability + digest pinning.
- **RLS-A13 vs EVT-A10 / EVT-L18** — EVT-L18 defines replay inputs as a **closed list** (*"same input
  event log + same fiction-clock state + same RNG seed"*) and EVT-A10 says the event log alone is
  *sufficient*. Digest pinning adds a non-event-sourced fourth input, so **both axioms need amending**.

`sim-core` simply takes `Rules` as an opaque immutable parameter; **if the carve-out is refused
upstream, the fix lands in 16, not here** — but I5's tuple is correct either way, because it describes
what determinism actually depends on.

### 4.1 `Payload` is an enum, not a trait object (SC-Q2 — RESOLVED)

> **SC-D2 — `D::Payload` is a domain-defined enum.** A boxed trait object would require `Box`
> (defeating the zero-allocation target in §14), add vtable indirection on the hottest path, and
> serialize poorly. The extensibility argument for trait objects **does not apply here**, because
> `Island<D: Domain>` already parameterises the payload by associated type — each domain defines its own
> exhaustive enum while `sim-core` stays fully generic.

### 4.2 The `seen` set is windowed (SC-Q3 — RESOLVED)

> **SC-D3 — Idempotency retention is bounded, and the window is part of the contract:**
> - **Encounter island** — `seen` dies with the island. **No eviction** needed; bounded by encounter length.
> - **Cell island** (long-lived) — **5-minute TTL window**, comfortably exceeding any client
>   reconnect-and-resend.
>
> Stated contract: *"a retry within 5 minutes is deduplicated; after that it may be reprocessed."*

An unbounded key set grows forever on a long-lived island; industry retention varies by two orders of
magnitude (Amazon SQS FIFO 5 min · Stripe ≥24 h · queue consumers ~7 d) precisely because **the window
is a product decision, not a protocol default**. Five minutes is chosen against *client retry horizon*,
which is the only legitimate source of duplicates here.

---

## 5. The step function — exact semantics

```rust
impl<D: Domain> Island<D> {
    /// Advance logical time. Class A work + due timers only. Never blocks.
    pub fn tick(&mut self, dt: Dt) -> ();

    /// Process exactly ONE ingress item, atomically (SL-A9 per-item atomicity).
    pub fn step(&mut self) -> StepResult {
        let Some(item) = self.ingress.pop() else { return StepResult::Idle };

        // I2 — idempotency. Duplicate is a normal recorded outcome.
        if !self.seen.insert(item.input_id) {
            return self.record(item, Outcome::Discarded { reason: Duplicate });
        }

        // Preconditions re-validated NOW, never at admission.
        match self.check(&item.preconditions) {
            Ok(())      => { let ev = self.apply(&item); self.record(item, Applied { events: ev }) }
            Err(viol)   => { let o  = self.resolve_fallback(&item, viol); self.record(item, o) }
        }
    }

    /// Drain proposals for the host. sim-core NEVER writes (AGT-A6 / DP-A6).
    pub fn drain_proposals(&mut self) -> Vec<Proposal>;
}
```

**Invariant enforced by construction:** `apply()` is only reachable through `check()`. A domain handler
**cannot** be called with unvalidated preconditions.

### 5.1 Authority — the island is the writer (PO decision 2026-07-26)

The draft was **contradictory**: `apply()` mutated island memory while `drain_proposals()` claimed
"sim-core NEVER writes". If commit-service could reject after `apply()`, we had split-brain with no
rollback machinery. Resolved:

> **SC-A4 — The island is the single writer for island-scoped state.** DP-A6 is satisfied **per
> aggregate**: exactly one writer per aggregate, and for island-scoped aggregates that writer is the
> island. Intra-island resolution **cannot be rejected**, because its preconditions were already
> validated at execution time (§5). `sim-core` emits **`Event`s** — facts, not requests — and
> commit-service **persists** them.

> **SC-A5 — Effects that LEAVE the island are still Proposals.** Anything crossing an aggregate
> boundary — loot into an inventory, XP into progression, a cross-island message, a reputation delta —
> is declared by `Domain::externals()` and goes to commit-service **for authorization**, exactly as
> AGT-A6 requires. Those may be rejected; rejection is a normal recorded outcome and never rolls back
> island state (it is a *separate* aggregate's decision).

This reinterprets AGT-A6's "a Decision is a Proposal" as scoped to **cross-aggregate effects**, not to
intra-island physics. The alternative — speculative apply with rollback — was rejected: it needs an undo
log per step and interacts badly with generational invalidation (§7), for no correctness gain.

```rust
pub fn drain_events(&mut self)    -> Vec<D::Event>;  // facts   -> persist
pub fn drain_proposals(&mut self) -> Vec<Proposal>;  // requests -> authorize
```

**Aggregate identity (was unspecified).** The island *is* the aggregate, which is what makes SL-A11's
per-aggregate ordering work:

| Island | `aggregate_type` | `aggregate_id` | `aggregate_version` | `channel_id` (CS-A6) |
|---|---|---|---|---|
| encounter | `combat_session` *(already registered)* | `encounter_id` | committed-event count | **own** ephemeral child channel, `level_name="encounter"` |
| cell | `cell` | `cell_id` | committed-event count | the cell channel |

**Aggregate and channel are different axes, and both apply** ([15 §7b.1](15_commit_service.md)): the
*aggregate* is the state; the *channel* is its DP-A15 total-ordering + visibility scope. An island has
one of each. Ordering within an island is therefore enforced twice over — by `aggregate_version` at the
event-store level and by `UNIQUE(reality_id, channel_id, channel_event_id)` at the DB.

### 5.2 Advancing time (was unspecified for event-driven islands)

> **SC-A6 — `dt` is a per-island-class CONSTANT, never a measured duration.** A measured wall-clock
> delta would destroy determinism (the classic variable-timestep failure). The host calls `tick()` at
> approximately the right real rate; the value passed is always the same.

| Island class | Advance |
|---|---|
| **Cell** (SL-D19: 20 Hz) | `tick(dt)` with fixed `dt = 50 ms`, accumulator pattern |
| **Encounter** (SL-D19: event-driven) | **`dt` unused** — `step()` pops the next due event and sets `T_sim` to its due time. Logical time *jumps*; the jump target comes from the priority queue, never the clock. |

### 5.3 Buffered intents keep their original `Seq`

A Gate-2-miss intent (§6) leaves the ingress queue for the intent buffer. It does **not** re-enter
ingress and is **not** re-stamped: it executes as part of the actor's **eligibility transition**, which
is itself a scheduled event ordered by `(T_due, action_value, actor_id)`. The original `Seq` is carried
into the emitted event for provenance and arrival-fairness auditing. Re-stamping would make replay
depend on *when* eligibility happened rather than on when the input arrived.

---

## 6. Ordering model — two gates

| Gate | Question | Ordered by | On failure |
|---|---|---|---|
| **1 — Admission** | in what order did this arrive? | **ingress `Seq` (FCFS)** | — (everything is admitted) |
| **2 — Eligibility** | may this actor act *now*? | `ActorEligible` precondition | `Fallback::Buffer` → pending intent |

A Gate-2 miss is **not** a rejection. The input is buffered as the actor's pending intent and fires the
instant the actor becomes eligible (Nystrom `setNextAction`). This is what produces action-game
responsiveness on a soft turn-based core.

```rust
pub trait OrderingPolicy {
    fn stamp(&mut self, arrival: ArrivalMeta) -> Seq;
}
pub struct Fcfs;                              // V1 DEFAULT
pub struct ClientTimestampWindow { hold: Dt } // fairness variant, deferred
```

**Safety does not depend on the policy** (§8 guarantees that). The policy only changes *outcomes*, which
is why it can be swapped later without touching game logic.

### 6.1 Two ingress lanes (SC-Q4 — RESOLVED)

> **SC-D1 — Ingress has two lanes: `Live` (Classes A + B) and `Background` (Class C).** `Live` drains
> first; `Background` drains under a **bounded per-tick budget** (`max_background_per_tick`), so it can
> neither starve live work nor be starved itself.

Without this, a burst of background results — an economy batch across a thousand cells — would
**head-of-line-block player input** in a single FCFS queue.

Determinism is unaffected: lane assignment is a pure function of `Class`, ordering within each lane is
FCFS by `Seq`, and the drain policy is fixed. The permutation-safety claim (SC-A1) covers lane
interleaving for free.

```rust
pub enum Lane { Live, Background }
impl Class { fn lane(self) -> Lane { match self { Class::C => Lane::Background, _ => Lane::Live } } }
```

---

## 7. Generational invalidation

```rust
fn transition(&mut self, id: EntityId, to: Lifecycle) {
    let e = &mut self.entities[id];
    e.lifecycle = to;
    e.gen.0 += 1;          // O(1) — invalidates every pending reference at once
}
```

No queue scan, no cancellation list, no missed item. Pending work referencing an old `Gen` fails its
precondition on contact and takes its declared `Fallback`. Reuses **EF_001**'s
`Existing | Gone | Removed` lifecycle — this is what its reference-safety design was for.

---

## 8. The correctness claim

> **SC-A1 — For any permutation of the ingress stream, `Island::step` produces a state satisfying
> I1–I8.** Outcomes differ between permutations; validity does not.

This is the property the chaos harness exists to falsify, and it is why game logic built above
`sim-core` never needs to reason about arrival order.

---

## 9. Cross-island protocol

```rust
pub struct IslandMessage {
    pub from:        IslandId,
    pub to:          IslandId,
    pub causality:   Seq,     // sender's seq — establishes causal (not total) order
    pub delivery_id: InputId, // exactly-once (I8)
    pub payload:     Payload,
}
```

- Delivered into the target's ingress at its **next tick** (+1 tick latency, SL-A10).
- **No island reads another island's state.** Ever.
- Target island missing/dissolved → message discarded with a recorded reason (never an error).

**Transport is IPC, not shared memory (SL-D20).** Islands live in separate OS processes (process-per-core,
PM2 fork), so delivery costs ≈ **1 ms**, not microseconds. Mitigated by **spatial co-location**
(SL-D20b): islands of the same region share a process, so intra-region messages stay in-process and only
cross-*region* traffic pays IPC. `sim-core` is unaffected either way — it emits a message and receives
one; the host chooses the transport. Whether 1 ms matters in play is **SL-Q9**, measurable at S4b.

## 10. Island lifecycle

`Spawning → Active → Dissolving → Gone`. Entities migrate by handoff (`EntityDeparted` →
`EntityArrived`, SL-A12); an entity is live in exactly one island at any logical time. Dissolution
checkpoints survivors (RTM-Q4) and discards all pending work by generation bump.

### 10.0 Who creates an island (was unspecified)

> **SC-A7 — `sim-core` never creates an island; it *requests* one.** Creation is a host concern
> (placement, process assignment, spatial co-location per SL-D20b), and `sim-core` holds no registry of
> other islands. An island emits `IslandSpawnRequested` as an **external** (`Domain::externals`,
> SC-A5); the host's **island manager** acts on it.

| Trigger | Creates |
|---|---|
| PC enters a Cold cell (Cold→Hot, §8/SL-D10) | cell island |
| a combat trigger commits | encounter island (RTM-Q4 instanced scene) |
| last live entity leaves | → `Dissolving{Idle}` (§10.1) |

The manager is host-side and therefore **not** determinism-critical; its decisions arrive back into
`sim-core` as ordinary stamped ingress items.

### 10.1 Dissolution reasons (F11 — modelled on Orleans `DeactivationReasonCode`)

**Why it dissolved determines what happens to pending work.** A single `Dissolving` state is not enough:

| Reason | Pending work | Entities |
|---|---|---|
| `Resolved` | discard (generation bump) | checkpoint + release |
| `Idle` | none expected | unload; re-spawn on demand |
| `Migrating` | **transfer with the island** | handoff to target node |
| `Unresponsive` | lost | force-kill; rebuild from last checkpoint |
| `MemoryPressure` | discard | evict coldest first |
| `NodeShuttingDown` | transfer | drain then handoff |
| `Failed` | discard, log | rebuild from checkpoint |

### 10.2 Migrate only at quiescence (F12)

> **SC-A3 — An island migrates only when it has no in-flight work.** Orleans exposes `MigrateOnIdle()`
> / `DeactivateOnIdle()` precisely so migration never interrupts a request. Ours: an **encounter island
> migrates between turns, never mid-turn**; a cell island migrates when its ingress queue is empty and
> no decision is outstanding. Otherwise the pending queue must migrate too — solvable, but not V1.

### 10.3 Migratability (F13)

Not everything may move. Orleans marks grain types `Immovable`. Ours:

| Island | Migratable |
|---|---|
| cell island, cold | freely |
| cell island, hot | at quiescence |
| **encounter island, active** | **no — pinned for the encounter's life** |

Mid-combat migration buys little and risks the determinism guarantee; encounters are short-lived by
construction (RTM-Q4), so pinning is cheap.

## 10.4 Panic containment (closed 2026-07-26)

**CS-A5 created this risk and it must be answered before S1.** With `sim-core` linked *natively* into
`commit-service`, a panic is no longer sandboxed — a WASM host would have contained it; a native crate
does not. One out-of-bounds index in one island's `step()` would otherwise kill the writer process and
**every island on it**.

> **SC-A8 — Every `step()` and `tick()` runs inside a panic boundary, and a panicking island is
> POISONED, never resumed.** A panic can occur part-way through `apply()`, so the island's invariants
> may be mid-mutation. It is therefore *not* recoverable in place: it is marked poisoned, dissolved with
> `DissolutionReason::Unresponsive` (§10.1), and rebuilt per §10.5.

```rust
match std::panic::catch_unwind(AssertUnwindSafe(|| island.step())) {
    Ok(outcome) => outcome,
    Err(_payload) => {
        island.poison();                       // state is UNKNOWN — do not resume
        quarantine(item);                      // EVT-V2 `quarantine` — see poison-pill below
        dissolve(island, Unresponsive);        // → rebuild, §10.5
    }
}
```

**The poison-pill trap.** Rebuilding replays committed events and re-consumes un-acked bus entries. If
the input that caused the panic is simply replayed, it panics again — **an infinite crash loop**. So:

> **SC-A9 — The input in flight when a panic occurs is QUARANTINED, never retried.** `EVT-V2` already
> defines `quarantine` (isolate for manual operator review, SEV2, no auto-reject and no auto-commit) —
> that is exactly the right destination, and it exists already.

Three implementation requirements, all easy to get wrong:

| | Requirement |
|---|---|
| **`panic = "abort"` must NOT be set** for the `commit-service` profile | `catch_unwind` cannot catch an aborting panic. Note the neighbouring Veloren workspace sets `panic = "abort"` in its dev profile — an easy pattern to copy by accident. |
| `AssertUnwindSafe` + explicit poison flag | `&mut Island` is not `UnwindSafe`; this is the same discipline `std::sync::Mutex` poisoning uses, for the same reason. |
| **Do NOT catch in `sim` / debug builds** | `cfg`-gate the boundary off so the chaos harness surfaces panics as test failures instead of silently quarantining them. |

## 10.5 Crash recovery (closed 2026-07-26)

§10.1 named `Unresponsive → "force-kill; rebuild from last checkpoint"` but never said *how*. The
procedure, almost entirely from mechanisms that already exist:

| # | Step | Mechanism |
|---|---|---|
| 1 | CP detects writer-node death, reassigns the writer | **DP-A16** — *"reassigned only on writer-node death"* |
| 2 | New writer receives a **new epoch token** | **DP-A16 is already a fencing token**: the old writer's token is now stale, so its `event_log` inserts fail. This *is* the split-brain guard — no new mechanism needed. |
| 3 | Rebuild island state = latest snapshot + events since | **`dp-kernel::load_aggregate`** over `aggregate_snapshots` + delta events — already built (and F8 shows RobustToolbox validating the same snapshot+delta shape) |
| 4 | Re-subscribe to the bus; un-acked entries redeliver | Redis Streams **PEL** at-least-once; **EVT-L3** idempotency dedup makes redelivery safe |
| 5 | Ephemeral state is re-derived or dropped (below) | — |

> **SC-A10 — Class B needs no separate checkpoint mechanism.** Every Class B commit is already durable
> in the event log, so **the event log is the recovery source**. Snapshots are a *speed* optimisation,
> not a correctness requirement. (Class A is the opposite — never event-sourced, so its RTM-Q4 position
> checkpoint *is* load-bearing.)

**What is lost on rebuild — stated, because silence here becomes a bug:**

| Lost | Consequence |
|---|---|
| **In-flight LLM decisions** (dispatched, not returned) | **Self-healing** — the actor is `AwaitingDecision` with no outstanding dispatch, so its deadline fires and **AGT-A2 fallback** commits. No special handling required. |
| **Buffered intents** (Gate-2 misses) | Lost; the player re-issues. They were never committed, so no invariant breaks. |
| **Class A ephemeral position** | Restored from the RTM-Q4 checkpoint (already designed). |
| **Un-stamped trusted-origin input in the gateway** | Lost; the player re-issues. Bus-borne input redelivers via PEL. |

The pleasing part: **the deadline/fallback machinery designed for slow LLMs turns out to be the recovery
mechanism for lost ones too.** Nothing extra to build.

---

## 11. Driver port

```rust
pub trait Driver { fn decide(&mut self, ctx: DecisionContext) -> DecisionHandle; }
```

`decide` returns a **handle**, never a `Decision` — dispatch, never await (SL-A4). `Script` and `Engine`
resolve the handle synchronously; `Llm` resolves it via the host, arriving later as a
`Producer::LlmDecision` ingress item. **The scheduler cannot tell the difference**, which is the whole
point of AGT-A3.

Every dispatch **reserves** the actor's turn slot; arrival **confirms** or **releases** it — the
reservation/saga pattern borrowed from flash-sale inventory.

---

## 12. Invariants (I1–I8)

| | Invariant | Checked |
|---|---|---|
| **I1** | Every admitted input commits or is discarded with a recorded reason | every step |
| **I2** | No input applied twice (`input_id`) | every step |
| **I3** | An actor never acts twice in one turn | every step |
| **I4** | No resource negative; no double-spend | every step |
| **I5** | Replay of the **tuple** `(recorded Seq order, ruleset digest, RNG seed)` → byte-identical state hash. **Amended 2026-07-26** (§4.0.1): the ruleset is an `apply` input (RLS-A12), so input order alone does not determine state. A replay run whose digest differs from the recorded one **fails loudly rather than silently diverging.** | end of run |
| **I6** | A slow producer never blocks a fast one | every tick |
| **I7** | Every deadline fires; no actor waits forever | every tick |
| **I8** | Cross-island message delivered exactly once | every step |

`invariants.rs` is compiled in under `debug_assertions` or the `sim` feature; **off in release**.

---

## 13. Chaos harness (`sim/`)

Modelled on [TigerBeetle's VOPR](https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/internals/vopr.md)
and [FoundationDB's simulator](https://pierrezemb.fr/posts/diving-into-foundationdb-simulation/).

**Seeded** — `ChaCha8Rng` (same generator family as TMP_001/CSC_001). Every run prints its seed; a
failing seed reproduces the bug exactly.

**Fault injection:**

| Fault | Range |
|---|---|
| LLM decision latency | 0.1 s – 30 s, plus never-returns |
| Input arrival reorder | full permutation within a window |
| Duplicate input | 0–5 % of inputs |
| Class C worker result | late, out-of-order, or dropped |
| Player disconnect / reconnect | any tick |
| Deadline expiry | forced |
| Cross-island message | delayed, reordered, target-dissolved |
| Island dissolve | mid-flight, with work pending |
| **Ruleset digest mismatch** (§4.0.1) | replay under a *different* digest must **fail loudly**, not diverge silently — the bite-test for the amended I5 |
| **Handler panic** (SC-A8) | injected mid-`apply()`; asserts poison → quarantine → rebuild, and that the poison-pill input is **not** replayed |
| **Writer-node death** (§10.5) | injected at any step; asserts rebuild from snapshot+events, stale-epoch writes rejected, in-flight decisions resolve via AGT-A2 fallback |

**Scenario 1 — "the meteor" (named regression):** 4v4 encounter island + 2 cell islands with live
players + RES_001 generators firing + a cross-island meteor that kills both remaining combatants while
one LLM decision is in flight and one player intent is buffered. Asserts I1–I8 and that all four pieces
of pending work are discarded with recorded reasons.

**Determinism gate:** every scenario runs twice per seed; differing event-log hashes fail the test
(the `MADSIM_TEST_CHECK_DETERMINISTIC` pattern).

**Harness is hand-rolled — `madsim` is NOT a dependency (finding F7, §16).** `madsim` exists to mock
**async I/O and time** (it substitutes `tokio`/`tonic`/`etcd`/`s3` and patches `getrandom`/`quanta`).
`sim-core` is **pure and synchronous** with no ambient clock or RNG (§3 dependency rule), so its
determinism is *structural* and madsim would buy nothing. Estimated harness size: **~300 lines**, zero
new dependencies. `madsim` remains a candidate for testing the **host** (network + commit-service)
later, which is a separate layer.

---

## 14. Performance targets (to validate, not assumed)

| Metric | Target |
|---|---|
| `step()` p99, single island | < 50 µs |
| Ingress throughput, single island | ≥ 10 000 items/s |
| Islands per 8-core host | ≥ 1 000 concurrent |
| Steady-state allocations per `step()` | 0 (arena/pooled) |
| Chaos sim speed | ≥ 1 000 × real time |

## 15. Prior-art comparison

| System | Partition unit | Inside a partition | Parallelism | Hot-partition answer |
|---|---|---|---|---|
| **WoW** (TrinityCore/AzerothCore) | **Map** (zone / instance) | single-threaded `Map::Update` | `MapUpdater` **thread pool**, N maps in parallel (`MapUpdate.Threads`) | dynamic **sharding** (parallel zone copies) |
| **EVE Online** | **solar system** → node | **single Stackless thread — no multicore for one system** | 55 Sol servers × processes, single shard | **time dilation (TiDi)**, to 10 % |
| **Orleans** (Halo 4/5) | **grain** (entity) | single-threaded per grain | across grains, cluster-wide | grain placement / rebalance |
| **Veloren** | world / chunk (specs ECS) | ECS systems | specs parallel dispatch | — |
| **RobustToolbox** (SS14) | map / grid (ECS) | ECS | — | PVS culling |
| **Bevy** | single world | **parallel systems, disjoint access sets** | data parallelism | — |
| **`sim-core`** | **island** (encounter / cell) | single-threaded queue | across islands | **TDIL load dilation** |

**The EVE row is the validation:** *"All players in a single solar system are isolated to a single
thread within a single stackless python process. This design does not permit real multicore concurrency
for a single system."* The largest single-shard MMO ever built accepts exactly the SL-A9 limit and
answers it with exactly SL-A13. **WoW's `MapUpdater` is the island thread pool in production C++.**

**The Bevy row is the future escape hatch:** intra-island parallelism *is* possible when access sets are
provably disjoint (e.g. movement integration for 200 non-interacting entities). Explicitly **V2** —
correctness first, and interaction-heavy work cannot use it.

---

## 16. What reading the code changed

Repos cloned to `D:\Works\source\game-research` and read 2026-07-26. Seven findings, three of which
change the spec.

**F1 — Cross-island messaging is confirmed, including precondition re-validation.** ✅ *validates SL-A10*
TrinityCore's `Map` holds `MPSCQueue<FarSpellCallback> _farSpellCallbacks`
([`Map.h:829`](file:///D:/Works/source/game-research/TrinityCore/src/server/game/Maps/Map.h)). A spell
crossing maps enqueues onto the **target's** queue from any thread; the target drains it in its **own**
single-threaded `DelayedUpdate`. The callback then **re-resolves the target by GUID**
(`ObjectAccessor::GetPlayer(map, targetGuid)`, `Spell.cpp:2049`) and bails if it's gone — that is
*exactly* our precondition re-validation, in production, for the same reason.

**F2 — TrinityCore uses a global barrier (BSP). We cannot.** ⚠️ *divergence, deliberate*
`MapManager::Update` is: `schedule_update` every map → `m_updater.wait()` (**barrier**) → sequential
`DelayedUpdate` over all maps ([`MapManager.cpp:324-357`](file:///D:/Works/source/game-research/TrinityCore/src/server/game/Maps/MapManager.cpp)).
So the whole server ticks in lockstep and **the slowest map sets the tick rate for everyone**.
That is tolerable when the slowest map is ~50 ms. **It is fatal for us** — one 5-second `LlmDriver`
decision would stall the entire server. Independent islands (SL-A9/SL-A10) are therefore **required, not
merely preferred.** What we give up is the free global-consistency window BSP provides after the
barrier; our +1-tick async message (SL-A10) buys the same safety without the barrier.

**F3 — AzerothCore runs different map classes at different cadences.** 🆕 *adopt*
`mapUpdateStep` cycles 0 = continents, 1 = battleground/arena, 2 = dungeon, each with **its own timer**
([`MapMgr.cpp:267-292`](file:///D:/Works/source/game-research/azerothcore-wotlk/src/server/game/Maps/MapMgr.cpp)).
Directly applicable: **encounter islands and cell islands need not share a tick rate.** Feeds SL-D12 —
tick rate should be per-island-class, not global.

**F4 — Threading is an optimization, not a structural assumption.** 🆕 *adopt — important for DST*
`if (m_updater.activated()) schedule_update(...) else map->Update(...)` — **the same code path runs
single- or multi-threaded.** We must do the same, and for a sharper reason than they had:
> **SC-A2 — `sim-core` must be steppable single-threaded.** The chaos harness runs **all islands on one
> thread** (deterministic, reproducible, I5-checkable); production runs them across a pool. Same code,
> two drivers. Determinism testing and parallelism are otherwise mutually exclusive.

**F5 — Per-island update time is the load signal.** 🆕 *adopt*
`TC_METRIC_TIMER("map_update_time_diff", TC_METRIC_TAG("map_id", …))` — per-map update duration is
already the instrumented metric. This is the concrete trigger for SL-A13 load dilation, alongside queue
depth. No heuristic invention needed.

**F6 — They enforce "no blocking I/O in the tick" at runtime; we do it at compile time.** ✅
`MapUpdater::WorkerThread` calls `WarnAboutSyncQueries(true)` on all four DB connections — a *runtime
warning* if a map update issues a synchronous query. Our §3 dependency rule (no `tokio`/`std::time`/
`sqlx` in the crate, CI-enforced) makes the same mistake **unrepresentable**. Keep it.

**F7 — `madsim` is not needed.** 🆕 *simplifies §13* — see the note there.

### RobustToolbox (replay) — F8–F10

**F8 — Replay = per-tick deltas + periodic full checkpoints.** ✅ *validates the existing foundation*
`ReplayData` holds `List<GameState> States` (per-tick deltas) plus `CheckpointState[] Checkpoints`
(full states), so seeking to tick 1001 applies the nearest checkpoint plus a few deltas instead of
1001 states. This is precisely `dp-kernel`'s `aggregate_snapshots` + delta-events model — the pattern
is **already in our foundation**; we just point replay at it.

**F9 — They record STATE; we record INPUT. Deliberate divergence.** ⚠️
RobustToolbox replays *recorded output states*; it never re-simulates.

| | State-replay (theirs) | **Input-replay (ours, I5)** |
|---|---|---|
| Tolerates a nondeterministic sim | yes | **no — requires determinism** |
| Storage | large (every tick's state) | tiny (inputs only) |
| **Proves determinism** | no | **yes — that is what I5 is** |
| Enables what-if / rollback | no | yes |

They chose state-replay because a client must render without running server logic, and cross-machine
.NET determinism is hard. **We can afford input-replay only because `sim-core` is pure** — which is a
direct payoff of SL-A8, and worth defending when purity feels inconvenient. We should still adopt F8's
periodic full checkpoints **on top of** input-replay, for fast seek.

**F10 — Dangling cross-boundary references are a real, shipped bug class.** ✅ *validates §7*
Their `CheckpointState` splits `AttachedStates` / `DetachedStates` because of a concrete failure: entity
A parented to B, both leave PVS, only B is deleted → blindly applying full state throws. That is a
**dangling reference across a visibility boundary** — the same class as our cross-island references.
Our generational invalidation (§7) handles it more cleanly than their state-splitting, because a stale
`Gen` fails a precondition rather than reaching a handler at all.

### Orleans (lifecycle / migration) — F11–F13

**F11 — Deactivation needs a reason taxonomy; ours had none.** 🆕 *spec gap, now fixed in §10.1*
Orleans' `DeactivationReasonCode` has 13 values — `ActivationIdle`, `DuplicateActivation`, `Migrating`,
`ActivationUnresponsive`, `HighMemoryPressure`, `ShuttingDown`, … **Why an activation ended determines
how it is recovered**, and our `Spawning → Active → Dissolving → Gone` collapsed all of that into one
state. Note `DuplicateActivation` — that is the single-activation guarantee (our SL-A12 "exactly one
owning island") enforced as a first-class, named failure rather than an assertion.

**F12 — Migration happens at idle, never mid-request.** 🆕 *now SC-A3, §10.2*
`MigrateOnIdle()` / `DeactivateOnIdle()` exist so migration never interrupts in-flight work. SL-A12
specified *how* an entity moves but never *when* — this closes it.

**F13 — Not everything is migratable.** 🆕 *now §10.3*
`GrainMigratabilityChecker` marks grain types `Immovable`, and unknown types default to immovable
(**fail-safe**). Ours: an active encounter island is pinned for its life.

### Veloren (Rust structure) — F14–F18

**F14 — Library/binary split, exactly as §3 assumes.** ✅
Workspace members include `server` (headless **library**) and `server-cli` (**binary**), plus `common`,
`common/ecs`, `common/state`, `common/systems`, `common/net`, `world`, `network`. Our `sim-core` (lib)
+ host (binary/WASM embed) split is the same shape, in the same language.

**F15 — Class C belongs in its own crate, with an explicit sync seam.** 🆕 *adopt*
Veloren's **`rtsim`** crate is background world simulation, entirely separate from the live ECS:
`rule/simulate_npcs.rs`, `rule/replenish_resources.rs`, `rule/migrate.rs`, `rule/cleanup.rs`,
`rule/report.rs`, plus persistent `data/` for faction, site, sentiment, quest, nature — and crucially
**`rule/sync_npcs.rs`**, the explicit seam back to the live simulation.

This validates the Class A/B ↔ Class C split as a **crate boundary, not a policy flag**, and it maps
almost one-to-one onto our deferred features: `replenish_resources` ≈ RES_001 generators, `report`/
`sentiment` ≈ REP_001, `faction`/`site` ≈ FAC_001/GEO. **Recommend a sibling `sim-rtsim` crate**
rather than a `Class::C` variant handled inside `sim-core`.

**F16 — `Phase { Create, Review, Apply }` — read-then-write ordering.** 🆕 *convergent*
Veloren's `System` trait requires each system to declare a phase. `Review` (read/validate) strictly
precedes `Apply` (mutate) — independently the same split as our check-preconditions-then-apply
dispatcher (§5). Their code marks it `TODO: make use of the phase for advanced scheduling`, i.e. it is
declared but not yet exploited; ours is load-bearing from the start.

**F17 — Instrumentation belongs *in* the core abstraction, not bolted on.** 🆕 *adopt*
`System` carries a `CpuTimeline` with `ParMode { None, Single, Rayon, Exact(u32) }` measurements, and
`gen_stats()` reconstructs per-core utilisation across all systems. Combined with **F5** (TrinityCore's
per-map timer), the conclusion is firm: **`Island` must carry per-island load accounting from the first
commit** — it is the input to SL-A13 dilation and it is painful to retrofit.

**F18 — Cheap runtime guard for pathological work.** 🆕 *adopt*
`if millis > 500 { warn!("slow system execution") }`. Same spirit as TrinityCore's F6. One line;
catches the class of bug where a handler silently becomes expensive.

### Bevy — not read in depth

Deliberately deferred: Bevy's archetype-based disjoint-access proof is the **V2** intra-island
parallelism story (§15), and reading it now would inform nothing in S1–S4.

---

## 17. Open questions

| # | Question |
|---|---|
**All five SC-Q items are RESOLVED as of 2026-07-26.**

| # | Question | Resolution |
|---|---|---|
| ~~**SC-Q1**~~ | ~~Host threading — thread pool vs process-per-island~~ | ✅ **SL-D20** — process-per-core, PM2 fork mode, Redis presence, spatial co-location (SL-D20b). Narrowed first by **F4**: `sim-core` stays single-thread-steppable, so this is a *host* decision that cannot leak into the crate. TrinityCore's `MapUpdater` (115 lines) remains the reference if we ever revisit the pool variant. |
| ~~**SC-Q2**~~ | ~~`Payload` enum or boxed trait object?~~ | ✅ **SC-D2** (§4.1) — domain-defined **enum**; *forced* by the zero-allocation target, and extensibility is already provided by the `Domain` associated type. |
| ~~**SC-Q3**~~ | ~~Does `seen` need bounded eviction?~~ | ✅ **SC-D3** (§4.2) — encounter islands never evict; cell islands use a **5-minute TTL**, documented as contract. |
| ~~**SC-Q4**~~ | ~~Class C shared queue or separate lane?~~ | ✅ **SC-D1** (§6.1) — **two lanes**, `Live` first, `Background` under a bounded per-tick budget. Prevents a background burst head-of-line-blocking player input. |
| ~~**SC-Q5**~~ | ~~Discarded-work metric vs the budget governor~~ | ✅ **SL-D25** — track `decisions_dispatched` vs `decisions_committed`; prefetch only when no scheduled event precedes the turn (risk is **computable** from the scheduler's own timer queue); auto-disable above ~25 % waste. |

### Still open (inherited, both measurements)

| # | Question |
|---|---|
| **SL-Q9** | Does ≈1 ms cross-island IPC actually matter in play? Measurable at **S4b**. |
| **SL-Q10** | Is a CSC_001 tile ~1 m? The ~24 m AOI target scales with it. Cheap to confirm against TMP_001/CSC_001. |

**Neither blocks S1–S4.**

## 18. Cross-references

- Loop design — [`13_simulation_loop.md`](13_simulation_loop.md)
- Module audit — [`12_module_coverage_audit.md`](12_module_coverage_audit.md) (AUD-F7)
- Agent drivers — [`11_agent_decision_standard.md`](11_agent_decision_standard.md)
- Entity lifecycle (generational refs) — [`features/00_entity/EF_001_entity_foundation.md`](features/00_entity/EF_001_entity_foundation.md)
- Movement authority / WASM seam — [`08_realtime_movement_authority.md`](08_realtime_movement_authority.md)

**Repos surveyed 2026-07-26:**
[TrinityCore](https://github.com/TrinityCore/TrinityCore) ·
[AzerothCore](https://github.com/azerothcore/azerothcore-wotlk) ·
[Veloren](https://github.com/veloren/veloren) ·
[RobustToolbox](https://github.com/space-wizards/RobustToolbox) ·
[Bevy](https://github.com/bevyengine/bevy) ·
[Orleans](https://github.com/dotnet/orleans) ·
[TigerBeetle](https://github.com/tigerbeetle/tigerbeetle) ·
[madsim](https://github.com/madsim-rs/madsim) ·
[Nakama](https://github.com/heroiclabs/nakama) ·
[Colyseus](https://github.com/colyseus/colyseus)
