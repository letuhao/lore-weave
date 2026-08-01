# 15 — commit-service (design)

> **Status:** DRAFT — 2026-07-26. Closes **AUD-F8**, re-scoped: the audit called it an *implementation*
> gap, but `commit-service` had **no design doc, no ownership-matrix row, and no service-shape spec** —
> only a name used across 16 files as though it existed.
> **Key finding: the semantics were never missing.** `EVT-A5/A7`, `EVT-V1..V7`, `EVT-L1..L6`, `EVT-P*`,
> `DP-A6/A15/A16/A17`, `DP-R7` already specify, in detail, *what* this role must do —
> [`07_llm_proposal_bus.md`](07_event_model/07_llm_proposal_bus.md) even has a section titled
> *"What an event-model-aware commit-service needs to know"*. What was missing is **where it runs, what
> it owns versus `sim-core`, and its interface.** This doc supplies only that.
> **Axioms** `CS-A1..A6`; decisions `CS-D1..D10`. Pending `_boundaries/` lock.
> **All four `CS-Q` open questions resolved 2026-07-26** (§9); two smaller ones opened, neither blocking.
> **PO decision 2026-07-26 (CS-Q1 → CS-A5/CS-D7):** `commit-service` **hosts `sim-core` natively**;
> `game-server` (TS) reverts to WS edge only. **Revises SL-D7/SL-A8** for the Class B scheduler;
> RTM-Q10 WASM stays for Class A walkability (§6).

> **✅ CORRECTED 2026-07-26 (REC-52)** — four fixes from the `07_event_model/` verification sweep
> (via the `18_reality_bootstrap.md` banner + `19` §12b): the **§3 origin table is superseded** by
> §7b.2's three-class model (the "player = trusted, straight to ingress" row was wrong); **CS-D9's
> System row corrected** — timers/generators are **EVT-T5 Generated** with the reduced subset
> schema → capability → causal-ref → commit, **not** EVT-T4 zero-stages (EVT-T4 is the DP-internal
> closed set of 8); **"hot-path gates on every path" scoped to turn-bearing paths** (the four
> registered gates are turn-scoped); **CS-D10** gains the EVT-L4 head-of-line coupling as a revisit
> trigger. The per-category subset registration in `_boundaries/03` rides the **REC-53 AMEND
> bundle**.

---

## 1. The one thing that decides the shape

> **DP-A16 — each active channel has exactly one writer node.** All channel-scoped writes execute on
> that node, and *"direct write attempt on a non-writer node bypassing the SDK fails at the DB layer
> because the writer's epoch token is required to insert into `event_log`."*

That constraint is load-bearing, and it settles the deployment question by itself:

> **CS-A1 — `commit-service` is a ROLE co-located on the channel's writer node, not a standalone
> microservice.** A separate deployable would (a) cross the network on every commit, (b) require the
> epoch token to be shipped off the writer node — dissolving DP-A16's forgery guard — and (c) break
> `EVT-L4`'s "process per-stream sequentially… matches DP-A16 single-writer".

**Our island *is* DP-A16's channel.** SL-A9 was a rediscovery, at the simulation layer, of what the data
plane locked in April. That is good news twice over: the models agree, and DP-A16 supplies three
mechanisms `13`/`14` did not have —

| We lacked | DP-A15/A16 already ships |
|---|---|
| forgery guard on writes | **epoch token** required for `event_log` insert |
| island migration protocol | **CP-coordinated writer handoff**; cell goes dormant when no sessions remain |
| non-owner write path | SDK-transparent **`route_channel_write` gRPC** to the writer node |
| total order within an island | `UNIQUE(reality_id, channel_id, channel_event_id)` at the DB |

> **CS-D1 — SL-A12 island migration is DP-A16 writer handoff.** Do not design a second protocol.

---

## 2. What it is: a wrapper around `sim-core`, on both sides

`sim-core` is pure and cannot do I/O (SL-A8). `commit-service` is the trusted, I/O-owning shell around it.

