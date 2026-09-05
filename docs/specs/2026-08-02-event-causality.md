# Event and causality — what an event IS, and what we store

**Status:** DESIGN, awaiting PO review · **Date:** 2026-08-02 · **Base:** `50bff49a4`
**Run state:** [`docs/plans/2026-08-02-event-causality-RUN-STATE.md`](../plans/2026-08-02-event-causality-RUN-STATE.md) — `E-1..E-3` sealed there, `I-1..I-11` inherited, findings `F-1..F-36`.
**Evidence:** five investigation reports, preserved at [`2026-08-02-event-causality-research/`](2026-08-02-event-causality-research/).

> ## 🔴 RED-TEAM VERDICT 2026-08-02 — READ BEFORE CITING ANY `EV-*` NUMBER
>
> Three cold-start reviewers with disjoint lenses (storage/retention · causality/runtime ·
> ontology/expressiveness) returned **ten FATALs**. **The DIAGNOSIS survives; most of the PRESCRIPTIONS
> do not.** Full adjudication in the RUN-STATE §7.1b–§7.1c; the status of each claim:
>
> | | claims |
> |---|---|
> | ✅ **survived, attacked from several sides** | **`EV-5`** the closed fold · **`EV-3`** trust is the producer's · **`EV-2`**'s conclusion (**on corrected, opposite evidence** — see §2.2) · **`EV-7`** · §3.2's DERIVED class · §1's measurements |
> | ❌ **REFUTED** | **`EV-18`** (retention classes cover 3 of 15 registered types) · **`EV-19`** (backwards — `archive-worker` does not carry `ruleset_digest`, and **nothing anywhere compares it**) · **`EV-15`** (false stage by stage) · **`EV-13`**'s second bound (not a bound, not deployed) |
> | ⚠ **REDESIGNED in §9.4** (they failed for one shared cause — no theory of ownership for anything spanning aggregates) | **`EV-14` → `EV-14′`** property + two mechanisms by scope · **`EV-17` → `EV-17′`** ambient context, nesting on the occurrence · **`EV-1` → `EV-1′`** lifetime classification, not a partition |
> | ⚠ **reason wrong, conclusion open** | **`EV-21`** · **`EV-16`** (its own §9.3 falsifier fired) |
>
> **The common cause, and it is one thing:** every FATAL is a claim about the **deployed** system that
> was **inferred rather than measured** — a component's real column list, its call sites, its
> implementation language. Each was one unopened file away. **Sections 2, 4 and 7 (what an event is, the
> eleven shapes, the rot ledger) rest on measurement and stand. Section 3's storage answers and §9's
> evaluations must be re-grounded before anything is built on them.**

> **Scope.** Two questions and no others. **`Q-A` — what IS an event.** **`Q-B` — what do we store.**
> Transport is out (`06_data_plane` is LOCKED and owns ordering, durability, fan-out). Per-feature event
> content is out — that is each feature's vocabulary. Implementation is out; no code this round.
> The **actor substrate is out** (`E-3`) — a sibling round owns it; its `D-1..D-109` are read here as
> evidence and are never re-opened.

---

## 1. What this settles, and why it could not wait

Four things were measured before any of this was written.

**① The causality layer is not half-built. It is unbuilt, with the holes pre-drilled.** There is no code
path where committing event A produces event B. `causation_id` has **five occurrences repo-wide** — a
declaration, an `is_empty()`, a doc line, **one assignment inside `mod tests`**, and a comment in a
dropped table. `causal_refs` is a real JSONB column plumbed end to end, and **all five of its call sites
pass `json!([])`** (`epoch_commit.rs:243`, `spine.rs:308`, `spine.rs:396`, `ceilings.rs:346`,
`ceilings.rs:414`); nothing reads it back. `IslandMessage.causality` looks alive, but `Island::step()`
returns `StepStatus` and nothing else — **applying an input cannot emit a message.**

**② No deployed process reads or writes the `events` table today.** Of 48 compose services, every service
touching the event store is absent; the one deployed Rust game service has zero references to events.
⇒ **every wire-format and storage decision in this round is still free.** It will not be free later, and
that is the single most important scheduling fact available.

**③ Three independent orderings of causality exist, and none is mapped to the others.**
`_boundaries/03_validator_pipeline_slots.md:25-109` — a **10-stage validator pipeline**.
`33_trigger_group_order.md:60-70` — an **8-group resolution law**, SEALED 2026-07-28, with six named
swap-bugs. `2026-08-02-actor-dataflow.md` §2.7 — a **V0..V6 ladder over time**. All three claim to order
the same thing. The event corpus references none of the other two.

**④ The corpus has said four times, independently, that the verb layer is the missing half.**
`31_world_simulation_architecture.md:48` — *"**WSA-F1 — the ontology does not supply WHEN.** … Without
it, nothing can happen except when a player acts."* Four blind role-played authors reached the same
place: *"What is missing, entirely, is the VERB layer. Nothing an author declares can HAPPEN"*
(`2026-08-02-actor-dataflow.md:5782`).

**The concrete failure this produces.** Six features subscribe to a death event whose owning feature
states it emits none — *"WA_006 emits no runtime events"* (`WA_006:75`). That is not a bug in six
features. It is six features correctly assuming a layer that was designed in three places and built in
none.

---

## 2. `Q-A` — what IS an event

### 2.1 The word covers six objects, and every surveyed failure is two of them sharing one representation

The prior-art sweep found the same split in every system examined, reached independently by each. Stated
with the test that separates each pair:

| # | object | the test that identifies it | our name for it |
|---|---|---|---|
| **①** | **Intent** — a request that may be refused | *"Can the receiver say no?"* If yes, it is an intent. | a **submission** |
| **②** | **Pending occurrence** — a durable row carrying a fire-time and a retry window | *"Does it exist before it happens?"* RimWorld `QueuedIncident{FireTick, TriedToFire, RetryDurationTicks}`; Paradox `trigger_event{days=N}` | a **beat** |
| **③** | **In-tick signal** — transient, pooled, depth-bounded | *"Does it survive the tick?"* Bevy `Events<T>` (2-frame TTL), Caves of Qud `MinEvent`+`CascadeLevel` | a **signal** |
| **④** | **Fact** — an immutable record of a transition already decided and accepted | *"Replayed in ten years against different code, does it produce the same transition?"* | a **fact** |
| **⑤** | **Chronicle record** — a fact a later *decision or narration* reads back | *"Does a future reader query this by subject rather than fold it by stream?"* DF `historical_event`, EVE killmail | a **chronicle entry** |
| **⑥** | **Notification** — that someone was told | *"Is it what happened, or that someone was told what happened?"* | not an event |

> **`EV-1`. Six objects, one word, and the word is the defect.** Every shipped failure the prior-art
> sweep could attribute traces to two of these sharing one representation. EVE's killmail rewrite was
> the discovery that they had stored **the rendering** instead of **the record**; fixing that dissolved
> truncation, lost mails and untranslatability at once.

⑤ is not a seventh storage tier — it is ④ *with a query obligation*. The distinction is load-bearing
because the reader is different: a fold reads a **stream in order**; a chronicle reads **by subject,
out of order, years later**. Our corpus already depends on this and does not name it: `ACT_001:342-343`
holds `recent_event_refs: Vec<EventId>` so an LLM can reference the past; `EF_001:182` keeps a frozen
location for *"where did Lý Minh die?"*.

### 2.2 The structural finding: our taxonomy classifies by ORIGIN, and a world occurrence is a SUBJECT

`EVT-T*` discriminates on **where a message came from** — Submitted · Derived · System · Generated ·
Proposal · Administrative. That is a producer-side property. A siege, a festival, a tribulation is a
**subject-side** concept. So:

> **`EV-2`. A game-world occurrence has no home in `EVT-T*`, and this is structural, not an omission.**
> Trace a siege: the scheduler fires `EVT-T5 Generated / Scheduled:WorldTick`; a wall falls as `EVT-T3
> Derived` on `aggregate_type=place`; an NPC dies as `EVT-T3` on `actor_status`; a PC's action inside it
> is `EVT-T1 Submitted`. **The siege itself is nowhere** — not a category, not a sub-type, not an
> aggregate. It is a word for *a set of causally related events across four categories*, and the corpus
> has no noun for that set. `EVT-T11_withdrawn` retired "WorldTick" **for being the same mechanism as
> NPCRoutine** — mechanically correct on that axis, and exactly the move that erased the occurrence.

Apply `D-98`'s discriminator (*a closed set is mechanism if the engine's arithmetic differs per member;
it is a feature's vocabulary in costume if the engine treats members uniformly*).

> ⚠️ **CORRECTED 2026-08-02 after red team `RT-7`. The first draft of this paragraph mis-read its own key
> evidence**, and the mistake mattered: it said the per-category validator subset *"was removed as a
> security defect"*. **It was not.** `services/commit-service/src/admission.rs:139-186`
> `Category::stage_verdicts()` **ships and genuinely differs per category** — T6 gets ten stages all
> applicable; T1 gets eleven with `a5-intent` / `a6-sanitize` / `a6-output` / `canon-drift` inapplicable
> plus `free-text-sanitisation`. What `PID-D5` removed is the **wire field**: a message's ability to
> *declare* its own category and so elect its own trust tier. **The selection survives; the
> self-declaration does not.** A reader who believed the wrong version and "simplified" by merging the
> categories would re-open `PID-D5`, which is why this is corrected in place rather than quietly fixed.

