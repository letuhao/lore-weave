# 32 — The world is an actor: closing WSA-F1 and WSA-F2

> **➤ CONTINUED 2026-07-30 by [`36_map_architecture.md`](36_map_architecture.md) (`SPG-*`) — the converse
> and the container.** This doc established `WSA-A7`: *a locus is both an entity and an actor*. Doc 36
> states the other half — **an entity may HOLD an interior, and interiors form a typed graph**
> (`SPG-A1`) — so the two together close the circle: *entity* and *space* are one kind of thing seen from
> outside and from inside. Where 32 asked *"can a place act?"*, 36 asks *"what is a place made of, what
> may it contain, and where is it?"*
> Doc 36 **reuses without re-opening**: `WSA-A9`'s existence ladder becomes the lazy-materialization rule
> for interiors (`SPG-A12`) rather than a second ladder; `WSA-A8`'s no-central-world-actor constraint is
> honored (a `Region` is a fold, never a writer); `WSA-F6`'s locus-as-ownable-entity is what lets
> territory change hands by rebinding an ownership relation instead of restructuring the containment
> tree. `WSA-F5(c)`'s unmeasured cost of acting loci is **carried forward unchanged** as `SPG-Q6`.
> **⚠ STATUS CORRECTED 2026-07-30 (REC-98) — this line read *"`WSA-R19..R24` are still PROPOSED, not applied"* and was FALSE for three of the six rows it covered.** Verified by opening each target rather than trusting this sentence: **`WSA-R21` APPLIED** (`NPC_001_cast.md:67` — *"`Locus` ADDED 2026-07-30 (`WSA-R21`; boundary review + lock claim)"*); **`WSA-R22` APPLIED** (`ACT_001:205` — *"Out-of-world actors forbidden V1 (ACT-A7) — NARROWED 2026-07-30 (`WSA-R22`)"*); **`WSA-R19` was HALF-APPLIED** — `EF_001` §5 declared `Place(PlaceId)` while four statements around it still said four variants, now finished. A blanket status line over six rows is the shape that goes stale silently, because nothing has to be true of all six for it to keep reading plausibly. **`WSA-R20`, `R23`, `R24` remain PROPOSED** — as this doc recorded. `SPG-R10` **depends on
> `WSA-R19`**: `EntityId::Place` (32) and `SpaceNode.holder` (36) are the same seam, so they must land in
> one pass. Both sets are registered in the ownership matrix as of 2026-07-30, together with a backfill
> of six prefixes — **including this doc's own `WSA-*`** — that docs 27–35 introduced and never
> registered. Annotation only; nothing sealed here is re-litigated.

> **Status:** SEALED 2026-07-28 (DESIGN). Continues the `WSA` prefix from
> [31](31_world_simulation_architecture.md) deliberately (axioms `WSA-A7..A11`, findings
> `WSA-F4..F6`, decisions `WSA-D2..D3`, amendment rows `WSA-R19..R24`, open `WSA-Q4..Q5`) — this is
> the same architecture answering its own two open findings, not a new subject.
>
> The PO's proposition, against [31 §1](31_world_simulation_architecture.md)'s two named gaps:
>
> > *"WSA-F1, WSA-F2 — tôi nghĩ là có lời giải: **world chính là 1 actor**."*
>
> **Verdict: it closes WSA-F2 almost completely and WSA-F1 substantially, and the corpus already
> contains the seam it needs.** The precise form is not *"the world is an actor"* but something
> slightly different, and the difference is what keeps it compatible with single-writer islands (§3).
> §6 states what it does **not** solve.
>
> 🔒 **SEALED** means the *reasoning* is closed and must not be re-litigated from memory — re-read it. Open questions listed in this file remain open, and the amendment rows are **PROPOSED, not applied**: no feature spec was edited by this arc.


---

## 1. The seam already exists — and so does a drift that proves the idea was already wanted

Three overlapping identity enums exist today, with **different variant sets**:

