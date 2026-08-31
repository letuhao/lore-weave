# Command and interaction structure — the substrate under verbs, effects and refusal

**Status:** DESIGN — **`CMD-1`..`CMD-6` and `CMD-10` are SEALED by the PO 2026-08-06**; `CMD-7`..`CMD-9` and `CMD-11`..`CMD-13` are not

> ⚠️ **This line said *"awaiting PO review"* while six of this document's decisions were already
> sealed and built on.** Corrected 2026-08-06 while surveying what remained unsealed — a status
> line is a claim like any other, and this run has now caught the same stale-claim shape in a
> register, a heading, a doc comment and here. `CMD-11`/`CMD-12` are PARKED (the offer registry
> waits on the subject source); `CMD-13` and `O-CI-23`..`O-CI-25` were RE-HOMED to the ruleset
> builder by `SCOPE-3`. · **Date:** 2026-08-02 · **Base:** `50bff49a4`
**Run state:** [`docs/plans/2026-08-02-command-interaction-RUN-STATE.md`](../plans/2026-08-02-command-interaction-RUN-STATE.md) — the measurement is §5 there and is not repeated here in full.
**Sibling:** [`2026-08-02-actor-data-structure.md`](2026-08-02-actor-hub/analysis/2026-08-02-actor-data-structure.md) + [`2026-08-02-actor-dataflow.md`](2026-08-02-actor-hub/analysis/2026-08-02-actor-dataflow.md). Their decisions `D-1..D-75` are **inherited and not re-opened**.

> **⚠ READ THIS FIRST — 2026-08-02, after the PO checkpoint.** This document is the **decision
> record**; [`2026-08-02-command-interaction-dataflow.md`](2026-08-02-command-interaction-dataflow.md)
> is the **reasoning, the prior art and the open register**. Where the two disagree, **the dataflow
> spec wins.**
>
> **Sections superseded since this file was written:** **§4.1** (the engine-closed four-role set is
> **withdrawn** — `CMD-7`: roles are author-declared, with an engine-closed *flag* set; dataflow §3)
> · **§4** (the verb row gains `considerations`, `success` and `attack_class`, and `costs` is
> renamed `spend` — `CMD-9`; dataflow §4) · **§6** (an eighth primitive, risk, and it has a real
> door; dataflow §2.3) · **§11** (`A-1`..`A-7` are adjudicated in dataflow §5 — two resolved, five
> confirmed).
>
> 🔴 **§2's classification test is WITHDRAWN — it cannot fail.** *"If the author would be choosing
> from a set the engine defines, it is vocabulary"* **passes `CommandKind`**, the thing this round
> exists to demolish. Replaced by dataflow §9's three-question test (`V1` extension · `V2`
> non-interference · `V3` identity-blindness), which fails on six real cases including two proposals
> from this round.
>
> **`CMD-1`..`CMD-6` are NOT sealed.** The PO declined to seal on the argument as written and was
> right to: the whole decision layer (dataflow §2) was missing from this document, and the test that
> would have justified sealing was vacuous.

**Scope.** How a verb is declared, identified, bound, required, adjudicated, applied, refused and
presented. **Which** verbs a reality has is authored content, not this design. Combat vocabulary
is out (`D-14`); the trigger mechanism is out (`D-9`).

---

## 1. What this settles, and the failure it is measured against

The actor round found three designs of one concept and no code. This layer is worse: it has
**four** designs, no code, **and** a running implementation that closes on the exact axis all four
designs say is open.

| | `PL_002` §2 | `PL_005` §2 | shipped `payload.rs` | shipped `vocabulary.rs` |
|---|---|---|---|---|
| verb identity | `CommandKind` — closed enum of 5 | `InteractionKind` — closed enum of 5 | `CombatPayload` — closed enum of 5 | a **name** loaded from JSON |
| target | — | `TargetRef` closed, *"V2+ adds Concept, Faction, Relationship"* | `EntityId` | an **offered candidate** list |
| effects | typed `CommandArgs` per variant | `OutputDecl { aggregate_type: String, delta: Value }` | `CombatEvent` — closed enum of **8** | — |
| binding | one `§6` contract section per command | — | — | a `match tool_name` with one arm per verb |

