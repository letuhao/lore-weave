# COMB_003 — Threat & Targeting

> **Conversational name:** "Threat" (THR). The **target-priority model** — who a hostile decides to attack,
> and why. Supplies the input COMB_002's TG-A4 stance vocabulary has always required (`CloseToMelee(target)`
> presupposes a *target*) and the input the concept notes' `Strike { target: "lowest_hp_hostile" }` selector
> assumed without ever defining.
>
> **Category:** COMB — Combat (COMB_003)
> **Status:** **DRAFT 2026-07-26**. Resolves the first third of **AUD-F9** ([`../../12_module_coverage_audit.md`](../../12_module_coverage_audit.md))
> — *"no threat/aggro — COMB_002's TG-A4 stance-picker has no target-priority model to pick whom to close on."*
> **THR-Q1..Q8 LOCKED** in this pass; `THR-A1..A6` axioms codified.
> **Stable IDs in this file:** `THR-A*` axioms · `THR-Q*` decisions · `THR-D*` deferrals · `THR-V*`
> validators · `AC-THR-*` acceptance criteria. Owns the `threat.*` reject namespace.
> **Builds on:** [COMB_001](COMB_001_combat_foundation.md) §2 `combat_session` + §4 engine determinism + §6
> sides · [COMB_002](COMB_002_tactical_grid.md) TG-A4 stance resolution + §5 range/LoS ·
> [ABL_001](../19_ability/ABL_001_ability_foundation.md) §4.1 `ModifyThreat` ·
> [DF07_001](../DF/DF07_pc_stats/DF07_001_actor_stat_block.md) §8 combat snapshot + A10 visibility ·
> [FAC_001](../00_faction/) stance · [REP_001](../00_reputation/) · [PF_001](../00_place/) `combat_safety`
> · [AIT_001](../16_ai_tier/AIT_001_ai_tier_foundation.md) tiers · [11 AGT](../../11_agent_decision_standard.md) A2/A3.
> **Determinism, LLM-zero-math and LLM-zero-space all bind here** — threat is integer, seedless and
> engine-owned (THR-A2).

---

## §1 — Purpose & V1 minimum scope

### Why this feature exists

COMB_002 shipped a positioning vocabulary whose every entry takes a target:

| TG-A4 stance | Presupposes |
|---|---|
| `CloseToMelee(target)` | a chosen target |
| `KiteAtRange(target)` | a chosen target |
| `Flank(target)` | a chosen target |
| `TakeCover` | "LoS-blocking toward **live enemies**" — which enemies matter? |

and COMB_001's ScriptDriver examples name selectors — `target: "lowest_hp_hostile"` (concept §9.2) — that
no doc declares. Meanwhile the LlmDriver is handed a `side_hostile` list with no ordering, so a Major NPC's
choice of victim is whatever the model feels like that round. Three consequences, all bad:

1. **Tank play is impossible.** Nothing an actor does can make an enemy prefer them, so the party's
   front-line has no mechanical function beyond occupying a tile.
2. **NPC behaviour is incoherent across rounds.** With no memory of who hurt whom, an LLM-driven NPC may
   switch victims every round for no in-fiction reason — and the A6 canon-drift detector cannot flag it,
   because nothing was contradicted; there was simply never a rule.
3. **`ModifyThreat` has nowhere to write.** ABL_001 §4.1 declares the op; this doc owns the table.

### V1 minimum scope

- **0 new aggregates** (THR-A3) — `threat_table` is a field inside COMB_001's already-ephemeral
  `combat_session`.
- **Deterministic integer accrual law** (§3) — no RNG, no seed role, no floats.
- **Per-round decay + target hysteresis** (§4) — the anti-flicker rule, which is the difference between a
  threat model that reads as intelligent and one that reads as broken.
- **Closed `TargetSelector` enum — 7 V1** (§5), formalising the concept notes' string selectors.
- **Driver bindings** (§6) — Script/Engine consume the selector directly; **Llm receives a top-K ranked,
  vague-labelled candidate list** (THR-A4), which is how the LLM keeps target agency at flat token cost.
- **Safe-zone and non-combatant guards** (§7) composing with PF_001 `combat_safety` + COMB_001 Q4.
- **6 V1 rule_ids** in the `threat.*` namespace + **6 validators** THR-V1..V6 + **AC-THR-1..12**.

### V1 NOT shipping