```
                    writer node for channel C
┌───────────────────────────────────────────────────────────────┐
│  proposal-bus consumer   (Redis Streams XREADGROUP, per-cell)  │
│         │                                                      │
│  ┌──────▼──────────── commit-service (ADMISSION) ───────────┐  │
│  │ EVT-L3 idempotency dedup                                 │  │
│  │ EVT-V5 hot-path gates  (<10ms, reject-only)              │  │
│  │ EVT-V1 validator pipeline (fixed order, EVT-A5 no-skip)  │  │
│  └──────┬───────────────────────────────────────────────────┘  │
│         │ validated input, stamped                             │
│  ┌──────▼──────────── sim-core (PURE) ─────────────────────┐   │
│  │ island = channel C · preconditions · apply · Events      │   │
│  └──────┬───────────────────────────────────────────────────┘  │
│         │ Events (facts)          Proposals (leaving island)    │
│  ┌──────▼──────────── commit-service (COMMIT) ─────────────┐   │
│  │ allocate channel_event_id under EPOCH TOKEN              │   │
│  │ insert event_log  (DP-A15 unique + monotonic)            │   │
│  │ EVT-V6 post-commit side-effects                          │   │
│  │ emit cross-island Proposals → bus (targeted at their     │   │
│  │   channel's writer node)                                 │   │
│  └──────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

> **CS-A2 — `commit-service` owns admission and durability; `sim-core` owns resolution.**
> Validation *before*, persistence *after*, purity in the middle.

---

## 3. Two input paths (EVT-A7, unchanged)

EVT-A7: *"Trusted-origin producers (orchestrator emitting deterministic content, scheduler firing
pre-declared beats) can commit directly."* So the validator pipeline is **not** on every path:

> ⚠️ **Superseded 2026-07-26 (REC-52) by §7b.2's three-class model.** The second row below was wrong
> twice: the **player is not an EVT-A7 trusted producer** — player input runs the player category
> subset (world-rule, capability, free-text sanitisation; §7b.2) and never goes straight to ingress
> — and **timers/generators are EVT-T5 Generated**, running the reduced subset
> schema → capability → causal-ref → commit, not a zero-stage pass. The table is retained for the
> EVT-T6 row and the DP-R7 citation only; §7b.2 is normative.

| Origin | Path | Why |
|---|---|---|
| **Untrusted** — `LlmDriver` proposals (EVT-T6) | bus → dedup → hot-path gates → **full EVT-V pipeline** → `sim-core` ingress | DP-R7 forbids `llm_output → dp::write`; the chain must be `llm_output → proposal_bus → validate → write` |
| ~~**Trusted** — player via gateway, timers, generators, `ScriptDriver`/`EngineDriver`~~ | ~~**straight to `sim-core` ingress** (still stamped, still dedup'd)~~ | ~~EVT-A7 trusted-origin; and EVT-P1 lists Player-Actor as producing *"via gateway-trusted commit-service"*~~ **superseded — see §7b.2** |

> **CS-A3 — The validator pipeline gates *admission*, not *execution*.** Once an input is admitted it
> enters `sim-core` as an ordinary stamped ingress item and is subject to SC-A1 ordering and
> precondition re-validation like any other.

---

## 4. Two rejection kinds — do not conflate them

This is the subtlest part of the seam, and it was previously unstated:

| | **Validator rejection** (EVT-V4) | **Precondition failure** (SC-A1) |
|---|---|---|
| When | at **admission**, before `sim-core` | at **execution**, inside `sim-core` |
| Means | "you may not do this" | "the world moved; this is stale" |
| Example | injection defense, world-rule, capability | the meteor killed the target |
| Result | commit `outcome = Rejected{reason}` via `dp::t2_write` | `Outcome::Discarded{reason}` |
| `turn_number` / `fiction_clock` | **do NOT advance** (EVT-V4) | n/a — no turn was claimed |
| Retryable by the player | yes, immediately, no penalty turn-slot | n/a |

> **CS-A4 — Both are recorded; neither is silent.** EVT-V2 forbids `silent_drop`; SC-A1 requires a
> recorded discard reason. Two different events, two different meanings, one discipline.

---

## 5. The ownership boundary (the question SC-A4 reopened)

`DP-A6` says the authoritative writer is *"the Rust game layer"* — which, since SC-A4, is `sim-core`.
So `commit-service` is **not** "the writer of everything"; that reading was never in DP-A6.

| Concern | Owner |
|---|---|
| what happens, given validated input | **`sim-core`** (SC-A4 — the island is the writer for island-scoped state) |
| whether an untrusted input may enter | **`commit-service`** (EVT-V1..V5) |
| `channel_event_id` allocation + `event_log` insert | **`commit-service`** (epoch token, DP-A15/A16) |
| post-commit side-effects (FictionClockAdvance, …) | **`commit-service`** (EVT-V6) |
| effects crossing an aggregate boundary | **`commit-service`** authorizes; emitted as Proposals (SC-A5) |
| proposal-bus consume/ack/dead-letter | **`commit-service`** (EVT-L2/L3/L6) |
| backpressure signalling | **`commit-service`** (EVT-L5 PEL monitoring) |

> **CS-D2 — `commit-service` never authors intra-island physics.** It cannot reject what `sim-core`
> resolved, because SC-A4 makes that resolution authoritative and its preconditions were already
> checked. It gates the door and it makes things durable.

---

## 6. Language and host — a genuine tension with SL-D7

`DP-A3` locks *"all new game services in Rust; SDK Rust-only"*, and `commit-service` does I/O (Redis,
Postgres), so it **cannot** be WASM. But `SL-D7` put `sim-core` in WASM inside the **TypeScript**
game-server. Both cannot sit in one process.

> **CS-A5 — RESOLVED (PO, 2026-07-26): `commit-service` hosts `sim-core` natively.** `sim-core` is a
> plain Rust crate in the `commit-service` process — **not** WASM. `game-server` (TS) reverts to being
> purely the WS edge + Colyseus rooms + patch broadcast. Island state, epoch token, validator pipeline
> and `event_log` writes are **all in one process**, which is what DP-A16 asks for and what DP-A3
> ("all new game services in Rust") requires.

```
game-server (TS)                     commit-service (Rust, native — writer node)
  WS edge · Colyseus rooms                ├─ proposal-bus consumer
  patch broadcast                         ├─ EVT-V pipeline (admission)
  └─ walkability.wasm  ← RTM-Q10   ──▶    ├─ sim-core  (plain crate, island = channel)
     (Class A, near the client)           ├─ epoch token → event_log
                                          └─ EVT-V6 post-commit side-effects
