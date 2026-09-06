# The story seed layer — story without a forced outcome

**Status:** DESIGN, awaiting PO review · **Date:** 2026-08-02 · **Base:** `50bff49a4`
**Run state:** [`docs/plans/2026-08-02-story-seed-RUN-STATE.md`](../plans/2026-08-02-story-seed-RUN-STATE.md) — `SEED-D1..D18` are sealed there with attribution; this document does not re-open them.
**Inherits:** [`2026-08-02-actor-data-structure.md`](2026-08-02-actor-hub/analysis/2026-08-02-actor-data-structure.md) + [`2026-08-02-actor-dataflow.md`](2026-08-02-actor-hub/analysis/2026-08-02-actor-dataflow.md), whose `D-1..D-121` bind here unchanged.

> **The problem, in the PO's words:** *roleplay with no story and no scenario is not playable; the problem
> is how to have story without forcing the outcome, because a world simulator does not know what happens
> next. What we need is a **seed**, not an outcome — an origin seed, and a seed that pushes the plot
> onward. So how do we design it without it being so strict that it never fires?*

**Scope:** the seed, the selector that ranks what wants to happen, and the detector that makes an
unreachable seed visible. Commitment/quest-tracking is **out** (`SEED-D6`). Knowledge/who-knows-what is
**out** (`SEED-D7`). Dialogue content generation is **out** — `NPC_001`/`NPC_002`/`AIT_001` own it.

---

## 1. First, what this design stands on — and it is thinner than the corpus reads

`RUN-STATE` invariant 6 (`DR-18`: *before citing any type as shipped, grep it and require a non-zero,
non-docs hit*) was applied to every type this document would otherwise have leaned on. **It fired on its
first use, three times.**

| cited as | `crates/` + `services/` | verdict |
|---|---|---|
| `threshold_sets` / `ThresholdSet` | **0** | designed in dataflow §2.6.2, unbuilt — already recorded by `D-84` |
| `statuses` table / `lifecycle_machines` | **0** / **0** | designed in dataflow §2.6.3–4, unbuilt — `D-84` |
| `ModifierRow` | **0** | already caught as `D-111`; what ships is `StatModifier` (10 hits), keyed on `StatSlot` |
| `granted` | **1**, and it is a **doc comment** at `commit-service/src/domain/state.rs:43` — a directory `D-35` forbids citing | confirms `D-85`; **prose in a source file is not a mechanism** |
| 🔴 **`ActorKind`** | **0 across every `.rs`, `.go`, `.ts`, `.yaml`, `.sql` in `crates/`, `services/`, `contracts/`** — 23 doc files | **NEW.** No `Locus` variant, no `Synthetic` variant; the only `Locus`/`Synthetic` hits in code are those English words inside test comments. The nearest real type is `ActorType` (`meta-rs/src/metawrite.rs:77`), an audit actor, not the game's. |
| 🔴 **`TierCapacityCaps`** | **0 in code, 0 in `contracts/capacity/`** — 15 doc files | **NEW.** `contracts/capacity/budgets.yaml` is per-**service** capacity, an unrelated concern. |

**Why the last two matter, stated precisely rather than dramatically.**

- `D-93` closed `O-118` with *"a World **is** a locus-actor, so a world-scoped quantity is an ordinary
  actor quantity."* The design argument is sound and rests on `SPG-A1`. But **`ActorKind::Locus` is a
  drawing**, exactly like `granted` and `ModifierRow` before it — and this document was about to put the
  entire narrative-pressure model on top of it. It still does, because there is nothing better and the
  round is design-only; it now says so.
- `D-94` closed `O-60` with *"AoS was measured at 11× at 65 536 residents; the hard stateful population
  cap is **120 per reality** (`TierCapacityCaps`)"*. The 11× was measured. **The 120 was not** — it is a
  design intention with no code and no contract, so nothing prevents it drifting, and if it drifts
  `O-60` reopens **silently**. The conclusion is not shown to be wrong; it is shown to be **unverified**,
  in a row that reads as measured.