Nine type names from the two design docs — `CommandKind`, `InteractionKind`, `ToolCallAllowlist`,
`InstrumentRef`, `TargetRef`, `ProposedOutputs`, `OutputDecl`, `ExamineTarget`,
`tool_call_allowlist` — return **zero hits** across `crates/`, `services/` and `migrations/`. 2,602
lines of design, no referent.

**The cost, counted rather than estimated.** Ten non-test source files across two languages name
the verb vocabulary, plus ten test files. **Adding `cast` to this engine today is a 10-file,
2-language edit.** Under `D-30` it must be one manifest row.

### 1.1 The concrete failure, and it is one function wide

[`vocabulary.rs:1-4`](../../services/commit-service/src/vocabulary.rs#L1) states the correct
principle and claims it is enforced:

> *"data, not code: one declaration serves the model as tool schemas AND commit-service as the
> validation set; **a drift between the two is impossible because there is only one file**."*

That is true of the tool **names** and false of the **binding**. `contains()` ([:77](../../services/commit-service/src/vocabulary.rs#L77))
answers from the loaded JSON. `validate()` ([:105](../../services/commit-service/src/vocabulary.rs#L105))
answers from a hardcoded `match tool_name` whose fallthrough is `other => Err(UnknownTool)`. Add a
fifth tool to `combat_v1.json` and:

```
contains("cast")            → true                      // the declaration says it exists
validate(…, "cast", …)      → Err(UnknownTool("cast"))   // the binding says it does not
```

**Two answers to one question, one function apart, in the file whose header says that cannot
happen.** It is latent rather than live only because the JSON carries exactly the four tools the
`match` has arms for — kept in step by hand, which is the drift the header calls impossible.

This is the command layer's `law.rs:218`/`225`: the seam declared, and the next statement closing it.

### 1.2 The project has already paid for this once

[`turnOutcome.ts:97-115`](../../services/game-server/src/wire/turnOutcome.ts#L97) records, in the
source, that a new event type without `turn_number` threw out of the replay and **killed a
channel's whole projection, for every client, permanently** — replay meets the same event again on
every retry. `ruleset.epoch_activated` was the first, caught by `/review-impl` before it shipped.
The comment states this round's thesis better than this document can:

> *"the writer should not be the only thing standing between a new event type and a dead room."*

## 2. The principle, and where it cuts

> **`D-2`, inherited.** The engine closes on **mechanism**. The manifest closes on **vocabulary**.

| concern | **Mechanism** — engine, closed | **Vocabulary** — manifest, declared |
|---|---|---|
| verb identity | ordinal assignment, append-only, never-reuse, inside the hashed bytes | **which verbs exist**, and their machine keys |
| roles | that a submission binds ROLES to refs, and that arity is validated before anything else runs | which roles each verb takes, their arity, and which ref kinds each admits |
| the pipeline | the stage list and its order (§5) — shared by every verb, not extensible | **nothing.** An author never inserts a stage |
| requirement | the closed set of requirement **kinds** (§7) | which requirements each verb carries, and the refusal reason for each |
| cost | that a cost is an effect committed at a fixed stage | what the cost is |
| effect | the closed **primitive set** (§6) and the arithmetic of each | which primitives a verb proposes, on which role, with what magnitude |
| adjudication | propose → adjudicate → apply, and that a reaction may intervene at the seam (`D-9`) | the reaction vocabulary — **deferred**, shape fixed |
| refusal | that a refusal is a committed fact carrying a stage and a reason ordinal | the reason vocabulary |
| presentation | that a committed fact carries a **cue ordinal** and no prose | which cue, and what every locale renders it as |
| submitter class | the closed set `Player \| Controller \| Engine` | which class may submit each verb |

**The shape is identical to the actor round's in every row: the policy enum is closed, the
assignment of a policy is declared.** The test for a new concern is `§27.1`'s — if the author would
choose *from a set the engine defines*, it is vocabulary; if they would define *the set*, stop.

### 2.1 Three levels, not two — `§27.1` applied here

| level | who | here |
|---|---|---|
| **KIND** | engine, closed | *"a verb has roles, requirements, costs, effects and a cue; effects are drawn from seven primitives"* |
| **RECORD** | the feature | what one `verb_declaration` row contains |
<!-- doc-language-gate: ok -- genre terminology and cited corpus spans. CLAUDE.md allows non-English where the text IS the subject matter: domain terms with no English equivalent (glossed in English on first use) and spans quoted from the corpus. The exposition around them is English. -->
| **MEMBER** | the author | `bái_sư` (kowtow to take a master), `song_tu` (paired cultivation between two actors), `/meditate` |

Conflating KIND with RECORD is what produced `OutputDecl { aggregate_type: String, delta: Value }` —
a record shape so open it hands schema authority back to whoever writes the string.

## 3. Prior art, and what each system decides for us

Six systems, chosen because each has shipped the *"add a verb without rebuilding"* problem and
survived it. None was consulted before the measurement, so agreement is evidence rather than
anchoring.

| system | what it did | what it decides here |
|---|---|---|
| **The Sims** — smart objects / affordances | interactions and their effects are defined **on the objects**, not in the Sim's logic; objects *advertise* what can be done with them, so new objects and interactions are added without touching the actor | **the engine must not hold the verb list.** The most direct confirmation of `D-2` at this layer, from the game that made it famous |
| **Unreal GAS** | `GameplayEffect` is a **data-only** asset configured by variables, never subclassed; requirements are `GameplayTag` sets (`ActivationRequiredTags`, `ActivationBlockedTags`, `ApplicationTagRequirements`, `OngoingTagRequirements`); **cost and cooldown are themselves GameplayEffects** applied by `CommitAbility()`; modifier ops are the closed set `Add · Multiply · Divide · Override` | **cost is not special** — it is an effect at a fixed stage (§5, stage 4). And a tag-set requirement is `D-29`'s declared threshold under another name: a **bit test**, not a grammar |
| **Inform 7** | action processing runs a fixed rulebook sequence — `Before · Instead · Check · Carry Out · After · Report`. **`Before`/`Instead`/`After` are SHARED across all actions; `Check`/`Carry Out`/`Report` are PER-ACTION** | **the stage list is engine-closed and shared; what happens in a stage is declared per verb.** Two decades of shipping, arrived at independently. This is `CMD-2` |
| **Caves of Qud** | an ECS where components are *"parts"*; a new object combining existing parts is *"a small XML snippet"*; `ObjectBlueprints.xml` supports `Load="Merge"` against an existing definition | **a verb declaration must merge, not replace** — which is the actor round's S1 layered fold (`engine_default → preset → book → reality → forge_override`) already |
| **Evennia** (MUD) | commands live in **cmdsets** collected from session (−20), account (−10), object (0), merged in priority order; a higher-priority set overrides a same-named command | **layered command availability is a solved shape**, and it is the same fold. It also gives the *context overlay* (§5 of the actor dataflow) a second independent confirmation |
| **Deterministic lockstep** (AoE, *1500 Archers*) | the network transmits **commands, not state**; a recording replays the commands and is guaranteed to reproduce the game | **a command is data by necessity, not by taste.** If the verb is code, the log is unreplayable — which the corpus already requires (`D-36`: two SSOTs, the log is one) |

**The convergence worth naming:** four of the six put the verb's *definition* outside the engine
and keep only the *pipeline* inside. The two that did not — Inform's shared rulebooks and lockstep's
fixed tick — kept exactly the part this design also keeps: **the order of operations.**

## 4. The verb — a declared row

> **`CMD-1`.** A verb is a declared row with an ordinal, in the hashed bytes, append-only, never
> reused. `CommandKind`, `InteractionKind` and `CombatPayload` are the same rot at three levels,
> exactly as `Actor.hp` / `VitalKind` / `StatSlot::MaxHp` were.

```
verb_declarations [
  key:             MachineKey          // ordinal = index. Append-only. Hashed. Never reused.
  roles:           [RoleSpec]          // §4.1 — arity + admitted ref kinds, per role
  requires:        [RequirementRow]    // §7 — evaluated at stage 3
  costs:           [EffectRow]         // §6 — committed at stage 4
  effects:         [EffectRow]         // §6 — proposed at stage 5, applied at stage 6
  cue:             CueOrdinal          // §9 — presentation, carries no prose
  submitter_class: Player | Controller | Engine
]
```

`submitter_class` is **not invented here** — it is generalised from `CombatPayload::EndTurn`, whose
comment already states the property: *"Submitted by the HOST, never reachable from the tool
vocabulary, so no driver (player, LLM or script) can mint itself another action by asking for one."*
That distinction exists in code, for one payload, by hand. It becomes a column.

### 4.1 Roles — `PL_005`'s best idea, kept and narrowed

`PL_005`'s 4-role pattern — **agent · instrument · direct target · indirect target** — is the right
decomposition and survives. What does not survive is `TargetRef` and `ExamineTarget` as closed enums:

```
RoleSpec {
  role:       Agent | Instrument | DirectTarget | IndirectTarget   // ENGINE-CLOSED
  arity:      Exactly(n) | AtLeast(n) | Range(n, m) | Absent
  admits:     RefKindMask        // which declared ref kinds may bind here
  from:       Offered | Any      // THR-A4 — must the engine have offered it?
}
```

**`ExamineTarget` dissolves.** It exists only because `Examine` needed a wider target set than
`Strike` and the shared enum could not express *"wider for this verb only"*. A per-verb `admits`
mask expresses exactly that, and the `V1+ may collapse into a 5th variant` note in `PL_005:53`
stops being a plan.

**`from: Offered` generalises `THR-A4`**, which is today implemented inside the `"strike"` arm of
`vocabulary.rs` and nowhere else. Every verb that names an actor should have it; only one does.

### 4.2 The ordinal space — and this is `C-3`, stated not settled

Verbs need `QTY-A5`'s never-reuse discipline: a log entry naming verb ordinal 7 must mean the same
thing forever. Two options, and **§27.4 already priced one of them**: opening a new ordinal space
costs a guard that `O-65`/`T0-4` must maintain, which is why the modifier-layer set was kept
engine-closed rather than becoming a fifth space.

- **Share the quantity space** — free guard, but `MAX_DECLARED_QUANTITIES = 32` is nowhere near
  enough for verbs, and raising it is `O-97`'s *engine capability width* problem.
- **A separate verb space** — correct sizing, one more never-reuse subject to guard.

**Recommendation: a separate space, sized independently**, and the guard is the same
`check_never_reused` routine `activate_reality_epoch` already runs (`D-45`) — so it is a second
*subject*, not a second *mechanism*. Recorded as `C-3` for the PO.

## 5. The pipeline — engine-closed, shared by every verb

> **`CMD-2`.** The stage list and its order are mechanism. What happens **in** a stage is declared
> per verb. This is Inform 7's shared-versus-per-action split, and it is the whole extensibility
> property.

| # | stage | shared / per-verb | status today |
|---|---|---|---|
| **0** | **Admit** — rate limit, authenticate, stamp the actor from the session | shared | ✅ shipped — [`ChannelRoom.submit`](../../services/game-server/src/rooms/ChannelRoom.ts#L250), and the confused-deputy guard is already correct |
| **1** | **Parse** — text or tool-call → `(verb ordinal, raw role bindings)` | shared | ◐ half — the tool-call path exists; the classifier is `PL_002` §7 and unbuilt |
| **2** | **Bind** — resolve refs; enforce `arity`, `admits`, `from: Offered` | shared | ◐ hardcoded for `strike` only |
| **3** | **Require** — evaluate declared requirements; refuse with the declared reason | per-verb declaration, shared evaluator | ❌ absent |
| **4** | **Cost** — commit the declared costs | per-verb declaration, shared evaluator | ❌ absent |
| **5** | **Adjudicate** — proposed effects → actual effects; **the `D-9` reaction seam is here** | shared | ◐ `PL_005`'s proposed→actual is designed, unbuilt |
| **6** | **Apply** — fold effect rows through the substrate's existing doors (§6) | shared | ◐ `law.rs`, hardcoded per verb |
| **7** | **Record** — commit atomically, one `seq` (`D-50`) | shared | ✅ shipped |
| **8** | **Present** — emit the cue ordinal; the client decides words (§9) | shared | 🔴 shipped **wrong** — `renderEvent`'s switch |

**Why the order is not negotiable, stated so nobody re-litigates it:** requirements must be
evaluated before costs are committed, or a refused verb has already spent; costs must commit before
adjudication, or a reaction can be paid for twice; adjudication must precede apply, or `D-5`'s three
layers fuse again. Each adjacency is load-bearing.

**GAS's contribution is stage 4 existing at all.** *"Spend 20 qi to cast"* is not a special case in
the verb's logic — it is an ordinary effect row, committed at a fixed point, by the same evaluator
that runs stage 6. One mechanism, used twice.

## 6. Effects — the closed primitive set, and how it is closed non-arbitrarily

> **`CMD-3`.** An effect is a **row** drawn from a closed primitive set, never executable logic.
> `D-27` at the verb layer.

This is the round's real difficulty (`C-1`). The actor round's decoupling works because its shared
shape is **arithmetic** — fold numbers into `values[]`. A verb's effects are not all arithmetic:
`give` moves an edge, `speak` calls an LLM, `sleep` advances fiction time. One `ModifierRow` will
not carry all of them.

**The rule that closes the set without arbitrariness:**

> **A primitive exists if and only if the actor substrate already built the door it goes through.**
> A verb may not cause something the substrate has no door for.

That is not a convenience. It is what keeps the set finite, keeps every effect replayable, and makes
the set's growth a *substrate* decision rather than a *content* one.

| # | primitive | what it does | the door it goes through |
|---|---|---|---|
| **1** | `Delta` | change a declared quantity on a role by a magnitude | actor dataflow §4.5 — the delta pipeline, class order, one clamp |
| **2** | `StatusPropose` | propose a declared status on a role | §4.6 — propose → adjudicate → apply, and the wave |
| **3** | `EdgeMove` | re-point a declared relation's endpoint | ⚠ **`commit_with_modifiers`'s feature-row half** (`D-50`) — §12.4 governs *where* the edge lives but is a **rule, not an operation** |
| **4** | `LifecycleRequest` | request a declared transition on a declared axis | §5.8 — validate against the declared set, run the cascade, append to the log |
| **5** | `ClockAdvance` | advance fiction time by N ticks | §5.9 — settling in closed form, which is why `O-20`'s invertibility restriction exists |
| **6** | `Materialise` / `Dispose` | bring an actor into a slot, or free one | §18.3 — the slot table; **disposal is cache eviction, not deletion** (`D-23`) |
| **7** | `Oracle` | a call whose result is **not** computable from the log | ⚠ §11.6 supplies a **classification** (`origin: Recomputable \| Oracle`), not a door. The door is the event log itself |

**Five of the seven have an unambiguous door. Two do not, and saying so is the point.** `EdgeMove`
attaches to a rule and `Oracle` to a classification — neither is an *operation* the actor round
built and named. That is not a reason to drop them (a `give` and a `speak` are the two most ordinary
verbs a reality will have); it is where the closure rule is thinnest, and it is `A-1` with a
concrete subject rather than a worry.

With that stated, the decomposition holds without residue: `give` = 3, `strike` = 1 → 2 → 4,
`sleep` = 5, `speak` = 7 → 1.

### 6.1 The row, deliberately shaped like `ModifierRow`

```
EffectRow {
  primitive: EffectPrimitive        // the closed seven
  role:      RoleOrdinal            // which of the verb's roles it lands on
  target:    Ordinal                // quantity / status / relation / state — per primitive
  magnitude: i32                    // fixed point 1e-4 (D-52), one scale everywhere
  condition: Option<ThresholdOrd>   // D-29 — a bit test, never a grammar
  origin:    Recomputable | Oracle  // §6.2
}
```

The resemblance to `ModifierRow` is the point, and it is the same argument `§13.6` made for fold
order: **a modifier, a delta and an effect are one thing seen at three times** — a modifier changes
what a value *would be*, a delta changes it *now*, an effect *causes* one of those. Three row
shapes for one concept would be the defect this corpus keeps finding under other names.

### 6.2 `origin` belongs on the EFFECT, not on the verb — `C-2` resolved

The tempting placement is a flag on the verb: *"`speak` is non-deterministic."* It is wrong, and one
example settles it: **`speak` emits an Oracle narration AND a deterministic opinion delta.** A
per-verb flag would force the whole verb to the non-recomputable path and make the deterministic
half unreplayable for no reason.

So: `origin` is per effect row. An `Oracle` effect's **result is recorded**; a `Recomputable`
effect's result is re-derived. This is `§11.6`'s decision — *the flag lives on the Decision, so
replay needs no binding history* — applied one level down, and it inherits that section's guarantee
that an Oracle result may never be recomputed.

### 6.3 What this refuses, said out loud

A verb **cannot**: run arbitrary code · read another feature's table · call a service directly ·
loop · branch on anything but a declared threshold · emit prose. If an author needs one of those,
either a primitive is missing — which is a substrate question, with a door to build — or the design
is telling us the thing is not a verb.

## 7. Requirements — declared thresholds, and no predicate grammar

> **`D-29`, inherited.** A condition is a declared threshold, never a predicate grammar. A grammar
> with nesting is a scripting language, which is `CPL-A17` violated by the mechanism meant to
> honour it.

```
RequirementRow {
  kind:    ThresholdActive | ThresholdInactive | QuantityAtLeast
         | StatusPresent   | StatusAbsent      | RoleBound | Capability   // ENGINE-CLOSED
  subject: RoleOrdinal
  ref:     Ordinal
  reason:  ReasonOrdinal       // what refusal is recorded when this fails
}
```

Every one is a **bit test or a comparison** against state `ActorQuantities` already holds:
`threshold_active` and `status_active` are in the hot struct precisely so this costs one AND.

**GAS reached the identical shape from the other end.** `ActivationRequiredTags` /
`ActivationBlockedTags` / `ApplicationTagRequirements` / `OngoingTagRequirements` are four tag-set
tests — a hierarchical label matched by presence, which is a declared threshold under another name.
Two systems, no contact, one answer.

**`reason` per requirement is what makes refusal useful.** *"You cannot"* is not a game; *"you are
not yet a disciple of this sect"* is. The reason is an ordinal, so the message is the author's and
the locale is the client's.

## 8. Refusal is a fact, not a dropped submission

> **`CMD-5`.** A refusal is committed, carrying the stage that refused and a declared reason
> ordinal.

Half-built already: `proposal.rejected` exists and `EVT-V4` correctly does **not** advance the turn
on a rejection. What is missing is the shape of the reason. Today `RejectDetail` carries
`{ stage: string, user_message: string }` — a free string, produced server-side, in one language.

```
RefusalFact {
  verb:   VerbOrdinal
  stage:  StageOrdinal      // §5's closed list — WHERE it refused is diagnostic
  reason: ReasonOrdinal     // declared vocabulary; the client renders it
}
```

`stage` is worth its byte: *refused at Bind* is a client bug, *refused at Require* is gameplay, and
*refused at Adjudicate* is a reaction. Today all three arrive as the same opaque string.

**And `O-10`'s discipline binds here:** a refusal is **recorded**, never silent. The corpus has
already spent a section establishing that a degrade path absorbing a failure and reporting success
is this codebase's recurring defect — `payload.rs`'s `capped` field exists because of the third
occurrence.

## 9. Presentation is a separate channel

> **`CMD-4`.** A committed fact carries a **cue ordinal** and no prose. The client decides words.

[`turnOutcome.ts:182`](../../services/game-server/src/wire/turnOutcome.ts#L182) already states the
rule — *"the SERVER ships facts, the client decides words (and, later, locale — CWC-D7)"* — and then
`renderEvent` violates it in the same file with a `switch` that formats English for each verb. Add
a verb and you edit that switch; add a locale and you cannot.

GAS separates `GameplayCue` from `GameplayEffect` for exactly this: the mechanical change and its
presentation are replicated independently, and a cue is addressed by tag rather than by a branch.
Ours is the same split with an ordinal in place of the tag.

This is the **cheapest** of the six proposals to implement and the one that pays twice — it removes
a per-verb edit site and it is the i18n mechanism the comment already anticipated.

## 10. Rot ledger

`U` = update, `D` = delete. Sites are line-accurate against `50bff49a4`.

| id | site | action |
|---|---|---|
| C-1 | [`PL_002:37`](../03_planning/LLM_MMO_RPG/features/04_play_loop/PL_002_command_grammar.md#L37) — `enum CommandKind { Verbatim, Prose, Sleep, Travel, Help }`, *"V1 closed set of 5"* | **D** — replaced by a declared verb ordinal |
| C-2 | `PL_002:132`, `PL_002:581` — *"V1 closed set: 5 commands"* and the `parse.unknown_command` copy listing them | **U** — unknown means *not declared by this reality*, and the list is per-reality |
| C-3 | `PL_002:382` — *"the server-side grammar is the closed set in §6"*, macros refused | **U** — a macro is a verb whose effects are other verbs, which is re-entrancy and belongs with `O-10`'s budget, not with a flat refusal |
| C-4 | `PL_002:5` — the amendment adding `/chat` + `/leave`, asserting *"NO change to closed-set vocabulary discipline; commands are additive per I14"* | **U, and keep the history.** This row is the evidence: two commands cost a doc amendment, two enum variants and two typed payloads. *Additive* is doing work the mechanism does not support |
| C-5 | [`PL_005:49`](../03_planning/LLM_MMO_RPG/features/04_play_loop/PL_005_interaction.md#L49) — `InteractionKind` closed enum of 5 | **D** — replaced by a declared verb ordinal. The `V1+ extensions … ADDITIVE per I14` note goes with it |
| C-6 | `PL_005:52` — `TargetRef` closed enum, *"V2+ adds: Concept, Faction, Relationship"* | **U** — a `RefKindMask` per role. **An enum whose extension plan is written into the doc is vocabulary wearing a mechanism's clothes** |
| C-7 | `PL_005:53` — `ExamineTarget`, an Examine-only target discriminator | **D** — dissolves into §4.1's per-verb `admits` mask |
| C-8 | `PL_005:56` — `OutputDecl { target, aggregate_type: String, delta: serde_json::Value }`, and `PL_005b`'s *"OutputDecl taxonomy"* | **U** — the free-string escape hatch, and the clearest case of KIND conflated with RECORD (§2.1). Becomes §6.1's `EffectRow` over the closed primitive set |
| C-9 | `PL_005b:262` — *"StrikeIntent=Disarm/Stun/Restrain rejected V1 (V1+ extensions)"* | **U** — three refusals that exist only because the enum was closed |
| C-10 | [`payload.rs:5`](../../services/commit-service/src/domain/payload.rs#L5) — *"both are closed sets for the same reason"* | **U** — record that the reason lapsed with `D-2`, and that this was a decision rather than an oversight |
| C-11 | [`vocabulary.rs:1-4`](../../services/commit-service/src/vocabulary.rs#L1) — *"a drift between the two is impossible because there is only one file"* | **U — the claim is false of the binding.** Correct the header, then fix the binding (`CMD-6`) |
| C-12 | [`turnOutcome.ts:182`](../../services/game-server/src/wire/turnOutcome.ts#L182) — `renderEvent`'s per-verb switch | **U** — contradicts its own docstring two lines above. §9 |
| — | `PL_005:568` — five inconsistent `MapKind` ladders as *"the strongest evidence that the enum was never load-bearing"* | **KEEP, and cite it.** The corpus made this argument once and did not generalise it |

## 11. Where this design is most likely wrong

Written for the red team, by the author, before they arrive.

| # | the attack surface |
|---|---|
| **A-1** | **§6's closure rule may be circular, and it is already strained.** *"A primitive exists iff the substrate already built the door"* is clean — but the actor round built its doors without commands in mind, and **two of seven primitives fail the rule as written**: `EdgeMove` attaches to a *rule* (§12.4) and `Oracle` to a *classification* (§11.6), neither of which is an operation. Either the rule needs weakening — at which point it stops closing the set — or two doors need building. This document does not say which, and gives no test to tell *a missing door* from *a missing primitive*. |
| **A-2** | **`Oracle` inside a replayable log.** §6.2 records the result so replay works — but the actor round distinguishes **two** replays (§6.1), and only one of them is a re-fold. Recording the result serves the fold; it does not obviously serve re-simulation. Nobody has checked this survives both. |
| **A-3** | **Parse is outside the engine's closure and decides the verb ordinal.** §5 stage 1 is shared, but the *classifier* is not in the digest. A model change silently changes which verb fires for the same text — a rules-provenance hole with the same shape as `A-1` in the actor spec, and it is not covered by `RulesPin`. |
<!-- doc-language-gate: ok -- genre terminology and cited corpus spans. CLAUDE.md allows non-English where the text IS the subject matter: domain terms with no English equivalent (glossed in English on first use) and spans quoted from the corpus. The exposition around them is English. -->
| **A-4** | **The role set is asserted closed** (§4.1) with no argument. Four roles came from `PL_005`, which derived them from five verbs. A verb with a beneficiary distinct from its target (*"I pay Lão Ngũ for Tiểu Thúy's room"*) may need a fifth, and `D-2` then says the role set is vocabulary and §4.1 is mis-classified. |
| **A-5** | **§4.2 recommends a fifth ordinal space** while `§27.4` refused a fifth space for modifier layers on the grounds that `O-65`/`T0-4` would have to guard it. The recommendation argues it is a second *subject*, not a second *mechanism* — that distinction is asserted here and was not accepted there. |
| **A-6** | **Stage 4 commits cost before stage 5 adjudicates.** GAS does this and it works there because refusal happens at `CanActivateAbility`, before `CommitAbility`. Ours has a reaction seam (`D-9`) *after* the cost. So either a reaction can refuse a verb whose cost is spent — and something must roll it back, which `D-50`'s one-transaction shape does not obviously permit — or reactions cannot refuse, which weakens the seam this round exists to protect. **This is the sharpest edge and the author knows it.** |
| **A-7** | **The whole design assumes verbs are the unit.** `PL_002`'s `/sleep` and `PL_005`'s `Speak` are not the same kind of thing: one is an out-of-fiction control, the other is an in-fiction act. Treating them as one declared table may be a unification as false as `LifecycleState` fusing residency with existence. |

## 12. What needs the PO

| # | question |
|---|---|
| **PO-1** | **Seal or amend `CMD-1`..`CMD-6`.** Six proposals; none is sealed. `CMD-6` is the only one with a live subject. |
| **PO-2** | **`C-5` — is the role set engine-closed or declared?** (§4.1, attacked at `A-4`.) A value judgement about how much authoring surface a role deserves, not an engineering one. |
| **PO-3** | **`C-7` — timing.** `CMD-6`'s binding fix is small, in-scope, root-cause-clear and independent of the rest of the design. The defer gate says *fix now*; the round says *no code*. Which wins is the PO's call. |
| **PO-4** | **Does this round produce a dataflow companion?** The actor round's two-document shape (decisions + reasoning with measured evidence) cost real effort and caught real defects. Worth repeating here, or is this document enough? |
