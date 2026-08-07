# RUN-STATE — game tier: the actor hub's first consumer, then the command substrate

**Opened:** 2026-08-06 · **Base:** `6c075b5b8` · **Status:** CLARIFY, awaiting PO seal
**Predecessors:** [actor round](2026-08-02-actor-substrate-RUN-STATE.md) ·
[command round](2026-08-02-command-interaction-RUN-STATE.md)

> **Re-read this file after any compaction, before `git log`.** Context is lossy; a file is not.
> Nothing here is sealed by its author. Sealing is the PO's, and the seal list is §4.

---

## 0. DEFINITION OF DONE — three axes and an independent verdict

> **The goal is to CLEAR the command substrate**, not to reach `M1`. `M1` is a step inside it.
>
> **Why it is written as pasted evidence:** the `/goal` evaluator **reads the transcript only — it
> cannot run a command or open a file.** It is therefore satisfied by the agent *claiming* a check
> passed. `/goal` enforces persistence, not honesty. Every clause below forces the proof INTO the
> transcript, because a clause that does not is a clause the author grades themselves.

### Axis 1 — CODE (static: does it hold without running?)

| | |
|---|---|
| `A1.1` | `cargo test -p actor-hub -p commit-service -p world-service` green, run fresh, **counts pasted** |
| `A1.2` | the game-server TypeScript suite green, **pasted** |
| `A1.3` | a full pre-commit gate run green, **tail pasted** |
| `A1.4` | greps pasted: `commit-service::domain::Actor` carries **no** `hp` / `max_hp` / `av` / `stats`; `actor_hub::` **is** used by commit-service; **no `match` on a verb name** survives in command core |
| `A1.5` | **the acceptance test exists and runs**: declaring a verb is rows only, and a test asserts **zero files in command core** changed — the actor hub's own test, one level up |
| `A1.6` | **NON-VACUITY, per check**: break it, paste the **RED**, restore, paste the **GREEN**. A check with no pasted red **is not a check** |

### Axis 2 — RUN (does it actually execute?)

| | |
|---|---|
| `A2.1` | a **live smoke on a real stack**: a command submitted → a committed fact on the log → projected to the wire. **Paste the actual ids and payload**, not a description of them |
| `A2.2` | the **refusal path fires on a real refusal** and commits a fact carrying its reason ordinal — pasted. A substrate that only proves its happy path has proved half of `CMD-5` |
| `A2.3` | the **cue channel carries the outcome** and the consumer renders it — pasted |
| `A2.4` | if the stack genuinely cannot boot, say `live infra unavailable: <reason>` explicitly — **and then this goal is NOT met.** The token is for honesty, not for credit |

### Axis 3 — DATA MEASURE (numbers off a real run, not off the design)

| | |
|---|---|
| `A3.1` | **determinism**: the same input replayed twice, **both digests pasted and byte-identical** |
| `A3.2` | the digest **MOVES** when the ruleset changes and **does NOT** move when only provenance changes — **both pasted.** One without the other proves nothing |
| `A3.3` | the fold produces a value **through a populated quantity table** — table size and resolved value pasted |
| `A3.4` | counts pasted: quantities declared · verbs declared · **which doors the verb actually used** (expected: `Delta` only — if more, the closure rule was broken and that must be argued, not assumed) |

### The independent verifier

| | |
|---|---|
| `V.1` | a **cold-start reviewer that did not write the code**, given the diff and told to **REFUTE** it, with its verdict pasted **in full — including what it could NOT break.** An absent finding is evidence and is part of the result |
| `V.2` | a **mechanical oracle**: at least one result computed by a **DIFFERENT method** and shown to agree, pasted. Two implementations of one method is not an oracle |

### What does NOT satisfy this goal

- **Renaming a legacy field into a quantity of the same name.** `quantity[0] = "hp"` passes every
  structural check and changes nothing — it is `D-2`'s failure surviving a refactor that looks like
  progress.
- **Claiming a check passed without pasting its output.**
- **A mock standing in for the live path** on Axis 2.
- **The author reviewing themselves in a different hat** on `V.1`.
- **A check that cannot fail**, however green.

## 1. The commitment

Two milestones, in this order, and the order is **derived rather than chosen** (§2):

1. **`M1` — the actor hub gets its first consumer.** `commit-service`'s domain is **rebuilt on the
   hub, and the legacy combat shape is DELETED** — not ported.
2. **`M2` — the command substrate's first declared verb**, replacing a hardcoded arm in `law.rs`.

> 🔴 **`M1` is a REPLACEMENT, not a migration — PO, 2026-08-06.**
> *"`hp` and friends are old src, rubbish too. Back then we only built to prove the kernel and the
> SDK could work, so dealing with them is right."*
>
> This is `D-11` (*the shipped engine is scaffolding and may be broken freely; zero production
> realities exist*) and `D-14` (*combat vocabulary is out of scope and will be rewritten*), stated
> again by the person who took them. **So `M1` does not port `hp` into a quantity one-for-one.** It
> declares the quantities the design needs and **deletes** `Actor`'s field list, `CombatStats`,
> and whatever else in the combat domain exists only to hold them.
>
> The distinction is load-bearing, not stylistic. A port preserves the old vocabulary in a new
> container — which is `D-2`'s exact failure (*a hardcoded noun is a manifest that cannot grow*),
> survived through a refactor that looked like progress. **Porting `hp` to `quantity[0] = "hp"`
> would satisfy every test and change nothing.**

**Done means:** a verb declared as a manifest row resolves end to end against a hub-backed actor,
with the refusal path and the presentation channel both real, and every check bite-tested.

## 2. The ordering is forced, and here is the measurement that forces it

Measured at `6c075b5b8`:

| | |
|---|---|
| `crates/actor-hub` | built, **91 tests green**, and **zero consumers** — no `Cargo.toml` in the workspace depends on it, `actor_hub::` appears nowhere outside the crate, and the only thing constructing a `DerivationRow` is `examples/two_plugins_fold.rs` |
| `commit-service::domain::Actor` | **live scaffolding, and it is `D-3`'s own subject**: `hp: i64` · `max_hp` · `defending` · `stance` · `fled` · `side` · `av` · `status` · `knocked_out`. **To be deleted, not carried** — see the PO note in §1 |
| the command substrate | **0 % implemented** — zero hits for `verb_declarations`, `VerbDeclaration`, `RequirementRow`, `EffectRow`, `offers_for`, `conflict_resolutions` |

**Why `M1` must precede `M2`.** A declared verb's `EffectRow` targets a **quantity ordinal**. While
an actor's numbers are struct fields, an effect cannot name one without a `match` arm per noun —
which is `CMD-6`'s defect, re-created by the very table meant to remove it. So the substrate cannot
be declarative until the actor's nouns are quantities.

**And `M1` does not need `M2`.** `law.rs` keeps driving changes, hardcoded, but operating on
quantities instead of fields. Each milestone is independently verifiable, which is the point.

> ⚠️ **A hub with no consumer is the shape this repo has already been burned by.**
> `scripts/orphan-model-gate.py` exists because seven `pc_*`/`npc_*` projection tables shipped with
> a projector, a rebuilder, a golden fixture, an independent oracle and a benchmark — and **no
> producer at all**. `M1` is what stops the actor hub becoming the same finding one layer up.

## 3. The door accounting — measured 2026-08-06, and it decides `M2`'s scope

`CMD-3` says an effect is a row from a closed primitive set, and the rule that makes the set
non-arbitrary is *"a primitive exists **iff the substrate already built the door** it goes
through."* `FATAL-2` found the rule unsatisfied by seven of eight. Re-measured at HEAD — nine of
its ten named surfaces still return **zero hits in the game tier**, and the tenth (`fiction_time`)
is in `tilemap-service`, an unrelated concept sharing a word:

| door | at HEAD |
|---|---|
| **`Delta`** | ✅ **BUILT** — hub quantities, `ModifierRow`/`DerivationRow`, the three-pass `fold`, `OpKind{Flat,Percent}` |
| `StatusPropose` | prose — `status_active`, 0 hits |
| `EdgeMove` | prose — 0 hits. The item round *designed* the holder graph; it is unbuilt, which is **buildable, not blocked** |
| `LifecycleRequest` | prose. `GoneState` is real but it is **entity existence** (severed/archived/dropped/user-erased) — a different ladder from a game lifecycle |
| `ClockAdvance` | prose — `fiction_time`, 0 hits in the game tier |
| `Materialise` | prose — `Residency`, 0 hits |
| `Oracle` | prose |

⇒ **One door of seven is open, and it is exactly the one the actor hub built.**