**And the honest statement about this round's own footing.** The dependency chain is
`threshold_sets (0 LOC) → statuses (0 LOC) → lifecycle_machines (0 LOC) → the seed layer` — **and §4.1b
adds a fifth link below all of them**, because the peer session's `E-4` measures that *none of the four
commit primitives in the event taxonomy's own table exists* either. This layer is
**fourth in a chain where nothing is built.** That is consistent with `D-67` (depth-first, actor core
last) and it is the correct place for a design-only round — but no sentence in this document should be
read as *"this plugs into something that exists."*

---

## 2. Prior art, measured

Nine systems. Full sources at §11.

| system | how content is selected | how it avoids never-firing | how roles are bound |
|---|---|---|---|
| **CK3** | **MTTH — mean time to happen.** Non-`triggered_only` events carry a mean time; modifiers apply a *factor* to it (`factor 0.5` ⇒ twice as likely). `triggered_only` events use `weight_multiplier` on `on_action` hooks. | **Intrinsic** — an MTTH event cannot never-fire; it can only be slow | runtime scope/target |
| **RimWorld** | weighted lottery; weights move with colony wealth, population, recent casualties | **"how long since the last major event"** — a monotone-rising term | pawn chosen when the incident fires |
| **L4D Director** | per-survivor *Intensity*, cycling **Build Up → Peak → Relax** | Peak is reached by construction; **Relax is written into the machine** | — |
| **Salience-based** (L4D dialogue, Firewatch) | **most specific match wins** | *"broad defaults first, more salient content later — **you are never committed to uniform coverage**"* | tags over world state |
| **Waypoint** (Glass) | pathfinding between conversation topics | the engine *"constantly tries to **heal** the story"*; used paths are **negatively weighted** so it cannot stall; a deprioritised fallback line exists | — |
| **QBN** (Fallen London) | thresholds on qualities | ❌ **none** — fails at scale; the *time-to-bootstrap* cost is severe | — |
| **Wildermyth** | authored spine, procedural content slotted in | mandatory roles carry score thresholds; **no valid cast ⇒ the story does not fire** | ⭐ **targets** — see below |
| **Starfreighter** | storylets binding concrete resources | high reuse ⇒ few seeds still play | ⭐ binds the entity **into the narration** |
| **Drama Llama** (2025) | LLM evaluates natural-language conditions; **first match** in author order | ❌ none; authors report heavy cost on *"trigger consistency"* | — |

### 2.1 Four convergences — what we must have

1. **Nobody ships boolean-only gating for ambient story** (`SEED-D8`). Four independent architectures, none
   of them boolean. The systems that *do* gate hard are hand-authored beat systems — the ones with the
   disease.
2. **Everyone carries a monotone-rising term** (`SEED-D9`). RimWorld's time-since-last · MTTH itself ·
   Glass's negative weighting · and **Tale of Immortal putting it inside the condition**: 大能传功奇遇
   (*"great-power technique transmission"* encounter) fires *within 5 years of **not** having reached
   Crystal Formation — i.e. **because the player is behind.***
3. **Everyone binds roles late** (`SEED-D10`). Wildermyth declares **targets** — `Party`, `HERO`,
   `overlandTile`, `site`, `foes`, `npcId` — filtered on personality, relationships, hooks, aspects and
   stats, with a `notAlreadyMatchedAs` clause, **matched in declared order because later picks degrade
   into "wishy-washy" fits.**
4. **Tension must fall** (`SEED-D11`). L4D writes **Relax** into the state machine; RimWorld eases off a
   losing player. `D-119` reached this from inside the corpus. ⇒ **the signed arrow (`C-0`) is a
   prerequisite of this layer, not an enrichment.**

### 2.2 Three divergences — where we must choose