```

**This revises SL-D7 / SL-A8, and narrows RTM-Q10 rather than reversing it.** RTM-Q10's WASM decision was
justified by *movement validation needing to sit near the client for prediction* — a **Class A** concern,
and it stays exactly as locked. It never justified hosting the **Class B** island scheduler in
TypeScript; that was an over-extension introduced in `13`/`14`, not in RTM-Q10 itself. The split is now
explicit:

| Concern | Where | Form |
|---|---|---|
| Class A walkability / speed validation | `game-server` | **WASM** (RTM-Q10, unchanged) |
| Class B island scheduler + Class C dispatch | `commit-service` | **native Rust crate** |

**What `sim-core` keeps regardless:** purity (SC-A8/SL-A8 — no I/O, no ambient clock or RNG) and
single-thread-steppability (SC-A2). Those were never WASM-specific; they are what make the chaos harness
and replay determinism work. **No change to `14`'s crate contract** — only to who links it.

**Rejected alternative — Rust sidecar** (keep `sim-core.wasm` in game-server, `commit-service` native
alongside, UDS between): preserves SL-D7 literally, but puts island state on the TS side while
durability lives on the Rust side, so **every commit crosses a process boundary and the epoch token sits
away from the island it protects**. Strictly worse against DP-A16.

---

## 7. Service registration (all currently missing)

| Surface | Required entry |
|---|---|
| `_boundaries/01_feature_ownership_matrix.md` | **no `commit-service` row exists** (grep: zero matches) — needs one, plus `CS-*` prefix |
| `contracts/language-rule.yaml` | **`commit-service: rust`** — required once `services/commit-service/` lands (PRR-21 completeness; the `jobs-service` miss of 2026-06-15 is the cautionary precedent) |
| CLAUDE.md service table | absent |
| `_boundaries/03_validator_pipeline_slots.md` | already the authoritative stage list — `commit-service` is its **executor**; no new stages needed here |

---

## 7b. Encounter identity, pipeline subsets, bus topics (CS-Q2/Q3/Q4 — RESOLVED 2026-07-26)

### 7b.1 An encounter IS its own channel (CS-Q2 → CS-A6)

> **CS-A6 — An encounter island is an *ephemeral child channel* of its cell,
> `level_name = "encounter"`, `Dissolved` on resolution.**

This needs **no DP change** — the existing primitives already permit it:

| DP-Ch1 fact | Consequence |
|---|---|
| `level_name: String` is **free-form** ("tavern", "cell", …) — no closed enum | `"encounter"` is legal today |
| `ChannelLifecycle { Active, Dormant, Dissolved }`, *"dissolution is terminal"* | exactly an encounter's lifecycle |
| strict tree, one parent, **max depth ≤ 16** | `… → cell → encounter` fits with room to spare |
| **Q27 bubble-up** — "aggregator at parent channel reading descendant events" (Unblocked) | encounter resolution bubbles to the cell as a **summary** |
| **Q32 privacy bubble-up** — visibility flag in `metadata` | non-participants don't see per-round deltas |

**Why its own channel rather than an aggregate inside the cell channel:**

- **Ordering.** DP-A15 gives one total order per channel. Sharing the cell's sequence would interleave every combat round into the cell's `channel_event_id` stream and flood it — a 12-round fight becomes ~50 cell events that non-participants must filter.
- **Visibility.** RTM-Q4 locked combat as an *instanced dedicated scene*; instancing implies separate visibility, which is a channel property, not an aggregate property.
- **Islands.** SL-A9 wants one queue per island. Two channels = two islands = two queues.

> **CS-D8 — The encounter channel's writer is its parent cell's writer node.** Participants come from
> that cell, and SL-D20b co-locates a region on one process — so encounter↔cell messages stay
> **in-process** and never pay the ≈1 ms IPC of SL-D20.

**Aggregate vs channel — both, and they are not in tension.** `combat_session` stays the **aggregate**
(the state, as registered 2026-06-20); the encounter channel is its **ordering + visibility scope**.
[14 §5.1](14_sim_core_spec.md)'s `aggregate_type = combat_session` is unchanged; it simply now also has a
`channel_id`.

### 7b.2 There is no "trusted fast path" — subsets are category-declared (CS-Q3)

> ⚠️ **CS-D4 as first written was wrong**, and invited someone to build a bypass. Corrected:

> **CS-D9 — `commit-service` never *chooses* which validator stages run.** The subset is declared
> **per EVT-T\* category** and locked by **EVT-V1** (*"EVT-T4 System runs zero stages; EVT-T8
> Administrative runs schema + capability + S5 dual-actor + causal-ref but skips A6 + canon-drift"*).
> `commit-service` **applies** the declared subset. There is no trust-based shortcut to invent.
>
> **Corrected 2026-07-26 (REC-52):** EVT-V1's T4 zero-stage row is real but applies **only to the
> DP-internal closed set of 8 sub-types** (EVT-P4 — no service can emit them). **Timers and
> generators emit EVT-T5 Generated**, whose declared subset is
> **schema → capability → causal-ref → commit** — reduced (no A6, no canon-drift), not zero. The
> first version of this decision mapped them to T4, the same error `18`'s RBS-A7 inherited.

Two corrections follow *(second-corrected 2026-07-26 — gate scope)*:

- **Hot-path gates (EVT-V5) run on every *turn-bearing* path.** They are about **state validity,
  not trust** — turn-slot availability, idempotency lookup, concurrent-turn detection, mortality. A
  trusted timer still cannot make a dead actor act, and a player still cannot take two turns at
  once. **CS-Q3 → yes**, scoped: the four registered gates are **turn-scoped**, so on non-turn
  paths (e.g. bootstrap seeding, where no actor or turn slot exists yet) only the gates whose
  subject exists run — in seeding's case exactly the idempotency gate (`18` RBS-A8). "Every path"
  as first written overclaimed.
- **The player is *not* an EVT-A7 trusted-origin producer.** EVT-A7's examples are *orchestrator* and
  *scheduler* — deterministic machine output. EVT-P1 lists Player-Actor as producing *"via
  gateway-trusted commit-service"*: commit-service is the trusted producer **on the player's behalf,
  after validating**. Player input still needs world-rule (EVT-V4's own example is a 23-day `/travel`
  rejected at world-rule) and free-text injection sanitisation.

**Three origin classes, not two:**

| Origin | Hot-path gates | Main pipeline |
|---|---|---|
| **LLM proposal** (EVT-T6, `LlmDriver`) | ✅ | full — incl. A6 injection defense + canon-drift |
| **Player** (via gateway) | ✅ | category subset — world-rule, capability, free-text sanitisation; not LLM-output stages |
| **System** (timers, generators, `Script`/`EngineDriver`) | ✅ (turn-scoped) | ~~zero stages (EVT-V1, EVT-T4 System)~~ **corrected 2026-07-26 (REC-52): EVT-T5 Generated — schema → capability → causal-ref → commit** (reduced, not zero; true T4 zero-stage is DP-internal only) |

> **Registration note (added 2026-07-26):** category-declared subsets skip stages by *declaration*,
> which must be reconciled with EVT-A5's no-skip rule — the reconciliation is that each category's
> subset is itself **registered in `_boundaries/03_validator_pipeline_slots.md`**, so a skipped
> stage is a declared absence, not a bypass. The per-category subset change above (System = EVT-T5
> reduced subset) **needs that registration and it rides the REC-53 AMEND bundle**; until it lands,
> CS-D2/CS-D9 cite this section.

### 7b.3 Encounter proposals ride the parent cell's stream (CS-Q4)

> **CS-D10 — No per-encounter bus stream.** Encounter proposals go to the **parent cell's** stream;
> `target_channel` distinguishes them.

EVT-L1 states topic granularity is operational and all EVT-L* designs are granularity-agnostic, so this
is reversible. Rationale: encounters are short-lived, so a stream per encounter churns Redis keys and
wastes per-stream `MAXLEN` budget (EVT-L5); and the **same writer node** consumes both, so a separate
stream buys no routing benefit. **Revisit** if measurement shows encounter traffic starving cell traffic
— which EVT-L5 backpressure would surface as a capacity signal rather than silently.

> **Revisit trigger added 2026-07-26 (REC-52):** sharing the cell stream also couples the two at the
> **head of line** — EVT-L4's *"process per-stream sequentially"* means a slow encounter admission
> blocks every cell proposal queued behind it (and vice versa), which is a **latency** coupling
> EVT-L5's depth-based backpressure does not surface. Head-of-line stalls between encounter and cell
> traffic are the second revisit signal, alongside starvation.

---

## 8. Decisions

| # | Decision | Resolution |
|---|---|---|
| **CS-D1** | Migration protocol | SL-A12 island migration **is** DP-A16 writer handoff — do not invent a second one. |
| **CS-D2** | Authority split | `commit-service` gates admission + owns durability; it never authors intra-island physics (SC-A4). |
| **CS-D3** | Deployment | Co-located role on the writer node (CS-A1), never a standalone microservice — forced by the epoch token. |
| ~~**CS-D4**~~ | ~~Trusted fast path~~ | ⚠️ **CORRECTED 2026-07-26 → CS-D9.** As written ("trusted-origin input skips the EVT-V pipeline") it was wrong and invited a bypass. The subset is **category-declared** by EVT-V1; `commit-service` applies it and never chooses it (§7b.2). |
| **CS-D5** | Rejection taxonomy | Validator rejection (EVT-V4, no turn advance) and precondition discard (SC-A1) are distinct events; neither is silent. |
| **CS-D6** | Reuse, don't redesign | The pipeline, bus, dead-letter, retry and idempotency semantics are **already locked** — this doc adds shape only, and changes no EVT-*/DP-* rule. |
| **CS-D7** | **Host shape** | **PO 2026-07-26 — Rust host (CS-A5).** `commit-service` links `sim-core` as a native crate; `game-server` (TS) is the WS edge only. **Revises SL-D7/SL-A8** (WASM-in-game-server) for the Class B scheduler; **RTM-Q10 unchanged** for Class A walkability. `sim-core`'s purity + single-thread-steppability are unaffected — [14](14_sim_core_spec.md)'s crate contract does not change, only who links it. |
| **CS-D8** | Encounter writer node | The encounter channel's writer **resolves to its parent cell's writer node** — participants come from that cell, and SL-D20b co-locates a region on one process, so encounter↔cell messaging stays in-process (§7b.1). **Mechanism (CS-Q5, corrected):** *CP-assigned* per DP-A16's non-cell rule, honouring a **co-location hint** passed at DP-Ch8 creation — **not** implicit inheritance, which would have violated DP-A16. |
| **CS-D9** | Validator subsets | `commit-service` **applies** the EVT-V1 category-declared subset; it never chooses one. **EVT-V5 hot-path gates run on every turn-bearing path** (state validity, not trust; the four registered gates are turn-scoped). Three origin classes: LLM proposal / player / system (§7b.2). **Corrected 2026-07-26 (REC-52):** System = timers/generators is **EVT-T5** with the reduced subset (schema→capability→causal-ref→commit), not EVT-T4 zero-stages; subset registration in `_boundaries/03` rides the REC-53 AMEND bundle. |
| **CS-D10** | Bus topics | **No per-encounter stream** — encounter proposals ride the parent cell's stream, distinguished by `target_channel`. Reversible; EVT-L1 makes granularity operational (§7b.3). **Revisit triggers (2026-07-26):** EVT-L5 starvation *and* EVT-L4 head-of-line stalls between encounter and cell traffic. |

## 9. Open questions

| # | Question |
|---|---|
**All four CS-Q items are RESOLVED as of 2026-07-26.**

| # | Question | Resolution |
|---|---|---|
| ~~**CS-Q1**~~ | ~~Host shape — sidecar vs Rust host~~ | ✅ **CS-A5 / CS-D7** — Rust host. **No longer blocks S3.** |
| ~~**CS-Q2**~~ | ~~Encounter: own channel or sub-scope of the cell?~~ | ✅ **CS-A6 / CS-D8** — its own **ephemeral child channel** (`level_name = "encounter"`, `Dissolved` on resolution), writer = parent cell's node. Legal under DP-Ch1 today; **no DP change** (§7b.1). |
| ~~**CS-Q3**~~ | ~~Do hot-path gates run on the trusted path?~~ | ✅ **CS-D9** — **yes, on every path**; and CS-D4 was corrected: subsets are category-declared by EVT-V1, never chosen by `commit-service` (§7b.2). |
| ~~**CS-Q4**~~ | ~~Per-encounter bus stream?~~ | ✅ **CS-D10** — no; encounter proposals ride the parent cell's stream (§7b.3). Reversible. |

### Newly opened (both small, neither blocking)

| # | Question |
|---|---|
| ~~**CS-Q5**~~ | ~~CP writer assignment or implicit inheritance?~~ | ✅ **RESOLVED 2026-07-26 — CP-assigned, with a co-location hint.** DP-A16's letter puts an encounter in the **non-cell** bucket ("*any non-cell level*: writer = CP-assigned at channel creation, persistent for the channel's lifetime"), so **implicit inheritance would have violated the invariant**. CS-D8's *outcome* (encounter writer = parent cell's node) is preserved by the correct mechanism: **CP assigns it, honouring a co-location hint** naming the parent cell's writer. CP already owns placement, so this needs **no DP-A16 amendment** — only that the hint be passed at `DP-Ch8` channel creation. |
| **CS-Q6** | What is the **shape of the encounter→cell bubble-up summary** (Q27), and what does Q32 privacy hide from non-participants — per-round deltas only, or participant identities too? Feature-owned (COMB), not `commit-service`. |
| **CS-Q7** | **Reconnect mid-encounter** — what does a returning client receive? DP-A15 mentions a `from_channel_event_id` **resume token** for durable subscribe, so the mechanism likely exists and needs wiring rather than designing. Confirm whether an ephemeral encounter channel supports resume, or whether reconnect always means full-state. *(Needed at S4b, not S1.)* |
| **CS-Q8** | **Joining an in-progress encounter** — can a player walk into a fight? Requires mid-combat channel membership (DP-Ch9 session move) **and** an initiative answer: where does a late joiner land in the action-value queue? Feature-owned (COMB) but touches CS-A6 channel membership. |

## 10. Cross-references

- Proposal bus (EVT-L1..L6) — [`07_event_model/07_llm_proposal_bus.md`](07_event_model/07_llm_proposal_bus.md)
- Validator pipeline (EVT-V1..V7) — [`07_event_model/05_validator_pipeline.md`](07_event_model/05_validator_pipeline.md)
- Untrusted-origin lifecycle (EVT-A7) + ordering (EVT-A5) — [`07_event_model/02_invariants.md`](07_event_model/02_invariants.md)
- Producer roles (EVT-P1, EVT-P6) — [`07_event_model/04_producer_rules.md`](07_event_model/04_producer_rules.md)
- DP-A6 / DP-A15 / DP-A16 / DP-A17 — [`06_data_plane/02_invariants.md`](06_data_plane/02_invariants.md)
- DP-R7 no-direct-LLM-write — [`06_data_plane/11_access_pattern_rules.md`](06_data_plane/11_access_pattern_rules.md)
- Simulation loop / islands — [`13_simulation_loop.md`](13_simulation_loop.md)
- `sim-core` spec (SC-A4/A5 authority) — [`14_sim_core_spec.md`](14_sim_core_spec.md)
- Audit finding — [`12_module_coverage_audit.md`](12_module_coverage_audit.md) (AUD-F8)
