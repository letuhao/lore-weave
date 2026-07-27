# 22 — Ingress & Action Admission Standard

> **Status:** DRAFT — 2026-07-27. Settles three questions asked together, because they are one
> question: *where does every actor's request converge*, *how is spam/abuse stopped*, and *does
> validation belong inside or outside the simulation loop*.
> Axioms `IAS-A1..A9`, decisions `IAS-D1..D7`, open `IAS-Q1..Q5`.
> **Prefix `IAS` registered** in [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
> `_boundaries/` ownership claim rides the pending batch with `CWC` / `CEI`.
>
> Cites rather than restates: [07 event model](07_event_model/02_invariants.md) (EVT-A1/A7/A8) ·
> [11 agent decision standard](11_agent_decision_standard.md) (AGT-A1/A2/A6) ·
> [13 simulation loop](13_simulation_loop.md) (classes, SL-A4) ·
> [14 sim-core](14_sim_core_spec.md) (preconditions, generations) ·
> [21 ceilings](21_architecture_ceilings.md) (the cost budget this standard is priced against) ·
> [`_boundaries/03_validator_pipeline_slots.md`](_boundaries/03_validator_pipeline_slots.md) (stage list).

---

## 1. The question that generated this document

> *"Ingest và validator nằm NGOÀI loop để tránh loop compute latency, hay để hết vào TRONG loop?"*

The instinct behind the question — *protect the loop, it is the serialization domain* — is correct.
The conclusion it suggests — *therefore move validation out* — is **wrong for the state-dependent
half, and dangerous**, because a state check performed outside the loop is not merely imprecise: it
is a **TOCTOU race** (time-of-check to time-of-use). Validate "target is alive" outside, and by the
time the loop applies the action the target may be dead, the encounter dissolved, the actor's turn
spent. The check passed. The world had moved.

And the cost premise does not survive contact with measurement. From [21](21_architecture_ceilings.md):

| Operation | Cost | Ratio |
|---|---:|---:|
| One precondition check (in-loop) | **≈ 4 ns** | 1× |
| One island step | ≈ 176–229 ns | ~50× |
| **One durable commit** | **≈ 5 400 000 ns** | **~1 350 000×** |

**IAS-A1 — in-loop validation is free at the scale that matters.** A precondition check is ~4 ns
against a 5.4 ms commit — six orders of magnitude below the dominant term. Moving a state-dependent
check out of the loop to "save loop time" optimises a cost that does not exist, and buys a
correctness race with the savings.

**The answer is BOTH, split by a rule that has nothing to do with cost.**

---

## 2. IAS-A2 — the partition rule (the load-bearing axiom)

> **A check belongs OUTSIDE the loop if, and only if, it is a pure function of the message, or of
> state the loop does not mutate. Every check that reads state the loop mutates belongs INSIDE.**

Not "cheap outside, expensive inside". Not "fast path / slow path". The partition is by **what
state the check reads**, because that is what determines whether the check can still be *true* when
the action is applied.

| | Outside (pre-loop) | Inside (at step) |
|---|---|---|
| Reads | the message; slow-moving reality state | island state |
| Correct because | the input cannot change | it IS the serialization point |
| Parallelisable | ✅ fully | ❌ serialized by construction |
| Examples | schema · vocabulary · idempotency-by-id · signature · rate limit · capability · lex · heresy · canon-drift | is it your turn · is the target alive · cooldown elapsed · in range · do you hold the item · resource ≥ cost |

**Corollary (IAS-A2.1):** a check on state the loop mutates may still run outside as an
**optimisation** — to reject early and cheaply — but it is then **advisory, never authoritative**,
and the same predicate MUST be re-checked inside. An outside-only state check is a defect, not a
performance win.

**Corollary (IAS-A2.2) — the trap in the current stage list.** Of the ten registered stages, most
are correctly outside-only. **`world-rule` and the `structural-validators` sub-stages
(3.5.a entity_affordance, 3.5.b place_structural, 3.5.e item_structural) read state the loop
mutates** — target aliveness, holder graph, item ownership. Implementing them as outside-only would
introduce exactly the race above. They must emit obligations (§3), not verdicts.

---

## 3. IAS-A3 — preconditions ARE the seam (and it is already built)

The two halves are not merely both present; they are **connected by a wire that already exists in
the kernel**. The outside pipeline's job is not only to accept or reject. It is to **compile the
message into a claim plus the proof obligations the loop must discharge at step time**:

```rust
// crates/sim-core/src/types.rs:96 — each variant carries the world-version it was true under
pub enum Precondition<D: Domain> {
    EntityAlive     { id: EntityId, generation: Gen },
    EncounterActive { id: EntityId, generation: Gen },
    ActorEligible   { id: EntityId, turn: Tick },      // ← the turn-slot / cooldown check
    ResourceAtLeast { id: EntityId, kind: D::ResKind, amount: i64 },
    IslandOwns      { id: EntityId },
}
```

The loop discharges them in a fixed order (`island.rs`): **generation gate → I2 dedup → deadline →
`check_all`**, and a failure is a *recorded outcome*, never a silent pass:
`Outcome::Discarded { reason: DiscardReason::PreconditionFailed(violation) }`, with the domain's
declared `Fallback` (Drop · Substitute · Buffer · Notify) deciding what the player sees.

**This is optimistic concurrency control, and the `generation` field is the version stamp.** The
outside validator reads state and asserts *"this was true at generation G"*; the island — the only
place where "now" has a definite meaning — checks G still holds. If the world moved, the claim is
discarded with a reason, not applied against stale assumptions.

**IAS-A3 — outside validation emits OBLIGATIONS, not verdicts, for every state-dependent
predicate.** An admission stage that reads mutable state and returns only pass/fail has thrown away
the information the loop needs to be correct.

### 3.1 What is actually wired today

| Path | Preconditions attached | |
|---|---|---|
| `admission.rs:277` (the **production** T1/T6 rail) | **`preconditions: vec![]`** | 🔴 empty obligation list |
| `main.rs:167` (the POC-2 turn runner) | `vec![Precondition::EntityAlive { … }]` | 🟡 more careful than production |
| `crates/sim/tests/*` | `ActorEligible`, `EntityAlive`, … | ✅ exercised only in kernel tests |

**The seam is built, the kernel honours it, and the production ingress sends nothing through it.**
`ActorEligible` — which *is* the turn-slot check — has never run outside a unit test. This single
line is also the whole explanation for the spam finding in §5: with an empty obligation list, there
is nothing for the loop to re-check, so 100 distinct requests are 100 valid actions.

---

## 4. IAS-A4..A5 — where requests converge, and how compliance is enforced

### IAS-A4 — one logical front door, four physical lanes (stated, not implied)

[EVT-A8](07_event_model/02_invariants.md) already mandates that every untrusted-origin producer
emits **EVT-T6 Proposal onto the bus, never a direct commit**, and [EVT-A7](07_event_model/02_invariants.md)
assigns each of seven producer roles its category and trust level. [AGT-A1](11_agent_decision_standard.md)
gives all four drivers (Llm · Script · Engine · Human) one interface, `decide(ctx) → Decision`, and
[AGT-A6](11_agent_decision_standard.md) makes a Decision a **proposal that executes nothing**.

That is the right architecture and it matches the field: in **Mudguy**, NPCs log into the MUD as
ordinary players over telnet — indistinguishable to the server; the **Bounded Autonomy** framework
(arXiv 2604.04703) organises LLM characters around agent-agent, agent-world execution, and
player-agent steering with an action-grounding pipeline; the underlying shapes are **Command +
Event Queue** and the **actor mailbox**.

What is missing is an honest statement that there are **four lanes, not one**:

| Lane | Carries | Admission | Correct? |
|---|---|---|---|
| **L1 proposal bus** (Redis Streams) | T1 Submitted · T6 Proposal | full pipeline | ✅ the front door |
| **L2 DP-internal** | T4 System | *"trusted by construction"* | ⚠️ assumed, unverified (IAS-Q3) |
| **L3 Class C workers** | T3 Derived, batch | own quota | ✅ different tempo, not the loop |
| **L4 Class A movement** | position intents, ~20 Hz | edge WASM + authoritative re-check | ✅ **never event-sourced** (SL-D11) |

L4 deserves emphasis: it is the one case where the partition rule's economics genuinely change.
At 20 Hz the per-tick budget is real, which is why walkability runs as WASM **at the edge** — but
per IAS-A2.1 that is an *advisory* check for prediction, re-verified server-side (RTM-A9). The rule
holds; only the placement of the advisory copy differs.

### IAS-A5 — the standard must be a TYPE, not a convention

Today nothing enforces any of the above:

```rust
// crates/sim-core/src/island.rs:178 — QueuedInput has public fields
pub fn submit(&mut self, lane: Lane, mut input: QueuedInput<D>) -> Seq
```

Anyone can construct a `QueuedInput` and call `submit()`. This is not hypothetical: **`main.rs`
already does it**, feeding `decide()` output straight into the island with no `admit_*` call.

**IAS-A5 — the island accepts only a token the admission module can mint.**

```rust
pub struct Admitted<D: Domain>(QueuedInput<D>);          // field PRIVATE to the admission module
impl<D: Domain> Island<D> {
    pub fn submit(&mut self, lane: Lane, input: Admitted<D>) -> Seq;
}
```

Bypassing admission then **fails to compile** — the compiler becomes the enforcement point, and no
lint, review or convention is required. There is direct precedent in this kernel: `dissolve(self,
reason)` **consumes** the island so that "Gone" is unrepresentable by move semantics. IAS-A5 is the
same technique applied to the front door.

---

## 5. IAS-A6..A8 — abuse resistance

### The finding this section exists for

Three layers should stop *"a player sends 100 attack requests"*. All three are open:

1. **`ChannelRoom` has no rate limiter.** `MessageRateLimiter` exists
   ([`ws/rate-limit.ts`](../../../services/game-server/src/ws/rate-limit.ts), 30 msg/10 s) and is
   wired into **`EchoRoom`** — the V0 demo — but not into the room that carries the game.
2. **Idempotency cannot help, by design.** `client_request_id` is **client-minted** (deliberately —
   it is what makes a retry idempotent). 100 requests with 100 distinct ids are 100 distinct
   *intents*; EVT-L3 dedup correctly admits all of them.
3. **No turn gate.** `turn-slot availability` and `world-rule` are `NotRun`, and per §3.1 the
   obligation list is empty, so the loop re-checks nothing.

> ⚠️ **Read from code, not yet executed.** Per the repo's bite discipline this is a *hypothesis*
> until a test demonstrates it. Tracked as **IAS-Q1**; the test is small (drive `admit_t1` + an
> island with 100 distinct `client_request_id`s and count commits).

### IAS-A6 — the rate limit must sit ABOVE the durable boundary

This is the non-obvious one, and it comes directly from the [21](21_architecture_ceilings.md)
measurements. **CS-A4 makes rejections durable events.** Combine that with CEI-2 (≈170 commits/sec
per channel, 5.4 ms each) and:

> 100 spam requests that are all **rejected** still write 100 rejection events — **≈ 0.57 s of that
> channel's entire commit budget.** The attacker does not need a single action to succeed; being
> refused loudly enough *is* the attack.

**IAS-A6 — a transport-level refusal MUST NOT produce an event.** Rate limiting is drop/close, with
no durable trace beyond a counter. An **admission**-level rejection stays durable: that is a genuine
verdict about a genuine intent, and CS-A4's guarantee (no silent rejection) is about *those*. The
boundary between "counted" and "committed" is the boundary between transport and admission.

### IAS-A7 — four layers, each catching what the others structurally cannot

| # | Layer | Stops | Cost | Durable |
|---|---|---|---|---|
| 1 | **Transport** — token bucket + connection cap at the WS edge | floods, packet spam | ~µs, in-process | ❌ **never** (IAS-A6) |
| 2 | **Session** — one in-flight turn per actor (PL_002 §6) | double-submit, races | O(1) | ❌ |
| 3 | **Turn economy** — turn slot, cooldown, GCD, action points | the actual rules of play | **≈ 4 ns, in-loop** | ✅ |
| 4 | **Behavioural** — loop-signature (same tool + same args repeated) | LLM runaway, bot farming | async, off the path | ✅ audit |

Layers 1–2 match standard practice: the gateway enforces per-user/per-endpoint quotas once auth
knows *who*, while the service layer enforces feature-specific rules the gateway cannot see; burst
size is set from the **worst-case legitimate burst** (~20–30), not the average. Layer 4 is borrowed
from LLM-agent guardrails, where a repeated identical tool call is the signature that pure rate
limits miss — and it matters here because an NPC's decision **costs real money**, making a runaway
loop a *financial* denial of service, not merely a compute one (AGT-D5).

**IAS-A8 — cheap-and-approximate at the edge; authoritative-and-exact in the loop. Never the
reverse.** The reason is structural, not stylistic: the island is single-writer and already holds
the actor's state in memory, so a cooldown check is a `BTreeMap` lookup (~4 ns). The same check at
the edge needs cross-replica shared state → Redis → ≈ 0.35 ms — roughly **90 000× more expensive**,
and still not authoritative. Server clock is the sole source of truth; a client-supplied timestamp
is never trusted, and a cooldown enforced client-side is bypassed trivially.

### IAS-A9 — the turn economy binds every world-acting actor

| Actor | L1 transport | L3 turn economy | Note |
|---|---|---|---|
| Player | ✅ per-connection | ✅ | untrusted |
| **NPC (LLM driver)** | ❌ (never touches WS) | ✅ **mandatory** | absent ⇒ one loop = 1 000 strikes; **+ token budget** |
| NPC (script driver) | ❌ | ✅ | cheap to run, still bound by the rules |
| Class C worker | own quota | ❌ (not turn-taking) | outbox + RabbitMQ |
| DP-Internal (T4) | ❌ | ❌ | "trusted by construction" — **assumed** (IAS-Q3) |
| Admin (T8) | ❌ | ❌ | dual-actor for Tier 1 |

Limiting only players is the classic error: a malfunctioning LLM NPC would still be able to destroy
an encounter from the inside.

---

## 6. Decisions

| Id | Decision | Rationale |
|---|---|---|
| **IAS-D1** | Validation is **split by state-readership**, not by cost | IAS-A2; an outside state check is a TOCTOU race |
| **IAS-D2** | Outside stages emit **`Precondition` obligations** for every mutable-state predicate | IAS-A3; the kernel already discharges them with a version stamp |
| **IAS-D3** | `Island::submit` takes **`Admitted<D>`**; `QueuedInput` fields become private | IAS-A5; makes bypass a compile error, precedent `dissolve(self)` |
| **IAS-D4** | Transport-level refusal is **drop/close, never an event**; admission-level rejection stays durable | IAS-A6; otherwise rejection is a write amplifier |
| **IAS-D5** | `MessageRateLimiter` is wired into **`ChannelRoom`**, above the durable boundary | the room that carries the game currently has none |
| **IAS-D6** | Turn economy (`ActorEligible` + cooldown) applies to **every world-acting actor**, NPCs included | IAS-A9 |
| **IAS-D7** | The four lanes (L1–L4) are **declared**, and any new producer must name its lane | IAS-A4; a lane that is not named is a bypass nobody reviewed |

## 7. Conformance — current state against this standard

| Requirement | State | Evidence |
|---|---|---|
| Single logical front door (EVT-A8) | ✅ designed, ✅ used by the spine | `spine.rs` → `admit_t6` |
| …enforced structurally | 🔴 **no** | `main.rs` bypasses; `submit` takes a public struct |
| Stateless validation outside | ✅ | schema · idempotency · vocabulary |
| State-dependent validation inside | 🔴 **not wired** | `admission.rs:277` → `preconditions: vec![]` |
| Turn slot / cooldown | 🔴 **absent** | `ActorEligible` used only in `crates/sim/tests/*` |
| Transport rate limit on the game room | 🔴 **absent** | limiter wired to `EchoRoom` only |
| Rate limit above the durable boundary | ⚪ n/a — no limiter to place yet | — |
| Behavioural / loop-signature detection | 🔴 absent | — |

## 8. Open

| Id | Question | Resolved by |
|---|---|---|
| **IAS-Q1** | Does the 100-request spam actually commit 100 actions? | The bite-test in §5 — **do this before any fix**, or the fix is unfalsifiable |
| **IAS-Q2** | Is `producer_service` on the bus **authenticated**? | If a compromised service can emit T1 for any actor, everything above is moot |
| **IAS-Q3** | Is EVT-T4 "trusted by construction" verified, or assumed? | Audit L2; a trusted lane nobody checks is a bypass |
| **IAS-Q4** | Ordering & fairness when N actors submit simultaneously | Doc 13 §4 flags arrival order as wall-clock; anti-starvation undecided |
| **IAS-Q5** | Edge backpressure — what does the front door return when the island saturates? | EVT-L5 forbids silent drop; SL-A14 dilation is the *internal* actuator only |

---

## 9. Build order

1. **IAS-Q1 bite-test** — prove the exploit. Nothing else is falsifiable until it exists.
2. **IAS-D5** — wire the limiter into `ChannelRoom` (smallest change, stops floods immediately).
3. **IAS-D3** — the `Admitted<D>` token; `main.rs` stops compiling, which is the point.
4. **IAS-D2 + IAS-D6** — admission emits obligations; `ActorEligible` + cooldown go live in-loop.

This sequence precedes the island manager. Building a manager on an unenforced front door
replicates the hole N times.