| Enum | Variants | Purpose (EF_001 §5.1) |
|---|---|---|
| `EntityId` | `Pc · Npc · Item · EnvObject` — *"closed V1; new variants require lock-claim + boundary review"* | **things in the world** (addressable, actable-upon) |
| `EntityRef` | `Actor · **Cell(ChannelId)** · Item · **Faction**` | ownership + cascade semantics (RES_001) |
| `ActorId` | `Pc · Npc · **Synthetic { kind }** · Admin` | *"actors with **turn-submission capability**"* |

EF_001 states the `EntityId`/`ActorId` split is deliberate and must not collapse, because *"collapsing
would corrupt either 'things in the world' or 'agents that submit turns' semantics."* **That
distinction is exactly right, and it is what makes the PO's idea precise rather than loose.**

Two facts make this more than a coincidence:

* **`ActorId::Synthetic { kind: SyntheticActorKind }` already exists** — the turn-submission surface
  already admits an actor that is not a person. The mechanism the proposition needs is built.
* **A cell is already an entity in two of the three enums**, and `entity_binding.cell_owner` carries
  the comment *"Applies ONLY when `entity_type == EntityType::Cell`"* — **referring to a variant
  `EntityType` does not have** (its four are `Pc · Npc · Item · EnvObject`), with a parenthetical
  admitting *"EF_001 may absorb cell-as-entity in V1+ migration."*

> **WSA-F4 — the corpus has already begun treating a place as an entity, inconsistently, in three
> enums with three different variant sets, and one field's doc-comment references a variant that does
> not exist.** This is [XST-F1](27_extensibility_stress_test.md)'s class exactly: *closed sets grow,
> and the documentation of their closedness rots first.* It is also evidence **for** the proposition —
> people reached for it before it was designed.

---

## 2. WSA-A7 — the precise form: a LOCUS is both an entity and an actor

> **WSA-A7 — a world locus (cell · place · settlement) is BOTH:**
> * an **entity** — addressable, ownable, and it **holds quantities**; and
> * an **actor** — it has a driver and it **submits turns**.
>
> These are the two enums EF_001 already keeps separate, and a locus is simply the first thing to be
> in both.

**But not one world-actor — a population of them.** This is the constraint that makes the idea
survive contact with the architecture:

> **WSA-A8 — there is no single "world actor". There is one locus-actor per island-local locus, plus
> FOLDS at larger scale.** [WSA-A3](31_world_simulation_architecture.md) requires every write to be
> local and unilateral; a centralised world-actor writing into every cell would break single-writer
> ownership across islands — precisely the bug class the whole island design exists to prevent.
>
> A region or a kingdom is therefore **not** an actor that writes. It is a **derived fold** over its
> loci, read locally — the same near/far asymmetry as
> [WSA-A4](31_world_simulation_architecture.md)'s standing fold. **The pattern repeating across two
> unrelated problems is the sign it is the right pattern.**

And the ladder applies unchanged:

> **WSA-A9 — loci get existence tiers exactly like actors do.** An unvisited cell is *Untracked* — a
> pure function of its seed, costing nothing. A cell the player has invested in is *Major* — stateful,
> and it **acts**. This is AIT_001's tiering applied to places, reusing the mechanism rather than
> inventing a second one, and it is what keeps the cost bounded (§6(c)).

The result is a single coherent model rather than four parallel ones: **one actor model, one turn
model, one transaction model, one existence ladder — applied to people *and* to places.**

---

## 3. This closes WSA-F2 (fields) — including the part I said was unrecoverable

[31 §1](31_world_simulation_architecture.md) conceded that per-cell discrete quantities were
recoverable but **continuous propagation was not**, and proposed declaring diffusion out of scope.
**WSA-A7 recovers it**, and I was wrong to concede it:

| Field phenomenon | Under WSA-A7 |
|---|---|
| fertility, contamination, stores, ambient danger | **quantities owned by the locus-actor** — ordinary resources with a place as owner |
| weather over a region | a **fold** over loci (WSA-A8), read locally, never a global writer |
| **gas / heat / sound spreading between cells** | **a conserved TRANSFER between adjacent locus-actors** — cell A gives 5 heat to cell B |

