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

### Debt
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
