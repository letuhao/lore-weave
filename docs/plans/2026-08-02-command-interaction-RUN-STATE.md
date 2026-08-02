# RUN-STATE — Command and interaction substrate (DESIGN)

> **Read this file FIRST after any compaction**, then `git log --oneline -15`, then continue.
> Never re-derive a sealed decision (§4) from memory — re-read it here.

**Started:** 2026-08-02 · **Branch:** `feat/game-logic` · **Base:** `50bff49a4` · **Size:** L
(files=7 logic=10 side_effects=0 — `workflow-gate.sh size L 7 10 0`)

**Phase:** CLARIFY → DESIGN → REVIEW → **STOP at the PO checkpoint.** No code this round.

**Companion spec:** [`docs/specs/2026-08-02-command-interaction-structure.md`](../specs/2026-08-02-command-interaction-structure.md)

---

## 1. What this round is

Design **how a command and an interaction are represented**, so that adding a verb is a
manifest row rather than an edit across ten source files in two languages.

This is the sibling of the actor round. That round settled *what an actor's data is*; this one
settles *what may be done to it and how that is expressed*. The two share one principle
(`D-2`) and the actor round's conclusions are **inherited, not re-opened** (§4a).

## 2. Standing invariants

1. **English in every persisted artifact** — docs, comments, commit messages, test names.
2. **No code this round.** The deliverable is a spec plus corrections to existing specs.
3. **Do not touch the data-ingest tier** — no glossary-service, knowledge-service, extraction, KG.
4. **Never `git add -A`; never `--no-verify`.**
5. **Rot is deleted, not layered over.**
6. **Do not decide a sealed question again.** §4 is the record; §6 is what is still open.
7. **Every absence claim is measured**, and the command used is recorded in §5. A `grep` that
   returns nothing is evidence; a handoff note that says something is missing is not.

## 3. What is IN and what is OUT

| IN | OUT |
|---|---|
| How a **verb** is declared, identified and bound to engine operations | **Which verbs a given reality has** — that is authored content, not this design |
| The **pipeline** a submission runs: parse → bind → require → adjudicate → apply → record | **Combat vocabulary and the damage chain** (`D-14`, inherited) — the current combat logic will be rewritten |
| The **effect primitive set** — the closed set of things a verb may cause | **The trigger / generator mechanism** (`D-9`, inherited) — this round only guarantees the seam |
| **Requirements / conditions**, and why they reuse declared thresholds | The **LLM proposal path's prompt engineering** — the tool-schema surface is in, the prompting is not |
| **Refusal** as a recorded fact, and its reason vocabulary | **NPC decision-making / Chorus orchestration** — `D-24`'s AI + emotion feature |
| **Presentation** as a channel separate from the mechanical effect | Any implementation |
| A **rot sweep of PL_002 / PL_005 / PL_005b / PL_005c**, measured against code | The relational family (`D-25`/§4.8, handed off) |

## 4. Sealed decisions

### 4a. Inherited from the actor round — NOT re-openable here

These were sealed on 2026-08-02 in
[`2026-08-02-actor-substrate-RUN-STATE.md`](2026-08-02-actor-substrate-RUN-STATE.md). They bind
this round. Re-deciding one is forbidden by §2 rule 6.

| # | what it binds here |
|---|---|
| **`D-2`** | The engine closes on **mechanism**; the manifest closes on **vocabulary**. A hardcoded verb is a manifest that cannot grow. |
| **`D-5`** | Propose → adjudicate → apply are three layers. Fusing them is what makes a reaction unimplementable. |
| **`D-9`** | The trigger mechanism is deferred; every layer must leave a hook. |
| **`D-11`** | The shipped engine is scaffolding and may be broken freely. Zero production realities exist. |
| **`D-14`** | Combat vocabulary is out of scope and will be rewritten. |
| **`D-27`** | **A contribution is DATA, never CODE.** A feature does not run during the tick; it leaves rows and the engine folds rows. |
| **`D-29`** | A condition is a **declared threshold**, never a predicate grammar. |
| **`D-30`** | Adding a feature must touch **zero files** in core. |
| **`D-37`/`D-50`** | Single writer per aggregate; one commit primitive, atomicity as a signature. |
| **§27.1** | Three levels: **KIND** (engine) → **RECORD** (feature) → **MEMBER** (author). |

### 4b. Proposed this round — **DRAFT, awaiting PO**

Numbered `CMD-*` to avoid collision with the actor round's `D-*`. **None is sealed.**

| # | Proposal |
|---|---|
| **CMD-1** | **A verb is a declared row with an ordinal**, in the hashed bytes, append-only, never reused — the same identity discipline as a quantity. `CombatPayload`, `CommandKind` and `InteractionKind` are the same rot at three levels, exactly as `Actor.hp` / `VitalKind` / `StatSlot::MaxHp` were. |
| **CMD-2** | **The pipeline is engine-closed and its stages are shared; what happens at each stage is declared per verb.** Inform 7's split — `Before`/`Instead` shared across all actions, `Check`/`Carry Out`/`Report` per action — is this exact shape, arrived at independently and shipped for two decades. |
| **CMD-3** | **An effect is a row drawn from a closed primitive set, never executable logic.** `D-27` at the verb layer. The primitive set is the genuinely hard part of this round and is enumerated in the spec §6. |
| **CMD-4** | **Presentation is a separate channel keyed by the verb ordinal, never a `switch` in the transport.** GAS separates `GameplayCue` from `GameplayEffect` for this reason; `renderEvent` in `turnOutcome.ts` is the same defect we would otherwise re-ship. |
| **CMD-5** | **A refusal is a committed fact with a declared reason ordinal**, never a dropped submission. Inherited shape from `O-11`; already half-built as `proposal.rejected`. |
| **CMD-6** | **Binding a declared name to an engine operation must be TABLE-DRIVEN, not a `match` arm.** This is what `vocabulary.rs` gets wrong today (§5, finding 4) and it is the narrowest, highest-leverage fix in the whole round. |

### 4c. PO decisions — 2026-08-02, at the CLARIFY/DESIGN checkpoint

| # | Decision |
|---|---|
| **`CMD-1`..`CMD-6`** | **NOT sealed. Sealing deferred pending prior art** — the PO declined to seal on the argument as written and directed a research pass first (`PO-5` below). Recorded as *deferred*, not *rejected*: no proposal was ruled against. |
| **`CMD-7`** | **ROLES ARE AUTHOR-DECLARED.** `C-5` decided **against** this document's recommendation. §4.1's engine-closed four-role set is withdrawn; a reality declares its own roles. **This makes the sixth-ordinal-space cost real and it is accepted.** The design now owes the answer to the objection it raised itself: *the engine must know which role pays the cost*, so role SEMANTICS cannot be fully open even when role NAMES are. Resolving that is a design obligation of this round, not a reason to re-litigate the decision (§2 rule 6). |
| **`CMD-8`** | **`C-7` — the `vocabulary.rs` binding fix is DEFERRED to BUILD.** Gate reason **3** (naturally-next-phase): this round is design-only by the PO's own scoping. **Tracked as `D-VOCAB-BINDING-TABLE-DRIVEN`.** Its wake-up trigger is mechanical and already stated: **the fifth tool added to any `contracts/agent/vocabularies/*.json`** makes `contains()` and `validate()` disagree. A test asserting that disagreement is impossible is the mechanism this row owes per the deferral-gate standard — a prose row is not enough. |
| **`PO-4`** | **The dataflow companion is FULL** — the actor round's shape repeated in full, including the author-agent rounds. |

#### 🔴 `PO-5` — the gap the PO found, and this spec has no place for it

> *"Instead of sealing early, go check the assumptions. How do other games design this — especially
> the tactical line, where the AI weights decisions, where every decision has a cost, a reward and a
> penalty, and where there is also a rock-paper-scissors."*

**This is a real hole and the document does not merely under-specify it — it has no slot for it at
all.** `verb_declarations` (spec §4) carries roles, requirements, costs, effects, a cue and a
submitter class. Nothing in that row lets a chooser ask *"which of my legal verbs is the good one
here?"*, and nothing anywhere expresses *"verb A beats verb B"*.

Three distinct things are missing, and conflating them would be the next defect:

| | what it is | why the current design cannot hold it |
|---|---|---|
| **① decision weight** | how an AI scores a legal verb against the situation | `RequirementRow` is boolean — *legal / not legal*. It has no gradient, and a chooser needs one |
| **② cost / reward / penalty** | the expected-value shape of an outcome, not its certain effect | §6's `EffectRow` states what an effect **does**, never what it is **worth**, and never that it might not happen |
| **③ the counter relation** | *strike beats X, X beats Y* — a property **between** verbs | every table in the design is per-verb. A relation between verbs has no home, and cardinality (`D-25`) says it is a pair table |

