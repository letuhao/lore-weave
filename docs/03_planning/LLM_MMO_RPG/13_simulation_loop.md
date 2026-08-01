# 13 — Simulation Loop & Scheduler

> **Status:** DRAFT — 2026-07-26. The missing **simulation tier**: what advances the world, at what
> cadence, in what order, and how work that takes **seconds to hours** coexists with movement that must
> resolve in **milliseconds**. Opened by **AUD-F7** ([`12_module_coverage_audit.md`](12_module_coverage_audit.md)).
> **Axioms** `SL-A1..A14`; decisions `SL-D1..D27`.
> **Revision 1 — 2026-07-26 (PO challenge):** §7 **Concurrency** added — the original draft specified
> the scheduler's *logic* but no *concurrency model*, which would have pinned the simulation to a single
> CPU core. Islands, cross-island messaging, migration, and overload absorption now specified.
> **Revision 2 — 2026-07-26 (open-question sweep):** **all eight `SL-Q` items resolved** →
> `SL-D19..D25`. Three were *forced* by decisions already locked (D22 by action-value initiative, D23 by
> SL-A6, and the enum choice in [14](14_sim_core_spec.md)); four were settled by external evidence
> (D19–D21, and SC-Q3). **SL-D12 superseded by SL-D19.** Two narrower measurement questions opened
> (SL-Q9, SL-Q10). **SL-Q6 is no longer a blocker on S1.**
> **This changes no locked decision.** It supplies the frame that HSR initiative (COMB_001 Q7), the Agent
> Decision Standard (11), RTM movement authority (08), and TDIL time-dilation were each designed *for*
> but which was never written down.
> **Pending** `_boundaries/` lock for the `SL-*` prefix + the `sim_core` aggregate before promotion.

---

## 1. The principle

The founding constraint, as stated by the PO: *some events take far longer than 50–100 ms to compute, so
the game cannot be a real-time action game.* The conclusion is correct, but the operative principle is
broader and more useful than "therefore turn-based":

> **SL-A1 — Decision latency is decoupled from world advancement.** No computation, however slow, may
> delay the advancement of the world. Turn-based combat is a *policy we choose* for tactical depth — not
> a constraint forced on us by latency.

This matters because the game is **not** purely turn-based: RTM-A1 locked near-realtime avatar movement.
The design is therefore **not** "turn-based instead of real-time" — it is **one scheduler hosting both**,
which is exactly the Final Fantasy XV / FF7R shape the PO named: a world that flows continuously, with
encounters that resolve discretely.

---

## 2. Three execution classes

> **SL-A2 — Every unit of simulation work belongs to exactly one execution class, defined by its deadline.
> A slower class may never block a faster one.** This single rule generates the rest of the architecture.

| Class | Deadline | Work | Allowed drivers | Persistence |
|---|---|---|---|---|
| **A — Tick-bounded** | ≤ 50 ms (one tick) | movement integration, collision/walkability, AOI recompute, occupancy | **Engine only — never an LLM** | ephemeral + periodic checkpoint |
| **B — Turn-bounded** | ~1–20 s | combat turns, dialogue, interactions, trade | any AGT driver, incl. `LlmDriver` | **fully event-sourced** |
| **C — Unbounded** | minutes–hours | economy, faction politics, offline progression, world simulation | background workers | event-sourced results |

The PO's "events that take a lot of time to calculate" are **Class C**. They are not a problem the loop
must solve — they are work that never touches the tick at all.

**Class A never contains an LLM call.** This is not a performance guideline; it is a structural
invariant. Any feature that wants LLM input into movement must instead express it as a Class B
*intent* that the engine resolves spatially — precisely the TG-A1 LLM-zero-space pattern.

---

## 3. The scheduler

> **SL-A3 — The scheduler never awaits a decision.** When an actor becomes ready, the scheduler
> *requests* a decision and immediately continues. The actor waits in `AwaitingDecision`; the world does
> not.

