# DF07_002 — Stat Block: edge cases, defects & closure

> **Status:** **CLOSURE PASS 2026-07-26** over [`DF07_001`](DF07_001_actor_stat_block.md) DRAFT, run against
> the five consumers that landed the same day (COMB_001 CANDIDATE-LOCK, COMB_003/004/005, ABL_001) plus
> PL_007/PL_007b. **4 defects found in the law** (one inverts a security property), **11 unhandled edge
> cases closed**, **3 open questions decided**, **1 left open with an owner**. A second pass across the
> **seams** (`/review-impl`, same day) raised **7 more defects owned by the family, not by DF7** — §1.5;
> two of them invalidated DF07 text written against them, corrected here.
> **Stable IDs:** `EC-1..EC-15` edge cases · new axioms `DF7-A12..A14` · new decisions `DF7-Q12..Q14` ·
> new deferrals `DF7-D14..D15` · new rejects `stat.tuning_invalid` · new AC `AC-DF7-16..21`.
> **Applies to:** DF07_001 (fixes landed there in the same commit — this doc is the *why*, DF07_001 is the
> *law*). Nothing here changes the slot set, the layer model or DF7-Q1..Q11.

---

## §1 — Defects in the law (found by this pass, fixed in DF07_001)

These are not edge cases; the DRAFT was **wrong** and would have shipped wrong.

### EC-1 — The Lex clamp was escapable (severity: high)

DRAFT order ran `Lex clamp → slot clamp`, justified as *"so an author clamp cannot escape a world rule."*
That is inverted. Clamps do not compose by priority — **the last clamp wins**:

```
Lex axiom:  strike_power ≤ 100      (a world rule: "no mortal exceeds 100")
author:     StrikePower.clamp = { min: 200, max: 5000 }
resolved v = 40  →  lex_clamp → 40  →  slot clamp(min 200) → 200      ✗ world rule breached
```

An author needs no malice to hit this — a high `clamp.min` is a normal way to floor a boss stat. Under DF4,
where Lex axioms are the mechanism by which a reality states *"here, magic is impossible"*, a silently
escapable ceiling is the difference between a rule and a suggestion.

**Fix (DF07_001 §4 step 5–6, DF7-A3):** `slot clamp → Lex clamp`. The world rule runs **last**.
**Bite test (AC-DF7-16):** the example above must resolve to 100, and it must *fail* if the two steps are
swapped back — a check that cannot fail is not a check.

### EC-2 — A percent debuff past −100% inverted the stat (severity: high)

`v × (1000 + Σpct) / 1000` with `Σpct = −1200` yields `v × −0.2`. Every affected slot flips sign, and since
the slot clamp for e.g. `Armor` is `0..100_000`, a −120% armour debuff produced **negative armour that
clamps to 0** (benign) while a −120% `StrikePower` debuff on a negative-min slot would have produced a
*negative* strike power feeding `base = max(1, sp − armor)` — benign only by accident of that `max(1, …)`.
The general form is not benign: stacking debuffs must saturate at "reduced to nothing", never invert.

**Fix:** `factor = max(0, 1000 + Σpct)`. −100% is the floor; further debuffs are absorbed.
**Note:** DF7-A5's additive-percent rule is what makes this bounded and inspectable at all — under
multiplicative chaining there is no single place to floor.

### EC-3 — `StatBlock` as a hash map broke the replay assertion (severity: medium)

DF07_001 §2 declared `HashMap<StatSlot, i32>`. Resolution itself is order-stable (§4 iterates the enum), but
the *container* is not: the moment any consumer serialises a block — COMB_001 now stores
`stat_snapshots: HashMap<ActorRef, (StatBlock, StatEpoch)>` and checkpoints it per round — hash iteration
order enters the replay bytes, and DF7-V4's "epoch-equal ⇒ byte-identical" assertion starts failing
nondeterministically (or worse, passes on one machine and fails on another).

