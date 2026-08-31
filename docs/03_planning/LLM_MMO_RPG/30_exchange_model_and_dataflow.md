# 30 — The exchange model: how *ta* and *chúng* interact, and the dataflow that follows

> **Status:** SEALED 2026-07-28 (DESIGN). Axioms `EXC-A1..A5`, findings `EXC-F1..F3`, laws `EXC-L1..L3`,
> open `EXC-Q1..Q3`. **Prefix `EXC` registered** in
> [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
>
> Follows [29 — ontology](29_ontology_existence_self_others.md). The PO's proposition:
>
> > *"Theo khái niệm tồn tại trong triết học duy vật biện chứng thì sự tồn tại chính là sự trao đổi
> > năng lượng có phải không? Và nó chính là resource management? Mọi tương tác đều có cost và earn —
> > earn có thể là resource, cũng có thể là tác động của ta đến chúng và ngược lại."*
>
> This document answers that question directly, including **where it is right, where it must be
> refined, and the one place where taking it literally would ship an expensive bug.**
>
> 🔒 **SEALED** means the *reasoning* is closed and must not be re-litigated from memory — re-read it. Open questions listed in this file remain open, and the amendment rows are **PROPOSED, not applied**: no feature spec was edited by this arc.


---

## 1. The honest answer to the proposition

**Accepted, and it is the right spine.** *Every interaction is an exchange with a cost and an earn* is
the correct universal shape for this product, for three reasons that are not philosophical:

1. **It gives every mechanic one auditable form**, which is exactly what
   [28 §5](28_product_definition.md)'s `WHEN · IF · THEN · ON` needed for its `THEN`: an effect is a
   *transaction*, not an arbitrary mutation.
2. **It answers [PRD-F1](28_product_definition.md)** — how the world can act without an LLM. §5.
3. **Half of it is already in the kernel.** `Precondition::ResourceAtLeast { id, kind, amount }` is a
   first-class kernel variant, and a failed one produces `Outcome::Discarded { reason }` — *a normal
   recorded outcome, never an error*. The cost side of the exchange model is **already built**.

**Refined on one point, and the refinement is load-bearing.** The proposition says earn *"có thể là
resource, cũng có thể là tác động của ta đến chúng"*. Those two are **not the same kind of thing**, and
modelling them as one type is a well-known and expensive mistake. §2.

**And one caution about the analogy itself.** In dialectical materialism, being is constituted through
*relation and motion*, not as isolated substance — that transfers perfectly, and it is exactly
[ONT-A1](29_ontology_existence_self_others.md)'s *"X exists to the degree the world keeps its
consequence"*. But **energy is conserved and social imprint is not.** Do not carry the physics further
than the relation. The genuinely useful dialectical import is a different one — *contradiction as the
motor of change* — and it turns out to be the key to §5.

---

## 2. EXC-A1 — there are THREE currencies, and conflating them is the expensive bug

> **EXC-A1 — an exchange moves value in one of three kinds, and the kinds obey different laws.
> Nothing in the engine may treat them as one type.**

| | **Thời gian** (time) | **Tài nguyên** (resource) | **Dấu ấn** (imprint) |
|---|---|---|---|
| Conserved? | **no — pure sink** | **yes — transfers sum to zero** | **no — created, never moved** |
| Transferable? | no | **yes** — has an owner, changes owner | **no** — cannot be given away |
| Who holds it | nobody; it is spent | **ta** (or a cell, faction, container) | **chúng** — it lives in the *other* party's state |
| Zero-sum? | n/a | **yes** across a transfer | **no** — my gaining your trust costs no one trust |
| Its decay law | irreversible, monotonic | `stockpile_cap`, spoilage (RES-D18) | **must decay**, or it inflates without bound (REP R8-L4) |
| Already in engine | ⚠️ TDIL clocks exist; **the PC has no time budget** ([P4](28_product_definition.md)) | ✅ RES_001 + `ResourceAtLeast` | ⚠️ stored (`actor_actor_opinion`, REP_001) but **written only at session end** |

**The mapping onto [29](29_ontology_existence_self_others.md) is exact, and that is the sign the
distinction is real rather than pedantic:**

> **Transfer changes what *ta* HAS. Imprint changes what *chúng* HOLDS about ta.** The two "earn"
> types in the PO's formulation are precisely the two directions of the ONT loop.

> **EXC-F1 — if imprint is modelled as a resource, you ship three bugs at once:** reputation becomes
> *tradeable* (I sell you my standing), *farmable* (grind a renewable source), and *conserved* (my
> gaining trust costs someone else trust). Each has shipped in real games. The type system must make
> them unwritable: an imprint has **no owner field and no transfer operation** — only a *subject* (who
> holds it) and an *object* (about whom).

**Time deserves its own row rather than being folded into resource**, and the corpus proves why:
TDIL_001 makes fiction-time *acquirable at a cost* — RES_001's own note cites the *"Dragon Ball chamber
365× wall-clock"* case. So time can be **bought but never given**. That is a third law, not a variant
of the second, and it is a whole genre's core mechanic (a cultivator's real scarcity is years).