> **WSA-A10 — diffusion is conserved transfer between adjacent loci.** It is not a new mechanism; it
> is [EXC-L1](30_exchange_model_and_dataflow.md) applied to neighbours. And the physical conservation
> law and the economic one are **the same assertion** — which is a pleasing result rather than a
> coincidence, because both are "value moved, nothing created".

Its honest cost: diffusion needs a **cadence** (it is time-driven, not action-driven), so it is Class C
batch work at a coarse tick, never the 20 Hz hot path — and it requires
[R01](31_world_simulation_architecture.md)'s amendment to DL-D1 (*"evaluated, never ticked"*), which
[EXC-F3](30_exchange_model_and_dataflow.md) already required for other reasons.

> **WSA-D2 — supersede [WSA-D1](31_world_simulation_architecture.md).** Continuous fields are **no
> longer out of scope**; they are *coarse-cadence conserved transfer between locus-actors*. What stays
> out of scope is **sub-cell continuous resolution** (a true fluid lattice inside a single cell) —
> that is a genuinely different substrate and should be refused explicitly.

---

## 4. This closes WSA-F1 (WHEN) — substantially, and by unification rather than addition

[31 §1](31_world_simulation_architecture.md) found the ontology supplies `ON`, `THEN` and `IF` but not
`WHEN`, leaving [XST-R9](27_extensibility_stress_test.md) as required engineering. WSA-A7 changes what
that engineering *is*:

> **WSA-A11 — every WHEN is "some actor took a turn".** The trigger problem and the actor problem are
> the same problem: *"when does X happen?"* is *"who decided X should happen?"*. In a system where only
> players and LLMs decide, nothing happens on its own — which is exactly
> [PRD-F1](28_product_definition.md)'s *"the world is a clock with scenery"*, restated as a
> scheduling fact.

Checked against the concrete triggers WSA-F1 listed:

| Wanted trigger | As an actor's turn |
|---|---|
| on day boundary | the locus-actor's **scheduled** turn |
| threshold crossed (stores hit 0, hunger critical) | the holder gets a turn; its `EngineDriver` evaluates declared rules and proposes — [EXC-F3](30_exchange_model_and_dataflow.md) |
| on enter a place | the **locus-actor** takes a turn (a trap is a place reacting) |
| on death | the dying actor's final turn + its locus's turn |
| **on being struck → reflect 30 %** | the struck actor gets an **interleaved micro-turn** and proposes a transaction |

The last row is the important one, because it produces the bound that
[XST-R9](27_extensibility_stress_test.md) said it needed:

> **A reaction is a turn. Turns are budgeted. Therefore reaction depth is bounded by the turn budget
> that already exists** — no new depth-limiting machinery, no new recursion guard. Priority-passing is
> also how the genre's most-tested rules engines (MTG, Hearthstone) bound the same problem.

**And it avoids the rot [PRD-F2](28_product_definition.md) predicted.** The alternative — a second,
bespoke trigger dialect bolted next to `TrainingRuleDecl.source` — is the `combat.rs` failure mode
arriving through a different door: one hardcoded WHEN per domain, forever. Unifying on turns means
generalising the *one* seam that exists rather than adding a second.

---

## 5. WSA-F6 — the strongest argument is neither of the two findings: it is strategy and economy

The PO's follow-on — *"nơi chốn chính là entity, nó chính là thứ cho cơ chế strategy và world economy
của game"* — is a better justification than §3 and §4 combined, because those close *gaps* while this
unlocks a *genre*.

> **WSA-F6 — a locus that is an entity is the substrate of the entire strategy and economy layer.**
> Everything that makes a world worth competing over requires a place to be an ownable, producing,
> losable **thing**:

| Requires locus-as-entity | Why it is impossible without it |
|---|---|
| **Owning territory** | ownership is a relation to an *entity* ([EXC-A3](30_exchange_model_and_dataflow.md)); a `ChannelId` cannot be owned, contested or inherited |
| **A world economy** | production and stores must have a **holder** for [EXC-L1](30_exchange_model_and_dataflow.md) conservation to mean anything; `RES_001`'s `cell_owner` already gropes for this |
| **Taking and losing ground** | a transfer of an ownership relation between actors — an ordinary transaction, but only if the object is an entity |
| **Places having standing** | *"this village regards you as a benefactor"* is an imprint whose subject is a locus ([WSA-A1](31_world_simulation_architecture.md)) |
| **Strategic scarcity** | a locus produces a *specific* quantity, so **where** something is becomes a reason to act — the whole of strategy |
| **Consequence that outlives the session** | a burnt farm stays burnt because the locus is stateful, which is [ONT-T1](29_ontology_existence_self_others.md) satisfied at world scale |

This also explains WSA-F4's drift constructively rather than as a mistake: `RES_001` needed
`cell_owner`, `EntityRef` needed `Cell`, and both reached past the closed `EntityId` to get it. **The
economy work had already discovered this requirement empirically and worked around the type system.**
R19 is therefore not a new feature — it is recognising a decision the code had already been forced to
make.

And it composes with the rest without a new mechanism: **strategy is the exchange model with loci as
counterparties.** Nothing in [30](30_exchange_model_and_dataflow.md) needs to change.

---

## 6. WSA-F5 — what this does NOT solve

Stated because a proposal that closes two findings and claims no residue is not being examined.

**(a) Reaction ORDER still has to be declared.** Interleaved turns give *an* order; they do not give
the *right* one. The deckbuilder report's Gisela case ([27a](27a_stress_test_agent_reports.md)) shows
two reactions in different orders producing 7 vs 8 — a real, visible difference. So
[XST-R11](27_extensibility_stress_test.md)'s **declared `replacement_priority`** is still required,
and under [XST-F5](27_extensibility_stress_test.md) (order is currently unfalsifiable) it needs a test
that can actually fail.

**(b) Trigger vocabulary becomes SCHEDULING POLICY.** *"What moments exist"* becomes *"who gets a turn,
when, and in what order"*. That is progress — one mechanism instead of two, and the initiative system
already exists — but it is a **transfer of the problem, not its disappearance**, and the new form has
its own hard question (WSA-Q4).

**(c) Cost.** Every locus that acts is an actor in the turn system, and there are far more places than
people. This is affordable only because of WSA-A9's tiering: Untracked loci never take turns, and
acting loci run at a **coarse Class C cadence**, not per-tick. Against
[doc 21](21_architecture_ceilings.md)'s measured ~4 892 commits/s aggregate versus a ~10 commits/s
working target, the headroom is large — **but this has never been measured with loci acting**, and
"there is headroom" is exactly the kind of claim that doc's §7 forbids inferring.

**(d) A live constraint conflicts.** ACT_001 rejects synthetic actors as observer or target of an
opinion (`actor.synthetic_actor_forbidden`). Under [WSA-A1](31_world_simulation_architecture.md) an
imprint's *object* may be a **place** (familiarity, notoriety here) and its *subject* may be a
**settlement** (how this village regards you). So either loci are **not** `Synthetic` — which is the
better answer, since `Synthetic` means out-of-world narrator/system — or that constraint must be
narrowed.

> **WSA-D3 — a locus is NOT `ActorId::Synthetic`.** It needs its own variant. `Synthetic` denotes an
> actor outside the fiction; a village is inside it, can be regarded, and can regard. Reusing
> `Synthetic` would put an out-of-world escape hatch on the critical path of the social layer.

---

## 7. Amendments this adds