**Therefore `M2`'s first verb is `Delta`-only** — which is not a compromise, it is the sub-language
the round independently measured as working today: *"`/sleep · give · poison · execute · summon ·
fixed heal` — a verb fits when every number is a constant, it touches one other actor, takes no
parameter, and needs no state between two actors."* Two measurements, no contact, one answer.

## 4. The seal list — PO decides, author does not

### 4.1 The condition that blocked `CMD-1`..`CMD-6` is DISCHARGED

The PO declined to seal *"pending prior art"* and directed a research pass. It ran, three times:
08-02 §3's six systems (The Sims · GAS · Inform 7 · Caves of Qud · Evennia · lockstep) · round 2's
decision layer (IAUS · Pokémon/WC3 classifier matrices · GOAP · the shipped RNG door) · and the
2026-08-05 round, which turns out to have been that directed pass performed blind, now folded.

**A second blocker replaced it and is not discharged**: `F-8` (the classification test could not
fail) → `V1/V2/V3` → `R4` (the replacement passes anything given a flag set). `CMD-10` proposes the
repair. **So the seal ORDER is forced: `CMD-10` first, then `CMD-1`..`CMD-6`.**

### 4.2 What is asked of the PO

| # | ask | note |
|---|---|---|
| **`CMD-10`** | seal the fourth question — *operand, not predicate* | **owes a bite** (author a member that sets an authority-bearing field; assert the build refuses it). It was deferred by `8b`'s design-only rule; `M1`/`M2` lift that, so the bite is now doable and should land **with** the seal, not after |
| **`CMD-1`..`CMD-6`** | seal, re-scored under `CMD-10` | `R4-5` said `CMD-1` is mechanism by its own test; `CMD-10`'s score-versus-rank boundary dissolves that. Re-scoring is the author's job, the verdict is the PO's |
| **`CMD-11`** | the offer registry, in commit-service | needed by `M2` only if the first verb takes a target. A `Delta`-only verb on the actor itself does **not** need it — so this can seal after `M2`'s first slice |
| **`CMD-12`** | keyed-MAC `offer_id` | ⚠ **the load-bearing hole is elsewhere** — `actorForUser` returns `LW_CHANNEL_DEFAULT_ACTOR ?? '1'` for any authenticated user absent from the env map, so two users are legitimately bound to one subject. A MAC over a subject the caller can already be is a lock on the wrong door. **Fix the subject source first** |
| **`CMD-13`** | horizontal composition | needs **two bundles** to have a subject. `M1`/`M2` have one. Seal the *mechanism* now if the PO wants it fixed cheaply, or park it until the second bundle — both are defensible |
| **`O-71`/`C-0`** | the signed arrow | carried from the actor round, *"the whole gate"*. Now priced: quantity → **value** is shipped and signed; quantity → **ceiling** is what is missing |

### 4.3 Decisions with no derivable answer — these need the PO, not more analysis

| # | question |
|---|---|
| **`O-CI-24`** | **where is a `conflict_resolutions` row authored** — a third reconciling bundle, or the reality that assembled the pair? |
| **`O-CI-25`** | does `strict` earn a member of the merge-strategy set? Cheap to add later, expensive to remove |
| **`O-CI-7`** | **one table or two.** `/sleep` leaves four of six new columns inert, and a row whose normal state is mostly inert is the *"29 accreted fields are FOUR kinds"* signal |

## 5. Where the deep dive goes — four, and each is named for a reason

Not a wish list. Each of these **blocks writing code**, and inventing an answer under time pressure
is the failure mode this project has recorded most often.

1. **The effect primitive set, and the six unbuilt doors** (`C-1` · `O-CI-1` · `FATAL-2`). The
   round calls this *"the round's real unknown"* and §3 prices it: one door of seven.
   
   > 🔴 **The question is NOT "should the substrate build doors" — PO, 2026-08-06.**
   > **A door belongs to the FEATURE that owns it.** `Delta`'s door was built by the actor hub,
   > which is feature #1; `StatusPropose`'s belongs to a **status feature**, which does not exist.
   > The substrate does not open a door — it *gains a primitive* when a feature opens one.
   >
   > The phrasing this replaces was *"build doors, or narrow the primitive set"*, which reads as
   > substrate work and is the same boundary violation `SCOPE-2` already refused once: designing
   > the chooser inside the substrate because the substrate is the thing being written. **The
   > author proposed it a second time, in a different costume, and the PO caught it again.**
   
   So the real question is narrower and it is the substrate's: **what does a primitive's row look
   like, such that a feature can open its door without the substrate learning what the door
   means?** That is answerable now. Which doors open, and when, is the features' — and `M2.3`
   therefore waits on feature #3, not on more substrate.
2. **`O-CI-16` — six types are named and never defined**: `ChanceSpec`, `InputKind`, arity's home,
   pair `subject`, the two-role `EffectRow`, `RefKindMask`. **Every `consideration` and every
   `success` row in a real manifest rests on an invented shape.** You cannot write code against a
   name. This is definition work rather than research, but it is genuinely undone.
3. **`O-CI-10` + `O-CI-11` — instance-level pair state, and its arity.** Twelve findings are one
   absence. No longer blocked on `O-71` (the magnitude it needs is shipped), but the real
   constraint is narrower and was found by measurement: **derivations read pass-1 values, so there
   is no derivation chain.** The open question is *where the bind-time projection lands in the
   fold* — and `O-CI-11` asks what happens at arity 3 (`believes(A, "B did X")`), where
   `O(arity^n)` stops being cheap.
4. **`O-CI-3` + `FATAL-3` — the roll.** `attack.rs` uses `SeedRole::Hit` **and** `SeedRole::Crit`
   inside one attack while the design's flat `gate` expresses one; and `role_rng` has **no verb
   term**, so `cast`'s roll would collide with `strike`'s. Fixing that touches **pinned replayed
   history**, which is why it is a dive and not an edit.

Honourable mention, because it will arrive on the first content request rather than the first
build: **`O-CI-21` — the dependency graph is acyclic BY ACCIDENT.** `statuses ⟷ thresholds` becomes
a real, unbreakable cycle the moment an author wants *"while `blood_low` is active, lose 3 blood
per tick"*. It is acyclic because a capability is missing, not because it was designed to be.

## 6. Slice board

`done` is an **evidence string**, never a tick.

| # | slice | evidence | state |
|---|---|---|---|
> 🔵 **Checked before opening `M1`, because getting it wrong would rebuild `D-3` one layer up:**
> `ruleset-core` and `actor-hub` are **not two parallel declaration systems — they are layered, and
> the layering is already correct.** `actor-hub` depends on `ruleset-core`;
> `ruleset-core::QuantityTable` holds the **names** (hashed, pinned) and `ResourceDecl` holds a
> pool's semantics against a `QTY-A5` ordinal; `actor-hub::QuantityDecl` is `{ ordinal, initial }`
> with **no name**, and `PluginDecl` carries *"no name, no kind, and no behaviour, because the hub
> knows nothing about what any of it means."* That is `D-2` running as designed: **the manifest
> closes on VOCABULARY, the engine closes on MECHANISM.**
> ⇒ **`M1` invents no plugin vocabulary.** The quantities are the ruleset's; the hub attaches and
> folds them. **But `QuantityTable::EMPTY` is the shipped default** (*"the engine declares
> nothing"*), so `M1` must also **populate a reality's quantity table** — that is content, and it is
> a real sub-task rather than a given.

| `M1.0` | **inventory what the legacy combat domain actually holds, and mark each: DELETE · re-declare · genuinely load-bearing.** The default is DELETE; anything claimed load-bearing needs a reason a reader can check | §6a below — 12 fields, each with a measured call-site count and a verdict | [x] |
| `M1.1` | declare the quantities the DESIGN needs — **derived from the design, never read off the old field list.** A quantity named because a struct field was named is the port this milestone refuses | `crates/ruleset-loader/artifacts/presets/proving-ground.toml` declares `vitality` · `swiftness` · `breath`, bound to `vital` · `initiative` · `action_budget`. **None is the name of the field it replaced**, deliberately: a rename would have satisfied every check, and different names make a surviving name-coincidence impossible | [x] |
| `M1.2` | `commit-service` depends on `actor-hub`; the domain resolves an actor through the hub's fold | `services/commit-service/Cargo.toml:40` + 12 `actor_hub::` sites. `A3.3` pasted: table size 3, stored fold 100, fold with a `+25` contribution 125 | [x] |
| `M1.3` | the legacy shape **deleted** — `Actor`'s field list, `CombatStats`, and whatever exists only to hold them. Deleted, not commented out | `grep -nE "^\s+(pub )?(hp\|max_hp\|av\|stats\|snapshot\|turn_slots)\s*:" domain/actor.rs` → **exit 1, no match**. `Actor` is now `{ hub, defending, stance, fled, side, status, knocked_out }` | [x] |
| `M1.4` | bite: delete a `QuantityDecl` and watch the consumer red | Bitten on **CONTENT**, which is stronger: the `action_budget` pool commented out of the preset → `RoleUnbound { role: "action_budget" }` at [`services/commit-service/src/domain/binding.rs:277`](../../services/commit-service/src/domain/binding.rs#L277), three suites red. Restored → 7/7 green | [x] |
| `M1.5` | **a vocabulary check with teeth**: no game noun re-enters the engine tier as an identifier. `hub-vocabulary-gate` already asserts the hub names no ordinal — extend it, or state why it cannot reach the consumer | **A NEW gate**, not an extension — different tree, different subject, opposite direction (see below). `scripts/engine-vocabulary-gate.py`, 89 files across 6 trees, self-test 13 cases, **6/6 harness mutations red**, and bitten on the real repo: a planted `name == "vitality"` in `law.rs` → 1 finding; removed → OK | [x] |
| `M2.1` | `CMD-10`'s owed bite, landed with its seal | `FORBIDDEN_VERB_KEYS` — three authority-bearing keys refused **by name, with the reason**, on the permissive parse before deserialization. Pasted: all three refusals name the verb, the key and why. `deny_unknown_fields` would have said *"unknown field"*, which is true and useless | [x] |
| `M2.2` | the verb row, `Delta`-only, as a declared table | `ruleset-core/src/verb/` — hashed, schema **6 → 7**, ordered by DECLARATION (`CMD-1`: an ordinal is the verb's identity). `EffectRow` has **no `kind` field**: one door is open, so there is nothing to discriminate, and the exhaustive destructure in `data_measure.rs` stops compiling when a second opens | [x] |
| `M2.3` | one `law.rs` arm replaced by a declared row | ⚠️ **NOT discharged, and the measurement is why** — see §6c. **No shipped arm is `Delta`-only.** What landed instead: the substrate has ONE arm for every verb that will ever exist, and the first declared verb is a new one | [~] |
| `M2.4` | refusal as a committed fact (`CMD-5`) + the cue channel (`CMD-4`) | Live, on real Postgres: `channel_event_id=7 {"actor":"1","reason":"requirement_unmet","type":"refused","verb":0}` · the cue reaches the client payload, parsed out of `TurnOutcome`'s narration | [x] |
| `A1.5` | **the acceptance test** — declaring a verb touches ZERO files in command core | `adding_a_verb_touches_zero_files.rs`, 7 tests. A verb declared in a TOML **string inside the test** resolves end to end; its cue reaches the fact; the tool manifest does **not** know it and it resolves anyway | [x] |
| `A2.*` | the live smoke | `scripts/declared-verb-live-smoke.sh` — **GREEN.** 7 rows read back out of Postgres, every one carrying its `ruleset_digest` pin; applied at `channel_event_id=5`, refused at `7`, wire payload pasted | [x] |
| `LIM-1` | **a hard ceiling becomes ingested DATA, not a magic number in the world engine** (PO — see the Decisions register) | `ruleset-core/src/limits.rs` + `ruleset-loader/src/patch_limits.rs`. **19 tests** (13 loader, 6 core) and **10/10 bite mutations RED**, including *"the shipped proving-ground `[limits]` block is load-bearing"* and *"`size_of::<Ruleset>()` is pinned with no slack"* (→ `error[E0080]` at `<= 6959`). `MAX_DECLARED_VERBS` 16 → **64**, repin 3696 → **6960**. Two files paid `IMP-D3`'s ceiling in **splits** rather than allowlist rows (`ruleset_size.rs`, `patch_limits.rs`) | [x] |
| `V.2` | the mechanical oracle | `scripts/declared-verb-oracle.py` — **AGREE.** Python · the preset parsed as TEXT · a running sum over rows read back from the log. Shares no method with the engine's fold-and-write | [x] |

## 6a. `M1.0` — the inventory, measured at `fa15b072f`

Counts are `grep -c '\.<field>\b'` across `services/commit-service/{src,tests}`. **The default
verdict is DELETE**; a row that survives says why in terms a reader can check.

| field | sites | verdict | the reason, checkable |
|---|---|---|---|
| `snapshot: StatSnapshot` | **0** | **DELETE outright** | Written twice, both `StatSnapshot::default()`; **read nowhere, not even in a test.** Its own doc-comment already passed this sentence on itself: *"written at construction and read nowhere outside tests today… if those land without consuming it, it must go."* They did not land. This is `orphan-model-gate`'s finding shape in a struct field. |
| `hp: i64` | 20 | **re-declare as a POOL** | `QTY-A4` (shipped, `resource/mod.rs:13`) already says a resource's `current` *"lives on the actor (`pools[ordinal]`)"*. **That slot has never existed.** `actor_hub::Actor::quantities` is it. |
| `max_hp: i64` | 2 | **DELETE — it is a CEILING, and the ceiling is already declared** | `CeilingBinding` exists and is hashed. A stored `max_hp` beside a declared ceiling is two SSOTs for one number. Both remaining sites are `llm_driver`'s display band. |
| `av: i64` | 9 | **re-declare as a QUANTITY** | A per-actor number that changes every turn and is **not** a stat slot — tempo state. It cannot be derived (the HSR advance subtracts it from everyone), so it must be stored, and the hub's array is where per-actor numbers live. |
| `stats: CombatStats` | 8 | **DELETE the FIELD; derive at use** | It is `CombatStats::archetype_melee(&rules.stats, max_hp)` — a pure function of the pinned ruleset and the ceiling, both available wherever it is read. A stored copy of a derivable value is the freeze the doc claims, implemented as duplication. **The TYPE survives** — see `M1-D3`. |
| `turn_slots: i64` | 6 | **re-declare as a POOL** | `state.rs` already calls it a *resource* (`CombatResource::TurnSlot`), and `ZeroBehaviour::BlockCosts` — *"refuse any action whose cost this pool cannot pay"* — is shipped, unused, and is exactly its semantics. Ceiling `Fixed(1)`. |
| `defending: bool` | 8 | **stays, recorded** | Non-numeric. It is the `StatusPropose` door, and §3 measures that door as **prose, 0 hits**. Porting it into a quantity would invent the door's shape from feature #1's chair. |
| `stance: Option<Stance>` | 2 | **stays, recorded** | Same. Also `TG-A4`, whose owner is `COMB_002`. |
| `fled: bool` | 3 | **stays, recorded** | Same, plus it is the island-handoff trigger (`externals`). |
| `knocked_out: Option<u8>` | 8 | **stays, recorded** | Same door, and it is a round counter, not a pool. |
| `status: AvStatus` | 4 | **stays, recorded** | Same door. |
| `side: Side` | 1 | **stays — genuinely load-bearing** | `COMB_001 Q5`: win/lose is evaluated per side, so an actor with no side can never be counted and the encounter can never end. Structural, not a number. |

⇒ **one outright deletion · four re-declarations · six recorded as the unbuilt `StatusPropose`
door · one structural.** `Actor` ends with **no `hp`, no `max_hp`, no `av`, no `stats`.**

### The three decisions this inventory forced

| # | |
|---|---|
| **`M1-D1`** | **The seam is SHIPPED and `M1` connects it — it does not invent one.** `QTY-A4` places a pool's `current` on *"the actor (`pools[ordinal]`)"* and the actor's array did not exist; the hub built it. So `M1` is not "add quantities to the actor", it is **wire QTY-A4's `current` to `actor_hub::Actor::quantities`.** That is why this milestone is derivable rather than designed. |
| **`M1-D2`** ⚠️ **SUPERSEDED by the build — see `M1-D2b` below.** | **Which ordinal is the vital is declared by CONTENT, through a binding that already ships and costs ZERO new hashed bytes.** `resource/mod.rs:103` states `Q2`'s exit criterion verbatim — *"a reality binds `Vital → qi` and the defeat law is **unchanged**"* — and `Vital` as a role has **exactly one occurrence in the repo: that comment.** It is unbuilt, which per the anti-laziness rule is *buildable*, not blocked. It is built as a **derivation, not a field**: the vital is *the pool whose `CeilingBinding` is `Slot(StatSlot::MaxHp)`*, which is the sentence `CeilingBinding::Slot`'s own doc already writes. Adding a `role:` field to `ResourceDecl` was rejected — `QTY-A10(c)` makes a hashed field permanent, and the module refuses `deps`/`tags` on that exact argument. **Zero, or two or more, is a boot REFUSAL naming the pools** — never a default. |
| **`M1-D2b`** ⚠️ **THE REVERSAL, recorded where the decision is, not only where the build is** | **`M1-D2` was overturned during `M1` and shipped the way it explicitly rejected: `ResourceDecl` gained `role: EngineRole`, schema 5 → 6.** The derive-from-`CeilingBinding` shortcut was dropped because it gives `ceiling` a second, hidden meaning (an author capping a second pool at `MaxHp` silently acquires a second vital) and because the two roles with no matching slot — `Initiative`, `ActionBudget` — have no honest key at all under it. **A cold-start reviewer found `M1-D2` still reading as sealed while the code said otherwise, which is exactly the stale-register defect this run has now recorded five times.** §6b row 1 carries the full argument; this row exists so a reader who re-reads the DECISION gets the right answer, per the run-state's own rule: *never re-litigate a sealed decision from memory; re-read it.* |
| **`M1-D3`** | **`M1` does NOT turn the ten `StatSlot`s into quantities, and that restraint is the decision.** `slots.rs` says the closed slot set is `DF7-A1`, and that doc 31 **`R02`** — *making the slot set ruleset-declared with digest-pinned ordinals* — is **PROPOSED, not applied**, adding: *"applying it here would be scope creep into a decision still open."* Storing the eight numbers as quantities would apply `R02` by the back door, under a milestone that is not about slots. So `CombatStats` survives **as `game-rules`' law-input view**, built where it is read; what dies is the actor's stored copy. **The finding this surfaced is recorded, not acted on:** `game_rules::stats::resolve_block` and `actor_hub::fold` are the same mechanism implemented twice, which is `D-3`'s *"same rot at three levels"* pointing at a fourth. Its trigger is `R02`. |

> ⚠️ **The trap this inventory was written to avoid, stated so it can be checked against the result.**
> Every re-declared row above names a quantity whose **name is authored in CONTENT and appears
> nowhere in engine source** — the engine holds ordinals and resolves the vital through a *binding*,
> not through a literal. That is the discriminator between this and `quantity[0] = "hp"`, which the
> PO named as the thing that would satisfy `M1` while changing nothing. It is not a matter of
> intent: `M1.5`'s gate is what makes it hold, and intent is not a mechanism.

## 6b. `M1` — what it cost, and the four things it forced that were not in the plan

`M1` is **DONE**. What it needed that §6's board did not anticipate is the part
worth recording, because each was a hole the plan could not see from outside.

| # | forced | |
|---|---|---|
| **1** | **`Vital` had to be BUILT — it existed as one prose sentence.** `Q2`'s exit criterion (*"a reality binds `Vital → qi` and the defeat law is unchanged"*) was written in `resource/mod.rs` and `Vital` appeared **nowhere else in the repository**. So `ResourceDecl` gained `role: EngineRole` — a new hashed field, schema **5 → 6**. It earns its permanence by the module's own test: `deps` and `tags` were refused for having **no consumer**, and this one has three engine laws reading it in the commit that adds it. The engine default's ENCODED size is unchanged (it declares no pools); the digest moved only because the schema version leads the stream, which is what that field is for. |
| **2** | **The hub had NO WRITE VERB, and its own doc said so.** `actor.rs` read *"no mutation verb for a quantity beyond attachment… every one of those features is unbuilt."* `M1` is the first one. `Actor::set_quantity` carries a value and refuses a writer that does not own the ordinal — the same shape as `set_existence`, and the door `M2`'s `Delta` walks through. **It made `attach`'s ownership guard observable for the first time**, exactly as that guard's comment predicted; the prediction held on the first try (bite pasted). |
| **3** | **`Actor.stats` was 64 bytes of duplicated ruleset, per combatant.** Every actor's block came from `archetype_melee(&rules.stats, max_hp)`, so the only per-actor difference was `CombatStats::max_hp` — and **no law reads that field**: `resolve_attack`, `action_value` and `evaluate_outcome` never touch it. One archetype per reality now. `Actor` went from ≤192 bytes to ≤160 **despite** gaining a 128-byte quantity array. |
| **4** | **A behaviour genuinely regressed, and it is tracked rather than glossed.** Per-actor stats no longer exist, so a per-actor `speed` cannot be expressed — the one test that used it (to make a hero act first) now sets the initiative pool directly, which is what it was reaching for. The advantage lasts until that actor's first reset instead of forever. `D-PER-ACTOR-STATS-UNEXPRESSIBLE`. |

**`M1.5` is a NEW gate rather than an extension of `hub-vocabulary-gate`, and the
distinction is the point.** That one guards `crates/actor-hub/src` and asks *does
the hub compare an ORDINAL to a literal* — the plugin's ordering vocabulary
leaking INTO the hub. This one guards the consumer and asks *does engine source
contain a quantity NAME* — the author's vocabulary leaking into the engine.
Different tree, different subject, **opposite direction**. Both were structurally
true and unguarded.

**Two ceilings were paid in SPLITS rather than absorbed into an allowlist**, which
is what a ceiling is for: `island/mod.rs`'s read surface → `island/view.rs` (its
row's fourth split in four slices), and the loader's shipped preset →
`ruleset-loader/src/preset.rs` (mechanism ↔ content, the only content file in
that crate). `actor.rs`'s unit tests became integration tests, which is an
improvement rather than a dodge: every item they touch is public surface, so a
unit test could pass against an API a plugin author cannot reach.

## 6c. `M2` — the measurement that changed the milestone, and what landed instead

**`M2.3` said *"one `law.rs` arm replaced by a declared row"*. It is NOT
discharged, and the reason is a measurement rather than an excuse.**

`CMD-3` closes the effect primitive set on *"a primitive exists iff the substrate
already built the door it goes through"*, and §3 measured **one door of seven
open** — `Delta`, a signed write to a declared quantity. Measured again at the
moment of building, against the four shipped arms:

| arm | what it changes | door |
|---|---|---|
| `strike` | a roll, then a vital delta, then a KO status | needs `ChanceSpec`, one of `O-CI-16`'s five undefined types |
| `defend` | a `bool` | `StatusPropose` — **prose, zero implementation** |
| `move` | an `enum` | `StatusPropose` |
| `flee` | a `bool` | `StatusPropose` |
| `EndTurn` | engine-only | never a declared verb, by construction (`IAS-D6`) |

⇒ **Not one of them is a pure `Delta`.** So `M2`'s first verb could not have
replaced an arm without opening a second door — which the closure rule forbids
until the door is built. The rule did its job; the plan's phrasing was written
before the measurement existed.

**What landed instead is the stronger half of what `M2.3` was for.** `law.rs`
has ONE arm for declared verbs, and it will never gain another: it routes to
`domain/substrate.rs`, which resolves every verb that will ever exist without
branching on a name. The four legacy arms are the combat vocabulary `D-14`
already slates for rewrite; they leave when their doors are built, and
`adding_a_verb_touches_zero_files.rs` is what makes the claim checkable now
rather than then.

### Three things `M2` forced that the plan did not anticipate

| # | |
|---|---|
| **1** | **A declared verb may not spend the ACTION BUDGET, and a test found it, not a design.** The engine spends that pool generically on every action (`IAS-D6`); the first authored verb declared the same cost, and it **refused itself with `RequirementUnmet` on its own first submission**. `BindingError::VerbSpendsEngineBudget` now says so at BOOT. The preset gained a role-free pool (`focus`) for verbs to spend — which is also the first demonstration that `EngineRole::None` is the common case. |
| **2** | **`EffectRow` has no `kind` field, and that is a decision.** A one-variant enum would put a discriminant byte in every reality's hashed bytes forever, encoding a choice that does not exist — and `QTY-A10(c)` forbids taking it back out. The kind arrives with the second door, as a schema bump, which is loud and is supposed to be. The count is kept by the COMPILER: an exhaustive destructure in `data_measure.rs` stops compiling when the field appears. |
| **3** | **`VerbTable` is ordered by DECLARATION, not sorted — the opposite call from `ResourceTable`.** A pool's identity is its quantity ordinal, assigned elsewhere, so that table can sort for a canonical encoding. A verb's identity IS its index (`CMD-1`, append-only, never reused) and committed history already names one; sorting would renumber every verb the moment an author added one whose name sorts earlier. |

### And a pre-existing RED, fixed in passing

`cargo build --all-targets` had been failing on this branch since migration
`0018` removed the `region`/`session`/`world_kv` projections as orphans and
deleted their fixtures: `services/world-service/benches/projection_hotpath.rs`
still named all three. **Nothing caught it because a bench is not built by
`cargo test`** — which is worth recording as its own small finding.

## 6d. `V.1` — the cold-start refuter found TEN, and six of them were real bugs

A reviewer that did not write the code, given the diff and told to **REFUTE** it,
working from a scratch crate outside the repo and editing nothing. **Every suite
was green when it started.** That is the whole argument for the clause.

| # | what it broke | fix |
|---|---|---|
| **1** | **A verb naming a quantity with no POOL committed a LIE.** `VerbTable::declare` validates against the QUANTITY table; an actor holds a number only for a declared POOL. So the verb passed every build check, wrote nothing, and committed `Acted { left: 5 }` for a quantity the actor does not have. *A silence would have been bad; a committed lie is worse* | `BindingError::VerbNamesUndeclaredPool` at boot, **plus** the substrate refusing rather than `unwrap_or(0)` — two layers, because a check whose only defence is another check's correctness is one edit from being wrong |
| **2** | **UNLIMITED FREE ACTIONS.** A verb whose `effect` targeted the action-budget pool: the engine deducted 1, the verb added it back. Four submissions, no turn boundary, budget never fell. `IAS-D6` defeated by content, boot-time-green | the refusal now covers **all three positions** |
| **3** | **The original bug still shipped.** The refusal's own docstring cited a `requires` incident while covering only `spend` — and the symptom it quoted (`RequirementUnmet` on the first submission) *cannot come from a spend at all*, which returns `CannotAfford`. **It was aimed at the wrong arm of the bug it was written for.** | same refusal |
| **4** | **Three SILENT paths**, under a header reading *"Every path commits a FACT"*. Out of budget, absent actor, resolved encounter → empty event vector → the spine committed `turn.resolved` with `events: []`, a turn that resolved into nothing. `RefusalReason::ActorAbsent` was **dead code**: the substrate had an arm nothing could reach | `refuse_declared`; `EncounterResolved` added (5 → 6 members, all three sides) |
| **5** | **`EffectRow::amount`'s "the engine clamps against the pool's own declared bounds" was FALSE.** It was `.max(0)` — a hardcoded floor ignoring `ResourceDecl::min`, and **no ceiling at all**. A pool of ceiling 100 driven to **15100** in three submissions | `RealityRules::pool_bounds`, and both the effect and the affordability test now read it |
| **6** | **Content could disable combat.** The verb table is consulted before the manifest and nothing refused a collision, so a preset declaring `strike` silently replaced the engine's attack with a self-targeted delta and dropped the target argument | `Reject::VerbShadowsTool` — refused, never resolved by precedence, because preferring either side makes the other silently lose |
| **7** | **`size_of::<Actor>() <= 160` did not fire on a new field.** 153 used in 160 allocated — **seven bytes of free growth** under a comment claiming otherwise. The hub's own `== 144` next door survived every attack | `== 160` |
| **8** | **The `QTY-A11` round-trip was true and UNTESTED at exactly the two versions this work added.** Every codec test uses `engine_default`, which declares zero pools and zero verbs — so the v6 role byte and every byte of the verb-row codec were never executed. `ROLE_SINCE` 6 → 5 reddened nothing | a round-trip over the shipped preset at every version, and the two length gates. **The mutation now reds** |
| **9** | **The live smoke reported `ok` when it did not run** — the skip's `eprintln!` is swallowed without `--nocapture`, so CI could not tell "smoked against Postgres" from "never touched a database". It also asserted `verb` and `cue` and **not** `delta`/`left`/`quantity`, so finding #1's fabricated `left` would have passed it | `REQUIRE_LIVE=1` (set by the script) turns a missing DSN into a failure; the three numbers are asserted, `left` against the declared bounds |
| **10** | **The oracle's stated check (4) was a TAUTOLOGY** — *"refusals carry no `delta` field"* is true by construction. In the one artifact whose whole premise is method-independence | the stream is walked and the vital is compared either side of each refusal |

**And the finding with no bug attached, which is the sharpest one.** The
acceptance test's *title* claims *"adding a verb touches zero files in command
core"*; what it asserted was *"one verb resolves end to end"*. Adding
`match verb { 0 => …, _ => … }` tomorrow would have left all seven green — and
`substrate.rs`'s header said *"if either appears, the acceptance test is false"*,
which **nothing checked.** `the_substrate_never_branches_on_a_verb` reads the
source at runtime and is bitten: a planted `verb == 0` reds it.

### What it tried and could NOT break — an absent finding is evidence

| attack | verdict |
|---|---|
| `engine-vocabulary-gate` | **SURVIVED the rule**, and its `[a-z][a-z0-9_]*` matches `QuantityName`'s charset exactly, so no legal quantity name evades it. Evasions found were contrived (`concat!`, `\u{79}`, byte arrays). **But it recorded two gaps in the gate's SCOPE, and both are now closed — see §6e.** |
| `QTY-A11` itself | **SURVIVED.** Holds at every version 1..=7, for `engine_default`, for the preset, and for a two-verb ruleset. Its COVERAGE was the defect, not the property |
| `actor_hub::Actor`'s `== 144` | **SURVIVED.** Exact; any field addition moves it |
| `FORBIDDEN_VERB_KEYS` | **SURVIVED**, and the refutation it tried is worth recording: *"`deny_unknown_fields` already rejects these, so the by-name refusal is decoration."* Measured false — that path never emits the VERB's name, which is what the test asserts. It also noted the `len() > 120` assertion alone would not bite (272 > 120); the name assertion is the load-bearing one |

## 6e. The gate's own scope was the defect it exists to refuse

`V.1` did not break `engine-vocabulary-gate`'s RULE. It broke its **scope**, in
two ways, and both are the shape the gate's own header condemns three paragraphs
above the code that had it.

**The scope was a hand-written list of directories.** The header says an
enumerated FILE list is *default-uncovered* — *"it says nothing about the file
created tomorrow"*. A directory list has the same defect one tier up: nothing
checked it against the dependency graph, so a crate created tomorrow that depends
on `ruleset-core` would be silently unguarded while the gate reported OK.

**It is DERIVED now** — every `src` tree whose `Cargo.toml` transitively reaches
`ruleset-core` or `actor-hub` through path dependencies. Those are exactly the
trees that can hold a quantity ordinal, so they are exactly the trees that could
name one instead; adding such a dependency extends the gate **in the same edit
that creates the risk.**

> **And the derivation caught the list being WRONG, not merely unchecked.** The
> hand-written version named `crates/sim-core/src`. `sim-core` does not depend on
> `ruleset-core` — `ruleset-core` depends on IT — so it can never hold a quantity
> ordinal. Six listed trees became **five derived** ones. A list I wrote by eye,
> defended in a header about lists written by eye.

**And the scope was `.rs` only** — while *the wire is exactly where `M2` worked
hardest to carry ordinals instead of names*. `contracts/game-wire/*.json` and the
TypeScript consumer that mirrors it were unguarded. Both are scanned now: 98
files became **108**.

**Bitten three ways, each pasted:** a quantity name planted in
`turnOutcome.ts` (a file the gate could not previously see) → 1 finding; a probe
crate depending on `ruleset-core` → 1 finding, where the hand-written list would
have been silent; and the harness, now **10/10 mutations red**, including *the
scope reverts to a hand-written list* and *the transitive closure stops*.

**Three of its own claims were also untested, and are now executed rather than
described:** `main()`'s empty-vocabulary refusal (`E1` stopped at `scan_source`
and *said in a comment* that main refuses — a claim about a branch nothing ran),
and both arms of the file walk, including the `--staged` path that pre-commit
actually uses.

## 6f. The features are NOT circularly dependent — and one artifact says why

The question, from the PO: *the missing pieces hook back into the actor hub, the
resource pool and an unfinished ownership design; the features depend on each
other; how do we untangle?*

**Tested rather than accepted, and it is not a cycle.** Tracing each missing
item to what it actually needs:

| tier | needs | items |
|---|---|---|
| **0** | **nobody** | the ordinal-space register · arity · a second relation (`at_most`) · the roll's verb term · `SEAM-1` |
| **1** | one external FIX, not a feature | roles + offer ← the subject source: `ChannelRoom.ts:375` returns `LW_CHANNEL_DEFAULT_ACTOR ?? '1'` for **any authenticated user absent from an env map**, so two users are bound to one actor. Re-measured at HEAD, not trusted from the register. It is a **tenancy defect** by `CLAUDE.md`'s own checklist before it is an offer problem |
| **2** | a feature to exist | status relations · a price that is not a quantity · `O-CI-4`'s reachable subject · six effect doors |

**It looks like a cycle because the coupling gets stated in NOUNS** — *the
substrate needs statuses; statuses need the substrate.* Stated in SHAPE it is
not:

> **A feature and the substrate are coupled only through an ORDINAL SPACE.** The
> substrate declares the space and the row shape; the feature declares what an
> ordinal MEANS; content assigns the name. **Neither needs the other to exist
> first.**

**This project has already done it twice and never stated it as a rule.**
`actor-hub` shipped with zero consumers and its first feature arrived two months
later; `M2`'s substrate resolves verbs whose meaning it never learns, and the
first verb arrived as a row in a TOML file. Both are held by shipped gates rather
than by intent — `hub-vocabulary-gate` and `engine-vocabulary-gate`.

⇒ **The rule is only MECHANICAL if the spaces are counted, and they were not.**
One design document says *"a sixth ordinal space"* and then corrects itself to
*"the honest count is TEN"* — in the same file, without listing either set. So
[`docs/specs/2026-08-06-ordinal-spaces.md`](../specs/2026-08-06-ordinal-spaces.md)
counts them, and it paid for itself on the first run:

| # | |
|---|---|
| **1** | **The word names two different things**, which is why six became ten: an AUTHOR-EXTENSIBLE space (content adds a member, one line of TOML) and a CLOSED ENGINE SET (a release, a codec arm, a mirror on every consumer). `§27.4`'s objection was about the first kind only |
| **2** | **`MAX_PLUGINS` derives its width from the wrong thing** — a COUPLING, not a safety hole; see `BDR-14` for the correction to this row's first draft. Two of the three aliases of the quantity space are *identity* — a pool IS a quantity, a progression kind IS a quantity. This one is aliased *"so the two ceilings move together"*, which is the exact shape `MAX_DECLARED_VERBS`' own doc refuses as *"a coincidence pretending to be an invariant"*. **The number is right and the derivation is wrong**: 32 is forced by `PluginSet` being a `u32`, and the correct pattern — deriving a width from the type's own integer — already ships eight files away on `FoldLayer::ORDINAL_SPACE`. Widening the quantity table silently widens the plugin ceiling today, and nothing would notice |
| **3** | **A THIRD kind exists that neither half describes** — plugin ordinals and fold layers are computed at BOOT and are **not in the hashed ruleset**. It cannot vary today (two constants, one plugin), so there is no live defect; the hazard is that it cannot vary *yet*. The day a reality's plugin set is content, two realities could share a digest and derive different plugin ordinals — `QTY-A14` arriving in a space the digest does not cover |
| **4** | **`cue` is unpriced.** `M2` shipped `cue: u16` with no width constant, no repin log and no argument, in a tier where every neighbour carries all three. `AF-8` had already found `RefKindMask` *"outside the six ordinal spaces"* — outside a set nobody had enumerated |

## 6g. Where the user→actor binding belongs — the answer, and the measurement behind it

**Asked by the PO**, who did not take it and asked which is optimal and most
standard, and why. It blocks the subject-source fix → roles + offer → any verb
that touches another actor. It blocks combat.

**Answer: `migrations/meta/012_player_character_index`, with the pc/npc vocabulary
removed. Not close.** Four reasons, heaviest first.

| | |
|---|---|
| **1 · The binding is inherently CROSS-REALITY; per-reality data is not** | A human exists across realities. In a per-reality DB, *"which actors do I drive?"* — the first question a character-select screen asks — becomes a fan-out over N databases |
| **2 · The meta DB is not infra-only, measured** | It already carries per-user rows on purpose, with the machinery this needs: `009_pii_registry` · `011_user_consent_ledger` · `018_user_cost_ledger` · `026_book_reality_subscription` · and `014_meta_read_audit` plus the `meta-sensitive-read-paths.yml` registry. It is the **cross-reality control plane** |
| **3 · `012`'s split is ALREADY the standard shape** | Its own header: `pc_id` is a *"per-reality PC identifier (**FK lives in per-reality DB**)"*. A control-plane pointer into a data-plane identity — exactly what `reality_ruleset_binding` is to a content-addressed artifact. `ruleset_boot.rs` states the same law: *"the meta DB holds the binding; the per-reality DB holds the channel log. Collapsing them would exercise a topology nothing runs"* |
| **4 · GDPR erasure** | This repo shipped a user-erasure orchestrator. Erasing a user must find EVERY binding; a fan-out over N reality DBs is the shape that leaves rows behind |

> **The general rule, since the PO asked for the standard:** the binding is
> **CONTROL, not SIMULATION.** Control questions are cross-instance by nature, so
> control data in a data-plane database is the anti-pattern. Meta = control
> plane (which reality, which ruleset, which human drives which actor);
> per-reality = data plane (the log, the state).

**And `012` already names the exact defect we have.** Its header:

> *"Risk: identity-manipulation attack (alter rows → impersonation, cross-user
> data leak). Defense: … sensitive-read audit on non-owner queries"*, with
> non-owner SELECTs registered as `player_index_cross_user`.

`actorForUser` returning `LW_CHANNEL_DEFAULT_ACTOR ?? '1'` for any unmapped
authenticated user **is** that identity-manipulation risk — and **the defence
written for it is sitting unused.** Building the binding anywhere else abandons a
defence that already exists and would have to be rebuilt.

**What is dead in `012`** is what the handoff already identified and nothing more:
`pc_name`, `status='npc_converted'`, `status='deceased'` — the two-kind vocabulary
and mortality in a lookup table. Keep the binding, drop those three.

> ⚠️ **The parking's own premise has EXPIRED.** It was parked because *"No
> producer, so nothing depends on it and deciding now would be guessing."* There
> is a producer now: the offer stage needs a subject it can trust. And
> `contracts/meta/player_index_parked_test.go` will go RED when a writer lands —
> **that is its trigger firing, not a regression.** It is the one deferral in
> this project whose mechanism is designed to announce its own discharge.

### And a register line that is WRONG — measured while answering this

The handoff says *"No producer, so nothing depends on it and deciding now would
be guessing."* **The first half is true; the second is false.**

```
services/meta-worker/pkg/user_erased_writer/pglive/pglive.go:58
   SELECT DISTINCT reality_id FROM player_character_index WHERE user_ref_id = $1
```

**The GDPR user-erasure path READS this table** — to find which realities a user
has an actor in — and a second leg scrubs `pc_name` through `MetaWrite`. Nothing
WRITES it, so it is empty and both legs run over nothing. That is currently
correct, because nothing records a user→actor binding anywhere; but it means
something stronger than "dormant":

> **The erasure path was built FOR this table and is waiting for it.** Landing
> the binding does not add work to GDPR — it **completes a path that already
> ships.** Same shape as `M1`: `QTY-A4` said a pool's `current` lives on *"the
> actor (`pools[ordinal]`)"* and that slot had never existed; the hub built it
> and `M1` connected it.

⇒ This strengthens the argument above rather than complicating it: the erasure
lookup already queries **this table, in the meta DB.** Putting the binding
anywhere else orphans a shipped GDPR path and requires rewriting it.

**One consequence worth naming:** removing `pc_name` does not only delete dead
vocabulary — it removes the **last PII in the table.** What remains is
`(uuid, uuid, uuid)`, and the meta scrub leg can retire with it.

### What is DEAD versus what INVERTED

The PO asked whether this is just old pc/npc confusion the new design no longer
needs. **Two thirds of it, yes — same call and same reason as `hp`.**
`npc_converted` is a transition between two kinds that no longer exist;
`deceased` is mortality in a lookup table, the same second-SSOT shape `0017`
removed.

**The third part inverts.** The new framing is *"a player is not a kind of actor
— it is a CONTROL INTERFACE: a human with a GUI driving an actor."* If "player"
is no longer a KIND, then `(user, reality, actor)` is the only thing that makes a
player a player. **Removing the PC/NPC distinction does not delete the binding;
it makes the binding the entire concept.** The dead half is the kind-vocabulary;
the live half became more load-bearing, not less.

### 🔴 CORRECTION — the recommendation above was WRONG about the TABLE

The PO asked *"keep it or make a new one, and what is the reason to keep it?"*
The honest answer, after auditing the columns rather than repeating the
handoff's *"half right"*: **right database, WRONG TABLE. Drop `012`.**

**The strongest keep-argument does not exist.** There is **no `INSERT` anywhere**
— only index definitions — so the table is **empty by construction** and can only
ever be empty. Nothing is preserved by keeping it.

**And the argument I actually used was weak.** *"The GDPR path already points at
this table"* — that query reads `user_ref_id` and `reality_id`, both of which
survive any rename. It is **one line of Go and one row of YAML**. I priced a
rename as a cost; it is not one.

**The column audit is worse than "two thirds":**

| | |
|---|---|
| `user_ref_id` · `reality_id` · `pc_id` | the binding — but `pc_id`'s NAME is dead vocabulary |
| `pc_name` | dead: two-kind vocabulary, and the table's last PII |
| `status` | **5 of 6 members wrong.** `npc_converted` dead · `deceased` a second SSOT for death · `active`/`offline` are **PRESENCE**, which belongs to the transport (a Colyseus room knows who is connected), not to a durable binding · `hidden` is a UI preference, which `CLAUDE.md` routes to `/v1/me/preferences` · only `deleted` is about the binding, and it wants to be `revoked_at TIMESTAMPTZ NULL` |
| `last_seen_at` | presence again |
| `pc_index_id` | a surrogate PK where `(reality_id, pc_id)` is already UNIQUE |

**And the precedent I missed:**
`contracts/migrations/per_reality/0017_drop_pc_npc_projections.up.sql`. **This
project DROPPED the other pc/npc artifacts** rather than renaming around them.
Keeping `player_character_index` while having dropped `pc_projection` contradicts
the project's own most recent decision on this exact class.

**The deepest reason is the NAME.** `player_character_index` says *player
character* — the concept the new framing deleted. Keeping it is `D-2`'s failure
and the PO's own `M1` instruction inverted: *DELETE, not port.* `pc_id` renamed
to `actor_id` inside `player_character_index` is `quantity[0] = "hp"` one tier
over — it passes every check and changes nothing.

**Proposed shape** (naming is the PO's):

```sql
actor_control_binding (
    user_ref_id  UUID NOT NULL,     -- who drives
    reality_id   UUID NOT NULL,     -- where
    actor_id     UUID NOT NULL,     -- what     (FK lives in the per-reality DB)
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at   TIMESTAMPTZ NULL,  -- the BINDING is revoked; the actor lives on
    PRIMARY KEY (reality_id, actor_id)
)
```

No PII. No presence. No actor lifecycle — `GoneState` already holds that, and a
second enum here would be a second SSOT.

**What survives from the section above, unchanged:** the DATABASE. Meta, for the
four measured reasons — cross-reality by nature, already a per-user control plane
with the audit machinery, `012`'s own control-pointer-into-data-plane split, and
GDPR erasure needing to find every binding without a fan-out.

**Still the PO's to take.** This section is the argument, not the decision.

## 6h. `FLOW-AUDIT` — the whole chain traced, 2026-08-07, and the PO's diagnosis confirmed

**The PO's words:** *"I thought the foundation was finished in May, but what got finished seems
to be only the KERNEL, not the foundation — it has no data tiering and no SDK."*
**That is exactly right, and it is measurable.** What follows is the measurement.

### The chain, segment by segment — spec status ‖ code status

| # | segment | governing spec | code | verdict |
|---|---|---|---|---|
| **A** | book → extraction → enrichment → baseline → **manifest** | [`38`](../03_planning/LLM_MMO_RPG/38_content_pipeline_architecture.md) `CPL-*` — **OVERVIEW**, per-element generators unwritten | `world-gen` 30 772 | **spec is an overview; 8 element modules unbuilt** |
| **B** | manifest → resolve → normalise → **digest** → ruleset store | [`16`](../03_planning/LLM_MMO_RPG/16_ruleset_loader_and_registry.md) `RLS-*` — deep, and the corrections landed | `ruleset-core` 5 197 + `ruleset-loader` 3 852 | ✅ **the one segment that is whole** |
| **C** | manifest → **SEEDING** → `*Born` → a reality with a world | [`18`](../03_planning/LLM_MMO_RPG/18_reality_bootstrap.md) `RBS-*` + `GDA-D3/D4` + [`37`](../03_planning/LLM_MMO_RPG/37_world_data_storage.md) `WDS-*` | **0** | ❌ **the hole. See below.** |
| **D** | ingress → island memory `D::State` → `step()` | `13`/`14` `SL-*`/`SC-*` | `sim-core` 2 459 · `game-rules` 1 029 · `actor-hub` 1 974 | ✅ built |
| **E** | proposal → admission → commit → `event_log` + outbox | `15` `CS-*` | `commit-service` 6 032 | ✅ built |
| **F** | `event_log` → projections · snapshots · rebuild | `02_storage` | `dp-kernel` 15 041 · `rebuilder` 1 043 | ✅ built — **and this is the "kernel" the PO means** |
| **G** | **tiers T0..T3 · cache · invalidation · the SDK primitive surface** | [`06_data_plane/`](../03_planning/LLM_MMO_RPG/06_data_plane/) — 25 files **LOCKED**, `DP-A/T/K/C/X/F/R/S/Ch` | **0** | ❌ **absent. See below.** |
| **H** | outbox → `dp:events:*` → durable subscribe → Colyseus room | `DP-Ch16..Ch20` + `GDA-A7` | `game-server` 3 192 · `publisher` | ⚠ transport built, **DP semantics not** |
| **I** | room → W0/W1/W2 → browser | [`20`](../03_planning/LLM_MMO_RPG/20_client_wire_contract.md) `CWC-*` — DRAFT, prefix **unregistered** | `contracts/game-wire/` 4 schemas · `frontend-game/src/net/` | ⚠ contract scaffolded, one producer |
| **J** | world → **prompt assembly** → LLM | `GDA-F10`/`R8` + `S09` (10 governance layers) | `prompt.rs` 797 | ⚠ **a validated shell around a hole** |

### `FLOW-1` — the SDK is not "thin", it is **zero**, and one grep says so

```
rg '\b(t1_read|t2_write|t3_write|read_projection_reality|read_projection_channel
     |query_scoped_reality|subscribe_channel_events_durable|subscribe_invalidation
     |DpClient|CausalityToken|cache_key!)\b' -g '*.{rs,ts,go}'
  →  2 occurrences, 2 files — and one of them is the agent worktree copy of the other.
     The single real hit is services/commit-service/src/bin/spine.rs.
```

Against that, `reality_id` as a **bare field** is **457 occurrences across 44 files in `crates/`
alone**. `22 §5`'s anti-pattern table forbids exactly this in as many words — *"Pre-resolve
`RealityId` from a config string and pass it everywhere → the newtype is module-private; obtain it
from `SessionContext::reality_id()` — `DP-A12` gates cross-reality leakage at the type level."*

⇒ **`dp-kernel` is not the data plane. It is `02_storage` in Rust** — event store, outbox,
snapshot, projection runner, upcaster, channel writer, canon cache, prompt composer. Every one of
those is segment **F**. Segment **G** — the four tiers, their coherency models, the ~42 primitives,
the cache-key macro, the capability token — **has no code at all**, and the crate that carries the
`dp-` prefix is the reason nobody noticed.

### `FLOW-2` — the flow WAS traced. In a draft. Whose corrections to the LOCKED spec were never applied

[`17_game_data_architecture.md`](../03_planning/LLM_MMO_RPG/17_game_data_architecture.md) (2026-07-26,
`GDA-*`) is the end-to-end flow document, and it opens by naming this exact defect: *"we have ~80
documents of data architecture and **zero end-to-end flows**… not one document traces a single
request from trigger to storage and back."* It then composes 6 boot levels + 16 flows and closes
**nine** seams.

**It is still `Status: DRAFT`, and its corrections to `06_data_plane` were parked.**
[`19_reconciliation_register.md`](../03_planning/LLM_MMO_RPG/19_reconciliation_register.md) line 392,
verbatim: **"All LOCKED-file changes marked pending-AMEND in place; none applied."** §15 files them
as the **AMEND bundle** — *"decision-complete, application-gated"*.

The bundle: `REC-53` (EVT + envelope v2) · `REC-58` (bus parked-state) · **`REC-65` (`DpError` drift
— `DP-K3` is LOCKED at 21 variants and 5+ docs mint satellites)** · `REC-68` (gate-reject audit) ·
`AGT-A2/D1` · `DP-A16` lease · **the `DP-Ch33`-adjacent hotset default**.

**Why this is not bookkeeping.** The doc hierarchy says *the locked spec wins* (`22 §8`). So the
authoritative text is the un-amended one — and `GDA-F8` measured what that text says: `DP-X3`'s V1
static hotset is **`player + session + region`**, and **none of those three aggregates exist** in the
52-row ownership matrix the feature layer actually uses. **The pre-warm, as locked, warms nothing.**
`GDA-D13` fixed it eleven days ago on paper and the fix was never written into the file it fixes.

### `FLOW-3` — the hole is segment C, and doc `38` named it a week ago

[`38 §0`](../03_planning/LLM_MMO_RPG/38_content_pipeline_architecture.md), 2026-07-30, traced the
same chain and printed the same shape:

```
Phase 0 authoring (TOML layers)              ✅ built
Phase 1 reality creation → digest → binding  ✅ built
Phase 2 SEEDING                              ❌ does not exist
Phase 3 node boot → island Cold→Hot          ✅ built
Phase 4 actor spawn                          ⚠  hp + one hardcoded archetype
Phase 5 the room projects the log            ✅ built
```

> *"The `RealityManifest` appears in **eight design documents and zero lines of code**. It has no
> type, no table, no producer, and no hash in the reality binding. So the engine can load a
> reality's **rules** and cannot load its **world**."*

**Re-measured today, 2026-08-07 — unchanged.** `rg 'RealityManifest|reality_manifest'` over
`*.{rs,go,ts,py,sql,json}` returns **two real files**: `crates/ruleset-loader/src/validate.rs`
(a **doc comment**) and `scripts/amendment-rot-gate.py` (a **gate**). Neither is a producer.
`CPL-F1` states the consequence precisely: *"the missing tier is not the manifest TYPE. It is the
pipeline that produces one. Declaring the struct tomorrow would leave every field unpopulated."*

And [`37`](../03_planning/LLM_MMO_RPG/37_world_data_storage.md) `WDS-F1` found that the sealed
mechanism for filling it is **half wrong**: `GDA-D4`'s *"seeding emits events, never direct writes"*
is a **record** for authored content and a **transcript** for generated bulk — ~33 k genesis events
at `Megaplanet` scale for a payload that regenerates in ~1 s from a 32-byte seed.

### `FLOW-4` — the LLM's READ of the world has no owner in code

MCP in the game tier is entirely the **decide** path — `AGT-A2`: *"the allowed-tool set is defined
once as MCP tools"*, and `AGT-A6`: a tool-call **executes nothing**, it IS the proposal payload.
(`REC-77` then amended the originator: ai-gateway is MCP tool-federation only; the `LlmDriver` lives
in `commit-service` — and **that one is built**, `src/llm_driver.rs`.)

**The read path is prompt assembly, and it is the hole `GDA-F10` opened.** `prompt.rs` documents its
own emptiness — `PromptContext` *"WHO + WHAT-FOR; no body"*, `ResolvedContext`'s filter chain
*"V1 = empty"*, `RetrievalHints` with nowhere to come from, and three `Noop` gates. `GDA-D16`
created the **`ContextResolver`** role to own it. Measured: **`ContextResolver` = 0 occurrences in
the entire tree.** So does `RealityBootstrapper`, `PlaceBorn`, `EntityBorn`, `BubbleUpAggregator`
and `hotset` — the whole named vocabulary of segments **C** and **G**.

### What this does to `SEALED-BUILD-ORDER`

**It confirms slices 1–4 and inserts a slice 0.** The order was derived from dependencies and the
dependencies hold. What the audit adds is that **slices 2 and 4 bind to text four pending
amendments were supposed to change** — most sharply `REC-65`, which says `DP-K3`'s error enum is
already drifting across five documents. Typing the write surface against the un-amended enum bakes
the drift into the first line of the SDK.

| slice | was | now |
|---|---|---|
| **0** | — | **apply the AMEND bundle** (or explicitly reduce it). `REC-65` before slice 4; the `DP-X3` hotset default before anything pre-warms |
| 1 | `DP-T0..T3` marker traits | unchanged — still zero-dependency, still discharges the `DP-R2` debt |
| 2 | the `DP-R3` lint, shipped RED | unchanged — and `FLOW-1` re-prices it: the allowlist is not 6 files, it is **every** call site, because there is no primitive to migrate *to* yet |
| 3 | `RealityId` + `SessionContext` | **re-priced by the 457 bare `reality_id` sites** — this is the largest single mechanical change in the plan |
| 4 | tier-typed write surface | unchanged, gated on slice 0's `REC-65` |
| 5 | `DpControlPlane` | unchanged |

**Segment C (seeding) is NOT in this order and that is deliberate** — it is a *consumer* of the SDK,
not part of it, and `38`/`37` already own its design. Recorded so it is chosen rather than
rediscovered: **after slice 4, the next thing the world needs is a world.**

### `FLOW-5` — FOUNDATION or FEATURE, and the test is one the repo already runs

**PO, 2026-08-07:** *"this needs to be made clear — segment C is unbuilt because it is
FEATURE-SPECIFIC. G, B and D–F are foundation. The rest I don't know. But yes, we are missing
foundation."* Correct on all three, and the criterion that separates them is already mechanical.

> **`FLOW-A1` — a layer is FOUNDATION if it can be written without naming a single game noun.**
> The moment a design cannot be stated without `place`, `hp`, `inventory`, `tilemap` or `combat`,
> it has stopped being the engine and started being a world. This is `D-2` — *the engine closes on
> MECHANISM, the manifest closes on VOCABULARY* — applied one tier up, to the question of what
> belongs in the foundation at all.

**It is not a new discipline: `scripts/engine-vocabulary-gate.py` already IS this test**, run
pre-commit, over every tree that transitively reaches `ruleset-core` or `actor-hub`, with the
forbidden words **parsed out of the shipped presets** rather than listed. It was pointed at
crate source. It was never pointed at the layering question.

### And then the split falls out, and it explains why the foundation went missing

| | segment | verdict | why |
|---|---|---|---|
| **A** | content pipeline | **SPLIT** — `CPL-A3`'s six-part contract (schema · extractor · enricher · normalizer · admission · repair) is foundation; the **eight element generators are feature**. `CPL-A2` is the seam: *the generator's output is admitted by the ENGINE'S OWN validator* | build-time authoring, and `world-gen` shipped as one instance of a contract nobody extracted |
| **B** | manifest → digest → ruleset | **FOUNDATION** ✅ built | names no noun: it resolves, normalises, hashes and stores whatever is declared |
| **C** | seeding | **SPLIT — and the PO is right about the visible half.** The emission DAG (`PlaceBorn`/`LayoutBorn`/`TilemapBorn`/`EntityBorn`) is **feature**. The lifecycle worker — CAS, checkpointing, resumability, idempotency keys, the reality writer lease — is **foundation**, and `GDA-A3` already separated them: *the worker HOSTS the `RealityBootstrapper` role* | **measured 2026-08-07: the STATES exist and the TRANSITION has no driver.** `crates/meta-rs/src/routing.rs` declares `Provisioning · Seeding · Active · Frozen · Migrating · Archived`; `rg '\b(Seeding\|seed_reality)\b'` finds **no worker**. A reality can be marked `seeding` and nothing will ever move it out |
| **D–F** | island → commit → log → projection | **FOUNDATION** ✅ built | the whole write spine, noun-free |
| **G** | tiers · cache · SDK primitives | **FOUNDATION** ❌ **zero** | `DP-X1`'s four coherency models mention no game object at all |
| **H** | outbox → stream → durable subscribe | **FOUNDATION** ⚠ transport built, DP semantics absent | resume tokens, gaplessness, redaction *policy* — mechanism. The specific policies are feature |
| **I** | client wire | **SPLIT** — `CWC-A1..A8` (room-is-a-projection · 64-bit-as-string · `client_protocol` ladder · reconnect-is-catch-up · DTO≠aggregate) is **foundation**; `PcSelf`/`InventorySummary`/`RosterEntry`/`CombatFrame` are **feature** | schemas scaffolded, one producer |
| **J** | prompt assembly | **SPLIT** — `Composer`, section structure, budget, filter chain, audit row = foundation (**built, gates `Noop`**); the `ContextResolver`'s section→source **table** = feature | `ContextResolver` itself is the missing *mechanism*, 0 occurrences |

### `FLOW-6` — the one-line statement of what is missing

Read the ✅ column and the ❌ column and they separate perfectly:

> **Everything built is a WRITE. Everything missing is a READ.**
>
> **B** writes the rules in · **C** writes the world in · **D–F** write state down. All specified,
> and every one of them either built or feature-scoped.
> **G** is the read contract (a tier IS a coherency guarantee — `DP-X1`'s columns are literally
> *read-your-writes* and *cross-session visibility*) · **H** is the read reaching a client · **I**
> is the read a browser can render · **J** is the read an LLM can reason over. **None exists.**

**And `GDA-F3` said this in July, about a smaller subject:** *"`02_storage` §4.4 documents the
WRITE path. There was **no read-path section anywhere** — a striking asymmetry for a system whose
founding premise is that event-sourcing reads are expensive."* It resolved that for one flow. The
asymmetry it noticed is the whole shape of the tier.

⇒ **This is why "missing foundation" is not the same as "unbuilt features."** A feature can be
missing and the ones that exist still work. **A read contract cannot** — every feature reads, so
each one either invents its own access (which is the 457 bare `reality_id` sites) or waits. That is
the precise sense in which the house has no floor: not that rooms are missing, but that everything
already standing is resting on the ground.

### `FLOW-7` — 🔴 **THE ROOT CAUSE: `dp-kernel` is a NAME COLLISION from a different track**

This is the answer to *"I thought the foundation was finished in May."* **Something named
`dp-kernel` did appear in May. It was never the data plane.**

| | measured |
|---|---|
| crates the LOCKED DP corpus names | **`dp`** (the SDK) · **`dp-derive`** (`04d` Deferred: *"macro code lives in `dp-derive` crate"*) · **`dp-clippy`** (`DP-K11`) · `loreweave-aggregates` (`OOS-2`) |
| times the DP corpus names `dp-kernel` | **ZERO** — `grep -rn 'dp-kernel\|dp_kernel' 06_data_plane/*.md` → no match |
| who created `crates/dp-kernel` | `21855a371` **`feat(raid-c8): L2 schema infra (F+G+H+I) — registry+eventgen+upcaster+validator`**, **2026-05-29** — the RAID track's event-contract infrastructure, five weeks *after* the DP spec locked (2026-04-24/25) |

**And then the coverage audit believed the prefix.**
[`12_module_coverage_audit.md`](../03_planning/LLM_MMO_RPG/12_module_coverage_audit.md) line 154:

> *"Data platform (events, snapshots, projections, outbox, PII, capacity) | thin | **very deep** —
> `crates/dp-kernel` (32 modules)"*

The document whose entire job is to say **what is covered** looked at a crate whose name starts with
`dp-`, counted 32 modules and 15 041 lines, and marked the data platform *very deep*. Every later doc
inherited it — `13`, `14`, `16` all cite `dp-kernel::` as the thing the design stands on.

⇒ **This is `NV` at the naming layer: a name that cannot fail to look like coverage.** No gate could
catch it, because nothing was wrong — the crate is good code doing a real job. What was wrong is that
**it answered a question nobody asked it**, and the answer was accepted because of five characters.

**The remedy is not a rename** (`dp-kernel` is 15k LOC with a legitimate lineage and consumers). It
is that **slice 1 creates `crates/dp` and the two are named, in both directions, for what they are**:
`dp-kernel` = the storage/contract plumbing (`02_storage`'s Rust home); `dp` = the SDK the LOCKED
corpus specifies. Anything less and the next coverage audit makes the same mistake.

### `FLOW-8` — `#[derive(Aggregate)]` already exists, with a different contract. Slice 1 collides on day one

`DP-Ch4` locks the derive as the enforcement point for scope exclusivity:
`#[dp(scope = "channel", tier = "T2")]` → emits `impl ChannelScoped` + `impl T2Aggregate`, and
`scope = "reality_and_channel"` is a **macro compile error**.

**Measured:** `crates/dp-kernel-macros/src/lib.rs:78` already declares
`#[proc_macro_derive(Aggregate, attributes(aggregate_type))]` — it emits `dp_kernel::Aggregate` +
`AggregateMeta` from a field-shape contract, and knows nothing of scope or tier. Same name, same
`dp-` family, different job. `04d`'s Deferred row says the DP one belongs in **`dp-derive`**.

⇒ Slice 1's first decision is not *what the traits are* — it is **`dp-derive` beside
`dp-kernel-macros`, or one macro serving two contracts**. Found by reading; it would otherwise have
been found by `cargo` in the middle of the build.

### `FLOW-9` — the channel ORDERING is built on a channel TREE that has no table

`DP-Ch2` locks a `channels` table in the **per-reality** DB: `parent`, `depth ≤ 16`, `lifecycle`,
`metadata`, plus `channels_no_orphan` and the no-cycle constraint. It is what `ChannelScoped` keys
on, what the ancestor chain walks, and what every visibility rule resolves against.

**Measured — `contracts/migrations/per_reality/`, 18 migrations:**

| | |
|---|---|
| `0014_channel_ordering` → `channel_event_index` | ✅ `DP-Ch11` (per-channel `channel_event_id` allocation) |
| `0015_writer_lease_liveness` → `channel_writer_state` | ✅ `DP-Ch12..Ch15` (writer binding + epoch fence) |
| **`channels`** | ❌ **no migration, no table** — `DP-Ch1`/`Ch2`/`Ch3` (identity · registry · CP cache) |

⇒ The **hardest** part of the channel design shipped (single-writer ordering, epoch fencing, lease
liveness) and the **structural** part did not. `commit-service` writes `(reality_id, channel_id,
channel_event_id)` against a `channel_id` that **no table defines**, so nothing enforces that a
channel exists, has a parent, or is `Active`. That is the same shape as `SEALED-SUBJECT`: a field
whose supplier is also its judge.

### `FLOW-10` — dead vocabulary inside a LOCKED primitive signature, one file away from where it was fixed

`04c` `DP-K6`:

```rust
pub enum BroadcastScope {
    Reality, Session(SessionId),
    Region(RegionId),   // players in one region (common for position)
}
```

`GDA-F8` measured that `region` is **not vocabulary the feature layer uses** (the 52-row ownership
matrix has `place` / `actor_core`), and `GDA-D13` fixed the one instance it found — the `DP-X3`
hotset default. **`RegionId` is the only other occurrence in the entire locked corpus** (measured:
one hit across all 25 files), it is in a **primitive's type signature** rather than a default value,
and it is on the **T1 position-broadcast path** — the RTM lane. It was missed because the July sweep
went looking for the hotset, not for the noun.

### `FLOW-11` — the locked spec contradicts itself on the read primitives' names

`04b` (LOCKED) defines `read_projection_reality` / `read_projection_channel` / `query_scoped_reality`
/ `query_scoped_channel` — the Phase-4 scope split — and `DP-K12`'s surface table lists exactly those
four. But **`04c` `DP-K8`'s worked example** calls `dp::read_projection::<PlayerInventory>(ctx, id)`
and **`DP-K11`'s lint skeleton** matches on `dp::read_projection` / `dp::query_scoped` — the
pre-split names. Small, and it is precisely the copy-paste surface: a worked example and a lint rule
are the two things an implementer lifts verbatim.

### What slices 1 and 2 now know that they did not

| | before | after this read |
|---|---|---|
| **slice 1** | *"`DP-T0..T3` marker traits"* | tier traits **and** `DP-Ch4`'s `RealityScoped`/`ChannelScoped`, exclusivity enforced by a derive that **must resolve the `FLOW-8` collision first**, in a new **`crates/dp`** + **`dp-derive`** that `FLOW-7` says must be named against `dp-kernel`, not beside it |
| **slice 2** | *"the `DP-R3` lint, shipped RED"* | `DP-K11` already specifies it: `dp::forbid_raw_kernel_client`, an explicit 7-path forbidden-import list (`sqlx::PgPool`, `redis::Client`, `deadpool_*`…), scoped by a **`dp-crate = true` Cargo marker** rather than a directory list — which is the `NV-3`-correct shape, already written |
| **new** | — | **`DP-Ch1/Ch2/Ch3` (`FLOW-9`) belongs in the slice order.** `ChannelScoped` in slice 1 is a marker for a scope key whose table does not exist |

### `FLOW-12` — 🔴 the tier system has **no test strategy**, its own spec says so, and the phase closed as complete anyway

`99` **`Q13`**, verbatim and still `open`:

> *"How do we test that a feature actually honors its declared tier? E.g., if a feature declares T2
> but occasionally writes T3 under error conditions, how is this caught? … **Why deferred:** test
> strategy depends on SDK API (Phase 2). Phase 1 only asserts that tier choice is locked at design
> time (`DP-A9`) and that the Rulebook review gate requires a tier table (`DP-R2`)."*

**Its stated precondition was met the same day it was written.** `Q1` and `Q14` both resolved
2026-04-25 — *"the SDK API is concrete"* — and `Q13` was never picked up. Then the file closes:
*"🎉 Phase 4 design phase is COMPLETE — every design action that could be taken has been taken."*

⇒ Read `Q13`'s own two sentences again: **`DP-A9` and `DP-R2` are the entire enforcement of the tier
system, and both are REVIEW-GATE claims.** A human reads a table and agrees. Nothing observes a
running feature. That is `non-vacuity` at the tier layer — *a check that cannot fail* — and it is the
one thing this repo has a whole standard about. **The spec identified it, classified it correctly,
and shipped the phase as complete with it open.**

This lands directly on the slice order: `DP-R2`'s tier table (the debt this run has carried since it
started) is **the weaker half**. The mechanism half is `Q13`, it is unbuilt, and it belongs with
slice 1 — a tier trait with no runtime observation is a comment with a type.

### `FLOW-13` — `Q2` waits on a service that left the game loop

`Q2` (the Python↔Rust proposal bus) is `open`, *"deferred: user flagged roleplay-service as a draft…
locking a bus protocol to a draft service would constrain that redesign. **Dependencies:**
roleplay-service design maturity."*

Since then, and none of it written back into `Q2`:

| | |
|---|---|
| `AUD-F16` root 7 | *"`roleplay-service` orchestrates LLM calls"* is **stale** — **roleplay-service exits the game loop entirely** |
| `REC-77` | the **`LlmDriver` in `commit-service` is the LLM-Originator** — and it is **BUILT** (`services/commit-service/src/llm_driver.rs`) |
| `15` §2 + `admission.rs` | the bus itself is **built** — Redis Streams `XREADGROUP`, per-cell, with the T6 proposal shape parsed at admission |

⇒ **The question survives its own subject.** The dependency it names cannot mature, because it is no
longer in the loop; the thing it was going to design got built by a different route. Not a defect in
anything shipped — but an `open` row that nothing will ever close is indistinguishable, to the next
reader, from work remaining.

### `FLOW-14` — `OOS-2`'s answer is a crate that does not exist, and `22` cites it as the ✅ Do

`OOS-2` resolves cross-service aggregate-type sharing to *"a shared `crates/loreweave-aggregates`
crate that all DP-using services depend on"*, and `22 §5`'s anti-pattern table makes it normative:

> ❌ *Build a runtime aggregate type registry across services* → ✅ *Use a shared workspace crate
> (`crates/loreweave-aggregates/`)* → **`OOS-2`**

**Measured: `crates/loreweave-aggregates` does not exist.**

⇒ Slice 1 creates **two** crates, not one — `dp` holds the tier + scope **traits**, and
`loreweave-aggregates` holds the **types** that implement them — or it knowingly collapses them and
records why. Deciding that by accident is how a runtime registry gets built later, which is the
exact thing `OOS-2` refuses.

### `FLOW-15` — the SLO doc says T1 is not exercised at V1. The thing being built puts T1 on the critical path

`DP-S1` (LOCKED): **V1 — Solo RP · 1 concurrent player per reality · *"T2/T3 only; T0/T1 not
exercised"***. And **`Q20` Part A** leaves the **whole `DP-S*` table unvalidated** — *"DP-S\* numbers
anchor on MMO scale… may be over-specced. No design action available without V1 prototype
measurement."*

Against that, the model actually under construction:

- `GDA-A1` makes **island memory authoritative while Hot**, and maps it to `DP-X1`'s **T1** row.
- `20` §5 ships **four RTM movement frames in the v1 client wire contract** — `MoveIntent`,
  `PositionPatch`, `SnapBack`, `ModeFlip` — which is the T1 broadcast lane.
- `Q18` itself rewrote T1's examples **to** the channel model (presence, typing, emote) — i.e. the
  tier the scale doc says V1 skips is the tier Phase 4 spent a question re-aiming at V1's own shapes.

⇒ **Slice 4 cannot ship T2/T3 first and defer T1 on the spec's authority.** The authority says T1 is
idle at V1, and it was written before the island model existed. This is **`Q20` Part A** in a form that
does not need a prototype to see: it is not a *number* being wrong, it is a *row* being wrong.

### `FLOW-16` — the LOCKED spec cannot be quoted without breaking the repo's own language law

Found by **being blocked by it**: `doc-language-gate` refused the commit above because I had quoted
`Q20`'s two sub-parts **verbatim**, and the LOCKED spec spells them in Vietnamese.

**Measured — 3 of the 25 locked files** (`_index.md` · `21_llm_turn_slot.md` · `99_open_questions.md`)
carry it, and not as prose: it is a **STABLE IDENTIFIER**, cited across all three, used as a section
heading and as a status-table row key. The two sub-part labels, quoted exactly because the spelling
IS the finding:

<!-- doc-language-gate: ok -- the non-English token IS the subject matter: this finding reports a Vietnamese IDENTIFIER inside a LOCKED English spec, and paraphrasing it would erase the defect being reported. -->
> `docs/03_planning/LLM_MMO_RPG/06_data_plane/99_open_questions.md:301` — `### Phần A — Quantitative DP-S* rescale 🟡 STILL DEFERRED`
> `docs/03_planning/LLM_MMO_RPG/06_data_plane/99_open_questions.md:305` — `### Phần B — LLM turn slot primitive + pattern doc ✅ RESOLVED`
<!-- doc-language-gate: end -->

Why this is not cosmetic:

- **An identifier that cannot be grepped in the language of the corpus is not an identifier.** An
  agent searching `Q20 Part A` finds nothing; any id-keyed gate cannot match it.
- **`doc-language-gate` is a staged-diff gate** — it scans *lines added by staged files*. That is the
  right scope for what it does and it means every pre-existing file is **default-uncovered** (`NV-3`
  again, and this time benignly, since a retro-sweep is a different tool).
- ⇒ The practical cost landed on this very session: **quoting the locked spec faithfully is a
  gate failure.** The correct output — *"`Q20` Part A"* — is now a **paraphrase of an id**, which is
  precisely the drift the id existed to prevent.

Not fixed here: renaming an id inside a LOCKED file is an `AMEND`, so it joins slice 0's bundle
rather than being patched past. Recorded with the rest.

*(Also confirmed in passing, and it closes `FLOW-7` beyond argument — `_index.md` line 60: **"SDK
implementation (Phase 2b `dp` / `dp-derive` / `dp-clippy` crates)"**. The index names the three
crates itself.)*

### `FLOW-17` — the BUILD corrected the locked spec twice, correctly, and neither correction was filed

`13` is the one place where code met the spec, and it is worth saying first that **the code was
right both times.** `0014_channel_ordering.up.sql`'s header:

> *"⚠ **SPEC CORRECTION** (plan D1 / **REC-80 candidate**): `DP-Ch11` asks for
> `UNIQUE (reality_id, channel_id, channel_event_id)` on the event log — **IMPOSSIBLE** here:
> `events` is `PARTITION BY RANGE (recorded_at)`, and PG requires the partition key inside any
> parent unique constraint."*

That is a genuine defect in a LOCKED file — `DP-Ch11`'s DDL cannot execute — and the migration ships
the correct substitute: a **non-partitioned `channel_event_index`** carrying the spec's exact PK,
written in the same transaction, plus a `channel_writer_state` CAS that is **both** the allocator
**and** the `DP-A16` fence. `0015` then adds what `CNC-F9` found missing — *"nothing assigns a
channel, notices a dead holder, or reassigns"* — because `DP-Ch12`'s CP does not exist, and it puts
issuance **in the same row**, with the seam stated: *"when the platform CP lands it takes over
ISSUANCE POLICY over this same table with this same fence."*

**And then:**

| | measured |
|---|---|
| is the `DP-Ch11` partition correction in the reconciliation register? | **no** — `grep 'PARTITION BY RANGE\|partition key\|channel_event_index'` over `19` **and** all 25 DP files returns **nothing** |
| does `REC-80` mean this? | **no — `REC-80` is already taken.** It is the `GEO_001` world-vs-continent row, applied 2026-07-30 |
| register's highest id | **`REC-98`** — so the intended row was never filed under any id |

⇒ **Two correct spec corrections exist only as SQL comments.** `19` §15a named this direction
*"the healthy direction of drift — code teaching the docs"* and filed three rows for it; these two
got a `candidate` label pointing at an occupied id, and stopped there. The locked `DP-Ch11` still
prints DDL that will not run.

### `FLOW-18` — `ChannelId` is three different types in three artifacts, and the built one lost the property it existed for

| artifact | type |
|---|---|
| **LOCKED `DP-Ch1`** | `pub struct ChannelId(pub(crate) Uuid)` — *"newtype with **module-private constructor** — **cannot be forged by feature code**"* |
| **built** `crates/dp-kernel/src/channel.rs:31` | `pub struct ChannelId(pub i64)` |
| **wire** `contracts/game-wire/common.schema.json` | `Uint64String` — *"`channel_id` … BIGINT server-side"* |

Two of three agree on **64-bit**, so the `Uuid` is the odd one and the build's choice is defensible
(a `BIGINT` allocator is what `DP-Ch11`'s counter actually wants). **What is not defensible is
`pub`.** `DP-Ch1`'s newtype is a *parallel shape to `RealityId`*, and `DP-A12`'s whole claim for
`RealityId` is that it *"gates cross-reality leakage at the type level"* by being unforgeable. The
shipped `ChannelId` has a **public field**: any caller can write `ChannelId(7)`.

⇒ **This is `SEALED-SUBJECT` in a third costume** — a value whose supplier is also its judge. Same
week, same tier, and the run has now recorded it three times: `actor` on the proposal, `event_category`
under `PID-D5`, and here.

### `FLOW-19` — the lease table points at a tree that is not there

`DP-Ch13` locks `channel_writer_state.channel_id UUID PRIMARY KEY **REFERENCES channels(id)**`.
Shipped: `PRIMARY KEY (reality_id, channel_id)`, `channel_id BIGINT`, **no foreign key** — which it
could not have had, because `channels` has no migration (`FLOW-9`).

So the shipped stack is: a **writer lease** on a channel, a **total order** within a channel, an
**epoch fence** protecting a channel — and **no definition of a channel.** Nothing can answer *does
this channel exist · who is its parent · is it Active or Dissolved*, which is exactly the set
`DP-Ch1`, `DP-Ch31` and the ancestor-chain visibility rules are built on. The hard half shipped
against a structural half that was never poured.

### `FLOW-20` — the locked spec's queries name a table that does not exist

`event_log` is the spec's table across **8 of the 25 DP files** (`02` · `13` · `14` · `15` · `17` ·
`18` · `20` · `99`). The shipped table is **`events`**, `PARTITION BY RANGE (recorded_at)` —
which is exactly what forced `FLOW-17`'s correction.

The sharp end is `DP-Ch18`'s **catchup query**, given as copyable SQL:

```sql
SELECT * FROM event_log
WHERE reality_id = $1 AND channel_id = $2 AND channel_event_id > N
ORDER BY channel_event_id ASC LIMIT 1000
```

It is correct in shape — `0014` even built `events_channel_order_idx` on exactly that predicate —
and it names a **relation that has never existed in this repo**. (`event_log` appears in code only
in `services/worker-infra`, an unrelated context.)

### `FLOW-21` — the DP Redis keyspace and the built Redis keyspace are disjoint

Every keyspace the locked corpus defines, measured across `crates/` + `services/` + `contracts/`:

| key | spec | code |
|---|---|---:|
| `dp:events:{reality}:{channel}` | `DP-Ch17` — **canonical event delivery** | **0** |
| `dp:inval:{reality}` | `DP-X2` — cache invalidation | **0** |
| `dp:channel_changes:{reality}` | `DP-Ch3` — channel-tree delta | **0** |
| `dp:writer_audit:{reality}` | `DP-Ch13` — handoff audit | **0** |

What the shipped publisher actually emits: **`lw.events.*`** (`services/publisher/pkg/redisemit`) and
**`xreality.*`** (`pkg/xreality_fanout`). Two namespaces, neither aware of the other, and
`DATA_ARCHITECTURE.md`'s `I7` (*"`meta-worker` is the only consumer of `xreality.*` Redis Streams"*)
governs the second while the DP corpus governs the first. **Nothing reconciles them** — which is
`BDR-21` again: a Redis plane with a single-reader rule already written down, in a file the DP
corpus does not cite.

### `FLOW-22` — the definitive Phase-4 measurement, and the one symbol that did it right

Every named primitive, type and table across `13`–`21`, swept against the tree:

| | count | |
|---|---:|---|
| **built** | **1** | `turn_number` — and by a **different route** than `advance_turn`: it is `commit-service`'s own field (`epoch_commit.rs`), not `DP-Ch21`'s primitive |
| **deliberately NOT built, with a written reason** | **1** | `channel_pause` — `epoch_commit.rs:24` and `contracts/events/reality.go:66` each state *why*: with every channel transcribing independently there is no reality-wide barrier to pause |
| **zero occurrences, no reason anywhere** | **16** | `advance_turn` · `TurnBoundary` · `BubbleUpAggregator` · `register_bubble_up_aggregator` · `deterministic_rng` · `channel_resume` · `ChannelPaused` · `MemberJoined` · `MemberLeft` · `CausalityToken` · `RouteChannelWrite` · `RedactionPolicy` · `claim_turn_slot` · `TurnSlotClaimed` · `projection_apply_state` · `bubble_up_aggregator_snapshot` |

⇒ **`channel_pause` is the shape the other sixteen should have had.** Not built, and a reader who
greps for it lands on a sentence explaining the decision. Sixteen others are indistinguishable, to
that same reader, from work nobody has got to yet. **The difference between a decision and a gap is
one comment**, and this tier wrote it once out of eighteen.

*(`MemberJoined`/`MemberLeft` deserve their own line: `DP-A18` makes them **canonical, DP-emitted,
feature-forbidden** — *"feature code cannot forge these — reserved event types"* — and `22 §5` lists
emitting them as an anti-pattern the **SDK type system rejects**. A reserved word that exists in no
type system reserves nothing.)*

### `FLOW-23` — the control plane is zero, and two names make it look otherwise

| `DP-C*` mechanism | code |
|---|---:|
| `tier_policy` · `tier_capability` (the registry `DP-C4` calls the source of truth for who may do what) | **0** · **0** |
| `GetChannelTree` · `ResolveAncestorChain` · `StreamChannelTreeUpdates` (the three gRPC methods `Q26` added) | **0** · **0** · **0** |
| `reality_hotset` (`DP-X3`) | **0** |
| `ControlPlaneUnavailable` (the `DpError` variant every degraded-mode path returns) | **0** |

So `17` §4 **B1 step 2.5** — added in the July correction pass as *"**mandatory**; a node that has
not fetched the tier policy cannot legally read or write"* — has **no subject**: there is no policy,
no fetch, and no error to return when it fails.

**And the two names that look like coverage:** `CircuitOpen` (13 files) and `RateLimited` (26) both
appear — from **`crates/breaker-core`**, whose own header says it *"mirrors Go `ErrCircuitOpen`"*.
They are resilience primitives from the platform tier, **not `DpError` variants**. `DpError` itself
is **1 file** (`spine.rs`). ⇒ **`FLOW-7`'s failure mode a second time, one layer down**: a symbol
that greps green while the contract it belongs to does not exist.

### `FLOW-24` — 🔴 the collision is a CLASS, not three accidents — and it is Phase 0 question 1, committed by the spec itself

`FLOW-7` found `dp-kernel`. `FLOW-23` found `CircuitOpen`/`RateLimited`. Reading `07` produced a
**third**, and at that point it stops being coincidence:

| the DP spec means | the platform already had | measured |
|---|---|---|
| `dp-kernel` | — (nothing; the spec's crates are `dp` / `dp-derive` / `dp-clippy`) | a RAID-track crate took the name 5 weeks after the lock |
| `CircuitOpen` · `RateLimited` — **`DpError` variants** | **`crates/breaker-core`**, *"mirrors Go `ErrCircuitOpen`"* | 13 + 26 files, none of them `DpError` |
| **`deploy_cohort`** — a **CP-side manifest** carrying `last_successful_drill`, the CI gate on every DP release (`DP-F10`) | `reality_registry.deploy_cohort **INT** CHECK (0..99)` — a **canary bucket**, `SR05 §12AH.4` | the column exists; `last_successful_drill` is **0** |

⇒ **The DP corpus never ran AUDIT-EXISTING against the tier it sits on.** `02_storage` and the meta
registry were already built and already had this vocabulary; `06_data_plane` reused three of their
words for different things. Every collision **reads as coverage** to a grep, and one of them fooled
the module-coverage audit for six weeks (`FLOW-7`).

**This is the same defect `CLAUDE.md` records as the canonical Phase-0 incident, committed by the
document family that most needed to be right.** And it is worth stating plainly: the August specs
that ignored `06_data_plane` were repeating what `06_data_plane` did to `02_storage`.

### `FLOW-25` — degraded mode: the DP says REJECT, the island model says BUFFER

`DP-F4`/`DP-F5` are unambiguous and locked — **consistency over availability**:

> *"T3 write … **Fails** with `DpError::CircuitOpen { service: "redis" }`"* · *"Partitioned SDKs:
> **stop accepting T3 writes**"*

The island model says the opposite, and `02_storage/SR06`'s own correction banner is where it is
written down:

> *"…and **'per-reality DB down → writes rejected' is inverted**: the island should **buffer and
> dilate ticks** while the sink is down, **not reject gameplay**."*

Both are defensible; they cannot both be built. And this seam is **not** the one `GDA-F11` found —
that one is about *when the ack fires* on a healthy path. This is about **whether the game stops**
when a store is down, and `17`'s flow set never traverses it: `B1`–`B5` are boot, `R1`–`R8` are the
healthy path, `L2` is crash recovery *after* the fact. **Degraded-mode-while-running has no flow**,
which is exactly the condition under which two layers disagree and nobody notices.

### `FLOW-26` — `DP-F10` gates production on drills that have no subject, beside seven drills that exist

`DP-F10` is a **release gate**: *"A DP release cannot ship to production if any mandatory drill has
failed in the preceding 30 days."* Its nine drills, against the tree:

| drill | subject exists? |
|---|---|
| Full reality freeze + thaw | ✅ — `world-service/src/bin/freeze_drill.rs` + `provision_drill.rs` |
| Schema migration rollback | ✅ — `migration-orchestrator/cmd/migrate-drill` + `canary-drill` |
| CP failover · game-node kill · Redis cluster node loss · invalidation-drop injection · SDK↔CP partition · backpressure saturation | ❌ **six** — every one names a component that does not exist |
| Cross-region DR | V3, explicitly deferred |

And **five harnesses exist that `DP-F10` does not name**: `restore-drill.sh` · `closure-drill` ·
`relocate-drill` · `canary-drill` · `provision_drill`.

⇒ `BDR-21`'s lesson, third occurrence: **the pattern already existed and the spec did not open the
file.** Two of the nine could have been written as *"extend the existing drill"*; six are honest
absences; and the CI gate that enforces all nine reads `last_successful_drill`, which is **0**.

*(`07`'s own Deferred list closes with **"Q13 test strategy — not resolved here; belongs in a
test-plan doc once SDK implementation starts."** So `FLOW-12`'s finding is deferred in **two**
locked files with the **same trigger** — and that trigger is the slice about to begin. `Q13` is not
stale; it is **due**.)*

### `SLICE-0` — DONE, 2026-08-07. What was applied, what was queued, and why the split is the work

Filed as **`REC-99`..`REC-102`** in `19_reconciliation_register.md` §16 — **no new registry**
(`GDA-D12`), because these are reconciliations and that file is their home.

**The load-bearing decision is the A/B/C split**, not any individual edit:

| class | meaning | verdict |
|---|---|---|
| **A** | a decision already made and never applied | **APPLY** — it was locked eleven days ago |
| **B** | the document states something **factually false about this repo** | **APPLY** — a doc naming a table that never existed is not a locked decision, it is an error, and an implementer copying it gets a Postgres error rather than a different design |
| **C** | changing it changes a **decision** | **QUEUE for the PO** — recorded, not applied |

#### Applied

| | edit | evidence |
|---|---|---|
| **B** | `event_log` → `events`, **37 identifier-position occurrences across 8 locked files** | shipped table is `events` (`0002_events_table.up.sql`); `event_log` exists nowhere in the game tier. Residual: **0** |
| **B** | `DP-Ch11`'s `UNIQUE (reality_id, channel_id, channel_event_id)` → the shipped `channel_event_index` + `channel_writer_state` CAS pair | the constraint **cannot be created**: `events` is `PARTITION BY RANGE (recorded_at)`. The build knew on 2026-07-27 and filed it as *"REC-80 candidate"* — an **id already taken**. Now `REC-99b` |
| **B** | `DP-Ch22`'s partial UNIQUE index → a non-partitioned `channel_turn_index` | **the same defect, one file over, never found** — partial unique indexes are not supported on partitioned tables at all. It survived because `advance_turn` was never built, so nothing executed the DDL. `REC-99c` |
| **B** | `BroadcastScope::Region(RegionId)` → `Channel(ChannelId)` | the only surviving `region` in the locked corpus, in a **type signature**, on the T1 broadcast path. `REC-101a` |
| **B** | bare `read_projection` / `query_scoped` → the scope-split four, at **4 sites** including `DP-K8`'s worked example and `DP-K11`'s lint skeleton | those two are what an implementer lifts verbatim — **the lint would have been vacuous on every call site**. `REC-101b` |
| **B** | `Q20 Part A/B` — **19 occurrences across 3 files** de-transliterated | it is a stable **identifier**, and `doc-language-gate` blocked this audit's own commit for quoting it faithfully. `REC-101c` |
| **A** | `DP-X3`'s V1 hotset → the **W1 first-frame set** | `GDA-D13`, decided 2026-07-26, never applied. `GDA-F8` measured that all three previously-named aggregates **do not exist** — the pre-warm warmed nothing |
| **B** | `_index.md` gains a **read-this-first** banner | the three crates it names are unbuilt; `dp-kernel` is not them; 16 of 18 `DP-Ch` symbols, every `DP-C*`, and every DP Redis keyspace are zero. `REC-100` |

#### `REC-102` — ✅ **PO APPROVED 2026-08-07, ALL THREE APPLIED** (spec *and* code, one commit)

| # | resolution | evidence |
|---|---|---|
| **(a)** `ChannelId` | spec adopts **`i64`** — two of three artifacts said 64-bit and `DP-Ch11`'s allocator is a **counter**, which a `Uuid` cannot be. Code's field becomes **`pub(crate)`**. `new_verified` deliberately **not** added: an unused constructor for a model nothing produces is the orphan shape `orphan-model-gate` refuses. Instead a named, greppable **`ChannelId::unverified(i64)`** that claims no safety and makes the mints **countable** | **22 call sites — 18 tests, 3 operator CLIs, and exactly ONE load-bearing**: `commit-service/src/manager.rs`, where the channel arrives **from the wire**. `SEALED-SUBJECT` verbatim, now visible. `cargo check -p dp-kernel -p commit-service --all-targets` green; `cargo test -p dp-kernel --lib` **315 passed** |
| **(b)** `DpError` | closes `REC-65` on a **full census**, not its original list. **21 → 23**: adopt `ResumeTokenExpired` (no variant carries *"the history you asked for is gone"*) + `AggregatorStuck` (**the only failure no retry can clear**); strike `ChannelAlreadyDissolved` (duplicate); **re-home the four `CausalRef*`** — `EVT-A6` itself says *"rejected at validator-pipeline time"*, and that pipeline is `commit-service`'s admission, **not the SDK**, so the drift is an **attribution**, not a variant | and `OwnershipTransferAlreadyActive` **is not a satellite at all** — the source never writes it as `DpError::`. **`REC-65` miscounted its own list**, which is the fifth time this project has caught a register row wrong about its own subject |
| **(c)** degraded mode | **a partition, not a winner.** T0/T1/T2 **buffer and dilate** — `SR06` is right that the island must not stop because a *sink* is unreachable. **T3 still rejects** — `DP-T3` *is* invalidate-before-ack, so a buffered T3 acks a promise not kept | **`GDA-F11`'s resolution applied one failure-mode over**: *the island stays authoritative for state, and the tier decides whether the write may proceed without its store.* Datable root cause: `DP-F1`–`F5` were written while the **DB was believed to be the SSOT** (`AUD-F16` root #3) |

**Verify evidence:** `event_log` 0 · `Part A/B` 0 residual VN · bare `read_projection`/`query_scoped`
0 · `RegionId` 1 (inside its own amendment note, deliberate) · `amendment-rot-gate` OK 380 docs ·
`phase0-reconcile-gate` OK · `citation-gate` OK.

**What slice 0 did NOT do, stated so it is not mistaken for done:** it changed no code, and it did not
touch `REC-53`/`REC-58`/`REC-68`/`AGT-A2`/`AGT-D1` — those are **EVT- and AGT-track** amendments this
audit never examined. Claiming the bundle is discharged would be false; the **DP-track half** is.

### Stated limit of this audit

Read in full: `22`, `06`, **`04c`**, **`04d`**, **`12`**, `17`, `20`, `38 §0–§4`, `37 §1`,
`19 §12b/§15`, `08`, `99`, `13`, `14`, **`07`**. **Read at the SYMBOL level only** — `15`–`21`:
every named primitive, type, table and Redis key in them was swept against the tree (`FLOW-21`,
`FLOW-22`, `FLOW-23`), which settles *is it built* but **not** *is the design internally sound*.
Sixteen of those symbols have zero occurrences, so for them the second question has no subject yet;
`07` has since been read in full (`FLOW-24`–`26`). What remains genuinely unread is `15`–`21`'s
internal design — five files of channel semantics whose every named symbol is zero, so the question
*is the design sound* has no subject there until slice 1 gives it one. Every count above is a command, and every command
is printed beside its claim. What is *not* claimed: that the nine unread files contain no further
seam. They are the remaining work of this review.

## 6i. `SDK-BOARD` — the slice board for the SDK track, and the DoD it is graded against

> 🔴 **Opened 2026-08-07 because the PO stopped a build that had already started without it.**
> *"Have we finished the spec and closed the run-state, or did we jump straight into build? If it is
> a build, it needs a goal with independent verification, and it has to be tested on the code axis,
> the run axis, and measured numbers — otherwise quality is not assured."*
>
> **The correction is accepted and it is exact.** Slice 0 (spec) is closed and pushed. Slice 1 was
> **started without a board, without a goal, and without a verifier** — four files of `crates/dp`
> written, **not compiled, not in the workspace, nothing claimed about them.** §0's three axes exist
> in this very file and I walked past them. Recorded as `BDR-26`.

### Why §0's DoD does not transfer verbatim, and what replaces it

§0 grades the **command substrate** — a thing that submits, commits and renders. Its Axis 2 asks for
a live smoke and its Axis 3 for digests off a real run. `crates/dp` **has no I/O by design**, so
copying those rows would produce ceremony that cannot fail, which is the exact defect this project
has a standard about. The axes are re-derived for a **type-level contract**, and the derivation is
stated so it can be argued with rather than assumed.

### Axis 1 — CODE

| | |
|---|---|
| `S1.1` | `cargo test -p dp` green, **counts pasted** |
| `S1.2` | `cargo clippy -p dp -- -D warnings` clean, **pasted** |
| `S1.3` | `crates/dp` is a **workspace member** and the whole workspace still builds — `cargo check --workspace` **tail pasted** |
| `S1.4` | full pre-commit gate run green, **tail pasted** |

### Axis 2 — RUN — *the compiler executing on adversarial input*

The claim slice 1 makes is **"these violations are unrepresentable"**. The only honest execution of
that claim is **rustc, run against code written to violate it.** That is a real process producing
real output; it is not a mock, and it is not a stand-in for a live smoke that does not apply here.

| | |
|---|---|
| `S2.1` | a `trybuild` UI suite runs and **each case FAILS to compile**, with the compiler's own message pasted |
| `S2.2` | the suite covers **all three** claims separately: (a) **two tiers** on one aggregate · (b) a **fifth tier** minted by a feature crate (the seal) · (c) a **runtime-varying** tier (`DP-A9`) |
| `S2.3` | `live infra unavailable: crates/dp declares no I/O and opens no connection — Axis 2 is the compiler, by construction, not by omission.` Stated explicitly so the absence is a **decision on the record**, not a gap |

### Axis 3 — DATA MEASURE

| | |
|---|---|
| `S3.1` | **zero-cost, measured**: `size_of` of every marker type pasted (expected `0`) |
| `S3.2` | **compile-time, proven**: `tier_row::<A>()` evaluated in a `const` context — if it compiles there, it costs nothing at runtime. Pasted |
| `S3.3` | **the bite matrix** — for each of `S2.2`'s three claims: remove the mechanism, show the UI case now **COMPILES** (guard was real), restore, show it fails again. **A guarantee nobody tried to break is a claim.** Both outputs pasted, per claim |
| `S3.4` | counts pasted: tiers declared · scopes declared · UI cases · assertions |

### The independent verifier

| | |
|---|---|
| `V.1` | a **cold-start refuter** that did not write the crate, given the diff and told to break it. Verdict pasted **in full, including what it could not break** |
| `V.2` | a **mechanical oracle by a DIFFERENT METHOD**: a test that **parses the tier numbers out of the LOCKED documents** (`03_tier_taxonomy.md`, `08_scale_and_slos.md`, `06_cache_coherency.md`) and asserts they equal the `const`s in `tier.rs`. Two hand-written tables agreeing is not an oracle; a **parser** disagreeing with a `const` is the drift alarm this entire audit exists about — `FLOW-2` is that alarm never having existed |

### What does NOT satisfy this

- **A trait with only test implementors and no bite.** The exclusivity claim is the product; an
  untested claim is `FLOW-12`'s `Q13` re-opened one layer down.
- **`cargo build` succeeding.** Slice 1's whole point is code that must NOT build.
- **Copying §0's live-smoke row** to look thorough. Axis 2 is re-derived above and the reason is
  written; a borrowed row that cannot fail is worse than a stated absence.
- **The author refuting themselves** on `V.1`.

### `V.1` round 1 — the cold-start refuter returned **BLOCK**, and it is right

> **Status: all 13 findings DISCHARGED 2026-08-07** — see the table after `V1-F13`
> for what each fix was and what evidence it produced. The findings are kept in
> full below rather than summarised away: **`V1-F1` changed what this crate is
> allowed to claim**, and a fix whose reason has been deleted is a fix nobody can
> re-argue. Slice 1 is still not closed — closure needs a **second, different**
> refuter (see the board).

**Run 2026-08-07 against the slice-1 diff, given the six claims and told to break them. Verdict:
BLOCK.** 13 findings, 1 BLOCKER, 4 MAJOR. Tree verified byte-identical afterwards (SHA-256 per file,
docs restored, `git diff --stat -- docs/` empty). **It fixed nothing, as instructed.**

#### 🔴 `V1-F1` BLOCKER — *"exactly one tier, structurally"* is **FALSE**, and I sold that claim to the PO

`DpAggregate` constrains the *impl*, not the *type constructor*. The refuter wrote, compiled and ran:

```rust
pub struct PlayerWallet<T: Tier, S: Scope>(PhantomData<(T, S)>);
impl<T: Tier, S: Scope> DpAggregate for PlayerWallet<T, S> {
    type Tier = T;  type Scope = S;  type Id = u64;
    const TYPE_NAME: &'static str = "player_wallet";   // ONE name, four tiers, both scopes
}
fn pick(degrade: bool) -> Box<dyn AnyTier> { if degrade { .. T1 .. } else { .. T3 .. } }
```
```
DP_DEGRADE=false -> type_name=player_wallet tier=T3 ack=50ms survives_outage=false
DP_DEGRADE=true  -> type_name=player_wallet tier=T1 ack=10ms survives_outage=true
BREAK-A: COMPILED AND RAN — tier is caller-chosen and runtime-selected
```

**And it does not even need generics** — two `impl`s with the same `TYPE_NAME` and different `Tier`,
selected by an `if`, also compile (`BREAK-E`). Nothing checks `TYPE_NAME` uniqueness.

**Why it is a BLOCKER and not a nit:** `TYPE_NAME` is the aggregate token in the `DP-Ch5` cache key.
Two tiers under one name = two live cache entries for one logical aggregate, **two different
coherency contracts**, and `survives_store_outage` flipping `false → true` on an env var — which is
**exactly the `REC-102c` promise this crate was written to make un-flippable.** `DP-A9`'s words are
*"not configurable per player"*; a `Box<dyn _>` chosen per request is per-player configuration.

> **The honest claim is: *"a single non-generic `impl DpAggregate` binds exactly one tier and one
> scope."*** That is much weaker than *"unrepresentable"*, and it is what the code supports. **I put
> the stronger wording in front of the PO as the reason to approve this shape.** `BDR-28`.

#### `V1-F2` MAJOR — the test named for `DP-A5` is vacuous (`NV-1`)

`assert_eq!([T0,T1,T2,T3].len(), 4, "DP-A5: closed at four")` — the array has four elements because
the test wrote four. **The subject cannot vary.** Proved by adding a fifth in-crate tier: `measure`
and `spec_oracle` **stayed green**; only an *incidental* pinned `.stderr` (rustc's *"other types
implement Tier"* help list) noticed. Delete that one expectation file and a fifth tier ships green.

#### `V1-F3` MAJOR — bite leg (a) is not a bite

`_bite_shape.rs` **does not reference `dp` at all** — `rustc` compiles it with no `--extern dp`, so
`ok_a` would be `True` if the crate were deleted. And `two_tiers.rs` fails on **`E0201`**, a Rust
language rule provable with a bare `trait Anything { type Whatever; }`. ⇒ leg (a) establishes *"a
strawman is weak"* and *"E0201 exists"*, not that any mechanism `crates/dp` installed is
load-bearing. **`runtime_tier_branch.rs` labels itself unbiteable and leg (a) got a substitute
instead of the same disclosure — the inconsistency is the finding.** Honest score: **2 bitten, 2
unbiteable-and-stated**, not `PASS 3/3`.

#### `V1-F4` MAJOR — the oracle's stated limits misdescribe its own sources

(a) **`03_tier_taxonomy.md` is named by `V.2` and never opened** — perturbing its T2 ack `5ms → 9ms`
left the suite green. (b) `Coherency` is called *"prose"*; `DP-X1` is **a markdown table** the
existing helper parses as-is. (c) `SURVIVES_STORE_OUTAGE` is called *"guarded by its own unit
test"* — and that test is a **second hand-written table**, which is the exact thing this file's own
docstring calls *"not an oracle — the same act done twice."* **`REC-102c` is the one genuinely new
decision in the crate and it is the one thing with no independent check.** (d) `parse_ttl` returns
`None` for unrecognised units, so `T0`'s cell can be edited to `1 h` and stay green.

#### `V1-F5` MAJOR — `TierRow` is freely forgeable

Every field is `pub`. A `T3` row was hand-built with `Coherency::None`, a **24-hour** TTL (the
`const` block asserts ≤ 1 h) and `survives_store_outage: true`. **A table that can be written by hand
is the hand-written table it was meant to replace.**

#### `V1-F6`..`V1-F13` — MINOR/NIT, each verified with pasted output

*"costs zero instructions at runtime"* is false at non-const call sites (disassembly pasted, 9
instructions at `-O3`, a real `callq` at `-O0`) · the bite harness blames the guard when the
**harness** breaks the crate · it mutates an **untracked** file, so only process memory holds the
original · `two_tiers.rs` tests rustc not `dp` · `S3.4` prints *"3 UI cases"* when there are **4** ·
`dp-crate = true` has no reader yet · one `Sealed` marker serves two unrelated taxonomies.

#### What it could NOT break — recorded because an absent finding is evidence

| claim | attempts |
|---|---|
| **the seal (`DP-A5`) vs an external crate** | `impl Sealed` → `E0603` · the **`#[fundamental]` `&T` orphan escape** → refused · any re-export path → none exists · `dyn Tier` → not object-safe. **Holds.** |
| **the spec oracle** | edited **one side only, three times** (`DP-S3`, `DP-X7`, `DP-S5`); each went red **naming both sides**. *"The mechanism itself is sound and is the best thing in this slice."* |
| **the `const _` invariant block** | not in my bite matrix, so the refuter bit it: flipping `T3`'s outage flag → **`E0080` build failure**. The *count-plus-named-exception* framing bites. |
| **`.stderr` pinning** | a drifting failure-reason does red. |
| **bite-harness restore** | `sha256` identical after a crate-breaking mutation **and** after an injected exception mid-mutation. |
| **`size_of` = 0** | confirmed for all six markers. |
| **claim 1's non-generic half** | `E0201` / `E0119`. Unbroken **for a concrete impl** — the break is at the type-constructor level. |
| **every citation** | `REC-102c` ↔ `07:149,158` matches the constants exactly; *"25 LOCKED documents"*, `dp-derive`/`dp-clippy` named-and-absent — **all verified accurate.** |

### `V.1` round 1 — how each finding was discharged, 2026-08-07

**Every row was fixed in code, not argued with.** The BLOCKER's fix is the one
worth reading: `V1-F1` is **not fully fixable in the type system**, and saying so
is the finding's real content.

| id | discharged by | evidence |
|---|---|---|
| 🔴 `V1-F1` | **Two halves.** (i) The claim is restated at every site it reached — `lib.rs`, `tier.rs`, `scope.rs`, `aggregate.rs`, `compile_fail.rs` — as *holds for a **concrete** impl · does NOT hold for a generic one*. (ii) The half rustc cannot hold is now held by **`scripts/dp-aggregate-gate.py`**: `type Tier`/`type Scope` must name a member of the closed set (parsed out of `tier.rs`/`scope.rs`, never typed into the gate), `TYPE_NAME` must be a literal, and no two impls may share one. | Bitten: the refuter's own `PlayerWallet<T, S>` file → gate exit 1 naming `R1`+`R2`, **while `cargo build -p dp --tests` exits 0** — the contrast IS the finding. Found a real `TYPE_NAME` collision on its first run (`measure.rs` ↔ `aggregate.rs`, both `player_inventory`). Wired pre-commit. |
| `V1-F2` | The vacuous `assert_eq!([T0..T3].len(), 4)` is **deleted**, not moved. The closed set is now `spec_oracle::the_tier_set_in_source_matches_the_taxonomy_doc`, comparing `declare_tier!` invocations parsed from `tier.rs` against the `DP-T*` rows of `03_tier_taxonomy.md`. **Neither number is written in the test.** | Bitten: `DP-T3` → `DP-T4` in the doc alone ⇒ red naming both sides. |
| `V1-F3` | `_bite_shape.rs` **deleted** — a control that controls for nothing is not evidence. The harness now reports **bitten** and **unbiteable-and-named** separately; `PASS 3/3` is gone. `two_tiers.rs` is labelled for what it is (an `E0201` regression pin), matching the disclosure `runtime_tier_branch.rs` already carried. | `dp-slice1-bite: PASS — 10 bite(s) bit, 2 leg(s) stated as unbiteable.` |
| `V1-F4` | All four sub-findings. (a) `03_tier_taxonomy.md` is opened, for what it is authoritative for — **which tiers exist**, not latency (its cell holds two numbers and only `DP-S3` says which is the ack). (b) `DP-X1` parsed against a new `Coherency::doc_phrase()`. (c) `REC-102c`'s verdict parsed out of `DP-F5`'s table. (d) every parser returns `Result`; an unreadable cell **panics naming the cell** instead of returning `None`. | 6 oracle bites, one per parsed source, each red **naming both sides**. `the_parsers_distinguish_absent_from_unreadable` pins the `1 h` case directly. |
| `V1-F5` | `TierRow`'s seven fields are **private**, with `const fn` accessors, so `tier_row::<A>()` is the only constructor. | New UI case `forged_row.rs` — the refuter's exact forged row → `E0451` naming all seven fields. Biteable, and bitten. |
| `V1-F6` | *"costs zero instructions at runtime"* corrected to what was actually measured: **at a `const` site the cost is zero**; a non-const call site is a function call like any other. | The refuter's disassembly (9 instructions at `-O3`, a `callq` at `-O0`) is now the reason for the wording. |
| `V1-F7` | The harness distinguished **"the guard is weak"** from **"the mutation broke the crate"**. | Caught its own regression on the first run: the `V1-F13` rename made leg (c)'s injected `impl` reference a trait that no longer exists, and it reported `HARNESS MISUSE` instead of blaming `DP-A9`. |
| `V1-F8` | Restores are proven by **sha256**, not assumed from a `finally`. | Found `BDR-32` immediately — the harness had been rewriting LOCKED docs' line endings invisibly. Now byte-exact I/O throughout. |
| `V1-F9`–`F11` | `two_tiers.rs` reclassified (see `V1-F3`); `S3.4`'s counts are **read off the tree at run time** — UI cases, `.stderr` pins, oracle tests — and it asserts every UI case has a pin. The stale *"3 UI cases"* sentence is gone. | `S3.4 compile-fail UI cases = 5 (…)` · `pinned .stderr files = 5` · `spec-oracle tests = 8`. |
| `V1-F12` | `[package.metadata.dp] dp-crate = true` **removed**. Its only reader is slice 2's lint. A declared input with no consumer is the orphan shape `orphan-model-gate` refuses. | It arrives in the same commit as the lint that reads it — moved to slice 2's row below. |
| `V1-F13` | One `Sealed` marker split into `SealedTier` + `SealedScope`. | `.stderr` pins regenerated; nothing else moved. |

### `V.1` round 2 — a DIFFERENT refuter, and it returned **BLOCK** again

**Run 2026-08-07 against `10fe795c5`. Two cold-start agents, neither of which wrote the code and
neither of which was the round-1 refuter: one on the MECHANISM lens (*do the guards hold?*), one on
the EVIDENCE lens (*is the proof non-vacuous?*).** Tree verified byte-identical after each; the
mechanism refuter fixed nothing, as instructed, and pasted a per-file sha256 table plus a
`git status --porcelain` digest matching its own baseline.

#### The split is the finding, and it is clean

**The type-system half is SOUND.** Claims 1, 2, 3, 4 and 6 were each attacked directly and none
moved. That is worth stating as loudly as the failures, because it is what `V1-F1`'s correction was
*for*: the honest half of the claim survived an adversary.

| claim | attacks that failed |
|---|---|
| **the seal (`DP-A5`/`DP-A14`)**, from a crate **outside this repo** | naming `sealed` → `E0603` · implementing `Tier` without it → `E0277` *"`Tier` is a sealed trait"* · a third scope → `E0277` · the **`#[fundamental]` `&T` orphan escape** → `E0277` · a blanket impl over a local marker → `E0210` · re-impl'ing an existing tier to flip `REC-102c` from outside → `E0117` · every `pub use` grepped: no export path to `sealed` exists |
| **one tier / one scope per concrete impl** | `E0201` · `E0119` |
| **no runtime tier** | `E0277` — `TierLevel: Tier` is not satisfied |
| **`TierRow` unforgeable in safe Rust** | the struct literal → `E0451` · **and the functional-update dodge** `TierRow { survives_store_outage: true, ..BASE }` → `E0451` |
| **`REC-102c`'s `const` block is sufficient AND live** | moving the refusing tier from T3 to T2 while keeping the count at 3 → **`E0080` build failure** quoting the message |

**The gate half is REFUTED six ways, and the diagnosis is structural, not a bug list.** In the
refuter's words: *"`dp-aggregate-gate.py` matches **tokens in text** where the property is about
**types after name resolution**, and text has more ways to spell a generic than the gate has
patterns."* Each break below is compiling, running Rust that the gate reports `OK` on — and four
reproduce `V1-F1` verbatim, `survives_store_outage` flipping on an env var included. The gate does
not merely miss them; it **affirmatively certifies** them.

| id | sev | the break | why it is the dangerous one |
|---|---|---|---|
| `R2-1` | 🔴 BLOCKER | **Name a generic parameter `T2`.** `impl<T2: Tier, RealityScope: Scope> DpAggregate for PlayerWallet<T2, RealityScope>` — `type Tier = T2` passes the membership test. | **`V1-F1` restored by a one-character rename**, and `T2` is an unremarkable name for a second type parameter. This is the likeliest *accidental* recurrence. |
| `R2-2` | 🔴 BLOCKER | **Associated-type projection.** A helper trait whose associated types are *named* `T2`/`RealityScope`; `type Tier = <Self as Pick>::T2`. `last_segment` splits on `::` and sees a legal token. | No parameter is renamed, so it defeats a fix aimed only at `R2-1`. |
| `R2-3` | 🔴 BLOCKER | **`const QUOTE: char = '"';`** — `strip_comments` has no char-literal handling. The char opens a phantom string, a later `/*` in what was string content starts a phantom comment, and **the impl is blanked entirely**. Impl count went *down*. | `'"'` is ordinary code in any quoting/CSV/escape routine. |
| `R2-4` | 🔴 BLOCKER | **An odd `{` inside a string.** `#[doc = "the cache key opens with a brace: dp:{"]` → `_balanced` returns `-1` → `continue`. **The gate fails OPEN, silently, with no diagnostic and no count.** | The worst of the four, because it is *invisible*: a doc comment about a `DP-Ch5` cache-key template — this crate's own subject matter — is enough. |
| `R2-5` | 🔴 BLOCKER | **`_FIXTURE_PARTS = ("tests/ui/",)` is an unanchored substring over the whole path**, so `src/tests/ui/mod.rs` in *any* crate — a normal compiled module — is excluded. | The docstring calls this exclusion *"a structural property of the directory, not an enumerated file list."* **That sentence is false**, and I wrote it. `NV-3` in the *exclusion*: default-**covering**. |
| `R2-6` | 🔴 BLOCKER | **`use dp::T3 as T2;`** — and under `#[cfg(feature)]`, the tier becomes a **cargo-feature** choice. The gate's report then names the *wrong tier*. | `DP-A9`: a tier is *"not switchable without a design-change"*. A feature flag is a build-time switch. |
| `R2-7` | MAJOR | **`TYPE_NAME` uniqueness compares literal SOURCE TEXT; rustc compares string VALUE.** `"wallet"` and `"walle\u{74}"` are one cache-key token and two `REC-102c` verdicts. | Certified `unique TYPE_NAME` while printing the opposite of the truth. |
| `R2-8` | MAJOR | **One `macro_rules!` body, N invocations.** The gate counts one block; rustc emits N impls sharing a `TYPE_NAME`. (The *metavariable* form `type Tier = $tier` **is** caught.) | |
| `R2-9` | MINOR | The `const _` block sums `T0..T3` **by hand**, so a fifth in-crate buffering tier builds clean. Mitigated — `spec_oracle` reds on the tier-set mismatch — but the *stated* mechanism for claim 6 does not extend. | |
| `R2-10` | MINOR | **There is no production `impl DpAggregate` in the repo.** `R5`'s subject check is satisfied entirely by `#[cfg(test)]` fixtures and a test binary. | It proves the gate can run, not that it guards anything shipped. Defensible for a slice that ships no aggregates — but weaker than its docstring reads. |
| `R2-11` | NIT | `transmute` forges a `TierRow` (24 h TTL, `survives = true`, on T3). Needs `unsafe` in the caller and `repr(Rust)` makes it UB. | Only that claim 4 is stated absolutely; the honest form is *"in safe Rust"*. |

#### The EVIDENCE lens — the same defect class, re-committed *inside* the discharge

| id | sev | the break |
|---|---|---|
| `V2-F1` | 🔴 BLOCKER | **`dp-aggregate-gate --self-test` never calls `scan()`.** It re-implements R1/R2/R3 inline and R4 with a *different regex*. Gutting the real path (`if seg not in legal:` → `if False:`) leaves the self-test printing *"non-vacuous in both directions"* — **with a live `V1-F1` generic escape sitting in `crates/dp/tests/` and the gate reporting `OK — every one binds one of ['T0','T1','T2','T3']`.** Two `scan()` branches (missing `type Tier`, missing `TYPE_NAME`) have **zero** coverage in either copy. |
| `V2-F2` | 🔴 BLOCKER | **`_FIXTURE_PARTS` is an enumerated skip list, and `R5` is a COUNT check, not a SCOPE check.** Adding one plausible substring (`"services/"`) took 494 files → 305, hid a real escape, and `R5` was satisfied by the four surviving fixtures. **Shipped in the same commit that rescoped `no-absolute-host-paths` off an enumerated skip list, for that exact reason.** The docstring calling the exclusion *"structural, not an enumerated file list"* is false twice over — see also `R2-5`. |
| `V2-F3` | MAJOR | **`parse_ms`/`parse_rate` are unit-blind.** `parse_ms` requires only that `ms` appear *somewhere*. `<5 ms ack, ≤1 s to projection` → `<5 s ack, ≤1 ms to projection` stays **green** — a 1000× SLO change on a LOCKED budget. `500 / s` → `500 / min` likewise. **And my own guard is `NV-2`:** `assert!(parse_ms("<1 s").is_err())` passes only because that fixture contains no `ms` at all, while every real `DP-S3` cell is a two-quantity cell. The guard's subject cannot vary in the direction that would fail it. |
| `V2-F4` | MAJOR | **A `pub(crate)` fifth tier leaves the entire crate green** — `cargo test`, `clippy`, the gate, and the oracle whose docstring says *"mint a fifth tier and the source side grows"*. The source side counts `declare_tier!` **invocations**, not types implementing `Tier`; a hand-written impl does not grow it. **And a claim I made about that finding was itself false (`G8`)**: I wrote that the *public* case is caught incidentally by trybuild's pinned `.stderr` containing rustc's *"the following other types implement trait `Tier`"* list. `fifth_tier.stderr` contains **zero** occurrences of that phrase — it is nine lines of `E0603` on the private `sealed` module. The sentence described a tree that no longer existed, in a table documenting how findings were discharged. |
| `V2-F5` | MAJOR | **`assert_eq!(tiers.len() * scopes.len(), 8)` is `NV-1`, and I wrote a comment claiming it is not.** *"A PRODUCT of two independently-declared sets"* — they are two array literals retyped three lines above. Adding a fifth `TierLevel` variant: the test **prints `tiers declared = 4` and `cells = 8`** and passes. It is `assert_eq!([T0..T3].len(), 4)` — the assertion `V1-F2` deleted from this very file — wearing a different costume. |
| `V2-F6` | MAJOR | **`TierLevel::as_key()` is pinned for T2 and T3 only.** Renaming T0→`"TIER_ZERO"` and T1→`"TIER_ONE"` passes all 20 tests. `as_key` is the tier token of the `DP-Ch5` cache key. |
| `V2-F7` | MINOR | Same as `R2-10` from the other lens: every `impl DpAggregate` in the repo is test code, and **no `Cargo.toml` outside `crates/dp` depends on `dp`.** |
| `V2-F8` | MINOR | **`no-absolute-host-paths` fixed the DIRECTORY dimension of its scope and left the EXTENSION dimension an enumerated list.** `_EXTS` has no `.rs` — in the commit that added a Rust crate to a repo with five Rust crates and three Rust services. Latent, not live (no `.rs` violation exists today). `.md` is unscanned too. |
| `V2-F9` | MINOR | `REC-102c`'s bolded-lead parse is disclosed in an inline comment but **absent from the module's "Stated limits" table** — the one place a reader checks. A row whose lead says `REJECT` and whose body says the opposite stays green. |
| `V2-N10` | NIT | The bite matrix's `10 bites bit` is true and its legs are **an enumerated list of six hand-picked anchors**. Every green in `V2-F3`/`F4`/`F5`/`F6` lives inside that blind spot. Honest about what it ran, silent about polarity. |
| `V2-N11` | NIT | `the_tier_set_in_source_matches_the_taxonomy_doc` compares `Vec`s, so reordering rows in a label-keyed table reds it. False-positive direction — which teaches *"the oracle is noisy"*, and that is how red becomes the normal colour. |

**What round 2 could NOT break, recorded because an absent finding is evidence only if the attempt is:**
the bite harness's restores are genuinely byte-exact (five files independently baselined, every digest
matched) · **all 10 bites are real bites**, verified in reverse · the two "unbiteable" legs are honestly
unbiteable (`E0201`; a *parse* error) · `V1-F7`'s misuse branch correctly separates the two failure
kinds · **the `no-absolute-host-paths` rescope loses no real coverage** — all 67 files that left the
scope were enumerated and checked, 0 violations, and the untracked-file leg still reds · `Tier::LEVEL`
is guarded · every one-sided *numeric* edit reds, and `parse_ttl`'s `Result` rewrite does exactly what
`V1-F4` claimed. **The residual hole is the UNIT, not the shape.**

> **The lesson, stated before the fix so it cannot be retro-fitted:** `V1-F1` established that the
> type system cannot hold this property. I concluded *"so a source gate holds it"* and did not ask
> **whether a source gate can hold it either.** It cannot, in general — the property is about types
> after name resolution and the gate reads text before it. The principled home is `dp-clippy`, which
> **`06_data_plane/` already names as one of its three crates** and which does not exist. That is
> `FLOW-1` pointing at me: the corpus named the tool for this job in April, and I built the thing I
> could build in an afternoon instead of the thing that was specified.

### `V.1` round 2 — how each finding was discharged, 2026-08-07

**The gate is a rewrite, not a patch**, because six of the eight mechanism
findings were its parser and its scope. The rules are no longer *"does this token
look like a tier"*; they are a **closed characterisation of how a generic can
reach `type Tier`** — it must name something the impl binds — plus the ways a
concrete-looking token can lie.

| id | discharged by | evidence |
|---|---|---|
| `R2-1` `R2-2` | **`R6`, the load-bearing rule:** the right-hand side may name **no generic parameter the impl binds and no `Self`**. This is a closure argument, not a pattern list — *to be generic, the RHS must name something in scope, and the only things in scope are the impl's parameters and `Self`.* Plus **`R7`**, which refuses a parameter *named* after a taxonomy member. | Both reproductions are permanent legs. `R2-1` → `R6`+`R7`; `R2-2` → `R6`. |
| `R2-3` | `strip_comments` handles **char literals and raw strings**. | The refuter's `const QUOTE: char = '"';` file → caught by `R6` instead of blanking the impl. |
| `R2-4` | **Two views of the same offsets** — one with string content intact (what the rules read), one with it blanked (what the brace counter walks) — and `find_impls` now **fails CLOSED**: an impl it cannot delimit is `R9`, a finding. | The `dp:{` doc string → caught. |
| `R2-5` `V2-F2` | The exclusion is **one anchored repo-relative directory**, and `R5` is a **set difference** rather than a count: every excluded path must be under it. | `src/tests/ui/mod.rs` is scanned; broadening `FIXTURE_DIR` to `"services/"` reds the self-test on both directions. |
| `R2-6` | **`R8`** — no `use ... as <taxonomy name>` in a file declaring an aggregate. | Permanent leg. |
| `R2-7` | `TYPE_NAME` compared by **decoded value** (`\u{..}`, `\x..`, escapes), because rustc does. | Leg, plus a cry-wolf case proving it does *not* fire on two genuinely distinct names. |
| `R2-8` | **`R10`** — an impl inside a `macro_rules!` body is refused: one body, N invocations, and the gate can only see the body. | Permanent leg. |
| `R2-9` | **Stated, with its two real mechanisms named** in the `const` block itself: the sum is over four *named* tiers and does not extend, so `the_tier_set_in_source_matches_the_taxonomy_doc` and `no_tier_is_implemented_outside_the_declare_tier_macro` are what cover a fifth. | |
| `R2-10` `V2-F7` | Recorded, not papered over — see the Debt row. Slice 1 ships no aggregates, so the gate's subject today is four fixtures. | |
| `R2-11` | Claim 4 now reads *"the only constructor **in safe Rust**"*. | |
| 🔴 `V2-F1` | **`self_test()` drives the real `scan()`** over synthetic files on disk. 19 cases, and two new ones (`a concrete NON-tier as the tier`, `…NON-scope as the scope`) exist because biting found the **membership branch had no case of its own** — gutting it left the old suite green. | **Every rule of `scan()` bitten:** removing R1's membership test, R6, R7, R8, R4, or the fail-closed branch each reds the self-test. 7/7. |
| 🔴 `V2-F2` | see `R2-5`. | |
| `V2-F3` | `parse_ms` reads the unit **off the leading quantity**; `parse_rate` **checks the denominator**. | The refuter's own edits are legs: `<5 ms ack, ≤1 s…` → `<5 s ack, ≤1 ms…` reds; `500 / s` → `500 / min` reds naming `PER-SECOND`. And the `NV-2` guard is replaced by cases on the **real two-quantity cell shape**. |
| `V2-F4` | New oracle test `no_tier_is_implemented_outside_the_declare_tier_macro` — a tier is *a type implementing `Tier`*, not a macro invocation. It also asserts the macro body still contains what it searches for, so the search cannot lose its subject. | Leg: a hand-written `pub(crate) struct T1p5` reds. |
| `V2-F5` | The `NV-1` product is **deleted**. `s3_4_counts` now compares **`TierLevel` variants parsed from source** against **`declare_tier!` invocations** — two independent things in one file. | Leg. **And the leg found something better:** a variant *alone* is `E0004`, because `as_key`'s match is exhaustive — rustc refuses the crate before any test runs. The mutation needs the arm too, which is what an author would write. |
| `V2-F6` | All four `as_key` values pinned, plus all four via `Display`. | Leg: renaming T0/T1's keys reds. |
| `V2-F8` | `.rs` and `.sql` added to `_EXTS`. **`.md` was tried and reverted** — it found four hits, all documents quoting a `docker compose -f "D:/…"` command someone ran. That widens the gate's **subject**, not its scope. | Bitten with a `.rs` violation. |
| `V2-F9` | The bolded-lead limit is now a row in the module's **Stated limits** table, where a reader checks — not an inline comment. | |
| `V2-N10` | The blind spot is the point: the matrix grew **10 → 23 legs** with two new kinds — `source` (mutate the crate, require `cargo test -p dp` red) and `gate-probe` (plant round 2's own reproduction, require the gate red **naming its rule**). | |
| `V2-N11` | Order-insensitive compare — `03`'s matrix is label-keyed, so reordering is meaning-preserving and must not red. | |

### `V.1` round 3 — **BLOCK**, and this one changed the design rather than the code

**Run 2026-08-07 against `06886e800`, in two isolated git worktrees** (`BDR-35`:
rounds 1 and 2 were run against a tree I was still editing, and the round-2
refuter caught me at it). One agent refuting the rewrite, one **completeness
critic** asking what had never been checked at all. Both returned BLOCK; both
verified their worktrees byte-identical afterwards, with digests.

#### The verdict that settled the design

> **R6's closure argument is sound as a statement about Rust; its three
> implementations are not.** *"What the impl binds"* is `impl_generics()`, which
> drops parameters two ways; *"the right-hand side of `type Tier`"* is a
> `re.search` over text that still contains string literals; *"the impl exists"*
> is a hand-rolled lexer that does not know one Rust literal form.

| id | sev | the break — all four compiled, ran, and passed the gate |
|---|---|---|
| `R3-B1` | 🔴 | **`#[doc = "type Tier = T2;"]`** above the real `type Tier = T;`. The body is sliced from text with string content intact and the regex takes the FIRST match, so the decoy is read instead. With a raw doc string it swallows `R3` and `R4` too — a runtime-selected cache-key token reads as a literal, and a real collision becomes invisible. |
| `R3-B2` | 🔴 | **`impl<F: Fn() -> u8, T2: Tier>`** — `_balanced` counts the `>` of `->` as the closing angle bracket, so `T2` is never recorded. `R6` finds nothing bound, `R7` finds no shadowing, and `R1` sees a declared tier. `V1-F1` restored **by adding a closure bound**. |
| `R3-B3` | 🔴 | **`impl<r#T2: Tier, ..>`** — a raw identifier fails `[A-Za-z_][A-Za-z0-9_]*` and the parameter is dropped. `r#T2` and `T2` are the same identifier to rustc. |
| `R3-B4` | 🔴 | **`cr#"unterminated quote: "tier"#`** — C-string literals (stable since 1.77) are not in the lexer's raw-string branch, so quote parity desyncs and **the impl vanishes silently**. Impl count went *down*; no `R9`, no warning. The gate failed OPEN on the exact defect `R2-3`/`R2-4`'s handling was written for. |
| `R3-M1` | MAJOR | **`R8` covers one of four alias spellings.** `type T2 = dp::T3;` (not looked at), `use dp::{T3 as T2};` (`{` is not in R8's path character class), and the alias **in another file** (`scan()` skips files with no impl) all pass — the gate then *names the wrong tier with full confidence*. |
| `R3-M2` | MAJOR | **`declare_tier!{ .. }`** — one character. `match_indices("declare_tier!(")` misses it, so a fifth tier with a 24-hour TTL and `REC-102c` inverted passed **both** mechanisms `tier.rs` names as its compensating control for `R2-9`, plus the gate and clippy. |
| `R3-M3` | MAJOR | **`PASS — 23 bites bit` is scoped to its own probe list.** With a live escape in the tree it still printed PASS, exit 0. *Bites bit* is not *the property holds*, and the PASS line reads as the latter. |
| `R3-N1..N4` | MINOR | `decode_rust_str` tracebacks on `\xZZ`; a `;` inside a `TYPE_NAME` literal is a false `R3`; `ScopeKind::Display` pinned by nothing; `DP-S5`'s **burst** column uncovered and undisclosed. |

#### And what the completeness critic found, which is a different kind of finding

| id | sev | never checked at all |
|---|---|---|
| `G1` | 🔴 | **The SCOPE taxonomy had no door and no oracle.** A third scope was *legal by being written*: the gate parses `scope.rs` for its legal set, so `ZoneScope` made the set three — and the gate **printed the widened set and reported OK**. `V2-F4` gave tiers a macro and a check; scopes had neither. |
| `G2` | 🔴 | **`tests/ui/` was default-uncovered in BOTH directions** — `compile_fail.rs` enumerates by hand, the gate excludes the directory. A planted `zzz_orphan.rs` + `.stderr` carrying a live escape kept parity, so `s3_4_counts` **printed 6 and passed**. |
| `G3` | 🔴 | **22 of 26 LOCKED documents are opened by nothing** — including `02_invariants.md`, which holds `DP-A5`/`DP-A9`/`DP-A14`, the three invariants the seal and the `const` block cite as their authority, and `12_channel_primitives.md`, the source of `as_key()`. |
| `G4` | 🔴 | **`D-DP-CLIPPY-NOT-BUILT` is prose-only and its row calls itself MECHANICAL.** Its stated mechanism is two *docstrings* — which CLAUDE.md names, by example, as the trap: *"a module docstring is prose that happens to live in a source file and does not count."* Written by me, in the commit discharging findings about that class. |
| `G5` | 🔴 | **The entire `S3.3` evidence ran nowhere.** `gate-wiring-gate`'s scope is a filename predicate, so `dp-slice1-bite.py` was not merely unwired — it was **not reportable as unwired**. |
| `G6`–`G13` | 🟠🟡 | the gate is absent from `gate-bite-harness.MUTATIONS`; clippy has no CI home at all and `cargo test -p dp` runs only on a PR to `main`; five `.stderr` pins float on `@stable` with no toolchain file; **a sentence I wrote about `fifth_tier.stderr` describes a tree that no longer exists**; two quotes in `tier.rs`/`aggregate.rs` are attributed to `DP-A5`/`DP-R2` but come from `22_feature_design_quickstart.md`; `DP-F7` holds a **second copy** of `DP-S5`'s numbers that nothing compares. |

#### The discharge — and it is a design change, not a patch

**The Python lexer is retired.** Eleven breaks across three rounds, every one a
fact about Rust's grammar that a partial reimplementation got wrong. Patching the
eleventh was not a strategy; the seventh already wasn't. The check now lives in
**`crates/dp/tests/aggregate_contract.rs`, over a real `syn` AST** — and
`scripts/dp-aggregate-gate.py` is a **runner** that keeps the pre-commit and CI
wiring the property already had. *Two checks for one property, one of them
known-defeatable, is the mirror defect this repo already has a gate about.*

| discharged | how |
|---|---|
| `R3-B1`–`B4` | **No special cases.** A doc attribute is an `Attribute`; `r#T2` and `T2` are one `Ident`; `cr#".."#` is a `LitCStr`; `Fn() -> u8` is a `TypeBareFn` inside a `TraitBound`. All four are caught by `R6`, the rule that was always right. |
| `R3-M1` | `R8` is now two AST rules — `UseRename` (which makes the braced and unbraced forms one node) and `ItemType` — applied **repo-wide**, not only in files containing an impl. All three demonstrated spellings, including the cross-file alias. |
| `R3-M2` | `syn` gives a `Macro` whose delimiter is *data*, so `declare_tier!{..}` and `declare_tier!(..)` are the same item by construction. Fixed in the oracle too. |
| `R3-N1` `R3-N2` | Gone with the hand-rolled decoder: `LitStr::value()` decodes exactly as rustc does, and a `;` in a literal is a literal. |
| `G1` | **`declare_scope!`** — the door scopes never had — plus `no_scope_is_implemented_outside_the_declare_scope_macro`, the sibling of the tier check. |
| `G2` | `s3_4_counts` now compares `compile_fail.rs`'s driven set against `read_dir(tests/ui)` — the enumerated list becomes a set difference, the same fix `V2-F2` applied to the gate's scope. |
| `G5` | `git mv` → `dp-slice1-bite-gate.py`. One rename puts 23 legs inside `gates.yml --run-all` and the wiring gate; discovery went 88 → 89. |
| `G9`/`R3-N3` | All four `ScopeKind` forms pinned — `as_key` and `Display`. |
| `R3-M3` | Accepted as stated, not closed: *bites bit* ≠ *the property holds*, and the enumerated probe list is `NV-3` by construction. The AST check is what closes the class; the legs pin the regressions. |

**Still open, and recorded rather than claimed:** `G3` (22 unopened LOCKED
documents), `G4`, `G6`, `G7`, `G8`, `G10`–`G13`, `R3-N4`.

### `V.1` round 4 — **BLOCK**, and four rounds now converge on one answer

**Run 2026-08-07 against `c31c2348f`, isolated worktree.** 6 BLOCKER, 4 MAJOR, 3 MINOR. Tree
verified byte-identical afterwards.

**The rate is not falling: 13 → 19 → 13 → 13.** That is the finding, more than any individual row.

| id | sev | the break |
|---|---|---|
| `V4-F1` | 🔴 | **`use dp::DpAggregate as Agg;`** — `is_dp` tests a SPELLING, and `R8` guards only aliases that take a *taxonomy* name. The trait's own name is not in that set. Four characters remove an impl from R1, R2, R3, R4, R6, R7, R10 and R11 at once, and it is not even COUNTED — so `impls > 0` cannot notice either. `V1-F1` restored, with the gate printing a sentence that is now false. |
| `V4-F2` | 🔴 | **A concrete impl whose tier is a lie.** `type Tier = <Wallet as Pick>::T2` where `Pick::T2` is an associated type *named* `T2` — `last_segment` reads `"T2"`, which is legal. `R6` looks for `Self` or a bound parameter; naming the concrete type removes the only ident it looks for. Contract counted it and certified it while `row.tier() == T3`. |
| `V4-F3` | 🔴 | **`agg!(DpAggregate, WalletA, dp::T2)`** — pass the trait in as a macro ARGUMENT and `R10`'s subject (the string `"DpAggregate"` inside the body) is gone. Three impls invisible in one file, including an `R4` duplicate and a generic escape. Same class covers a proc-macro `quote!` — which matters, because `dp-derive` is a named deferred crate. |
| `V4-F4` | 🔴 | **Both "one sanctioned door" tests read ONE FILE each**, and the seal is `pub(crate)` — i.e. crate-wide. A new `src/zone.rs` mints a fifth tier (24-hour TTL, `REC-102c` inverted) and a **public** third scope, with the full suite green. |
| `V4-F5` | 🔴 | **`include!("x.inc")`** — outside `git ls-files "*.rs"`, and `R9` never fires because the *including* file parses fine. Same hole covers `#[path]` and a `build.rs` writing to `OUT_DIR`. |
| `V4-F6` | 🔴 | **The scan-scope guard is a TAUTOLOGY** — `excluded` is defined by a predicate and then filtered by the same predicate, so `stray` is `∅` for every possible repo state. `FIXTURE_DIR = ""` excludes the entire repository and it stayed silent. **I wrote it as the fix for `V2-F2`, a vacuity finding, in the file whose thesis is non-vacuity.** |
| `V4-F7` | MAJOR | **`PASS — 25 bites bit` with two live rules DELETED.** The legs assert on `R4`/`R6`/`R8`/`R10` only; `R1`, `R2`, `R3`, `R7`, `R9`, `R11` are named by no leg. Removing `R9` and `R11` left both the bite gate and the runner's `--self-test` at their highest score. **The number measures legs, not coverage.** |
| `V4-F8` | MAJOR | `DP-X7`'s **1-hour TTL cap** can become 24 hours with the oracle green — while `tier.rs`'s `const _` block asserts `≤ 3600` *quoting that exact sentence*. A hand-transcribed number from prose the oracle never opens. |
| `V4-F9` | MAJOR | `cache_key_tokens_match_dp_ch5` — **added by the commit under test** — reads one token out of a six-field template. Deleting `{channel_id}` from the channel-scoped key leaves it green. |
| `V4-F10` | MAJOR | **`TierRow::cache_ttl()` and `write_ack_p99()` have no reader**, so `tier_row()`'s derivation of them is unwatched: sever either from the type and 25 tests agree. The `(d)` bite leg proves **privacy** bites and says nothing about **derivation**. |
| `V4-F11`–`F13`, NIT | MINOR | `table_cells` returns column 2 only, so a whole column is invisible in tables the oracle *does* parse · `the_tier_set_matches_dp_a5` reads only the digit · the success line states conclusions the code did not reach · `measure.rs:160` still uses the delimiter-sensitive `declare_tier!(` that `R3-M2` fixed everywhere else. |

#### What survived, and it is the same thing every round

> **R6's closure argument survives, as a statement about Rust and as an implementation over `syn`.**
> Everything that got past worked by attacking one of R6's **premises** — that the impl is visible as
> an `ItemImpl` with the literal trait name (`F1`, `F3`, `F5`), that the last path segment names the
> type it resolves to (`F2`), that the scan enumerates every `.rs` (`F5`, `F6`).

**And that is the answer four rounds have been converging on.** Every remaining break is about **name
resolution** (`F1`, `F2`), **macro expansion** (`F3`), **module scope** (`F4`), or **file inclusion**
(`F5`). Not one is a defect in the rule. All four evaporate inside a `rustc` lint, which sees resolved
paths, expanded macros and the whole crate graph — and `06_data_plane/` has named **`dp-clippy`** as
one of its three crates since April.

⇒ **`D-DP-CLIPPY-NOT-BUILT` should stop being a debt row and become a slice.** Four independent
adversaries have now arrived at it from four directions, and the source check has been rewritten
twice without closing the class.

#### Discharged so far

| | |
|---|---|
| `V4-F6` | Fixed. The scope is now checked against an **independent enumeration** — `read_dir` on the trybuild directory, which does not know `FIXTURE_DIR` exists — plus a positive canary. Bitten: `FIXTURE_DIR = "crates/dp/tests/"` and `FIXTURE_DIR = ""` both red, where the tautology saw neither. |

**Everything else is recorded and OPEN**, pending the `dp-clippy` decision, because patching `F1`–`F5`
in the source checker is the third rewrite of a thing four rounds have shown cannot close the class.


### `1b.5` — the cold-start refuter returned **BLOCK**

**Isolated worktree against `bd43be69c`, live Postgres, worktree verified byte-identical and every
throwaway database dropped.** 4 HIGH, 5 MEDIUM, 7 LOW.

#### The one that matters: `FLOW-2` recurred INSIDE the commit written to kill it

| id | sev | finding | state |
|---|---|---|---|
| `1b5-H1` | 🔴 | **`REC-103`/`REC-105` reached ONE of FOUR locked SQL sites.** `13_channel_ordering_and_writer.md:209` — **the document `0019`'s own header cites by name** — still declares `channel_id UUID PRIMARY KEY REFERENCES channels(id)`. So does `16_bubble_up_aggregator.md:339`. And `17_channel_lifecycle.md:63` holds a **second locked `ALTER TABLE channels`** (four columns + a constraint) that Phase 0 never found. `dp-channels-schema-gate.py` reads `12_channel_primitives.md` **only** — *the gate built to stop `FLOW-2` is scoped to the one file where `FLOW-2` did not happen this time.* | ⬜ OPEN |
| `1b5-H2` | 🔴 | **`DP-Ch1`'s *"strict tree, not a DAG"* / *"No cycles"* is asserted, not enforced.** A 2-cycle takes one `UPDATE` and is accepted; delete the root and the reality is a pure cycle with **zero roots**. Any consumer walking `parent` to build an ancestor chain hangs. `channels_no_self_parent` covers length 1 only. | ⬜ OPEN — needs a decision: a trigger/recursive check in the DB, or an explicit *"SDK-enforced"* statement. |
| `1b5-H3` | 🔴 | **`depth` is a free-floating column.** `DP-Ch1:97` names the mechanism — *"no cycles, enforced by `depth` (children = parent.depth + 1)"* — and the schema never relates `depth` to the parent. A child of the root can declare `depth 16`; a 100-node chain can sit entirely at `depth 1`. `H2` and `H3` are one defect: the spec's stated anti-cycle mechanism IS the depth relation, and neither half is implemented. | ⬜ OPEN |
| `1b5-H4` | 🔴 | **The schema gate is blind to `PRIMARY KEY`, `NOT NULL`, `DEFAULT`, FK bodies/actions and every index but one.** A four-way mutant — `ON DELETE CASCADE`, `level_name` losing `NOT NULL`, `metadata` losing its `DEFAULT`, an extra `UNIQUE` — applies cleanly and the gate says OK. **The primary key is `REC-105`'s entire subject** and the gate does not look at it. With the mutant applied, one `DELETE` of the root silently wiped the tree. | ⬜ OPEN |
| `1b5-M4` | 🟠 | `id <= 0` is accepted. `REC-103` cites the wire contract's unsigned `Uint64String` as a ground for `BIGINT` and carried the **width** but not the **domain**. Empty `level_name` likewise. | ⬜ OPEN |
| `1b5-M5` | 🟠 | **The gate cries wolf on formatting.** Lowercasing a type, or deleting one space in `ON channels (reality_id)`, reds it — and reports `channels_root_single ... None`, which reads as *"`REC-104` has regressed"*. **The no-space style is what the spec itself uses for its other three indexes**, so an author normalising them gets that message. The *"switched off within a day"* failure, arriving through formatting rather than through `CHECK` bodies. | ⬜ OPEN |
| `1b5-L3`/`L4` | 🟡 | A **dissolved root forecloses the reality permanently** (the index ignores lifecycle; `DP-Ch33` keeps the row indefinitely). And the index gives *at most* one root, not *exactly* one — zero-root realities are legal. The refuter answered the brief's question directly: **"one root" is correct, not "one ACTIVE root"**, because ids are never reissued — but the foreclosure is a consequence nobody wrote down. | ⬜ OPEN |
| `1b5-L5`/`L6` | 🟡 | `DP-Ch31`'s terminal-Dissolved and `DP-Ch33`'s descendants-first both fall to a plain `UPDATE`; `DP-Ch31:77` claims a *"row-level rule"* that does not exist. And **`0019` is default-uncovered by `scripts/migration-idempotency-validator.sh`**, whose target list is an enumerated `0001_initial` — `NV-3`'s named shape, pre-existing, and this commit added the 19th uncovered file. | ⬜ OPEN |

#### Fixed here — the ones that were FALSE, plus two absent mechanisms

| id | was | now |
|---|---|---|
| `1b5-L1` | **`DP-Ch17` cited three times as "lifecycle".** `DP-Ch17` is *Hybrid backing store* (`14_durable_subscribe.md:76`); channel lifecycle is `DP-Ch31`..`DP-Ch37`. I read a **file number as a stable ID**. | corrected in all three places, with the error named |
| `1b5-L2` | **Three artifacts claimed `SQLSTATE` was printed** — the docstring, the commit message, and a helper literally called `sqlstate()`. None printed one. | the claim is corrected rather than the output padded: what *is* printed is the **constraint name**, which is stronger evidence — a generic code says *a check failed*, `channels_no_orphan` says *which* |
| `1b5-M1` | **The bite's "restore" was a NO-OP for five of six constraints.** It re-applied the migration, and `CREATE TABLE IF NOT EXISTS` skips — so legs 2..6 ran on a progressively stripped table and the exclusivity the leg advertises was not what the evidence established. (No false pass today; the refuter checked all six for cross-coverage.) | drop + re-create + **re-seed the tree** + verify the constraint is back. The re-seed is itself a `1b.5` lesson: without it a leg's `parent` dangles and the FK rejects for the wrong reason. |
| `1b5-M2` | **`1b.2` contained a row refused by TWO barriers** — a *root at depth != 0* in a reality that already had a root. `CHECK`s evaluate before index insertion, so attribution passed and the ambiguity was invisible. The exact hazard `1b.4` exists for, inside `1b.2`. | a third reality with **no** root, so the row violates `channels_no_orphan` and nothing else |
| `1b5-M3` | **The down migration's guard argued about a reference that does not exist.** *"If something references `channels`, the drop must FAIL"* — nothing references `channels`; that is `FLOW-19`, still open. **`REC-104`'s exact shape, in the file written to fix `REC-104`.** | the comment now says what it guards and what it does not, and names `FLOW-19` as still open |

#### What the refuter could NOT break

`channels_parent_fk` stops a cross-reality parent **structurally** — the shared `reality_id` column
makes it inexpressible, and the `MATCH SIMPLE` NULL escape was hunted specifically and is closed
because `reality_id` is `NOT NULL`. Constraint attribution is genuine on `INSERT` **and on `UPDATE`,
which the smoke never exercises** — seven mutation paths, each refused by the right constraint.
`channels_root_single` is the right index with the right predicate. The migration applies cleanly on
the real `0001`->`0019` chain. A wrong-shaped pre-existing `channels` is **not** silently accepted
(the index creation catches what `CREATE TABLE IF NOT EXISTS` masks). The gate's self-test runs on
**every** invocation and cannot be skipped. And `REC-103`/`REC-105` are both confirmed sound —
`0014_channel_ordering.up.sql:31` really is `PRIMARY KEY (reality_id, channel_id)`, so the composite
shape is forced rather than chosen.

### `1b.6` — the `1b.5` BLOCK discharged. **All ten itemised findings, with evidence.**

**Live Postgres 18 (`infra-postgres-1`), throwaway `dp_slice1b_smoke_test`, dropped after: 46/46.**
The migration has still never been applied to a real database, so `0019` was AMENDED IN PLACE rather
than superseded by an `0020`.

#### `REC-106` — `DP-Ch1`'s anti-cycle mechanism, implemented instead of asserted

`1b5-H2` and `1b5-H3` were always one defect, and `12_channel_primitives.md:97` had been naming the
missing mechanism the whole time: *"No cycles. Enforced by `depth` (root = 0, children =
parent.depth + 1) + referential integrity on `parent`."* The first schema implemented the second half.
`depth` was a free-floating number.

```sql
parent_depth SMALLINT GENERATED ALWAYS AS ((depth - 1)::smallint) STORED,
CONSTRAINT channels_id_depth_uq UNIQUE (reality_id, id, depth),
CONSTRAINT channels_parent_fk FOREIGN KEY (reality_id, parent, parent_depth)
    REFERENCES channels (reality_id, id, depth) DEFERRABLE INITIALLY IMMEDIATE,
```

**A cycle is not rejected — it is not representable.** Depth decreases by exactly one along every
parent edge, so a cycle of length `k` requires `d = d - k`. Seven attacks, each refused by
`channels_parent_fk` and each pasted in the smoke output: a self-parent · a child of the root claiming
`depth 16` · a child at its parent's own depth · a 2-cycle by `UPDATE` · **a cycle built inside one
transaction with `SET CONSTRAINTS ... DEFERRED`, which fails at `COMMIT` and leaves zero rows** ·
deleting the root · re-parenting a node whose children still reference its depth.

Three consequences, none of them optional and all of them stated rather than discovered:

| | |
|---|---|
| **`channels_no_self_parent` was REMOVED** | The foreign key makes a self-parented row unrepresentable, so the `CHECK` could no longer fail. Keeping it for readability is `NV-1` — and `1bF-2`, the vacuous `UNIQUE (id)`, is the same defect in the same table. The proof is the bite: drop `channels_parent_fk`, and the row `channels_no_self_parent` used to catch **inserts**. |
| **Re-parenting became a SUBTREE operation** | A parent's `depth` is referenced by its children, so it cannot move one row at a time. That is why the key is `DEFERRABLE`, and the escape hatch does not weaken anything: the impossibility is arithmetic, not a matter of check timing. Both halves are measured — the rigid path is refused, the deferred subtree move succeeds, and the resulting tree is printed. |
| **`1b5-L4` closed as a byproduct** | The index gives *at most* one root; this key gives *at least* one for any non-empty reality, because walking `parent` strictly decreases `depth`, so the walk terminates, and only `depth = 0` can terminate it — which `channels_no_orphan` forces to be a root. **Exactly one**, which is what `DP-Ch1` says. |

#### The one that was found by running it: `1b5-M2`, recreated by the fix for `H2`/`H3`

The first smoke run after `REC-106` landed came back **44/46**, and the two red legs were `no orphan`
and `depth bounded`. Their violating rows were now refused **twice** — a child at `depth 0` has
`parent_depth = -1`, and a child of the root at `depth 17` needs a parent at `depth 16`; neither
exists, so `channels_parent_fk` refused both before the constraint under test ever ran.

**That is `1b5-M2` exactly — a row refused by two barriers — recreated by a decision made two hours
earlier in the same slice.** It is `NV`'s hardest shape, *an adjacent decision defeats it*, and the
only reason it did not ship is that the bite harness asks each constraint to be the SOLE refuser.
The rows were re-chosen so the foreign key is satisfied: a **root** at `depth != 0` in a reality with
no root (`parent IS NULL`, so the `MATCH SIMPLE` key is never checked, and `channels_root_single` is
not a second barrier either), and a **genuine 17-deep chain** so the violating row's parent really is
at `depth 16`. Building that chain is the cost of proving the bound still does independent work —
past `REC-106`, `depth 17` is not reachable by declaration, only by digging.

#### The rest

| id | discharged by |
|---|---|
| `1b5-H1` | The three other locked SQL sites amended — `13:209` (a `channel_writer_state` that does not exist: wrong type, wrong arity, wrong reference, **and** a column set superseded by `0014`/`0015` without the document moving), `16:339` (`bubble_up_aggregator`, spec-only, no migration), `17:63` (a second locked `ALTER TABLE channels`). **The gate now globs every `.md` in `06_data_plane/`** — 26 documents — so a file created tomorrow is covered by existing rather than by an author remembering (`NV-3`). `17:63`'s five columns have **no writer and no reader anywhere in the tree**, so migrating them would be apparatus with no subject; they are a `PENDING_ALTERS` row naming what would wake them up, and **the register is built to SHRINK** — if `0019` gains one, the gate reds until the row is retired. |
| `1b5-H4` | The gate parses the table **structurally** instead of line by line: columns with `NOT NULL`/`DEFAULT`/`GENERATED`, the `PRIMARY KEY` list, every constraint body including the foreign key's referenced columns, actions and deferrability, and every index's uniqueness and partial predicate. **11 mutations are each proven visible** in the self-test, including the four-way mutant that used to apply cleanly. |
| `1b5-M4` | `channels_id_positive` and `channels_level_name_nonempty`. `REC-103` cited the wire contract's unsigned `Uint64String` and carried the **width** across without the **domain**; `DP-Ch11` allocates `MAX() + 1`, which starts at 1. |
| `1b5-M5` | Everything is normalised before comparison — keyword and type case, whitespace, `IF NOT EXISTS`, the space before `(`, and `int8`/`bigint` aliasing. **6 formatting changes are each proven invisible**, including the exact two the refuter used. |
| `1b5-L3` | Written down rather than left to be discovered: a dissolved root **forecloses its reality permanently**, and that is correct — `DP-Ch11` never reissues an id, and a `lifecycle <> 'dissolved'` predicate would let a reality be re-rooted while the old tree's events still reference the old root. |
| `1b5-L5` | A `BEFORE UPDATE OF lifecycle` trigger. `DP-Ch31`'s terminal-Dissolved and `DP-Ch33`'s descendants-first are statements about a **transition**, which no `CHECK` can see — and `17_channel_lifecycle.md:77` attributed them to a *"row-level rule"* that existed nowhere. In the DB and not only in the SDK, because the spec says *"row-level rule **+** SDK transition validator"*. Children rather than descendants, which is not a weakening: a child may only dissolve when its own children have, so by induction the subtree is dissolved. Both rules bitten — drop the trigger and the forbidden transition goes through, with `pg_trigger 1 -> 0` printed. |
| `1b5-L6` | `scripts/migration-idempotency-validator.sh`'s default target list was **two files while the directory held 38**, so 36 migrations were default-uncovered — `NV-3`'s named shape, and the answer to *"what happens to a file created tomorrow?"* was measured rather than guessed: `0019` was written, committed and checked by a pre-commit hook that never looked at it, the 19th file to which that happened. Now a glob. Bitten by appending a bare `CREATE INDEX` to `0019` — **red at line 218**, and green again when removed. |

#### Found while fixing, and it was in the gate itself

**A markdown file is prose with SQL in it, and the prose is hostile input.** `norm()` tracks
single-quoted literals so `'active'` keeps its case — and English prose contains apostrophes.
``DP-Ch1`'s`` is one. **One unbalanced apostrophe in a sentence puts the rest of the file inside a
string literal and silently stops normalising it**, which is how the gate's first real run reported a
case difference as a schema disagreement. It had been reading whole documents rather than their SQL
fences. Fixed, and bitten at all three call sites — each reverted, each turns the self-test red.

### `1b.10` — **`1b.7` returned BLOCK from BOTH refuters, and they were right**

Two cold-start refuters against `adbfcdd9e`, each in its own worktree, given
**different jobs on different bytes**: one drove a live Postgres and attacked the
schema; one never ran a query and asked *what did nobody look at* (`BDR-37`'s
lesson — an adversary attacks what is there, and absences need their own pass).
**Both returned BLOCK. Neither found what the other found**, which is the whole
argument for the shape.

#### The one that was mine, and it was an argument rather than a bug

**`1b7db-01` / `1b7gap-H3` — a live channel can be created under a dissolved
one, and it falsifies the induction the other two lifecycle rules lean on.**
Both refuters found it independently. `0019`'s comment said: *"a child may only
reach Dissolved when ITS children are Dissolved, so by induction a Dissolved
channel's whole subtree is Dissolved."* **Induction over TRANSITIONS says nothing
about CREATION**, and the trigger fired `BEFORE UPDATE OF lifecycle` — so an
INSERT never consulted it, and neither did a re-parenting UPDATE, which names no
`lifecycle` column. Reproduced before fixing: `INSERT 0 1`. Both routes now
refused by `channels_no_child_of_dissolved`; the induction is true because a
third rule makes it true, not because it was asserted.

#### The four the live refuter found that I had no idea about

| id | what |
|---|---|
| `1b7db-02` | **The cycle guarantee lived in a COLUMN DEFINITION, which is DDL, not data.** `ALTER COLUMN parent_depth DROP EXPRESSION` needs only table ownership — no superuser, no rewrite — and then a caller supplies `parent_depth` by hand and self-parents in one statement; a deferred pair then builds a full 2-cycle with **zero roots**. Nothing asserted `parent_depth = depth - 1`. `channels_parent_depth_derived` does now, and its bite is INVERTED: drop the EXPRESSION, watch the CHECK start refusing, drop the CHECK, watch the row go in. **This is `NV`'s *"an adjacent decision defeats it"* against the very argument I wrote it to make.** |
| `1b7db-03` | `session_replication_role = replica` and `ALTER TABLE ... DISABLE TRIGGER ALL` suspend enforcement outright; rows persist and `pg_constraint.convalidated` still reports `t`. No table-level mechanism can defend against that. ⚠ Both need superuser — **and `loreweave`, the role every service in the compose stack connects as, IS superuser.** That is a deployment finding, recorded not fixed. The claim is now *"through ordinary SQL a cycle is not representable"*, because **the description was stronger than the mechanism**, which is `REC-104`'s own defect wearing my prose. |
| `1b7db-04` | **Three semantic mutations of the shipped migration left BOTH gates green.** A dormant child no longer blocking dissolution — because the harness never put a `dormant` row in the table at all, only used it as a rejection target. The trigger's `reality_id` tenancy filter deleted — because `seed_tree()` gave reality B a lone childless root, so no cross-reality row could be mistaken for a descendant. A 4th undocumented `lifecycle` value — because the smoke only ever probed `'zombie'` and the gate deliberately does not compare CHECK bodies. Three legs added, each because its absence was *demonstrated*. |
| `1b7db-07` | **Dissolving a subtree in one statement was IMPOSSIBLE, in every row order**, including an explicit leaf-first `ORDER BY depth DESC` — a `BEFORE`-row trigger cannot see the other rows its own command is updating. The only working shape was N single-row statements, documented nowhere. `DP-Ch33` is now an `AFTER` CONSTRAINT trigger, so it sees the statement's whole effect and is `DEFERRABLE` for a multi-statement subtree move. **A rule whose SHAPE forbids a legal operation is a design defect, not a strict reading.** |

#### The four the completeness critic found, which no attack could have

| id | what |
|---|---|
| `1b7gap-H1` | 🔴 **`0019` is applied by NOTHING.** `contracts/migrations/manifest.yaml` ended at `0013`; six migrations had shipped since, none registered, so the orchestrator has been applying an eight-month-old schema. `0019` was written, reviewed, **live-smoked 46 times**, gated pre-commit — and could not exist in a real per-reality database. **The gap was ALREADY TRACKED**: a manifest comment names `D-MANIFEST-0009-0012-UNREGISTERED` and explains four deliberately-unregistered files, and six more drifted straight past it. *A row is not a mechanism.* Fixed by registering `0014`–`0019` **and** by `scripts/migration-manifest-gate.py` (gate #91): every `*.up.sql` needs an entry or a reasoned exclusion, and the exclusion list must shrink. ⚠ This CHANGES WHAT THE ORCHESTRATOR APPLIES, which is the point and is called out rather than slipped in. |
| `1b7gap-H2` | 🔴 **`scripts/orphan-model-gate.py` was cited TWICE as the mechanism refusing a subject-less model — by me, in `17_channel_lifecycle.md`, and in `crates/dp-kernel/src/channel.rs`.** It cannot see either: it asks whether an **event** a projector handles has a **producer**, reads `.rs`/`.ts`/`.go`, and never opens a `.sql` file. It reports OK across 14k files while `channels` has no writer at all. **Citing a green gate for something outside its subject is worse than citing nothing — it reports evidence and silences review.** Both citations now state the REASON and stop borrowing a mechanism's authority. |
| `1b7gap-M1` | 🟠 **`REC-103`'s third leg cited the wrong allocator.** `DP-Ch11` is *"`channel_event_id` allocation"* — the position of an event WITHIN a channel, not the id OF a channel — and seven downstream comments inherited it, including a smoke label. The conclusion (BIGINT) stands on its other two legs. **Nothing in the corpus specifies how `channels.id` is allocated**, and that is now recorded as unowned rather than invented in a comment. |
| `1b7gap-M3` | 🟠 **`1b5-H1` said "one of FOUR locked SQL sites"; there are at least EIGHT.** Four more still declared `UUID` after `REC-103` — two of them within 200 lines of blocks the previous commit amended, one in a ` ```rust ` fence calling `channel_id.as_uuid()` (a method that does not exist; `grep` finds nothing), one in an unlabelled fence **inside the file the gate parses as schema authority**. All four were invisible because the scan read ` ```sql ` fences and two patterns. It now reads every fence of every language and the prose between them, skipping comments — and **all five re-introduced violations are bitten red**, so the comment-skip did not swallow the subject. |

#### What survived, and it is worth as much as the findings

The live refuter could not break the arithmetic. With the schema intact it found
**no ordinary-SQL route** to a cycle, a self-parent, a second root or a rootless
non-empty reality; `d = d - k` is genuinely unsatisfiable and the foreign key
re-checks on both sides when `depth` moves. Claim 2 — that `DEFERRABLE` does not
weaken it — was independently verified true, `COMMIT` refusing and leaving zero
rows. **Two overlapping deferred transactions** interleaved with `pg_sleep`, one
re-parenting and one shifting a child's depth, both aborted with the table
byte-identical afterwards. `INSERT ... ON CONFLICT`, `MERGE` and `COPY` all fire
the trigger and are not bypasses. And the bite legs were audited as honest: each
drops exactly its own constraint and shows the row move from rejected to
accepted. *"The harness's problem is coverage, not integrity."*

#### `1b7gap-M8` — the Phase-0 gate could not see the file where Phase 0 happened

`scripts/phase0-reconcile-gate.py` had `SPEC_ROOTS = ("docs/specs", "docs/03_planning")` and
`governed_specs()` returned **three files**. The Phase-0 discipline for this entire build lives in
`docs/plans/2026-08-06-game-tier-build-RUN-STATE.md` — a file the gate could not open — and
`CLAUDE.md` lists `docs/plans/YYYY-MM-DD-<feature>.md` as a first-class PLAN artifact in the same
table as `docs/specs`. **An omission, not a decision: `NV-3` at the process level, inside the gate
written to stop Phase 0 being skipped.** Scope widened; 3 governed specs → 4.

Two things fell out of doing it, and both were real:

* **The standards index had NO ROW for `DP-Ch1–Ch37`** — twenty-six LOCKED documents governing this
  tier, and nothing to reconcile *against*. The gate could not have checked this slice even had it
  been reading the right directory. Row added, naming the four mechanisms that now hold the family.
* **`Reconciles:` listed `FLOW-9` and `FLOW-19`**, which are this run's own audit findings rather
  than prior art. *Reconciles* means *"here is what I opened before designing"*; listing your own
  findings there inflates the look you took. They moved to a separate sentence. The field is also
  now ONE LINE, because the regex is `$` under `MULTILINE` and had only ever read the first — so
  the two unresolvable entries were the only two it would have seen, which is luck, not design.

Bitten both ways: remove the line → red; name a phantom row → red.

#### The sentence to carry forward

> **The migration's mechanism is strong, and its DESCRIPTION of the mechanism was
> stronger than the mechanism.** "Not representable" is not what a constraint
> gives you — a constraint gives you *"rejected, as long as the thing it depends
> on is still there."*

That is `REC-104` and `1bF-2` one level up: those were checks that could not fail;
this was a claim that could not be true. `BDR-41` records it.

#### `1b.9` — `1bF-3` DECIDED: **the `FLOW-19` foreign key is NOT added, and the reason is the reverse of the one expected**

`1bF-3` left this open on purpose — *"Whether to add it is a slice-1b decision, not an assumption."*
The slice's own framing was that `FLOW-19` becomes **writable** once `channels` exists at `BIGINT`
with a composite key, which it now does. The type-check is no longer the obstacle. Something else is.

| table | writer |
|---|---|
| `channel_writer_state` | **live.** `dp-kernel::acquire_writer_lease` INSERTs on every lease acquisition — `crates/dp-kernel/src/channel.rs:112`, with `ON CONFLICT (reality_id, channel_id) DO UPDATE`. |
| `channels` | **none.** No `INSERT`/`UPDATE`/`SELECT` against it anywhere in `crates/`, `services/` or `frontend/`. |

⇒ **Adding `FOREIGN KEY (reality_id, channel_id) REFERENCES channels (reality_id, id)` today would
make `acquire_writer_lease` fail for every channel**, because no channel is ever registered. It would
take a working code path and break it, in exchange for referential integrity against an empty table.

**This is *subject before apparatus* running in the opposite direction from usual.** The familiar
version is a mechanism with nothing to guard. This is a mechanism whose *target* has nothing in it,
and the cost of adding it lands on the one side that DOES work. The ordering is forced and it is
`SEALED-BUILD-ORDER`'s: the floor exists, the writer arrives with the SDK's write surface.

**Trigger, so this wakes up by itself:** the first non-test writer of `channels` — `DP-Ch11`'s
allocator on the tier-typed write surface (slice 4) or `DpControlPlane` (slice 5). `FLOW-19` stays
open and now says *why* it is open, which is a different sentence from the one it carried for eight
weeks (*"it could not have had a foreign key, because there was nothing to reference"*).

⚠ **And it names what `channels` is today: a table with no producer.** That is the `pc_*`/`npc_*`
shape and it deserves the comparison rather than a defence. The difference is the one `DPA-SWEEP`
drew for `prompt.rs` and the PO confirmed on 2026-08-06: **spec-first with a consumer pending is this
project's workflow; a model whose subjects were all DROPPED is rot.** `channels` is the first —
`FLOW-9` is that `06_data_plane/` specified it in Phase 4 and no migration ever shipped, and the
consumer is named, scheduled and two slices away. `scripts/orphan-model-gate.py` cannot see either
case, because it asks whether an EVENT has a producer, not whether a TABLE has a writer.

#### `1b.8` — the chain, and a finding that MEASUREMENT KILLED

The live smoke applies `0019` **alone, into an empty database**. That is right for testing the
table's constraints and it makes the smoke structurally blind to the other eighteen migrations —
and `1b.5`'s *"applies cleanly on the real `0001`->`0019` chain"* was measured **before `REC-106`
rewrote the file**, so by the time it mattered it described a previous version.

`scripts/dp-migration-chain-smoke.py` (new): **18 migrations applied AND retried**, `channels` as
**Postgres reports it** compared against `0019`'s declaration — 11 columns, 16 constraints (including
the seven `NOT NULL` rows PG17+ records in `pg_constraint`, which is `1b5-H4`'s subject asserted from
the database side), 6 indexes, the trigger, and `parent_depth` confirmed generated as `depth - 1`
because **that expression IS `REC-106`'s argument**; a 2-cycle refused on a chain-built table; the
down chain leaving an empty schema and no leftover function. `0008_pgvector_setup` is **skipped and
reported as skipped, not counted as a pass** — the `vector` extension is not installed in this
container.

**And a finding that did not survive being tested properly.** A naive chain test re-applies the whole
history and gets two failures — `0001_initial` (a later migration changed `events`' key) and
`0007_drift_metadata` (`0017`/`0018` narrowed an allowlist that `0007` seeds into). Against
`scripts/migration-idempotency-validator.sh`, which had just been widened to all 38 files for
`1b5-L6` and reports PASS on both, that reads as **exactly `BDR-36`'s shape — the check reads TEXT
where the property is BEHAVIOUR — inside the check I widened two hours earlier.** It is not. The word
*idempotent* covers two claims: **retry-safety**, which is what a crashed runner needs and what the
validator is a proxy for, and **whole-history replay**, which a versioned runner never performs.
Applying each migration and *immediately* re-applying it — the precise test — is **18 of 18 clean**.
Both replay failures are correct behaviour. ⇒ Recorded, with the distinction written into the
validator's own header, because the wrong version of this finding is one careless test away and it
would have cost a day.

#### ⚠ A discrepancy in the record, not in the code

`1b.5`'s header says **7 LOW** and its table itemises **six** (`L1`–`L6`). The seventh has no row and
no description, so it cannot be discharged, re-run, or looked up. Recorded here rather than
reconciled by quietly changing the count — the missing row is the finding.

### Slice board

| # | slice | done = |
|---|---|---|
| **0** | AMEND bundle | ✅ `217d325f0` + `3e6358749` |
| **1** | `crates/dp` — tiers, scopes, `DpAggregate` | 🟡 **Four rounds, four BLOCKs, 58 findings.** Round 3 retired the hand-rolled lexer for a real `syn` AST. **Not closed** — `G3`/`G4`/`G6`–`G13` are recorded and open, and no round has yet returned CLEAR. The residual limit is stated rather than closed: `dp-clippy` (`D-DP-CLIPPY-NOT-BUILT`). |
| **1b** | the `channels` table (`DP-Ch1/Ch2/Ch3`) | 🟡 **board written — §6j.** Phase 0 found three things before any code: `DP-Ch2`'s LOCKED schema says `UUID` and contradicts PO-approved `REC-102a` (`i64`); `channels_root_single UNIQUE (id)` is **vacuous** — `id` is already the primary key, so the constraint its name claims (*exactly one root*) is enforced by nothing; and `FLOW-19` becomes EXPRESSIBLE by this slice rather than blocked on it -- **expressible is not discharged**, and `1b.9` decides it stays open, with a trigger. |
| **2** | `dp::forbid_raw_kernel_client`, shipped RED | ⬜ *board TBD.* **Carries `[package.metadata.dp] dp-crate = true`**, removed from `crates/dp/Cargo.toml` by `V1-F12`: it is `DP-K11`'s marker and it is the right shape, but its only reader is this lint. It lands in the same commit as the thing that reads it. |
| **3** | `RealityId` + `SessionContext` | ⬜ *board TBD* |
| **4** | tier-typed write surface | ⬜ *board TBD* |
| **5** | `DpControlPlane` | ⬜ *board TBD* |

**Boards are written per slice, at its start, not all now** — a board for slice 4 written today would
be graded against a design that slices 1–3 will change, which is how a DoD becomes decoration.

## 6j. `SLICE-1b` — the `channels` table. **Board written first, at the slice's start.**

> `BDR-26` is the rule this obeys: *a finished slice is not a licence to start the next one; the next
> one starts when its board exists.* Slice 1 ended green four times over, and green is not authority.

### Phase 0 · AUDIT-EXISTING — three findings, before a line of migration

Asked the three questions with commands rather than memory, and all three answered something.

| # | finding |
|---|---|
| `1bF-1` | 🔴 **`DP-Ch2`'s LOCKED schema contradicts `REC-102a`, which the PO approved on 2026-08-07.** The spec declares `id UUID PRIMARY KEY, parent UUID REFERENCES channels(id)`. `REC-102a` settled `ChannelId` as **`i64`** — because two of the three artifacts said 64-bit (the shipped `crates/dp-kernel/src/channel.rs`, verified `pub struct ChannelId(pub(crate) i64)`, and the client wire contract's `Uint64String`), and because `DP-Ch11`'s allocator is a **monotonic per-channel counter seeded from `MAX()`**, which is what a `BIGINT` is for and which a `Uuid` cannot do. **The migration must be `BIGINT`, and `12_channel_primitives.md` needs the amendment `REC-102a` implied and did not reach.** |
| `1bF-2` | 🟠 **`CONSTRAINT channels_root_single UNIQUE (id)` is vacuous.** `id` is already `PRIMARY KEY`, so the constraint adds nothing and can never fire. Its NAME says what it was meant to do — *exactly one root per reality* — which is a real invariant (`DP-Ch1`: *"a strict tree; every channel except the root has exactly one parent"*) and is **enforced by nothing**. The honest form is a partial unique index on `(parent IS NULL)`. This is a check that cannot fail, in a LOCKED spec, which is `NV-1` and was sitting there before this run. |
| `1bF-3` | **`FLOW-19` becomes EXPRESSIBLE by this slice.** (⚠ This read *"is discharged BY this slice"* until `1b7gap-H4` measured the contradiction: two artifacts said discharged, `0019_channels.down.sql:12` and `13_channel_ordering_and_writer.md` said still open, and `FLOW-*` appears **zero** times in `scripts/deferral-gate.py` -- so nothing would have noticed if the key never landed. `1b.9` decides it stays open and `flow19_trigger()` in the schema gate reds the moment `channels` gains a non-test writer.) `channel_writer_state.channel_id` ships as `BIGINT` with **no foreign key** — which it could not have had, because `channels` has no migration (`FLOW-9`). Once the table exists at `BIGINT`, the FK becomes writable. Whether to add it is a slice-1b decision, not an assumption: it is a per-reality DB, and the lease table is keyed `(reality_id, channel_id)`. |

**Reconciles:** `DP-Ch1–Ch37`, `DP-A1–A19`, `Locked Decisions ledger`

Which is: `DP-Ch1` (the tree) · `DP-Ch2` (the registry) · `DP-Ch3` (the delta stream) · `DP-Ch11`
(the allocator — **and `1b7gap-M1` later measured that it allocates `channel_event_id`, not
`channels.id`**) · `DP-Ch13` (the writer lease) · `DP-Ch31`–`DP-Ch37` (lifecycle) · `DP-A2` (CP not
on the hot path — why this is per-reality and not CP) · `REC-102a` (`ChannelId` is `i64`). **The
`DP-Ch1–Ch37` row did not exist in the standards index until `1b7gap-M8`** — twenty-six LOCKED
documents governing this tier, and no row, which is why the Phase-0 gate could not have checked this
slice's reconciliation even had it been reading `docs/plans/`.

**What this slice DISCHARGES, which is a different list** (`1b7gap-M8`): `FLOW-9` (the table does
not exist) and `FLOW-19` (the lease table references it anyway) — both findings of §6h, this run's
own audit, not rows of the standards index. They stood inside the `Reconciles:` field until the
Phase-0 gate was widened to `docs/plans/` and rejected them by name. **The gate was right and the
distinction is real:** *reconciles* means *"here is the prior art I opened before designing"*, and
listing your own findings there inflates the look you actually took. It also only ever read the
FIRST line of the field — `$` under `MULTILINE` — so the two unresolvable entries were the only two
it saw, which is luck rather than design and is why the field is now one line.

### Why §0's DoD applies here and slice 1's does not

Slice 1 re-derived Axis 2 as *"the compiler on adversarial input"* because `crates/dp` declares no
I/O. **1b is a migration.** It has a live subject, so the substitute is not available and would be
dishonest: `S2.3`'s *"live infra unavailable"* line does not transfer, and copying it would be the
borrowed row §6i's own "What does NOT satisfy this" forbids by name.

| axis | 1b |
|---|---|
| **CODE** | migration applies to a throwaway DB · `sqlx`/driver-level types match `ChannelId`'s `i64` · workspace builds · full pre-commit |
| **RUN** | **a live Postgres.** Apply forward, insert a root and a child, assert the tree constraints REJECT what they name — a second root, an orphan at `depth > 0`, a root at `depth != 0`, a `depth` past 16, a bad `lifecycle`. Each rejection is the DB's own error, pasted. **`live infra unavailable` is NOT available to this slice**; if Postgres cannot be reached, the slice does not close. |
| **MEASURE** | row counts · the reject cases as a table of `(input, SQLSTATE, message)` · `MAX(id)+1` allocator behaviour under two concurrent inserts |
| **BITE** | drop each constraint, show the violating row now INSERTS, restore. A `CHECK` nobody has inserted against is `1bF-2` again. |
| **`V.1`** | cold-start refuter, **worktree-isolated, against a commit** (`BDR-35`) |
| **`V.2`** | the oracle parses `DP-Ch2`'s `CREATE TABLE` out of `12_channel_primitives.md` and compares it to the migration — column names, types, and the `CHECK` bodies. `FLOW-2`'s alarm, on the one artifact where spec and code are both SQL. |

### Slice board

| # | done = |
|---|---|
| `1b.0` | ✅ `REC-103` (`UUID` → `BIGINT`), `REC-104` (`channels_root_single` made able to fail), `REC-105` (`reality_id` + composite keys). Spec before code. |
| `1b.1` | ✅ `contracts/migrations/per_reality/0019_channels.{up,down}.sql` |
| `1b.2` | ✅ **24 checks on a live Postgres.** Every constraint rejected what its name claims — with the database's own `SQLSTATE` — and accepted what it must, including a root in a *different* reality. Down migration reverses to zero tables. |
| `1b.3` | ✅ `scripts/dp-channels-schema-gate.py` — spec SQL vs migration SQL, wired pre-commit. Bitten on **both** sides plus a `REC-104` regression. Stated limit: it does not compare `CHECK` **bodies**, because two spellings of one predicate would cry wolf; that half is `1b.2`. |
| `1b.4` | ✅ each of the six constraints DROPPED and its violating row shown to **insert**, then restored. A constraint that rejects with it and accepts without it is the only proof nothing else is silently backstopping it. |
| `1b.5` | 🔴 **BLOCK** — 4 HIGH / 5 MEDIUM / 7 LOW. Five discharged at the time (the three FALSE claims + two absent mechanisms); `H1`-`H4`, `M4`, `M5`, `L3`-`L6` were left OPEN. |
| `1b.6` | ✅ **all ten remaining findings discharged, on a live Postgres 18 — 46/46.** `REC-106` makes a cycle *unrepresentable* rather than rejected (seven attacks, including a deferred one that fails at `COMMIT`), which closed `H2`/`H3`/`L4` and forced the removal of `channels_no_self_parent` as newly vacuous. The gate was rewritten from line-shaped to structural and from one file to a **glob over all 26** tier documents. `1b5-M2` **recurred**, caught by the bite harness on the first run after `REC-106`: two violating rows became double-refused by the new foreign key. `1b.5`'s own record is one LOW row short of its own count. |
| `1b.7` | 🔴 **BLOCK from BOTH refuters — 8 HIGH / 9 MEDIUM / 8 LOW, and neither found what the other found.** One drove a live Postgres; one never ran a query and asked what nobody looked at. Both independently found that a live channel can be created under a dissolved one, which falsifies an induction argument I wrote. |
| `1b.10` | ✅ **every HIGH and MEDIUM discharged, re-verified live: 54/54.** `0019` was applied by NOTHING (the manifest ended at `0013`, six migrations unregistered, past a row that tracked four); the cycle guarantee lived in DDL rather than data; three semantic mutations left both gates green; a one-statement subtree dissolve was impossible in every row order; and `orphan-model-gate` was cited twice for something it cannot see. |

**`1bF-4` was found DURING the build, not by the board** — every shipped per-reality table keys on
`(reality_id, …)`, so `DP-Ch2`'s single-column `id` made the `channel_writer_state` foreign key
**inexpressible**, and following the spec literally would have re-created `FLOW-19` inside the
migration written to discharge it. Recorded as `REC-105` and flagged: it is the one **judgement** in
1b rather than a correction, and nothing has run against a real database.

## 6k. `SLICE-2` — Phase 0 only. **The board is NOT written and slice 2 has NOT started.**

Run while `1b.7`'s refuters were working, because Phase 0 reads `crates/` and `services/` and they
read `scripts/` and `docs/` — different bytes, no rework risk either way. `BDR-26` still holds: the
board gets written when the slice starts, and it does not start while `1b` is open.

Three questions, each answered with a command.

| # | finding |
|---|---|
| `2F-1` | ✅ **The subject is real, and it is large.** `DP-R3`'s lint has something to be red about on day one: `sqlx::` appears in **36 files across three services** — `world-service` 16, `commit-service` 12, `roleplay-service` 8 — and **15 across four crates** (`dp-kernel` 8, `meta-rs` 3, `service-http` 3, `world-gen` 1). This is the opposite of the `pc_*`/`npc_*` finding: a mechanism whose subject exists before the mechanism does. |
| `2F-2` | 🔴 **`DP-R3`'s own exemption names a crate that is not where the database code lives.** [`11_access_pattern_rules.md:66`](../03_planning/LLM_MMO_RPG/06_data_plane/11_access_pattern_rules.md) locks the rule as *"scans for forbidden imports in any crate other than `dp` itself"*. Applied literally it fires on **`crates/dp-kernel`**, which holds `event_store_pg.rs`, `outbox.rs`, `load_aggregate.rs` — the code whose whole job is to touch Postgres. `dp-kernel` was created five weeks *after* this rule was locked, by a different track; that is `FLOW-6` again, arriving as an exemption list that cannot be right. **The slice must decide what the exempt set IS, and derive it rather than type it** — an enumerated crate list is `NV-3`, and this is the second time in this run that an enumerated list has been the defect. |
| `2F-3` | 🔴 **The enforcement mechanism `DP-R3` names does not exist, and neither does any infrastructure for it.** It specifies a *"custom clippy rule `dp::forbid_raw_kernel_client` … Presence = lint error, breaks CI."* A real custom clippy lint needs `dylint`, `clippy_utils` or `rustc_private`: **grep finds none of the three anywhere in the tree.** Meanwhile the repo has **90 wired gates**, each with a self-test and a bite, which is the mechanism that actually holds every other rule here. ⇒ **This is a decision slice 2 must make out loud, not discover halfway through**: stand up a dylint toolchain to honour the letter, or implement the rule as a wired gate and amend `DP-R3`'s enforcement line to say what enforces it. `D-DP-CLIPPY-NOT-BUILT` names the debt and does not name this fork. |
| `2F-4` | 🟠 **`roleplay-service` is a THIRD candidate game-layer service, and `DPA-SCOPE` named two.** It carries `sqlx::` in 8 files and `reality_id` in `services/roleplay-service/src/handlers/mod.rs:10` and `services/roleplay-service/src/models.rs:32`. `DPA-SCOPE` derived *"game-layer ⇒ uses the SDK"* from `01_scope_and_boundary.md` §4 and cited `commit-service` and `world-service`. Whether `roleplay-service`'s `reality_id` is a per-reality DB access or a foreign key in a platform DB decides whether the RED allowlist is 28 files or 36 — **and nobody has looked.** |

## 7. Registers — append as it happens

### Decisions

| # | sealed | |
|---|---|---|
| **`SCOPE-1`** | 2026-08-06 | **The scope contract is SEALED** — [`2026-08-06-command-hub.md`](../specs/2026-08-06-command-hub.md). The DUMB DRIVER test decides in-or-out; the architecture line is the actor hub's one level up, and **if the two sentences stop being the same sentence, one of the two designs has drifted** |
| **`SCOPE-2`** | 2026-08-06 | **The chooser is a FEATURE, not a column.** `considerations`, `InputKind`, the effectiveness matrix and `attack_class` leave the substrate. The substrate owes the decision layer a **declared seam** and nothing else. `PO-5` is honoured, not overridden: it asked for the layer, and this says which side of the boundary it lives on |
| **`SCOPE-3`** | 2026-08-06 | **The substrate RESOLVES actions; it does not BUILD rulesets.** `CMD-13` and `O-CI-23`..`O-CI-25` are the **ruleset builder's**, not this layer's |
| **`SEALED-CMD`** | 2026-08-06 | 🔴 **PO: `CMD-10` is SEALED, and `CMD-1`..`CMD-6` with it.** The blocking condition was discharged three times over (prior art: 08-02 §3's six systems · the decision-layer round · the folded 08-05 round), and **`CMD-10`'s owed bite landed in `M2`** — `FORBIDDEN_VERB_KEYS` refuses three authority-bearing keys by name, with their reasons, and all three refusals are pasted. §4.1's forced order is discharged in the order it forced. |
| **`AUTHOR-1`** | 2026-08-06 | 🔴 **THE MANIFEST AUTHOR IS NOT A PROGRAMMER — PO, and this is a CONSTRAINT, not a preference.** *"The author is not a developer, and they usually use an LLM to produce the manifest, so if it gets too complex they cannot do it."* **Complexity in the AUTHORED SURFACE is a hard cost, priced against whatever it buys.** This is why `SEAM-1` resolves the way it does: striking `submitter_class` is not merely *"`CMD-10` came later"* — it **removes a field the author would have had to get right**, and a field whose wrong value is an authorisation defect. Consequences, stated so they are not re-derived: an extra `spend` row, a relation grammar, and a row that must name its own ordinal space each carry this cost and must earn it; `D-29` (*a declared THRESHOLD, never a predicate grammar*) is this axiom arriving from the other side; and where a space can be IMPLIED by the field's type it should be, because that is one thing fewer to write. |
| **`SEAM-1`** | 2026-08-06 | 🔴 **RESOLVED by the PO — strike `submitter_class` from the sealed contract's §4.** `CMD-10` is right and the build already followed it. See `AUTHOR-1` for the reason that decided it, which is stronger than seniority between two decisions. |
| **`SEALED-BINDING`** | 2026-08-06 | 🔴 **PO: DROP `012_player_character_index`. The user→actor binding gets a NEW table, in the META database.** The keep-argument did not survive measurement — the table has no writer anywhere so it is empty by construction; the GDPR path that reads it needs one line of Go and one row of YAML to follow a rename; the status enum is 5/6 wrong with two members that are PRESENCE, a second SSOT against the live transport; and `0017` had already set the precedent by DROPPING the sibling pc/npc artifacts. **The deciding reason is the NAME** — `player_character_index` carries the concept the new framing deleted, and `pc_id → actor_id` inside it is `quantity[0] = "hp"` one tier over. The DATABASE choice is unchanged and was never in doubt: meta, because the binding is CONTROL and control questions are cross-instance by nature. See §6g. |
| **`SEALED-BINDING` · BUILT** | 2026-08-06 | Migrations **034** (`actor_control_binding`, meta) + **035** (drop `player_character_index`, and swap the read-audit CHECK id). The decision above is now code. What moved with it, because a table swap that leaves its readers behind does not fail loudly — it **wedges the GDPR pipeline shut**, which is what this same file records happening to `pc_projection`: the erasure lookup, the meta-erasure leg (a scrub becomes a **DELETE**, since the new table has no PII to overwrite — the `@erasure_method: hard_delete` the header declares), the events allowlist (`pc.index.*` → `actor.control.granted/revoked/erased`), the sensitive-read path id, and **four cross-language mirrors that caught the rename by going red** (`meta-rs/sensitive_paths.rs`, `pii_l1a2_test.go`, `audit_l1a3_test.go`, `read_audit_test.go`). Two single-column PK-lookup rows were **removed, not renamed**, in both languages: the successor has no state machine and a COMPOSITE key. `player_index_parked_test.go` → `actor_control_binding_test.go`, re-pointed rather than deleted — its own trigger (*"if 012 was deleted"*) could never fire, because a migration file is history and you drop, never delete. On its first run the re-pointed guard found **three live references I had missed**. |
| **`SEALED-BUILD-ORDER`** | 2026-08-07 | 🔴 **PO: the build order is the APRIL DATA PLANE FIRST, then what was defined today.** *"I see the next build path now — the right one is the data plane from April, then the thing we defined today."* **This names what every finding of 2026-08-06/07 was a symptom of: the actor hub and the command substrate were built on BARE GROUND.** `01_scope_and_boundary.md` §1 locks *"the SDK is the only door"* and §4 makes `commit-service`/`world-service` game-layer services by a mechanical rule — but the door was never raised, so they went straight to `sqlx`. Every downstream oddity follows: no tier tables (**no tier types to bind to**), `reality_id` a bare field in 86 places (**no `SessionContext` to derive it from**), 15 "owed mechanisms" (**really two unbuilt things: a service and an SDK**). ⚠️ **The consequence, stated so it is chosen and not discovered:** building the floor means the two shipped features get **RE-SEATED** onto it — the command substrate moves from raw `sqlx` to the SDK write surface. That is a real migration, and it is what the ordering buys: it happens once, on purpose, instead of twice. **Derived slice order** (from the measured dependency chain, cheapest-first, each with real value on its own): **(1) `DP-T0..T3` marker traits** — zero dependencies, and they give `DP-R2`'s tier table something to bind to, which discharges the debt this run has carried since it started. **(2) the `DP-R3` lint** — buildable today and it will be RED (`sqlx::` in 6+ commit-service files); shipping it RED with a shrinking allowlist makes the debt bounded and visible instead of invisible. **(3) `RealityId` + `SessionContext`** with a local binder, since the control plane is needed to VERIFY a capability, not for the types to exist. **(4) the tier-typed write surface** over `dp-kernel`'s existing event store — the plumbing is already there (15k lines). **(5) `DpControlPlane`** last, largest, stubbed until then. **No SDK crate exists**: the workspace has `dp-kernel` (plumbing) + `dp-kernel-macros`; the SDK is a new crate. |
| **`DPA-SCOPE`** | 2026-08-07 | 🔴 **The normativity question I asked the PO three times is ANSWERED — by a LOCKED document, mechanically, and it was there the whole time.** [`06_data_plane/01_scope_and_boundary.md`](../03_planning/LLM_MMO_RPG/06_data_plane/01_scope_and_boundary.md) **§4**: *"if a service reads or writes any aggregate in a **per-reality database** (`reality_<id>_db`), it is a **game-layer service and uses the DP SDK**."* `commit-service` and `world-service` both read/write the per-reality `events` table. **So by a rule that is LOCKED, both are game-layer services and must go through the SDK.** **§6 calls its five consequences *"mechanical enforcement rules, not principles to be interpreted"*, and at least three are untrue of the shipped tree today:** (1) *"Game services must NOT have direct Postgres credentials for per-reality databases — only the SDK does"* → both use `sqlx` directly. (2) *"must NOT have direct Redis credentials for the game-layer cache namespace"* → `game-server` holds the proposal streams. (5) *"every gameplay feature's design review includes a tier assignment check — **without it the review cannot pass**"* → actor hub and command hub have **zero** tier tables. **§1 locks Option (c) for exactly the reason the PO raised**: *"making any service bypass trivially possible defeats the 'no feature can violate the tier policy' guarantee… Option (c) makes the SDK **the only door**."* ⚖️ **The fair half: the SDK does not exist.** This is not going AROUND a door — it is building before the door was raised, which is this project's own spec-first workflow. The violation is a **debt with a name**, not misconduct. ⇒ And the taxonomy gap I spent the previous sweep chasing — the island's in-RAM, zero-loss, event-sourced actor state fits **no tier** (T1 accepts ≤30s loss + a Redis snapshot; T2/T3 read through a **projection**; `04b`'s SDK surface has `read_projection_*` and `t0..t3_write` and **no event-sourced primitive**) — is **downstream of that**, not a separate defect. |
| **`DPA-SWEEP`** | 2026-08-07 | **Two mechanical sweeps over the data-plane tier, and what they did NOT find is most of the result.** **(1) Code-first, every closed set in `dp-kernel` + `sim-core`:** ONE real defect — `AggregateType`, deleted (`SEALED-OPEN-KIND`). Five clean: `Class{Web,LlmGateway,…}`, `Kind{Counter,Gauge,…}`, `SourceLayer{PiiKek,…}` are infrastructure MECHANISM, the right side of `D-2`; `PresenceState` is a **governed** closed set (its doc states the change protocol — *"Go-AND-Rust in the same PR + a SQL CHECK migration"* — plus a Go mirror), which is what `AggregateType` had none of; ~20 error enums are mechanism. **(2) Doc-first, every table name in all 25 `06_data_plane` docs against 53 created / 14 dropped tables across all migrations:** ONE stale reference — `03_tier_taxonomy.md:135` still lists *"Session scoped memory writes into `npc_session_memory_projection`"* as a `DP-T2` **example**, and `0017` dropped that table. Six other docs name tables, all alive. **NOT edited: the doc is LOCKED, and unlocking is the PO's.** Severity is low (an example, not a definition) and it corroborates rather than extends the Phase-0 incident. ⚠️ **A suspicion that MEASUREMENT KILLED, recorded because an absent finding is evidence:** `dp-kernel/src/prompt.rs` (797 lines, `Intent{SessionTurn, NpcReply, …}`, `Section{SYSTEM, WORLD_CANON, …}`) looked like a second `AggregateType` — closed sets, LLM vocabulary, and **zero consumers on either side of its Go/Rust mirror**. It is not. It is a spec-driven mirror (`S09_prompt_assembly.md` §12Y.4) of a live Go package, naming its pending consumer in its own header (`roleplay-service`, scaffolded 2026-06-24). **Spec-first with a consumer pending is this project's workflow, not rot** — the distinction the PO drew on 2026-08-06, applied. It is a COST (two languages of mirror with no reader), not a defect, and I was one step from proposing to delete 797 lines of legitimate work. ⇒ **The cheap mechanical axes are exhausted.** What remains unclear needs reading rather than grepping: `DP-R2`'s tier tables, the ~6 overlapping ids, `DP-A3` vs `I3`, and the 15 owed `DP-R*` mechanisms. |
| **`SEALED-OPEN-KIND`** | 2026-08-06 | 🔴 **PO: `AggregateType` cannot stay — it breaks the plugin architecture at the LOWEST layer, and it closes the engine against extension.** `dp-kernel/src/entity_status.rs` declared `enum AggregateType { Pc, Npc, Region, WorldKv, Session }` — a **closed engine set carrying GAME VOCABULARY**, which is `D-2` inverted: the engine had closed on vocabulary instead of on mechanism, so a new aggregate kind needed an ENGINE RELEASE. **Three measurements make the deletion unarguable.** (a) All five members named projections that `0017`/`0018` **DROPPED** (`pc_*`, `npc_*`, `region_projection`, `world_kv_projection`, `session_participants`) — the enum outlived every one of its subjects. (b) **Zero consumers** outside its own file, verified with a full-tree grep. (c) `EventEnvelope.aggregate_type` was **already a `String` on BOTH sides of the wire**, so the enum closed a door the design had deliberately left open, in one helper struct. **And the Rust side was simultaneously MORE CLOSED and LESS VALIDATED than the Go mirror it claims to mirror**: `contracts/entity_status/resolver.go` has always used an open string AND checked it non-empty; Rust's `validate()` checked `entity_id` and `reality_id` and never the kind, because the enum made emptiness unrepresentable. So the deletion had to ADD a guard, not just remove a type — dropping a closed set without it would trade *"cannot be a new kind"* for *"can be nothing at all"*, a strictly worse bargain. Bitten: remove the check → RED. Neither `closed-set-gate` (its `ALL` list was complete) nor `orphan-model-gate` (it asks whether an EVENT has a producer, not whether an ENUM MEMBER still has a subject) could see it. **A third blind spot on Phase 0's question 1, found the same day the gate for it shipped.** |
| **`GUARD-1`** | 2026-08-06 | 🔴 **PO: *"is there anywhere a module that may not touch the DB reaching down to it, and how is that guarded?"* — the audit found NO live violation and THREE unguarded invariants.** Each was true, and true for no reason a machine could state. (a) **The kernel was outside its own gate.** `crate-purity-gate`'s `PURE_CRATES` listed `game-rules` + `actor-hub`, and R3 (*no I/O-capable std path in `src/`*) scans `crates/<name>/src` **for exactly the names in that list** — so `sim-core` and `ruleset-core` were **default-uncovered** (`NV-3`), including the one crate the whole determinism argument rests on. The gate's own header says R1 is transitive *"so a sibling crate written tomorrow is refused"*; that polarity was never applied to R3. Now guarded, `sim-core` with **empty** dependency sets so adding ANY dep to the kernel reds. **4/4 bites.** (b) **The transport tier had no capability rule.** 0/5 TypeScript services declare a DB driver and nothing would have noticed one arriving — `language-rule-lint` maps a service to a LANGUAGE and stops. New `scripts/tier-capability-gate.py`: R1 manifest (deps AND devDeps — that is how it would arrive first), R2 source imports (a workspace hoist makes a package importable undeclared), R3 subject check. `ioredis` deliberately allowed, with the reason written down: it is the **bus** the proposal goes ON, not a store of record. **4/4 bites.** (c) **`meta-write-discipline-lint.sh` ran nowhere** — see the cleared deferral. ⇒ **An unguarded true statement is one commit from being a false one**, and all three were found by one question rather than by any check. |
| **`SEALED-SUBJECT`** | 2026-08-06 | 🔴 **PO: THE SUBJECT IS RESOLVED ON THE KERNEL PATH, NOT ASKED FOR BY THE TRANSPORT.** *"The deferred part is right — because it has to go through the kernel. That is the architecture."* I had proposed a gateway/BFF route so `ChannelRoom` could LOOK UP the actor; that is the wrong shape. **Measured:** `ChannelRoom` puts `actor: Number(actor)` on the proposal and `admission.rs` accepts it — the producer SIGNATURE is verified, the SUBJECT is not. So `actor` is a wire field whose supplier is also its judge: **`CMD-10`'s V4 test failing on the transport instead of in a manifest**, and the same call `SEAM-1` made when it struck `submitter_class`. `PID-D5`'s comment sits *directly under* `pub actor: u64` making this argument about `event_category` (*"a proposal could elect its own trust tier"*) — one field over, never applied. ⇒ The proposal carries the **user**; the authoritative side resolves `user → actor` from `actor_control_binding`, which `commit-service` can already reach (`ruleset_boot.rs`'s `meta_url`). **Fixing the transport fixes one instance; moving the resolution kills the class** — a subject the caller cannot assert cannot be forged, so `CMD-11`/`CMD-12`'s offer MAC finally guards a door that is not already open. Tracked as `D-ACTOR-BINDING-NOT-READ-BY-TRANSPORT`; **seam recorded, NOT implemented.** |
| **`SEALED-CUE`** | 2026-08-06 | 🔴 **PO: the cue space is PER-REALITY.** `MAX_DECLARED_CUES` is now a named width **derived** from `MAX_DECLARED_VERBS` — every cue comes from a verb row and there is exactly one per row, so a reality with `N` verbs cannot need an `N+1`th. Refused at `declare` AND at decode; bitten (`if false` → RED, restored → GREEN). **No cue TABLE**, by `AUTHOR-1`: a reality declares cue NUMBERS and the words live in presentation content. The derivation is asserted, so a non-verb emitter arriving cannot widen it silently. |
| **`LIM-1`** | 2026-08-06 | 🔴 **PO: A HARD CEILING IS THE MANIFEST'S TO DECLARE, NOT THE ENGINE'S TO CHOOSE.** *"A hard ceiling should be pushed out for the reality manifest to decide, because we only build a world engine. A hardcoded number should be DATA and INGESTED, not a magic number inside the world engine. That is rot — if you find it, fix it rather than skip it."* The engine's refusal used to read *"exceeds this engine's capacity of 32"* — the engine answering *how big may this world be*, with a number chosen by whoever wrote the crate. **One number was doing two jobs**: a binary's array WIDTH (a deployment fact) and a world's declared SIZE (a design decision that was living in the wrong repository). Shipped: `ruleset-core/src/limits.rs` — `OrdinalSpace` (§3's register, now in code, four exhaustive matches deep) + `Limits`, folded from a `[limits]` block through `RulesetPatch::apply`, **before** the rows of its own layer so an author raises a ceiling and spends it in one file, and **per row** so the message names the row that did not fit. Three refusals, **two audiences**: `AtLimit`/`BelowDeclared` are the author's, `AboveCapacity` names a **rebuild** and is the deployer's. NOT in the digest and not on `Ruleset` — read once at ingest, never again (`RLS-A15`'s precedent; `QTY-A10(c)` breaks the tie), so `Limits` has no `CanonEncode` impl, the same structural exclusion `Provenance` uses. Capacity stays compile-time **deliberately**: runtime width means a heap allocation (`QTY-A6 ⊥ QTY-A12`), and a per-deployment `option_env!` knob is refused for a sharper reason — *two nodes of one cluster would disagree about whether a manifest is valid.* `MAX_DECLARED_VERBS` 16 → **64** with the repin 3696 → **6960**. See [`ordinal-spaces §4c`](../specs/2026-08-06-ordinal-spaces.md). |
| **`SEAL-ORDER`** | 2026-08-06 | `CMD-10` seals **first** — it is the test by which the rest are classified — and **its owed bite lands WITH the seal**, not after. Then `CMD-1`..`CMD-6`, re-scored under it |

### What the evictions changed — run immediately after sealing, because a goal aimed at a stale remainder is the wrong goal

| row | after `SCOPE-2` / `SCOPE-3` |
|---|---|
| `O-CI-12` per-archetype weighting | **RE-HOMED** to the decision-layer feature. It was never a substrate question |
| `R1-8` `Logistic` needs `exp` (`D-8` forbids it); the compensation factor self-refutes §2.2 | **RE-HOMED.** Both are properties of the chooser's *aggregation*. Note the feature inherits `D-8` — a float-free hashed substrate does not become float-friendly by moving one layer out |
| `R1-6` `effectiveness` is a MAP and `canon.rs` has no map primitive · `R1-7` sparse-with-a-default gives one behaviour two digests | **RE-HOMED** with the effectiveness matrix — **and they travel WITH it.** `R1-7` is `D-PROGRESSION-EMPTY-PIN` returning by the front door, and eviction does not fix it, it relocates it |
| `O-CI-16` six types named and never defined | **SHRINKS to five.** `InputKind` leaves with the chooser (it is `ConsiderationRow`'s input field). `ChanceSpec`, arity's home, a pair's `subject`, the two-role `EffectRow` and `RefKindMask` **all stay undefined** |
| `O-CI-7` one table or two | **NARROWED, not closed.** `A-7` counted four of six columns inert for `/sleep`; two of those four were `considerations` and `attack_class`, now gone. Two remain |
| `O-CI-10`/`O-CI-11` pair state | **STAYS.** A bribe's legality and an opposed check's magnitude are what-happened questions, not should-it questions. The dumb driver still needs them |
| `O-CI-19`/`O-CI-20` ordinal budget | **RELIEVED, not resolved.** Fewer columns; `RefKindMask` is still unpriced and still outside the six ordinal spaces (`AF-8`) |
| `CMD-9` spend ≠ weight | **CONFIRMED by the eviction.** It separated two meanings of one word; they now live in two different layers, which is the strongest possible form of that separation |

### Parked
| # | why | wakes on |
|---|---|---|
| `CMD-13` | needs two bundles to have a subject | the second bundle in a ruleset |
| `CMD-11`/`CMD-12` | a `Delta`-only verb on the actor itself takes no offered target | the first verb with a target role |

### Debt — 🔴 **SWEEP 2026-08-07: every open thread of the data-plane audit, with its trigger**

> **PO, 2026-08-07:** *"check whether every todo has actually been listed into the run-state — if not
> it will drift badly."* It had not. Before this sweep the Debt register held **three** rows, all
> from the command-substrate run, while the audit had produced **26 findings** and slice 0 had
> **queued three more** — every one of them living only in a session-local todo list, which is
> exactly the surface that evaporates. Recorded as `BDR-27`.
>
> **The `TRIGGER` column is the row's reason to exist.** This project's own rule: *a row is not
> enough — a tracked deferral needs a MECHANISM; intent is not a mechanism.* So each row below says
> **what would wake it up**, and the `M` column says whether that waking is **mechanical** (something
> changes colour by itself) or **prose** (a human must notice). Six are mechanical. **Thirteen are
> prose, and that is stated rather than dressed up.**

| # | what | trigger — what wakes it | M |
|---|---|---|:-:|
| `1b7db-03` | 🔴 **Every service in the compose stack connects to Postgres as a SUPERUSER.** `loreweave` is the **only** login role and it is `rolsuper = t`, `rolbypassrls = t` (measured 2026-08-08). A refuter used that to run `SET session_replication_role = replica` and `ALTER TABLE ... DISABLE TRIGGER ALL`, then wrote a persistent cycle and a rootless reality — rows surviving the session, with `pg_constraint.convalidated` still reporting `t`. **No table-level mechanism can defend against this**, so `REC-106`'s guarantee is *"through ordinary SQL"* and cannot be more. The `rolbypassrls` half has **no subject today**: `ENABLE ROW LEVEL SECURITY` / `CREATE POLICY` appear in **zero** files, although the standards index names RLS as a mechanism for LLM safety — so the index claims a defence the tree does not implement, which is its own finding. Out of scope for slice `1b`: the fix is a per-service role design, not a schema change. | a per-service Postgres role, OR the first `CREATE POLICY` (at which point `rolbypassrls` acquires a subject and this becomes urgent) | prose |
| `1b7db-08` | 🟡 `CREATE TABLE ... INHERITS (channels)` — no superuser needed — puts a self-parent, a dangling parent, a duplicate id and two roots into `SELECT ... FROM channels`. Constraints are not inherited by the parent's view of the child. **Conscious won't-fix:** the SDK is the only sanctioned writer (`DPA-SCOPE`, `01_scope_and_boundary.md` §1 Option (c)), and a caller who can run `CREATE TABLE` in the reality schema has already left the sanctioned path. Recorded so it is a decision rather than an oversight. | a non-SDK writer appearing in a per-reality schema | prose |
| `1b7db-11` | 🟡 **`channels_id_positive CHECK (id > 0)` constrains a derivation nobody has written.** `DP-Ch1`:96 says the root's `id == ChannelId::reality_root(reality_id)`; `04a_core_types_and_session.md:89` and `12_channel_primitives.md:39` both declare it `{ /* deterministic derivation */ }` and **it exists in no Rust file**. A naive i64-from-UUID hash is negative about half the time, so the constraint would break it — masking the sign bit is trivial, but the choice is now FORCED rather than discovered after the fact, which is the good direction. Unreconciled and recorded. | the first implementation of `ChannelId::reality_root` | mechanical — `channels_id_positive` refuses the row on the first live insert of a derived root |
| `D-CHANNELID-UNVERIFIED-22` | 22 `ChannelId::unverified` mints; **one is load-bearing** (`commit-service/src/manager.rs`, channel from the wire) | **slice 3.** The fn is deleted and **the compiler enumerates every site** | ✅ |
| `D-DP-DERIVE-DEFERRED` | `dp-derive` not built — with associated types the derive is ergonomics, not enforcement (`FLOW-8`) | the **first real aggregate**; until then it would have no non-test caller | ✅ |
| `D-LOREWEAVE-AGGREGATES-DEFERRED` | `crates/loreweave-aggregates` absent while `22 §5` cites it as the ✅ Do (`OOS-2`, `FLOW-14`) | **two services sharing one aggregate type.** Zero do today | ✅ |
| `D-DP-KERNEL-NAME-COLLISION` | `crates/dp-kernel` is not the SDK and fooled `12_module_coverage_audit` (`FLOW-7`, `REC-100`) | **`crates/dp` landing** makes the ambiguity live in one workspace | ✅ |
| `D-Q13-BEHAVIOURAL-HALF` | slice 1 makes the tier *declaration* a compile problem; whether a T2 write path *behaves* as T2 is untested (`FLOW-12`) | **slice 4** — there is no write surface to observe until then | ✅ |
| `D-DP-S1-V1-TIER-ROW-WRONG` | `DP-S1` says V1 exercises *"T2/T3 only; T0/T1 not exercised"*; island memory is T1 and `20 §5` ships four RTM movement frames in the v1 wire contract (`FLOW-15`) | **slice 4 shipping T1** — the amendment lands with the code that falsifies the row | ✅ |
| `D-DP-REDIS-KEYSPACE-DISJOINT` | all four DP keys (`dp:events` · `dp:inval` · `dp:channel_changes` · `dp:writer_audit`) are **0**; the shipped publisher emits `lw.events.*` + `xreality.*`, governed by `DATA_ARCHITECTURE.md` `I7`, which the DP corpus never cites (`FLOW-21`) | slice 4's write surface must publish **somewhere**; the choice is forced then. **No mechanism until it is** | ⬜ |
| `D-DP-CLIPPY-NOT-BUILT` | 🔴 **The property `V1-F1` identified has no home that can fully hold it.** The type system cannot see across monomorphisations; `dp-aggregate-gate` reads **text before name resolution** and round 2 got six spellings past it (all now closed, but the closure is *at the token level*, which is not the same as closed). `include!`, a build script, a proc-macro or a determined `cfg` maze remain outside it. **`06_data_plane/` has named `dp-clippy` as one of its three crates since April** — a lint running *after* name resolution is where `type Tier = T` resolving to a parameter is decidable rather than guessable | 🔴 **PROSE-ONLY, and the row used to claim otherwise (`G4`).** It said *"MECHANICAL"* and named two **docstrings** as its mechanism — which `CLAUDE.md` calls out by example as the trap: *"a module docstring is prose that happens to live in a source file and does not count."* Written by me, in the commit discharging findings about that exact class. **What would actually wake it:** the day a `DpAggregate` impl ships in a crate `git ls-files` does not reach (a vendored crate, generated code, an `include!`), or the day a refuter gets a generic past the `syn` check — because `syn` parses syntax and the remaining escapes all need name resolution. `deferral-gate` cannot see this row: the game-tier RUN-STATE has no `deferral-registry` block | ⬜ |
| `D-DP-AGGREGATE-GATE-NO-PRODUCTION-SUBJECT` | **Every `impl DpAggregate` in the repo is test code** — three in `aggregate.rs`'s `#[cfg(test)] mod tests`, one in `tests/measure.rs` — and no `Cargo.toml` outside `crates/dp` depends on `dp` (`R2-10`, `V2-F7`). `R5` proves the gate can RUN; it does not prove the gate GUARDS anything shipped | **MECHANICAL**, and it is `R5` itself: the gate FAILS on `impls == 0`, so the fixtures cannot be deleted without the gate saying so — and the row closes on its own the first time a real aggregate lands, because that is when the subject stops being fixtures. Defensible for a slice that ships no aggregates; **not** defensible once slice 3 or 4 does | ⬜ |
| `D-DP-CH-SIXTEEN-UNEXPLAINED` | 16 of 18 Phase-4 symbols are zero **with no reason written anywhere**; `channel_pause` is the one that did it right, in two source comments (`FLOW-22`) | prose. **The mechanism that would fix the class**: a gate listing `DP-Ch` symbols with zero occurrences and no reason-comment — cheap, and not built | ⬜ |
| `D-DP-F10-DRILLS-NO-SUBJECT` | `DP-F10` gates every DP release on drills: **6 of 9 name components that do not exist**, 5 existing harnesses go unnamed, and `last_successful_drill` is 0 (`FLOW-26`) | **slice 5** gives three of them a subject; the CI gate stays inert until then | ⬜ |
| `D-Q2-SURVIVES-ITS-SUBJECT` | `Q2` is `open`, waiting on *"roleplay-service design maturity"* — and `AUD-F16` root 7 removed roleplay-service from the game loop, `REC-77` moved the originator to `commit-service::LlmDriver` (**built**), and the bus is **built** (`FLOW-13`) | **nothing.** A row whose dependency cannot mature never closes — which is why it is here: it needs a decision (close as OOS, or re-home), not a wait | ⬜ |
| `D-SEEDING-PHASE2-ABSENT` | `RealityManifest` = 8 design docs, **0 code**; the engine loads a reality's *rules* and cannot load its *world*. `38 §0` named it 2026-07-30; re-measured 2026-08-07, unchanged (`FLOW-3`) | **deliberately NOT in the slice order** — `FLOW-5` classifies the emission DAG as FEATURE. But the **lifecycle worker is foundation and is also absent**: `meta-rs/src/routing.rs` declares all six states and **no code drives `seeding → active`** | ⬜ |
| `D-CONTEXTRESOLVER-ABSENT` | the LLM's READ path has no owner in code. `prompt.rs` is 797 lines documenting its own emptiness; `GDA-D16` created `ContextResolver` to own it; **0 occurrences** (`FLOW-4`) | prose. Adjacent and already tracked: `GDA-D18` (S09 layers 4–7 all `Noop`) | ⬜ |
| `D-AMEND-BUNDLE-EVT-AGT-HALF` | `REC-53` · `REC-58` · `REC-68` · `AGT-A2`/`D1` — **untouched.** Slice 0 discharged the **DP half only**, and says so | the EVT/AGT tracks' own lock cycles. **Not mine, and the bundle must not read as discharged** | ⬜ |
| `D-DP-15-21-SYMBOL-LEVEL-ONLY` | `15`–`21` were swept at the **symbol level**, which settles *is it built* (no) and not *is the design sound* | slice 4/5 touching those primitives. Until then the second question has no subject | ⬜ |
| `D-DP-R4-VIOLATED-IN-DP-KERNEL` | `DP-R4` (cache keys via the macro, never hand-built) violated twice inside `dp-kernel` — `canon_cache.rs:100`, `entity_status.rs:380` | **slice 2's lint**, if its scope reaches `dp-kernel`; otherwise a fix-now during slice 4 | ⬜ |
| `D-DPA-SPEC-RETIRE` | `docs/specs/2026-08-06-data-plane-access-law.md` — 600 lines, **BLOCKED + superseded in substance** by `REC-99..102` and this audit | prose. It should be **retired**, not carried: a superseded spec that stays readable is the `12`-line-154 failure waiting to happen again | ⬜ |
| `D-OVERLAPPING-IDS-ADJUDICATE` | ~6 ids overlap between the DP corpus and the August specs, plus **`DP-A3` (Rust-only) vs `I3`** (TS realtime transport) | **PO decision.** Not derivable — both rules are locked and both have consumers | ⬜ |
| `D-AUDIT-READ-BYPASS-UNSCANNED` | `meta-sensitive-read-bypass-lint.sh`'s extractor **had matched nothing since the day it was written** (found by the same PO question as `GUARD-1`) | prose. Same class as the meta-write gate that ran nowhere — and that one is fixed | ⬜ |
| `D-ACTOR-BINDING-NOT-READ-BY-TRANSPORT` | `SEALED-SUBJECT`: the proposal carries `actor`, admission verifies the **producer** and never the **subject**. Seam recorded, **not implemented** | **slice 3** — `SessionContext` is where a subject stops being a wire field | ✅ |