③ is the sharpest of the three because it is the one that is **structurally** homeless: ① and ② are
missing columns, ③ is a missing table. **This is exactly the shape of the actor round's `D-15`
finding one level up** — and it is the strongest evidence so far that sealing `CMD-1`..`CMD-6` at
the DESIGN checkpoint would have been premature. The PO was right to refuse.

## 5. The measurement — taken 2026-08-02, base `50bff49a4`

Recorded so no later section has to re-assert it, and so a red team can re-run it.

### Finding 1 · The designs do not exist in code

```
grep -rl CommandKind InteractionKind ToolCallAllowlist InstrumentRef \
         TargetRef ProposedOutputs OutputDecl ExamineTarget tool_call_allowlist \
         crates/ services/ migrations/         →  0 hits for all nine
```

**2,602 lines of design** across `PL_002` (643) + `PL_005` (631) + `PL_005b` (820) + `PL_005c`
(508), and none of its vocabulary has a referent. The same ratio the actor round found for
`RES_001`/`EF_001`.

### Finding 2 · What actually runs is smaller, and closed at every level

| | |
|---|---|
| `CombatPayload` | closed 5-variant enum — `Strike · Defend · Move · Flee · EndTurn` ([payload.rs:22](../../services/commit-service/src/domain/payload.rs#L22)) |
| `CombatEvent` | closed **8**-variant enum ([payload.rs:44](../../services/commit-service/src/domain/payload.rs#L44)) — ⚠ **this line said 6 until R3 re-counted it; see §9.7** |
| `DomainEvent` (TS) | closed **6**-variant union, hand-mirrored across the language boundary ([turnOutcome.ts:168](../../services/game-server/src/wire/turnOutcome.ts#L168)) — **8 ≠ 6: the mirror is ALREADY BROKEN in production** |
| `renderEvent` (TS) | a `switch` with one arm per verb, producing English prose ([turnOutcome.ts:182](../../services/game-server/src/wire/turnOutcome.ts#L182)) |
| wire surface | exactly one inbound message, `turn.submit`, carrying an opaque `action` ([ChannelRoom.ts:250](../../services/game-server/src/rooms/ChannelRoom.ts#L250)) |

`payload.rs`'s own header states the intent plainly: *"both are closed sets for the same
reason."* That is the decision this round reverses, and it was a decision — not an oversight.

### Finding 3 · Adding one verb today — counted, not estimated

Non-test source files that name the verb vocabulary: **10, across 2 languages**
(`domain/payload.rs`, `domain/law.rs`, `domain/actor.rs`, `vocabulary.rs`, `llm_driver.rs`,
`ruleset-core/combat.rs`, `ruleset-core/classification.rs`, `ruleset-loader/validate.rs`,
`ruleset-loader/patch.rs`, `wire/turnOutcome.ts`). Test files: **10 more.**

> This is the number the PO asked about. **Adding `cast` to this engine is a 10-file,
> 2-language edit plus its tests.** Under `D-30` it must be one manifest row.

### Finding 4 · 🔴 `vocabulary.rs` contradicts its own header, and the seam is visible in one function

[`vocabulary.rs:1-4`](../../services/commit-service/src/vocabulary.rs#L1) claims:

> *"data, not code: one declaration serves the model as tool schemas AND commit-service as the
> validation set; **a drift between the two is impossible because there is only one file**."*

That is **true of the tool NAMES and false of the BINDING.** `contains()` (`:77`) answers from
the loaded JSON; `validate()` (`:105`) answers from a hardcoded `match tool_name` with one arm
per verb and an `other => Err(Reject::UnknownTool)` fallthrough. So for a fifth tool added to
`combat_v1.json`:

```
vocabulary.contains("cast")  →  true      // the declaration says it exists
vocabulary.validate(…, "cast", …)  →  Err(UnknownTool("cast"))
```

**Two answers to one question, in one file, one function apart.** It is *latent* rather than
live today only because `combat_v1.json` carries exactly the four tools the `match` has arms
for, kept in step by hand — the drift the header calls impossible.

This is the command layer's `law.rs:218`/`law.rs:225`: the right structure declared, and the
next statement defeating it.

### Finding 5 · The project already paid for this failure mode once, in production

[`turnOutcome.ts:97-115`](../../services/game-server/src/wire/turnOutcome.ts#L97) records it in
the source: a new event type without `turn_number` threw out of the replay and **killed the
channel's whole projection, for every client, permanently** — replay meets the same event again
on the next attempt. `ruleset.epoch_activated` was the first such event, caught by
`/review-impl` before it shipped. The comment's own conclusion is this round's thesis:

> *"the writer should not be the only thing standing between a new event type and a dead room."*

### Finding 6 · The corpus has already made this argument once and did not generalise it

[`PL_005:568`](../../docs/03_planning/LLM_MMO_RPG/features/04_play_loop/PL_005_interaction.md#L568)
found **five mutually-inconsistent `MapKind` ladders** across the corpus and concluded that this
is *"the strongest evidence that the enum was never load-bearing."* The identical argument
applies to `InteractionKind`, `CommandKind` and `CombatPayload`, and nobody made it.

### Finding 7 · What is already RIGHT and must survive the redesign

| | |
|---|---|
| `PL_005` §3 | *"Zero new aggregates … Interaction is a payload pattern + dispatch contract, not a state owner."* — the `DF7-A2` shape, correct. |
| `PL_005` §2 | `ProposedOutputs` → `ActualOutputs` derived at the validator — this is `D-5`'s propose/adjudicate/apply, already present. |
| `vocabulary.rs` header | one file serving both the model's tool schemas and the engine's validation set — the right instinct, defeated only by the binding. |
| `turnOutcome.ts:182` | *"the SERVER ships facts, the client decides words"* — already the `GameplayCue` split, stated. `renderEvent` then violates it in the same file. |
| `ChannelRoom.ts:250` | the wire carries an **opaque** `action`; the transport does not close on a verb set. |
| `payload.rs` `EndTurn` | an engine-only payload unreachable from the tool vocabulary — the submitter-class distinction this design needs, already discovered. |

## 6. Open register

| # | question | class |
|---|---|---|
| **C-1** | **The effect primitive set is the round's real unknown.** The actor round's decoupling works because its shared shape is arithmetic. A verb's effects are not all arithmetic: `give` moves an edge, `speak` calls an LLM, `sleep` advances fiction time. One row shape will not carry all four. | genuine unknown — spec §6 |
| **C-2** | **A non-deterministic verb inside a replayable log.** `speak` is `origin: Oracle` in §11.6's sense; `strike` is `Recomputable`. Does the verb declaration carry that flag, or is it a property of the effect primitive? | decidable — argue it |
| **C-3** | **Where does the verb ordinal space live** — one space per reality alongside quantities, or its own? `QTY-A5`'s never-reuse must cover it either way. | decidable |
| **C-4** | **Target resolution and the offered-candidate gate.** `THR-A4` (the engine offers, the model chooses) is shipped for `strike` only, inside the hardcoded arm. Generalising it is most of what a declared verb needs from binding. | decidable |
| **C-5** | **Arity and role validation.** `PL_005`'s 4-role pattern (agent / instrument / direct / indirect) is a good shape; is the role set engine-closed, or does a verb declare its own roles? | needs the PO or an argument |
| **C-6** | **Does a command belong to the same wave budget as the status wave** (`O-10`)? A verb that applies a status that crosses a threshold that proposes a status is the same re-entrancy, entered by a new door. | decidable — likely yes |
| **C-7** | **`CMD-6`'s fix is small enough to do now** and is not blocked by the rest of the design. It may not belong in a design-only round; recording the tension rather than resolving it. | timing — PO's call |

## 7. Drift log

Appended as it happens. **A run that ends with an empty drift log is dishonest.**

| # | what nearly went wrong |
|---|---|
| **DR-1** | I first wrote finding 4 as *"`vocabulary.rs` has a live drift bug."* It does not — the JSON and the `match` are in sync today, so the `other =>` arm is unreachable. Rewritten as **latent**, with the exact condition that makes it live. Claiming a live bug that a reviewer then disproves would have cost the whole finding, and the finding is the best one in the sweep. |
| **DR-2** | The prior-art search returned an immersive-sim result set with no technical content (design criticism, not architecture). I nearly cited *"verb-noun matrix"* as established terminology on the strength of a TV Tropes page. It is not in the sources; the argument is made from the Sims/GAS/Qud evidence instead, which is concrete. |
| **DR-5** | **I predicted the home genre would fit, in writing, and it scored worst.** Dataflow §8 read *"the cultivation genre is the wrong one to start with — it is the home genre and **will fit by construction**."* Run last, blind, **unprimed**: `3 ✅ · 27 ⚠ · 22 ❌` — a **5.8 % ✅ rate, the lowest of the four**, against wuxia's 19 %. The prediction is deleted from §8 rather than annotated. **What makes this a drift entry rather than just a wrong guess:** I wrote that line to justify *not* running the genre, and had the PO not said *"expand the investigation"* I would have skipped the measurement that falsified it. **The reasoning that excludes a test because you know its answer is the reasoning that never learns you were wrong.** |
| **DR-4** | **I led the witness.** After the occult author scored a design it had not read, my correction message listed the identifiers it missed — including *"`RoleSpec.arity` … so multi-operand targets ARE expressible; check this before you re-file W4/W5."* It duly re-filed them ✅. The re-run was necessary and its **new** findings (`AF-5`..`AF-8`) are sound, but its **score** is contaminated and must not be averaged with the other two. The clean fix, had I thought of it: name the identifiers **without** saying what they imply, or commission a fresh agent that never saw the first attempt. |
| **DR-3** | The spec's §6 first read *"seven primitives, and not one of them is new"* — a satisfying line that was **false for two of them**. `EdgeMove` attaches to §12.4, which is a rule about where an edge is stored, not an operation; `Oracle` attaches to §11.6, which is a classification, not a door. Caught on self-review, corrected in place, and `A-1` was rewritten from a worry into a finding with a named subject. **The closure rule that makes §6 non-arbitrary is the thing my own summary sentence quietly broke** — which is the `NV` shape exactly: a claim of coverage that the check underneath does not deliver. |

### 4d. Added after the `PO-5` research pass

| # | Decision |
|---|---|
| **`CMD-9`** | **`costs` is renamed `spend`, and the chooser's weight lives in `considerations`.** GOAP models an action as *preconditions · effects · **cost***, and that cost is a **planner search weight**; GAS's `CommitAbility()` cost is a **spend taken from the actor**. Two different things, one word — and a single column would have had the chooser subtracting qi. A verb can be free to spend and expensive to prefer (*fleeing*), or the reverse. This is `D-21`'s discipline (the word *"tier"* named three ladders) applied **before** the collision ships. |

**Prior art that decided `PO-5`, recorded so §2 of the dataflow spec does not have to be re-derived:**

| finding | decides |
|---|---|
| IAUS multiplies consideration scores, and needs a **compensation factor** because the product decays toward 0 as considerations are added | **the aggregation is engine-closed** — an author adding a consideration would change every other consideration's arithmetic invisibly. `O-96`'s modifier-layer argument, one layer up, reaching the same split |
| **Pokémon relates 18 types to 18 types, not 1,000 species to 1,000 species**; Warcraft III ~6 attack × ~7 armour types in editable Gameplay Constants | **the counter matrix is over CLASSIFIERS, never over verbs.** The N² problem is solved by making N small and putting the instances outside it. Sparse, neutral default ⇒ a reality with 4 interesting matchups writes 4 rows |
| GOAP = preconditions · effects · cost, shipped 2005, from STRIPS 1971 | the verb row is already this shape — which is confirming, and it exposed `CMD-9` |
| `role_rng(session_seed, actor, action_idx, SeedRole)` already exists, keyed by an action index, with **pinned discriminants so reordering cannot change a historical roll** | **risk has a real door** — an operation, not a rule or a classification. It removes one of `A-1`'s two exceptions |

## 8. What is done, and what is next

- [x] Prior-art research round 1 — six systems, structure spec §3
- [x] Rot sweep, measured — §5 above
- [x] Structure spec — [`2026-08-02-command-interaction-structure.md`](../specs/2026-08-02-command-interaction-structure.md)
- [x] **PO checkpoint** — `C-5` decided (`CMD-7`), `C-7` deferred (`CMD-8`), `PO-4` decided (full companion), **`PO-5` raised**
- [x] Prior-art research round 2 — the decision layer (`PO-5`): IAUS · Pokémon/WC3 classifier matrices · GOAP · the shipped RNG door
- [x] Dataflow companion, first pass — [`2026-08-02-command-interaction-dataflow.md`](../specs/2026-08-02-command-interaction-dataflow.md): flow drawn, decision layer designed, `A-1`..`A-7` adjudicated (2 resolved, 5 confirmed), `O-CI-1..9` opened
- [ ] **Red team** against dataflow §2–§4. **Attack `O-CI-4` first** — spend-before-veto is the finding most likely to be fatal
- [ ] **Author agents, run BLIND** — the wish list is written before the surface is read, or the measurement self-confirms. Do **not** start with the cultivation genre; it is the home genre and will fit by construction
- [ ] Re-present `CMD-1`..`CMD-9` for sealing once the red team has run
- [ ] Rot ledger applied to `PL_002` / `PL_005` / `PL_005b` / `PL_005c` + `rng.rs` (structure §10 + dataflow §7)
- [ ] `D-VOCAB-BINDING-TABLE-DRIVEN` — BUILD round (`CMD-8`), with the bite-test named in that row

## 10. Consolidated verdict — all six agents in

**Totals: 17 FATAL/blocking findings across three reviewers, three blind author scores, and four
errors in my own measurements.** Two open rows closed with arguments (`O-CI-2`, `O-CI-4`). Detail in
§9.4–§9.7; this is the conclusion.

### 10.1 What SURVIVED — validated repeatedly, by methods that could not see each other

| | who confirmed it |
|---|---|
| **a verb is a declared row; the pipeline is closed and its contents declared** | all three authors, both structural reviewers |
| **`CMD-7` — roles with OPEN names and a CLOSED flag set** | the PO's call against my recommendation, and the occult author calls it *"the sharpest bit of design in either file"* |
| **`CMD-9` — spend ≠ weight** | wuxia #14: *"free to spend, expensive to prefer"* is *"exactly what the design nails"* |
| **`considerations`** | *"the best thing in either document"* (political); the seam that makes a bribable, hesitant faction fall out for free |
| **`CMD-4` — the cue channel** | and R3 found it is **cheaper than I claimed**: `labels.rs` already ships the storage, the naming discipline and the i18n argument |
| **the sub-language that works today** | `/sleep · give · poison · execute · summon · fixed heal` — *"a verb fits when every number is a constant, it touches one other actor, takes no parameter, and needs no state between two actors"* |

### 10.2 What is broken IN the design — mine to fix

| | |
|---|---|
| **F-8** | the classification test **cannot fail** in the direction the round needs. `NV-1`, in the rule that licenses everything |
| **F-2 + AF-6** | **`EffectRow` is static in EVERY field** — magnitude is a literal, target is a fixed ordinal, effects cannot read their own bindings. **This is `O-71`/`C-0` rebuilt verbatim** in a round that declared `D-1..D-75` inherited |
| **FATAL-2** | the closure rule is unsatisfied by **seven of eight** doors, not two. Its real predicate is *"a design document has a section about it"* |
| **FATAL-3** | `role_rng` has no verb term ⇒ `cast` collides with `strike`; and fixing it touches **pinned replayed history** |
| **R1-8/R1-9** | `Logistic` needs `exp` (forbidden by `D-8`) · the compensation factor **self-refutes §2.2's own argument** · **`CurveKind` already exists, shipped and hashed** |
| **HIGH-5** | *"stage"* already names two closed sets — `D-21`'s defect through the door `CMD-9` was written to lock |
| **F-4/F-5/F-6/AF-5/AF-7** | no pair state · no create/destroy in **either** direction (`Grant` and `Revoke` both absent) · no multi-target · the one pair table returns a scalar |
| **R1-5** | only a **tail** retirement is expressible — while my rot ledger deletes rows for a living |
| **AF-8** | **`RefKindMask` is unpriced** and is not one of the six ordinal spaces |

### 10.3 What is broken BENEATH the design — **escalate out of this round**

These are not the command layer's to fix, and the command layer **multiplies** each of them.

| | |
|---|---|
| **R1-1** | the replay reader **strips the pin**, and a stripped pin is byte-identical to a legitimate `NULL` ⇒ **the F3 refusal can never fire** (`NV-4`). Five new ordinal spaces would rest on it |
| **R1-2** | **`P-F` is false for the shipped engine** — two RNG coordinates are snapshot-only |
| **FATAL-1** | the `CombatEvent`↔`DomainEvent` mirror is **already broken in production** (8 ≠ 6), the guard comment claiming test coverage is false, and **my own miscount hid it** |
| **R1-11** | there is **no input log**, so verification replay has nothing to run on |

### 10.4 The strategic inversion, and it decides what to do next

> **What both documents treated as expensive is mostly built.** Six ordinal spaces ≈ M, cloned from
> two shipped templates; the never-reuse guard ≈ 20 lines of trait extraction, not the heavy
> obligation `O-CI-5` records.
>
> **What both documents treated as settled is where all the unbuilt work is.** *"A primitive exists
> iff the substrate built the door"* — seven of eight doors are prose.
>
> ⇒ **The round's real deliverable is not a verb table. It is the seven doors, and they belong to
> the actor round, which wrote no code.**

### 10.4b Post-review dig — three things resolved without needing the PO (2026-08-02)

| | |
|---|---|
| **`F-8` FIXED** | The vacuous test is **withdrawn** and replaced by dataflow §9's three questions — **V1** extension (can a member be added as a manifest row?) · **V2** non-interference (does adding one change existing members?) · **V3** identity-blindness (does the engine's arithmetic depend on *which* member?). **It fails on six real cases, two of them proposals from this round** (`considerations`' count fails V2 — the compensation-factor self-refutation; `effectiveness` cells fail V2 — the sparse-default hazard), and it **independently reproduces `O-96`'s verdict** on modifier layers. It also carries a bite-test obligation: *add a member in a fixture, assert nothing else moved.* |
| **`M-16` ANSWERED — TWO tables, not five** | Four of the five proposed kinds are **not kinds**: two are ordinary `Option`-is-`None`, and two (**relational**, **parameterized**) are **missing capabilities**, and splitting on those would freeze an absence into a schema — the `LifecycleState` error. The one real split: **out-of-fiction controls (`/help`, `/leave`) leave the ruleset entirely**, with a clean test — *does it append a fact a replay must fold?* `/undo` is decided **against**: in an event-sourced world an undo is a **compensating fact**, so a reality declares a compensating verb and the out-of-fiction `/undo` does not exist. |
| 🔑 **`O-CI-10` — TWELVE findings are ONE absence** | see below |

#### 🔑 The synthesis: there is no instance-level pair state

`F-4` (bribe needs disposition) · `AF-3` (opposed checks) · `AF-5` (the one pair table returns a
scalar) · `AF-7`/`F-5` (create an edge, not re-point one) · **Arrow B** (who believes what, and who
they think did it) · reading progress per (reader, tome) · a cover story (who believes it) · a favour
balance with *this* contact · a life-debt with a creditor and a magnitude · per-recogniser
recognition · *"two banks differ only by their quantities — there is no per-actor agenda"* — and
**both 0 %-expressible verb kinds**.

> **Every one is a VALUE ON A PAIR.** The design has exactly one pair table — `effectiveness` —
> and it is **ruleset-level with a scalar codomain**. There is **no instance-level pair state
> anywhere.**

**And the corpus named the pattern, then made it structurally unreadable.** Actor `§12.4` says
plainly *"actor ↔ actor | many ↔ many | **on a pair table**"* and names `actor_actor_opinion`. Then
`§12.3` says *"actor core never reads them"* and §2.2 says `InputKind` must read `ActorQuantities` at
phase 0. **Two individually correct rules, jointly forbidding what twelve findings need** — the same
shape the political author found for Arrow B, one layer down.

**Resolution proposed (dataflow §11.2): a bind-time projection, and it is not a new mechanism.** After
stage 2 the roles are bound to concrete refs and `arity` is declared and bounded — so the relevant
pairs are **known, small, and need no query**. A stage 2·5 projects `O(arity² × declared pair
quantities)` values into a scratch block (16 values for a 2-role verb with 4 pair quantities). Actor
core is untouched, `size_of` does not move, `D-15` holds, and it is `D-49`'s phase-0 projection —
the shape that already turns `PL_006`'s records into `status_active: u64` — applied to pairs.

**A pair whose value is EXISTENCE is an edge**, so `F-5`'s missing `Grant`/`Revoke` becomes a `Delta`
on a pair quantity rather than a ninth primitive.

**It is blocked on `O-71`** — a pair value the magnitude cannot read buys nothing. **That is the
third independent line arriving at the same unblocker.**

#### And Arrow A is smaller than it looked

`D-29` bars a stored *predicate*, but its own escape applies: **a condition is a declared
THRESHOLD**, and a threshold ordinal stored on a record is flat and already-evaluated machinery. ⇒
**Arrow A = `D-9`'s deferred trigger mechanism + a declared record kind + `condition:
ThresholdOrdinal`.** Not a refusal to overturn — **a deferral whose cost is now measured**, at 14 of
one author's 29 ❌. That is the number `D-9` did not have when it was taken.

### 10.5 Recommendation to the PO

1. **Do NOT seal `CMD-1`..`CMD-6`.** `F-8` invalidates the test that would justify sealing them.
   Fix the test first: the discriminator is **who may ADD a member**, not who picks one.
2. **Escalate §10.3 out of this round.** `R1-1` in particular is a foundation defect with a live
   subject; it is not a command-layer question and must not be fixed inside a command-layer spec.
3. ⚠️ **RE-RANKED by the round-2 measurement (spec §12).** The order is now:
   **① Arrow A** — quantified by two blind authors independently at **14/29** and **13/22** of their
   ❌ columns, and §11.4 argues it may not violate `D-29` at all (a threshold ordinal stored on a
   record is flat, already-evaluated machinery). It is `D-9`'s deferral **with a price tag attached
   for the first time**. **② `O-71`/`C-0`** — one variant, one codec arm, one acyclicity check;
   asked for by the red team and **all four** blind authors, and `O-CI-10` is blocked on it.
   **③ `O-CI-10`** pair state. **④ `F-6`** unbounded target sets — *"being seen"* is load-bearing in
   two genres and **no proposal on the table reaches it**.
4. **Ship L5 (Present) first if anything ships.** XS, and it **fixes `FATAL-1` as a side effect** —
   an ordinal has no unmatched switch arm. Scope it to include the two orphaned event types.
5. **Reconsider whether this is one table.** `M-16` found the row's normal state is *mostly inert*,
   and named five kinds — two of which (**relational**, **parameterized**) are **0 % expressible**.
6. **Answer the question the authors converged on**, because no amount of good authoring routes
   around it: **is this engine willing to have more than one account of what happened?**

---

## 8b. PO standing constraint — 2026-08-02, and it overrides the recommendations in §10.5

> **This session is DESIGN ONLY. No code, at all. Anything found gets written into the spec to be
> solved later.**

⇒ **Recommendation `10.5 #4` (ship L5 first) is OFF for this session**, and so is `CMD-8`'s binding
fix. Both stay as recorded work with their triggers intact. **The one thing this changes about how
findings are handled: a finding is not "fixed", it is FILED** — into the spec body where it belongs,
not merely into a register row, because a register row is prose and this project has measured what
prose is worth (`deferral-gate`, 9 of 19 rows prose-only).

**Direction given: expand the investigation.** Round 2 in §9.8.

## 9.8 Investigation round 2 — method recorded BEFORE the results

**Three agents, and the third covers a modality nobody has run.**

| # | agent | why it is not redundant with round 1 |
|---|---|---|
| **A4** | **修真 cultivation author, BLIND** | the HOME genre — expected to score well, so **a high score proves nothing on its own.** What it actually tests is whether **even the home genre hits the same walls**: `雙修` paired cultivation, `師徒` master–disciple, `傳功` transmission, `結怨` a mutually-carried grudge, `道侶` dao companions are **all state living BETWEEN two characters**, which is `O-CI-10`. If cultivation hits the pair-state wall, the wall is not a genre preference |
| **R4** | **red team on §9 · §10 · §11 ONLY** | those three sections were written **after** round 1 and have never been reviewed. `§11.2`'s bind-time projection is the newest and least examined idea in either document, and it is the one most likely to harden before anyone attacks it. Given the round-1 finding list explicitly, so it cannot re-report known defects |
| **G1** | **can an LLM actually AUTHOR this manifest** | 🔑 **the uncovered modality.** All three round-1 authors measured *expressiveness*. **Nobody measured generability** — and the sibling round's `PO-1` chose its three-table layout **specifically on the grounds that "the manifest is generated by an LLM"** and that a plausible-but-wrong generated row is the worst failure mode. **The command layer inherited that constraint and never tested against it.** G1 does not review; it *writes eight verbs' worth of actual rows* and reports the row count, the ordinal count, the guesses, the forward-reference problem and the dependency order |

**`DR-4`'s lesson is applied:** A4 gets **no identifier list** — it is told to read carefully and to
cite real names, and nothing about what the design contains. The occult re-run was contaminated by my
priming and its score is excluded from comparison.

**What would make round 2 untrustworthy:** A4 scoring high **and** its ❌ column containing no pair
state — that would mean the wish list was written to the genre's clichés rather than its mechanics ·
R4 attacking §1–§8 instead of §9–§11 · G1 *describing* a manifest instead of writing rows, which is
the failure that makes the exercise a review again.

## 9. The review round — method recorded BEFORE the results

Written first on purpose. A method described after its results is a method chosen to suit them.

**Why sub-agents at all, stated per the fan-out discipline:** *six agents, because for all six the
ISOLATION IS THE PRODUCT.* The three reviewers must not be able to see the argument that produced
the design — the author cannot un-know his own reasoning. The three authors must write their wish
list having read **nothing**, and the author of the spec has read all of it and therefore cannot
produce a blind list. This is the sanctioned case (*"independent judgement, adversarial verify,
cold-start review"*), not a per-item fan-out.

### 9.1 Red team — three lenses, deliberately non-overlapping

| # | lens | told to attack first |
|---|---|---|
| **R1** | **determinism, replay, provenance** | `O-CI-4` (spend before veto) · `O-CI-2` (Oracle vs the two replays) · `A-3`/`O-CI-6` (the classifier and the chooser are outside the digest) · byte-stability of the chooser's multiply against `D-8` · never-reuse across six ordinal spaces · what a **sparse** matrix cell means when a later epoch adds it |
| **R2** | **does the extensibility claim hold** | walk concrete verbs through the design until one does not fit — `bribe`, `craft`, `teach`, `negotiate`, `sneak past`, `pray`, `/undo`, `dual-wield`. Plus the strongest available attack on the whole design, handed to them explicitly: *count the engine-closed sets, and ask whether "the engine closes on mechanism" still does any work or has become "the author only picks from menus"* |
| **R3** | **is any of it TRUE, and is any of it buildable** | re-run §5's measurements from scratch · check each of the eight primitives' "doors" for whether they are shipped code, a design section, or neither · verify the RNG-door claim by reading who actually calls `role_rng` · size the build honestly and say what already exists |

R3 was told the thing this project has learned the hard way: **assume the spec's claims about the
code are wrong until checked**, and it was warned off `commit-service/src/domain/` as evidence of
intent (`D-35` — it misled a sibling document four times).

### 9.2 Author agents — three genres, run BLIND

**The experiment's entire value is in the ordering.** Each agent writes 35–50 wishes **before
opening a single file**; reading the surface first would make them fit their wishes to what exists,
which is a self-confirming measurement. **Written blind, the gap IS the measurement.** Each is
required to return its Phase-1 list **verbatim and untidied**, so the blindness is auditable rather
than promised.

| genre | chosen because |
|---|---|
| **武俠 wuxia martial** | no cultivation ladder — and its load-bearing acts are **social and reputational** (拜師 taking a master · 比武 a formal duel · public renunciation), which the design has barely considered |
| **political chronicle** | **the interesting actors are not people** — a faction, a claim, a law, a famine. It also carries retroactive acts (*declare a past act to have been treason*) and delegation, neither of which has a home |
| **modern occult investigation** | the primary resource is **knowledge, not hit points**; results are **information that may be false**; and a character may end **strictly worse** than they began — which is the axis the actor round found the corpus structurally forbids |

**修真 cultivation is deliberately EXCLUDED** from this round. It is the home genre and will fit by
construction, so including it would inflate the score without testing anything. If the other three
converge, cultivation is the confirmation round, not the measurement.

### 9.4 Author-agent results — 2 of 3 scored

| genre | score | its ONE thing |
|---|---|---|
| **武俠 wuxia** | `12 ✅ · 21 ⚠ · 29 ❌` | **a door that mints a durable, WORLD-OWNED record — and a condition stored ON it that the engine re-evaluates without anyone submitting anything.** *"Fourteen of my twenty-nine ❌s are one missing capability wearing fourteen costumes"* — the promise, the oath with a penalty clause, the vouching, the life-debt, the favour owed, the duel agreement, the month-hence appointment, the ambush, the sealed manual, the blood feud, the planted evidence, the rumour, the accusation, the assembly's verdict |
| **political chronicle** | `8 ✅ · 27 ⚠ · 20 ❌` | **per-observer state — a knowledge layer, so that *what is true* and *what an actor believes, and who they think did it* are different rows.** Twelve wishes dead outright, four crippled. Runner-up, named as *"the one I expect to be told is easy"*: a **scheduler** / `pending_acts` |
| **modern occult** | `10 ✅ · 32 ⚠ · 8 ❌` ⚠️ **see the bias warning below** | **a holder dimension on a proposition, and a Bind stage that resolves a role against the HOLDER's view rather than the world's.** *"Declared statuses already give me boolean propositions for free — I no longer need a belief engine, I need one more coordinate on facts I can already write, plus permission for stage 2 to lie to me."* Sharper than its first pass, and it is Arrow B |

> ⚠️ **The occult re-run's score is NOT comparable to the other two, and the reason is my fault.** Its
> first pass scored a design it **reconstructed rather than read** (§9.3), so I sent it back — and my
> correction message **named the identifiers it had missed**, including *"`RoleSpec.arity` … so
> multi-operand targets ARE expressible; check this before you re-file W4/W5."* **That is leading the
> witness.** Its `16 % ❌` against wuxia's `47 %` and the chronicle's `36 %` is partly my priming, not
> a genre difference. Recorded as `DR-4`. **What survives the bias is what it found that I did NOT
> name** — and that is the valuable part: no dyadic state · the one pair table returns a scalar ·
> effects cannot read their own bindings · no revoke · `RefKindMask` is unpriced.

#### What the corrected occult read found that nobody had named

| | finding | why it is new |
|---|---|---|
| **AF-5** | **The one pair table returns a SCALAR.** `effectiveness[atk][def] → multiplier_milli` is excellent for *"the wrong ritual for that category"* and useless for every (A,B) → *different outcome* wish. **There is no pair table whose codomain is an effect.** | Names precisely what `F-4`'s pair-state hole would need in order to be filled |
| **AF-6** | **Effects cannot read their own bindings.** `EffectRow.target` is a fixed ordinal, so a verb can *bind* the right operand and still not *act on what was bound*. | The same family as `F-2` (magnitude is a literal): **the effect row is static in every field**. Roles solved arguments for *legality and targeting* and not for *outcome* |
| **AF-7** | **There is no REVOKE.** `StatusPropose` has no inverse among the eight primitives, and `Dispose` is explicitly *"cache eviction, not deletion"* (`D-23`). **Knowledge, once granted, cannot be taken.** | A missing primitive nobody had counted — and it pairs with `F-5`'s missing `Grant` to make the create/destroy axis absent in *both* directions |
| **AF-8** | **`RefKindMask` is unaccounted for.** It decides whether a case file, an organisation, a memory, a ritual, a request or a concept can be **named at all** — and it is **not among the six ordinal spaces** §3.1 enumerates and prices. | *"The highest-leverage unanswered question in the document, and it is not in `O-CI-1..9`."* Correct — it is not |

**Its verdict flipped to *"build on this"*, with three cautions in order:** the belief coordinate
(*"it deserves its own spec, not a wedge into `RequirementRow.kind` — the closed-set discipline is
**why** the rest works and I don't want it bent for me"*) · **`O-CI-4` attacked before anything else**
(*"my whole genre is verbs whose cost lands whether or not they work"*) · and **the two doorless
primitives matter because they are `give` and `speak`** — *"not a refinement; the difference between
a shippable case and a demo."*

#### 🔑 The convergence — and it is TWO doors, not one

Three blind wish lists, three genres, no contact. **Two arrows, each named independently by at least
two of the three:**

> **Arrow A — the world must be able to OWN a record and CHECK a condition with no actor submitting.**
> wuxia's #1 · political's runner-up · occult's `W13` (a cost that lands later), `W25` (a ward that
> decays), `W47` (irreversible-with-warning).
>
> **Arrow B — there must be able to be MORE THAN ONE ACCOUNT of what happened.**
> political's #1 · occult's #1 (*"the investigator who is certain, and wrong"*) · wuxia's #28 (a
> stolen art discovered later), #32 (a contested accusation), #49 (poison hidden from its victim).

**Both are things this design decided against, and the political author put the knife in exactly the
right place:** Admit stamps the true actor from the authenticated session (a security property), and
the log is one global append-only SSOT every replay folds identically (a determinism property).
**Individually correct, jointly fatal to Arrow B.** That is not an oversight to patch; it is a
question the PO has to answer — *is this engine willing to have more than one account of what
happened?*

#### Four specific findings worth more than their size

| | finding | why it matters |
|---|---|---|
| **AF-1** | **`RefusalFact` carries no effects.** *"Be refused, and it wounds"* is unwritable — and the refused party still paid `spend` at stage 4 with no way to register the insult. | **A new face of `O-CI-4`**, from the author side rather than the engineer's. In both genres the *refusal is the dramatic beat*: a kowtow refused, a demand for homage ignored, a marriage proposal declined. |
| **AF-2** | **`EffectRow.magnitude` is a constant `i32`.** No computed magnitude. | **All three authors hit this same column** — an insult scaled by who is watching (wuxia #31), a lord with 3 votes needing a different verb from a lord with 1 (political `W32`), paying half a dowry (`W54`). Cheapest fix in the whole round, largest reach. |
| **AF-3** | **`RequirementRow` compares a role to a LITERAL ordinal, never to another role**, and `ChanceSpec` has no contested form. | **Opposed checks are unwritable** — *"backfires unless your standing genuinely exceeds theirs"* (wuxia #38), *"works only if the denier's credibility exceeds the accuser's"* (political `W14`). An engine for social conflict that cannot compare two actors. |
| **AF-4** | **No ref kind names a past committed event.** | *"An act whose object is another act"* — ratify · forbid · avenge · investigate · commemorate · attaint. Political's verdict: *"half a political world is unwritable."* Wuxia's #58 independently. |

**Both scoring authors returned the same verdict in the same words: *"wait — but not long, and not for
a redesign."*** Both said the verb-as-a-row decision is right, the closed-pipeline/declared-contents
split is right, and `considerations` is the best thing in either document. Neither would author on it
today.

### 9.5 Red team R2 (extensibility) — **9 FATAL**, and I verified the load-bearing four myself

**Verdict returned: *"the claim is false as stated and true only for a narrow sub-language."*** Of 12
verbs walked, **8 require a new engine enum member, a new ordinal space, or a mechanism that does not
exist.** I re-ran the four claims that carry the review rather than accepting them:

| | claim | verified? |
|---|---|---|
| **F-9** | *"`check_never_reused` is a method on `QuantityTable` and nothing else"* — so structure §4.2's and dataflow §3.1's mitigation (*"a second SUBJECT, not a second MECHANISM"*) is fictitious | ✅ **TRUE.** [`never_reuse.rs:45`](../../crates/ruleset-core/src/never_reuse.rs#L45) is `impl QuantityTable`, not a trait. A verb table cannot be passed to it. `O-65` (🔴, still open) is the generalisation, and it is *unbuilt* |
| **F-5** | a `Grant` door exists (`granted \|= 1<<ord`) with **no matching primitive**, falsifying the closure rule's ⇐ direction | ✅ **TRUE** — [actor-dataflow.md:586](../specs/2026-08-02-actor-hub/analysis/2026-08-02-actor-dataflow.md#L586) states it operationally |
| **F-2** | `EffectRow.magnitude: i32` is a literal, reproducing `O-71`/`C-0` verbatim one layer up | ✅ **TRUE** — `O-71` is the sibling's *"single highest-leverage change in the register"* (**still awaiting the PO**), and this round declared `D-1..D-75` inherited and then rebuilt the identical defect |
| **O-101** | 25 of 32 quantity ordinals already committed before statuses, items or relationships exist | ✅ **TRUE** — which is why F-7's defender-classifier has no free slot |

#### 🔴 The two the PO must hear immediately

> **F-9 — the PO accepted the sixth-ordinal-space cost against a mitigation that does not exist.**
> `CMD-7` was sealed with §3.1's cost note saying the guard is an existing routine applied to a new
> subject. It is not. **The cost accepted was understated**, and this is my error, not the PO's.

> **F-8 — the classification test that licenses this entire round CANNOT FAIL in the direction the
> round needs.** My test: *"if the author would be choosing from a set the engine defines, it is
> vocabulary."* Apply it to the thing this round exists to demolish: an author writing
> `CommandKind::Sleep` **is** choosing from a set the engine defines ⇒ by my own test, `CommandKind`
> is vocabulary and needs no change. **The test passes the defect.** The correct discriminator is not
> *who picks a member* but **who may ADD one**. This is `NV-1` — a check that cannot fail — in the
> classification rule the whole design rests on, written in a repo whose LOCKED standard exists for
> exactly this. Accepted in full.

#### The rest, in severity order

| # | finding |
|---|---|
<!-- doc-language-gate: ok -- genre terminology and cited corpus spans. CLAUDE.md allows non-English where the text IS the subject matter: domain terms with no English equivalent (glossed in English on first use) and spans quoted from the corpus. The exposition around them is English. -->
| **F-1** | **The acceptance test names a verb the design cannot express.** `bái_sư` is relational — it *creates* an edge and reads the prospective master's disposition. Per F-4 and F-5 the design does neither. **The round's flagship example is unrunnable.** |
| **F-3** | **No verb parameter ⇒ one ordinal per content item.** `cast fireball` and `cast icebolt` differ in `effects[]`, which lives in the verb row. So `cast` = one ordinal **per spell**, `craft` = one **per recipe**, in an append-only never-reuse space. §1's headline (*"adding `cast` must be one manifest row"*) fails against its own design |
| **F-4** | **Pair state is unreadable ⇒ every social verb is inexpressible.** `InputKind` must read `ActorQuantities` at phase 0; disposition is `actor_actor_opinion`, a pair table, channel B, which *"actor core never reads"*. `bribe`'s requirement, its consideration AND its chance are all three unreachable |
| **F-6** | **No multi-target, no selector — the whole area-of-effect family is dead.** `sneak past` (opposed vs everyone present), `fireball`, `cleave`, `bless the party`. Three independent blocks: binding the set, rolling per observer, landing per target. Strictly larger than `O-CI-3` and nowhere admitted |
| **F-7** | **§2.4's matrix is still homeless on the DEFENDING side.** Every candidate home is closed: a field on `ActorQuantities` trips the `size_of` gate · a feature table is unreadable by core · a quantity ordinal is unaffordable (`O-101`) and indistinguishable from ungranted |
| **M-13** | **`spend: [EffectRow]` makes one arm of `O-CI-4` IMPOSSIBLE, not merely awkward** — a spend may be an Irreversible lifecycle transition or a committed `ClockAdvance`, neither of which rolls back. Only the *seam-cannot-veto* reading survives, i.e. the one that guts the seam |
| **M-18** | **The escape hatch is already granted, in my own rot ledger.** `C-3` rewrote `PL_002`'s macro refusal into *"a macro is a verb whose effects are other verbs."* Verb-invokes-verb + threshold conditions + gates + a depth budget **is a call graph with conditionals** — the scripting language `§6.3` forbids, conceded as a routine `U` with no design and no register row |
| **M-16** | **`O-CI-7` is not a `/sleep` anomaly; inert columns are the row's NORMAL state.** `/help` 7/9 inert · `/undo` 7/9 · `give` 3/9 · `strike` 1/9 — and `considerations` is inert for **every player-submitted verb** by §1's own diagram. The real kinds: out-of-fiction control · self-directed act · opposed act · **relational act (0% expressible)** · **parameterized act (0% expressible)** |
| **M-17** | **Nothing would refuse a seventh ordinal space.** §27.4's *refusal criterion* has been converted into an *accepted cost note*, and a cost note is not a refusal mechanism — the *escape-hatch-cannot-reach-its-reason* shape. Honest count at S2 is **ten** spaces, four already unguarded (`O-65`) |
| **M-10** | `submitter_class` is a scalar ⇒ `strike` is player-only **or** NPC-only. One-word fix (a mask); blocks every reality on day one as written |
| **M-24** | **`CMD-7` un-dissolved `ExamineTarget`.** Structure §4.1 deleted it (rot row `C-7`) on the strength of a **per-verb** `admits` mask; dataflow §3 moved `admits` to **per-role-globally**, and the dataflow spec wins. `examine` and `strike` sharing a role now share one mask. **`A-4` is marked RESOLVED and the resolution introduced this** |

#### The sub-language that DOES work — recorded, because it is real

`/sleep` · `give` · `poison` (fixed status) · `execute` (declared transition) · `summon` · a
fixed-magnitude heal. **The pattern, in the reviewer's sentence:** *a verb fits exactly when every
number in it is a constant, it touches at most one other actor, it takes no content parameter, and
it needs no state living between two actors.*

<!-- doc-language-gate: ok -- genre terminology and cited corpus spans. CLAUDE.md allows non-English where the text IS the subject matter: domain terms with no English equivalent (glossed in English on first use) and spans quoted from the corpus. The exposition around them is English. -->
**That set does not contain `strike` — the verb the engine already ships — nor `bái_sư`.**

#### 🔑 Red team and blind authors converged with no contact

| the hole | red team | authors |
|---|---|---|
| **magnitude cannot derive from state** | `F-2` (FATAL) | `AF-2` — **all three** independently |
| **pair state / opposed checks unreachable** | `F-4` (FATAL) | `AF-3` — wuxia #38, political `W14` |
| **`EdgeMove` cannot CREATE a relation** | `F-5` (FATAL) | wuxia #13/#15/#22 — life-debt, 拜師, sworn brotherhood |
| **stored condition the world re-checks** | `M-18` (the macro hatch already conceded) | **Arrow A** — wuxia's #1, political's runner-up |

**Four holes, found twice, by methods that could not see each other.** That is the strongest
evidence this round has produced, and it is evidence *against* the design.

### 9.6 Red team R1 (determinism / replay) — **4 FATAL, 7 MAJOR**, and it CLOSED two open rows

I re-verified the four load-bearing claims against code; all four hold exactly as stated.

#### 🔴 The two that are bigger than this round

> **R1-1 — the replay reader STRIPS the pin, and `RulesPin` does not exist.**
> `grep -rn "RulesPin" crates/ services/ contracts/ migrations/` → **no output**. What exists is
> `EventEnvelope.ruleset_digest: Option<String>`. [`event_source.rs:114`](../../services/world-service/src/rebuild/event_source.rs#L114)
> hardcodes `ruleset_digest: None`, and `EVENT_COLUMNS` ([:121](../../services/world-service/src/rebuild/event_source.rs#L121))
> does not select the column — **verified: the list ends `payload, metadata`.** The migration's own
> `COMMENT ON COLUMN` promises *"Replay compares this against the ruleset it resolves under; a
> mismatch is refused (F3)."*
>
> **And `NULL` is a LEGITIMATE value** (events not produced by a pinned simulation), so a *stripped*
> pin is byte-identical to a *legitimately absent* one. **The F3 refusal can never fire on this path
> — not because it is unimplemented, but because the input it would compare has been destroyed and
> re-labelled as valid.** `NV-4`: an adjacent decision defeats the guard.
>
> ⇒ Dataflow §1's `LOG -.-> SEAL` edge — *"resolve every ordinal against the pin"* — **is not
> something the code can do**, and this round proposes to add **five more ordinal spaces** that are
> interpretable only through it.

> **R1-2 — `P-F` is FALSE for the shipped engine, and this round inherited it unchecked.**
> `session_seed` and `next_action_idx` are fields of `CombatState` and are both RNG coordinates fed
> to `role_rng`. `grep -rn "next_action_idx" crates/ services/ migrations/` returns **three sites,
> all in `domain/`** — never in an envelope, a payload or a migration. They live in
> `IslandCheckpoint` ([checkpoint.rs:41](../../crates/sim-core/src/checkpoint.rs#L41)), whose
> docstring is *"everything needed to rebuild a stepping-identical island … rng position"*.
> **The checkpoint is authoritative for two values that determine every future roll, and the log
> cannot reproduce them.** `D-20`/`P-F` says a snapshot disagreeing with the log is discarded —
> discard this one and there is nothing to rebuild from.

#### ✅ `O-CI-4` is DECIDED, and the argument is one I accept

The two readings **are not symmetric**, which is what my *"both readings break something"* framing missed:

| reading | what actually breaks |
|---|---|
| the spend **rolls back** inside `D-50`'s transaction | the reaction must run **inside** `apply` to reach the rollback — fusing stages 4/5/6. **Breaks two SEALED inherited decisions** (`D-5`'s three layers, `D-9`'s seam) |
| the spend **does NOT roll back** | only `RefusalFact` breaks — it cannot say *"and the spend stands"*. **Breaks one shape proposed this round** |

⇒ **The spend does not roll back**, and `RefusalFact` gains `spend_committed` (or the spend becomes
its own gated row in the same `seq`) — *"otherwise a replay that reconstructs pools from refusals
will over-credit every vetoed verb."* **The vocabulary was already there and I did not see it:**
§2.3 defines `gate: Always` as *"the cost of trying"*. That **is** the non-refundable spend.

**And the ambiguity already ships.** [`law.rs`](../../services/commit-service/src/domain/law.rs):
four distinct control paths emit an indistinguishable `CombatEvent::Missed`, and **exactly one of
them advanced the RNG cursor** — so the log cannot tell you whether `next_action_idx` moved.
`spine.rs:344` advances `turn_number` on `Outcome::Applied { events: [] }`: **a spend with no
committed fact, shipped.**

#### ✅ `O-CI-2` is DECIDED — and §6.2 put the flag on the wrong artifact

| | recovery replay | verification replay |
|---|---|---|
| Oracle result recorded | **served** — the event says what happened | **broken** — §6.8 property 2 wants a *byte-identical* event stream; re-running `speak` calls the LLM again |

Every Oracle effect is a **guaranteed false positive, forever** — and an oracle that always reports
drift is one an operator learns to ignore, which is `canon.rs`'s own stated failure mode (*"it fails
loudly and WRONGLY"*).

> **And moving the flag INVERTED the property that made `§11.6` correct.** There, `origin` lives on
> the **Decision** — an *event-side* artifact a replay can read. Structure §6.2 moved it *"one level
> down"* onto `EffectRow.origin`, a **ruleset-side** artifact, and the event vocabulary carries no
> effect-row id. A verification runner cannot classify an event without resolving the pin *and*
> re-running the computation it is trying to classify.

**Corollary nobody had stated: there is no input log.** `grep -rn "input_log\|inputs_log" crates/
services/ migrations/` → **empty**. Verification replay's stated input **does not exist in this
repo**, so `O-CI-2` could never have been closed by argument.

#### The rest, verified where checkable

| # | finding |
|---|---|
| **R1-5** | **Only a TAIL retirement is expressible.** `never_reuse.rs:91-98`: a shorter table *"can only drop from the TAIL"* because the ordinal **is** the index into a dense prefix. Drop `verb[3]` of 10 and the fold re-densifies 4..9 → 3..8, `check_never_reused` fires, and **the entire epoch switch is refused** including every unrelated change. ⇒ **a reality can never retire anything but its most recently declared verb** — while my own rot ledger repeatedly *deletes* enum variants using a mechanism that cannot delete a row |
| **R1-6** | **`effectiveness` is a MAP and `canon.rs` has no map primitive** — its module doc forbids *"maps with nondeterministic iteration order"* explicitly, and the `Canon` surface is scalars + `seq_len` + `i32_slice`. §2.4's engine/author split lists four engine obligations and **the encoding order is not one of them** |
| **R1-7** | **Sparse-with-a-default gives one behaviour two digests** — an absent cell and an explicit `1000‰` cell are the same behaviour under different pins. **This is `D-PROGRESSION-EMPTY-PIN` returning by the front door**, and no guard can see it because the hazard is **cell-shaped, not ordinal-shaped**: `check_never_reused` compares ordinal→name, and a matrix cell has no ordinal |
| **R1-8** | 🔴 **`Logistic` requires `exp`, which `D-8` names as forbidden hazard 1** (*"transcendental libm functions (sin, cos, exp, ln, powf)"*, [RUN-STATE:545](2026-08-02-actor-substrate-RUN-STATE.md#L545)) — verified — **and the chooser's `argmax` decides which verb is committed**, so it is squarely in the replayed path. **Plus the self-refutation:** IAUS's compensation factor is `1 − 1/n` over the *author-declared* consideration count, so **adding a consideration changes every other score on that verb** — which is **precisely the property §2.2 claimed engine-closing the aggregation would prevent.** My own argument refutes itself |
| **R1-9** | 🔴 **`CurveKind` ALREADY EXISTS** — [`progression/mod.rs:153`](../../crates/ruleset-core/src/progression/mod.rs#L153), re-exported from the crate root ([`lib.rs:67`](../../crates/ruleset-core/src/lib.rs#L67)), with **canon-pinned `u8` discriminants inside the hashed progression table**. Verified. `CMD-9` was raised because `costs` named two things; **`CurveKind` names two things already, one of them shipped and hashed, and neither document noticed.** `D-21`'s defect, in the round that cites `D-21` |
| **R1-10** | **`A-3` made concrete — the provenance hole is three artifacts wide**, and none is a model version: `Dispatch` records tokens/latency/finish_reason/raw_tool but **no `model_ref`, no provider, no version** · `SYSTEM_PROMPT` is a `&str` const in a service binary · `hp_band`'s two hardcoded thresholds decide what state the model even sees. `law_version` does not cover any of it and is *"bumped by hand"*. **The two un-reproducible committed facts are exactly what stages 1 and 2.5 exist to produce** |
| **R1-12** | `renderEvent`'s `DomainEvent` **drops `crit` and `capped`** — and `capped` exists specifically so a bound ceiling is *"a fact in the log rather than a number nobody can explain"*. The projection re-silences it, and the cross-language test asserts the discriminant set, not the fields |

#### What it could NOT break — recorded, because an absent finding is evidence

1. **A new field cannot silently escape the digest.** `CanonEncode for Ruleset` destructures exhaustively with no `..` — adding a field is **E0027, a hard error**. The six new tables *will* be pinned once they exist. **The problem is downstream of the digest, not at it.**
2. **The never-reuse check cannot run against a partial history** — a missing prior returns `PriorRulesetMissing` rather than degrading permissive, with the `NV-3` reasoning stated in the source. *"My finding is that it has one subject, not that the subject is wrongly guarded."*
3. **The check runs before the append** — a refused switch leaves the binding table untouched.
4. **`SeedRole` discriminants are pinned against reordering** — genuinely already right, and the discipline `O-CI-8` would need.
5. **`law_version` fixed the two-builds-one-digest bug** (`QTY-D13`); what survives is its narrow scope and manual bump.
6. **Digest format drift on the wire is refused**, Rust and Go both. *"The `Option` is the problem, not the format check."*
7. **The shipped damage chain's fixed-point order is safe** — all factors multiplied in `i128`, divided **once** at the end. *"My arithmetic complaint is that the NEW chooser and the NEW composition have a data-dependent factor count, not that the existing chain is unstable."*

### 9.7 Red team R3 (implementability) — it audited MY measurements, and found four wrong

#### 🔴 The miscount hid a LIVE instance of the defect this round exists to describe

**`CombatEvent` is 8 variants, not 6.** Verified: `Struck · Missed · Defended · Moved · Fled ·
Downed · **StatusExpired** · **EncounterEnded**` ([payload.rs:44-103](../../services/commit-service/src/domain/payload.rs#L44)).
Both §5 finding 2 **and** structure §1's table carry the 6.

The two I missed are **emitted on live paths** — `law.rs:227`, `:276`, `:295` — and
`grep -rn "status_expired\|encounter_ended" services/game-server/src contracts/` returns **nothing**.
`spine.rs` serialises the whole `Vec<CombatEvent>`; `asDomainEvents` is an **unchecked cast**; and
`renderEvent`'s switch has no arm for either and **no default**, so it returns `undefined` into
`ResolvedDetail.events: string[]`. `noImplicitReturns` cannot see it — the switch *is* exhaustive
over the **declared** union; the cast is what lies.

> **This changes the round's thesis from prophecy to postmortem.** Structure §1.2 and §9 argue *"add
> a verb and you edit that switch"* as a thing that **will** go wrong. **Two events were added and
> the switch was not edited.** It is the current state of the resolved-turn path, one class milder
> than the dead room (an `undefined` in a list).
>
> **And my miscount is what hid it** — 8 ≠ 6 was the tell, and I wrote 6 twice.
>
> The source comment covering it is also false: *"the closed `type` set is asserted in the tests
> rather than trusted"* — `renderEvent`, `asDomainEvents` and `DomainEvent` appear **zero times** in
> `turnOutcome.test.ts` or anywhere in `services/game-server/`. A claim of coverage with no check
> underneath, which is the shape `DR-3` congratulates itself on catching one layer up.

#### 🔴 FATAL-2 — the closure rule is not strained by two; it is **unsatisfied by seven**

The actor round's RUN-STATE says **"No code this round"** (§2 rule 2). So every surface the seven
door-sections name — `ActorQuantities`, `pool_spec`, `threshold_active`, `status_active`,
`lifecycle_machine`, `Residency`, `SlotTable`, `fiction_time`, `EdgeMove`, `wave_budget` — returns
**zero hits in the game tier**.

| | honest verdict |
|---|---|
| doors 1–7 (`Delta`·`StatusPropose`·`EdgeMove`·`LifecycleRequest`·`ClockAdvance`·`Materialise`·`Oracle`) | **design only** |
| door 8 (risk / `role_rng`) | **the ONLY shipped one — and it is not in structure §6's table** |

> *"Structure §6 says five of seven have an unambiguous door. **The honest count is one**, and the
> predicate of the closure rule is really 'a sibling design document has a section about it.'"*
>
> **My self-criticism identified the wrong two.** `EdgeMove` and `Oracle` were called weak for
> attaching to a *rule* and a *classification*. Under the corrected reading `Delta` and
> `StatusPropose` attach to **prose describing an operation nobody has written**, which is weaker.

#### 🔴 FATAL-3 — `role_rng` has no VERB term, so `cast`'s roll collides with `strike`'s

The coordinate is `(session_seed, actor, action_idx, SeedRole)`. There is no verb component, and
`SeedRole` has no member a declared verb could use (`O-CI-8`, correctly found). The consequence
`O-CI-8` missed: a declared verb must **reuse** a role, `Hit` is the obvious one, and then `cast`'s
success roll and `strike`'s hit roll by the same actor at the same `action_idx` are **bit-identical**
— *"precisely what the module doc's own justification describes as the thing to prevent."*

Second half: `action_idx` advances **only in the `Strike` arm** (`law.rs:188-189`). So either every
declared verb advances it — an edit to `law.rs`, the file `D-30` says must not be touched — or verbs
share an index and every verb between two strikes draws the **same number**. And widening the
coordinate means re-keying `SeedRole`, whose discriminants are pinned *specifically so they can never
move*: **the one change in this design that touches replayed history.**

#### Three more errors of mine, recorded rather than quietly fixed

| | |
|---|---|
| **`O-CI-9` cites a STALE DOCSTRING as if it were the code.** | Verified: `hit_chance_pm` reads `rules.hit_base_pm / hit_floor_pm / hit_ceiling_pm` — **all declared and hashed**. The literals I quoted live only in the docstring at `attack.rs:9-10`. Worse, the code comment says *"**That the clamps EXIST is the law; their values are the ruleset's** (IMP-D1)"* — it already implements the exact split this round argues for. **`O-CI-9` is not merely wrong, it is backwards: that function is a positive example, not rot.** And citing a comment as a measurement is the error class this round exists to name |
| **The 10-file count is 4 wrong and 3 short.** | 4 of the 10 name *tuning constants* (`defend_divisor`, `move_base`, `move_max`) that nobody would edit to add `cast`; 3 that **would** be edited are missing (`main.rs`'s hardcoded `"tool":"strike"` payloads, `admission.rs`'s `strike.target` gate, `state.rs`'s `next_action_idx`). **A total reached by two offsetting errors is not a measurement**, and this project treats a miscounted table as a defect |
| **§5's grep is not reproducible as written** | It returns 9 `node_modules` hits for `TargetRef`. The substance is right; §2 rule 7 says the *command* is recorded, and the recorded command does not produce the recorded result |

#### And two findings that HELP, from evidence I never found

| | |
|---|---|
| **MED-7** | [`resource/mod.rs:21-35`](../../crates/ruleset-core/src/resource/mod.rs#L21) is a **shipped precedent** on ordinal spaces — *"a resource does not get an ordinal of its own"* — and the recorded reason is **actor-array width**, not guard cost. Verbs/roles/classifiers/reasons/cues are **not per-actor arrays**, so the reason that killed the resource space **does not apply to them**. `A-5`/`O-CI-5` argued from a design section when the engine had already decided it in code — and the decision **strengthens** this round's case |
| **MED-8** | **`CMD-4` is not new prior art; this repo shipped it one module over.** [`labels.rs:1-27`](../../crates/ruleset-loader/src/labels.rs#L1) is a digest-keyed, overwriting, **unhashed** label sidecar with the argument already written: *"the hashed name is a MACHINE key; its human-readable label is localized content and lives elsewhere. **This is elsewhere.**"* §9 called `CMD-4` the cheapest of the six; it is cheaper still — storage, naming discipline and the i18n argument are all built |

#### 🔑 The sizing — and it inverts what both documents assumed

| layer | size | note |
|---|---|---|
| **L1 · six ordinal spaces** | **~M total, S each** | *"Smaller than the docs think."* `quantity.rs` and `progression/table.rs` are two shipped templates. **The guard is ~20 lines of trait extraction plus one line per space in `epoch.rs`** — `O-CI-5` was *"right that it is real and wrong that it is heavy."* Real cost = five permanent rungs on the digest re-encode ladder |
| **L2 · Parse, Bind** | **L** | `CMD-6`/`CMD-8`'s binding fix is **XS-to-S** and *"the bite-test writes itself"* |
| **L3 · Require, Spend** | **M, blocked** | the evaluator is small; **its subject (`ActorQuantities`) has zero code** |
| **L4 · Adjudicate, Apply** | **XL — and it is NOT this round** | seven doors, every one a first build |
| **L5 · Present** | **XS — the cheapest real win**, and **it fixes FATAL-1 as a side effect** (an ordinal has no unmatched switch arm) |
| **L6 · decision layer** | **M for the tables**; `success` blocked on FATAL-3 |

> **The strategic sentence, and I accept it:** *"The parts the documents treat as expensive are
> mostly built or trivially cloned — the repo has solved the declared-table problem twice and guards
> it in production. The part the documents treat as settled — **a primitive exists iff the substrate
> built the door** — is where all the unbuilt work is. **The round's real deliverable is not a verb
> table; it is the seven doors, and those belong to the actor round, which wrote none of them.**"*

### 9.3 What would make this round's result untrustworthy

Named in advance so it cannot be rationalised afterwards:

- an author agent whose Phase-1 list contains vocabulary from the spec ⇒ **it was not blind, discard it**
- a reviewer returning only findings the documents already admit ⇒ it re-read the register instead of the design
- **all three authors scoring high.** The actor round's four genres returned `7 ✅ · 12 ⚠ · 24 ❌` on its
  first blind pass. A materially better score here, on a **younger** design, is more likely to mean
  the wish lists were tame than that the design is good
- ⚠️ **ADDED AFTER IT HAPPENED, because I did not anticipate it: an agent that scores a design it
  RECONSTRUCTED instead of read.** The occult author's Phase 2 described `CommandDef`,
  `InteractionDef`, `outcome_bands`, `TriggerDef`, `target_kind: self|actor|entity|tile`, and effect
  kinds `adjust_resource / set_flag / grant_item / spawn`. **A grep for every one of those strings
  across `docs/` + `crates/` + `services/` + `contracts/` returns zero files.** It built a plausible
  generic action-system from its priors and scored against that — and the tell was that it *praised*
  a construct (`outcome_bands`) the spec does not contain. **Blindness was verifiable because I
  required the Phase-1 list verbatim; READING was not verifiable, and that was the hole in the
  method.** The fix, applied on the re-run: name the actual identifiers the document contains and
  require the re-read to surface them. **The general lesson is the one this repo keeps relearning —
  a check that cannot fail is not a check.** I verified the half that was easy to verify.