> **EXC-A2 — every action costs time, always.** This is what makes choice real: doing A means not doing
> B. It also converts [PRD-Q3](28_product_definition.md) (*does the PC spend a time budget?*) from an
> open question into a **requirement** — without it, "living in the world" has no cost, and a world
> with no cost has no decisions in it.

---

## 3. EXC-A3 — the house example, decomposed (and what it reveals)

The PO's test case: *"nhân vật tốn tiền (tài nguyên) để đổi lấy việc sở hữu 1 căn nhà"*. Worked
through properly, it produces the missing piece of the whole model.

| Step | Kind | Note |
|---|---|---|
| money leaves me, arrives at the seller | **transfer** | conserved; `ResourceAtLeast` already gates it |
| an **ownership edge** `ta ↔ house` is created | **relation** | not a resource — it is a *relation*, and it has no amount |
| the seller, the neighbours, the local faction **recognise** it | **imprint** | held by *chúng*, about *ta* |
| I can now store, rest, be found, host, be robbed | **capability** | *derived* — see below |

**Two things fall out, and both are structural.**

> **EXC-A3 — ownership is not a property of me and not a property of the house. It is a RELATION that
> the world recognises.** Strip the recognition and I am not an owner, I am a squatter. In a world
> with no *chúng* (the [ONT-F3](29_ontology_existence_self_others.md) state today), ownership is a
> database flag and nothing more. In a world with *chúng*, ownership can be **contested, inherited,
> stolen, or recognised by one faction and not another** — and *that* is where the gameplay is.

> **EXC-A4 — capability is DERIVED, never stored.** What I *can do* is computed from (what I own) ×
> (what others hold about me) × (what I am), the same derived-never-stored discipline
> [DF7-A2](27_extensibility_stress_test.md) already applies to stat blocks.

EXC-A4 is the payoff, because it **is** the missing arrow:

> [ONT-F4](29_ontology_existence_self_others.md) found the loop's last arrow absent — *"what they hold
> changes what I can do"* — and diagnosed it as the **stored-but-never-read** bug class applied to the
> entire social layer. **Capability derivation is the read.** It is the one mechanism that closes the
> loop, and it is a *derivation*, not a new subsystem.

The smallest honest form is already reachable: a `Precondition` variant that reads standing, so an
action refused for social reasons is `Outcome::Discarded { reason }` — a recorded normal outcome,
exactly like every other failed precondition. This is [ONT-Q1](29_ontology_existence_self_others.md)'s
proposal arriving from the exchange side, which is a good sign for both.

---

## 4. EXC-A5 — the transaction is the unit of dataflow

> **EXC-A5 — every action is a TRANSACTION: a proposal that declares its costs, is authorised against
> them, and commits a set of deltas across the three currencies.**

```
ACTION (proposal)
 ├─ COST     time (always)  ·  resource (maybe)  ·  capability preconditions
 │              └─── authorised in-loop: Precondition::{ResourceAtLeast, …}
 │                   failure ⇒ Outcome::Discarded{reason}   ← recorded, not an error
 └─ EARN     resource delta   (conserved transfer, owner→owner)
             imprint delta    (created in the OTHER's state; decays)
             relation delta   (ownership / membership / title edges)
                        │
                        ▼
             CAPABILITY  (derived, never stored)
                        │
                        ▼
             the set of actions possible next  ──▶ ACTION
```