**Fix:** `StatBlock = [i32; STAT_SLOT_COUNT]`, indexed by slot ordinal. Dense, fixed-size, trivially stable.
ABL_001 reached the identical conclusion independently for `known_abilities` (`BTreeSet`, ABL-V7) — the same
discipline, and a sign the constraint is real rather than stylistic.
**Consumer note (declared to COMB_001):** the *outer* `stat_snapshots` map wants `BTreeMap<ActorRef, …>` for
the same reason.

### EC-4 — Unbounded intermediate arithmetic (severity: low, but a panic)

`milli_mul(prog.raw_value: u64, weight)` has no bound. PROG_001 explicitly supports `Unbounded` cap rules and
cultivation values that grow without a ceiling; a `raw_value` past ~9.2×10¹⁵ overflows i64 milli-units, and
the percent step multiplies again. In debug builds that is a panic in the middle of combat resolution; in
release, a wrap — i.e. a stat that becomes huge or negative at a threshold no author can see.

**Fix:** all intermediate arithmetic is **saturating** (`saturating_mul_div`), and the slot clamp — whose
`max` is bounded by construction — brings the value back into range. Stated in DF07_001 §4.

### §1.5 — Raised to the family (not DF7's to fix)

The same pass, run across the seams, surfaced defects **outside** this feature. Recorded here because they
were found here and because two of them invalidate DF07 text that was written against them.

- **HIGH-1 — the Untracked group HP pool has no declaring owner.** COMB_001 AC-COMB-7 requires it,
  COMB_004 SPO-A1/A6 fire loot *when it reaches zero*, and DF07 §9 supplies its ceiling
  (`archetype.MaxHp × count`) — but `combat_session` (COMB_001 §2) has **no field for it**, and Untracked
  actors hold no RES_001 `vital_pool` row (AIT-A8). The default tier for every spawn therefore has no place
  to keep its current HP. Proposed fix: `combat_session.group_pools: BTreeMap<ActorRef, GroupPool { max,
  current, member_count }>`, COMB_001-owned, ceiling from DF7, zero-trigger read by COMB_004. **DF07 §9
  reworded** to supply the ceiling and explicitly disclaim the storage.
- **HIGH-2 — ABL_001 `ScaleTerm` reads progression live, breaking the snapshot invariant.** ABL §4.3
  resolves `prog[s.kind_id].raw_value` at cast time while every other law-chain input comes from the DF07
  snapshot. PROG_001 Action-triggered training fires *during* combat (striking trains swordsmanship), so an
  ability's damage drifts mid-encounter while a basic `Strike`'s does not — contradicting AC-COMB-15 and
  breaking AC-COMB-16's byte-identical replay. **DF7-V4 cannot catch it**: the epoch guards the block, not a
  direct progression read that bypasses it. Fix: resolve `ScaleTerm` against a snapshotted progression view
  keyed by the same `progression_turn`, or fold scaling into the slot terms.