| Feature | Defer to | Why |
|---|---|---|
| Cross-encounter threat memory ("that one robbed me last week") | V1+ (THR-D1) | belongs to ACT_001 `actor_actor_opinion`, which already owns durable bilateral sentiment — threat is the *encounter-local* layer |
| Threat transfer / redirect (misdirect, taunt-to-ally) | V1+ (THR-D2) | needs a second-order op; `ModifyThreat` V1 is self-scoped or single-target |
| Per-archetype aggression personality (berserker vs coward AI) | V1+ (THR-D3) | IDF_003 personality already carries the inputs; wiring is a tuning pass, not a schema one |
| Threat from non-damage social acts (insults, Speak) | V1+30d (THR-D4) | PL_005 `Speak` has no combat severity model yet |
| Stealth / threat-drop / vanish | V1+ (THR-D5) | needs a visibility model; COMB_002 §5 LoS is binary and has no concealment tier |
| Player-visible numeric threat meter | V1+30d (THR-D6) | §9 defines the data contract; the V1 surface is a binary "targeting you" indicator (THR-A5) |
| Out-of-combat aggro radius / engagement trigger | **COMB_005** (THR-D7) | deliberately *not* this doc — see §8 |
| Threat-driven flee decisions | V1+ (THR-D8) | COMB_001's `Flee` is a speed roll; morale is a separate model |

---

## §2 — Concepts & axioms

| Concept | Maps to | Notes |
|---|---|---|
| **ThreatValue** | `i32`, milli-units | Integer throughout (THR-A2). Clamped `0..=THREAT_MAX`. |
| **threat_table** | `BTreeMap<(ActorRef, ActorRef), ThreatValue>` on `combat_session` | Key is `(observer, target)`. `BTreeMap` for order-stable iteration. |
| **ThreatEvent** | Engine-emitted on damage / heal / status / `ModifyThreat` | Not a stored event — a resolution-time call into §3. |
| **TargetSelector** | Closed enum, 7 V1 | What a ScriptDriver entry names (§5). |
| **CandidateList** | Top-K ranked `Vec<(ActorRef, VagueTier)>` | What an LlmDriver receives (§6.2). K = 3 V1. |
| **ThreatScope** | `SelfOnly \| SingleTarget` | `ModifyThreat`'s reach (ABL_001 §4.1). |

### Axioms

- **THR-A1 (Engine owns priority; the agent chooses within it).** The engine computes and ranks target
  priority. An LLM-driven actor picks from a **bounded, engine-ranked candidate list** it cannot extend;
  a scripted or engine-driven actor takes the ranked head directly. This is COMB-A1 (LLM-zero-math) and
  TG-A1 (LLM-zero-space) extended to *whom* — the third and last axis on which an LLM could otherwise
  improvise its way past the engine.
- **THR-A2 (Threat is deterministic and seedless).** All accrual and decay is integer arithmetic over
  values the engine already computed. **No RNG, no seed role** — COMB_001 Q8's roles stay
  `{damage, crit, hit, position}` (+ `loot`, COMB_004). Same encounter, same actions ⇒ byte-identical
  threat tables on replay. Randomising target choice would make the same fight resolve differently on
  replay for no design gain.
- **THR-A3 (No new aggregate; encounter-ephemeral).** `threat_table` lives and dies with the
  `combat_session` (COMB_001 §2), checkpointed with it per round. Durable cross-encounter sentiment is
  ACT_001's `actor_actor_opinion` and stays there (THR-D1).
- **THR-A4 (The LLM never sees a threat number).** The candidate list carries **ranked order plus the
  COMB_001 Q6 five-tier vague label**, never a `ThreatValue` and never a raw stat. A leaked threat integer
  is a leaked aggro formula, and DF7-A10 already forbids raw slot values in LLM-bound payloads for exactly
  this reason.
- **THR-A5 (Threat is legible to players, opaque in numbers).** A PC sees a binary *"this enemy is
  targeting you"* indicator plus the ordering among their own party. Exact numbers are THR-D6. The purpose
  is that a player can tell whether taunting **worked** without being handed the formula.
- **THR-A6 (Threat cannot cross a safety boundary).** No threat accrues to or from an actor whom PF_001
  `combat_safety` or COMB_001 Q4's disparity cap protects. A safe-zone bystander can never become a target,
  so anti-grief does not depend on every AI driver behaving.

### Event-model mapping

COMB_003 introduces **no new aggregate, no new EVT-T\* category and no new event sub-type.** Threat changes
ride the existing per-round delta:

| Trigger | Event | Owner |
|---|---|---|
| Any accrual / decay / target switch | **EVT-T3 Derived** `aggregate_type=combat_session`, `delta_kind=CombatRoundDelta` (existing) | COMB_001 |
| Encounter ends | table discarded with the session (`CombatSessionResolved`) | COMB_001 |

---

## §3 — The accrual law (THR-Q1 LOCKED)

Threat accrues to `(observer, target)` — read as *"how much `observer` wants to attack `target`"*. Every
source is a value the engine has **already computed** during resolution, so threat adds no new mechanic:

| Source | Contribution to `threat[(observer, target)]` | Notes |
|---|---|---|
| `target` damages `observer` | `+ damage_applied × dmg_factor` | the dominant term; `dmg_factor` = 1000‰ default. **`damage_applied`, not `damage_rolled`** — see the overkill rule below |
| `target` heals an **ally of** `observer`'s enemy side | `+ healing_applied × heal_factor` split across the healed actor's **current attackers** | `heal_factor` = 500‰ default — healers matter, but less than the blow. Split rule resolved at **THR-QO1**, §14.1 |
| `target` applies a status to `observer` | `+ status_flat × magnitude` | `status_flat` = 200 default |
| `target` fires `ModifyThreat { delta_pct, SingleTarget }` (taunt) | `threat[(observer, target)] = max(threat[(observer, target)], max(current_top, taunt_floor) × delta_pct / 100)` | a taunt at `delta_pct = 130` puts the caster 30% above the current leader. **`taunt_floor`** and the `max(…)` are load-bearing — see the two rules below |
| `target` fires `ModifyThreat { delta_pct, SelfOnly }` (fade) | `threat[(o, caster)] × delta_pct / 100` **for every observer `o`** | a drop applies across every observer. Scope `SelfOnly` ⇒ the subject is the **caster**, not the ability's target |

**Three rules the naive formula gets wrong** (each was a live defect in the first draft of this section):

1. **Overkill does not inflate threat.** Threat reads `damage_applied` — the amount actually subtracted
   from the vital pool — not the rolled figure. A 400-damage blow onto a 12-HP actor accrues 12. Otherwise
   a finishing blow banks enormous threat against a corpse's allies, and burst builds hold aggro through
   arithmetic that never happened. *(Healing follows the same rule: overhealing accrues nothing, which is
   also why healer threat stays proportional to real contribution.)*
2. **A taunt at round zero must not be inert.** `current_top` is `0` before anyone has acted, so
   `0 × 130 / 100 = 0` — an opening taunt would do **nothing**, which reads as a broken ability rather than
   as a rule. `taunt_floor` (manifest, default 500 — the same magnitude as `initiator_bonus`) is the floor
   the percentage applies to, so a taunt always establishes a real position.
3. **A taunt never *lowers* threat.** The `max(…)` wrapper matters when the caster is *already* the leader:
   without it, a taunt at `delta_pct = 130` against a caster holding 10 000 threat while `current_top` is
   their own 10 000 recomputes to 13 000 — fine — but a taunt at `delta_pct = 110` from an actor who is
   already at 3× the runner-up would **cut** their threat. Taunting to lose aggro is the opposite of the
   ability's meaning.
| encounter initiator (COMB_001 §6 trigger) | `+ initiator_bonus` at `CombatSessionBorn` | 500 default — whoever swung first is the natural first target |
| FAC_001 / REP_001 standing | `+ stance_bias` at `CombatSessionBorn` | hostile faction / notorious reputation start higher; **seeding only**, never per-round |
| adjacency (COMB_002) | `+ proximity_bonus` if adjacent at the observer's turn | 100 default — the small term that keeps melee coherent when all else ties |

```pseudo
// all i64 milli-units, one clamp at write — the DF7-A4 discipline applied to threat
fn accrue(session, observer, target, source) -> ():
    if observer == target:                        return    // THR-V7 — self-threat is unrepresentable
    if !threat_eligible(observer, target):        return    // §7 safety guard
    delta = source.value * factor_of(source) / 1000         // source.value is *applied*, not rolled
    t = session.threat_table.entry((observer, target)).or_insert(0)
    *t = clamp(*t + delta, 0, THREAT_MAX)
```

**`observer == target` is refused at the entry point, not filtered at selection.** A self-heal would
otherwise accrue threat from an actor to itself, and `HighestThreat` would happily return "attack
yourself". Refusing the write makes it unrepresentable rather than merely unselected — the same reasoning
as THR-Q7's safety guard, and it is asserted by THR-V7.

- **Clamped at 0** — threat never goes negative, so a fade cannot make an actor *anti*-targeted, and the
  ordering stays a total order over non-negative integers.
- **`THREAT_MAX`** (default 1 000 000) bounds a long encounter; hitting it is a balance signal, not an
  error, and the clamp keeps ordering meaningful rather than overflowing.
- **All factors are `RealityManifest` fields** (§9), so a reality can flatten threat entirely
  (`dmg_factor = 0`, everything ties, selection falls to the deterministic tie-break) or make it dominant.

---

## §4 — Decay and target hysteresis (THR-Q2 LOCKED)

### §4.1 Decay

