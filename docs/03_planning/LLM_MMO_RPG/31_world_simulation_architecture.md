# 31 — World-simulation architecture + spec reconciliation

> **Status:** SEALED 2026-07-28 (DESIGN + RECONCILIATION). Axioms `WSA-A1..A6`, findings `WSA-F1..F3`,
> amendment rows `WSA-R01..R18`. **Prefix `WSA` registered** in
> [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
>
> Closes the arc [28 product](28_product_definition.md) → [29 ontology](29_ontology_existence_self_others.md)
> → [30 exchange](30_exchange_model_and_dataflow.md) by answering the PO's thesis:
>
> > *"Chỉ cần chúng ta thiết kế dataflow và software architecture giải quyết được các khái niệm triết
> > học ở trên thì cơ bản world simulation của chúng ta có thể extend mọi cơ chế gameplay — đây chính
> > là bản chất của sự tồn tại."*
>
> **§1 tests that thesis rather than accepting it.** §2 is the architecture that satisfies it. §3–§6
> are the reconciliation: what in the existing corpus must change, what merely changes meaning, and
> what does not exist yet.
>
> ⚠️ **The amendment rows are PROPOSED, not applied.** Each row is marked `verified` (I read the
> source text this session) or `verify` (inferred from an index or a cross-reference and must be
> confirmed before editing). No spec file was edited by this document.
>
> 🔒 **SEALED** means the *reasoning* is closed and must not be re-litigated from memory — re-read it. Open questions listed in this file remain open, and the amendment rows are **PROPOSED, not applied**: no feature spec was edited by this arc.


---

## 1. The thesis, tested

**Mostly right, and for a better reason than it was offered.** The three concepts, made operational,
turn out to supply **three of the four parts** of a mechanic as defined in
[PRD-A2](28_product_definition.md) (`WHEN · IF · THEN · ON`):

| Part | Supplied by | How |
|---|---|---|
| **ON** — what can be addressed | **tồn tại** | the existence ladder says what persists and is therefore addressable at all |
| **THEN** — what an effect may do | **exchange** | a delta across the three currencies; there is no other kind of effect |
| **IF** — what may be tested | **ta × chúng** | capability derivation reads (what I own) × (what they hold) × (what I am) |
| **WHEN** — the moments that exist | ❌ **not supplied** | see WSA-F1 |

That is a genuinely strong result: it means the *effect* and *predicate* vocabularies stop being
open-ended wish-lists and become **closed by construction** — three currencies and one derivation. It
is why [XST-R10](27_extensibility_stress_test.md) (combinators, not more `EffectOp` leaves) is the
right answer: with a uniform delta type, composition is all you need.

**But two things are outside it, and naming them is what makes the thesis usable rather than a
slogan.**

> **WSA-F1 — the ontology does not supply WHEN.** [EXC-F3](30_exchange_model_and_dataflow.md) supplies
> exactly one new trigger (a ledger that cannot balance), and it is a big one — but *"any mechanic"*
> needs a general moment vocabulary: on-hit, on-enter, on-death, on-threshold-crossed, on-day-boundary.
> Without it, nothing can happen except when a player acts. **[XST-R9](27_extensibility_stress_test.md)
> is still required engineering; the ontology reduces it from "design a whole effect system" to
> "design a trigger vocabulary", which is perhaps a quarter of the work.**

> **WSA-F2 — field state has no home in the three currencies.** Weather, temperature, gas, light,
> fertility, contamination: state owned by *nobody* and held *about* nobody. Not resource (no owner),
> not imprint (no subject), not time. This is the immersive-sim report's BREAK 2
> ([27a](27a_stress_test_agent_reports.md)).
>
> **Most of it is recoverable cheaply**: treat a **cell as an entity that owns quantities**, and
> fertility/stores/contamination become ordinary owned resources with a place as the owner. What is
> *not* recoverable that way is **continuous propagation** (gas diffusing, heat spreading, sound
> travelling), which needs a lattice the island model does not have.
>
> ~~**WSA-D1 (proposed): declare continuous fields OUT OF SCOPE, explicitly, in the docs.** Per-cell
> discrete quantities are in; diffusion is out.~~ [27 §7.1](27_extensibility_stress_test.md) already
> established that promising Dwarf-Fortress-level simulation and shipping less is worse than promising
> less.
>
> **⛔ SUPERSEDED by [`WSA-D2`](32_locus_as_actor.md) (doc 32, SEALED 2026-07-28) — applied 2026-07-30
> per `WSA-R24` / [REC-85](19_reconciliation_register.md).** `WSA-A7` (a locus is both an entity and an
> actor) **recovers** the part conceded here: diffusion is **a conserved TRANSFER between adjacent
> locus-actors** — cell A gives 5 heat to cell B — which is [`EXC-L1`](30_exchange_model_and_dataflow.md)
> applied to neighbours, not a new mechanism. Its honest cost is a **cadence**: diffusion is time-driven,
> so it is Class C batch work at a coarse tick, never the 20 Hz hot path.
> **What stays refused, and is refused BY NAME rather than by omission:** *sub-cell* continuous
> resolution — a true fluid lattice inside a single cell — which is a genuinely different substrate.
> The §7.1 principle above is untouched and is exactly why the refusal is explicit.

**One refinement that strengthens the model.** Testing it against knowledge and rumour — *"I know a
secret"*, *"the village heard about the murder"* — shows that these are not a fourth currency:

> **WSA-A1 — an imprint is non-conserved state held by a SUBJECT about an OBJECT, where the object may
> be an actor, a fact, a place or a faction.** Telling you a secret does not make me forget it, which
> is exactly the non-conservation law [EXC-L2](30_exchange_model_and_dataflow.md) already states. So
> reputation, opinion, familiarity, knowledge, rumour and notoriety are **one kind with different
> object types** — not six systems. This is a real simplification, and it means rumour propagation
> (currently V3, LLM-gated) has a deterministic form: an imprint copy with a decay.

**Verdict:** the thesis holds for *effects and predicates*, which is the larger half. It does not
supply *moments*, and it deliberately excludes *continuous fields*. Both are now named, so neither can
be discovered late.

---

## 2. WSA-A2..A5 — the architecture

### 2.1 Four layers, and only one of them writes

> **WSA-A2 — the system has four layers, and layer 3 is the ONLY mutator of layer 2.**

```
L1  DECLARATION   ruleset, digest-pinned      quantity kinds · currency kinds · law constants
                                              (ordinals pinned by digest, never by load order)
        │ resolved cold
        ▼
L2  STATE         per entity, single-writer    holdings (resource) · imprints held ABOUT others
                  island                       · self dimensions · relation edges
        ▲
        │ the ONLY write path
L3  TRANSACTION   proposal → precondition →    deltas across the 3 currencies
                  apply → events → ledger      (a mutation that is not a committed transaction
                                                is a defect, not a shortcut)
        │
        ▼
L4  DERIVATION    read-only, never stored      capability · stat block · standing fold
```

L4 never writes. L3 writes only through committed events. L1 is immutable within a reality version.
This is the same *derived-never-stored* discipline [DF7-A2](27_extensibility_stress_test.md) applies
to stat blocks, raised to a system rule.

### 2.2 The write rule — why an unbounded society fits on shared-nothing islands

> **WSA-A3 — every write is LOCAL and UNILATERAL.** An entity's island writes only that entity's rows,
> *including the imprint halves that entity holds about others*. Nobody ever writes into my state
> because of what they think of me.

This is [ONT-A4](29_ontology_existence_self_others.md) promoted to an architecture rule, and it is what
makes SL-A12 (one owning island per entity) compatible with a society. The enabling decision —
ACT-A5's *"symmetric pair NOT enforced; stored as 2 SEPARATE rows"* — was taken for a fictional reason
and happens to be exactly right here.

### 2.3 The read rule — near/far asymmetry

If capability derivation had to read *everyone's* opinion of me, it would be a cross-island scan and
the design would collapse. It does not:

> **WSA-A4 — individual imprint is read at CLOSE range; aggregated imprint is read at DISTANCE.**
>
> * **Near** — the actor I am interacting with is, by construction, in my island (an encounter or a
>   cell). Their individual opinion of me is a **local read**.
> * **Far** — everyone else's view reaches me only as a **fold**: standing per (actor, faction), per
>   (actor, place). The fold is a **derived aggregate**, updated as a Class C batch, eventually
>   consistent, and **read locally**.
>
> Consequence: **capability derivation is O(1) and island-local.** No cross-island read on the hot
> path, ever.

`REP_001` (per-`(actor, faction)` standing) **already is that fold** — it was built as a reputation
feature and turns out to be the load-bearing scalability mechanism. That should be recorded on
REP_001 itself, because a future refactor that "simplifies" standing into a live query over opinion
rows would silently reintroduce the cross-island scan.

### 2.4 Module shape

> **WSA-A5 — one crate per stable boundary**, extending [IMP-A5](26_implementation_architecture.md)
> rather than replacing it.

```
crates/
  ruleset-core/        Manifest · Ruleset · REAL digest · Provenance          (no I/O)   ← F1
  ruleset-loader/      provider stack · presets · interning · validation      (I/O)      ← F2
  world-quantities/    the declared quantity set: slots, resource kinds,
                       imprint kinds; ordinals pinned by digest                          ← E2
  exchange/            the transaction: cost declaration, delta application,
                       the ledger + EXC-L1 conservation assertion
  capability/          derivation: (holdings × imprint fold × self) → allowed
                       actions; epoch-stamped like StatSnapshot, never stored
  game-rules/          the LAWS (combat chain, initiative, stat resolution) —
                       pure, no I/O                                                      ← S2
services/commit-service/
  src/domain/  src/admission/  src/manager/
```

Dependency rules, each mechanically checkable:
* `game-rules` and `capability` must **not** depend on `ruleset-loader` ([IMP-D2](26_implementation_architecture.md)).
* `capability` must **not** depend on `exchange` — derivation cannot mutate.
* `exchange` **must** depend on `world-quantities` — a delta names a declared kind, never a literal.

> **WSA-A6 — a currency kind is DECLARED (L1) and its ordinal is pinned by the digest.** ~~This is
> [XST-R6](27_extensibility_stress_test.md) generalised from stat slots to all three currencies~~ —
> **re-based 2026-07-28**: XST-R6 is retired ([QTY-D4](35_quantity_architecture.md)) and a declared
> currency kind is now simply an **L2 declared quantity**
> ([QTY-A2](35_quantity_architecture.md)), inheriting its ordinal discipline
> ([QTY-A5](35_quantity_architecture.md): assigned not authored, never reused, **assignment table
> inside the hashed ruleset**) and its width rule ([QTY-A6](35_quantity_architecture.md): the array
> width is a **compile-time** constant, the identities inside it are declared per reality — A6's first
> draft said the opposite and was reversed by red team the same day).
> The axiom is unchanged; it now has a substrate. It carries the same deadline: **ordinals must be
> fixed before they are serialised into replay logs** — cheap now, a data migration after
> ([27 §11.6](27_extensibility_stress_test.md)).
>
> ⚠️ **Note the layer-name collision:** WSA's "L1" (declared canon) and
> [QTY](35_quantity_architecture.md)'s "L1" (closed derived) are different numbering schemes over
> different things. QTY's layers are always written `L0..L3` with the QTY prefix in scope.

---

## 3. WSA-R01..R08 — amendments required (the spec now contradicts itself)

| # | Target | Says now | Must say | Why | Confidence |
|---|---|---|---|---|---|
| **WSA-R01** | `DL_001` **DL-A1 / DL-D1** | ambient sim splits by cost: deterministic ⇒ V1, generative ⇒ V2/V3; routines *"evaluated, never ticked"* | add the **third row — deterministic + accumulating** — and narrow DL-D1 so the world may keep a consequence | [EXC-F3](30_exchange_model_and_dataflow.md): the world acts when a ledger cannot balance. DL-D1 forbids it for **token-cost** reasons that do not apply | **verified** |
| **WSA-R02** ⚠️ | `DF07` **DF7-A1** closed `StatSlot` | 10 slots closed **in the binary** | ~~slot set **declared per ruleset** … closed *head* + open tail~~ **MECHANISM REVISED 2026-07-28 → [QTY-D5](35_quantity_architecture.md).** The **finding stands** (ONT-F2: a person is not ten numbers; the escape hatch is un-validated) but the fix does not: the laws read **9 of 10** slots by name, so an "open tail" of slots is one dead slot. `DF7-A1` **stays closed**. The open layer is **L2 declared quantities** (primary · resources · elements), and laws bind to **roles** ([QTY-A3](35_quantity_architecture.md)) so a reality may bind `Vital → qi` with no engine release | [ONT-F2](29_ontology_existence_self_others.md) + [XST-F9](27_extensibility_stress_test.md): a person is not ten numbers, and the escape hatch is currently un-validated | **verified (finding); mechanism replaced** |
| **WSA-R03** | `DF07` **DF7-A5** percent-sum rationale | sums *"so the result is order-independent"* | rationale is **wrong** — multiplication commutes too. State the real rule: **one commutative operator per stage; stages ordered** | [XST-F12](27_extensibility_stress_test.md) | **verified** |
| **WSA-R04** | `ACT_001` **ACT-A5** | two unilateral rows, because feelings are asymmetric | **add the second, load-bearing reason**: it gives every relationship half exactly one writer under SL-A12. Mark as LOCKED against "simplifying" into one symmetric row | [ONT-A4](29_ontology_existence_self_others.md) / WSA-A3 | **verified** |
| **WSA-R05** | `ACT_001` §3.1.2 `FlexibleState` | *"typed standard fields + extension keys, **NOT engine-validated**, author guidance"* | extension keys become **declared quantities** (L1) — validated, ordinal-pinned. The property bag is retired | [ONT-F2](29_ontology_existence_self_others.md): the self's escape hatch is unvalidated, which is where slot-overloading starts | **verified** |
| **WSA-R06** | `AIT_001` `Forge:PromoteUntrackedToTracked` | **AdminAction only** | add an **in-world trigger**: meaningful interaction promotes, bounded by `TierCapacityCaps`, defer-never-drop on overflow (DL-D6 precedent), as a committed event | [ONT-D1](29_ontology_existence_self_others.md): existence must be earnable by attention, because the author cannot predict who the player will care about | **verified** |
| **WSA-R07** | `ACT_001` `actor_actor_opinion` mutability | **session-end derivation** + Forge admin; V1 pattern is **NPC→PC only** | written **by the transaction**, during play; **NPC→NPC (ACT-D3) promoted into the critical path** | [ONT-F3](29_ontology_existence_self_others.md): with neither, there is no society — only a set of NPCs each holding one number about you | **verified** |
| **WSA-R08** | `ACT_001` `actor_session_memory` | scoped **per session** | needs a durable tier for what is personally remembered; per-session memory cannot support "chúng" | [ONT-F3](29_ontology_existence_self_others.md) | **verified** |

---

## 4. WSA-R09..R13 — recontextualised (text unchanged, meaning or priority changed)

| # | Target | Change |
|---|---|---|
| **WSA-R09** | `TDIL_001` | **PROMOTED from decoration to load-bearing.** [EXC-A1](30_exchange_model_and_dataflow.md) makes time a currency with its own laws, and TDIL is the only mechanism that lets it be *acquired at a cost*. Its own cited case (a 365× chamber) is now a core-economy mechanic, not a flavour feature. |
| **WSA-R10** | `RES_001` | Its four generators are **declared sources** under [EXC-L1](30_exchange_model_and_dataflow.md), and consumption/spoilage are **declared sinks**. No text is wrong; the framing changes from "generators" to "the only legal points where conservation is broken". |
| **WSA-R11** | `REP_001` | Recorded as **the scalability mechanism of WSA-A4**, not just a reputation feature. A refactor into a live query over opinion rows would reintroduce a cross-island scan. |
| **WSA-R12** | `COMB_001` + `COMB_002/003` + `ABL_001` | **Unchanged and correct**, and **demoted** ([PRD-D3](28_product_definition.md)). Combat depth passes none of [ONT-T1/T2/T3](29_ontology_existence_self_others.md) — an independent confirmation of the same call. |
| **WSA-R13** | `00_VISION.md` | **Stale in two ways**: §8 says this track *"is not on the roadmap"* (it has been built for months) and its staging table frames V1 as *"solo RP"*, which DL_001 already had to argue around. Needs a correction banner pointing at [28](28_product_definition.md), the way its own §0 corrected the "text-based" framing. |

---

## 5. WSA-R14..R18 — new spec work that does not exist

| # | Item | Depends on | Note |
|---|---|---|---|
| **WSA-R14** | **The ledger** — conservation assertion, declared sources/sinks, and the bite test that a source-less 10 coins goes red | `world-quantities` | [EXC-F2](30_exchange_model_and_dataflow.md): the engine has the transaction, not the ledger. Same retrofit deadline as R02 — impossible once content is balanced against a leaky economy, because then **the leaks are the balance** |
| **WSA-R15** | **Capability derivation** — `(holdings × imprint fold × self) → allowed actions`, epoch-stamped, never stored; plus a `Precondition` variant that reads standing so a social refusal is `Outcome::Discarded{reason}` | `world-quantities`, REP fold | **This closes the ONT loop's missing arrow.** It is a derivation, not a subsystem |
| **WSA-R16** | **The PC time budget** — [EXC-A2](30_exchange_model_and_dataflow.md) makes every action cost time; NPCs have `ScheduledActionDecl` and the player has nothing | TDIL | Answers [PRD-Q3](28_product_definition.md) affirmatively. Without it, living in the world has no cost and therefore no decisions |
| **WSA-R17** | **The balancing cell** — one cell with production, consumption, stockpile and the four-rung escalation (draw down → buy → take → starve → disperse) | R14 | The world-tier equivalent of *"one REAL encounter"*; candidate answer to [PRD-Q2](28_product_definition.md) / [EXC-Q1](30_exchange_model_and_dataflow.md) |
| ~~**WSA-R18**~~ | ~~**The trigger vocabulary** (WSA-F1) — a closed `TriggerPoint` set with a depth budget~~ **⛔ RETIRED 2026-07-30 → [`XST-R9`](27_extensibility_stress_test.md) ([REC-94](19_reconciliation_register.md)).** This row and `XST-R9` are **the same work under two ids**, proposed by two registers three days apart — and this row *cites* `XST-R9` in its own reference column, so the duplication was visible at the moment of writing and still produced a second id. That is `XST-F1`'s class arriving in the **register** layer: two indexes of one corpus, neither reading the other. One id had to die before either could be scheduled, or the work gets estimated twice and done zero times. **`XST-R9` survives** (it is the more specific statement, and it is what this row pointed at). ⚠ **Both were also SHRUNK by `WSA-A11`** — *"every WHEN is some actor took a turn"* — so what remains is **not** "design a trigger system": see the narrowed `XST-R9`. | ~~R14, R15~~ | ~~E3~~ **retired — duplicate id** |

---

## 6. The consolidated build order

Merging [IMP-A8](26_implementation_architecture.md), [PRD-D3](28_product_definition.md),
[ONT-D2](29_ontology_existence_self_others.md) and §5. **Nothing advances on "the code is written" —
each row states the evidence that closes it.**

| # | Slice | Done when |
|---|---|---|
| **F1** | `ruleset-core` — real digest | a digest is computed from bytes; two rulesets are distinguishable; zero `RulesetDigest([0u8;32])` outside tests |
| **F2** | `ruleset-loader` | a reality loads its ruleset from a file and the digest lands in a committed envelope |
| **F3** | **Make the digest BITE** ([XST-D5](27_extensibility_stress_test.md)) | edit one constant → the digest moves → replay under a mismatched digest is **refused**. *This test cannot be written today, which is the tell* |
| **X1** | **The four silent-correctness fixes** ([XST-D1/D6/D7/D8](27_extensibility_stress_test.md)) + four tests that can fail | each fix has a test that reds when the fix is reverted |
| **Q0** | **[QTY-A11](35_quantity_architecture.md) length-declared canon + `upcast_rules` + epoch-switch** — *inserted 2026-07-28, and it precedes W1* | an artifact written at 10 slots loads on an 11-slot engine, the old digest still verifies, the transition is an event in the reality's log — **bite-proven**. Deadline: **before any production reality exists** |
| **W1** | `world-quantities` = **[QTY](35_quantity_architecture.md) L2** (R02 *as revised*, R05, WSA-A6) | a reality declares a quantity that does not exist in the engine, and it works end-to-end; ordinals pinned by digest |
| **W2** | `exchange` + the ledger (R14) | a source-less creation reds the conservation assertion |
| **W3** | **chúng** — imprint written by the transaction; NPC→NPC (R07, R08) | two NPCs hold different opinions of the same PC, changed during play, surviving the session |
| **W4** | `capability` derivation + the standing precondition (R15) | an action is refused for a social reason, and the refusal is a recorded outcome |
| **W5** | **tồn tại** — attention promotes (R06) | an Untracked NPC a player interacted with is still there, still marked, next session |
| **W6** | **the balancing cell** (R17) | a village left alone long enough starves and disperses, deterministically and replayably, with no LLM |
| **E3** | the trigger vocabulary (R18) | an author declares a mechanic the engine did not know about, and it fires |

**W3 before W5 before W1's full use** is the [ONT-D2](29_ontology_existence_self_others.md) inversion:
"chúng" is cheapest and closes the loop; existence makes it *matter*; the self's new dimensions are
the largest work and are sharpened by both.

**F3 and X1 stay first** regardless of product direction — they are the *cheap now / archaeology later*
rows from [27 §11.6](27_extensibility_stress_test.md).

---

## 7. Questions now closed

| Was open | Closed by |
|---|---|
| [PRD-Q1](28_product_definition.md) — may the world act deterministically? | **Yes** — [EXC-F3](30_exchange_model_and_dataflow.md), when a ledger cannot balance. R01 amends DL-A1/D1 to permit it |
| [PRD-Q2](28_product_definition.md) — smallest world-acting mechanic | **WSA-R17**, the balancing cell |
| [PRD-Q3](28_product_definition.md) — does the PC spend time? | **Yes, required** — [EXC-A2](30_exchange_model_and_dataflow.md); R16 |
| [ONT-Q1](29_ontology_existence_self_others.md) — what does opinion gate? | **Capability derivation** — [EXC-A4](30_exchange_model_and_dataflow.md); R15 |
| [XST-F9](27_extensibility_stress_test.md) — closed 10 slots? | **No** — R02, on ontology grounds, not performance grounds |
| [EXC-Q2](30_exchange_model_and_dataflow.md) — is knowledge a fourth currency? | **No** — WSA-A1 generalises the imprint's *object* |

## 8. Still open

| # | Question |
|---|---|
| **WSA-Q1** | **Is `relation` (ownership, membership, title) a fourth state kind or a degenerate imprint?** [EXC-Q2](30_exchange_model_and_dataflow.md) carried forward — WSA-A1 absorbed *knowledge* but not *edges with no magnitude*. |
| **WSA-Q2** | **Where does the ledger assertion run** — in-loop per commit, or a Class C audit sweep? [EXC-Q3](30_exchange_model_and_dataflow.md) carried forward; unmeasured. |
| **WSA-Q3** | **How does the standing fold stay fresh enough?** WSA-A4 makes it eventually consistent. How stale may standing be before the fiction breaks — and is staleness observable to a player? |
| **ONT-Q2** (carried) | What counts as "meaningful interaction" for R06's promotion trigger, and how is promotion-farming prevented? |

---

## 9. Cross-references

* [`28_product_definition.md`](28_product_definition.md) · [`29_ontology_existence_self_others.md`](29_ontology_existence_self_others.md) · [`30_exchange_model_and_dataflow.md`](30_exchange_model_and_dataflow.md)
* [`27_extensibility_stress_test.md`](27_extensibility_stress_test.md) · [`27a_stress_test_agent_reports.md`](27a_stress_test_agent_reports.md)
* [`26_implementation_architecture.md`](26_implementation_architecture.md) — code/config line, module boundaries
* [`13_simulation_loop.md`](13_simulation_loop.md) SL-A12 · [`14_sim_core_spec.md`](14_sim_core_spec.md) preconditions/outcomes
* [`19_reconciliation_register.md`](19_reconciliation_register.md) — the existing register this one parallels