- **MED-3 — innate abilities leak to Untracked actors.** ABL §6's derived-set predicate is
  `∀ req ∈ a.requires : …`; with `requires` empty the quantifier is **vacuously true**, so an innate ability
  enters the set with no `actor_progression` row — contradicting the prose two paragraphs later ("their
  derived set is empty"). The missing-row case is also undefined for non-empty `requires`.
- **MED-4 — round-scoped status expiry is asserted by three docs and owned by none.** ABL's
  `StatusApply { duration_rounds }`, COMB_001's `knocked_out` 5-round lifecycle and the `defending` /
  `slowed` / `hasted` / `stunned` set all require expiry, while PL_006 V1 ships **no auto-expire** (manual
  dispel only; scheduler V1+30d).
- **MED-5 — Untracked ability costs have no store.** ABL §7.1 deducts from `vital_pool`; archetype-granted
  abilities are precisely the Untracked case, which has none. Same root as HIGH-1.
- **LOW-6 — COMB_004 writes `actor_progression` with no declared `TrainingSource`.** PROG_001's enum is
  closed (Action / Time; Mentor / Quest / CrossActor V1+); a victory award is none of them.
- **LOW-7 — ABL's `PowerTerm` arithmetic is not saturating**, though it claims to inherit DF7-A4. Same
  overflow class as EC-4, against the same `Unbounded` cultivation values.

---

## §2 — Edge cases closed

| # | Edge case | Resolution |
|---|---|---|
| **EC-5** | `stat_tuning.speed_per_tile = 0` — a **divisor** — or `max_move = 0`, or `base_move > max_move`. | Stage-0 validator + new reject **`stat.tuning_invalid`** (DF7-V1). A division-by-zero must be impossible before an actor resolves, not caught at the first movement. |
| **EC-6** | An actor **promoted Untracked → Tracked** (COMB_005 §7 `tier_hint`) switches stat source from the archetype block to the derived block, and its `MaxHp` can move 30 → 100. | **Promotion is pre-`Born`, so the switch never happens inside an encounter** — COMB_005 §6 runs tier promotion at step 4 and `CombatSessionBorn` at step 5, and SPN-A9 fixes participants at Born. The block is therefore resolved **once**, already on the derived path, and the snapshot never changes stat *source* mid-fight. *(Corrected 2026-07-26 during the review pass: the first version of this row described a mid-encounter switch and leaned on RES_001's max-change rule to preserve "current HP" — a value Untracked actors do not have, since they hold no `vital_pool` row. Both halves were wrong; see §1.5 HIGH-1.)* If a V1+ path ever promotes mid-encounter, it must land at a round boundary via `progression_turn`, and it needs HIGH-1 resolved first. |
| **EC-7** | Do **Untracked** actors get equipment/status layers, or archetype only? DF07_001 §9 said "archetype block; no per-actor resolution", but §4's pseudocode still summed modifiers for them. | **DF7-A12 (archetype is terminal).** Untracked actors resolve **archetype + engine defaults only** — no progression, equipment or status layer, because under AIT-A8 they hold no per-actor rows to read. Anything that *needs* a per-actor modifier (a status, a dropped weapon) is precisely the signal to promote (COMB_005 §7 / PROG-D22). This also keeps COMB_001's `EngineDriver` group pool honest: one block × N, as COMB_005 §7 already assumes. **The archetype path still applies both clamps** — an archetype that skipped `lex_clamp` would reintroduce EC-1 through the back door for exactly the actors a world rule most often targets (a bandit horde in a no-magic realm). |
| **EC-8** | `Percent` on a **per-mille slot**: is "+10% accuracy" `+25‰` (10% of 250) or `+100‰`? | **10% of the subtotal** — `op: Percent` is always relative, never percentage-points (DF7-A13). Authors wanting "+10 percentage points" use `Flat: 100`. Called out because on per-mille slots the relative form is almost always *not* what an author means, and a silent misreading is a balance bug nobody can see. |
| **EC-9** | Does an **LLM driver** see its *own* exact stats? DF07_001 A10 said "self/party exact", which reads as yes; COMB_003 THR-A4 and ABL_001 §8.3 both assume **no numbers at all** in prompts. | A10 **tightened**: exact numbers go to the human UI only; **no LLM-bound payload carries a raw slot value, including the actor's own**. The looser reading would have re-opened the leak COMB_003 closed. |
| **EC-10** | Which instrument does `instrument_match` match against, given PL_005 `Strike` carries a per-action `tool` while PL_007 tracks an *equipped* item? | The **equipped main-hand instance** (PL_007 `actor_equipment`). A per-action `tool` that is not equipped contributes nothing — identical to PL_007 §6.5's "carrying a sword in a sack does not arm you", and it keeps `active_instrument` inside `StatEpoch.equipment_version` rather than being a hidden per-action input the snapshot cannot see. |
| **EC-11** | Status magnitude under PL_006's **`Sum`** stack policy (Drunk, Wounded) can exceed the documented `1..=10`. | DF7 clamps `m` to `10` when computing modifiers. PL_006's `status.invalid_magnitude` is the primary guard; DF7 does not *rely* on an upstream invariant for a value it multiplies by. |
| **EC-12** | `VitalMaxRecomputed` while the actor is **Dead / Dying / Ghost / knocked_out**. | Ceiling recomputes as normal; `current_value` clamps as normal; **no transition fires** — the max-decrease rule already states a clamp never triggers `OnZeroEffect`. Mortality state is WA_006/PCS_001-owned and DF7 never writes it. |
| **EC-13** | An actor with **no `actor_progression` row and no archetype entry** (e.g. a PC in a sandbox reality that declares neither). | Engine defaults (DF7-A6) — playable, not a reject. Note the deliberate asymmetry with COMB_005 **SPN-V2**, which *does* reject a spawn whose archetype is undeclared: a spawner naming a class that doesn't exist is an authoring error, whereas an actor in an undeclared-stats reality is the documented zero-declaration case. |
| **EC-14** | `MoveRange` when `Speed` clamps to its floor of 1. | `3 + ⌊1/50⌋ = 3`, clamped to `[1, max_move]`. No zero-movement state exists by construction — an actor that cannot move at all is a `stunned`/`knocked_out` **status** (COMB-owned, DF7-A8), not a stat of 0. |
| **EC-15** | Two encounters, same actor, same turn (an actor cannot be in two `combat_session`s — COMB_001 §6) — but a **manifest hot-reload** mid-encounter changes `stat_slots` for everyone. | `manifest_version` is a `StatEpoch` field, so every combatant's snapshot invalidates together at the next round boundary. Rounds already resolved keep the numbers they resolved with — which is exactly the atomicity DF7-Q5 exists to protect. |

### New axioms

- **DF7-A12 (Archetype is terminal for Untracked actors).** An actor without an `actor_progression` row
  resolves `archetype + engine defaults` and **nothing else** — no progression, equipment or status layer.
  Under AIT-A8 it holds no per-actor rows to read, and inventing them would defeat the quantum-observation
  budget. A modifier that must apply to such an actor *is* the promotion signal (COMB_005 §7).
- **DF7-A13 (`Percent` is relative, never percentage-points).** `op: Percent` scales the post-flat subtotal.
  On per-mille slots use `Flat` for point-wise changes. One meaning, everywhere, including PL_007 items and
  PL_006 statuses.
- **DF7-A14 (Clamp order is a security property, not a formatting choice).** Whichever clamp runs last wins;
  therefore the **Lex clamp runs last**, unconditionally, and any future clamp source (DF4 axioms, admin
  caps, event-scoped caps) must state where it sits relative to it. Adding a clamp without answering
  "before or after the world rule?" is a defect.

---

## §3 — Open questions decided

| # | Question | Decision |
|---|---|---|
| **DF7-Q12** | Should `Speed` bind to **non-combat** systems — TVL travel duration, PL_001 turn order outside combat? | **No, V1.** `Speed` binds to initiative (`av = 10000/speed`) and `MoveRange` only. TVL_001 derives journey duration from route + mode + `time_flow_rate`; injecting a stat there would make travel time an emergent function of equipment, which no travel AC anticipates and which interacts badly with TDIL clock-split. Tracked as **DF7-D14** if a "fast traveller" fantasy is ever wanted. Naming it prevents the accidental version where someone "obviously" multiplies travel time by speed. |
| **DF7-Q13** | Do **skill checks** (PL_005 competence gating) read stat slots or PROG_001 kinds directly? | **PROG_001 kinds directly**, as DF07_001 §1 already scoped. Slots are the *combat-engine* vocabulary; a persuasion check reading `Accuracy` is a category error. ABL_001's `ProgressionReq` (ability acquisition) confirms the split independently — it gates on kinds, not slots. |
| **DF7-Q14** | Does DF7 need a **materialised cache table** now that five features read blocks per round? | **Still no** (DF7-D7 holds). The heaviest V1 reader is combat, and combat reads the **snapshot**, not a live resolve — that was DF7-Q5's second purpose. Non-combat reads are ~1/turn for the UI. Revisit only with a profile, per the no-defer-drift rule. |

**Left open (owner named, not resolved here):** **DF7-D15** — the `SetFloor` op PL_007 §6.3 originally
proposed and its current DRAFT dropped. It is genuinely useful ("this armour guarantees at least 10
armour"), but no V1 consumer emits one, and DF7-A14 now requires any new op to declare its position in the
clamp order. It lands with the first authoring need, between the percent step and the slot clamp.

---

## §4 — Acceptance criteria added (AC-DF7-16..21)

Each is a **bite test** — it must be able to fail, and the listed mutation is how you prove it does.

| # | Criterion | Bite (must fail when applied) |
|---|---|---|
| **AC-DF7-16** | Lex ceiling 100 + author `clamp.min` 200 ⇒ resolved value is **100**. | Swap steps 5 and 6 back → yields 200. |
| **AC-DF7-17** | `Σpct = −1200` on `StrikePower` ⇒ value **0**, never negative. | Drop the `max(0, …)` on `factor` → yields a negative stat. |
| **AC-DF7-18** | A block serialised into `stat_snapshots` and replayed is **byte-identical** across two runs and two machines. | Swap `StatBlock` back to a hash map → ordering drifts, DF7-V4 fires `stat.snapshot_epoch_mismatch`. |
| **AC-DF7-19** | `raw_value = u64::MAX` on a `StrikePower` term ⇒ saturates to the slot `clamp.max`, **no panic, no wrap**. | Use plain `*` → debug panic / release wrap to a negative. |
| **AC-DF7-20** | An Untracked bandit with a `Wounded` status resolves the **archetype block unchanged**; promoting it to Tracked mid-encounter changes its block only at the **next round boundary**, and its current HP is unchanged by the `MaxHp` rise. | Apply status modifiers to Untracked actors → the group pool desyncs from the per-actor block. |
| **AC-DF7-21** | `stat_tuning.speed_per_tile = 0` is rejected at canonical seed with `stat.tuning_invalid`. | Remove the validator → division-by-zero panic on the first `MoveRange` resolve. |

---

## §5 — What this pass did **not** change

Stated explicitly so the next reader doesn't re-litigate: the closed 10-slot set, DF7-A1/A2 (no aggregate,
derived-only), the fixed-point discipline, the snapshot model, the stat-layer/resolution-time boundary
(DF7-A8), the status→stat table, and every DF7-Q1..Q11 decision stand unchanged. The four defects in §1 were
internal to resolution and none had propagated.

**Verified clean at the seams** (listed so "no finding" is evidence, not a shrug): PL_007's ITM-C10
(Untracked hold nothing; gear is archetype flavour) and DF7-A12 agree exactly, reached independently from
opposite sides · the `StatModifier` shape and per-mille percent convention match on both sides of the
PL_007 seam · COMB_003's threat math is stat-free and seedless, so it neither reads a slot nor leaks one
(THR-A4 ∧ DF7-A10) · COMB_004 keys `loot_tables` by the same `ActorClassRef` as `stat_archetypes`, with
SPO-V3 enforcing the direction that matters · COMB_005 SPN-V2's stricter archetype requirement for *spawns*
is a deliberate asymmetry against EC-13's permissive fallback for *actors*, and both are now documented ·
the COMB_001 Q8 seed family gained exactly one role (`loot`) and threat/population correctly stayed out of
it · ABL's "`Heal` is not a negative `Damage`" rule keeps `Armor` from reducing healing · `Skill`'s retype
to `AbilityId` closes `combat.skill_unknown` onto a real declaring owner.

**Not clean:** the seven items in §1.5 — two of which (HIGH-1, HIGH-2) invalidate assumptions this document
was originally written against, and one of which (HIGH-2) is invisible to DF7-V4 by construction.

---

## §6 — Cross-references

- The law — [`DF07_001`](DF07_001_actor_stat_block.md) (§4 resolution · §6 layers · §9 tiers · §13 validators)
- Combat spine + snapshot host — [`COMB_001`](../../18_combat/COMB_001_combat_foundation.md) §2/§4
- Threat + prompt discipline — [`COMB_003`](../../18_combat/COMB_003_threat_and_targeting.md) THR-A4
- Loot / archetype key — [`COMB_004`](../../18_combat/COMB_004_loot_and_spoils.md) §3
- Spawning / tier promotion — [`COMB_005`](../../18_combat/COMB_005_encounter_spawning.md) §7, SPN-V2
- Abilities / `PowerTerm` — [`ABL_001`](../../19_ability/ABL_001_ability_foundation.md) §4.3
- Items / equipment seam — [`PL_007`](../../04_play_loop/PL_007_item.md) §6.3/§6.5