At each round boundary, for every entry: `threat = threat × decay_milli / 1000` (default `decay_milli` =
950, i.e. −5%/round). Truncating integer division; entries reaching 0 are removed to keep the table sparse.

Decay exists so that a fight's *early* history does not dominate its *late* state — without it, the first
big hit determines the target for the rest of the encounter and nothing a player does afterwards matters.

> **Decay-to-empty is a real state, and it must not strand `current_target`.** Truncating division drives
> every entry to 0 in finite time, so a long stand-off (both sides `Defend`ing, or a stalled kite) empties
> the table while `current_target` still names someone. **Rule:** `current_target` survives an empty table
> — it is the *last* thing decayed away, and an observer with no threat entries keeps attacking whom it was
> attacking. The alternative (clearing it) makes a lull cause every hostile to re-pick simultaneously,
> which is the flicker §4.2 exists to prevent, arriving by a different road. `current_target` is cleared
> only by ineligibility (§7), never by decay.

### §4.2 Hysteresis — the anti-flicker rule

> **The rule:** an observer switches away from its current target only when a challenger's threat exceeds
> the current target's by a **switch margin**: `challenger > current × switch_margin_pct / 100`
> (default 110 for melee-range observers, 130 for ranged — the standard tactical-RPG asymmetry, since
> repositioning costs a melee actor its whole turn and costs a ranged actor nothing).

Without hysteresis, two party members within a few points of each other trade the enemy's attention every
single round, which reads to a player as an AI bug rather than as tactics. With it, pulling an enemy off a
target is a deliberate act that requires *decisively* out-threatening the incumbent — which is exactly what
makes a taunt feel like it did something.

Locked companion rules:
- **Losing the target forces a re-pick** — if the current target is KO'd, dead, fled or no longer
  `threat_eligible`, the margin does not apply; the observer re-picks freely that round.
- **Hysteresis is per-observer**, stored as `current_target: Option<ActorRef>` alongside the table.
- **Hysteresis never overrides a taunt** — a `ModifyThreat` taunt is defined (§3) as a *percentage of the
  current leader*, so a `delta_pct` above the switch margin clears the margin by construction. A reality
  that sets `switch_margin_pct = 200` and leaves taunts at 130 has made taunts inert; **THR-V3 warns at
  schema stage** rather than letting the author discover it in play.

---

## §5 — `TargetSelector` (THR-Q3 LOCKED)

The concept notes wrote `target: "lowest_hp_hostile"` as a bare string. Formalised:

```rust
pub enum TargetSelector {
    HighestThreat,        // the default; §4 ordering incl. hysteresis
    LowestHpHostile,      // the finisher — reads absolute HP, not a percentage
    LowestHpPctFriendly,  // healer targeting; the only friendly-side selector V1
    NearestHostile,       // Chebyshev (COMB_002 §5); the proximity-script baseline
    MostThreatenedAlly,   // "protect whoever is being focused" — the guard behaviour
    SelfTarget,
    CurrentTarget,        // explicit stickiness: keep hitting whom I am hitting
}
```

**Resolution is total and deterministic.** Every selector filters to eligible targets (§7), then orders by
its key, then breaks ties by `(ActorRef.actor_index)` — the same stable index COMB_002 §8 uses for
pathfinding tie-breaks. An empty result yields `None` and the driver falls back to `Defend`, never a panic.

**Why `LowestHpHostile` reads absolute HP but `LowestHpPctFriendly` reads a percentage:** a finisher wants
the target it can actually kill this turn (an absolute number), while a healer wants the ally in the most
danger relative to their own pool (a ratio). Using one metric for both produces a healer that ignores a
wounded tank in favour of a scratched mage.

### §5.1 Hysteresis applies to `HighestThreat` only (precedence, locked)

The switch margin (§4.2) is a property of **threat ordering**, not of target selection in general. Applying
it to every selector produces incoherent behaviour: a `LowestHpHostile` finisher would refuse to switch to
a nearly-dead enemy because the *threat* margin was unmet, which is the exact opposite of what the selector
was chosen for.

| Selector | Hysteresis |
|---|---|
| `HighestThreat` | **applies** — this is the rule's home |
| `LowestHpHostile` · `LowestHpPctFriendly` · `NearestHostile` · `MostThreatenedAlly` | **does not apply** — these are intent-driven and re-evaluate freely each turn |
| `CurrentTarget` | **subsumes it** — the selector *is* maximal stickiness; it re-picks only on ineligibility (§7) |
| `SelfTarget` | n/a |

`CurrentTarget` and hysteresis are therefore not in conflict and not redundant: hysteresis is *soft*
stickiness on a threat ordering, `CurrentTarget` is *hard* stickiness that ignores ordering entirely. A
script that wants "finish what you started, no matter what" names the latter.