**Six mechanical, thirteen prose.** The ratio is the honest finding of this sweep: most of what the
audit surfaced is waiting on a *slice*, and a slice arriving is not something that changes colour by
itself. **The cheapest single mechanism available** is the one named in
`D-DP-CH-SIXTEEN-UNEXPLAINED` — a gate that refuses a `DP-Ch` symbol which is neither built nor
explained — and it would convert three of the prose rows at once.

### Debt — carried from the command-substrate run
| # | |
|---|---|
| `D-VOCAB-BINDING-TABLE-DRIVEN` | `CMD-8`, deferred to BUILD — **this run is that BUILD.** Its trigger is mechanical and already stated: the fifth tool in any `contracts/agent/vocabularies/*.json` makes `contains()` and `validate()` disagree |
| `D-REPLAY-PIN-REFUSAL-UNDEFINED` · `D-RNG-COORDS-SNAPSHOT-ONLY` · `D-NO-INPUT-LOG` | escalated 2026-08-06, each with a `PROSE_ONLY` trigger |
| `D-PROGRESSION-LIMITS-UNDECLARED` | **`LIM-1` covers three of the four author-extensible spaces.** `MAX_DECLARED_PROGRESSION_KINDS` and `MAX_TIERS_PER_KIND` are the same class and are NOT in `[limits]` — structurally, not by oversight: a progression kind folds into a stored TABLE referenced by digest (`S-1b`), not into the `Ruleset` the limits fold walks, so it needs `resolve_and_pin`'s store arm. Gate #3 (naturally-next-phase). **Mechanism, not prose:** `progression_is_the_one_space_limits_does_not_yet_reach` reds the moment progression joins `OrdinalSpace`; and until then a manifest writing `[limits] progression_kinds` is refused BY NAME (`deny_unknown_fields`, asserted in `a_misspelled_limits_key_is_refused_rather_than_ignored`) rather than silently ignored — which is the failure that would actually hurt. |
| **the `FATAL-1` fix and `D-14`** | Stated rather than discovered later: `0c7577600` fixed the `CombatEvent` ↔ `DomainEvent` drift, and `CombatEvent` is combat vocabulary that `D-14` slates for **rewrite**. What survives the rewrite is the **mechanism** — the contract `$defs`, and a mirror test on each side checking against it rather than against the other language — and that is the part worth having, since it is what stops the *next* enum drifting. What does not survive is the variant list. The fix was still right: it closed a live defect (`renderEvent` returning `undefined` for facts the server emits) and removed a comment that falsely claimed test coverage. **`M1.3` should delete the variants and keep the mirror.** |