This is [Nystrom's turn-based loop](https://journal.stuffwithstuff.com/2014/07/15/a-turn-based-game-loop/)
(`getAction()` returns null → return control, don't block) generalized to slow deciders. A 3-second LLM
call does not stop the world; that actor simply is not ready yet.

```
loop(dt):                                  # driven by the host at fixed timestep
    T_sim += dt                            # logical clock, integer ticks
    advance_class_A(dt)                    # movement, collision, AOI — always completes
    while queue.head.T_due <= T_sim:       # discrete-event queue
        ev = queue.pop()
        match ev:
            ActorReady(a)      -> dispatch_decision(a); park(a)
            DecisionReady(a,d) -> validate(d) -> emit Proposal
            DeadlineExpired(a) -> emit Proposal(fallback)
    emit_proposals()                       # to commit-service; never a direct write
```

### The unifying mechanism — dispatch / ingest

> **SL-A4 — Deferred work protocol.** Any computation that cannot complete inside its class's deadline is
> **dispatched, never awaited**. Its result re-enters the simulation as a **scheduled event at a declared
> logical time**. Every dispatch carries `(deadline, fallback)`; if the deadline is reached while the work
> is still outstanding, the **fallback commits instead**.

The same mechanism covers all three slow cases — this is why the classes share one scheduler:

| Dispatch | Typical latency | Transport | Fallback on deadline |
|---|---|---|---|
| `LlmDriver.decide()` | 1–5 s | ~~ai-gateway (MCP)~~ **commit-service → ai-gateway dispatch** | AGT-A2 context fallback (`Defend`) |

> **⚠ CORRECTED 2026-07-26 (REC-61 / decision-path sweep): the transport label conflated two
> directions.** "ai-gateway (MCP)" labelled MCP as the transport for `decide()` dispatch — but
> **MCP is the LLM's tool-call direction** (AGT-A4: the model invoking proposal-schema tools
> *inside* ai-gateway's tool-loop), not the host-invokes-driver hop. Per the REC-54/55/56
> resolution: the `LlmDriver` lives in **commit-service** (Rust) and **dispatches
> `DecisionContext` to ai-gateway**; ai-gateway runs the tool-loop with the model via
> provider-registry; the return path is the EVT-T6 proposal bus. The row's latency and fallback
> are unchanged.
| Class C world-sim batch | minutes | RabbitMQ + outbox | apply next cycle |
| Offline progression | hours | scheduled worker | apply on next login |

All three already have infrastructure: `dp-kernel::outbox`, RabbitMQ, and the AGT driver contract.
**No new transport is needed** — only the scheduling discipline around them.

---

## 4. Determinism (the part that will bite)

If NPC B's `ScriptDriver` returns in 0.4 ms and NPC A's `LlmDriver` returns in 3 s, **B must not commit
first.** Arrival order is wall-clock and therefore not reproducible.

> **SL-A5 — Commit order is by logical key, never by arrival time.** The scheduler holds a priority queue
> keyed by `(T_due, action_value, actor_id)`. An early-arriving decision is **parked** until its entry
> reaches the queue head. Arrival order is invisible to the event log.

> **SL-A6 — Wall-clock decisions are recorded, never re-evaluated.** Any event whose cause is real time —
> a turn deadline expiring, an AFK timeout — is written to the log as an explicit event
> (`TurnDeadlineExpired`). **Replay reads the recorded event; it never re-consults a clock.**

Together these preserve **TDIL-A9 replay** and make divergence *testable*: replay the log, assert
byte-identical state. Retrofitting either is expensive; both are nearly free now.

Float determinism is inherited from the host choice (§6): WASM specifies strict IEEE-754 with no
implicit FMA fusion, so identical inputs produce identical floats across platforms — a genuine advantage
over native builds, where compiler flags can silently change results.

---

## 5. Turn-pressure policy (PO decision 2026-07-26)

> **SL-A7 — Turn pressure is encounter *policy*, not scheduler *branching*.** The scheduler has exactly
> one code path; pressure is a data field on the encounter.

```
TurnPolicy {
    pc_deadline:  Option<Duration>,   // None = wait indefinitely
    npc_deadline: Duration,           // ALWAYS bounded — never None
    on_expire:    FallbackAction,     // AGT-A2 context fallback
    afk_guard:    Duration,           // absolute, applies even when pc_deadline is None
}
```

| Encounter | `pc_deadline` | Rationale |
|---|---|---|
| Solo / instanced | `None` | full tactical deliberation; nobody else is waiting |
| Group (≥2 PCs) | `Some(20s)` shot clock | one slow player must not stall the party |

`npc_deadline` is **never** `None` — an unbounded NPC deadline would let a hung LLM call pin an encounter
indefinitely. The `afk_guard` (proposed default 5 min) is required even in the solo case, or a
disconnected player pins the instance forever.

The one-path property matters: two schedulers would mean two determinism stories to test.

---

## 6. Where the loop runs (PO decision 2026-07-26)

> **SL-A8 — The simulation core is a *pure* Rust crate** — no I/O, no ambient clock, no ambient
> randomness.
>
> ⚠️ **REVISED 2026-07-26 (CS-A5 / SL-D7 above).** As first written this axiom also said "*compiled to
> WASM, hosted inside the TypeScript game-server*", citing RTM-Q10. That host binding is **withdrawn**:
> `commit-service` links `sim-core` as a **native** crate, because the epoch token and `event_log` writes
> must be co-located with the island (DP-A16) and game services must be Rust (DP-A3). **The purity
> requirement — which is the load-bearing half — is unchanged**, and it was never WASM-specific: purity
> plus single-thread-steppability (SC-A2) are what make replay determinism and the chaos harness work.
> RTM-Q10's WASM remains in force for Class A walkability in `game-server`.

```
game-server  (TypeScript / Colyseus)
  ├─ room lifecycle · WebSocket · broadcast · patch-rate
  ├─ HOST: drives tick(dt), supplies inputs, ships proposals
  └─ sim-core.wasm  (Rust — PURE, no I/O)
       ├─ Class A  tick loop
       ├─ Class B  turn scheduler + priority queue
       ├─ walkability / LoS / pathfinding  (RTM-Q10, TMP_001)
       └─ damage law-chain                 (COMB_001)
                    │  Proposals only (AGT-A6)
                    ▼
              commit-service  ──▶  event store
```

**`sim-core` is pure**: `(state, inputs, dt) → (state', proposals)`. It performs no I/O, holds no clock,
and opens no socket — the host drives it. Three consequences worth stating:

1. **It cannot write state**, which enforces AGT-A6 / DP-A6 *structurally* rather than by discipline.
2. **It is trivially testable** — feed a recorded input tape, assert the output state.
3. **WASM has no ambient threads or timers**, so the purity cannot be accidentally violated.

Class C workers remain **native Rust services** (no WASM constraint) — they are dispatched by the host,
not by `sim-core`.

---

## 7. Concurrency — the loop is not one loop

> **PO challenge 2026-07-26:** *"we cannot design it like one core/thread — the game would be locked to
> one CPU's speed. This is an MMO, it needs async/parallel."* Correct, and §3–§6 as first written
> described a scheduler without a concurrency model. This section supplies it.

### 7.1 The unit of parallelism

> **SL-A9 — The unit of parallelism is the *simulation island*: a set of entities that may interact with
> each other within a single tick. One island = one queue = one thread. Islands run in parallel; nothing
> *inside* an island is parallelized.**

Sequential-inside is a deliberate choice, not a limitation:

- Entity interaction inside an island is inherently **N²** (AOI, targeting, occupancy) and parallelizes
  badly.
- Locks introduce **thread-scheduling nondeterminism**, which would destroy SL-A5/SL-A6 replay — trading
  cores for a broken event log.

Scale comes from **many islands**, which is what every production MMO does:

| System | Island unit | Inside |
|---|---|---|
| EVE Online | one process per **solar system** (single shard) | sequential |
| WoW | one process per **zone / dungeon instance** + dynamic sharding on overload | sequential |
| Orleans / Halo 4-5 | a **grain** (virtual actor) | sequential per grain, parallel across grains |
| Colyseus | a **room** | sequential |

### 7.2 LoreWeave's islands

The locked design already yields two, and V1 needs no others:

| Island | Definition | Isolation |
|---|---|---|
| **Encounter island** | an instanced combat scene (**RTM-Q4**) | **isolated by construction** — combat is embarrassingly parallel, for free |
| **Cell island** | a **CSC_001** cell + its live entities | isolated by cell boundary; cross-cell effects via §7.3 |

Cold cells (§8) instantiate no island at all.

### 7.3 Cross-island interaction

> **SL-A10 — Islands communicate only by asynchronous message, never shared memory.** A cross-island
> effect is delivered as a message ingested at the receiving island's **next tick** (+1 tick latency).
> No island ever reads another island's state directly.

This is the actor model, and it is the same dispatch/ingest protocol as SL-A4 — only the transport
differs (in-process channel rather than MCP or RabbitMQ).

**Design consequence:** island boundaries should coincide with **gameplay** boundaries (walls, doors,
scene edges) so that cross-boundary interaction is *rare*. CSC_001 cells are room-shaped, which fits.

> **SL-A11 — Ordering is *total within* an island and *causal across* islands.** No global total order
> exists, and none is required.

**This is already true of the foundation** — `event_store_pg` reads `ORDER BY aggregate_version ASC`
(per-aggregate), not a global sequence. A store built on one global sequence would need re-architecting
to support parallel islands; this one does not. Replay determinism is therefore asserted **per island**,
with cross-island causality carried by the message events themselves.

### 7.4 Migration

> **SL-A12 — An entity has exactly one owning island at any logical time.** Crossing a boundary is a
> **handoff**: source island emits `EntityDeparted`, target ingests `EntityArrived`; the entity is never
> live in two islands. This is RTM-A4 node handoff applied one level down, and it reuses the RTM-Q4
> position checkpoint.

### 7.5 The hot island — overload absorption

The fundamental limit: 100 players in one battle is one island on one core. Every MMO hits it. EVE's
answer is **time dilation** — when a node saturates, slow that system's clock (to as low as 10% in a
3 000-player battle) instead of dropping work.

> **SL-A13 — Overload is absorbed by *dilating an island's tick*, never by dropping work or splitting a
> live encounter.** The dilation factor is per-island and continuous.

**We already own this mechanism.** `TDIL_001` was designed for *fiction* time (the Dragon-Ball-chamber
case); load-dilation is **the same knob with a different driver**. Reuse the clock machinery; add a
load-derived multiplier alongside the fiction-derived one.

Turn-based combat makes this **far milder than EVE's case**: we do not simulate N entities at 20 Hz — we
resolve **one actor at a time**. Per-encounter cost scales with **turn rate**, not
`entity_count × tick_rate`.

### 7.6 Host threading — RESOLVED 2026-07-26 (SL-D20)

**Colyseus rooms all execute in one Node process, and Node is single-threaded.** Rooms provide logical
isolation but **not** core parallelism by default.

> **SL-D20 — One OS process per core, via PM2 *fork* mode.** Colyseus's own scalability guidance:
> PM2 in **fork** mode (explicitly *not* cluster mode), `instances: os.cpus().length`, rooms
> distributed across processes, **each room belongs to exactly one process**, Redis **presence**
> required for cross-process coordination.

**Consequence — cross-island messaging is IPC, not shared memory.** Separate processes cannot share an
in-process channel, so SL-A10 delivery costs ≈ **1 ms**, not microseconds. Two things make this
acceptable:

1. **§7.3 already requires cross-island messages to be rare** (island boundaries = gameplay boundaries).
2. > **SL-D20b — Spatial co-location.** Islands of the same region are placed on the **same process**,
   > so intra-region cross-island messages stay in-process. Only cross-*region* traffic pays IPC.

Redis appears here as **presence/registry only** — never as simulation state (§9).

`worker_threads` (shared memory via `SharedArrayBuffer`, µs-scale messaging) is the alternative, but
Colyseus does not distribute rooms across threads, so we would be rebuilding room distribution
ourselves. **Revisit only if profiling shows IPC dominating.** SL-A8's WASM choice keeps both doors
open — a `sim-core` instance is isolated, single-threaded and holds no ambient handles either way.

---

### 7.7 Dilation vs backpressure (SL-Q11 — RESOLVED, premise corrected)

**SL-Q11 asserted a feedback loop: dilation slows consumption → the PEL grows → EVT-L5 throttles harder
→ … Working it through, that is wrong, and the direction is worth being explicit about.**

**Dilation slows *fiction-time*, not *processing*.** An island dilated 10× advances one fiction-second
per ten wall-seconds, so action-values pop **less often in wall-clock terms** → fewer turns per second →
**fewer `LlmDriver` dispatches** → **fewer inbound proposals**. The PEL therefore **shrinks**. Dilation
is not a consumption brake; it is a **dispatch-rate brake**, and dispatch is what fills the bus.

Nor can player input take up the slack: Gate 2 buffers **one pending intent per actor** (§6), so an
input backlog coalesces rather than accumulating.

> **SL-A14 — Dilation and backpressure answer *different* overloads, and dilation relieves both.**
> `SL-A13` dilation responds to **simulation** overload (too much work per tick inside an island);
> `EVT-L5` responds to **pipeline** overload (commit-service cannot drain the bus). Because dilating
> lowers dispatch rate, it drains the PEL too — so they are **complementary, not competing**.

**The real risk is double-correction**, not oscillation: if both fire independently on one overload you
get dilation *and* producer throttling for a single cause, which feels far worse to players than either
alone.

> **SL-D26 — One actuator, two inputs.** Dilation is the **sole** first-line response; island step-time
> **and** PEL depth are both *inputs* to it, never separate controllers.
>
> ```
> load = max(normalised_step_time, normalised_pel_depth)
> dilation = f(load)                       // primary actuator, continuous
> ```

> **SL-D27 — EVT-L5 producer throttling is an ESCALATION, not a parallel path.** It engages only when
> dilation is already at its floor and load is still rising. Precedent: EVE caps TiDi at 10 % and does
> not stack a second mechanism underneath it.

**Signal scoping caveat:** dilation is **per-island** but the PEL is **per-stream**, and `CS-D10` puts
encounter proposals on the parent **cell's** stream. So PEL depth is a *cell-scoped* signal covering the
cell island **and** its encounter islands; step-time stays per-island. When a shared stream backs up,
every island feeding it dilates. Simple, and it errs toward relieving the actual bottleneck.

---

## 8. Region hotness — what ticks when nobody is there

> Nothing. A region is **Hot** if it contains ≥1 live entity (a PC, or an NPC promoted by engagement per
> AGT-D5). **Cold** regions receive **no Class A tick at all** — only Class C, at coarse intervals.

This is not a new policy; it is DF05's 95%-ambient model and ILR-A3's zone-placed-vs-live distinction,
applied to the loop. AOI (RTM-A6..A8) already defines "live". Cold→Hot transitions on PC entry.

---

## 9. Persistence — the loop writes to the event store as a *sink*

> **Concrete write path: [`17_game_data_architecture.md`](17_game_data_architecture.md) §R2** (peer
> session, 2026-07-26). It composed this tier against `02_storage` and found **GDA-F2**: `02_storage`
> §4.4/§4.6 describe a **pre-`sim-core`** write path — command handler writes directly in a DB
> transaction, validating against a *projection read* — which contradicts SC-A4 (the island is the
> writer) and SC-A1 (preconditions re-validated at step time, not at admission).
>
> **Resolved as GDA-D10, and the split is sharper than "the old design is wrong":** §4.4's *sequence*
> is obsolete, but §4.6's *synchronous in-transaction projection* is an **independent** choice that
> survives — it merely re-homes from the command handler to `commit-service` step 5. **No change is
> needed here**: that insert happens *after* `sim-core` has applied to island memory, so the log is
> still a sink. The write-amplification arithmetic below concerns **Class A at 20 Hz**, which never
> reaches that path at all (SL-D11 / SC-D11 — Class A is never event-sourced); at Class B turn rates an
> in-transaction projection costs nothing.

Published MMO practice is explicit that the database is a **persistence medium, not the source of
truth** ([PRDeving](https://prdeving.wordpress.com/2023/09/29/mmo-architecture-source-of-truth-dataflows-i-o-bottlenecks-and-how-to-solve-them/)),
with per-component durability classes rather than one uniform model
([Nockawa](https://nockawa.github.io/blog/what-game-engines-know-about-data/)). Mapped onto the classes:

| Class | Live state | Durability |
|---|---|---|
| A | in `sim-core` memory | **never event-sourced**; ephemeral + checkpoint on scene/zone transition (RTM-Q4, ILR-A2) |
| B | in `sim-core` memory | **fully event-sourced** — every committed Decision is an event |
| C | worker memory | event-sourced result only |

The arithmetic that makes this non-negotiable: naive event-sourcing of Class A at 20 Hz × 1 000 players
is **20 000 writes/s**. With checkpoint-only it is roughly *one write per zone transition* — call it
single-digit writes/s. The event store is written at **human timescale** (Class B commits, seconds
apart), never at tick rate.

This is the concrete form of RTM-A3 ("the realtime layer never writes kernel state"), and it is the
reason the existing event-sourced foundation is an asset rather than a bottleneck: **turn-based combat is
a ledger**, and ledgers are exactly what that foundation is good at.

---

## 10. Latency hiding — the FFXV lesson

FFXV and FF7R feel continuous despite discrete decisions because **the animation of the current action
covers the decision latency of the next one**. That is an architectural lever, not an art choice.

> **SL-D9 — Speculative decision prefetch.** Dispatch actor *N+1*'s `decide()` when actor *N*'s action
> **commits**, not when *N+1*'s turn arrives. One animation (~1–3 s) of cover — frequently the entire
> `LlmDriver` budget, hidden.

The risk is that state changes between prefetch and turn (the target dies). The mitigation is free:
**AGT-A2 already mandates validation at commit**, so an invalidated prefetch simply falls through to
re-decide or fallback. Prefetch is an optimization the correctness model already tolerates.

---

## 11. How this integrates with what is already locked

Every mechanism the loop needs already exists under another name. The loop is the frame they were built
for:

| Loop mechanism | Existing locked design |
|---|---|
| readiness / energy threshold | HSR action-value initiative (COMB_001 Q7) |
| `getAction()` | AGT-A1 `decide(DecisionContext) → Decision` |
| deadline escape hatch | AGT-A2 reject → context fallback |
| slow decider does not stall the world | RTM-Q4 instanced combat scene |
| decider cost tiering | AGT-A3 four drivers + AGT-D5 budget governor |
| decision is never a write | AGT-A6 / DP-A6 (Proposal → commit-service) |
| spatial resolution stays in-engine | TG-A1 LLM-zero-space, RTM-Q10 WASM |
| logical vs fiction time | TDIL-A3 per-turn O(1) generators |
| sparse cost | DF05 95%-ambient, ILR-A3 |
| island isolation (free parallelism) | RTM-Q4 instanced combat scene |
| island migration / handoff | RTM-A4 node handoff + RTM-Q4 position checkpoint |
| overload absorption (load dilation) | TDIL_001 clock machinery (fiction-time → also load-time) |
| per-island ordering | `dp-kernel` event store — already per-aggregate, not global |

**No locked decision is reopened by this document.**

---

## 12. Decisions

| # | Decision | Resolution |
|---|---|---|
| **SL-D1** | Loop model | Discrete-event scheduler over a logical clock, driven at fixed timestep by the host (SL-A3). |
| **SL-D2** | Execution classes | Three — tick-bounded / turn-bounded / unbounded; slower never blocks faster (SL-A2). |
| **SL-D3** | Slow work | Dispatch, never await; result re-enters at a declared logical time; `(deadline, fallback)` on every dispatch (SL-A4). |
| **SL-D4** | Commit ordering | By logical key `(T_due, action_value, actor_id)` — never arrival time (SL-A5). |
| **SL-D5** | Wall-clock events | Recorded as events; replay never re-consults a clock (SL-A6). |
| **SL-D6** | Turn pressure | **PO 2026-07-26** — hybrid: solo `pc_deadline: None`, group 20 s shot clock; `npc_deadline` always bounded; AFK guard always on (SL-A7). |
| ~~**SL-D7**~~ | ~~Host — `sim-core` → WASM inside the TS game-server~~ | ⚠️ **REVISED 2026-07-26 by [15](15_commit_service.md) CS-A5/CS-D7.** `commit-service` must be native Rust (it does I/O; DP-A3), and DP-A16 requires the epoch token to sit on the writer node **with** the island — so `commit-service` **hosts `sim-core` as a plain Rust crate**, and `game-server` (TS) reverts to WS edge only. RTM-Q10's WASM stays for **Class A** walkability near the client; extending it to the **Class B** scheduler was an over-reach introduced here, not in RTM-Q10. **`sim-core`'s crate contract is unchanged** — purity (SL-A8) and single-thread-steppability (SC-A2) still hold; only *who links it* changed. |
| **SL-D8** | V1 scope | **PO 2026-07-26** — design all three classes now; **stage the build** (§13). |
| **SL-D9** | Latency hiding | Speculative prefetch of the next actor's decision at current-actor commit; validated at commit (§10). |
| **SL-D10** | Region hotness | Cold regions receive no Class A tick; Class C only (§8). |
| **SL-D11** | Class A persistence | Never event-sourced; ephemeral + checkpoint at scene/zone transition (§9). |
| ~~**SL-D12**~~ | ~~Tick rate — global 20 Hz~~ | ⚠️ **SUPERSEDED 2026-07-26 by SL-D19** — a global rate wastes CPU on turn-based islands. |
| **SL-D13** | Unit of parallelism | The **simulation island** — one island = one queue = one thread; parallel across islands, sequential within (SL-A9). |
| **SL-D14** | V1 island kinds | **Encounter island** (RTM-Q4 instanced scene — isolated by construction) + **cell island** (CSC_001 cell). No others in V1 (§7.2). |
| **SL-D15** | Cross-island | **Async message only, never shared memory**; ingested at the receiver's next tick (+1 tick latency). Same dispatch/ingest protocol as SL-A4 (SL-A10). |
| **SL-D16** | Ordering | **Total within an island, causal across islands.** No global total order. Matches the existing store (`ORDER BY aggregate_version`) — no re-architecture needed (SL-A11). |
| **SL-D17** | Migration | Exactly one owning island per entity; boundary crossing is a handoff (`EntityDeparted` → `EntityArrived`), reusing RTM-A4 + the RTM-Q4 checkpoint (SL-A12). |
| **SL-D18** | Overload | Absorbed by **dilating the island's tick** (EVE TiDi), never by dropping work or splitting a live encounter. Reuses TDIL_001 clock machinery with a load-derived multiplier (SL-A13). |
| **SL-D19** | **Tick rate — per island class** *(supersedes SL-D12)* | **Cell island: 20 Hz sim / 10 Hz snapshot** + client interpolation (RTM-A2). **Encounter island: event-driven, no fixed tick** — a turn-based encounter has nothing to integrate between turns. Precedent: AzerothCore's per-map-class timers (F3); WoW ticks ~20 Hz; network tick is commonly 10–12 Hz and is **distinct from** sim tick. Doubling tick rate roughly doubles both CPU and bandwidth. |
| **SL-D20** | **Host threading** | **One OS process per core, PM2 fork mode** (Colyseus native; *not* cluster mode), `instances = os.cpus().length`, Redis presence for coordination. **SL-D20b:** islands of a region co-locate on one process, so only cross-*region* messages pay ≈1 ms IPC (§7.6). |
| **SL-D21** | **Island granularity** | The **CSC_001 cell** stays the unit. Research: best performance at **FOV ≈ 1.5 × partition size** — a **unit-free ratio**, so for a 16-tile cell the target is **AOI radius ≈ 24 tiles** (SL-Q10: CSC_001 defines no metres-per-tile, and does not need to). Cold cells **merge into a region-level island** so empty space costs no per-island overhead. |
| **SL-D22** | **Shot clock granularity** | **Per-turn**, not per-round — *forced*: HSR action-value initiative has no well-defined round (fast actors act more often), so "per-round" cannot be expressed without inventing a boundary the initiative model lacks. |
| **SL-D23** | **Load dilation vs fiction time** | **Separate multipliers.** `effective_rate = fiction_rate × load_factor`. `fiction_rate` is canonical, player-visible and **replayed**; `load_factor` is operational, invisible and **always 1.0 on replay** — forced by SL-A6, since server load is an environmental artifact, not a game event. |
| **SL-D24** | **Class C late results** | **Stall that aggregate's Class C lane only** — never Classes A/B, never another aggregate. Deadline → **skip to next cycle**, recorded. No compensating corrections in V1 (economy-scale delay is player-invisible). |
| **SL-D26** | **Overload control — one actuator** | Dilation is the **sole** first-line response; island **step-time** and **PEL depth** are both *inputs* to it (`load = max(norm_step_time, norm_pel_depth)`), never separate controllers. Prevents double-correction (§7.7, SL-A14). |
| **SL-D27** | **Producer throttling is escalation** | `EVT-L5` throttling engages **only** when dilation is at its floor and load is still rising — not in parallel with it. Precedent: EVE caps TiDi at 10 % without stacking a second mechanism. |
| **SL-D25** | **Prefetch policy** | Prefetch actor *N+1* **only if no timer/generator/AoE event is scheduled to fire before N+1's turn** — the scheduler can inspect its own timer queue, so for *scheduled* events the risk is **computable, not guessed**. Track `decisions_dispatched` vs `decisions_committed`; **auto-disable prefetch on an island exceeding ~25 % waste**. Residual risk is unpredictable player input only. Closes SL-Q5 against AGT-D5. |

---

## 13. Staged delivery

Design is full-scope (SL-D8); the build is staged, because Class B has hard prerequisites that do not
yet exist (AUD-F5 items, AUD-F6 stats, AUD-F8 commit-service).

| Stage | Delivers | Prerequisites |
|---|---|---|
| **S1** | `sim-core` crate skeleton — logical clock, priority queue, class registry, pure-function boundary, input-tape test harness. **One instance = one island** from the first commit (SL-D13). **Panic boundary + poison flag from the first commit** ([14 §10.4](14_sim_core_spec.md), SC-A8/A9) — retrofitting containment around an already-written `step()` means auditing every handler. | none |
| **S2** | Class B turn scheduler + dispatch/ingest + deadline/fallback; `ScriptDriver` only | AUD-F6 stats |
| **S3** | Proposal emission → `commit-service` → event store; **per-island** replay-determinism test | **AUD-F8 commit-service** |
| **S4** | Class A tick — movement, walkability, AOI; WASM host integration in game-server | RTM-Q10 WASM seam |
| **S4b** | **Island parallelism** — host threading model (SL-Q6), cross-island message bus, migration handoff | SL-Q6 decided |
| **S5** | `LlmDriver` dispatch + prefetch + budget governor | ai-gateway MCP tools |
| **S6** | **Class C complete** — `sim-rtsim` full rule set: NPC schedules, ambient activity, resource replenishment, ambient economy, PC→NPC conversion; dispatch/ingest via outbox + workers; the `sync` seam back to `sim-core`. **Scope raised 2026-07-26 by AUD-F13** (full daily life in V1, promoting DL from V2). | **DL feature tier must be designed first** — currently an empty namespace |
| **S7** | Load-dilation (SL-A13) wired to TDIL_001 clock | SL-Q8 decided |

**Note on S1:** the island boundary must exist in the crate's type signatures from the first commit —
retrofitting "this loop actually owns N islands" onto a single-island `sim-core` is the re-architecture
this section exists to prevent.

S1 is unblocked **today** and is the natural first code of the game tier.

---

## 14. Open questions

| # | Question | Why it is open |
|---|---|---|
**All eight SL-Q items are RESOLVED as of 2026-07-26.** Two new, narrower questions replaced them.

| # | Question | Resolution |
|---|---|---|
| ~~**SL-Q1**~~ | ~~Tick rate — is 20 Hz right?~~ | ✅ **SL-D19** — per island class: cell 20 Hz sim / 10 Hz snapshot; encounter event-driven. |
| ~~**SL-Q2**~~ | ~~One encounter or all hot regions per `sim-core`?~~ | ✅ **SL-D13/D14** — one instance per **island**. |
| ~~**SL-Q3**~~ | ~~Class C late results — stall or correct?~~ | ✅ **SL-D24** — stall that lane only; deadline → skip to next cycle, recorded. No corrections in V1. |
| ~~**SL-Q4**~~ | ~~Shot clock per-turn or per-round?~~ | ✅ **SL-D22** — per-turn; *forced*, action-value initiative has no well-defined round. |
| ~~**SL-Q5**~~ | ~~Prefetch vs the AGT-D5 budget governor?~~ | ✅ **SL-D25** — prefetch only when no scheduled event precedes the turn (risk is computable); auto-disable above ~25 % waste. |
| ~~**SL-Q6**~~ | ~~Host threading model?~~ | ✅ **SL-D20** — process-per-core, PM2 fork, Redis presence, spatial co-location. **No longer a blocker.** |
| ~~**SL-Q7**~~ | ~~Is the CSC_001 cell the right island size?~~ | ✅ **SL-D21** — yes; AOI ≈ 1.5 × cell ⇒ ~24 m; cold cells merge to a region island. |
| ~~**SL-Q8**~~ | ~~Load dilation — shared clock or second multiplier?~~ | ✅ **SL-D23** — separate multiplier; `load_factor` = 1.0 on replay. *Forced by SL-A6.* |

### Newly opened (both are measurements, not design forks)

| # | Question | Why it is open |
|---|---|---|
| **SL-Q9** | Does the ≈1 ms cross-island IPC cost (SL-D20) actually matter in play? | Only measurable once S4b runs. If cross-region traffic turns out to be common, `worker_threads` returns to the table — but that means rebuilding Colyseus room distribution, so the bar is high. |
| ~~**SL-Q11**~~ | ~~Do EVT-L5 backpressure and SL-A13 dilation fight each other?~~ | ✅ **RESOLVED 2026-07-26 → §7.7. The premise was wrong** — dilation *reduces* bus pressure rather than increasing it, so there is no feedback loop. The real risk is **double-correction**, fixed by making dilation the sole actuator with two inputs (SL-A14 / SL-D26 / SL-D27). |
| ~~**SL-Q10**~~ | ~~Is a CSC_001 tile ~1 m?~~ | ✅ **RESOLVED 2026-07-26 — the question had a false premise.** CSC_001 defines **no metres-per-tile at all**; positions are abstract `TileCoord`. Nothing in the design needs a real-world scale. The research finding is a **ratio** (FOV ≈ 1.5 × partition size) and is therefore **unit-free**, so SL-D21's target is properly stated as **AOI radius ≈ 24 *tiles*** for a 16-tile cell. The "~24 m" phrasing imported metres that do not exist in this design; corrected. If a world scale is ever defined, **nothing here changes**. |

---

## 15. Cross-references

- Opened by — [`12_module_coverage_audit.md`](12_module_coverage_audit.md) (AUD-F7)
- Movement authority / WASM seam — [`08_realtime_movement_authority.md`](08_realtime_movement_authority.md) (RTM-A1..A9, RTM-Q4, RTM-Q10)
- Position stack — [`09_interaction_layer_reconciliation.md`](09_interaction_layer_reconciliation.md) (ILR-A2, ILR-A3)
- Agent drivers / authority — [`11_agent_decision_standard.md`](11_agent_decision_standard.md) (AGT-A1..A6, AGT-D5)
- Combat initiative / damage — [`features/18_combat/COMB_001_combat_foundation.md`](features/18_combat/COMB_001_combat_foundation.md) (Q7, Q8)
- Tactical grid / LLM-zero-space — [`features/18_combat/COMB_002_tactical_grid.md`](features/18_combat/COMB_002_tactical_grid.md) (TG-A1, TG-A4)
- Time dilation / replay — [`features/17_time_dilation/TDIL_001_time_dilation_foundation.md`](features/17_time_dilation/TDIL_001_time_dilation_foundation.md) (TDIL-A3, TDIL-A9)
- Session sparsity — `features/DF/DF05_session_group_chat/DF05_001_session_foundation.md`
- Decisions / IDs — [`decisions/locked_decisions.md`](decisions/locked_decisions.md) · [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md)

**Prior art surveyed (2026-07-26):**
[A Turn-Based Game Loop — Nystrom](https://journal.stuffwithstuff.com/2014/07/15/a-turn-based-game-loop/) ·
[Game Programming Patterns — Game Loop](https://gameprogrammingpatterns.com/game-loop.html) ·
[Command pattern](https://gameprogrammingpatterns.com/command.html) ·
[MMO Architecture: source of truth & I/O](https://prdeving.wordpress.com/2023/09/29/mmo-architecture-source-of-truth-dataflows-i-o-bottlenecks-and-how-to-solve-them/) ·
[What game engines know about data](https://nockawa.github.io/blog/what-game-engines-know-about-data/) ·
[Fixed-timestep loop & determinism](https://andreleite.com/posts/2025/game-loop/fixed-timestep-game-loop/) ·
[Gambetta — client-server architecture](https://www.gabrielgambetta.com/client-server-game-architecture.html) ·
[Active Time Battle](https://en.wikipedia.org/wiki/Active_Time_Battle) ·
[Colyseus rooms](https://docs.colyseus.io/room)

**Concurrency prior art (§7, surveyed 2026-07-26):**
[Orleans — Distributed Virtual Actors for Programmability and Scalability (MSR, Halo 4/5)](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/Orleans-MSR-TR-2014-41.pdf) ·
[Orleans overview — grains](https://learn.microsoft.com/en-us/dotnet/orleans/overview) ·
[EVE Online — Introducing Time Dilation (TiDi)](https://www.eveonline.com/news/view/introducing-time-dilation-tidi) ·
[How EVE dealt with a 3 000-player battle](https://games.slashdot.org/story/13/01/29/2157234/how-eve-online-dealt-with-a-3000-player-battle) ·
[Single-shard continuous universe — spatial partitioning](https://medium.com/nguyen/a-single-shard-continuous-universe-one-world-no-boundaries-f9fee0c7d7f0) ·
[Horizontal scaling for a single-shard MMO](https://gamedev.net/forums/topic/627622-horizontal-scaling-for-a-single-shard-mmo/) ·
[Many-core MMO server (N² inside a partition)](https://gamedev.net/forums/topic/487617-many-core-mmo-server/4185898/) ·
[Locality-aware dynamic load management for MMOs](https://www.researchgate.net/publication/221643569_Locality_aware_dynamic_load_management_for_massively_multiplayer_games)