---

## §6 — Driver bindings (AGT-A3)

### §6.1 Script / Engine drivers

| Driver | Behaviour |
|---|---|
| **ScriptDriver** (Minor NPC) | `combat_reaction_table` entries name a `TargetSelector` (schema-validated, THR-V2). Zero LLM. Replay-perfect. |
| **EngineDriver** (Untracked bulk) | `HighestThreat` from the **group's single observer row-set**: the group is one `ActorRef`, so it holds **one row per eligible target** (T rows) rather than one row per member per target (N×T). A 12-bandit group facing a 4-person party holds **4** rows, not 48 (AIT_001 parity). |
| **HumanDriver** (PC) | free choice among legal targets; the UI surfaces the THR-A5 indicator so the player can see whose attention they hold. |

### §6.2 LlmDriver — the bounded candidate list (THR-A4)

A Major NPC's `AssemblePrompt` (NPC_002 combat mode, COMB_001 closure item 4) receives:

```
{target_candidates}:                       # engine-ranked, top-K (K = 3 V1), NEVER numeric
  1. Lý Minh        — Wounded    (currently engaged)
  2. Tiểu Thúy      — Unharmed
  3. Lão Ngũ        — Bloodied
```

- **Ranked by §4 ordering**, labelled with the COMB_001 Q6 five-tier vague label, **no threat integers and
  no stat values** (THR-A4 / DF7-A10).
- The LLM may pick **any of the K** — so a character-consistent NPC can plausibly ignore the tank and lunge
  at the healer, which is precisely the dramatic agency the Chorus exists to provide. It may **not** pick
  outside the list; an out-of-set target is a canon-drift flag → fallback to candidate 1 (not `Defend` —
  the *action* was valid, only the target was not, so degrading the action would be over-correction).
- **Token cost is flat** — K entries regardless of encounter size. Same argument TG-A1 made for space.
- `K` is a manifest field (`threat_candidate_k`, default 3, clamp 1..=5); K = 1 makes Major NPCs behave
  exactly like scripted ones, which is the cost lever AGT-D5 asks for.

---

## §7 — Eligibility and anti-grief (THR-A6)

```pseudo
fn threat_eligible(observer, target) -> bool:
       target.side != observer.side                       // COMB_001 §6 side bucketing
    ∧ target.lifecycle == Existing ∧ !target.knocked_out   // KO removes from the table (§7.1)
    ∧ !target.has_fled
    ∧ !pf_001_safe(observer, target)                       // PF_001 combat_safety band
    ∧ !comb_q4_disparity_shielded(observer, target)        // COMB_001 Q4 cap, incl. PvE-in-safe-zone
    ∧ target.actor_class != NeutralCivilian                // COMB_001 §6 non-combatant exclusion
```

- **KO clears the target's rows** (`threat[(*, target)]` removed) so a downed actor stops drawing fire —
  which matters because COMB_001's `knocked_out` is revivable for 5 rounds and continuing to focus a downed
  body is both mechanically pointless and narratively absurd.
- **Fleeing clears rows** the round the flee succeeds.
- **The safety guard is at accrual, not at selection.** Threat toward a protected actor is never *written*,
  so no driver — including a hallucinating LLM handed a stale list — can route around it. Guarding only at
  selection would leave the vulnerability one bug away.

---

## §8 — What this doc deliberately does not own

**Out-of-combat aggro is COMB_005's** (THR-D7). The question *"a wolf notices a PC 6 tiles away and starts
a fight"* is **encounter formation** — it needs an aggro radius, an AOI hook (RTM-A6..A8), a spawn-group
notion, and the COMB_001 §6 state-machine trigger. All of those are population concerns. COMB_003 begins
at `CombatSessionBorn` and ends at `CombatSessionResolved`.

The seam is one call: COMB_005 hands `CombatSessionBorn` the **initiator** and the **participant list**;
COMB_003 seeds the table from them (§3, initiator bonus + stance bias). Nothing else crosses.

---

## §9 — `RealityManifest` extensions

```rust
pub struct ThreatConfig {
    pub dmg_factor_milli:      u32,   // default 1000
    pub heal_factor_milli:     u32,   // default  500
    pub status_flat:           u32,   // default  200
    pub initiator_bonus:       u32,   // default  500
    pub taunt_floor:           u32,   // default  500   — the floor a taunt's percentage applies to (§3
                                      //   rule 2); without it an opening taunt multiplies zero

    pub proximity_bonus:       u32,   // default  100
    pub decay_milli:           u32,   // default  950   (−5%/round)
    pub switch_margin_pct_melee:  u16, // default 110
    pub switch_margin_pct_ranged: u16, // default 130
    pub threat_candidate_k:    u8,    // default    3   (clamp 1..=5)
    pub threat_max:            i32,   // default 1_000_000
}
// RealityManifest.threat_config: Option<ThreatConfig>   — OPTIONAL; None ⇒ all defaults
```