So the arithmetic **does** differ per member, and `EVT-T*` is therefore **genuine, load-bearing
mechanism** by `D-98`'s test. The question that remains is *mechanism for what* — and the answer is
**which validator subset a message must pass**, which is **trust**.

> **`EVT-T*` is a producer-TRUST taxonomy, correctly built, wearing an event ontology's name.** That is
> why it can be real mechanism and still supply no ontology of *what happened*: it was never answering
> that question. (The commit-primitive half of the original argument is separately true and separately
> useless — `advance_turn` 0, `t3_write` 0, `t2_write` one comment — but it is not what decides this.)

There is also **no duration**. `fiction_ts_start` + `fiction_duration` is a field on an instantaneous
message, not a span. A three-day siege is not expressible as one thing.

### 2.3 The category is a property of the PRODUCER, and we learned that from a security hole

`02_invariants.md:29` specifies that the wire format carries a `category` the SDK validates against the
`EVT-T*` allowlist. [`services/commit-service/src/admission.rs:47`](../../services/commit-service/src/admission.rs#L47)
records the opposite, and why: `event_category` is **deliberately absent**, because it *used to ride the
wire and select the validator subset, so a proposal could elect its own trust tier* — an LLM-originated
message writing `"T1"` skipped the entire LLM-safety stage set. Trust is now derived from an
HMAC-verified producer identity.

> **`EV-3`. Trust is derived from the producer; it is never carried by the message.** The shipped
> correction is right and the specification still says the opposite. This is `Q-A`'s sharpest single
> answer: **at least one thing everyone calls "the event's kind" is not a property of the event at all.**

### 2.4 The answer, stated

> **`EV-4`. An event is a FACT: an immutable record of a transition that has already been decided and
> accepted, whose payload is sufficient to reproduce that transition under a pinned ruleset.**
> Everything else that shares the word is a different object with a different lifetime: an **intent** is
> refusable and is not a fact · a **beat** is a scheduled *intention* and is not yet a fact · a
> **signal** is intra-tick and never leaves the tick · a **chronicle entry** is a fact plus a query
> obligation · a **notification** is a reactor output and is not a record of the world.

And the two classifications are separate and must stay separate:

| classification | axis | who owns it | status |
|---|---|---|---|
| **trust class** | who produced it | **engine** — derived from verified producer identity | ✅ shipped correctly (`admission.rs`), specified wrongly |
| **subject identity** | what in the world it is about | **the declaring feature's vocabulary** | ❌ does not exist — this is `EV-2`'s hole |

**Fusing them is what erased the siege.** `EVT-T*` is the trust classification and should be renamed to
say so; the subject identity is a separate, open design question (§9, `PO-E2`).

---

## 3. `Q-B` — what we store

### 3.1 The rule, not the list

> **`EV-5`. The fold must be CLOSED. An event's payload is exactly the decision inputs and outputs that
> are NOT re-derivable from (pinned ruleset ∪ prior events).**

Fowler states the failure directly: *"If I ask for an exchange rate on December 5th and replay that event
on December 20th, I will need the exchange rate on Dec 5 not the later one."* ⇒ **dice rolls, clock
reads, LLM outputs and cross-aggregate reads at decision time must be IN the event.** Everything
computable from the pinned rules plus earlier events must **not** be.

This is a rule rather than a list, which is why it is usable by features nobody has designed yet — and
it beats every granularity heuristic in the literature, where there is no consensus.

### 3.2 The four storage classes, taken from the features' own words

The demand census read ~244 demands across ~30 feature documents. **The demand is overwhelmingly for
MEMORY, not for delivery** — and, sharply, several features go out of their way to say a thing must
**not** be recorded. A design that treats "event" as "anything that changes" over-records exactly where
those features bought their cheapness.

| class | rule | attested by |
|---|---|---|
| **DURABLE** | it is a fact, and its absence changes a later fold, audit or narration | *"channel event stream **IS** the audit log (no separate `faction_event_log`)"* `FAC_001:78`, `FF_001:10` · *"`first_kill_only` is a fact about what has already happened, and **no amount of arithmetic recovers it**"* `COMB_004:238` · on death, memory is **frozen, not deleted** `WA_006:5` |
| **EPHEMERAL + CHECKPOINTED** | recoverable by replay, not in the canonical log | *"In-memory + per-round checkpoint (replay-recoverable) … not in the canonical event log beyond the lifecycle + round deltas"* `COMB_001:130-134` |
| **DERIVED — never stored as truth** | a pure function of (rules ∪ events) | DF7 *"introduces no new aggregate … **It is a law, not a store**"* `DF07_001:264` · known abilities derived live, *"nothing stored, nothing to clean up"* `ABL_001:435` |
| **DELIBERATELY UNRECORDED** | recording it would create drift where a pure function was cheaper | *"**A respawn is not an event**; it is the passage of fiction time changing the answer to a pure function. Nothing is written, nothing is scheduled, nothing can drift."* `COMB_005:151` · an expired pending edit's audit entry is *"NOT logged"* `WA_003:732` · rejected authoring drafts evaporate, **but their cost is durable** — *the money is remembered; the reasoning is not* `GEO_001b:56` |

> **`EV-6`. The fourth class is the one a naive design loses, and it is the one the features defend most
> explicitly.** *"Nothing is written, nothing is scheduled, nothing can drift"* is an argument that
> **not recording is a correctness property**, not a saving.

### 3.3 Two corollaries that decide real cases

> **`EV-7`. A threshold crossing is NOT an event and is never stored. Store the quantity; derive the
> band.** RimWorld persists hediff *severity* and derives the stage; threat points are computed on demand
> and appear nowhere in `Storyteller.ExposeData()`. GAS stores `BaseValue`, derives `CurrentValue`.
> **A stored threshold is a cache with no invalidation story.** This is also why
> `2026-08-02-actor-dataflow.md` §4.6.2 rules that *a threshold is not a subscription point*.

> **`EV-21`. The band is derived. The crossing is not an event. But a CONSEQUENCE that may be taken at
> most once produces a fact — and the fact is THE CONSEQUENCE, not the crossing.**
>
> This resolves what looked like a contradiction between `EV-7` and `COMB_004:238` (*"`first_kill_only`
> is a fact about what has already happened, and no amount of arithmetic recovers it"*). Three objects
> were sharing one word:
>
> | object | verdict | why |
> |---|---|---|
> | **band membership** — *is hp below 30% right now* | **DERIVED, never stored** | a pure function of the quantity and the declared band |
> | **the crossing** — *the edge, `prev != now`* | **not an event** | it is `threshold_active`'s edge state, intra-tick, and it emits a **proposal**, never an application (§4, `EV-9`) |
> | **the latch** — *this consequence has already been taken* | **DURABLE FACT** | it is a transition already decided and accepted, which is `EV-4`'s definition of a fact |
>
> `first_kill_only` and `COMB_005:101`'s cleared-camp bit are **latches on a consequence**, not stored
> thresholds. Both features arrived at one independently, and the second names why it was unavoidable:
> *"because the seed is deterministic, a naive re-roll would produce the same items again, i.e. **silent
> duplication that no diff would catch**"* (`COMB_004:300`).
>
> **And the latch satisfies `EV-5` rather than escaping it.** *"Did this ever cross"* looks re-derivable
> by folding the quantity's history — and it is not, because **the quantity's trajectory is not fully in
> the log**: regen and decay are closed-form per tick delta, and `D-49`'s phase 0 recomputes the whole
> block with *nothing durable written*. A crossing that happened between two commits leaves no trace to
> fold. So the latch is exactly `EV-5`'s *"not re-derivable from (pinned ruleset ∪ prior events)"* — it
> must be in the log, and for the general reason rather than as a threshold exception.

> **`EV-8`. A refusal WITH in-world consequences is a fact. A malformed or unauthorised request is not.
> These are two different refusals and our corpus does not currently separate them.** UK GOV Publishing
> API ADR-002 is the one documented architectural decision naming the cost of getting it wrong: rejected
> events put *"information that has no bearing on the behaviour of the system"* in the log, and *"an
> attempt to replay an event history containing rejected events would encounter errors."* The price of
> the correct side is **synchronous validation**. ⚠ We currently have both policies at once — `EVT-V4`
> commits a rejected turn as a canonical event, `TRG-L2` requires a discarded trigger to be a recorded
> event *(and it must not be silent)*, while `PL_006:252` makes `status.dispel_not_present` a silent
> no-op. `EV-8` is the line that resolves them: `SpellFizzled` and `Outcome::Discarded{reason}` are
> **facts with consequences**; a schema-invalid submission is **not a fact about the world**.

### 3.4 What is stored ALONGSIDE the fact

| | verdict | why |
|---|---|---|
| `message_id` · `correlation_id` · `causation_id` | **durable, on the event** | `correlation_id` answers *"what all happened because of this trigger"*; `causation_id` answers *"what directly caused THIS"*. **With only `correlation_id` you get the set but not its shape** — you cannot tell a 3-deep chain from 3 parallel siblings, which is exactly what diagnosing a runaway cascade requires. |
| projection checkpoint / processor position | **durable, but OUTSIDE the log** | a cursor, not a domain fact |
| process-manager state | **durable, ideally its own stream** | *"have I already sent it?"* cannot be re-derived from the aggregate's events |
| idempotency / dedup record | **durable, bounded TTL, outside the log** | |
| snapshot | **cache, never a source** | already our `D-20`/`P-F` |
| field-level diffs (`EntityUpdated`, `XChanged`) | **never** | property sourcing: *"many tiny, copy/pasted, meaningless events"* |

---

## 4. `Q-C` — eleven causality shapes, and two of them are not shapes

The census attests **eleven**, not the eight this round guessed — and corrects two of the guesses.

| # | shape | what makes it distinct |
|---|---|---|
| 1 | **Threshold** | hysteresis, exactly-once firing, and it emits a **proposal**, not an application |
| 2 | **Status** | stack policy, magnitude, source, expiry form, and a **veto point** |
| 3 | **Lifecycle** | a declared machine, an atomic cascade, an append-only reason log |
| 4 | **Scheduled** | coordinator order, day-boundary dedup, batch catch-up, determinism |
| 5 | **Interaction** | the 4-role payload, proposed-vs-actual split |
| 6 | **Ambient / world** | needs a holder for conservation — a locus-actor or a field model |
| 7 | **Narrative / generated** | propose→validate→commit gate, seeded probability, rate caps, cycle detection |
| 8 | **Derived / reactive** | epoch invalidation; **must not be stored as truth**; resolves last |
| **9** | **OBSERVATION** ⭐ | *the act of looking is itself the causal event* — it commits a clock advance, materialises accrued state, and fabricates history. Closed observer set, plus a law forbidding it from changing outcomes (`34_when_the_world_runs.md:213-218`, `:272-302`) |
| **10** | **EXISTENCE-TIER TRANSITION** ⭐ | movement into and out of *being modelled at all*, which must **backfill a history the entity never had** (`AIT_001:404-473`) |
| **11** | **ADMIN / AUTHORING** ⭐ | multi-approver, TTL'd intentions, non-atomic audit, may **mutate the declarative manifest itself**, and an expired one is deliberately unrecorded (`WA_003:304-312`) |

> **`EV-9`. Shapes 1→2→3 are a fixed PIPELINE, not three peers.** `TransitionDecl.trigger` is
> `OnStatus(StatusOrdinal)`, so a threshold proposes a status and only a status can move a lifecycle.
> **Any design that lets a threshold fire a lifecycle transition directly is building a second,
> undeclared path.**
>
> **`EV-10`. Shape 8 sits UNDERNEATH the others.** Derived/reactive is not a kind of event; it is what
> must happen after every other kind, exactly once, in the last group — `G8 DERIVE`. Treating it as a
> peer invites the double-counting class that DF07, COMB and PL_007 each guard against separately.

**`EV-11`. Shape 9 is the one a design that starts from *"an actor did something"* will miss**, and it
interacts directly with `I-5` (*canon is what is written to the ledger*): **if looking is what writes,
then what is canon depends on who looked.** The corpus already carries the test that keeps this honest —
*"Run a scenario twice with different observation schedules. Assert: identical final state, and identical
`occurred_at` on every event — only `recorded_at` and log order may differ. **This is the sharpest single
test in the world tier**"* (`34_when_the_world_runs.md:296`).

**Eight orthogonal AXES cut across all eleven** and each is separately load-bearing: `occurred_at` ≠
`recorded_at` · canonical vs flavour · **aspect scope** (body / soul / held-by-others) · four timing
classes · four storage classes (§3.2) · partiality of invalidation · **insertion point** · **lineage**.

⇒ **`EV-12`. The answer to `Q-A` is `shape × axes`, not a flat category enum.** That is the structural
reason the `EVT-T*` closed set keeps producing counterexamples — including the one it cannot survive:
**`StatusProposed`, the load-bearing event of the whole propose/adjudicate/apply design, is classifiable
by none of the six active categories.** Not Submitted (no actor intent) · not Derived (not a committed
delta) · not Generated (no probability) · not System (not DP) · not Proposal (not untrusted-origin) · not
Administrative.

---

## 5. `Q-D` — how a chain is bounded

### 5.1 The strongest available answer is already sealed, and the event corpus has never cited it

[`33_trigger_group_order.md`](../03_planning/LLM_MMO_RPG/33_trigger_group_order.md) — SEALED 2026-07-28,
`TRG-A1..A18`. It supplies, and this round adopts:

- **Eight ordered groups**: `G1 ADMIT → G2 AUTHORISE → G3 REPLACE → G4 APPLY → G5 LIFECYCLE → G6 REACT →
  G7 IMPRINT → G8 DERIVE`, with **six adjacent-swap tests each naming the concrete defect the swap
  produces** — an acceptance suite, not an illustration. Swap `G5 ↔ G6` and a *"when I die"* reaction
  cannot fire while a body-scoped reaction fires from a corpse whose body is already gone.
- **`TRG-A8` — reactions resolve in WAVES**, because full recursion would make reactions order-dependent
  and break within-group commutativity by design.
- **`TRG-A10` — G3 REWRITES, G6 SPAWNS, and neither may do the other.** This is what makes termination
  *provable* rather than *budgeted*: a replacement applies at most once per event so its set strictly
  shrinks; a reaction decrements a wave budget. **If either could do the other's job they would recurse
  into each other**, which is precisely the source of Magic: The Gathering's hardest rules cases.
- **`TRG-A14` — a reaction kind fires at most once per originating chain** ⇒ max depth =
  `|reaction_kinds|`, deterministically, with no dice and no budget.
- **`TRG-A18` — a chain commits ONCE**, because the real constraint is write amplification (~170
  commits/s single-writer ceiling), not compute (an island step is 176–229 ns).
- **`TRG-L5` — `attributed_to` is stamped at commit and never re-derived**, or a property transfer
  silently rewrites history.

### 5.2 What `33` is missing, from the prior art

> 🔴 **`EV-13` — HALF REFUTED (`RT-3`), marked here rather than only in the banner.** The diagnosis is
> right; the claim that **we already have the second bound is false**. `EVT-L9:77` states its own intent:
> the idempotency key *"lets the same `beat_id` fire at multiple fiction-times"* — it bounds
> **duplication, not quantity**. `EVT-L8:49-53` carries **no chain identity**, and a mutation creates a
> **new** `beat_id`. `EVT-L11:106` — **V1: the scheduler is not deployed.** Worst: **chain identity
> RESETS**, because a beat enters as an external message → `G1` → a new chain (`TRG-A9`), so
> **`TRG-A14`'s fired-kind set empties every tick.** Scenario: a curse schedules a beat whose payload
> re-satisfies its own `WHEN`; every intra-chain bound stays green forever while beats double daily.
> ⇒ **we have ONE bound, not two**, and `EV-14′` (§9.4.1) is what gives the missing one a home to be
> built in.

> **`EV-13`. A chain needs TWO INDEPENDENT bounds, because chains fail in two ways.** All three of
> `TRG`'s termination layers are **intra-chain**. A depth budget does nothing about a consequence
> **scheduled for next Tuesday**; a durable queue does nothing about a **synchronous self-refire**. Every
> surveyed system that got this right has both: Bevy's 2-frame TTL *and* nothing; RimWorld's
> `IncidentQueue` retry-window+expiry *and* nothing; Paradox's 1000-iteration `while` cap *and*
> `days=`/`fire_only_once`. Ours are `TRG-A14` (intra) and `EVT-L7..L11` scheduled beats (cross-tick),
> **and no document states that they are one problem with two bounds.**

### 5.3 The reaction seam itself — and the two independent arrivals that decide it

> **`EV-14`. An event must never directly cause an event. Every reaction routes
> `event → view → command → decider → event`.** This is the only surveyed approach that bounds cascades
> **by construction**, because the sole producer of events remains the decider — every link passes a
> point that can refuse. Projections are documented as **forbidden** from emitting.

This agrees exactly with `I-8` (`D-27` — *a contribution is DATA, never CODE; the engine never calls a
feature*) reached from an entirely different direction. **Two independent arrivals at one shape is the
strongest evidence available for it**, and it is the answer to the seam `D-9` left open.

Its cost, stated rather than hidden: **an extra derived artifact per automation**, and a reaction that is
not part of the fold — so a rebuild will not re-derive *"the reaction happened"* unless the reactor emits
a **fact** which is in the fold, guarded by a checkpoint rather than by the fold.

### 5.4 The three orderings, reconciled

They are not three answers to one question. They are three different questions that were each given the
word "order":

| | what it actually orders | scope |
|---|---|---|
| `_boundaries/03` — 10-stage validator pipeline | **admission of one candidate message** | one message, at the trust boundary |
| `33_trigger_group_order.md` — 8 groups | **resolution of one transaction and its wave** | one turn, inside the loop |
| `actor-dataflow` §2.7 — V0..V6 ladder | **which layer in TIME a check belongs to** | the whole system's lifetime |

> ## `EV-15′` — the reconciliation, and the three are not rivals: they own three different things
>
> **`EV-15` was false three ways** — stage 9 is `G4`+`G5` · **~75 % of the pipeline's rules are `V1
> RESOLVE`, not `V3`** · and *a plan is not an element of an algebra*. What replaces it:
>
> | artifact | owns | why it and not the others |
> |---|---|---|
> | **`33_trigger_group_order.md`** | **THE ORDER** | it is the **only falsifiable** one — six adjacent-swap tests, each naming the concrete bug the swap produces |
> | **`actor-dataflow` §2.7** | **THE LAYER** | it is the **only one that can classify the ~120 canonical-seed bootstrap rules**, which are `V1 · Resolve` and were being carried as if they were admission checks |
> | **`_boundaries/03`** | **THE REGISTRY** | it holds the rows. It should **stop asserting a sequence and DERIVE one**, by sorting on `(trg_group, ladder_layer, intra-group key)` |
>
> ⇒ **The pipeline is not a fourth ordering. It is a REGISTRY whose order is a projection of the other
> two.** That is what dissolves the three-month circular SSOT deadlock (`E-23`) — neither prose file
> needs to win, because the sequence stops being authored. Per `D-40` the mechanism is a **machine
> contract**: `contracts/validator-stages.yaml` generating `admission.rs:151-184`, with four gates that
> **each red today** (an unmapped `ability.*`; non-decreasing group; operand topology; obligations).
> ⚠ A **fourth** ordering exists at `05_validator_pipeline.md:166`.
>
> ### The order IS wrong — but at 7↔9, not at 6, and the corpus already filed it
>
> **`REC-31`** (`19_reconciliation_register.md:198-204`, type LOCK, register status **OPEN**):
> *"Canon-drift can only compare narration against a `ResolutionResult` if the derivation stage already
> ran — true in `PL_005b`'s order, false in the locked one."* That is a **`G4`→`G8` inversion**, which is
> structurally `TRG-L1:94`'s stale-standing bug. The symptom is reported **four times**: `REC-31`
> (`ABL_001 §8.3` and `AC-COMB-10` unsatisfiable) · `REC-33` (`language.*` rejects firing in
> `canon_drift.*`'s slot — fixed in `IDF_002` only, still live in five files) · `REC-32` · and
> `PL_005c:321` — *"T2 (HpDelta) committed; T3 (MortalityTransition) failed → dead-letter … state
> inconsistency window"*, i.e. **damage applied, death not**.
>
> **That last one is the closest thing in the corpus to *"nobody ever dies from a hit"* — and its cause
> is not stage order. It is the ABSENCE OF `TRG-A18`** (a chain commits once). Which is the same finding
> as `EV-14′`, arriving from the pipeline side.
>
> ### The real defect is the POST-COMMIT TABLE
>
> Nine rows spanning **five groups** (`G4·G5·G6·G7·G8`) **with no order axis at all**. `:135`'s
> `PlaceDestroyed` cascade **mutates AND spawns consumer reactions in one unordered bucket** — exactly
> the `G3`/`G6` conflation `TRG-A10` forbids, and the conflation that makes termination unprovable.
> Two structural conflicts fall out: `05_validator_pipeline.md:121,125,133,167` makes **every side-effect
> its own event, running schema + capability and committing separately** — violating **`TRG-A9`** (a
> nested pass never re-enters `G1`) **and `TRG-A18`** (a chain commits once).
>
> ### Why this is cheap right now
>
> **`admission.rs:315-317` records `NotRun` for all ten stages.** The pipeline is **latent, not live** —
> so this is fixable **before the affected code exists**, which is the same window `AS-1` describes and
> the same reason `EV-17′` is urgent.
>
> ⚠️ **CORRECTION TO MY OWN RULING.** I accepted `RT-2` *"in full"*; **three of its six claims
> over-reach**, and accepting a red-team finding without verifying it is the mirror of the error that
> produced the FATALs. **(1)** Stage 5 **mutates nothing** — `WA_002:382-388` *queues* both deltas
> post-commit ⇒ `G2` decision + `G4` queued delta, and the spawn is **V2+ only**. **(2)** Canon-drift is
> **not `G8`** — `22:63` lists it *Outside*, i.e. `G1`-class; what is true is that its **operand** is a
> `G4`/`G8` artifact and its knowledge-service read is missing from `PL_005c:340-342`'s determinism
> inputs, so **`V6` is unprovable there**. **(3)** The stage-6 death detector is a **GHOST**:
> `WA_006:10,29,58` hands it to `05_llm_safety`, **which has no such file**, and `PL_005c:205` implements
> death at the **world-rule** stage instead. ⇒ **`G5`-before-`G4` does not hold**; the transition is
> already post-commit.

<details><summary>Superseded — the original <code>EV-15</code> and its refutation, kept because §7's rot discipline records reversals rather than deleting them</summary>

> 🔴 **`EV-15` — REFUTED STAGE BY STAGE (`RT-2`), and NOT YET REPLACED. Do not build on this section.**
> Checked against `_boundaries/03:25-109`: **stage 5** is budget tracking + cascade-on-exceed — a mutation
> **plus a spawn** ⇒ `G4`+`G6` · **stage 6** hosts the `WA_006` mortality death-detection sub-validator
> ⇒ **`G5`** · **stage 7** canon-drift reads knowledge-service ⇒ a `G8` artifact, cross-service, inside a
> path that must replay byte-identically · and **`:108` is literally `[commit] dp::advance_turn OR
> dp::t2_write`** ⇒ `G4`, inside the range cited below. `IAS-A2.2` (`22_…:70-74`) names 3.5.a/3.5.b/3.5.e
> and `world-rule` **by number** as reading loop-mutated state, so they cannot be `G1` either. The ladder
> half is wrong too: `_boundaries/03:247,253` — **~120 of ~161 rules are canonical-seed bootstrap
> validators**, i.e. `V1 · Resolve`, not `V3`.
>
> **Sharpest consequence, and it is bigger than my error:** death detection at stage 6 runs **before**
> `[commit]` — `G5` before `G4` — which is `TRG-L1`'s own named swap-bug, ***"nobody ever dies from a
> hit."*** That is a property of the **shipped pipeline**, not of my mapping.
>
> ⚠ **I replaced three orderings with a WRONG mapping, which is worse than three.** A reconciliation is
> in flight; until it lands **this section states a problem and not an answer**, and the paragraph below
> is retained only so the refutation has a subject.

> **`EV-15`. The validator pipeline is `G1 ADMIT` + `G2 AUTHORISE` expanded, and it is `V3 ADMISSION` on
> the ladder. It is one stage of one group of one layer.** Its current claim to order *"every event
> candidate"* is what makes it look like a rival to `33`. ⚠ **And it currently has no owner:**
> `05_validator_pipeline.md:199` calls `_boundaries/03` authoritative, while `_boundaries/03:5` says the
> authoritative source is *pending* the very phase that then locked without landing it. **A circular SSOT
> deadlock, three months old** — and the consequence is that the T1 validator chain is stated **four
> times in four different orders**.

</details>

---

## 6. `Q-E` — where the mechanism / vocabulary line falls

Applying `D-2` and `D-98`'s discriminator to each contested item:

| concern | verdict | why |
|---|---|---|
| **trust class** | **MECHANISM, and derived — never declared, never on the wire** | `EV-3`. Arithmetic genuinely differs per member (which validator subset runs), and letting it be carried was a security defect. |
| **subject identity** (what an occurrence IS about) | **VOCABULARY** | the engine treats subjects uniformly; only the declaring feature knows what `siege` means |
| **the eight resolution groups** | **MECHANISM, engine-owned, LOCKED** | `TRG-A2`: an author declares `WHEN·IF·THEN·ON`; the engine derives the group. Order is observable and swap-testable, so it is real. |
| **`replacement_priority` within G3** | **VOCABULARY** | prevention effects genuinely do not commute; the priority is a balance decision |
| **wave budget value** | **VOCABULARY** (a declared ruleset constant) | two realities may legitimately differ |
| **`on_exceeded` behaviour** | **MECHANISM, engine-fixed `Refuse`** | `D-79`. A truncated wave is order-sensitive by construction (`TRG-A11`), so `Truncate` is not a legitimate choice. |
| **storage class of an event kind** | **MECHANISM — the four classes; VOCABULARY — the assignment** | the same shape as every other closed-policy/declared-assignment pair in this project |
| **`causation_id` / `correlation_id`** | **MECHANISM, always present** | they are how a cascade is diagnosable at all |
| **retention class per event type** | **VOCABULARY**, but the class set is **MECHANISM** | `contracts/retention/event_classes.yaml` already ships the classes; nothing maps to them |

---

## 7. Rot ledger — `07_event_model`, LOCKED 2026-04-25

**31 rows.** `U` = update · `D` = delete · `K` = keep-with-note. Full detail with quotations in
[`2026-08-02-event-causality-research/research-A3-event-model-rot-sweep.md`](2026-08-02-event-causality-research/research-A3-event-model-rot-sweep.md).

### 7.1 Contradicted by shipped code

| id | site | why it is false now | action |
|---|---|---|---|
| **E-1** | `02_invariants.md:29` | the wire `category` + SDK allowlist **was built and removed as a security defect** (`admission.rs:47`); the category is derived from a verified producer; `EvtCategory` has 0 occurrences | **U** |
| **E-2** | `06_per_category_contracts.md:27-42` | **8 of the 12 specified envelope fields do not exist**; the shipped envelope carries `ruleset_digest`, which the corpus never mentions; it is keyed on **aggregate**, not channel | **U** — the largest single divergence |
| **E-3** | `02_invariants.md:184` · `12_generation_framework.md:266` · `22_…:167` | `dp::deterministic_rng` — **0 occurrences**. Cited three times as *the* enforcement mechanism | **U** |
| **E-4** | `03_event_taxonomy.md:26-31,43,69` · `06_…:61,85,123` | **none of the four commit primitives exists** — `advance_turn` 0, `t3_write` 0, `t2_write` = one comment | **U** |
| **E-5** | `08_scheduled_events.md:30,35` · `10_…:45` · `12_…:85-89` | `subscribe_channel_events_durable` — **0 occurrences**; four of five `EVT-G2` trigger kinds rest on it | **U** |
| **E-6** | `09_causal_references.md:28-33,57-61` | the JSONB column exists; **`CausalRef` as a type has 0 occurrences and none of the four integrity checks exists** — the typed-over-opaque argument's whole payoff is the part that was dropped | **U** |
| **E-7** | `12_generation_framework.md:156,173,279-303` | the entire `EventModelError` taxonomy — `GeneratorRateLimited`, `GeneratorCycleDetected`, `generator_capacity_budgets`, `registry_uuid`, `cascade_depth` — **all 0** | **U** |
| **E-8** | `12_…:32,251-262` | the registry row exists, but there is **no "Generator-rows section"**, and **no registered generator carries the mandatory `registry_uuid` or `capacity_ceiling`** | **U** |
| **E-9** | `11_schema_versioning.md:27-34` | shipped versioning is **per-event-type** (`_registry.yaml` + `upcaster.rs:139`), not an envelope-wide counter | **U** |
| **E-10** | `03_event_taxonomy.md:97-108` | `_registry.yaml` registers **15 types and not one of the 8 DP-locked System sub-types appears** — `D-63` found the same gap from the actor side | **U** |
| **E-11** | `03_event_taxonomy.md:259-265` | `world.tick` is a **registered, shipped event type** under the name the corpus permanently retired | **K** — a name collision to resolve, not to silently re-retire |
| **E-12** | `02_invariants.md:210,236,270` · `12_…:71` | three named codegen/lint gates; the codegen that exists validates the Go registry and none of the three | **U** |

### 7.2 Contradicted or contested by the 2026-08-02 decisions

| id | site | why | action |
|---|---|---|---|
| **E-13** | `05_validator_pipeline.md:25-31` + `02_invariants.md:102` | one linear commit-time pipeline vs the **V0..V6 ladder over time**; under §2.7 most checks must **not** be commit-time. Two models, different axes, neither citing the other | **U** — `EVT-V*` is `V3 ADMISSION` only (§5.4) |
| **E-14** | `02_invariants.md:199-201` | *"every observable change has a committed event"* — but `D-49`'s phase 0 changes observable state with **nothing durable written**, by design | **U** — restate as *"every change to the two SSOTs"* |
| **E-15** | `02_invariants.md:69-96` | the 7 producer role classes are contested by `D-27` (the engine never enumerates features) and superseded in fact by **producer identity via MAC** | **U** |
| **E-16** | `03_event_taxonomy.md:75` | three of the 13 aggregate types are contested by name or ownership — `vital_pool` has **zero hits in code**, `npc_pc_relationship_projection` left actor core (`D-24`), `actor_status` became a projection (`D-25`) | **U** — it is a design register, not an inventory |
| **E-17** | `12_…:128-136` | **three uncoordinated cascade bounds** — cap 16 vs `TRG` groups vs wave depth 8 | **U** — one bound, one owner |
| **E-18** | `02_invariants.md:122-126` + `09_…:75-91` | required `Vec<CausalRef>` up to 64 per Generated event is the per-event-cost pattern `D-46` argues against — **not refuted, but the cost side was never weighed** | **K** — CONTESTED |
| **E-19** | `10_…:99` + `11_…:82-88` | replay determinism and indefinite upcaster retention both assume an intact log, while `archive-worker` **drops partitions at 90 days** and `archive-restore` restores into a table `load_aggregate` does not read | **U** — both must state the retention precondition |
| **E-20** | `08_…:27-43` + `12_…:87` | restate against `D-96`'s turn/tick separation and `D-19`'s two clocks | **U** |
| **E-21** | `12_…:186-215` | *"generators ALREADY run in-process"* is a present-tense claim about code that does not exist — the `D-57` shape | **U** — the deployment argument may survive; its evidence does not |
| **E-22** | `06_…:53` · `03_…:318` · `05_…:3` | four `EVT-*` rules delegate their SSOT to a hand-maintained matrix that has already been caught carrying false *"applied"* claims (`REC-97`, `D-40`) | **K** — sound delegation, unreliable delegate |

### 7.3 The corpus contradicting itself

| id | site | why | action |
|---|---|---|---|
| **E-23** | `05_…:3,199` **vs** `_boundaries/03:5` | **circular SSOT deadlock** — each names the other as authoritative. Three months old. **The sharpest internal rot in the corpus.** | **U** — one must claim it |
| **E-24** | four files | the T1 validator chain stated **four times in four different orders**; two stages in the SSOT appear in none of the three restatements | **U** — delete the restatements, cite the SSOT once |
| **E-25** | `02_invariants.md:32` | *"add EVT-T13 (next free)"* — **next free is T12**; under stable-ID discipline this permanently burns an id | **U** — one word |
| **E-26** | `_index.md:36` | reading order says `A1..A8`; the file has `A1..A12` and A8 was reframed | **U** |
| **E-27** | `01_scope_and_boundary.md:83` | sends the reader to `T1..T11`, five of which are withdrawn | **U** |
| **E-28** | `99_open_questions.md:12,34,44,66,90` | five open questions cite **dead anchors** from before the redesign the same file documents | **U** |
| **E-29** | `10_…:43` vs `:50` | specifies `localStorage` for `last_seen_channel_event_id` **and cites CLAUDE.md's no-localStorage rule six lines later** — it contradicts itself inside one section and misattributes the rule to justify the violation | **U** |
| **E-30** | `_index.md:5,71-72` | *"folder closed for design"* / *"all deferrals RESOLVED"* — closed on twelve unbuilt mechanisms and a circular SSOT | **U** — reopen, stating what was designed vs what was verified |
| **E-31** | `03_event_taxonomy.md:269-310` | the closed-set proof's input was four features and one spike from April; the domain has roughly tripled, and **`StatusProposed` is a live counterexample** (`EV-12`) | **K** — CONTESTED: stale, not false. Re-run or state its scope |

---

## 8. What survives, and must not be re-decided

Recorded because inheriting is cheaper than re-deriving, and because a rot ledger that names no survivors
is an argument for a rewrite nobody asked for.

- **`EVT-A10`** — the event log is the audit log; features must not build private ones. **Already
  implemented**: `load_aggregate` folds with a snapshot fast path, and
  `0004_aggregate_snapshots_table.up.sql` states *"snapshots are a write-path cache, **not the SSOT**"*.
  Six features depend on this clause explicitly.
- **`EVT-A8`** — non-canonical regenerable content is not an event. Independently reached by EVE's
  killmail rewrite (`EV-1`) and by `D-23`.
- **`EVT-A7`**, hardened in the shipping — untrusted-origin events need a pre-validation lifecycle, now
  anchored to producer-identity MAC rather than a self-declared field.
- **`EVT-L1..L6`** — the proposal bus is **genuinely shipped**; `bus.rs` implements it by name and
  `spine.rs:187` uses the exact per-cell topic. **`L2` is load-bearing**: a proposal is never promoted in
  place; a fresh event is committed.
- **`EVT-V2`** — five fail modes with `silent_drop` **forbidden**. **`EVT-V6`** — a consequence is its own
  event with a causal ref to its parent, never a field on its cause.
- **`EVT-L9`** — N threshold crossings ⇒ N firings, exactly once, in fiction-chronological order.
- **`EVT-L12..L15`** — the causal-ref integrity rules: single-reality, exists, **non-forward**, backward
  walks only, acyclic by construction.
- **`EVT-L18`** — two replay modes, and only the structural one is bit-deterministic. **`EVT-S3`** —
  upcasters are append-only and retained for the life of retention.
- **`EVT-G2`** — the 5-kind closed trigger taxonomy is **the only place in the corpus that enumerates
  what can cause an event**, and it survives as the input to `EV-14`'s command layer.
- **All of `TRG-A1..A18`** (§5.1), and `34_when_the_world_runs.md`'s observation law and its test.

---

## 9. The five residual questions, evaluated against what this layer must SERVE

The PO's direction, 2026-08-02: **do not escalate these as preferences — evaluate them against what the
layer must serve, now and in the future.** That is the right method, and it only works if the service
model and its assumptions are written down in a form that can be **falsified**. §9.1 does that; §9.2
evaluates each question against it; §9.3 records what would have to change to reverse each answer.

### 9.1 The service model, and the assumptions it rests on

**What it serves NOW — measured, and the number is close to zero.**

| | measured |
|---|---|
| deployed processes reading or writing `events` | **0** of 48 compose services (§1②) |
| code paths where event A causes event B | **0** (§1①) |
| production call sites for the read path | **0** (`load_aggregate`, `SnapshotCache`, `canon_cache`, `snapshot_write`) |
| live route from durable truth to a client | **1** — `ChannelRoom`, and it folds the wrong stream |
| realities in production | **0** (`D-11`) |

**What it must serve in the FUTURE — and this is where all the weight is.**

| consumer | status today | what it needs from this layer |
|---|---|---|
| the **eleven shapes** (§4) | 8 designed, 3 unnamed until this round | a home for each; shapes 6/7/9 currently have none |
| `13_quests` · `14_crafting` · `15_organization` | **reservation notes only** — and 13 already reserves live event hooks | occurrences, scheduled beats, chronicle queries |
| `07_social` · `08_narrative_canon` · `09_emergent` · `11_cross_cutting` | **index only** — *"No features designed yet"* | almost entirely occurrence- and memory-shaped |
| the **relational / AI + emotion feature** (`D-24`, parked `P-6`) | handed off, unbuilt | imprints, attribution, grudges that outlive the dead |
| the **166 blind author wishes** re-filed across nine features (`D-90`) | a requirements corpus | *"what happens when a number crosses a line"* — the verb layer, named as the missing half four times independently |
| **NPC memory** | designed, load-bearing on the log (`K19`) | chronicle reads **by subject, out of order, years later** |
| **replay / conformance** | the correctness gate, partially built | a closed fold and a self-describing record |

**The four assumptions this evaluation rests on. Each is stated so it can be shown false.**

> **`AS-1` — Reversal is cheap NOW and expensive later, and the crossover is the first pinned reality.**
> *Falsified by:* any reality being pinned, or any deployed service beginning to write `events`. This is
> the assumption doing the most work, and it is currently **measured true**, not assumed.
>
> **`AS-2` — The unbuilt features are the majority of the demand, and they are occurrence- and
> memory-shaped rather than delivery-shaped.** ~244 demands were read; the great majority carry an
> explicit durability requirement in the feature's own words, and seven feature folders that are empty
> today are the ones whose whole subject is *what happened*. *Falsified by:* the stub folders landing
> with designs that need only notification.
>
> **`AS-3` — A per-event field cannot be backfilled; a derived index can be rebuilt.** If a fact is not
> written at the moment it happens, `D-23` says it did not happen. *Falsified by:* a demonstrated
> reconstruction path for the specific field in question.
>
> **`AS-4` — What the platform ALREADY DOES outranks what a document says it should do**, because the
> code is the thing that will be running when the first reality is pinned. *Falsified by:* the shipped
> behaviour being scheduled for removal on independent grounds.

### 9.2 The evaluations

#### `PO-E1` — the refusal line: **it falls at the DECIDER, and the corpus already drew it under another name**

*Served now:* one real consumer — `PL_001b:292-303`, an operator's raw SQL scan of `channel_events`
filtered on `outcome = 'Rejected'`. *Served later:* `TRG-L2`'s *"when my reflect is prevented, gain
rage"*, which requires discards to be in the reaction surface; NPC memory, which reads the log.

The framing *"rejected vs accepted"* is what makes this look hard. The service model reframes it: **the
question is whether a decider ran.**

> **`EV-16`. A refusal adjudicated by a decider is a FACT. A refusal that happened before any decider is
> an OPERATIONAL record and does not belong in the event log.** And this is exactly `TRG`'s existing
> boundary: **`G1 ADMIT` is the trust boundary** — pure-message checks, producer identity, dedup, rate
> limiting, outside the loop — and `TRG-A9` already states that a nested pass runs `G2..G8` and **never
> `G1`**, because running it would mean *the engine rate-limiting its own emissions*. So: **a refusal in
> `G1` is transport; a refusal in `G2..G8` is history.** *"You cannot afford the stamina"* is `G2`, and
> it is unambiguously in-world.

This dissolves the conflict rather than choosing a side. `EVT-V4` (a rejected turn commits with
`outcome=Rejected` and the clock does **not** advance) is **compatible**, and the reason is precisely
ADR-002's reason: folding it is a **no-op**, so it cannot make a replay error. `PL_006:252`'s silent
no-op is the one that must change — it is a `G2`-or-later refusal being dropped, which `TRG-L2` already
forbids.

The price stands: **validation before `G1` must be synchronous.** That is affordable specifically because
`G1` is pure-message checking with no domain reads.

#### `PO-E2` — the world occurrence: **yes, a first-class reference, and it is the one thing that cannot wait**

*Served now:* nothing. *Served later:* three of the eleven shapes have no home without it, and **four of
the seven empty feature folders are about nothing else.**

Two candidate cheap answers fail on inspection:

- **`correlation_id` cannot express it.** Correlation groups *everything that followed from one
  originating trigger*. A three-day siege spans many turns, many actors, many originating triggers.
  Correlation is a **causal** grouping; an occurrence is a **subject** grouping. They are different
  partitions of the same events.
- **`aggregate_id` cannot express it either**, and the reason is structural: single-writer-per-aggregate
  means an event has exactly **one** aggregate. A siege event is *also* about a place, an actor, a
  faction. **The occurrence is a SECOND reference axis, orthogonal to the aggregate** — which is why it
  reads as missing rather than as duplicated.

> **`EV-17`. An event carries an optional `occurrence_id` — a second, subject-side reference axis
> orthogonal to `aggregate_id` — and the occurrence itself is opened and closed by ordinary facts.**
> The occurrence's *kind* (`siege`, `festival`, `tribulation`) is **declared vocabulary** (`Q-E`); the
> engine never learns those words. It gives §2.2's missing noun, §2.1's ⑤ chronicle its query key, and
> §4's shape 6 its holder — one field, not a taxonomy.

**`AS-3` is what makes this urgent rather than merely desirable.** *"Which events belonged to the
siege"* is not recoverable after the fact by any heuristic worth trusting, and under `D-23` an
unwritten fact did not happen. So this is a **reversal**, in `D-84`'s sense: cheap now, impossible once
content exists. Every other answer in this section can be deferred; this one cannot.

#### `PO-E3` — truncation: **the STORAGE CLASS decides it, not the snapshot — and that mapping is the gap we already found**

*Served now:* `archive-worker` is **deployed and drops partitions at 90 days.** *Served later:* canon
must fold forever; volatile NPC chatter must not.

The apparent contradiction — `D-61` says snapshot-before-drop, prior art says a snapshot cannot license
truncation — assumes **every event must fold forever**. The platform already denies that:
`contracts/retention/event_classes.yaml` **ships** with `canon_events` (never deleted) and
`volatile_npc` (30 hot / 60 warm / archive).

> ## ⚠️ `EV-18` REVISED 2026-08-02 after red team `RT-17`, then **re-measured** — and the measurement is
> sharper than the review.
>
> The first form said *"a partition may be dropped iff every event in it is volatile-class, or a
> `PeriodClosed` carry-forward FACT preserves what the fold needs."* **Two of its three parts do not
> survive contact with the deployed system**, and the third is better than it looked.
>
> **① The class does not COVER, and the uncovered ones are exactly the canon.** Measured directly:
> `contracts/events/_registry.yaml` registers **15** event types; `contracts/retention/event_classes.yaml`
> maps **5**; **the intersection is 3** (`npc.said`, `xreality.canon.promoted`, `xreality.user.erased`).
> Two mapped names are **phantoms** — `npc.moved` is unregistered, and `canon.promoted` is a misspelling
> of the registered `canon.entry.promoted`. ⇒ **12 of 15 registered types have no retention class, and
> they include all four `canon.entry.*` and all four `admin.canon.override.*`** — precisely the events
> the `canon_events` class exists to protect.
>
> **② `PeriodClosed` has no possible writer, and the escape hatch eats itself.** Both production
> `INSERT INTO events` paths are **Rust** (`crates/dp-kernel/src/channel.rs:164`,
> `event_store_pg.rs:251`) and the channel append requires the writer-lease CAS; **`archive-worker` is
> Go**. And a `PeriodClosed` written today lands in **today's** partition and is dropped 90 days later.
> **Withdrawn.** A carry-forward fact is only coherent if it lives outside the partition scheme it is
> protecting — which makes it a different artifact, not an event.
>
> **③ The class MECHANISM is right, and the gap is TRACKED — this is buildable work, not a blocker.**
> `event_classes.yaml` says of itself: *"Cycle 11 ships this as a CONTRACT SKELETON. The full classifier
> (L2.K.3) that maps `event_type` → retention_class lands incrementally… V1 retention-worker reads this
> file at startup to validate config-shape; it does **NOT yet branch policy by class**."* The coupling
> lint is **explicitly deferred as `D-EVENT-CLASS-LINT`**. Per CLAUDE.md's anti-laziness rule this is
> *missing infrastructure that we could write*, not an external dependency.
>
> ### The re-grounded rule
>
> > **`EV-18′`. A partition may be dropped only if EVERY event type occurring in it has an explicit
> > retention class, and none of those classes is `canon: true`. COVERAGE is the precondition — not
> > class membership, because an unmapped type is currently indistinguishable from a volatile one.**
> > Today `partition_picker.go:99-128` filters on **age alone**, so the invariant is unenforced in the
> > direction that loses canon. The work item is `D-EVENT-CLASS-LINT`, and it is one table plus one gate:
> > **a registered event type with no retention class must fail CI**, and **`archive-worker` must refuse
> > a partition containing an unmapped type.**
>
> This also closes `EVT-S3`'s *"which events are `Forever`-tier"* and `T1-2` — one table, three open
> questions — which the first form got right for the wrong reason.

#### `PO-E4` — per-event `ruleset_digest`: **keep it, because `D-46`'s argument is right about cost and silent about risk**

*Served now:* the column exists and is written (`AS-4`). *Served later:* replay, and divergence
detection under `D-39`.

`D-46` is correct that the digest is **derivable**: `(reality_id, epoch)` → digest is an append-only
binding, so identity costs zero bytes per event. But derivable **from what?** From a binding history that
must survive. And the measured state of that history is: `archive-worker` drops partitions at 90 days,
and `archive-restore` restores into `events_restore_<YYYYMM>`, **a table `load_aggregate` does not
read** (`D-69`). `D-47` already noticed the sharp end of this from the other side — a collector evicting
old rulesets *"breaks the next epoch switch, immediately and loudly."*

> ## 🔴 `EV-19` WITHDRAWN 2026-08-02 after red team `RT-15`/`RT-16`. **The argument was exactly
> backwards, and `D-46` was right for a reason neither document stated.**
>
> The withdrawn claim was: *keep the per-event digest, because the derived alternative depends on a
> binding history that may not survive retention.* Measured, the opposite is true:
>
> | | |
> |---|---|
> | **the per-event digest** | `services/archive-worker/pkg/pgio/pgio.go:125-129` selects **13 columns and `ruleset_digest` is not one**; `types.go:55-69` has no field for it; `restore.go:76-96` creates a restore table without it ⇒ **it is dropped with the partition and does not come back on restore** |
> | **the derived alternative** (`reality_ruleset_binding`) | **non-partitioned and never archived** ⇒ it is the thing that survives |
>
> ⇒ **The shipped retention path makes the DERIVED form durable and the PER-EVENT form the one that gets
> deleted.** And the live smoke that would have caught this
> (`archive_worker_live_smoke_test.go:79-81`) inserts only base columns, **so it could never have gone
> red** — an `NV-1` vacuity in the test that guards the path.
>
> **And the word the whole argument rested on was unearned: nothing anywhere COMPARES an event's
> `ruleset_digest`.** The only production readers are a deserialize (`event_store_pg.rs:396`) and a
> fan-out (`pgsource.go:66`). The only `RulesetMismatch` refusal in the tree
> (`sim-core/src/island/lifecycle.rs:152-155`) compares an island **checkpoint**, not an event. The
> migration comment `0016:53` states *"a mismatch is refused"* **as fact; it is aspiration.** I called the
> digest *"a check"* without asking whether anything checks.
>
> **What survives, and it is not nothing.** The digest's **write** path is genuinely good — `spine.rs:306,394`
> derive it from the island that actually ran the rules, guarded by a regression test. So the column is
> **correct and unused**. The honest statement is: *the per-event digest is a well-formed fact with no
> reader, no comparator and no retention* — three separate reasons it cannot yet be a check, each of
> which is buildable and none of which is an argument for the field's cost.
>
> **`D-46` stands.** Identity is answered by the append-only ordinal registry at zero bytes per event.

#### `PO-E5` — validator ordering: **the owner is the code; until then, `_boundaries/03`, and the evidence is in the divergence itself**

*Served now:* nothing runs it. *Served later:* admission, which is `G1`+`G2` and `V3` on the ladder
(§5.4) — **one stage of one group of one layer**, not a rival ordering.

The tell is in the four divergent restatements: the boundary file's list contains **`lex_check` and
`heresy_check`, which appear in none of the three corpus files**, and it puts world-rule lint last where
all three put it mid-chain. A list with two stages the others never heard of is the one closer to the
thing being ordered.

> **`EV-20`. `_boundaries/03_validator_pipeline_slots.md` owns the stage list and must delete its
> "pending" clause; `05_validator_pipeline.md` keeps the FRAMEWORK (`EVT-V2`'s five fail modes with
> `silent_drop` forbidden, `V3` retry, `V6` consequences-as-events) and deletes its stage list.** And
> per `D-40`, the durable answer is that neither prose file owns it: the ordering becomes a **machine
> contract** generated from the same artifact that serves `D-37`'s single-writer gate and `D-38`'s
> read-sets. Prose ownership here is an interim, and should be labelled as one.

### 9.3 What would reverse each answer

Stated so that the evaluation is checkable rather than merely persuasive.

| # | reversed if |
|---|---|
| `EV-16` | a `G1`-stage refusal turns out to have an in-world consequence — i.e. the trust boundary is not actually free of domain reads |
| `EV-17` | someone demonstrates a trustworthy reconstruction of occurrence membership from `correlation_id` + subject joins, falsifying `AS-3` for this field |
| `EV-18` | the retention classes turn out not to partition cleanly — an event class that is both volatile and an input to a forever-fold |
| `EV-19` | the ordinal/binding registry gets a retention guarantee independent of the events table, at which point the digest becomes genuinely redundant |
| `EV-20` | `D-40`'s machine contract lands, at which point both prose files stop owning anything |

**One thing this evaluation does NOT resolve, and it should not be smoothed over:** every answer above
leans on `AS-1`, and `AS-1` has an expiry date. The first pinned reality ends it. **`EV-17` is the only
one that becomes impossible rather than merely expensive after that**, which is why it is the single item
here that belongs in front of the others.

---

## 9.4 The three that needed redesign — `EV-14`, `EV-17`, `EV-1`

The red team killed these three separately. They failed for **one** reason, which is why they are
redesigned together rather than patched one at a time.

> **The common cause: this spec had no theory of ownership for anything that SPANS AGGREGATES.**
> `D-37`'s single-writer rule is per aggregate, and it was inherited without being applied to the two
> new things introduced here. A reaction **wave** spans aggregates. An **occurrence** spans aggregates.
> Both failed on the same question — *who writes it* — and `RT-9` asked it in exactly those words.

### 9.4.1 `EV-14′` — the property, and the two mechanisms that satisfy it at two scopes

`RT-1` was right that `EV-14` as written is unsatisfiable: a *view* is a projection over **committed**
events, `TRG-A18` says **a chain commits once**, and waves are where 100 % of reactions live — so
inside a chain the view can never contain the event being reacted to. What `EV-14` was adopted **for**
survives; the mechanism it named does not.

> **`EV-14′`. NO EMITTER IS ITS OWN AUTHORISER.** Every event→event edge passes a point that can
> **refuse**, and that point is never the thing that proposed the edge. This is the property; the
> mechanism differs by scope, and the discriminator is **whether the cause is inside the same commit
> batch** — which, by `TRG-A18`, is the same question as *"is it in the same chain."*

| scope | mechanism | the refusal point | why the other mechanism cannot apply |
|---|---|---|---|
| **intra-chain** (same commit batch) | **`TRG`'s wave model** — `G6` spawns proposals into wave *n+1*; wave *n+1* runs **`G2 AUTHORISE`** | **`G2`**, and `TRG-A10` (G3 rewrites, G6 spawns, neither does the other) is what makes termination *provable* rather than budgeted | nothing is committed yet, so **no projection exists**. `TRG-L4`'s read-old/write-together is what makes the uncommitted working state safe, and that is a stronger guarantee than a view would give |
| **cross-tick** (the cause is already committed — a beat, a generator reacting to a fact) | **`event → view → command → decider`**, the Automation pattern | the **decider**, which may reject the command | the wave has ended; there is no `G2` to route through, and the reacting party is a different process |

**Three things this fixes at once.** *"When my reflect is prevented, gain rage"* works again — the
discard is in the wave's own stream and `G2` is the refusal point, exactly as `33_…:348` advertises.
**`EVT-G2(d)` `OtherGeneratorOutput` stops being a contradiction** (`RT-13`): a generator reacts to a
**committed** event, so it is cross-tick, so it is the view→command→decider path, so it is legal — and
§8 may keep it. And **`EV-13`'s two bounds now have one home each** instead of two mechanisms competing
for both: `TRG-A14` bounds the intra-chain scope structurally; the cross-tick scope is bounded by the
scheduler — **which `RT-3` measured as neither a bound nor deployed**, and that is now stated as
outstanding work rather than as a property we have.

### 9.4.2 `EV-17′` — an occurrence is ambient CONTEXT, and nesting lives on the occurrence

`RT-8` and `RT-9` killed the first form: no nesting rule while the corpus already ships a nested
occurrence (`CombatSessionBorn → CombatRoundDelta → CombatSessionResolved` inside a multi-cell siege),
and no possible writer, since all three candidates fail. **A fourth candidate resolves both**, and it
is the one the failure of the other three points at.

> **`EV-17′`. An occurrence is OPENED AND CLOSED BY ORDINARY FACTS, and `occurrence_id` on an event is
> AMBIENT CONTEXT the engine propagates — exactly as it propagates `correlation_id` — never interpreted,
> never branched on.**

| the objection | why it dissolves |
|---|---|
| *producer-stamps is a subject-side claim on the wire — the confused-deputy shape `producer.rs:6-9` exists to close* | it is **not a claim by the producer about the subject**. The engine stamps *which open occurrence this was produced within*, the same way it stamps correlation. A producer cannot elect an occurrence any more than it can elect a correlation |
| *engine-derives is forbidden by `Q-E` — "the engine never learns those words"* | it still never does. The **`kind`** (`siege`, `festival`, `tribulation`) lives on the **occurrence record** and is declared vocabulary; the engine handles an opaque id |
| *propagation is transport, declared out of scope* | propagating an ambient id **within a chain** is not transport — `TRG-A18` says the chain commits once, so the whole chain shares one ambient context by construction. This is the same reason `RT-9`'s *"`EV-14` severs it at the first reaction"* no longer bites |

**Nesting — and the fix is to put the edge where cardinality says it goes.** `D-25`: *an edge lives on
the MANY side.* A parent occurrence has many children ⇒ **the parent link belongs on the child
occurrence, not on the event.**

```
event      → occurrence_id            // the INNERMOST open occurrence. fixed width. one field.
occurrence → { kind, parent: Option<OccurrenceId>, opened_by, closed_by }
```

So a round-delta inside a duel inside a siege carries **the duel**, and *"every event in the siege"* is
a transitive walk over a small occurrence tree — not a scan, and not a second membership projection of
the kind `EVT-A10` forbids. `RT-8`'s silent under-return is impossible because there is no choice to
get wrong.

> ⚠ **The residue, stated rather than hidden:** this assumes occurrences that overlap are **nested**. An
> event that genuinely belongs to two *unrelated* occurrences — a festival and a siege in one place —
> has no representation, and the tree does not help. The honest options are to **forbid it** (the author
> picks, and the engine can enforce that an occurrence's ancestors are its only co-members) or to accept
> that such a case is **not one event**. This is the sharpest thing left open in `EV-17′` and it should
> be settled before the field is written, because `AS-3` still applies: it cannot be backfilled.

### 9.4.3 `EV-1′` — six objects is a LIFETIME classification, not a partition of shapes

`RT-10` classified the eleven shapes into the six objects and got 3 clean · 3 double-booked · 4
homeless · 1 form-without-definition. **The double-booking is not a defect in either list; it is a
defect in my assumption that they were the same kind of thing** — and `EV-12` had already said so
(*"the answer is `shape × axes`, not a flat enum"*) before I turned `EV-1` into a partition anyway.

> **`EV-1′`. The six objects classify LIFETIME, not subject. A SHAPE IS A PROCESS, and one process
> emits several objects at different stages.** An interaction (shape 5) emits an **intent** ① and then a
> **fact** ④; a threshold (shape 1) emits a **signal** ③ and possibly a **latch** ④. That is not double
> booking — it is a pipeline, and reading it as a partition is what made it look like one.

The four "homeless" shapes resolve, and two of them were never homeless:

| shape | resolution |
|---|---|
| **8 · derived/reactive** | **emits no object at all**, and that is correct — it is `G8 DERIVE`, the last group, which invalidates and re-resolves. `EV-10` already said it sits underneath the others; it has no home in `EV-1` because it produces nothing to store |
| **11 · admin/authoring** | **belongs to SSOT #1, not to the event log** — it mutates the *ruleset*, which is why `EV-4`'s *"reproducible under a pinned ruleset"* read as circular. The machinery already exists and is registered: **`ruleset.epoch_activated`**. Its home is the epoch switch, not a category here |
| **9 · observation** | its **effects** are the objects — a clock advance and a materialisation are **facts** ④. The looking itself is not an event, which is why it classified as ⑥. ⚠ But `RT-4` still stands against it: `WSA-A23` writes `f`'s output into `f`'s own input set, so two observation schedules produce different event **sets**, and `WSA-T4` — the test `EV-11` rests on — **is unpassable as written.** Unresolved, and now stated as such |
| **6 · ambient/world** | needs a **quantity holder that is not an actor**. `D-93` answered it from the other side: **a World IS a locus**, and a locus is an entity, so a world-scoped fact is an ordinary fact on the World locus-actor. The residue `O-118b` (a sect **treasury** is held by the group as such) is the social system's question, not this one |

---

## 10. Where this design is most likely wrong

> **⚠ METHOD CHANGED 2026-08-02 — the first version of this section did real harm.** It attacked
> `EV-14` on **cost**, an axis `21_architecture_ceilings.md:191` had **already closed**, while the actual
> defect was structural incompatibility with `TRG-A18` — **which the same document quoted approvingly 40
> lines earlier.** A *"where this is most likely wrong"* section that names a plausible-but-closed
> weakness is **worse than none**: it reads as diligence and steers the reviewer away. The fix is not
> more care. **A self-attack must enumerate each claim's own DEPENDENCIES and check every one**, not
> guess at a failure mode. So this section is now organised by dependency.

### 10.1 The new claims, by what each DEPENDS ON

| claim | depends on | checked? |
|---|---|---|
| **`EV-14′`** | `TRG-A18` (a chain commits once) · `TRG-A10` (G3 rewrites / G6 spawns) · `TRG-A9` (a nested pass keeps `G2`) · that a cross-tick reaction's cause **is** committed | first three **verified against `33_trigger_group_order.md`**. The fourth is **assumed**: nothing proves a beat's cause is always committed when the beat fires, and `RT-3` measured the scheduler as **not deployed** |
| **`EV-17′`** | that the engine can propagate an ambient id without interpreting it (`correlation_id` as precedent) · `TRG-A18` giving one chain one ambient context · `D-25` (an edge lives on the many side) · that overlapping occurrences are always **nested** | first three hold. **The fourth is the open residue and is stated in §9.4.2** — an event in two *unrelated* occurrences has no representation |
| **`EV-18′`** | that coverage of the registry by `event_classes.yaml` is **achievable** · that `archive-worker` can be made to refuse an unmapped type | coverage is **3 of 15 today**, measured; the refusal does not exist — `partition_picker.go:99-128` filters on **age alone**. Both are `DBT-2`, buildable, tracked |
| **`EV-1′`** | that a shape may emit several objects without ambiguity about **which** object a given record is | **unchecked.** If one shape emits both a signal and a fact for the *same* subject, nothing here says how a reader tells them apart |
| **`EV-16`** | that `G1` is free of domain reads | **FALSIFIED** by `_boundaries/03:119`'s pre-pipeline mortality gate (`RT-6`). Its own §9.3 reversal condition fired; the decider line survives, its mapping onto `G1` does not |
| **`EV-21`** | that the quantity's trajectory is **not** fully in the log | **CONTESTED** — `actor-dataflow:2052-2053` records both `QuantityDelta` **and** `ThresholdCrossed` (`RT-20`), and both exemplars contradict the *durable* reading: `COMB_004:254-257` calls the latch *"not durable state"* and `SPO-D10` **accepts that it can fire twice** |

### 10.2 The residual attack surfaces

Written for the red team, by the author, before they arrive.

| # | the attack surface |
|---|---|
| **A-1** | **`EV-14` (never let an event cause an event) may be too expensive at game tick rates.** The pattern comes from enterprise systems where a hop costs milliseconds and correctness dominates. Our budget is an island step of **176–229 ns**. The view→command→decider hop per reaction, per wave, may be unaffordable — and the measured constraint (~170 commits/s) is about *writes*, which `TRG-A18` already batches. **Nobody has priced `EV-14` against a wave.** |
| **A-2** | **`EV-12`'s `shape × axes` has no proposed encoding.** It is a diagnosis of why a flat enum fails, not a design. Eleven shapes × eight axes is a large surface, and the obvious encodings (a tag union, a bitfield, a row per axis) each have a failure mode this document has not examined. |
| **A-3** | **The six-object split (`EV-1`) is asserted from prior art, not from our corpus.** Our features may collapse two of them for good reasons this round did not find. In particular ⑤ chronicle-vs-④ fact may not survive contact with `contracts/retention/event_classes.yaml`'s two classes. |
| **A-4** | ✅ **RESOLVED by `EV-21` (§3.3), and the resolution strengthens `EV-7`.** Three objects shared one word: the **band** is derived · the **crossing** is not an event · the **latch** (*this consequence has already been taken*) is a durable fact, by `EV-4`'s own definition. `first_kill_only` and the cleared-camp bit are latches, not stored thresholds. The latch satisfies `EV-5` for the general reason — the quantity's trajectory is **not** fully in the log (regen is closed-form; phase 0 writes nothing durable), so *"did it ever cross"* is genuinely not re-derivable. ⚠ **Residue:** this makes the latch's OWNER an open question — it is neither the quantity nor the event log's business, and nothing in this spec says where a latch lives. |
| **A-5** | **Shape 9 (observation) may break `I-5`.** If looking is what writes canon, then two players with different observation schedules produce different logs. `34_…:296`'s test asserts identical `occurred_at` with only `recorded_at` differing — but **that test does not exist in code**, and this document is now resting a load-bearing shape on it. |
| **A-6** | **The rot ledger's 31 rows are a measurement of a corpus, not a plan.** Nothing here says who applies them or in what order, and a ledger nobody applies is `DR-15`'s failure — *a recorded contradiction that is not applied is indistinguishable from an unnoticed one*. |