| | the field disagrees | our choice, and why |
|---|---|---|
| rank vs first-match | Drama Llama first-matches by author order; salience ranks | **Rank** (`SEED-D14`). Not because it is better content — because first-match **produces no number**, and §7's detector would have no subject. |
| LLM vs symbolic conditions | Drama Llama proves NL conditions are authorable and pleasant | **Symbolic in the state path, LLM in the narration path** (`SEED-D13`). An LLM YES/NO is non-deterministic and `D-36` requires every state change to fold from the log. Take the authoring lesson, refuse the mechanism. |
| specificity vs authored weight | salience counts specificity; CK3/RimWorld tune weights | **Specificity first, weight only as tie-break** (`SEED-D15`). Specificity is *counted*, not tuned, which is the answer to this design's own "soup of magic numbers" risk. |

### 2.3 The one gap nobody fills

Searched specifically for tooling that detects content which can never become eligible:

- Emily Short's practical storylet guidance — **no tooling guidance at all**
- Kreminski's storylet survey — covers authoring burden, **not** unreachability
- Drama Llama — **acknowledges it as an unaddressed limitation**, proposing cooldowns and ordering
  constraints as future work

⇒ **§7 is genuinely new work** (`SEED-D17`). It is also the part that makes this design satisfy `NV-1..6`
rather than merely intend to, so it is not optional.

---

## 3. The model

> **`SEED-D5`. A seed applies PRESSURE; it does not pull a TRIGGER.** A trigger waits for a condition and
> may wait forever. A pressure **bends the world toward** the condition and can only be slow.
>
> This is `SEED-D2` (*seed, not outcome*) restated mechanically. **The PO's product requirement and the
> anti-starvation mechanism are the same design**, which is why solving one solved the other.

An outcome is what a trigger produces. A tendency is what a pressure produces. The PO asked for tendencies.

### 3.1 The two seed kinds are not equally hard

| | what it is | when it fires | is "never fires" possible? |
|---|---|---|---|
| **Origin seed** | the world's starting condition — initial state plus the initial pressure set | **t = 0, trivially** | **no.** The problem does not exist here. |
| **Propelling seed** | a pressure that ripens later and re-opens the story | when it ripens | **yes — and this is the entire difficulty.** |

The reservation document already sketched the origin seed under another name
([`00_V2_RESERVATION.md`](../03_planning/LLM_MMO_RPG/features/13_quests/00_V2_RESERVATION.md) §5 Path B:
`RealityScenario { premise, starting_beats }`).

**The origin seed is easy to fire and easy to under-specify, so it gets its own paragraph rather than a
dismissal** — the PO's sentence was *"roleplay with no story **and no scenario** is not playable"*, and the
scenario is this half. It is **two things with different homes**, and conflating them is how a premise ends
up in the same table as a pressure:

| part | what it is | where it lives |
|---|---|---|
| **the situation** | the initial pressure set + the initial cast + the world's opening state | **`StorySeed { kind: Origin }`** — §4's row, unchanged. Fires at t=0. |
| **the premise** | *"Town X is under bandit threat; the PC arrives on day 1"* — prose the narrator needs | **narration content, never mechanism.** It is `I18nBundle` text that enters the LLM's prompt context and **touches no state**, exactly like §6's top-K list. |

**The premise must not be able to change state**, or `SEED-D13` is violated at the very first tick and the
world's opening is unreplayable. An origin seed that wants a mechanical opening declares **pressures**; the
premise only describes them.

Everything below is about the second kind.

### 3.2 Tale of Immortal answers the "when is it re-issued" question

⚠️ **Confidence MEDIUM** — the wiki's Destiny page returned HTTP 402 and the Steam patch note yielded no
body; this rests on search summaries and encounter guides. Recorded as `B-2`; re-measure before any of it
becomes load-bearing rather than corroborating.