**How much of this exists.** The left half is built: proposals, in-loop authorisation, the
precondition vocabulary, the discard-as-outcome discipline, event commit, replay. The right half is
not:

| Piece | Status |
|---|---|
| cost declaration + authorisation | ✅ `Precondition`, `ResourceAtLeast` |
| failure as a recorded outcome | ✅ `Outcome::Discarded` |
| resource delta on commit | ✅ RES_001 generators + inventories |
| **imprint delta on commit** | ❌ opinion is written **at session end**, not by the transaction |
| **relation delta** | ⚠️ ownership exists per-aggregate; no uniform edge concept |
| **capability derivation** | ❌ does not exist — nothing reads standing back |
| **the ledger / conservation check** | ❌ does not exist |

> **EXC-F2 — the engine already has the transaction. What it lacks is the LEDGER.** Costs are checked
> one at a time against one holder; nothing asserts that what left one place arrived at another. Until
> that exists, "resource management" is a set of independent counters, and counters drift.

---

## 5. EXC-F3 — the world acts when a ledger fails to balance (this answers PRD-Q1)

This is where the dialectical framing earns its keep, via the part that is *not* about energy
exchange: **change is driven by internal contradiction.**

[PRD-Q1](28_product_definition.md) asked whether the world may act *deterministically* — the unnamed
cell in DL-A1's cost table (*deterministic + accumulating*). The exchange model supplies the trigger
for free:

> **EXC-F3 — an entity acts when its ledger cannot balance.** A cell whose consumption exceeds its
> production has an unsatisfiable obligation, and an unsatisfiable obligation is a *contradiction*
> that must resolve into an action. No LLM, no scheduler, no authored plot.

A worked escalation, entirely from mechanisms that already exist:

| Ledger state | The world's response | Built from |
|---|---|---|
| production < consumption | draw down `stockpile` | RES_001 |
| stockpile exhausted | **buy** — spend resource, imprint on the seller | transfer + imprint |
| no resource to spend | **take** — raid a neighbour; large negative imprint | transfer + imprint |
| nothing left to take | **starve** — `HungerTick` commits deaths | DL-D13 sweep |
| enough deaths | **disperse** — the settlement stops existing | ONT existence ladder, downward |

Every row is deterministic, replayable, cheap, and reads only quantities the design already has. It is
the *"bandit camp grows if unchecked"* / *"village starves after a failed harvest"* class that
[PRD-F1](28_product_definition.md) identified as forbidden-by-accident — forbidden by DL-D1's
*"evaluated, never ticked"*, which was written to protect **token cost** and does not apply here.

**It also creates existence degree 4** — the rung [29 §2](29_ontology_existence_self_others.md) noted
was missing. An entity that resolves its own contradictions is an entity that *chooses*, which is the
top of the existence ladder.

> **EXC-Q1 — what is the smallest ledger that makes this true?** Almost certainly *one* cell with
> production, consumption, a stockpile, and the four-rung escalation above. That is also a strong
> candidate answer to [PRD-Q2](28_product_definition.md) (*the smallest world-acting mechanic that
> proves the loop*) — it is the world-tier equivalent of "one REAL encounter".

---

## 6. The three laws, each with the test that can fail it