A reality that declares nothing gets a working, balanced-enough threat model — the same
zero-declaration-plays discipline as DF7-A6, ABL-Q8 and PL_007's item-free reality.

---

## §10 — Decisions (THR-Q1..Q8 — LOCKED 2026-07-26)

| # | Question | Resolution & reasoning |
|---|---|---|
| **THR-Q1** | Explicit threat table, or infer priority from state each round (lowest HP, nearest)? | **Explicit accumulating table** (§3). Pure state-inference has no memory, so nothing a player *did* can influence targeting — tanking becomes impossible and taunts have nowhere to write. The table costs one ephemeral map on a session that is already ephemeral. |
| **THR-Q2** | Do targets switch the instant threat flips? | **No — hysteresis with a switch margin** (§4.2). Instant switching makes near-tied threats flicker every round, which reads as broken AI. The margin is what makes pulling a target a deliberate act, and it is why a taunt feels like it did something. |
| **THR-Q3** | ScriptDriver target strings or a closed selector enum? | **Closed enum, 7 V1** (§5). The concept notes' `"lowest_hp_hostile"` string would put author typos into runtime behaviour; a closed enum makes them schema rejects. Same discipline as DF7's `StatSlot` and ABL's `EffectOp`. |
| **THR-Q4** | Does the LLM pick the target, or does the engine? | **Engine ranks, LLM picks within top-K** (THR-A4, §6.2). Engine-only kills the Chorus's dramatic agency (an NPC could never make a characterful bad choice); LLM-only makes targeting unbounded and un-replayable. Top-K is the same bounded-vocabulary move AGT-A2 makes everywhere else, and its token cost is flat. |
| **THR-Q5** | Is threat randomised? | **No — fully deterministic, no seed role** (THR-A2). Randomness here buys nothing (the engine already rolls hit/crit/damage) and costs replay equality plus a fifth seed role. COMB_001 Q8's role set is unchanged by this doc. |
| **THR-Q6** | Encounter-local or persistent across encounters? | **Encounter-local** (THR-A3). Durable bilateral sentiment already has an owner — ACT_001 `actor_actor_opinion`. Two homes for "who dislikes whom" is the drift `_boundaries/` exists to prevent; the cross-encounter hook is THR-D1 and reads *from* ACT_001, never writes a second copy. |
| **THR-Q7** | Where is anti-grief enforced — selection or accrual? | **Accrual** (THR-A6, §7). Guarding at selection leaves the protection one driver-bug away; refusing the *write* means no code path can target a protected actor, including a hallucinating LLM handed a stale candidate list. |
| **THR-Q8** | Does COMB_003 own out-of-combat aggro? | **No — COMB_005 does** (§8). Aggro radius needs spawn groups, AOI and the encounter trigger; all are population concerns. COMB_003 spans exactly `CombatSessionBorn` → `CombatSessionResolved`. |

---

## §11 — Failure-mode UX (`threat.*` namespace)