| Tale of Immortal | our name |
|---|---|
| **Nature Destiny** — 3, chosen at character creation | origin seed |
| **Rewrite Destiny** — 1-of-6 (1-of-9 on Chaos) **at every major-realm breakthrough** | propelling seed |
| **Nurture Destiny** — from quests and events | short-lived pressure |

Three lessons, and the first is the useful one:

1. **The propelling seed is re-issued at a PROGRESSION THRESHOLD, not at a story checkpoint.** Narrative
   pacing rides on character progression — which this project already has as `threshold → status`
   (`D-83`). **No separate story scheduler is needed, and none should be built.**
2. **A Destiny is a bundle of modifiers, not a plot.** It changes what is *likely*, never what *happens*.
   `SEED-D2` shipped in a real game.
3. **NPCs carry Rewrite Destinies too.** Under `D-93` (a World is a locus-actor — §1's caveat applies)
   seeding the world and seeding an NPC are **one mechanism on different subjects**.

### 3.3 The four causes of "never fires", and what kills each

| # | cause | what kills it | cost |
|---|---|---|---|
| **A** | **A conjunction of independent rare facts.** *"X is angry AND it is night AND the player is in village Y AND holds item Z"* → P → 0. Every authored AND is a multiplication. | **`D-29`, unchanged.** A condition is *one* declared threshold — **the author cannot write an AND.** Wanting "angry and night" means **declaring a threshold that means it**, and `D-29` already argues this is the right pressure: *a condition worth attaching is worth naming.* | **zero** — already sealed |
| **B** | **The condition names an INSTANCE.** *"Bandit chief Groknar is alive"* — Groknar died in turn 3, the arc is dead forever. **The single worst failure mode in an emergent world.** | **Casting** (`SEED-D10`). A seed declares **roles**; the engine casts at ripen time. Groknar dies, someone else is cast, the arc survives. | new: the role table |
| **C** | **Nothing pushes the world toward the condition.** The seed waits passively on a world it cannot influence. | **Pressure** (`SEED-D5`) — the seed writes modifier rows that bend a quantity toward the threshold. | new: the pressure channel |
| **D** | **Fires once, never re-arms.** | **Hysteresis, already declared** — actor spec §6: *enter and exit conditions are distinct declared values; events inside a declared window coalesce.* | **zero** — already sealed |

**A and C are two faces of one coin, and that is the load-bearing observation of this document:** you
cannot *move toward* a conjunction — there is no partial credit on an AND — but you can move toward a
number. That is the entire reason for replacing the predicate with a pressure, and it is why `D-29`'s
anti-scripting-language rule, made for a completely different reason, turns out to be the anti-strictness
mechanism too.

---

## 4. The seed, field by field

Every field is tested against `D-27` (*a contribution is DATA, never CODE — the engine folds rows and
never learns a word from the fiction*) and `D-30` (*adding a feature touches zero files in actor core*).

```
StorySeed {
  id
  kind:        Origin | Propelling
  pressure:    [ModifierRow]           // (subject, target ordinal, op, magnitude, layer,
                                       //  condition, source, expiry) — D-27's row, unchanged
  ripens_at:   ThresholdOrdinal        // exactly ONE. Not a list. Not an expression. (D-29)
  roles:       [RoleReq]               // declared order = casting order (SEED-D10)
  on_ripe:     [StatusOrdinal]         // a STATUS. Never an outcome. (SEED-D16)
  hysteresis:  ThresholdOrdinal        // the exit value; distinct from ripens_at (§6, cause D)
  weight:      i32                     // tie-break ONLY (SEED-D15)
  expiry:      Option<TickDelta>
}

RoleReq {
  slot:        RoleOrdinal
  subject:     ActorKindOrdinal        // ⚠️ §1 — ActorKind has zero code
  requires:    Option<StatusOrdinal>   // declared status, not a predicate
  threshold:   Option<ThresholdOrdinal>// declared threshold, not a predicate
  mandatory:   bool                    // no valid cast + mandatory ⇒ does not ripen (Wildermyth)
}
```

**Field-by-field verdict:**

| field | does the engine learn a fiction word? | verdict |
|---|---|---|
| `pressure` | no — it is `ModifierRow`, whose shape the engine already validates and folds | ✅ reuse |
| `ripens_at` | no — one ordinal, one bit test in `threshold_active` | ✅ reuse (`D-29`) |
| `roles` | no — ordinals and declared statuses only; **no free strings, no expressions** | ⚠️ new table, closed shape |
| `on_ripe` | no — status ordinals; `D-83`'s `TransitionDecl.trigger = OnStatus` carries it onward | ✅ reuse |
| `hysteresis` | no | ✅ reuse (§6) |
| `weight` | no — `i32` at `D-52`'s `1e-4` scale | ✅ |

> **`SEED-D16` is what makes `SEED-D2` mechanical instead of a promise.** A seed may say *"succession
> instability is now high."* It may **not** say *"the king dies."* The world decides that, through the
> author-declared lifecycle machine. **The seed layer is structurally incapable of writing an outcome**,
> because its only out-edge is a status ordinal.

### 4.1b What a ripening seed EMITS — and it collides with a live event-model rule

⚠️ **Found 2026-08-02 22:0x, in a peer session's uncommitted working tree.** `07_event_model/` is under
active audit by another session; its findings are cited here **read-only** and nothing in that folder was
edited by this round.

A ripening seed is mechanically an **`EVT-T5 Generated`** — that is exactly what `Scheduled:QuestTrigger`
was reserved as, and `EVT-T5`'s definition is *"rule/aggregator/scheduler emits based on condition +
probability."* But `EVT-A6` + `EVT-L14` make **causal-refs REQUIRED on `EVT-T5`, capped at 64 per event.**

**A pressure-driven ripening has no small enumerable set of parent events.** It is an *integral*: the world
drifted across a threshold over N ticks under contributions from an unbounded number of modifier rows.
Three ways to satisfy a required causal-ref list, and two of them are bad:

| | |
|---|---|
| ref every contributing row | blows the 64 cap immediately, and pays per-event forever |
| ref only the threshold crossing | fits, always available, cheap — but says *"it ripened because the number crossed"*, which is **true and uninformative** |
| **say the cause is not a per-event fact** | ✅ — and `D-46` already made exactly this argument for the neighbouring problem: *"stamping a 32-byte digest on every event pays forever for a question the registry answers once."* |

> **`SEED-D19`. A ripening event refs the THRESHOLD CROSSING; the *why* is recovered from the pressure's
> PROVENANCE, not from an enumeration.** `ModifierRow` already carries `source`, and `D-28` requires a
> modifier row to be written and removed **in the same commit as the feature row that justifies it** — so
> *"why is this pressure here"* is answered structurally and does not need re-stamping on every event.
> **Causation by provenance, not causation by enumeration.**

**This is the round's contribution back to a question the event-model session has open.** Its `E-18` note
records `EVT-A6`/`EVT-L14` as *"contested rather than refuted"* and says plainly: **"the cost side was
never weighed here. Weigh it before re-locking."** The seed layer is the weight — **the first designed
consumer of `EVT-T5` whose causation is an accumulation rather than an event.** Going second is a load
test for the tier beneath, exactly as `D-66` recorded for going first.

⚠️ **Two honesty notes.** `ModifierRow` has **0 occurrences** (`D-111`), so `SEED-D19`'s mechanism rests on
a drawing like everything else in §1. And the emission path itself does not exist: the peer's `E-4`
records that **none of the four commit primitives in the taxonomy's own table exists** across `crates/` +
`services/`, which makes §1's dependency chain **deeper than §1 states**.

### 4.1 This is also the guardrail against salience's one documented disease

Emily Short records that *The King of Chicago* could **accidentally satisfy the preconditions for endings
nobody intended**, and notes it is unclear the game did anything about it. A salience system left to
itself will produce outcomes no author wrote.

For us half of that is *desirable* — it is emergence. What must not happen is an **accidental
irreversible** outcome. The defence is already built into the inherited design and costs nothing here: a
seed reaches only a **status**; only an **author-declared transition** with an author-declared cascade
policy (`D-12`) can move existence; and `Irreversible` is a declared tier the author opts into. **The
lifecycle machine is the brake.**

---

## 5. Where the pressure lives — and `Q2` has a real answer, not a flag

`QTY-A6` caps a reality at **32 quantities total**, one ordinal space, shared with hp/mana/qi/everything.
Six narrative pressures would be 19 % of the entire budget. The obvious reading — *narrative pressure is a
world quantity, therefore it eats the 32* — is wrong, and `D-25`/`D-27` already contain the split:

| pressure kind | who reads it | where it lives | budget cost |
|---|---|---|---|
| **fiction-visible** — 天道 pressure making tribulations harsher, i.e. **a law reads it** | a law | **a declared quantity, inside the 32** | 1 ordinal |
| **selector-only** — narrative tension, time-since-last-beat, arc heat | only §6's selector | **a table owned by the seed feature, keyed by subject** — actor core never reads it (`D-27` channel: *own a table*) | **zero** |

> **The rule, author-facing and testable: a pressure enters the 32 only when a LAW must read it.**
> Everything the selector alone consumes stays in the feature's own table, and is therefore free.

This keeps `D-30`'s acceptance test true (zero files in actor core) and preserves the *principle* behind
`D-26`'s anti-accretion gate. ⚠️ **It does not satisfy the gate, because the gate does not exist:**
`grep -rn ActorQuantities crates/ services/` returns **0**, which is `D-55`/`T0-2` and is the same class as
§1's findings. Saying *"`size_of::<ActorQuantities>()` never moves"* would be citing a mechanism with no
subject — **inside the document whose §1 is about doing exactly that.** The correct statement is: this
design gives that gate nothing new to catch **once someone writes it**.

⚠️ It also does **not** dissolve `O-97`: a reality
that genuinely wants six *fiction-visible* pressures still spends six ordinals, and **this is a new,
independent arrival at the engine-width question** which `D-80` says has no home in `D-2`'s two-way split.

---

## 6. The selector

Every tick, for every seed, compute salience. Rank. Take top-K under a declared budget.

| term | source | why |
|---|---|---|
| **specificity** | count of declared conditions the world currently matches | `SEED-D15` — counted, not tuned |
| **distance to ripeness** | `ripens_at` value minus current value | how close is this to happening |
| **staleness** | ticks since this seed last fired · ticks since **any** seed fired | `SEED-D9` — **the monotone term, mandatory** |
| **cast quality** | how well the best available cast fits the roles | Wildermyth's score threshold |
| **weight** | authored | tie-break only |

**The floor is not silence.** When no seed is ripe, the top-K salience list is the **narrator's prompt
context**, and the LLM improvises over the strongest current pressures **with no state change**
(`SEED-D12`). Over-strictness degrades to **flavour**, never to *nothing happened*.

**Three storytellers, one content set.** RimWorld ships Cassandra/Phoebe/Randy over identical incidents —
the *selector* is swappable, the *content* is not. Our selector's term weights should be a declared,
swappable profile for the same reason. This is vocabulary by `D-98`'s test: the engine's arithmetic does
not differ per profile.

---

## 7. Making an unreachable seed VISIBLE — the part with no prior art

`SEED-D4`: the acceptance criterion is not expressiveness. It is that **a seed which can never ripen is
detectable**. Per `non-vacuity.md`, a design that merely *intends* not to over-constrain has no defence.

Ranking (`SEED-D14`) is what makes this possible: **salience is computable for every seed on every tick,
including seeds that are nowhere near ripening.** Boolean gating produces no such number, which is why
first-match was rejected.

| the observable | what it catches |
|---|---|
| max salience ever reached, per seed | a seed that has **never** entered the top-K in N ticks — the over-constrained author |
| distance-to-ripeness, per seed, over time | a seed whose distance **never decreases** — no pressure points at it (cause **C**) |
| cast-fill failures, per role | a role no living actor can ever fill (cause **B**, surviving casting) |
| top-K empty for N ticks, per reality | **the world has gone quiet** — the system-level alarm |

**Two obligations this places on the build, stated now so they are not discovered later:**

1. **The detector must have a subject before it is written.** Building it against zero seeds is exactly
   the `NV-2` vacuity that `S1b` already demonstrated in this repo. **Trigger: the first authored seed.**
2. **It must be bite-tested** — author a deliberately over-constrained seed, watch the detector report it,
   remove it, and paste the output. `D-62`'s `T0-2` is the standing lesson: *a number four design rounds
   and four red-team agents reasoned from, that nobody measured.*

---

## 8. `Q1`–`Q6`, answered

| # | answer |
|---|---|
| **Q1** | §4. Six fields; four reuse shapes the inherited design already validates and folds; one new closed table (`roles`); no free strings and no expressions anywhere. |
| **Q2** | §5 — and it is a real split, not a deferral. A pressure enters the 32 **only when a law must read it**; selector-only pressure is a feature-owned table and costs zero ordinals. Residue: `O-97` gains an independent arrival. |
| **Q3** | **Parked, correctly** — it no longer blocks. The seed model is identical under either answer; the question decides only whether *knowledge* is a real system, and belongs to that round. |
| **Q4** | `on_ripe` is a list of **status ordinals and nothing else** (`SEED-D16`). That *is* the closed output vocabulary, and it is one variant wide. Wildermyth needed an enumerated output set because it writes gear/stats/map directly. ⚠️ **Corrected during self-review — the first draft claimed `D-83`'s chain "turns a status into every downstream consequence", and that overclaims.** The cascade-policy set is `Drop \| Cascade \| Suspend \| Keep` ([`EF_001:416`](../03_planning/LLM_MMO_RPG/features/00_entity/EF_001_entity_foundation.md)) and those move **held entities when a holder transitions** — they do not grant an item or a currency. **So a ripened seed cannot hand out a reward, and that is deliberate, not an oversight:** a reward is owed to a *commitment* somebody took on, which `SEED-D6` puts in a different feature. A seed changes the world's condition; it does not pay anyone. See §9 `SEED-A7`. |
| **Q5** | **Yes, §6's hysteresis suffices unchanged** — distinct enter/exit values plus in-window coalescing is exactly a cooldown, and it is already declared. Note this is the mechanism Drama Llama lists as *future work*; we inherit it. |
| **Q6** | **Before it can be BUILT, not before it can be specified.** This document is complete without `C-0`. But `SEED-D11` means a seed layer on unsigned arrows can only ever raise tension, which is `D-119`'s divergent series with no sink — so **`C-0` gates the build**, and this is one more independent arrival at `O-107`. |

---

## 9. Where this design is most likely wrong

Written for the red team, by the author, before they arrive.

| # | attack surface |
|---|---|
| **SEED-A1** | **The whole thing rests on `threshold_sets` + `statuses` + `lifecycle_machines`, which are 0 LOC each** (§1). This is a design on a design on a design. The failure mode is not that it is wrong — it is that **nothing here can be falsified until three unbuilt layers exist**, so every claim in this document is currently unfalsifiable. |
| **SEED-A2** | **`D-29`'s one-threshold rule is asserted to be sufficient for story, and it was designed for modifiers.** A story condition is plausibly far more expressive-hungry than *"below 30 % hp"*. If authors routinely need three thresholds, they will declare a compound threshold per seed, the threshold table will explode, and **cause A returns wearing a declaration.** Nothing here measures that. |
| **SEED-A3** | **Specificity-ranking is untested at our scale.** It self-tunes in dialogue systems with hundreds of one-line barks. It is not shown to work for a handful of long-lived narrative arcs, where the most specific match may be a trivial one. |
| **SEED-A4** | **The detector's thresholds are unspecified.** *"Never entered top-K in N ticks"* — what are K and N? Unanswered, and `D-44` already records that the game tier states no quality targets at all. A detector with an unset threshold is prose. |
| **SEED-A5** | **Casting quality is a scoring function and §6 gives it one line.** Wildermyth paid for the ordering rule the hard way; we have taken the rule and none of the tuning experience behind it. |
| **SEED-A6** | **§5's split assumes the selector never needs a law's output.** If a narrative pressure ever needs to read a derived quantity, the "free" table stops being free and the 32-budget argument changes. |
| **SEED-A7** | **A seed cannot grant a reward, and the boundary holding that line is untested.** `Q4` routes rewards to commitment, which is a feature nobody has designed. If it turns out an author's *"the harvest festival succeeds and the village prospers"* wants a resource grant with no commitment in sight, the status-only out-edge is too narrow and `SEED-D16` has to widen — which is precisely the moment the seed layer starts growing an output vocabulary and becomes Wildermyth's enumerated effect list after all. |

---

## 10. What this deliberately does NOT do

| | why |
|---|---|
| **No quest tracking, no quest log** | `SEED-D1`/`SEED-D6` — a different feature at a different tier. The log is a **projection over commitments** (`D-39`), not a mechanism. |
| **No knowledge/rumour propagation** | `SEED-D7` — a different feature. `BubbleUp:RumorBubble` is already reserved for it in EVT-T5. |
| **No story scheduler** | `SEED-D18` — pacing rides on progression thresholds. Building a second clock would be `D-19`'s two-clocks defect repeated. |
| **No namespace registration** | `_boundaries/_LOCK.md` is held by a peer session (RUN-STATE `B-1`), and it is not yet clear this layer is `QST-*` at all. |
| **No code** | `D-72` — *stub code and garbage cost a great deal to de-rot later.* |

---

## 11. Sources

- [Beyond Branching: Quality-Based, Salience-Based, and Waypoint Narrative Structures — Emily Short](https://emshort.blog/2016/04/12/beyond-branching-quality-based-and-salience-based-narrative-structures/)
- [Survey of Storylets-based Design (Kreminski) — Emily Short](https://emshort.blog/2019/01/06/kreminski-on-storylets/)
- [Storylets: You Want Them — Emily Short](https://emshort.blog/2019/11/29/storylets-you-want-them/)
- [Drama Llama: An LLM-Powered Storylets Framework for Authorable Responsiveness in Interactive Narrative (arXiv 2501.09099)](https://arxiv.org/html/2501.09099v1)
- [Wildermyth Wiki — Story Inputs and Outputs](https://wildermyth.com/wiki/Story_Inputs_and_Outputs)
- [Crusader Kings 3 Dev Diary #30 — Event Scripting](https://forum.paradoxplaza.com/forum/developer-diary/crusader-kings-3-dev-diary-30-event-scripting.1397140/)
- [RimWorld Wiki — AI Storytellers](https://rimworldwiki.com/wiki/AI_Storytellers)
- [Left 4 Dead Wiki — The Director](https://left4dead.fandom.com/wiki/The_Director)
- [Tale of Immortal Wiki — Destiny](https://tale-of-immortal.fandom.com/wiki/Destiny) (HTTP 402 at time of writing) · [鬼谷八荒 encounter walkthrough (9game)](https://www.9game.cn/news/5014716.html) · [Tale of Immortal on Steam](https://store.steampowered.com/app/1468810/_Tale_of_Immortal/)
