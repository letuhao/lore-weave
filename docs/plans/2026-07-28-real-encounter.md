# Plan — one REAL encounter (COMB_001 spine)

> **Created:** 2026-07-28. Scope agreed with the PO after the doc 21–25 hardening run.
> Milestone chosen: *"một encounter THẬT, đầy đủ"*. Scale posture chosen: *"chứng minh kiến trúc
> trước"*. Both were previously **unrecorded anywhere in the corpus** — §1 fixes that.

---

## 1. Two decisions that had no home

### PLAN-D1 — the scale target is "prove the architecture", not "carry load"

**~100 concurrent players · 1 reality · ~20–30 islands · one machine.**

This had never been written down. The only number in the corpus is doc 13 §7.5's *"100 players in one
battle is one island on one core"* — a statement about a **physical per-island limit**, not a
deployment target, and the two were being conflated.

Consequences, now that it is stated:

| Measured | Needed at this target | Verdict |
|---|---|---|
| CEI-5: ~4 892 commits/s aggregate | ~10 commits/s (LLM-gated turns, ~30 islands) | ~500× headroom |
| CEI-6: knee at K≈16–24 islands/PG | 20–30 islands | **at the knee — the one number that is close** |
| CEI-7: ~98 island writers per PG | ~30 | fits; **pgbouncer not needed yet** |
| CNC-Q1 cross-replica limit | one game-server replica | already built, ahead of need |

**The useful conclusion is a negative:** at this target, nothing in doc 21 is a constraint. Effort
belongs in *making the game real*, not in throughput. CEI-6 is the only figure worth re-checking, and
only if island count climbs past ~24.

### PLAN-D2 — the next milestone is ONE real encounter, not breadth