| Reject rule | Stage | User-facing message (I18nBundle `default`) | When |
|---|---|---|---|
| `threat.target_ineligible` | 2 validate | "You cannot attack them." | target fails §7 (same side, KO'd, fled, safe-zone-protected, neutral civilian) |
| `threat.target_out_of_candidates` | 2 validate | (ops-level; canon-drift flag) | LlmDriver returned a target outside the top-K list (§6.2) → fallback to candidate 1 |
| `threat.selector_unknown` | 0 schema | (schema-level) | a `combat_reaction_table` entry names a selector outside the closed enum |
| `threat.no_eligible_target` | 2 validate | "There is no one left to fight." | every selector resolves empty → driver falls back to `Defend` |
| `threat.config_invalid` | 0 schema | (schema-level) | `decay_milli > 1000` (threat would grow on decay), `threat_candidate_k` outside 1..=5, or any factor negative |
| `threat.modify_scope_invalid` | 0 schema | (schema-level) | `ModifyThreat` declared with `SingleTarget` scope on an ability whose `TargetRule` is `SelfOnly` |

Per RES_001 §2, every `threat.*` reject carries `RejectReason.user_message: I18nBundle` with an English
`default` plus a Vietnamese translation from day one.

**Player-visible data contract (UI is THR-D6):** a PC sees a binary *"targeting you"* marker per hostile
and the relative ordering **within their own party** (so a tank can tell they hold the line). A PC sees
**no** numeric threat and **no** hostile ordering detail. The LLM sees §6.2's list and nothing more.

---

## §12 — Validators

| ID | Stage | Check |
|---|---|---|
| **THR-V1** | 0 schema | `ThreatConfig` sane: `decay_milli ≤ 1000`; `threat_candidate_k ∈ 1..=5`; all factors ≥ 0; `threat_max > 0` |
| **THR-V2** | 0 schema | every `TargetSelector` named by an AIT_001 `combat_reaction_table` entry is in the closed enum, and `LowestHpPctFriendly` is only used by an actor whose side can contain allies |
| **THR-V3** | 0 schema | **warn** (non-blocking): any `ModifyThreat.delta_pct` ≤ `switch_margin_pct_melee` — the taunt cannot clear its own hysteresis margin and will be inert (§4.2) |
| **THR-V4** | runtime | **accrual guard is non-bypassable**: no `threat_table` entry exists for a pair failing `threat_eligible` (§7) |
| **THR-V5** | runtime | selection totality: every selector over a non-empty eligible set returns exactly one `ActorRef`; ties resolve by `actor_index` |
| **THR-V6** | replay | same encounter + same actions ⇒ byte-identical `threat_table` and identical target choices at every round (THR-A2) |
| **THR-V7** | runtime | no `threat_table` entry has `observer == target` (§3); and every accrual reads `damage_applied` / `healing_applied`, never a rolled figure (overkill rule) |

> **THR-V4 and THR-V6 are the non-vacuous pair.** THR-V4 can fail: moving the safety check from `accrue()`
> to the selector — the natural refactor, since that is where it is "used" — lets threat accumulate toward
> a safe-zone bystander, and the first driver that reads the table raw targets them. Its bite-test is that
> exact move, and the check must reject. THR-V6 can fail: swapping the `BTreeMap` for a `HashMap` makes
> tie-broken selection depend on hash order and replay diverges on the first tie. Neither check is
> structurally guaranteed — both assert something a plausible implementation gets wrong.

---

## §13 — Acceptance criteria (AC-THR-1..12)

1. **Damage drives targeting** — two party members attack one bandit; the one dealing more cumulative
   damage becomes and remains its target.
2. **Healer accrual** — a healer who never attacks accrues threat via `heal_factor` and becomes a target
   once their contribution exceeds the incumbent by the switch margin.
3. **Taunt works** — `ModifyThreat { delta_pct: 130, SingleTarget }` pulls the enemy onto the caster in the
   **same** round, clearing the 110 melee margin by construction (§4.2).
4. **Inert-taunt warning (bite test)** — a manifest with `switch_margin_pct_melee: 200` and a 130 taunt
   trips THR-V3 at schema stage; the author is told before play, not after.
5. **Hysteresis prevents flicker** — two actors whose threats stay within 10% of each other cause **zero**
   target switches across 10 rounds.
6. **Forced re-pick** — when the current target is KO'd, the margin does not apply; the observer re-picks
   the same round and the KO'd actor's rows are gone (§7).
7. **Decay** — after 10 rounds with no new accrual, a 1000-threat entry reads exactly
   `floor(1000 × 0.95^10)` under truncating integer division at each step — no float drift.
8. **Safe-zone guard (bite test)** — a bystander protected by PF_001 `combat_safety` has **no**
   `threat_table` entry at all; relocating the guard from accrual to selection makes THR-V4 fail.
9. **LLM bounded to K** — an LlmDriver handed 3 candidates that returns a 4th actor is rejected with a
   canon-drift flag and falls back to candidate 1, keeping its chosen action (§6.2).
10. **No numbers leak** — the candidate list payload contains ranked names + vague tiers and **no**
    `ThreatValue`, HP number or stat slot (THR-A4 / DF7-A10).
11. **Untracked parity** — a 12-bandit `EngineDriver` group facing a 4-person party holds exactly **4**
    threat rows (one observer × 4 targets), not 48, and targets by `HighestThreat` (§6.1).
12. **Replay equality (bite test)** — the same encounter replays to byte-identical tables and target
    choices; swapping the `BTreeMap` for a `HashMap` trips THR-V6 on the first tie.

---

## §14 — Edge cases (resolved 2026-07-26)

An adversarial pass over §3–§7. Each row was **unanswered** by the first draft; the resolution is now
normative. Cases 1–4 were live defects, not merely gaps.

| # | Case | Resolution |
|---|---|---|
| 1 | **Overkill inflates threat** — a 400-damage blow on a 12-HP target banking 400 threat with its allies | accrual reads `damage_applied`, not `damage_rolled` (§3). Same for overhealing. THR-V7 |
| 2 | **Opening taunt is inert** — `current_top = 0` at round 0 makes `0 × delta_pct = 0` | `taunt_floor` (default 500) is the floor the percentage applies to (§3 rule 2) |
| 3 | **Taunt lowers threat** — a caster already far above the runner-up is *cut* by a 110 taunt | `max(…)` wrapper: a taunt can only raise (§3 rule 3) |
| 4 | **Self-threat** — a self-heal accrues `(actor, actor)`; `HighestThreat` returns "attack yourself" | refused at `accrue()`, not filtered at selection (§3). THR-V7 |
| 5 | **Decay empties the table while `current_target` is set** (a stand-off) | `current_target` survives an empty table; cleared only by ineligibility, never by decay (§4.1) |
| 6 | **Hysteresis vs non-threat selectors** — a finisher refusing to switch to a dying enemy | hysteresis applies to `HighestThreat` only (§5.1) |
| 7 | **`CurrentTarget` vs hysteresis** — apparent redundancy | soft vs hard stickiness; not in conflict (§5.1) |
| 8 | **Untracked group row count** — first draft claimed "one row"; a group facing 4 targets holds 4 | one observer × T targets (§6.1). AC-THR-11 corrected |
| 9 | **`AllHostiles` ability threat** — one ability hitting 4 enemies | accrues independently with each, from each one's `damage_applied`. No special case; falls out of §3 |
| 10 | **`Defend` generates no threat** | correct and deliberate — defending is not a provocation. A reality wanting "taunt by defending" declares a `ModifyThreat` ability instead (THR-D2 territory) |
| 11 | **Faction defection mid-encounter** (COMB-D6, V1+) | out of scope V1, but recorded: on a side change the defector's rows are **dropped**, not transposed — inherited threat across an allegiance flip has no coherent meaning |
| 12 | **Both `SingleTarget` taunt and `SelfOnly` fade in one ability** | legal; ops execute in declared order (ABL §4.1), so the later one wins on any overlapping pair. Author-visible, no engine rule needed |

## §14.1 — Open questions resolved (were THR-QO1/QO2)

**THR-QO1 — how healer threat splits. RESOLVED: across the healed actor's *current attackers*, not all
enemies.** The first draft chose "all enemies" for simplicity. It is wrong in the case that matters: in a
fight where 5 of 6 enemies are locked on the tank, splitting a heal across all 6 gives each a
sixth-of-a-heal, so no single enemy ever accumulates enough to switch — the healer becomes **unaggroable**
by construction, and the tank's job stops being a job. Splitting across *actual attackers of the healed
actor* concentrates the threat where the heal actually mattered, which is both the intuitive reading
("you undid **my** work") and the one that makes healer positioning a real decision. Cost: the attacker
set is `threat_table` data the engine already holds. If the healed actor has **no** current attackers
(a pre-emptive top-up), the heal accrues **nothing** — correct, since it undid nothing.

**THR-QO2 — should the switch margin scale with encounter size? RESOLVED: no.** The concern was that a
6-enemy fight produces more switching than a 2-enemy one at the same margin. It does — and that is the
correct behaviour, not a defect: more enemies means more independent observers, each making its own
decision, and a crowded fight *should* feel more chaotic than a duel. Scaling the margin by participant
count would make each individual enemy stickier precisely when the player most needs to be able to pull
one off an ally, and it would make the margin — a per-observer property — depend on global state, which
breaks the per-observer locality that makes §4.2 cheap and inspectable. **Closed as won't-fix**; the
existing melee/ranged asymmetry already provides the tuning surface.

## §14.2 — Deferred (THR-D1..D8)

See the §1 "V1 NOT shipping" table — each row is the corresponding `THR-D*`. **No open questions remain.**

## §15 — Cross-references

- Audit finding — [`12_module_coverage_audit.md`](../../12_module_coverage_audit.md) AUD-F9
- Encounter host + sides + Q4/Q6 — [`COMB_001`](COMB_001_combat_foundation.md) §2, §6
- Stance vocabulary this feeds — [`COMB_002`](COMB_002_tactical_grid.md) TG-A4, §5
- `ModifyThreat` op — [`ABL_001`](../19_ability/ABL_001_ability_foundation.md) §4.1
- Encounter formation + out-of-combat aggro — [`COMB_005`](COMB_005_encounter_spawning.md)
- Visibility discipline — [`DF07_001`](../DF/DF07_pc_stats/DF07_001_actor_stat_block.md) A10
- Durable sentiment (deliberately not duplicated here) — [`ACT_001`](../00_actor/ACT_001_actor_foundation.md) `actor_actor_opinion`
- Driver model — [`11_agent_decision_standard.md`](../../11_agent_decision_standard.md) AGT-A2/A3
