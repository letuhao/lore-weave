# 27 — Extensibility stress test + live-defect record

> **Status:** INVESTIGATION — 2026-07-28. Written to disk mid-investigation at the PO's instruction
> (*"ghi toàn bộ điều tra vào file để tránh bị trôi"*) because everything below existed only in a
> conversation.
> Findings `XST-F1..F12`, defects `XST-D1..D10`, recommendations `XST-R1..R13`.
> **Raw evidence:** the five agents' full reports are preserved verbatim in
> [`27a_stress_test_agent_reports.md`](27a_stress_test_agent_reports.md). This file is the
> distillate; §11 records what the first distillation dropped and why.
> *(The first draft of this line said "F1..F14, D1..D4" — neither was true when written. Left
> recorded rather than quietly fixed: it is XST-F1, the very rot this document is about, occurring
> inside this document.)*
> **Prefix `XST` registered** in [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
>
> **COMPLETE** — all five agents reported. §9 holds the adversarial critique, which is the most
> consequential section: it ran **probes against the real code** rather than reviewing the summary,
> and found that **four stated invariants are false in the implementation and a fifth is
> unfalsifiable**.
>
> §9 was reconstructed verbatim from the session transcript after a context compaction — the
> original write failed on a shell-quoting error. Nothing was lost.

---

## 1. Why this exists

The PO asked whether the architecture can absorb **new quantities and new mechanics** without
breaking, given that the prior project (`chaos-backend-service`) had to retreat from dynamic typing
to hardcoded arrays after measuring a **125.78 ns vs 1.42 ns (88×)** HashMap-vs-array stat access.

Method: web research across four genre clusters + five independent sub-agents given a compact
architecture brief (so none had to re-read this corpus), each asked to propose new mechanics and
judge SURVIVES / BENDS / BREAKS against a named axiom.

**The investigation found more than it was looking for: four live defects in code committed
2026-07-28 (`9ac178221`, `4c42150dc`), one of which is a spec violation of a defect the spec had
already found and fixed.**

---

## 2. XST-D1 — the worst one: I implemented a documented kill-mutation

**Severity: HIGH. Spec violation, not a design question.**

`DF07_002_edge_cases_and_closure.md` records this as an already-found, already-fixed defect:

> **EC-2 — A percent debuff past −100% inverted the stat (severity: high)**
> **Fix:** `factor = max(0, 1000 + Σpct)`. −100% is the floor; further debuffs are absorbed.

and gives it an acceptance criterion with an explicit kill-mutation:

> **AC-DF7-17** — `Σpct = −1200` on `StrikePower` ⇒ value **0**, never negative.
> **Kill-mutation:** *"Drop the `max(0, …)` on `factor` → yields a negative stat."*

`DF07_001` §7 pseudocode line 257 states it directly:

```
factor = max(0, 1000 + pct_sum)     // EC-2: −100% floors at zero, never inverts
```

**What was implemented** (`services/commit-service/src/stats.rs`):

```rust
let value = flat.saturating_mul(1000 + pct) / 1000;   // no max(0, …)
```

Verified numerically:

| Σpct | Scenario | StrikePower |
|---:|---|---:|
| −500 | one −50% debuff | 50 |
| −900 | two debuffs | 10 |
| **−1200** | **two −60% debuffs** | **−20** |
| −2000 | realm-suppression stack | −100 |

The only guard is `StatSlotDecl.clamp.min`, which is **optional** in the implementation
(`slot_clamps.iter().find(...)` returns `Option`).

**The lesson is the finding.** The spec found this bug on paper, fixed it, wrote the test, and named
the exact mutation that would reintroduce it — and the implementation reintroduced it anyway,
because it was written from the axiom list rather than from the edge-case document. This is the
strongest available evidence for the PO's call to stop implementing and build foundation→SDK first:
**a supply chain that hands the implementer the *resolved* rules would have made this unreachable.**

---

## 3. XST-D2..D4 — three more live defects, all SILENT

All three pass every existing test (76/76 green), and all three are **deterministic**, so replay
agrees with itself and the conformance suite stays green. None is observable.

### XST-D2 — the damage chain silently saturates (HIGH)

`combat.rs` builds `numer = base × ELEM(1000) × (1000−RESIST) × roll_band × crit_mult` with
`saturating_mul`, `denom = 1000⁴`.

| `crit_mult_pm` | base saturates above |
|---|---:|
| 1000 (no crit) | 8 020 323 |
| 1500 (default 1.5×) | 5 346 882 |
| **5000 (a modest ARPG 5×)** | **1 604 064** |

`StrikePower` is `i32` and percent modifiers **sum**, so `strike_power 100 000` with `Σpct = +2000%`
resolves to 2.1M — already past the ceiling. Above it **every hit returns the identical saturated
number**.

The irony is recorded in the code itself: the comment at `combat.rs:226` congratulates fixed-point
for making a scale error *"fail LOUDLY"* — and the line below it uses `saturating_mul`, which makes
overflow fail in total silence. **Same pattern as CNC-F16**: a degrade path absorbs the bug and
reports success.

**Compounding:** every additional per-mille factor divides the ceiling by 1000. Adding an element
factor plus one multiplicative bucket takes the safe base from 1.6M to ~1600. **i128 intermediates
are a prerequisite for any of §7's extensions, not an optimisation.**

### XST-D3 — the damage roll band never reaches its maximum (MED)

`roll_band_pm = 850 + roll_pm × 300 / 1000` where `roll_pm = range_u64(1000)` yields `0..=999`.

* Actual range: **850..=1149**, never 1150.
* Mean: **999.400‰** instead of 1000‰.
* A permanent, systematic **−0.06 %** damage shortfall.

Small, but it is a *bias*, not noise: it never averages out.

### XST-D4 — the implemented action set diverges from the spec's closed set (MED)

`COMB_001` §V1 closed `allowed_tools`: **Strike · Defend · Skill · UseItem · Flee**, and states
explicitly that **movement is not a verb** — a turn grants a movement budget *and* an action
(TG-A3 supersedes the earlier "no Move verb").

Implemented `CombatPayload`: `Strike · Defend · Move{stance} · Flee · EndTurn`.

So: `Skill` and `UseItem` are absent, and `Move` exists as a payload where the spec makes movement a
budget. `Move{stance}` is TG-A4 *stance*, which is a different concept wearing the same name — the
exact category-error shape `ABL-A1` was written about.

---

## 4. XST-F1 — closed sets grow, and the documentation of their closedness rots first

`ABL_001`'s `EffectOp` is described as a **"closed 9-variant dispatch vocabulary"** in at least three
places: the module-coverage audit, `SESSION_HANDOFF`, and — inherited without checking —
[doc 26](26_implementation_architecture.md).

Counting the enum body gives **11** variants (`VitalRestore · StatusApply · StatusDispel ·
ResourceGrant · Reveal · Unlock · Inert · Damage · ModifyThreat · ForceMove · SeverBinding`); a
helper agent counted 10. **The disagreement is the point: nobody knows, and nothing checks.**

`scripts/design-lint.py` already has a `count-assertions` check. It is configured
`INFO, not parsed in v1` — the repo built the detector for exactly this class and left it switched
off.

> **This is empirical data about the central question.** Closed sets are not static in practice.
> What decays first is not the set — it is the claim that the set is closed.

---

## 5. Agent findings — the four genre reports

> These are **summaries**. The verbatim reports are in
> [`27a_stress_test_agent_reports.md`](27a_stress_test_agent_reports.md) — read them before
> concluding a genre raised nothing on a given topic, because this compression dropped four
> load-bearing findings (recovered in §11).

Each agent read its own genre research (disjoint bytes) and was handed the architecture brief, so
none re-read this corpus. Verdicts are theirs; the numeric verifications in §2–3 are mine.

### 5.1 Deckbuilders / roguelikes — *the compositional-effects test*

**Sharpest result — an arithmetic disproof that multiplicity is unprojectable.**

> Multistrike 2 (attacks twice more). StrikePower 10, target Armor 8.
> Truth: 3 × `max(1, 10−8)` = **6**.
> To project into StrikePower: `max(1, sp−8) = 6` ⇒ `sp = 14`.
> **Same unit, Armor 0:** truth = 3 × 10 = **30** ⇒ `sp = 30`.

The required projection weight **depends on the target's Armor**, unknowable at cold projection time,
because step 1 of the chain (`max(1, sp − armor)`) is **non-linear** and hit-count does not
distribute across it.

> The 10 slots have a **magnitude** dimension and no **cardinality** dimension, and cardinality is
> not reachable from magnitude.

Verified independently — the arithmetic holds.

Other breaks: reactive triggers (no dispatch path from a committed event back into resolution);
effects that modify other effects (Balatro Blueprint copies its neighbour — a missing *combinator*,
not a missing leaf); MTG replacement ordering (double-then-halve = 7, halve-then-double = 8, both
legal); numeric range (Balatro exceeds 1e30).

Better than the genre: replay across a patch (Balatro/StS seeds break between versions); Hearthstone
had to *legislate* "order of play" + queue immutability, which fall out of event sourcing for free;
MTG needs CR 613's seven layers + CR 706 to define what a copy copies — a locked layer order makes
"copy at layer N" a declarative cut.

### 5.2 ARPG / MMO itemization — *the stat-count and damage-formula test*

Found **XST-D2** (saturation) and **XST-D3** (roll band) by reading the code.

Breaks: **the damage value is a scalar** — a hit that is 60 % physical / 40 % fire cannot be
represented, and this silently invalidates leech, reflect, thorns and ailment magnitude, all of which
need the typed breakdown. Damage conversion (PoE phys→fire) has no seat in the locked chain, *and*
armour must not apply to the converted portion — the current order applies it to everything.
Ailments scaled off the causing hit are impossible because `StatusApply { magnitude: u8 }` is an
author constant.

Key correction to our own rationale, and it matches the deckbuilder agent independently:

> **DF7-A5's stated reason is half-wrong. Multiplication is commutative, so chaining is *also*
> order-independent.** What summing actually buys is (a) no exponential stacking from content and
> (b) no integer-truncation path-dependence. Those are the real axioms — and bounded multiplicative
> *buckets* preserve both.

Better than the genre: **Diablo 4 shipped the opposite mistake** — fully multiplicative buckets,
damage inflation, and in Season 2 moved Crit/Vulnerable into the *additive* pool; D3 needed a full
number squish. **This design starts at the answer.** Also: integer determinism is the professional
choice, not a handicap — FFXIV ships `⌊200(CRIT−420)/2780+50⌋/1000`.

### 5.3 Immersive sims / colony sims — *the open-ended-modding test*

**The single most load-bearing observation in the whole exercise:**

> `StatSlot` is a Rust enum, so **the slot set is a property of the binary, not of the ruleset.**

Its proposal — carried below as **XST-R6** — follows directly: move `SLOT_COUNT` from a *language* constant to a *ruleset*
constant. `[i32; MAX_SLOTS]` with `MAX_SLOTS = 32` and a live count; hot access becomes a
bounds-checked index at **~1.5–2 ns vs 1.42 ns direct, vs 125.78 ns HashMap**.

> The closedness that buys determinism is **cardinality-bounded + ordinals pinned by digest**, not
> **declared in Rust**.

That is what Skyrim does at record-type level and Factorio does at prototype level.

Breaks: per-limb wounds (RimWorld recomputes `PawnCapacity` **on every hediff change** — i.e. on
every strike, which makes "cold path resolution" false); needs/mood/sanity/stealth have **no slot to
project into at all** — the cleanest proof that the problem is *closed-in-code*, not *closed*;
relationships are edge properties and cannot live in a per-entity dense array, and with one entity
per island the edge has no single writer; temperature/gas/fluid fields fall in the gap between
Class A (20 Hz, not event-sourced), Class B (turn-based) and Class C (minutes) — ONI had to extract
its element sim into a separate native library on its own thread.

**BREAK 1 restated, because it is subtle and applies to us today:** the cold/hot boundary is drawn by
*authoring time*, but the genre needs it drawn by *change frequency*. The dense array is justified by
"resolution is cold" — and the moment wounds, encumbrance or status severity become terms, that
justification is false and nobody has budgeted the re-resolution.

### 5.4 Cultivation / idle / prestige — *the unbounded-growth test*

Found **XST-D1** (sign inversion).

Breaks: **realm suppression is inexpressible** — there is no `(attacker, defender)` relational term
anywhere in the locked chain, and `max(1, …)` guarantees a mortal always does ≥1 damage, so a mortal
army always kills an immortal given rounds. Prestige composition is multiplicative across layers; two
×100 layers give **×199 instead of ×10 000**, and the error widens without bound. And a new *pool*
(qi) has nowhere to go: `MaxHp`/`MaxStamina` are the only pool slots, so a robe's "+20 % max qi"
exits the entire equipment/status/percent/Lex pipeline.

> **"Project into 10 slots" is true for derived quantities and false for pools.** A pool is not a
> projection target — it is a container with a max, a current, a regen and a zero-behaviour.

Better than the genre: offline accrual here is **exact**, where *Antimatter Dimensions* documents its
own catch-up as *"only somewhat accurate"*; idle games compute offline gain client-side from the wall
clock, so the entire genre has a clock-rollback exploit that server-authoritative fiction-time closes.

---

## 6. XST-F2 — the six convergence points

Four agents, four genres, no contact with each other. Where they agree is the signal.

| # | Convergent finding | Raised by |
|---|---|---|
| 1 | **Interned tag/keyword bitsets** as the extension escape hatch | deckbuilder · immersive-sim |
| 2 | **Closed *per ruleset*, not closed *in the binary*** | ~~immersive · cultivation · ARPG~~ ⚠️ **MISATTRIBUTED — see §6.1** |
| 3 | **Percent: products across stages, sums within a stage** | deckbuilder · ARPG · cultivation |
| 4 | **The integers are too narrow** (i128 intermediates / `[i64; N]`) | ARPG · cultivation |
| 5 | **No trigger substrate** — nothing carries a committed event back into resolution | all four |
| 6 | **RNG key lacks a discriminator** (`sub_index` / cascade depth) | deckbuilder · ARPG · cultivation |

Point 6 is concrete and cheap **today**: `role_rng(seed, actor, action_idx, role)` gives every hit of
a multi-hit action the *same* draw — all crit or none. Retrofit cost rises monotonically with every
replay log written.

### 6.1 ⚠️ Convergence #2 is MISATTRIBUTED — correction 2026-07-28 ([QTY-D8](35_quantity_architecture.md))

A cold-start adversarial audit checked each attribution against the raw reports in
[27a](27a_stress_test_agent_reports.md). **Convergence #2 had one source, not three**, and two of the
three named agents recorded the *opposite* position:

| Agent | What it actually wrote |
|---|---|
| **immersive-sim** ✅ | the genuine source — *"move `SLOT_COUNT` from a language constant to a ruleset constant … converts 'closed enum' (a fact about the binary) into 'closed set per ruleset' (a fact about data)"* ([27a:502-511](27a_stress_test_agent_reports.md)) |
| **cultivation** ❌ | *"None of these introduces a map, a float, **or an author-declared slot**"* ([27a:730](27a_stress_test_agent_reports.md)); its S7 keeps a dense closed `[i64;12]` and spends *"the engine-release cost DF7-A1 anticipates … once"* ([27a:740](27a_stress_test_agent_reports.md)); *"What I would not change: **the dense closed array**"* ([27a:747](27a_stress_test_agent_reports.md)) |
| **ARPG** ❌ | grows the **binary's** enum `[i32;10] → [i32;26]`, *"the 88× HashMap argument is untouched"* ([27a:349](27a_stress_test_agent_reports.md)); per-element resist *"survives **only if `ElementId` is engine-closed and small**"* ([27a:274](27a_stress_test_agent_reports.md)) |

The second independent voice for the closed-head/open-tail form is the **fifth (adversarial) agent**,
which was reading *our code* rather than a genre ([27a:980](27a_stress_test_agent_reports.md)) — not
one of the three named. **The honest count is one genre agent plus one code-reading adversary.**

**What survives the correction, and it is the more useful reading:** the cultivation agent objected to
author-declared *stat slots* and in the same breath proposed author-declared *pool identity* —
*"The behaviors stay closed; only the **identity** opens"* ([27a:739](27a_stress_test_agent_reports.md)).
Both positions are right, and [QTY-A3](35_quantity_architecture.md) is where they meet: **the closed
set is the set of ROLES the laws bind to, not the set of quantities.** ARPG's density requirement is
satisfied too, because [QTY-A6](35_quantity_architecture.md) makes the width a *per-reality* constant
— the set really is closed and small, just not in the binary.

---

## 7. XST-R1..R9 — recommendations, ordered by (value ÷ cost)

Every item preserves: dense ordinal-indexed arrays, no hot-path map, no float, closed vocabularies,
deterministic replay.

| Id | Recommendation | Fixes | Cost |
|---|---|---|---|
| **XST-R1** | Restore `factor = max(0, 1000 + Σpct)` and add AC-DF7-17 as a test | XST-D1 | one line |
| **XST-R2** | Widen damage intermediates to **i128**; replace `saturating_mul` with a **declared** `MAX_HIT` cap that is observable | XST-D2 | small; **prerequisite** for R6/R7 |
| **XST-R3** | Fix the roll band to be inclusive of 1150 | XST-D3 | one line |
| **XST-R4** | Add `sub_index` to the RNG coordinate; **reserve** roles `shuffle`/`draw`/`cost`/`trigger_order`/`ailment` now | convergence #6 | small now, expensive later |
| **XST-R5** | Emit a signal when a slot saturates, when Σpct goes negative, or when a clamp fires | XST-D1/D2 and the whole silent class | small; directly the repo's non-vacuity discipline |
| ~~**XST-R6**~~ | ~~`SLOT_COUNT` becomes a **ruleset** constant; `[i64; MAX_SLOTS]`, ordinals pinned by digest~~ **RETIRED 2026-07-28 → [QTY-D4](35_quantity_architecture.md).** Opening the slot set is the wrong fix: the laws read **9 of 10** slots by name, so the "open tail" is one dead slot while every pressure case needs a *head* slot. The pressures are real and are re-homed — pools → [QTY-A4](35_quantity_architecture.md), capacities/mood → L2 declared quantities, law binding → [QTY-A3](35_quantity_architecture.md) roles. **Also: the "medium" cost here was self-authored and contradicted by "cheap now (two accessors, ~11 tests)" at §11.6 — two estimates of two different designs, never reconciled; the real surface is 102 `StatSlot::` references across 6 files** | convergence #2 (⚠️ misattributed — §6.1) | ~~medium~~ **retired** |
| **XST-R7** ✅ | `StatSlotDecl { …, combine: Sum \| Product }` — stage-scoped operator. **ADOPTED 2026-07-28 → [QTY-D11](35_quantity_architecture.md).** Because terms in one slot's pool carry **distinct `kind_id`s**, `Product` is a genuine *cross-quantity* product — which is what `mị ma song tu` (qi × body) and `ngự khí` require. **Three edges it does not solve are now [QTY-Q8](35_quantity_architecture.md):** `combine` is per-decl not per-term (so a mixed polynomial `2×str + qi×body` is inexpressible, and `stat.duplicate_slot_decl` forbids the two-decl workaround); any zero term **annihilates** the slot; and the n-ary milli divisor is unspecified corpus-wide | convergence #3 | one enum field |
| **XST-R8** | Interned tag bitset `[u64; 4]` + one `Precondition::HasTags(mask)` variant | convergence #1 | medium |
| **XST-R9** | Closed `TriggerPoint` + `Reaction { when, guard, then }` with a depth budget | convergence #5 | medium-large |

**Four further recommendations — `XST-R10..R13` — were dropped by the first distillation and are recovered in [§11.5](#115-xst-r10r13--four-recommendations-7-dropped).** R10 in particular is the only proposal that actually answers XST-F7.

**Two disciplines that must ship with R8 or it becomes the property-bag it replaced:**

1. **Tags are membership, never values.** `Flammable` yes; `melting_point = 1811` never.
2. **Ordinals come from the digest, never from load order.** Otherwise this reproduces Skyrim's
   EditorID/FormID collision — but as *silent replay divergence*, which is strictly worse than a
   broken sword.

Independent corroboration for R8: Dwarf Fortress invented the same escape hatch
(`[REACTION_CLASS:whatever]`). Two of the three most-modded games in the genre converged on it.

### 7.1 What to deliberately NOT fix

* **Pairwise material dispatch** (DF-grade: steel maul vs iron plate takes the blunt path; steel
  sword takes shear). It would unlock genuinely deeper combat, but the locked 4-step chain is what
  makes damage auditable, LLM-explainable and replay-stable. Recover ~70 % of the flavour cheaply via
  R8: a bounded 2-D tag table feeding `elem_mult`, not a solver.
* **Relationships / opinions.** Edge-keyed, Class C batch, outside `StatBlock`. Do not make islands
  hold them.
* **True incremental-game numeric range** (`break_infinity.js` territory, 1e9e15). This is a
  cultivation-RPG architecture, not an incremental-game architecture. Say so in the docs.
* **Total conversion at Skyrim/DF level.** What this supports is Factorio-level: retune everything
  *within* the slot set and the locked chain. Promising DF-level moddability and shipping reskins is
  worse than promising reskins.

---

## 8. XST-F3 — what the architecture gets RIGHT

Named because a stress test that only lists breaks is not a stress test. Each of these was raised
independently by at least two agents.

1. **Replay across a patch.** No shipped game in any of the four genres can do it — Balatro and StS
   seeds break between versions. Digest-pinning the ruleset into every event makes a run reproducible
   across arbitrary content churn.
2. **Per-coordinate RNG derivation.** Adding a new random call anywhere never renumbers history.
   Idle games and deckbuilders break replays and leaderboards on nearly every content patch for
   exactly this reason.
3. **Integer determinism is the professional choice.** FFXIV ships floor-based rating formulas; WoW
   ratings are integers; Factorio is in the same class and got there the same way.
4. **Σ-percent is where Diablo 4 *ended up* after shipping the mistake.** Starting there is correct;
   §7's R7 refines it rather than reversing it.
5. **Order-independence makes multi-author content commutative** — RimWorld `StatWorker` ordering and
   Skyrim perk-entry ordering both produce "mod A before mod B gives a different number", which is
   unfixable by construction and spawns endless patch mods.
6. **Proposal → validate → commit** beats direct mutation (Papyrus mutating state directly is the
   source of Skyrim's save bloat and orphaned scripts) *and* is the only thing that makes an LLM
   driver safe.
7. **Single-writer islands** beat DF's global single thread and ONI's need to extract its sim.
8. **A measured, published perf budget.** Nobody in these genres publishes one. It is what will let
   this project say *no* to a bad extension with evidence rather than taste.

---

## 9. Adversarial critique — invariants that are FALSE in code

The fifth agent did not critique the brief; it read the implementation and **ran probes**. Every
claim below about our code was re-verified by me against the source before being recorded here.

### 9.1 XST-D5 — the ruleset digest is decorative (FATAL)

* `EventEnvelope` (`crates/dp-kernel/src/envelope.rs`) has **no `ruleset_digest` field**.
* `RulesetDigest` exists on `Island` and in the checkpoint, is **never stamped into an event and
  never compared to anything** — a repo-wide grep for `digest ==` / `DigestMismatch` returns zero.
* `Island::restore` takes `rules` from the caller and stamps `cp.digest` on them **without
  verifying that those rules hash to that digest**.
* `CombatRules` has two fields: one documented as dead (`strike_damage`), one with a single read
  site (`ko_duration_rounds`).

**Every number that actually decides a fight is a Rust literal**: `500/50/950` in `hit_chance_pm`,
the `850..1150` band, `ELEM_MULT_PM`, `RESIST_PM`, `1200/800/2000/750` in `action_value`, and all
ten stat defaults.

> Edit the variance band from `300` to `250`, ship the binary: every historical event now replays
> differently and **the digest does not move**. The mechanism built to detect exactly this is blind
> to it.

This supersedes [doc 26](26_implementation_architecture.md)'s IMP-D6, which framed the problem as
"the digest is all zeros". It is worse than that: **even a correct digest would cover a struct that
governs almost nothing.** Replay-correctness is therefore currently *vacuous* — there is no test
that can bite on rules drift, because the rules are not in the artifact being hashed.

### 9.2 XST-D6 — the "inescapable" Lex clamp is escapable (HIGH, verified)

```
PROBE: MoveRange under a Lex ceiling of max=2  ->  5
```

`resolve_block` applies slot clamps then Lex clamps *inside* the per-slot loop, then calls
`derive_move_range` **after** the loop, which overwrites `MoveRange` with its own
`clamp(1, tuning.max_move)` — discarding the world rule.

The Lex-clamp-last property is a **recorded correction** (DF07_002 EC-1) with a dedicated test —
and that test covers `StrikePower`. Nothing covers the one slot where the invariant is actually
broken.

My own comment is the tell: *"Speed feeds the derivation, so it must run after the loop."* The
reasoning about `Speed` is correct; it simply did not notice it was destroying a clamp.

### 9.3 XST-D7 — three modifier sources are silently dropped (HIGH, verified)

```
PROBE: Base      Flat(+50) on StrikePower(10) -> 10   (dropped)
PROBE: Archetype Flat(+50) on StrikePower(10) -> 10   (dropped)
PROBE: Lex       Flat(+50) on StrikePower(10) -> 10   (dropped)
PROBE: Equipment Flat(+50) on StrikePower(10) -> 60   (applied)
```

The flat loop iterates only `[Progression, Equipment, Status]`. Three of six `ModifierSource`
variants are constructible, accepted, and discarded. The **percent** filter is *not* source-filtered,
so **`Lex` Percent applies while `Lex` Flat vanishes** — a world rule works or does nothing depending
on which operator the author picked.

This is exactly the **no-silent-no-op** class CLAUDE.md names as a shipped bug. The enum should not
be able to express something the resolver ignores.

### 9.4 XST-F4 — the 88× benchmark does not support the conclusion I drew from it

> ⚠️ **UNVERIFIED — NO COMMITTED HARNESS. Do not quote the table below as measurement**
> (correction 2026-07-28, [QTY-D8](35_quantity_architecture.md)).
>
> The numbers come from an agent's narrative report whose own method note reads *"probe file written,
> run, then **deleted**; working tree is clean"* ([27a:782](27a_stress_test_agent_reports.md)). No
> benchmark file for this comparison exists anywhere in the repo (`criterion` is declared only in
> `world-gen` and `world-service`), `StatId` has **zero** hits in `.rs`, and there is no machine spec,
> iteration count or variance. **In a repo whose stated discipline is the bite-test, this may not
> overturn a locked decision.** Re-running it with a committed harness is `Q0`'s companion task
> ([35 §12](35_quantity_architecture.md)).
>
> **Separately, the framing below is wrong even if the numbers are right.** 88× compares closed-array
> vs **`HashMap`**; 1.08× compares closed-array vs **interned-ordinal array**. Those are different
> competitors, so 1.08× does not refute 88× — and chaos's *committed* criterion output supports 88×
> for the map (8.2 ns / 50 ordinal reads vs 704.9 ns / 50 `HashMap<u64>` reads). **88× was never an
> argument against ordinal-interned openness.** The closed-derived decision is now re-grounded on
> [QTY-A3](35_quantity_architecture.md) (laws bind to named *roles*) rather than on either number.

The agent re-ran the comparison that actually matters:

| | ns/read |
|---|---:|
| closed `[i32; 10]` by enum ordinal (shipped design) | **1.384** |
| **open** `Box<[i32]>` indexed by interned `StatId(u16)` | **1.496** |
| `HashMap<String, i32>` (SipHash) | 11.952 |

Two consequences, and both cut against [doc 26](26_implementation_architecture.md) §1:

1. **The cited 125.78 ns is ~10× slower than even a plain string-keyed HashMap.** It did not measure
   "dynamic stats" — it measured something pathological (nested maps, cloned keys, or lock/Arc
   indirection). The number is real; the *inference* from it is not.
2. **The open design costs 1.08× — 0.11 ns per read**, i.e. **0.05 %** of a 176–229 ns island step.
   Doc 26's claim that a dynamic path would cost "~1 µs, or 5× the whole step budget" assumes the
   hot path performs the lookup.

**And it doesn't — by our own design.** `CombatStats::from_block` projects the block into a flat
struct once; `resolve_attack` reads that struct and never touches the block. **IMP-A3 (resolve
extensibility cold, ahead of the hot path) already eliminated the hot-path lookup.** The closed
enum is therefore a *second* payment for a problem projection had already solved — and the ceiling,
the ownership matrix and the engine-release cost buy 0.11 ns.

This does not overturn the code/config line in doc 26. It overturns **the evidence used to justify
the specific closed-10 decision**, which now needs re-deciding on its real merits (matchability of
named slots in the laws) rather than on a performance argument that does not hold.

### 9.5 XST-F5 — the LOCKED layer order is currently unfalsifiable

```
PROBE: swap flat values across layers -> 10 vs 10   (equal => order unobservable)
```

Flat layers are **summed**, and addition commutes. My comment claims iterating an ordered source
list *"keeps the result independent of the order modifiers happen to arrive in"* — but plain
summation already is. The only orderings that are actually observable today are
**flat-before-percent** and **slot-clamp-before-lex-clamp**.

> The "inviolable layer order" invariant has **no test capable of failing**. The mechanism does not
> merely pass the check — it makes the check unfalsifiable.

That is tolerable until someone adds a genuinely order-sensitive op (a multiplicative modifier, a
`SetTo`), at which point the invariant becomes load-bearing with zero regression coverage behind it.

### 9.6 XST-D8..D10 — three more concrete defects

| Id | Defect | Evidence |
|---|---|---|
| **XST-D8** | **Clamps do not compose.** `slot_clamps.iter().find(...)` takes the **first** clamp for a slot and discards the rest. Two content packs each clamping `MaxHp` ⇒ the winner is decided by `Vec` order, i.e. **load order** — order-dependence reintroduced through the back door of the mechanism advertised as order-independent. | `stats.rs` |
| **XST-D9** | **Handoff fabricates a corpse.** `extract` is `state.actors.remove(&id).unwrap_or_else(\|\| Actor::new(0))` → `hp: 0, max_hp: 0, Side::B`. `type Portable = Actor` **has no empty case**, so the trait's "TOTAL" contract was satisfied by inventing a dead body. Combined with `outcome_of` iterating **all** `state.actors` with **no encounter scoping**, an entity crossing in with no domain row installs a dead Side::B actor ⇒ **`Victory` declared for side A**. | `domain.rs` |
| **XST-D10** | **`CombatState` is single-encounter; `Island` is multi-encounter.** One `session_seed`, one `round_number`, one `outcome` — but `Island` maintains `encounters: BTreeMap<EntityId, Gen>`. The first time two encounters share an island, A's victory condition is evaluated over B's corpses. | `domain.rs` / `island.rs` |

Also flagged: `depart`/`arrive` are two non-atomic calls on two islands with **no durable carrier**
anywhere in the production path. "Exactly one island" is structurally enforced against
**duplication** but not against **loss** — a crash between the two leaves the entity in zero islands.

### 9.7 XST-F6 — the rot prediction, and it is not the file doc 26 guessed

Doc 26 §4 predicted `domain.rs` (539 lines) as the future god-object. The agent argues that is the
wrong guess — dispatch files grow linearly and split cleanly.

> The god-object will be **`combat.rs::resolve_attack`**, because every mechanic the slot system
> cannot express gets solved the same way: a special case threaded into the law.

**The pattern is already in the file, twice, before any content ships:**

* `defending: bool` is a **parameter** of `resolve_attack` with `if defending { 2 }` in the
  denominator — explicitly documented as *"not a stat modifier (DF7-A8)"*.
* `AvStatus { slowed, hasted, stunned }` is a **second, parallel, ad-hoc modifier system** that
  exists precisely because those effects could not be stat modifiers.

Trajectory: `resolve_attack` grows a `&ResolutionFlags` argument; that struct accumulates ~20 bools;
the denominator becomes a chain of `if` multipliers whose **order is load-bearing, undocumented and
untested** — because §9.5 established there is no harness for order. And it is the file the digest
does not cover (§9.1).

### 9.8 XST-F7 — closed `EffectOp` grew 22 % before a line of Rust exists

* `26_implementation_architecture.md` and `SESSION_HANDOFF`: *"closed **9**-variant"*
* `catalog/cat_19_ABL_ability.md`: *"closed **11**-variant"*

And `PL_007c_integration.md §12.13` records that two copies of the enum **diverged within 24 hours**
(`StatusApply` gained `duration_rounds` in one and not the other), and that a signed
`VitalDelta { amount: i32 }` was a **damage-law-chain bypass** — an unmissable, armour-ignoring
weapon usable in a sanctuary.

> **The closed vocabulary did not prevent the bypass.** A closed enum constrains *which* variants
> exist; it says nothing about whether a variant routes through the law chain. That defect was
> caught by a human reading two files side by side.

### 9.9 XST-F8 — the real determinism constraint is the missing clock, not the missing float

The no-float rule genuinely holds (zero `f32`/`f64` in `sim-core` or `commit-service` outside
benchmarks). It forbids almost nothing a turn-based RPG needs.

The actual constraint is that **`Domain::apply` receives no `Tick`.** The domain cannot ask "how long
has it been", so every duration must be a counter decremented by an explicitly injected engine
payload — as `knocked_out: Option<u8>` already is. Correct and workable, but it means **the number of
scheduled admissions scales with the number of live timed effects**. At 100 players with DoTs, HoTs
and buffs, timer inputs become the dominant admission load — and doc 21 §7 lists validator-pipeline
cost as explicitly unmeasured. **This is the load nobody has budgeted.**

### 9.10 What the adversary judged genuinely right

Named because these are specific and rare, and because the critique above is otherwise unrelieved:

1. **Per-coordinate RNG derivation with pinned discriminants** — *"the best decision in the
   codebase"*. The common design draws sequentially from one PRNG, coupling every historical roll to
   the count of prior draws, so adding one ability silently renumbers all history.
2. **Non-vacuity with real bites, asserted as ratios** — doc 21 §8 ships a falsifier per ceiling and
   asserts ratios rather than absolutes, so the gate stays honest on other hardware. §7 then
   enumerates what is *not* measured and forbids inference.
3. **The no-float rule is held, not merely stated** — most projects declare it and leak within a
   month.
4. **Rules held behind `Arc` outside `State`**, so they cannot enter checkpoints or crash rebuilds —
   tiny, correct, and agonising to retrofit once state has been serialised with rules embedded.
5. **A failed precondition is a recorded normal outcome, not an error** — every item's fate is
   recorded, including duplicates and expiries.
6. **Departure removes the registry entry before any message can exist**, making duplication
   structurally impossible (the loss side still needs closing — XST-D9).

### 9.11 The adversary's three changes for TODAY

1. **Make the digest bite.** Move every game constant out of `combat.rs`/`stats.rs` into the rules
   struct; hash the real struct; add `ruleset_digest` **and `engine_build`** to `EventEnvelope`; make
   `Island::restore` **verify** rather than stamp. Then write the bite test the repo's own discipline
   demands: *edit one constant → assert the digest moves → assert replay under a mismatched digest is
   refused.* **That test cannot be written today, which is the tell.**
   This also surfaces an unanswered question: there is **no migration story for a locked order under
   digest-pinned replay**, because nothing versions the rules *engine* (`upcaster.rs` versions event
   schemas, not rules). `Rules` must be resolvable by historical version, not just by digest — a
   trait-shape change today and an impossible retrofit later.
2. **Fix the four silent-correctness defects and add the four tests that can fail.**
3. **Open the tail of the stat array, keep the closed head.** Keep the enum for the ~8 slots the laws
   `match` on — they must be named to be matched — and give author-declared stats an interned
   `StatId(u16)` tail that feeds projections, UI and content conditions. Measured cost 1.08×.

## 10. Corrections to statements made earlier in this investigation

Recorded because a record that keeps only its correct claims is a highlight reel.

* I stated `EffectOp` has **11** variants; a helper agent counted **10**; the docs say **9**. The
  count is unresolved and unchecked — which is itself XST-F1, but my "11" should not be quoted as
  settled.
* I initially diagnosed five failover-test failures as **connection exhaustion (CEI-7)** and wrote
  that explanation into four test files as a comment. The real cause was the dev Postgres container
  being stopped. The comments were corrected; the pool-size reduction was kept as sizing hygiene,
  not as a fix.
* [Doc 26](26_implementation_architecture.md) §2 repeats the stale "closed 9-variant `EffectOp`"
  claim, inherited without verification.
* **[Doc 26](26_implementation_architecture.md) §1's central performance argument does not hold.**
  I used the prior project's 125.78 ns vs 1.42 ns to justify the closed 10-slot enum, and computed
  that a dynamic path would cost "~1 µs, 5× the whole step budget". Re-measurement (§9.4) shows an
  open interned-ordinal design costs **1.08×, or 0.05 % of a step** — and that our own projection
  step already removes the lookup from the hot path entirely. The code/config *line* in doc 26
  stands; the *evidence* for closed-10 specifically does not, and that decision needs re-making on
  the grounds that actually apply (the laws must `match` on named slots).
* I described the sign-inversion defect as a hazard I had found. It is not: **DF07_002 EC-2 records
  it as an already-found, already-fixed defect with acceptance criterion AC-DF7-17, whose stated
  kill-mutation is exactly what I implemented.**

---

## 11. Recovered from the raw reports — what the first distillation dropped

§5 compressed five ~25 KB agent reports into ~25 lines each. **That compression — not the later
context compaction — is where material was lost.** The full reports were afterwards recovered intact
from the session's subagent transcripts and are preserved verbatim in
[`27a_stress_test_agent_reports.md`](27a_stress_test_agent_reports.md). This section promotes what
§5 dropped and that turned out to be load-bearing. New ids: `XST-F9..F12`, `XST-R10..R13`.

Worth stating plainly, because it changes how the rest of this file should be read: **the summary was
lossy in a way the summariser could not see.** Four of the seven items below bear directly on
decisions §7 and §9 left open — including the one that settles §9.4.

### 11.1 XST-F9 — projecting onto a fixed slot is TYPE-INCORRECT, not merely lossy

§9.4 removed the *performance* justification for the closed 10-slot set and left the decision to be
re-made on expressiveness. **This is that argument, and it is stronger than "some detail is lost".**
Three cases exist in the code as written:

**(a) `Accuracy` — wrong operator.** `hit_chance_pm = clamp(500 + acc − dodge, 50, 950)` makes
accuracy *a term in a difference*. Project two author concepts onto it: *"keen-eyed"* (+accuracy) and
*"true strike: ignores dodge"*. The second is **suppression of the dodge term** — a different
operator, not a larger accuracy. The only available projection is a big `acc`, which saturates at 950
and makes the actor near-unmissable against **every** target rather than the evasive one. Against a
0-dodge target the two concepts are indistinguishable; against a 400-dodge target both give 950. The
mechanic is not approximated — **it is replaced by a different mechanic**, and which build is strong
changes as a result.

**(b) `Armor` — a ratio projected into a difference.** `base = (strike_power − armor).max(1)`. Plate
is a flat reduction; a ward is a *percentage*. Encoding 30 % reduction as `Armor` requires a flat
number correct at exactly one attacker power level and wrong everywhere else, degrading to the
`.max(1)` floor against weak attackers. The slot where a ratio belongs is `RESIST_PM` — which is
`const RESIST_PM: i64 = 0` at compile time. **There is nowhere else to put it.**

**(c) `MoveRange` collapses two independent axes.** It is derived from `Speed`, so *"lumbering but
long-striding"* and *"quick but short-stepping"* are the same point in the model. Not lossy —
**unrepresentable**.

And the organisational prediction, which is the part that makes this urgent rather than academic:

> Once "engine release + ownership-matrix registration" is the price of a slot, people **stop asking
> and start overloading** — fire resistance encoded as a negative `Armor` contribution or a
> `CritMult` fudge — and two years later nobody can say what `Armor` means.

Named precedent: Bethesda's Creation Engine has a fixed, enumerated Actor Value list and grew the
open-ended **keyword (`KYWD`)** record as its escape hatch; the modding community's standing
complaint is running out of usable actor values. **A closed attribute list plus an open tag namespace
is the shipped answer to this exact problem** — i.e. XST-R6 + XST-R8, which §7 already proposes on
weaker grounds.

Realistic pressure for slot #11+: per-element resistances (3–6 slots), resource pools, casting speed,
healing power, threat modifier, stealth, carry weight, block/parry. All table stakes for the genre.

### 11.2 XST-F10 — the damage packet is a scalar, and step 1 of the locked chain is armour

Absent from §5–§7 entirely, and it breaks COMB_001 §4 rather than extending it.

An author ships a *Flameblood Saber*: **60 % of physical damage converted to fire**. Target is a Fire
Wraith: 0 armour, 75 % fire resist. Correct resolution: 40 % of base takes armour and no resist;
60 % takes no armour and 75 % resist. `resolve_attack` has **one** `base`, **one** `ELEM_MULT_PM`,
**one** `RESIST_PM` — and every expressible ordering is wrong:

* armour-then-element (the current order) subtracts armour from the fire portion too, so a
  fire-converted build gets **worse** against armour — backwards from every game in the genre;
* even after adding `Resist(ElementId)` slots (DF7-D2), a **scalar base cannot carry which fraction
  is which element**.

It cascades: leech (*"gain 5 % of fire damage as life"*), reflect (*"reflects physical"*) and ailment
magnitude (*"ignite for 90 % of fire damage"*) all need the typed breakdown, so the scalar silently
invalidates four later features. One trap in the fix: **`max(1)` must apply once to the total** —
per-component and an 8-element hit gets 8 free damage, turning a fully-resisted attack into
guaranteed chip.

### 11.3 XST-F11 — the cold/hot boundary is drawn on the wrong axis

The dense array is justified by *"the hot path only indexes; resolution is cold."* `StatSlotDecl` draws
that boundary by **authoring time**. The genre needs it drawn by **change frequency** — and the two
diverge the moment anything mutates a term during play.

RimWorld, concretely: a bolt to the leg drops `leg.HitPoints` → `CalculatePartEfficiency` →
`CalculateLimbEfficiency` (segments, `appendageWeight` lerp) → `CalculateTagEfficiency` (weighted
average over `MovingLimbCore`) → `Moving` capacity falls → `MoveSpeed` falls → below 15 % the pawn is
downed. **That entire cascade runs on the damage event.**

> This is **not** a performance problem — re-projecting 10 slots × K terms is tens of ns inside a
> 176–229 ns step. It is an **architectural-claim** problem: the moment wounds, encumbrance, status
> severity or metabolism become terms, the "cold path" invariant is false and **nobody has budgeted
> the re-resolution**.

Rated the report's highest danger precisely because it is invisible until the first system that needs
it, by which time "cold path" has quietly come to mean "the path that runs whenever, unbudgeted". It
is the same root cause as XST-F8's unbudgeted timer load: **both are the admission/resolution
schedule being asserted rather than measured.**

### 11.4 XST-F12 — DF7-A5's stated justification is wrong; the property it wants is *staging*

DF7-A5 sums percent modifiers and justifies it as *order-independence*. **Multiplication is also
commutative.** What actually destroys order-independence is **mixing `+` and `×` in one unordered
pool** — Balatro's `40 × ((4+4)×2) = 640` vs `40 × ((4×2)+4) = 480`.

So the correct rule is not *"never multiply"*, it is:

```
within a stage: contributions combine by ONE commutative operator (Sum or Product)
across stages:  the LOCKED layer order applies
```

This is the rationale XST-R7 (`combine: Sum | Product`) was missing: R7 is not a *concession* to
multiplicative content, it is **the corrected statement of the axiom**. Product-mode declarations
still resolve cold, still emit a dense `i32`, and are still order-independent within their stage.
Viewed this way, Balatro's player-dragged joker order is a UI for **choosing stage assignment** — and
staging is the better model because it is replayable.

### 11.5 XST-R10..R13 — four recommendations §7 dropped

| Id | Recommendation | Fixes | Cost |
|---|---|---|---|
| **XST-R10** | **`EffectOp` gets combinators, not more leaves** — `Seq`, `Repeat(u8, id)`, `IfElse(Precondition, id, id)`, stored in a **flat arena** in the content artifact and referenced by `u32`. A closed `match` becomes a closed **grammar**. | XST-F7 (the 9→11 growth) — *"if the variants are all leaves you will be at 40 within a year"* | medium; **the actual answer to F7**, which tightening cannot fix |
| **XST-R11** | **A `REPLACE` stage in front of the locked 4-step chain**, holding a closed `DamageReplacement { Double, Halve, SetTo, MinimumOf, PreventAll }` ordered by a **declared** `replacement_priority: i16`, ties by creation index. MTG CR 616 made deterministic. | prevention/doubling effects that today have no home | medium; keeps the 4 steps locked |
| **XST-R12** | **Status *instances*, not flags** — `StatusInstance { flag_ordinal, severity_milli, stacks, expires_at_tick }` in a bounded (≤32) per-entity array, with the `StatusFlag` bitmask **derived** and kept as the ~1 ns hot check. | severity/stacking/duration, none of which a flag can carry | medium; bitmask stays the fast path |
| **XST-R13** | **Typed side-tables + an explicit, budgeted `Reproject { dirty_slots }` step**, and redefine "cold path" as *"resolved from a declaration"* rather than *"never runs during play"* — then **measure** it. | XST-F11 | medium; converts a rotting invariant into a visible cost |

XST-R10 deserves emphasis: it is the only proposal that actually addresses XST-F7. A closed
vocabulary that keeps growing by leaves is not closed in any useful sense; a closed vocabulary that
grows by *composition* is.

### 11.6 The adversary's fixable-now vs rewrite-later triage

The most decision-grade artifact in the whole exercise, and §9 dropped it. The right-hand column is
the cost of **not** doing it now.

| Finding | Verdict |
|---|---|
| XST-D5 digest decorative | **Cheap now (~200 LOC).** After 10⁶ events: archaeology. |
| XST-D6 Lex clamp escaped | **Trivial now.** Reorder + one test. |
| XST-D1 percent underflow | **Cheap now.** After content tuning: full rebalance. |
| XST-D7 dropped flat modifiers | **Trivial now.** |
| XST-F9 / F5 closed slots | **Cheap now** (two accessors, ~11 tests). **After ordinals are serialised: data migration + rewrite.** |
| XST-D9 handoff corpse / loss | **Cheap now.** Durable handoff later = protocol rewrite. |
| XST-D10 encounter scoping | **Cheap now.** Later: mystery-bug archaeology. |
| XST-F5 unobservable layer order | **Cheap now** — make it observable, or drop the claim. |
| XST-D8 clamp composition | **Trivial now.** |
| XST-F7 `EffectOp` growth | **Not fixable by tightening** — needs the open tag namespace (XST-R8) + combinators (XST-R10). |
| XST-F6 `combat.rs` rot | **Preventable now by policy; not fixable later at any price.** |

Two rows carry a genuine deadline rather than a preference:

1. **Slot ordinals must be decided before they are serialised into replay logs.** Today the cost is
   two accessors; after the first committed event stream it is a data migration.
2. **`combat.rs` rot is preventable only by policy, and only now.** There is no later fix, because by
   then the special cases *are* the game.

### 11.7 Why this was lost, and the rule that follows

Nothing here was lost to context compaction — the compaction was survivable and §9 was recovered
verbatim. It was lost when five reports were compressed into a table and four paragraphs, by a
summariser who could not tell which dropped sentence was load-bearing. The tell was visible in
hindsight: §5.3 quoted an agent's own proposal id with no corresponding entry in §7, and §9's
adversarial list skipped straight from F5 to the rot prediction with no F6.

> **Rule:** when an investigation's raw evidence is model output that will be summarised, **write the
> raw output to disk before summarising it**, not after. The summary is a lossy derived artifact; the
> reports are the SSOT. That is the same derived-never-stored discipline DF7-A2 applies to stat
> blocks, applied to research.