Stated as laws because [the repo's discipline](21_architecture_ceilings.md) is *rule + SoT + gate +
test*, and a law with no falsifier is decoration.

> **EXC-L1 — Conservation of resource.** Across any committed transaction, resource deltas sum to
> **zero**, except at a **declared source** (a generator) or a **declared sink** (consumption, decay,
> tax). Both must be declared in the ruleset and stamped in the event.
> **Bite test:** a transaction that creates 10 coins with no declared source must FAIL the ledger
> assertion. If the assertion cannot fail, it is not testing anything.

> **EXC-L2 — Imprint is created, never moved, and always decays.** No transfer operation may exist on
> an imprint. Every imprint kind declares a decay so standing cannot inflate without bound.
> **Bite test:** attempt to transfer standing between two actors — must be **unrepresentable in the
> type system**, not merely rejected at runtime. And: hold an imprint constant with no reinforcement
> over N periods; it must fall.

> **EXC-L3 — Time is monotonic and never refunded.** Fiction-time may be *acquired at a cost*
> (TDIL dilation) but never transferred and never reversed.
> **Bite test:** no action's earn may include a negative time cost.

**EXC-L1 has a deadline of the same kind as [XST-R6](27_extensibility_stress_test.md) (retired 2026-07-28 -> [`QTY-D4`](35_quantity_architecture.md))'s.** Conservation
is cheap to assert while there are few resource flows and effectively impossible to retrofit once
content has been balanced against a leaky economy — because by then the leaks *are* the balance.

---

## 7. What this decides about dataflow — the direct answer

The question was *how do ta and chúng interact, because that decides the dataflow.* The answer:

1. **They interact ONLY through transactions.** There is no other path by which one actor changes
   another. This is the dataflow rule, and it is enforceable: a mutation that is not a committed
   transaction is a defect.
2. **The direction determines the currency.** *ta → chúng* writes an **imprint** into the other party's
   state (single-writer safe: [ONT-A4](29_ontology_existence_self_others.md) — the observer's island
   owns its own half). *ta ↔ ta* and *ta ↔ world* move **resource**, which is conserved and owned.
3. **The return path is a derivation, not a message.** *chúng → ta* does **not** push anything. What
   others hold is **read** at capability-derivation time (EXC-A4). This keeps the fan-in bounded and
   keeps islands shared-nothing — nobody writes into my state because of what they think of me.
4. **Time is the universal cost and the only unconditional one**, which is what makes the loop a
   sequence of choices rather than a checklist.

Points 2 and 3 together are the important structural result: **writes are unilateral and local; the
social influence flows back as a READ.** That is what lets an unbounded society exist on top of a
single-writer, shared-nothing island model — the thing that looked like the deepest tension in
[29 §4](29_ontology_existence_self_others.md) dissolves once the return path is a derivation rather
than a message.

---

## 8. Open

| # | Question |
|---|---|
| **EXC-Q1** | The smallest balancing ledger that makes EXC-F3 true (§5) — also the candidate answer to [PRD-Q2](28_product_definition.md). |
| **EXC-Q2** | **Is `relation` a fourth currency or a degenerate imprint?** Ownership, membership and title are edges with no amount. They may be imprints with a boolean magnitude, or a genuinely separate kind. Deciding wrongly either duplicates the imprint machinery or forces edges through a numeric type that does not fit them. |
| **EXC-Q3** | **Where does the ledger assertion live?** In-loop (every commit balances — strong, costs step budget) or as a Class C audit sweep (cheap, detects drift after the fact). The [ceilings](21_architecture_ceilings.md) suggest in-loop is affordable, but it has never been measured for this. |

---

## 9. Cross-references

* Ontology — [`29_ontology_existence_self_others.md`](29_ontology_existence_self_others.md)
* Product loop + the 4-tuple mechanic model — [`28_product_definition.md`](28_product_definition.md)
* Extensibility findings — [`27_extensibility_stress_test.md`](27_extensibility_stress_test.md)
* Resources, generators, stockpiles — [`features/00_resource/RES_001_resource_foundation.md`](features/00_resource/RES_001_resource_foundation.md)
* Opinion + standing — [`features/00_actor/ACT_001_actor_foundation.md`](features/00_actor/ACT_001_actor_foundation.md) · [`features/00_reputation/`](features/00_reputation/)
* Time + dilation — [`features/17_time_dilation/TDIL_001_time_dilation_foundation.md`](features/17_time_dilation/TDIL_001_time_dilation_foundation.md)
* Daily life, the evaluated world — [`features/12_daily_life/DL_001_daily_life_foundation.md`](features/12_daily_life/DL_001_daily_life_foundation.md)
* Kernel preconditions + outcomes — [`14_sim_core_spec.md`](14_sim_core_spec.md)