Not the 65 V1 validators (admission cost is irrelevant at PLAN-D1's scale), and not the Class A
movement lane (a different load profile that needs CNC-Q2 first). One encounter, resolved by the real
rules, through the spine that was just hardened.

---

## 2. What "real" means here — and what it does not

The POC domain is four tools, flat 10 damage, no turn order. COMB_001's real encounter is a
**closure**, not a feature: `CombatSession` references COMB_002 (grid), COMB_003 (threat),
COMB_004 (spoils), COMB_005 (spawning), ABL_001 (abilities), DF07 (stats), PL_007 (equipment).

Building that blind is XL+ and would fail halfway. It is therefore sliced, and the slicing is by
**what makes combat stop being a toy**, not by document boundaries:

| # | Slice | Why this order |
|---|---|---|
| ~~**1**~~ ✅ | **Combat spine** — HSR initiative, 4-step damage chain, hit/dodge/crit on seeded RNG, rounds + status expiry, sides, win/lose, KO | This is the slice that changes the *kind* of thing it is. Turn order stops being "who submitted first"; damage stops being a constant; actors can die and be revived; someone wins |
| ~~**2**~~ ✅ | **DF07 stat snapshots** | DONE — and it corrected slice 1, see §6 |
| **3** | COMB_003 threat + targeting | NPCs choose targets properly instead of "first hostile" |
| **4** | COMB_002 tactical grid | Space: range, LoS, movement |
| **5** | ABL_001 abilities + PL_007 equipment | Depth on top of a working fight |

**Slices 1+2 are the deliverable of this plan.** 3–5 are named so the sequence is visible, not
promised here.

---

## 3. Slice 1 — the exact rules, from COMB_001 §4

Everything below is quoted spec, not invention. This matters: the engine is **deterministic and
LLM-free** (COMB-A1), so every one of these is a testable law rather than a tuning knob.

**Damage law-chain (4-step, LOCKED, order fixed for V1+):**
```
base = max(1, atk.strike_power − def.armor)
     × elem_mult      (V1 = 1.0)
     × (1 − resist)   (V1 = 0)
     × roll(0.85–1.15) × crit_mult
V1 collapse: floor(max(1, sp − armor) × roll × crit)
```
Status applies **after** damage.

**Hit/dodge:** `hit_chance = clamp(0.5 + acc − dodge, 0.05, 0.95)`; a miss is damage 0 **plus a Miss
event** — never a silent nothing.

**Initiative (HSR action value):** `av = 10000 / speed`; **lowest acts**; AV resets on act; status
mutates AV (`slowed +20%`, `hasted −20%`, `stunned +100%`); the initiator's first turn is `AV × 0.75`.

**Win/lose:** all hostiles at 0 HP → Victory · all friendlies → Defeat · all fled → Disengaged.

**Status expiry is ENGINE-owned and round-scoped.** The engine decrements every round-scoped status at
the round boundary. Doc COMB_001 flags why this is stated explicitly: **PL_006 V1 has no auto-expire
at all**, so three documents were assuming a mechanism that did not exist, and a 3-round debuff would
have been permanent.

**Seed:** `(reality_id, turn_id, actor_id, action_idx, role)` with `role ∈ {damage, crit, hit,
position, loot}`; `action_idx` is monotonic per `combat_session.next_action_idx`.

### 3.1 Where this lands in the code

`services/commit-service/src/domain.rs` is the `Domain` impl the island steps. The rules go there —
`apply` stays **deterministic, total and pure**, drawing only from the injected `DetRng`, which is
exactly what the seed roles above require. No kernel change is expected: `Domain::Rules` (RLS-A12)
already carries the ruleset slice, and `turn_slots` (IAS-D6) already gates who may act.

The interesting interaction is between **IAS-D6's turn slot** and **HSR initiative**. They are not
the same thing and must not be collapsed: the turn slot is an *anti-abuse budget* (one action per
actor per turn, enforced in-loop); initiative is *whose turn it is at all*. A correct encounter needs
both — the slot stops a player firing ten actions in their own turn, the queue decides when that turn
comes.

---

## 4. Non-negotiables carried in from the hardening run

* **Determinism** — `apply` is pure; all randomness via `DetRng` under the seed roles. The CNC-D5
  conformance test (1-vs-N threads) must stay green, and it will catch any ambient randomness.
* **Every outcome recorded** — a miss, a KO, an expiry are all events. CS-D5/EVT-L5: nothing silent.
* **Paired tests (IAS-D10)** — a test that a rule *blocks* something is paired with one that
  legitimate play still works. The turn-economy work proved why: a frozen game blocks abuse perfectly.
* **Structured payloads** — `CombatEvent` serialises structurally with decimal-string entity ids
  (CWC-A2); never `format!("{:?}")`.

## 5. Done when

Slice 1: an encounter runs to Victory/Defeat through the real chain, with initiative deciding order,
misses and crits observable, KO revivable, and statuses expiring at the round boundary — all
deterministic under a fixed seed, and all replayable.

---

## 6. Slice 2 — what DF07 changed about slice 1

Reading DF07 properly turned slice 2 from "swap the archetype" into a
**correction**.

**DF7-A4 (Integer determinism)** — *"all resolution runs in i64 milli-units;
exactly one `floor` at slot emit; **no float anywhere in the stat path**; same
inputs → byte-identical block on any machine."*

Slice 1 stored `accuracy` / `dodge` / `crit_chance` / `crit_mult` as `f64`, and
ran the damage chain and action value in floating point. That is reproducible
*within* a build but not reliably *across* targets — a fused multiply-add or an
x87 80-bit intermediate is enough — and this project replays committed
encounters as its recovery model (EVT-A9, CNC-D5, and now the writer recovery
of CNC-D2). A roll differing in the last bit on another machine makes a
replayed fight diverge.

So the whole combat path is now integer:

| | Before | After |
|---|---|---|
| fractional stats | `f64` 0.0–1.0 | **per-mille** `i64` 0–1000, as DF07 specifies |
| `hit_chance` | `clamp(0.5+acc−dodge, .05, .95)` | `hit_chance_pm` → `clamp(500+acc−dodge, 50, 950)` |
| damage roll | `0.85 + u*0.30` | per-mille band `850..=1150` |
| damage chain | float multiply | one integer expression, divisions carried to the end |
| `action_value` | `10000.0/speed × factors` | one numerator/denominator, single division, round-to-nearest |

**A bug this immediately caught.** The integer chain multiplies **four**
per-mille factors (elem, resist-complement, roll band, crit) and I divided by
`1000³`. Every hit came out 1000× too large and the damage-band test failed on
the first run. That is the trade fixed-point makes: it swaps float's quiet
rounding drift for scale errors that fail *loudly*.

**Round-to-nearest in `action_value`** is deliberate. Truncating would bias
every status toward acting sooner than its multiplier says — a small, systematic
advantage that would be very hard to notice as a bug and very easy to feel as
"the speed stat is wrong".

### 6.1 The DF07 axioms now under test

* **DF7-A6** a bare block is already playable (no declaration required).
* **DF7-A5** percent modifiers **sum**, never chain — two +50% give ×2.0, not
  ×2.25 — which also makes the result order-independent.
* **DF7-A3** the **Lex clamp runs LAST**. This encodes a correction the spec
  itself records (DF07_002 EC-1): the first draft ran `Lex → slot`, reasoning
  that an author clamp must not escape a world rule, which is backwards —
  whichever clamp runs last wins, so an author `min` above the Lex ceiling
  raises the value back through it. **Bite-proven**: reversing the order makes
  the test report exactly the predicted 80 instead of 50.
* **DF7-A2 / §8.2** the snapshot detects staleness via `StatEpoch` and is
  re-resolved, never patched.
* **§8.1** stats are snapshotted at encounter start, because a progression tick
  mid-fight would retroactively change how earlier rounds *should* have
  resolved — and that is the normal case: striking trains swordsmanship.