| # | Target | Change | Confidence |
|---|---|---|---|
| **WSA-R19** | `EF_001` §5 `EntityId` | add a **`Place`/`Locus` variant** (lock-claim + boundary review, as its own rules require) so a locus is addressable in the *same* enum as everything else | **verified** — currently closed to 4 |
| **WSA-R20** | `EF_001` `entity_binding.cell_owner` doc-comment | references `EntityType::Cell`, **which does not exist** in the four-variant enum. Fix the drift, and record it as a `count-assertions` case | **verified** |
| **WSA-R21** | `NPC_001` §2 `ActorId` | add a **`Locus` variant** (WSA-D3) — *not* reusing `Synthetic` | **verified** |
| **WSA-R22** | `ACT_001` `actor.synthetic_actor_forbidden` | narrow it: it must exclude out-of-world synthetics **without** excluding loci, once R21 lands | **verified** |
| **WSA-R23** ✅ **VERIFIED 2026-08-22 — the gap is real and the MECHANISM in the row is wrong** | `AIT_001` | extend the existence tiering to **loci** (`WSA-A9`) | **VERIFIED by opening it.** `AIT_001` is entirely NPC-shaped: a 2-variant `NpcTrackingTier { Major \| Minor }`, `TierCapacityCaps` at Major≤20 / Minor≤100, deterministic *Untracked NPC* ids. **Loci are not in it.** But extending it as written would put a per-row TIER ENUM on every locus, and that is exactly what [`SDF-R1`](36_map_architecture.md) MEASURED as **92.4× worse at 0.1 % live** — ladder-as-FIELD versus ladder-as-INDEX (doc 41 §2). **`AIT_001` already uses the right mechanism for its own lowest tier and says so:** *"Untracked = **absence** of `actor_progression` aggregate (semantic)"* — absence IS index membership. **So the extension is: a locus's tier is membership in the live set (`T2`), never a column on the node** — which is `SDF-A1`'s *materialization is a STAGE, not a FIELD* reaching the tier that owns tiering. The row survives; the word "extend" was doing the damage |
| **WSA-R24** | [31](31_world_simulation_architecture.md) `WSA-D1` | **superseded by WSA-D2** — continuous fields are back in scope as coarse-cadence conserved transfer; only sub-cell lattice resolution stays refused | **verified** |

The build order from [31 §6](31_world_simulation_architecture.md) is unchanged in sequence, but two
rows gain content: **W6 (the balancing cell)** becomes the first *locus-actor*, and is therefore the
natural proof of this entire section; **E3 (trigger vocabulary)** shrinks from "design a trigger
system" to "design a turn-scheduling policy + a declared reaction priority".

---

## 8. Open

| # | Question |
|---|---|
| ~~**WSA-Q4**~~ | ✅ **RESOLVED in [34](34_when_the_world_runs.md)** — a locus publishes `next_wake`, the fiction-time of its own next threshold crossing, computed in closed form. No tick, no cadence. |
| ~~**WSA-Q5**~~ | ✅ **RESOLVED in [34](34_when_the_world_runs.md)** — **yes**, and DL-D1's zero-cost-cold-cell property survives intact: a locus at equilibrium publishes no wake and costs nothing; only loci **out of balance** cost anything. The village starves unwitnessed, in one event. |
| **WSA-Q1..Q3** (carried) | relation-as-fourth-kind · where the ledger assertion runs · standing-fold freshness |

---

## 9. Cross-references

* [`31_world_simulation_architecture.md`](31_world_simulation_architecture.md) — the layers, write/read rules, reconciliation register
* [`30_exchange_model_and_dataflow.md`](30_exchange_model_and_dataflow.md) — three currencies, EXC-L1, ledger-imbalance-as-trigger
* [`29_ontology_existence_self_others.md`](29_ontology_existence_self_others.md) — existence ladder, the loop
* [`28_product_definition.md`](28_product_definition.md) — the loop, the 4-tuple mechanic model
* [`features/00_entity/EF_001_entity_foundation.md`](features/00_entity/EF_001_entity_foundation.md) — the three identity enums
* [`features/00_place/`](features/00_place/) · [`features/16_ai_tier/AIT_001_ai_tier_foundation.md`](features/16_ai_tier/AIT_001_ai_tier_foundation.md)