### Drift
**A run that ends with an empty drift log is dishonest.**

| # | what nearly went wrong |
|---|---|
| `BDR-42` | 🔴 **I cited a green gate as coverage for something it cannot see — twice, and one of them was in a file arguing against exactly that.** `scripts/orphan-model-gate.py` asks whether an EVENT has a PRODUCER. I cited it in `17_channel_lifecycle.md` and in `crates/dp-kernel/src/channel.rs` as the mechanism that refuses *a model with no subject* — a column with no writer, an unused constructor, a table nothing writes. It reads `.rs`/`.ts`/`.go`, never opens a `.sql` file, and reports OK across 14k files while `channels` has no writer at all. **What makes this worse than citing nothing is that it reports evidence and silences review**: the next reader sees a named, wired, green gate and stops asking. ⇒ **Before citing a gate as covering X, read its subject line and check that X is in it.** The tell I ignored: I had *independently derived* this exact gap earlier in the same session — "orphan-model-gate asks whether an event has a producer, not whether a contract has a consumer" — and then wrote the false citation anyway, two hours later, in a new file. **Knowing a mechanism's limit does not stop you invoking it; only checking at the point of citation does.** |
| `BDR-41` | 🔴 **The DESCRIPTION of a mechanism can be stronger than the mechanism, and that is a distinct defect from a check that cannot fail.** I wrote that a cycle is *"not rejected — it is not REPRESENTABLE"*. The arithmetic is sound and survived every ordinary-SQL attack. But the guarantee rested on `parent_depth = depth - 1`, which lived in a **column definition** — DDL, not data — and `ALTER COLUMN ... DROP EXPRESSION` needs only table ownership. A refuter self-parented in one statement and then built a 2-cycle with zero roots. ⇒ **A constraint gives you "rejected, as long as the thing it depends on is still there", and any sentence stronger than that is a claim, not a property.** `REC-104` and `1bF-2` were checks that could not FAIL; this is a claim that could not be TRUE, and no amount of biting the constraint would have found it, because the constraint worked. What found it was someone asking *what does this rest on?* |
| `BDR-40` | 🔴 **A gate I wrote to compare SQL was reading English prose, and the failure mode was SILENT DEGRADATION rather than a crash.** `norm()` tracks single-quoted literals so `'active'` keeps its case. A markdown document is prose with SQL in it, and prose has apostrophes — ``DP-Ch1`'s`` is one. **One unbalanced apostrophe puts every byte after it inside a string literal**, so normalisation quietly stops and the comparison starts failing on case. It reported that as a schema disagreement on its first real run. ⇒ **A parser pointed at a file format it was not written for does not error — it succeeds on the wrong bytes.** The fix is one line (`sql_only`), and the reason I did not see it is that both the spec and the migration ARE SQL, so "just parse the file" felt like the whole design. It is not: one of them is a document that CONTAINS SQL. |
| `BDR-39` | 🔴 **`1b5-M2` recurred inside the commit fixing `1b5-H2`, and the two decisions were each individually correct.** `REC-106` put `depth` in the parent foreign key. Two bite legs' violating rows — a child at `depth 0`, a child of the root at `depth 17` — thereby became refused by the foreign key *before* the constraint under test ran, so neither leg proved its own constraint was load-bearing any more. **This is `NV`'s hardest shape** (*an adjacent decision defeats it*) and it is the second time in this slice that a row was refused by two barriers. ⇒ **A new constraint does not only add coverage; it can silently REMOVE the exclusivity of an old one.** The only reason it did not ship is that the bite harness demands each constraint be the SOLE refuser — a property no amount of "the tests are green" would have shown, because they were green. **The harness earned its cost here, in a way I could not have argued for in advance.** |
| `BDR-38` | 🔴 **I answered *"the type system cannot hold this"* with *"so the source can"* and never asked what a source check provably cannot do — then did it again one level down.** Round 2 broke the first lexer six ways and I rewrote it; round 3 broke the rewrite four more, and every one of the four was a fact about **Rust's grammar** that a partial reimplementation got wrong: the `>` of `->`, a raw identifier, a doc attribute, a C-string literal. **The rule `R6` states was correct throughout all three rounds.** What kept failing was that I was re-implementing a parser to check it, badly, in a language with no stake in Rust's grammar — while `syn` sat in the workspace's own `[workspace.dependencies]`, unused by me and already correct. ⇒ **When a check needs to understand a language, use that language's parser. A regex over a grammar is a claim that you know the grammar better than the people who wrote the parser, and eleven times over three rounds is the price of finding out you do not.** |
| `BDR-37` | **The completeness critic found five 🔴 gaps in work that two adversarial rounds had just certified — and they were not bugs, they were ABSENCES.** A scope taxonomy with no door · a directory covered in neither direction · 22 of 26 LOCKED documents opened by nothing · a debt row calling itself MECHANICAL while its only mechanism was a docstring · 23 bite legs wired to nothing. **Two refuters told to BREAK things found none of them**, because an adversary attacks what is there and every one of these is what is not. ⇒ *"Try to break it" and "what did nobody look at" are different questions, and a verification plan needs both.* The cheapest one was a `git mv`. |
| `BDR-36` | 🔴 **The two rounds are one defect wearing seven costumes, and it is mine.** Every finding across both refuters is *the check reads a PROXY for its subject*: the gate reads **text** where the property is about **types after name resolution** · the self-test reads a **re-implementation** where the subject is `scan()` · the tier set reads **`declare_tier!` invocations** where the subject is *types implementing `Tier`* · `parse_ms` reads **digits** where the subject is a *quantity with a unit* · `s3_4` reads **an array literal it just wrote** where the subject is the taxonomy · `as_key` pins **two of four** variants · the fixture exclusion reads **a floating substring** where the subject is one directory. ⇒ **The rule I did not have: a check must read the same thing the property is about, and must be driven through the same path production uses.** I had the first half (that is `NV-1`) and not the second, and the second is where five of the nine landed. |
| `BDR-35` | **I ran two cold-start refuters against a working tree I was editing at the same time.** The evidence refuter reported it: `git diff HEAD` was empty when it started and later showed three files it had never opened, and a probe file appearing and vanishing moved the gate's reported impl count **6 → 5 → 4 across its runs**. Nothing it concluded turned out to depend on the drift, and it flagged the anomaly rather than absorbing it — but that is the refuter being careful, not the method being sound. **A verifier's whole value is that its subject is fixed**; I gave it a moving one and got lucky. ⇒ *Refute a COMMIT, in a clean tree or a worktree — never a branch you are still typing into.* |
| `BDR-34` | 🔴 **`V1-F1` taught me the type system could not hold a property, and I did not ask the same question about the thing I replaced it with.** The reasoning went *"rustc cannot see across monomorphisations ⇒ check it over the source"* — and stopped. A source gate reads **text before name resolution**; the property is about **types after it**. Round 2 found six spellings of a generic the gate has no pattern for, four of them reproducing `V1-F1` exactly. **The tell was available and I walked past it twice:** `06_data_plane/` names **`dp-clippy`** as one of its three crates, `crates/dp/src/lib.rs` says so **in its own opening paragraph**, and I wrote that paragraph. The corpus named the right tool in April; I built the one I could finish in an afternoon and called the property enforced. ⇒ **When a mechanism is a fallback for one that provably cannot work, ask what the fallback provably cannot do — before claiming the property, not after a refuter asks.** |
| `BDR-33` | **I put `git checkout -- <file>` inside a bite script, on a file with uncommitted edits, and it reverted my own work.** The script mutated `gate-self-tests.py`, and I used `git checkout` as the restore step — on a file whose edits were not committed. It restored to HEAD, i.e. deleted the change under test, and the "restore" leg then reported the pre-fix number as though it were the post-fix one. Recovered by re-applying. Worth a row because it is `BDR-32`'s twin from the other side: **that one trusted a `finally` and did not check the bytes; this one checked out bytes that were never the baseline.** The rule both point at: *the baseline is what you read at the start of the bite, held in memory, verified by digest — never what a VCS thinks the file should be.* |
| `BDR-32` | 🔴 **The bite harness had been silently rewriting the line endings of LOCKED design documents on every run, and `git diff` could not see it.** `Path.read_text`/`write_text` open in text mode with `newline=None`, so on Windows the restore wrote CRLF wherever the file had LF. It was invisible for the exact reason that makes it worth recording: **`.gitattributes` normalises to LF on read, so `git status` and `git diff` both showed clean** — the two tools a reviewer checks with are the two tools blind to it. Found by `V1-F8`'s digest check on its **first run**, which is the argument for the check: the previous version restored in a `finally` and *asserted nothing about the result*. ⇒ **"the restore ran" and "the bytes are back" are different claims, and only one of them is checkable.** |
| `BDR-31` | **My fix for `BDR-32` rewrote 1069 files to repair 12.** The harness had touched four documents and a few sources; I ran the CRLF→LF normalisation across every tracked text file in the repo. It was content-neutral to git (`git diff --numstat` = 16, of which 12 were mine) and the four strays were reverted — so nothing was lost. But the blast radius was ~90× the problem, on a branch mid-slice, and had any of those 1057 files been genuinely CRLF-in-index I would have created a diff I did not understand across the whole tree. ⇒ **A repair's scope should be the damage's scope. I knew which files the harness touched — they are listed in the harness — and I swept the repo instead.** |
| `BDR-30` | **`mutated != original` passed while the mutation said nothing.** `BDR-19` made every bite verify that its mutation APPLIED; the `DP-S5` leg changed `"\| T2 writes"` to `"\| T2 writes "` — one space — so the bytes differed, the assertion passed, and the parse was **identical** because `table_cells` trims labels. The oracle stayed green and was right to. The leg scored red and I nearly filed it as a gate weakness. ⇒ **`BDR-19` is necessary and not sufficient: a mutation must change what the subject SAYS, not merely what it contains.** The same shape appeared twice more in one hour — a stale trait name that still *matched* because it was a prefix, and a struct-field anchor that pub'd one field of seven. All three were caught by the harness reporting red rather than by me reading it. |
| `BDR-29` | **I was one keystroke from fixing a gate by adding an entry to the list that was already the bug.** `no-absolute-host-paths` blocked the slice-1 commit on `target/tests/trybuild/dp/Cargo.toml` — a generated, gitignored file where `cargo` writes an absolute path by design. The obvious fix is `_SKIP_DIRS + {"target"}`, and it is **`NV-3` one entry later**: the next generated directory reopens it. The real defect was that the gate's SCOPE (`rglob` over the working tree) was wider than its SUBJECT (its own docstring says *committed* code). ⇒ **When a gate fires on something it should not see, ask what it is scanning before asking what to exclude.** Now scoped by `git ls-files --cached --others --exclude-standard`, which is strictly *"everything that could be committed"* — and it still reds on both a staged and an untracked offender, bitten in four legs. |
| `BDR-28` | 🔴 **I put an overclaim in front of the PO as the reason to approve a design, and the cold-start refuter broke it in one file.** The option I offered read *"an associated type has ONE binding — a second is not rejected, it is **unrepresentable**"*, and the PO approved on that basis. It is false: `DpAggregate` constrains the **impl**, not the **type constructor**, so `PlayerWallet<T: Tier, S: Scope>` lifts the tier into a parameter and a `Box<dyn _>` picks it per request — `DP-A9`'s *"not configurable per player"*, violated by the shape I sold as enforcing it. **The true claim was available and I did not write it**: *a single non-generic impl binds exactly one*. ⇒ **The failure is not the missing generic case — it is that I stated a guarantee at the strength I wanted rather than the strength I had checked**, in a decision put to the PO, in a session whose entire subject is documents claiming more than their code delivers. `FLOW-24` said the DP corpus never audited what it sat on; `V1-F1` says I never audited what I claimed. Same defect, and mine is worse because I had just finished writing about it. |
| `BDR-27` | 🔴 **Twenty-six findings and three PO-approved queue items lived only in a session-local todo list, and I did not notice until the PO asked.** The Debt register held **three** rows, all from the previous run. Every FLOW row was written into §6h *as narrative* — which reads as recorded and is not: a finding inside a 26-item essay has no trigger, no owner and no way to be re-read as a work item. The tell I missed is embedded in this file's own header: **the RUN-STATE exists because context is lossy**, and I had been treating the harness todo list as if it were the durable half. It is the opposite — **the todo list is the volatile one, and the file is the anchor.** ⇒ *a finding is recorded when it has a trigger, not when it has a paragraph.* |
| `BDR-26` | 🔴 **I went from a clean spec commit straight into writing code — no board, no goal, no verifier — and the PO stopped it.** Four files of `crates/dp` existed, uncompiled and outside the workspace, before anything said what *done* meant. The damning part is not that the rule is obscure: **§0 of this very file is a three-axis DoD with an independent verdict, and I had re-read it in this session.** What made it easy to walk past is worth naming, because it will recur: **slice 0 ended in a green commit**, and a green commit *feels* like a checkpoint that authorises the next thing. It authorises nothing — it closes the thing it committed. ⇒ **A finished slice is not a licence to start the next one; the next one starts when its board exists.** And the sharper form: I had spent the whole session proving that *intent is not a mechanism* in other people's documents, then relied on my own intent to keep a build honest. |
| `BDR-25` | **A regex over a type name is a regex over a WORD, and this tier has four things sharing one.** Migrating `ChannelId(` → `ChannelId::unverified(` swept `services/tilemap-service`, which has its **own unrelated `pub struct ChannelId(pub String)`**, and emitted `pub struct ChannelId::unverified(pub String);`. Caught by `cargo`, reverted in full, ~40 seconds lost. Worth recording anyway because **it is `FLOW-24` biting the person who wrote `FLOW-24`**: I had just finished documenting three name collisions between the DP corpus and the platform, and then took a fourth one in the face while acting on that very finding. The corpus-wide lesson holds one level lower than I stated it — **the collisions are not only between DOCUMENTS, they are between TYPES in one workspace**, and a rename is never safe on a name alone. |
| `BDR-23` | **I was one message from starting slice 1, and the PO stopped me to finish the review — which then found slice 0.** The build order was sealed, committed and pushed; every dependency in it was measured and every one of them held. What it was missing was not a dependency, it was a **precondition**: `REC-65` records `DP-K3`'s error enum already drifting across five documents, and slice 4 types the write surface against it. Building in the sealed order would have been correct and would still have baked the drift into the SDK's first line. ⇒ **A dependency graph answers *what can be built first*. It does not answer *what is safe to build against*, and I had only asked the first question.** |
| `BDR-24` | **I proposed `FLOW-AUDIT` as new work, and two of its four findings were already written down** — `38 §0` had printed the same six-phase chain with the same `❌ Phase 2` a week earlier, and `17`'s opening paragraph names the *"zero end-to-end flows"* defect in its own words. My contribution was **re-measuring them against today's tree** (both still true) and joining them to `FLOW-1`, which was new. Worth recording because the instinct on being asked *"keep reviewing"* is to look for something unfound, and here the unfound thing was **that two known findings were the same finding, and neither had moved.** |
| `BDR-1` | I opened this file about to write *"the first consumer is the command substrate"*, which is what the previous turn's summary implied. Measuring first showed the ordering is the other way and **derivable**: an `EffectRow` targets a quantity ordinal, so while the actor's numbers are struct fields the substrate cannot be declarative. A plan whose first line is wrong about its own order is worse than no plan. |
| `BDR-3` | **I wrote `M1` as a MIGRATION of `commit-service::Actor`'s nouns into quantities, and the PO corrected it mid-draft**: that struct is scaffolding built to prove the kernel and SDK work, and it is to be deleted. `D-11` and `D-14` both say so and I had read both in this same session. The correction matters because a port is the *comfortable* answer — it keeps every test green, it looks like progress, and it carries the old vocabulary into a new container, which is `D-2`'s failure exactly. **`quantity[0] = "hp"` would have satisfied `M1` as I first wrote it.** The slice board now defaults every legacy field to DELETE and forbids deriving a quantity from a struct field name. |
| `BDR-21` | **A cold-start red team returned BLOCK on the DPA spec, and the two most expensive findings were AUDIT-EXISTING misses in a document about not duplicating what exists.** `DATA_ARCHITECTURE.md` **§5 is a dedicated section on this exact plane** and line 343 already states invariant `I7` — *"`meta-worker` is the only consumer of `xreality.*` Redis Streams"* — **a single-reader rule for a Redis plane, in the file my spec says is silent, while my own table records Redis's port as "nothing".** And `scripts/restore-drill.sh` is **already a rebuild drill over a data plane**, so `DPA-A17` is that script generalised rather than a new pattern. I wrote a law against re-inventing registries and then re-invented one, without opening the file I cited as the model. |
| `BDR-22` | **Two of the spec's headline numbers were produced by commands that measured something else — the third and fourth time this run.** Redis *"40 files, 3 languages"*: the grep passed `--include=*.rs --include=*.go --include=*.ts` and **omitted Python, which is the largest group** (32 `.py` vs 27 `.go`). Manifest *"1 accessor"*: the grep matched `Ruleset::engine_default()` — **construction** — and I labelled the result *accessor*; the real count of `.rules()` call sites is **10**. Both shipped in a document whose second line reads *"every number below was measured"*. `BDR-9`/`BDR-17`/`BDR-19` are the same defect; this is the first time it reached a whole document rather than a sentence. ⇒ **the label MEASURED is not a claim about effort, it is a claim about the COMMAND — and the command has to be re-read against the word.** |
| `BDR-19` | **My bite harness reported a gate as vacuous when the harness was wrong, twice in one session, both times through CRLF.** `crate-purity-gate`'s R2 mutation and `sim-core/Cargo.toml` — the anchor was `"[dependencies]\n"` against a CRLF file, so the mutation silently did not apply and the run came back green, which I printed as **STILL GREEN — VACUOUS**. The same trap had already cost two mutations on `ChannelRoom.ts` an hour earlier. A harness that fails to mutate reports the SAME STRING as a gate that fails to catch, and the wrong one of those is a finding about the gate. ⇒ **a mutation harness must assert the mutation APPLIED before it runs the check** — `assert mutated != original` — and mine now does, but only after I had twice written a false verdict about someone else's code. |
| `BDR-20` | **I labelled a correct mechanism vacuous because I tested the wrong claim.** Unwiring `tier-capability-gate` from `.githooks/pre-commit` did not turn `gate-wiring-gate` red, and I wrote **STILL GREEN — VACUOUS**. Measuring: coverage comes from `--run-all` in CI iterating `discovered()`, and the gate's own docstring says so in as many words — *"the pre-commit hook still names the FAST gates individually. That is a latency optimisation, not the coverage story."* I ran a bite against a claim the file explicitly disclaims. **The measurement did land a real finding, but a different one:** `TOO_SLOW` REMOVED its member from `runnable`, so the meta-write gate ran in neither place. Right conclusion, wrong route — and if the numbers had come out the other way I would have shipped the wrong verdict. |
| `BDR-18` | **I fixed the instance and wrote the class into a deferral as the wrong shape.** Removing `?? '1'` was right and closes the live hole. But the row I wrote next said the remaining work is *"a gateway/BFF route or an internal endpoint"* — a way for the TRANSPORT to ask who it is carrying. The PO answered in one line: *it goes through the kernel, that is the architecture.* Measuring it took thirty seconds and shows the correction is not a preference: the proposal carries `actor` and admission verifies the producer signature but never the subject, so the caller supplies a field that IS a verdict — **`CMD-10`'s V4, which I had applied to authored verbs the same week and did not think to point at the wire.** `PID-D5`'s comment makes the identical argument about `event_category` **directly under the `actor` field** and I read past it twice. The tell I keep missing: when a fix is *"stop trusting X"*, ask whether X should have been sent at all. |
| `BDR-17` | **I wrote a measurement into a migration header without running it.** `035`'s safety argument said *"`player_character_index` has no INSERT anywhere in the tree — measured, not assumed"* and printed a grep that *"returns no match"*. The grep returns **two matches**: both test fixtures, in the very package whose reader I was moving. The CONCLUSION survives (no production writer, so the table is empty in every deployment) but the sentence I shipped as evidence was false, and it was false in the form *"measured, not assumed"* — the phrase this project uses to mean the opposite. Caught by running it before staging, one file after `BDR-9` recorded the same shape. **A claim labelled "measured" is the one that most needs the command run, because the label is what stops the next reader checking.** |
| `BDR-16` | **I answered a general objection with a defence, conceded one instance, and would have shipped the fix for that instance only.** `BDR-15` is accurate about the memory arithmetic and accurate that my argument for `16` was borrowed from the wrong neighbour — and it framed the remedy as **raise the number**. That fixes ONE constant. The PO's reframing (`LIM-1`) is that the number was the wrong **kind of thing**: an engine has no business deciding how big somebody else's world is, and *"exceeds this engine's capacity of 32"* is that sentence said out loud, in production, for two features. **Twenty-one other constants would have kept saying it.** The tell I should have read: my own §4b table led with *"two thirds of that is already answered by `QTY-A6`"* — a defence written before the class was measured. `QTY-A6` answers *can the SIZE vary per reality* (yes). The PO asked *who DECIDES it*, which no axiom in the tier addressed. **A correct rebuttal to the question I heard is not an answer to the question asked.** |
| `BDR-15` | **I applied a per-ACTOR memory discipline to a per-REALITY table.** `MAX_DECLARED_VERBS = 16` is a literal I chose, and the argument I wrote for it explains why the table is cheap rather than why the number is sixteen. `[i32; 32]` on `Actor` costs 128 B **per resident actor** — that is what forces 32. `[VerbDecl; 16]` on `Ruleset` costs 1088 B **once per reality**, so 64 would cost ~3.2 KB resident and **zero encoded**. Sixteen actions is small for a game. The PO found it by objecting to hardcoded ceilings in general; the general objection is answered by `QTY-A6` (`n` hashed, `N` in the binary, widening moves no digest) — **and it landed anyway, on the one ceiling where my reasoning was borrowed from the wrong neighbour.** |
| `BDR-14` | **The register repeated the error the register exists to catch.** §4 said widening the quantity table *"silently widens the plugin ceiling, and nothing would notice"* — and a `const` assertion sits directly below the alias whose own comment records it **measured failing at 16 and at 64**. The PO asked one question (*"is `MAX_PLUGINS` hardcoded?"*) and measuring the answer exposed it. **I claimed a guard was absent without reading the twenty lines under the constant I was auditing** — in a document whose entire subject is counting things nobody had counted. The finding survives, smaller and of a different kind: it is a COUPLING (a chosen number blocked by a forced one), not a safety hole. |
| `BDR-13` | **I recommended keeping `player_character_index` after repeating the handoff's phrase *"half right"* WITHOUT auditing the columns.** The PO asked what the reason to keep it actually was, and there was not one: the table has no writer anywhere, so it is empty by construction; the GDPR argument I leaned on is a one-line query edit; the status enum is 5/6 wrong including two members that are PRESENCE, a second SSOT against the live transport; and `0017` had already set the precedent by DROPPING the sibling pc/npc artifacts. **Fourth time this session I reasoned over a summary instead of the artifact** — and the first time the PO caught it rather than a gate or a reviewer. |
| `BDR-12` | **I shipped an ordinal with no width, in the week I spent auditing widths.** `M2`'s `cue: u16` has no named constant, no repin log and no argument, while `MAX_DECLARED_VERBS` — twelve lines away, written the same hour — carries all three and an essay about why it is not an alias. Nothing caught it: no gate counts ordinal spaces, which is precisely what `AF-8` reported about `RefKindMask` and what nobody acted on. **The register exists because the register did not exist**, and its first run found my own omission alongside the two it was looking for. |
| `BDR-11` | **I proposed opening a second effect door as the substrate's next task, and the PO refused it as a boundary violation.** `Delta`'s door was built by the ACTOR HUB — feature #1 — not by the substrate; `StatusPropose`'s belongs to a status feature that does not exist. The substrate never opens a door, it gains a primitive when a feature opens one. **This is `SCOPE-2` a second time in a different costume**: the chooser got designed inside the substrate because the substrate was the thing being written, and the same gravity pulled the doors in. §5's own wording carried it (*"build doors, or narrow the primitive set"*), so the plan had been saying it for two days and I read past it. ⇒ `M2.3` waits on **feature #3**, not on more substrate work. |
| `BDR-9` | **Six of the ten findings were bugs I had already written a CORRECT SENTENCE about.** `EffectRow::amount` said *"the engine clamps against the pool's own declared bounds"* while the code did `.max(0)`. `substrate.rs` said *"every path commits a FACT"* above three `return Vec::new()`. `actor.rs` said *"adding a field moves this number"* under a `<=`. `binding.rs`'s refusal cited an incident it did not cover. **The prose was not wrong — it was written first and never checked against the code beneath it**, which is the same defect as a stale register, one level down. A doc comment is a claim, and this run has now recorded that lesson at three scales: a register, a heading, and a doc comment. |
| `BDR-10` | **I nearly did not run `V.1` at all.** Every suite was green, both milestones were committed, the goal's other clauses were pasted, and the reviewer felt like ceremony on top of work already finished. It found six real bugs — including one that let content grant **unlimited free actions** — in code that had passed 2254 tests, 21 gate self-tests, a live smoke and an independent oracle. **Everything else I built measures whether the code does what I designed. Only this measured whether the design was right.** |
| `BDR-7` | **I wrote `M2.3` into the board as *"replace a `law.rs` arm"* and only measured whether that was possible when I came to do it.** It was not: no shipped arm is a pure `Delta`, and §3 had already priced the door count at one of seven — I had the number and did not apply it to the sentence beside it. The plan was internally inconsistent for two days. What saved it was refusing to open a second door to make a checkbox tick, which is the closure rule working; but the near-miss was *"just make `defend` a declared verb"*, which would have shipped `StatusPropose` as a `Delta` in disguise. |
| `BDR-8` | **The first authored verb refused itself, and I nearly patched the symptom.** `gather` declared a spend of the same pool the engine spends generically, so its own requirement failed on its first submission. The reachable-in-one-edit fix was to move the engine's generic spend after the verb's — which would have let a declared verb take an action for free. The right fix was a BOOT refusal saying the author may not re-declare the engine's turn cost, and it took longer. **A test failure whose quickest fix changes an invariant is the shape to slow down on.** |
| `BDR-4` | **I nearly shipped `M1` with the actor's numbers named `hp`, `av` and `turn_slots` in content** — the names were sitting in the field list I had just inventoried, and copying them would have read as faithful. The PO's correction (`BDR-3`) was about the *engine*, and I first satisfied it by moving the same words one file over. What stopped it was writing `M1.5`'s gate BEFORE choosing the names: a gate that greps for the declared vocabulary in engine source is trivially green when the vocabulary IS the engine's own words. **Different names are not decoration — they are what makes a surviving name-coincidence detectable.** |
| `BDR-5` | I wrote *"`scripts/engine-vocabulary-gate.py` is what keeps it one"* into `binding.rs`'s module doc **while the file did not exist.** It was true within the hour, which is exactly why it is the dangerous kind of claim: a citation to a mechanism that is *about to* exist is indistinguishable, to every future reader, from one that never will. This project has recorded four stale-register catches in a week and this would have been the fifth, authored deliberately. |
| `BDR-6` | **The bite harness caught a hole in my own gate's self-test.** Every one of my twelve cases reached `_exempt` through the comment-block branch; nothing reached the same-line branch, so `if PRAGMA in raw[line_no - 1]` could have been deleted with the suite green. I had written the header sentence *"a gate with no cry-wolf case is half-tested"* and then shipped a half-tested branch under it. **The mechanism found what the intent did not** — which is the standard's own thesis, demonstrated on its author. |
| `BDR-2` | `FATAL-2`'s door count was written when the actor round declared *"No code this round"*, and `actor-hub` has shipped since. I nearly carried the old *"seven of eight are design only"* forward unchanged. Re-measured: it improved by **exactly one door**, and that one is `Delta`. Carrying it forward would have been the fourth stale-register claim this week. |
