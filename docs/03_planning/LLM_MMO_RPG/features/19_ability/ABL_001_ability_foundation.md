# ABL_001 — Ability Foundation

> **Conversational name:** "Ability" (ABL). The catalogue of **activatable effects** — what COMB_001 §3's
> `Skill { skill_id, target? }` actually refers to, what it costs, how far it reaches, how it is acquired,
> and the closed vocabulary of what it is permitted to do.
>
> **Category:** ABL — Abilities (19_ability)
> **Status:** **DRAFT 2026-07-26**. Resolves **AUD-F10** ([`../../12_module_coverage_audit.md`](../../12_module_coverage_audit.md))
> — *"no doc defines what a skill is, how it's acquired, or its cost model."*
> **ABL-Q1..Q9 LOCKED** in this pass; `ABL-A1..A7` axioms codified.
> **Stable IDs in this file:** `ABL-A*` axioms · `ABL-Q*` decisions · `ABL-D*` deferrals · `ABL-V*`
> validators · `AC-ABL-*` acceptance criteria. Owns the `ability.*` reject namespace.
> **Builds on:** [COMB_001](../18_combat/COMB_001_combat_foundation.md) §3 action set + §4 damage law-chain
> + §2 `combat_session` · [COMB_002](../18_combat/COMB_002_tactical_grid.md) TG-A1 (LLM-zero-space) + §5
> range/LoS · [DF07_001](../DF/DF07_pc_stats/DF07_001_actor_stat_block.md) §3 stat slots + §8 combat
> snapshot · [PROG_001](../00_progression/PROG_001_progression_foundation.md) §3 `actor_progression` +
> `ProgressionType` · [RES_001](../00_resource/RES_001_resource_foundation.md) §4.1 `vital_pool` ·
> [PL_006](../04_play_loop/PL_006_status_effects.md) `StatusFlag` ·
> [11 AGT](../../11_agent_decision_standard.md) A2 bounded vocab.
> **Coordinates with — does not depend on — [PL_007](../04_play_loop/PL_007_item.md) §7.1 `UseEffectDecl`.**
> PL_007 (parallel track) has **no ability concept**: its items declare `UseEffectDecl`, and its `EquipDecl`
> carries stat modifiers, not abilities. The unification is **proposed** in §4.2 / ABL-Q9 and requires that
> doc's owner; every item-granted-ability reference below is marked as proposal, not as existing schema.
> **Defers to:** [COMB_003](../18_combat/COMB_003_threat_and_targeting.md) for the threat model the
> `ModifyThreat` op writes into.
> **i18n compliance:** conforms to RES_001 §2 — stable IDs English `snake_case`/`PascalCase`; user-facing
> strings `I18nBundle`.

---

## §1 — Purpose & V1 minimum scope

### Why this feature exists

Three locked surfaces reference an ability by an ID that **nothing defines**:

| Consumer | References | Defined where before this doc |
|---|---|---|
| COMB_001 §3 | `Skill { skill_id, target? }` — *"PROG_001 skill; stamina cost; range/LoS per skill"* | nowhere — `SkillId` has no declaring type |
| COMB_002 §5 | `skill.range` tiles | nowhere |
| COMB_001 §7 | rejects `combat.skill_unknown`, `combat.skill_insufficient_stamina` | the rejects exist; the thing they reject against does not |
| PL_005 `Use` out of combat | firing a technique outside an encounter | nowhere |

The concept notes ([`../18_combat/00_CONCEPT_NOTES.md`](../18_combat/00_CONCEPT_NOTES.md) §6) papered over
this with *"V1 skills come from PROG_001 skill kinds"*. They cannot, and §2 explains why that sentence is a
category error rather than a shortcut. This doc supplies the missing declaring type.

### V1 minimum scope

- **0 new aggregates** (ABL-A4). The known-ability set is *derived* from `actor_progression` + equipment;
  cooldown state is a field inside COMB_001's already-ephemeral `combat_session`.
- **`AbilityDecl`** — a RealityManifest extension (§3), OPTIONAL; a reality with no abilities plays.
- **Closed `EffectOp` dispatch vocabulary — 9 V1** (§4), a strict superset of PL_007 §7.1's
  `UseEffectDecl`, every variant routing into an aggregate someone else already owns.
- **`PowerTerm`** (§4.3) — the mechanism by which an offensive ability changes damage **without ever
  emitting a damage number**, preserving COMB_001 §4's 4-step chain as the sole damage authority.
- **Closed `TargetRule` set — 6 V1** (§5), resolved by the engine under COMB_002's Chebyshev range +
  corner-line LoS. The LLM never emits a tile or a distance (TG-A1).
- **Derived acquisition** (§6) — `requires: Vec<ProgressionReq>` against PROG_001, plus item grants.
- **Cost + cooldown model** (§7) against existing RES_001 vitals.
- **12 V1 rule_ids** in the `ability.*` namespace + **7 validators** ABL-V1..V7 + **AC-ABL-1..13**.

### V1 NOT shipping

| Feature | Defer to | Why |
|---|---|---|
| AoE shapes (blast / cone / line) | V1+ (ABL-D1) | COMB_002 §11 already defers AoE; V1 `TargetRule` is single-target + self |
| Channelled / multi-round abilities | V1+ (ABL-D2) | needs an interrupt model; COMB_001's round loop is one-action-per-turn |
| Reaction / counter abilities | V1+ (ABL-D3) | COMB_002 §11 defers retaliation; a reaction fires outside the initiative pop |
| Ability trees / explicit unlock spend | V1+30d (ABL-D4) | V1 acquisition is a *derived* threshold (§6); a tree needs a spend aggregate |
| Out-of-combat cooldowns | V1+ (ABL-D5) | would need a durable per-actor cooldown table; V1 out-of-combat gating is cost-only (ABL-A7) |
| Ability ranks / scaling levels per ability | V1+ (ABL-D6) | `PowerTerm` already scales continuously off a progression kind — ranks are a second curve, the DF7-Q10 trap |
| Summon / pet abilities | V2+ (ABL-D7) | needs an actor-spawn path inside combat; COMB_005 owns spawning and defers mid-encounter summons |
| Elemental typing on abilities | V1+ (ABL-D8) | COMB_001 §4 pins `elem_mult = 1.0`; lands with DF7-D2's `ElemPower`/`Resist` slots |
| Cast time / initiative-cost variance per ability | V1+ (ABL-D9) | COMB_001 Q7 AV is locked at `10000/speed`; per-ability AV is a balance-visible change |
| Ability-specific animation / VFX binding | client-build track (ABL-D10) | §9 defines the data; pixels are not this track |
| Player-authored / LLM-authored abilities | **never** (ABL-D11) | ABL-A2 — an LLM-authored effect program is arbitrary code inside the determinism envelope |

---

## §2 — The vocabulary fix (ABL-A1)

> **ABL-A1 — An Ability is not a progression kind.** `AbilityId` and `ProgressionKindId` are different
> types naming different things. A **progression kind** is a number that grows (`swordsmanship: 8`,
> PROG_001 `ProgressionType::Skill`). An **Ability** is an effect you fire (`rising_dragon_cut`).
> Progression **gates and scales** abilities; it never *is* one.

| | Progression kind (PROG_001) | Ability (ABL_001) |
|---|---|---|
| Shape | a growing integer on `actor_progression` | a declared effect program in the manifest |
| Player verb | trains it | fires it |
| Storage | `actor_progression` row (SSOT) | none — derived set (ABL-A4) |
| Example | `swordsmanship`, `qi_cultivation` | `rising_dragon_cut`, `minor_mending` |
| Relationship | **input** to `requires` (gate) and `PowerTerm` (scale) | **consumer** of one or more kinds |

**Why the concept-notes sentence had to go.** *"V1 skills come from PROG_001 skill kinds"* implies
`Skill { skill_id }` takes a `ProgressionKindId` — so firing `swordsmanship` would be a legal combat
action, with no declared cost, no range, no target rule and no effect. Every downstream reject
(`combat.skill_unknown`, `combat.skill_insufficient_stamina`) would have nothing to check against. The
one-word overlap is the whole bug; naming this module **Ability** is the fix.

**COMB_001 keeps the verb name `Skill`** — it is player-facing, already locked, and renaming it would
churn PL_005, AGT tool vocab and the concept notes for no mechanical gain. The verb `Skill` takes an
`AbilityId`. Recorded as closure item 1 (§10).

---

## §3 — `AbilityDecl` (RealityManifest extension)

```rust
pub struct RealityManifest {
    // ... PROG_001 / RES_001 / COMB_001 / DF07 / PL_007 / … existing fields ...

    /// Author-declared ability catalogue. Absent ⇒ the reality has no abilities (valid; ABL-Q8).
    pub abilities: Vec<AbilityDecl>,
}

pub struct AbilityDecl {
    pub ability_id: AbilityId,                   // author snake_case, unique per reality
    pub display_name: I18nBundle,
    pub description: I18nBundle,

    // --- who may fire it (§6) ---
    pub requires: Vec<ProgressionReq>,           // ALL must hold; empty ⇒ innate, everyone has it
    pub grant_only: bool,                        // true ⇒ never derived from `requires`; granted explicitly
                                                 //   (V1: an AIT_001 archetype list, §6; V1+: item grants
                                                 //    once ABL-Q9's `grants_ability` proposal is agreed)

    // --- what it costs (§7) ---
    pub costs: Vec<AbilityCost>,                 // RES_001 vitals; empty ⇒ free
    pub cooldown_rounds: u8,                     // 0 ⇒ no cooldown; encounter-ephemeral (ABL-A7)

    // --- where it reaches (§5) ---
    pub target_rule: TargetRule,                 // closed enum, 6 V1
    pub range: u8,                               // Chebyshev tiles; 0 ⇒ self/adjacent-free
    pub requires_los: bool,                      // corner-line LoS per COMB_002 §5

    // --- what it does (§4) ---
    pub effects: Vec<EffectOp>,                  // executed in declared order; 1..=4 V1 (ABL-V1)

    // --- context gates ---
    pub usable_in_combat: bool,
    pub usable_out_of_combat: bool,

    pub tags: Vec<AbilityTag>,                   // author-open; UI filtering, V1+ crafting/quest hooks
}

pub struct ProgressionReq { pub kind_id: ProgressionKindId, pub min_raw_value: i64 }

pub struct AbilityCost { pub vital: VitalKind, pub amount: u32 }   // RES_001 §4.1
```

**`ability_id` is author-open; `EffectOp`, `TargetRule` and `VitalKind` are engine-closed.** Identical
discipline to DF7-A1 (closed `StatSlot`, open `progression_kinds`) and ITM-A1/PL_007 §7.1 (closed
`UseEffectDecl`, open `ItemDefId`). A tu tiên reality declares `thanh_long_kiem_quyet`; a modern reality
declares `first_aid`; the engine knows neither and executes both through the same nine ops.

---

## §4 — What an ability may do

### §4.1 `EffectOp` — closed dispatch vocabulary, 9 V1

> **ABL-A2 — Abilities are declared programs over a closed dispatch vocabulary, never scripts.** Every
> `EffectOp` variant routes into an aggregate **already owned by another feature**. ABL adds no new effect
> substrate — it is a dispatch table, which is exactly what keeps it bounded for AGT-A2 and inspectable
> for balance. There is no expression language, no conditional, no loop, and **no LLM-authored effect**
> (ABL-D11): an author-declared program is reviewable and replay-stable; a generated one is arbitrary code
> inside the determinism envelope.

```rust
pub enum EffectOp {
    // ── shared with PL_007 §7.1 UseEffectDecl (identical semantics; see §4.2) ──
    VitalDelta    { vital: VitalKind, amount: i32 },        // → RES_001 §7.5   heal / drain
    StatusApply   { flag: StatusFlag, magnitude: u8, duration_rounds: u8 },  // → PL_006
    StatusDispel  { flag: StatusFlag },                     // → PL_006
    ResourceGrant { kind: ResourceKind, amount: u64 },      // → RES_001 resource_inventory
    Reveal        { canon_ref: CanonRef },                  // → Oracle / knowledge-service
    Inert,                                                  // flavour only; narration, no delta

    // ── combat-only, ABL-owned ──
    Damage        { power: PowerTerm },                     // → COMB_001 §4 law-chain  (§4.3)
    ModifyThreat  { delta_pct: i16, scope: ThreatScope },   // → COMB_003 threat_table
    ForceMove     { kind: ForceMoveKind, tiles: u8 },       // → COMB_002 engine pathing (§5.3)
}
```

- **Ops execute in declared order**, each fully resolved before the next. Order is author-visible and
  matters (`StatusApply{Wounded}` then `Damage` is not the same as the reverse) — but the **COMB_001
  invariant that status applies AFTER damage** still binds *within* a single `Damage` op's resolution
  (§4.3). An author may not use op ordering to slip a pre-damage status onto the same blow.

**Four resolution rules the op list needs** (each was ambiguous in the first draft, and each has a wrong
answer that a reasonable implementer would pick):

| Question | Rule | Why the alternative is wrong |
|---|---|---|
| **One hit roll per ability, or per `Damage` op?** | **One roll per (ability, target) pair**, taken before the op list runs. A miss skips **every** `Damage` op against that target but still runs non-damage ops (a shout that debuffs and cuts still debuffs on a miss, if the author declared it that way) | Per-op rolls make a 3-`Damage` ability statistically *more reliable* than a 1-`Damage` one at the same accuracy — partial hits — which no player would predict from the description |
| **`AllHostiles` — one roll or one per target?** | **One roll per target.** Each target is an independent hit/crit resolution against its own `Dodge` and the attacker's `Accuracy` | A single shared roll makes one unlucky number miss an entire room, and makes high-`Dodge` targets protect low-`Dodge` ones |
| **An op kills its target mid-list** | remaining ops against that target are **skipped**; ops against *other* targets continue. The kill is resolved once, at the op that caused it | Continuing lets a corpse be debuffed, and (with COMB_003's overkill rule) the skipped damage correctly accrues no threat |
| **An op kills the *caster*** (self-damage, §4.3 note) | the op list **halts immediately**; already-resolved ops stand | Letting a dead caster finish channelling a heal is the kind of ordering artefact that survives into shipped games |
- **1..=4 ops per ability V1** (ABL-V1). The cap is deliberate: it bounds narration payload size and keeps
  the Lex severity estimate (WA_001) single-pass, the same reasoning PL_007 §7.1 used for its one-effect
  rule.
- **`amount` / `magnitude` come from the declaration, never from a payload** — inherited verbatim from
  ITM-A4. An `AbilityId` plus an optional target is the *entire* LLM-emittable surface.

### §4.2 Relationship to PL_007 `UseEffectDecl` (coordination — needs PL_007 sign-off)

PL_007 §7.1 defines `UseEffectDecl`, a closed 7-variant dispatch enum for item `Use`. Six of its variants
are **semantically identical** to `EffectOp` variants above; the seventh (`Unlock { key_tag }`) is
item-specific and stays PL_007's.

Two closed enums covering overlapping ground is precisely the drift `_boundaries/` exists to catch, so the
resolution is recorded rather than left implicit:

- **V1 (this DRAFT):** the two coexist. `EffectOp` is a strict superset for the six shared variants; both
  dispatch to the same owner aggregates, so a heal is a heal regardless of entry point. `Unlock` remains
  PL_007-only; `Damage` / `ModifyThreat` / `ForceMove` remain ABL-only.
- **Proposed (needs PL_007 owner agreement, ABL-Q9):** PL_007 §7.1 re-expresses `UseEffectDecl` as
  `pub type UseEffectDecl = EffectOp;` restricted by an item-context validator, plus `Unlock` folded in as
  a tenth `EffectOp`. One substrate, one validator set, `Use potion` and `Skill heal` provably identical.
- **Not proposed:** ABL absorbing PL_007's item semantics, or PL_007 absorbing combat ops. Each keeps its
  entry-point legality rules; only the *effect vocabulary* merges.

This is flagged as a **coordination item, not a unilateral change** — §10 closure item 5. Until it is
agreed, an author declaring a heal twice (once as an item use-effect, once as an ability) gets two
declarations with identical runtime behaviour, which is redundant but not incorrect.

### §4.3 `PowerTerm` — damage without a damage number (ABL-A3)

> **ABL-A3 — An ability never emits damage; it substitutes into the law-chain.** COMB_001 §4's 4-step
> chain is the **sole** damage authority. `Damage { power }` supplies a replacement for the chain's
> `atk.strike_power` input; steps 2–4 (element, resist, roll × crit) and the status-after-damage rule run
> **unchanged**. An ability that could emit a final number would undo the `damage_amount` removal COMB_001
> already made (its own DRAFT closure item 2) through the back door.

```rust
pub struct PowerTerm {
    pub slot: StatSlot,          // DF07 §3 — usually StrikePower; read from the combat snapshot (DF07 §8.1)
    pub mult_milli: u32,         // ×1000 fixed point; 1000 = 100% of the slot
    pub flat: i32,               // added after the multiply, before the chain
    pub scale: Option<ScaleTerm>,// optional progression scaling
}

pub struct ScaleTerm { pub kind_id: ProgressionKindId, pub weight_milli: u32 }

// resolution — i64 milli-units throughout, exactly one floor, per DF7-A4; saturating (DF07_002 EC-4)
effective_strike_power =
    floor( ( sat_mul(snapshot.stats[slot], mult_milli)
           + scale.map(|s| sat_mul(snapshot.prog[s.kind_id], s.weight_milli)).unwrap_or(0) ) / 1000 )
    + flat
// → substituted for `atk.strike_power` in COMB_001 §4 step 1; steps 2..4 unchanged.
```

> **⚠ CORRECTED 2026-07-26 (`/review-impl` seam pass — DF07_002 §1.5 HIGH-2).** `scale` previously read
> `prog[kind_id].raw_value` **live**, while every other law-chain input came from the DF07 combat snapshot.
> PROG_001's `Action` training trigger fires *during* combat — striking trains swordsmanship — so an
> ability's damage drifted mid-encounter while a basic `Strike`'s stayed frozen, contradicting AC-COMB-15
> and breaking AC-COMB-16's byte-identical replay. Worse, **DF7-V4 could not catch it**: the epoch assertion
> guards the stat block, and a direct progression read goes around the block entirely, so the one check
> designed for this failure class was blind to it. **Fix:** the DF07 combat snapshot is extended to carry
> the progression values any declared `PowerTerm.scale` references — `snapshot.prog`, captured at
> `CombatSessionBorn` and refreshed on the same `progression_turn` epoch as the block (DF07 §8.2), so
> scaling and slots move together or not at all. The referenced `kind_id` set is known at schema stage
> (ABL-V3 already validates it), so the capture is bounded and needs no extra lookup at cast time.

- **Fixed-point, no floats, saturating** — the whole path inherits DF7-A4, so DF7-V4's replay assertion
  stays meaningful across abilities. `sat_mul` matters here for the same reason it does in DF07 §4: a
  PROG_001 kind may be declared `Unbounded`, and `raw_value × weight_milli` overflows i64 milli-units
  without it — a debug panic mid-resolution, or a release wrap that silently inverts a cultivator's damage.
- **`Heal` is not a `Damage` with a negative sign.** Healing is `VitalDelta { amount: +n }` and does *not*
  pass through the damage chain — armour, crit and the hit roll are meaningless for a heal, and routing it
  through the chain would make `Armor` reduce healing. Stated because it is the obvious wrong shortcut.
- **A pure-utility ability declares no `Damage` op** and never touches the chain.

**Worked example.** `rising_dragon_cut`: `PowerTerm { slot: StrikePower, mult_milli: 1800, flat: 0,
scale: Some(swordsmanship × 200‰) }`. An actor with snapshot `StrikePower` 24 and `swordsmanship` 8 gets
`floor((24×1800 + 8×200)/1000) = floor(44.8) = 44` effective strike power, which then enters COMB_001 §4
step 1 against the defender's `Armor` — hit roll, crit and variance all applied by the engine exactly as
for a basic `Strike`.

---

## §5 — Targeting, range and movement

### §5.1 `TargetRule` — closed, 6 V1

```rust
pub enum TargetRule {
    SelfOnly,
    OneHostile,
    OneFriendly,
    OneAny,
    AllFriendlies,      // side-wide; no tile geometry (a "rally" / party heal)
    AllHostiles,        // side-wide; still gated by range + LoS per target (§5.2)
    // V1+ (ABL-D1): Blast { radius }, Cone { arc, length }, Line { length }, GroundTile
}
```

`AllFriendlies` / `AllHostiles` are **side-scoped, not shape-scoped** — they need no AoE geometry, which is
why they ship in V1 while `Blast`/`Cone`/`Line` wait for COMB_002 §11's AoE work.

### §5.2 Range and line-of-sight (engine-owned; TG-A1)

`AbilityDecl.range` is in **Chebyshev tiles** and `requires_los` selects COMB_002 §5's corner-to-corner
check. This is where `skill.range` — referenced by COMB_002 §5 and previously undefined — resolves.

- `range = 0` ⇒ self / no positional requirement.
- `range = 1` ⇒ melee-equivalent adjacency (including diagonals).
- Per-target evaluation for `AllHostiles`: each target is independently range- and LoS-checked; those that
  fail are silently excluded, not rejected. An area-denial ability that clips two of four enemies is a
  positioning outcome, not a player error — rejecting the whole action would make it unusable.
- **The LLM emits neither tiles nor distances** (TG-A1). It emits `{ ability_id, target }`; the engine
  computes everything spatial. Token cost is flat regardless of grid size.

### §5.3 `ForceMove`

```rust
pub enum ForceMoveKind { PushFromCaster, PullToCaster, SwapWithTarget }
```

Engine-resolved along the Chebyshev line between caster and target, stopping at the first Obstacle or
Occupied tile (COMB_002 §4 rules unchanged). Deterministic; no pathfinding search, so no tie-break needed.
It does **not** consume the target's own movement budget — a forced move is not a turn action — and it
cannot push an actor off the grid (it clamps at the boundary, `ability.force_move_blocked` is *not* raised;
partial displacement is the correct outcome).

**Degenerate cases, locked:**
- **`ForceMove` with `TargetRule::SelfOnly`** — `PushFromCaster` / `PullToCaster` have no defined direction
  when caster and target coincide, and `SwapWithTarget` would swap an actor with itself. **Rejected at
  schema stage** (`ability.force_move_self_invalid`, ABL-V1). A self-displacement ability (a dash, a
  blink) is a *different* op and is V1+ — it needs a destination model, not a direction.
- **`SwapWithTarget` across any distance** — legal within `range`; both tiles are by definition occupied
  and walkable, so no obstacle check applies. It is the one `ForceMoveKind` that cannot be partially
  applied: it either happens or it does not.
- **Zero displacement** — a push against an adjacent wall moves 0 tiles. This is a **success**, not a
  failure: the ability resolved, the cost is paid, nothing moved. Reporting it as a rejection would refund
  a resource for an action the fiction says happened.

---

## §6 — Acquisition (ABL-A4)

> **ABL-A4 — The known-ability set is derived, never stored.** No `known_abilities` aggregate,
> no unlock ledger. Mirrors DF7-A2 exactly: a derived set cannot drift from its inputs, replay recomputes
> it for free, and MV12 time-travel needs no ability snapshot.

```pseudo
fn known_abilities(actor, reality) -> BTreeSet<AbilityId>:      // BTreeSet ⇒ order-stable (ABL-V7)
    // No progression row ⇒ NO derived abilities, innate included. Short-circuit, not a quantifier:
    // `∀ req ∈ []` is vacuously true, so an empty `requires` would otherwise admit an innate ability
    // to an Untracked actor that has no row to check (DF07_002 §1.5 MED-3). A missing kind_id inside a
    // non-empty `requires` reads as 0 — absent competence, not an error.
    derived = if actor_progression(actor).is_none() { ∅ } else {
              { a ∈ reality.abilities
                : !a.grant_only
                ∧ ∀ req ∈ a.requires : actor_progression[req.kind_id].raw_value ?? 0 ≥ req.min_raw_value } }
    granted = archetype_granted(actor)                             // AIT_001 archetype list (§8.2)
           // ∪ item_granted(actor)   ← V1+ ONLY, gated on ABL-Q9; PL_007 has no such field today
    return derived ∪ granted
```

> **On `granted`:** in V1 the only source is an AIT_001 archetype's declared list, which is what gives an
> untracked bandit its two abilities without a progression row. **Item-granted abilities do not exist in
> V1** — PL_007's `EquipDecl` carries stat modifiers, not abilities, and adding `grants_ability` to it is
> part of the ABL-Q9 proposal (§4.2). The union above is written to accept that source additively, so
> agreeing the proposal requires no change to this law.

- **`requires` empty ⇒ innate.** Every actor in the reality has it. This is how a reality ships a baseline
  `basic_mending` without a progression schema.
- **Threshold, not spend** (ABL-Q4). Crossing `swordsmanship ≥ 5` grants `rising_dragon_cut`
  automatically. There is no point-spend, no respec, and therefore no aggregate to keep consistent.
  Explicit trees are ABL-D4 — and would need a spend ledger, which is exactly the stored state this axiom
  avoids in V1.
- **Losing a requirement loses the ability.** If progression can decrease (PROG-D5 atrophy, V1+30d) or the
  granting item is unequipped, the ability leaves the set. Nothing to clean up, because nothing was stored.
- **Untracked NPCs** have no `actor_progression` row (DF7 §9), so their derived set is empty; their
  abilities come from the archetype's `grant_only` list. A 12-bandit mob resolves one archetype's ability
  set, not twelve.

---

## §7 — Costs and cooldowns

### §7.1 Costs

`costs: Vec<AbilityCost>` deducts from RES_001 `vital_pool` — V1 realistically `Stamina`, with `Mana` when
a reality declares it. **All costs are checked, then all are deducted, atomically**: a two-cost ability that
can pay one but not the other is rejected whole (`ability.insufficient_resource`), never partially charged.

Costs are paid **on successful resolution**, not on submission — the same ordering rule PL_007 §6 uses for
item consumption, and for the same reason: an ability rejected for range should not have already spent the
stamina. COMB_001's existing `combat.skill_insufficient_stamina` reject maps onto ABL-V4.

### §7.2 Cooldowns (ABL-A7)

> **ABL-A7 — Cooldown state is encounter-ephemeral.** `cooldown_rounds` is tracked in
> `combat_session.cooldowns: HashMap<(ActorRef, AbilityId), u8>`, decremented at each round boundary,
> and discarded when the session resolves. **Out of combat, V1 abilities have no cooldown** — gating is
> cost-only.

The alternative — a durable per-actor cooldown table keyed to fiction-time — needs a new aggregate, a TDIL
clock binding, and a decision about what happens across time-dilated chambers (TDIL_001) where two actors
experience different elapsed time. That is a real design problem and V1 does not need to solve it to have
combat abilities. Deferred as ABL-D5 with the reasoning recorded, so the V1 cut is a decision rather than
an oversight.

Consequence worth stating: an ability with `cooldown_rounds > 0` and `usable_out_of_combat = true` is
**spammable outside combat**, limited only by its cost. ABL-V2 warns on that combination at schema stage so
authors meet the constraint at declaration time rather than discovering it in play.

### §7.3 `duration_rounds` outside combat

`StatusApply { duration_rounds }` is measured in **combat rounds**, and outside an encounter there are no
rounds — so the field has no meaning on the out-of-combat path. Locked:

- **Out of combat, `duration_rounds` converts to fiction-time** at the reality's `round_fiction_seconds`
  (COMB_001 §12.1 already fixes a round's fiction duration — this reuses it rather than inventing a
  second conversion). PL_006 owns the resulting expiry exactly as it does for any other status.
- **A status applied out of combat and still active when combat starts** keeps its remaining fiction-time
  and is converted **back** to rounds at `CombatSessionBorn`. Round-tripping through one declared constant
  is lossy only by truncation, and truncation is toward the player's benefit on buffs and against them on
  debuffs — a deliberate, stated asymmetry rather than an accident.
- **`duration_rounds: 0`** means *"this round only"* in combat and is **rejected** out of combat
  (`ability.duration_meaningless`), because it converts to zero fiction-time — a status applied and
  expired in the same instant, which is a declaration error rather than a design.

The alternative — a second `duration_seconds` field — was rejected: two duration fields means every
consumer must decide which one applies, and the first one that guesses wrong ships a permanent debuff.

---

## §8 — Combat binding

### §8.1 The `Skill` verb

COMB_001 §3's `Skill { skill_id, target? }` resolves here. `skill_id: AbilityId` (§2). Resolution order:

```
1. known        — ability ∈ known_abilities(actor)             else ability.unknown
2. context      — usable_in_combat in CombatActive             else ability.wrong_context
3. cooldown     — cooldowns[(actor, id)] == 0                  else ability.on_cooldown
4. cost         — all costs affordable                          else ability.insufficient_resource
5. target       — TargetRule satisfied; range + LoS (COMB_002)  else ability.invalid_target / out_of_range / los_blocked
6. RESOLVE      — effects in declared order (§4.1)
7. pay          — deduct costs; set cooldown                    (only now — §7.1)
```

Steps 1–5 are **pure predicates over engine state**, which is what makes step 8.2's bounded tool-set
possible: the engine can compute the legal set before asking anyone to choose.

**Is the known-set snapshotted like stats? No — and the asymmetry is deliberate.** DF7 §8.1 snapshots the
*stat block* at `CombatSessionBorn` so that mid-encounter changes cannot retroactively alter how earlier
rounds should have resolved. The known-ability set is **evaluated live, each turn**. The two are treated
differently because the failure modes are opposite:

| | Snapshot | Live |
|---|---|---|
| **Stats** | ✅ a mid-round `StrikePower` change would make round 3's damage un-replayable against round 1's inputs | a live read is a replay hazard |
| **Abilities** | ❌ a snapshot means a COMB_004 progression award mid-fight grants an ability the actor **cannot use until the next encounter** | a live read is *correct* — the set only ever grows or shrinks at turn granularity, and each turn's legality is evaluated fresh anyway (steps 1–5) |

Nothing is lost: the ability *effect* still reads the snapshot (`PowerTerm.slot` resolves against
`stat_snapshots`, §4.3), so the numbers stay atomic per encounter. Only *which abilities are offered*
is live. Losing a requirement mid-fight (a debuff dropping a progression value below a threshold) likewise
removes the ability from the next turn's set, which is the behaviour a player would predict.

### §8.2 The agent boundary (AGT-A2 / COMB-A1)

> **ABL-A6 — The LLM chooses from a pre-filtered set it cannot extend.** The `Skill` entry in a combatant's
> `allowed_tools` enumerates only abilities passing steps 1–4 **right now**. The LLM picks an
> `ability_id` and a target from that set and emits nothing else — no cost, no damage, no tile, no range.

| Driver (AGT-A3) | Ability selection |
|---|---|
| **HumanDriver** (PC) | UI shows the same filtered set; unusable abilities render greyed with the failing predicate as the tooltip (that is what makes a cooldown legible) |
| **LlmDriver** (Major NPC) | receives the filtered set in `available_actions` (concept §9.1); an out-of-set `ability_id` is a canon-drift flag → **fallback `Defend`**, per COMB_001 §1 |
| **ScriptDriver** (Minor NPC) | `combat_reaction_table` entries name an `AbilityId`; an entry naming an ability the actor cannot know is a **schema-stage** reject (ABL-V5), not a runtime surprise |
| **EngineDriver** (Untracked) | archetype's `grant_only` list; highest-`PowerTerm` affordable ability, deterministic tie-break by `ability_id` |

Token cost is flat in the number of abilities the actor can *currently* use — typically 2–6 — not in the
size of the catalogue. This is the same argument TG-A1 made for space, applied to the ability surface.

### §8.3 Narration (Layer 3)

The `ResolutionResult` batch handed to the narration LLM carries `{ ability display_name, target, per-op
outcomes }` — never `PowerTerm`, never `mult_milli`, never an opponent's raw slot values (DF7-A10). An
ability's `description` is prose the author wrote; the narrator may use it as flavour context but the
**numbers in the prose must match the ResolutionResult** or the A6 canon-drift detector fires, exactly as
COMB_001 §8 AC-10 requires for basic strikes.

---

## §9 — Decisions (ABL-Q1..Q9 — LOCKED 2026-07-26)

| # | Question | Resolution & reasoning |
|---|---|---|
| **ABL-Q1** | Is a combat `Skill` the same thing as a PROG_001 `ProgressionType::Skill`? | **No — different types, different verbs** (ABL-A1, §2). A progression kind is a number that grows; an ability is an effect you fire. The concept-notes conflation left `skill_id` with no declaring type and every `combat.skill_*` reject with nothing to check. Progression gates and scales; it never *is* the ability. |
| **ABL-Q2** | New namespace, or fold into COMB / PROG? | **New namespace `19_ability`.** Two V1 callers already span it — COMB_001's `Skill` verb and PL_005's out-of-combat `Use` — so folding it into `18_combat` would make out-of-combat ability use depend on the combat feature. Folding it into PROG_001 would put an *activatable effect* inside a doc that deliberately owns only *competence values* (PROG_001 §1: no level, no power rating). Same reasoning that gave DF07 its own home rather than extending PROG_001. *(A third caller — item-granted abilities — is proposed, not existing; ABL-Q9.)* |
| **ABL-Q3** | Do abilities compute damage, or feed the law-chain? | **Feed it** (ABL-A3, §4.3). `PowerTerm` substitutes for `atk.strike_power`; steps 2–4 and status-after-damage are untouched. An ability emitting a final number would silently undo COMB_001's own `damage_amount` removal and give the game two damage authorities. |
| **ABL-Q4** | Threshold-derived acquisition or an explicit unlock spend? | **Threshold-derived** (ABL-A4, §6). Zero aggregates, replay-free, nothing to drift, and losing a requirement cleanly loses the ability. A spend model needs a ledger — the exact stored state DF7-A2 and this axiom both avoid. Trees are ABL-D4. |
| **ABL-Q5** | Open effect language or closed dispatch enum? | **Closed, 9 V1** (ABL-A2, §4.1). Every variant routes into an already-owned aggregate, so ABL invents no effect substrate. An expression language — or an LLM-authored one (ABL-D11) — puts arbitrary code inside the replay-asserted envelope. |
| **ABL-Q6** | Where does cooldown state live? | **`combat_session.cooldowns`, encounter-ephemeral** (ABL-A7, §7.2). A durable cooldown table needs a TDIL clock binding and an answer for time-dilated chambers — a real problem V1 need not solve. Out-of-combat gating is cost-only, and ABL-V2 warns authors who declare a cooldown they will not get. |
| **ABL-Q7** | Is healing a negative `Damage`? | **No** — `VitalDelta` bypasses the chain entirely (§4.3). Routing a heal through the damage chain would let `Armor` reduce it and the hit roll miss it. Recorded because it is the obvious and wrong shortcut. |
| **ABL-Q8** | A reality that declares no abilities? | **Fully valid.** `Skill` never enters `allowed_tools`; combat runs on `Strike` / `Defend` / `UseItem` / `Flee`. Mirrors DF7-A6, PL_007's item-free reality, and PROG_001 §11.3 composability. |
| **ABL-Q9** | `EffectOp` vs PL_007 `UseEffectDecl` — merge now? | **Coexist in V1; merge proposed, not imposed** (§4.2). PL_007 is authored in a parallel track; unilaterally rewriting its closed enum would be exactly the boundary violation `_boundaries/` forbids. The V1 overlap is redundant, not incorrect — both dispatch to the same owners. Merge is closure item 5, gated on PL_007 owner agreement. |

---

## §10 — Closure-pass-extensions

Applied as **dated additive notes**. Item 1 is applied at COMB_001's CANDIDATE-LOCK promotion in this same
cycle; 2–6 are declared and land when each feature is next opened.

| # | Target | Change | Status |
|---|---|---|---|
| 1 | **COMB_001 §3 / §7** | `Skill { skill_id }` typed as `AbilityId` (was undeclared); `combat.skill_unknown` / `combat.skill_insufficient_stamina` delegate to `ability.unknown` / `ability.insufficient_resource`; `combat_session` gains `cooldowns` | applied this cycle |
| 2 | **COMB_002 §5** | `skill.range` resolves to `AbilityDecl.range` (Chebyshev) + `requires_los` | declared |
| 3 | **COMB_003** | `ModifyThreat { delta_pct, scope }` is the taunt/threat-drop op; COMB_003 owns the table it writes | applied in COMB_003 this cycle |
| 4 | **PROG_001 §3** | `ProgressionReq` reads `actor_progression.values[kind_id].raw_value`; **no PROG_001 schema change** — a read-only consumer, plus the §2 disambiguation note | declared |
| 5 | **PL_007 §7.1** | `UseEffectDecl` ⊂ `EffectOp` merge proposal (§4.2, ABL-Q9) — **requires PL_007 owner agreement**, not applied unilaterally | proposed |
| 6 | **AIT_001** | Untracked actors' abilities come from the archetype `grant_only` list, resolved once per group (§6) | declared |

---

## §11 — Failure-mode UX (`ability.*` namespace)

| Reject rule | Stage | User-facing message (I18nBundle `default`) | When |
|---|---|---|---|
| `ability.unknown` | 0 schema / 2 validate | "You do not know that technique." | `AbilityId` absent from the catalogue, or from `known_abilities(actor)` |
| `ability.duplicate_id` | 0 schema | (schema-level) | two `AbilityDecl` share an `ability_id` |
| `ability.requires_kind_unknown` | 0 schema | (schema-level) | `ProgressionReq.kind_id` ∉ `progression_kinds` |
| `ability.effect_count_invalid` | 0 schema | (schema-level) | `effects` empty or > 4 (ABL-V1) |
| `ability.power_term_slot_invalid` | 0 schema | (schema-level) | `PowerTerm.slot` is not a DF07 `StatSlot`, or `mult_milli` = 0 with `flat` = 0 |
| `ability.grant_only_derivable` | 0 schema | (schema-level) | `grant_only = true` declared together with a non-empty `requires` (contradictory) |
| `ability.no_context` | 0 schema | (schema-level) | both `usable_in_combat` and `usable_out_of_combat` false — an unfireable declaration |
| `ability.force_move_self_invalid` | 0 schema | (schema-level) | a `ForceMove` op on an ability whose `TargetRule` is `SelfOnly` — no defined direction (§5.3) |
| `ability.duration_meaningless` | 2 validate | "Nothing lingers." | `StatusApply { duration_rounds: 0 }` fired out of combat — converts to zero fiction-time (§7.3) |
| `ability.wrong_context` | 2 validate | "Not here." | fired in a context its gates forbid |
| `ability.on_cooldown` | 2 validate | "Not ready yet." | `cooldowns[(actor, id)] > 0` |
| `ability.insufficient_resource` | 2 validate | "You lack the strength for that." | any declared cost unaffordable (checked whole, §7.1) |
| `ability.invalid_target` | 2 validate | "You cannot use that on them." | `TargetRule` unsatisfied (wrong side, self-target on `OneHostile`, dead target) |
| `ability.out_of_range` | 2 validate | "Too far." | Chebyshev distance > `range`, or `requires_los` and LoS blocked (delegates to `combat.los_blocked` in combat) |

Per RES_001 §2, every `ability.*` reject carries `RejectReason.user_message: I18nBundle` with an English
`default` plus a Vietnamese translation from day one.

**Player-visible data contract (UI is ABL-D10):** own abilities → name, description, cost, range, cooldown
remaining, and the *failing predicate* when unusable. Hostile abilities → name only once observed
(narration already reveals it); **never** `PowerTerm`, cost or cooldown of a hostile (DF7-A10 applied to
abilities — a leaked `mult_milli` is a leaked damage formula).

---

## §12 — Validators

| ID | Stage | Check |
|---|---|---|
| **ABL-V1** | 0 schema | catalogue well-formed: unique `ability_id`; `1 ≤ effects.len() ≤ 4`; `range ≤ grid_max`; `grant_only` ⇒ `requires` empty; no `ForceMove` under `TargetRule::SelfOnly` (§5.3) |
| **ABL-V8** | runtime | **one hit roll per (ability, target)**, taken before the op list; a miss skips every `Damage` op against that target and no others (§4.1). Ops after a target's death are skipped; ops after the *caster's* death halt the list |
| **ABL-V2** | 0 schema | **warn** (non-blocking): `cooldown_rounds > 0` ∧ `usable_out_of_combat` — the cooldown will not be enforced outside combat (ABL-A7) |
| **ABL-V3** | 0 schema | every `ProgressionReq.kind_id` ∈ `progression_kinds`; every `PowerTerm.slot` ∈ `StatSlot`; every `StatusFlag` ∈ PL_006's set; every `VitalKind` ∈ the reality's declared vitals |
| **ABL-V4** | 2 validate | the §8.1 predicate chain (known → context → cooldown → cost → target/range/LoS) |
| **ABL-V5** | 0 schema | every `AbilityId` referenced by an AIT_001 `combat_reaction_table` entry or an archetype grant list resolves, **and** is reachable by that actor (a ScriptDriver cannot name an ability its actor can never know). Extends to item grants if ABL-Q9 is agreed — no rule change needed |
| **ABL-V6** | commit | costs deducted **exactly once** per successful resolution, and **not at all** on any rejected path (§7.1 ordering) |
| **ABL-V7** | replay | `known_abilities` iteration is order-stable (`BTreeSet`) ⇒ EngineDriver selection and effect ordering are byte-identical on replay; feeds DF7-V4 |

> **ABL-V6 and ABL-V7 are the non-vacuous pair.** ABL-V6 can fail: moving the deduction before step 5
> (the natural implementation) charges stamina on an out-of-range skill, and the check catches it. Its
> bite-test is a deliberately reordered deduction. ABL-V7 can fail: swapping the `BTreeSet` for a `HashSet`
> makes EngineDriver ability choice depend on hash iteration order, and replay diverges. Its bite-test is
> that swap. Neither is structurally prevented — both are real assertions about real code.

---

## §13 — Acceptance criteria (AC-ABL-1..13)

1. **Ability-free reality plays** — a manifest with no `abilities`: `Skill` never appears in
   `allowed_tools`; combat resolves on `Strike` / `Defend` / `Flee` (ABL-Q8).
2. **Vocabulary separation** — `Skill { skill_id: "swordsmanship" }` (a progression kind, not an ability)
   rejects `ability.unknown`; `Skill { skill_id: "rising_dragon_cut" }` resolves (ABL-A1).
3. **Law-chain routing** — `rising_dragon_cut` at snapshot `StrikePower` 24 / `swordsmanship` 8 yields
   effective strike power 44 (§4.3 worked example), which then passes through COMB_001 §4 steps 2–4
   including the hit roll and crit — **not** a direct damage write.
4. **Determinism** — same seed, same snapshot, same ability ⇒ byte-identical damage on replay; no float
   anywhere in the `PowerTerm` path (DF7-A4).
5. **Heal bypasses the chain** — a `VitalDelta { Hp, +30 }` ability restores exactly 30 regardless of the
   target's `Armor`, and cannot miss or crit (ABL-Q7).
6. **Derived acquisition** — raising `swordsmanship` 4 → 5 adds `rising_dragon_cut` to the known set with
   **no** unlock event and **no** stored row; lowering it back removes the ability (§6).
7. **Cost atomicity** — a two-cost ability with only one cost affordable rejects
   `ability.insufficient_resource` and deducts **nothing**.
8. **Failed action costs nothing (bite test)** — an out-of-range `Skill` deducts no stamina and sets no
   cooldown; deliberately moving the deduction ahead of the range check makes ABL-V6 fail.
9. **Cooldown lifecycle** — `cooldown_rounds: 3` blocks re-use for exactly 3 round boundaries, then clears;
   the counter is gone once the `combat_session` resolves (ABL-A7).
10. **Bounded agent set** — an LlmDriver handed 4 currently-usable abilities that returns a 5th (or one on
    cooldown) is rejected and falls back to `Defend`, with a canon-drift flag (ABL-A6 / COMB_001 §1).
11. **ScriptDriver schema gate** — an AIT_001 `combat_reaction_table` naming an ability the actor's
    archetype can never know fails at **schema** stage via ABL-V5, not at runtime.
12. **Replay stability (bite test)** — replacing the `BTreeSet` in `known_abilities` with a `HashSet`
    makes EngineDriver selection diverge on replay and trips ABL-V7.
13. **Narration discipline** — the Layer-3 payload for an ability contains its `display_name` and per-op
    outcomes, and contains **no** `PowerTerm`, `mult_milli`, or hostile slot value (DF7-A10 / §8.3).

---

## §14 — Edge cases (resolved 2026-07-26)

An adversarial pass over §4–§8. Rows 1–5 were genuine ambiguities — each had a plausible wrong answer an
implementer would have picked without noticing.

| # | Case | Resolution |
|---|---|---|
| 1 | **Multiple `Damage` ops** — one hit roll or several? | one per (ability, target), before the op list (§4.1). Per-op rolls would make multi-hit abilities silently more reliable |
| 2 | **`AllHostiles`** — one shared roll or one per target? | one **per target**; each resolves against its own `Dodge` (§4.1) |
| 3 | **An op kills its target mid-list** | remaining ops on that target skipped; other targets continue (§4.1) |
| 4 | **An op kills the caster** (self-damage) | op list halts; resolved ops stand (§4.1) |
| 5 | **`StatusApply` out of combat** — `duration_rounds` has no rounds to count | converts via COMB_001 §12.1's `round_fiction_seconds`, and back at `CombatSessionBorn`; `duration_rounds: 0` rejects out of combat (§7.3) |
| 6 | **`ForceMove` with `SelfOnly`** | schema reject — no defined direction (§5.3) |
| 7 | **`ForceMove` displacing 0 tiles** (pushed into a wall) | **success**, cost paid, nothing moved. Not a rejection — refunding would contradict the fiction (§5.3) |
| 8 | **`SwapWithTarget`** | all-or-nothing; both tiles are occupied and walkable by definition (§5.3) |
| 9 | **Known-set changes mid-encounter** (a COMB_004 progression award) | evaluated **live**, unlike the stat snapshot — the asymmetry is deliberate and tabulated in §8.1 |
| 10 | **Self-damage abilities** (`Damage` + `SelfOnly`) | legal — sacrifice abilities are a genre staple. Bounded by rule 4 |
| 11 | **Ability used out of combat, combat starts immediately, used again** | permitted — cooldowns are encounter-ephemeral (ABL-A7). ABL-V2 warns the author at schema stage so it is a chosen behaviour |
| 12 | **`AllHostiles` partial range/LoS coverage** | out-of-range targets silently excluded, not rejected — clipping two of four is a positioning outcome (§5.2) |

## §14.1 — Open questions resolved (were ABL-QO1/QO2)

**ABL-QO1 — should `AllHostiles` cost more than a single-target ability? RESOLVED: no engine rule; it is
an authoring concern, and the schema already carries it.** `costs` is per-ability and author-declared, so
an author who wants a sweep to cost triple simply declares that. Adding an *engine* multiplier for
side-wide abilities would (a) put a balance opinion inside the engine, which every other decision in this
family has refused, and (b) interact badly with encounter size — the same ability would cost more in a
crowded fight, which is a hidden dynamic cost no player could plan around. **Closed as won't-fix.** The
lever that *does* exist and is sufficient: `cooldown_rounds`.

**ABL-QO2 — should `ForceMove` provoke anything? RESOLVED: no, and it is now closed rather than parked on
COMB_002 §11.** The question presumed zone-of-control might arrive and bring "provoked" reactions with it.
Even if ZoC lands (COMB_002 §11, V1+), a **forced** move must not provoke: the moved actor did not choose
to move, and punishing an actor for someone else's action is the kind of rule that makes a mechanic feel
unfair rather than tactical. This is a stable answer independent of ZoC, so it does not need to wait for
it. Recorded so that whoever implements ZoC does not have to re-derive it: **`ForceMove` never provokes.**

## §14.2 — Deferred (ABL-D1..D11)

See the §1 "V1 NOT shipping" table — each row is the corresponding `ABL-D*`. **No open questions remain
except ABL-Q9**, which is a cross-track coordination item (the `UseEffectDecl` ⊂ `EffectOp` merge) and
cannot be closed unilaterally — it needs the PL_007 owner's agreement.

## §15 — Cross-references

- Audit finding that mandated this doc — [`12_module_coverage_audit.md`](../../12_module_coverage_audit.md) AUD-F10
- The `Skill` verb + law-chain — [`COMB_001`](../18_combat/COMB_001_combat_foundation.md) §3, §4
- Range / LoS / grid — [`COMB_002`](../18_combat/COMB_002_tactical_grid.md) §4, §5
- Threat op target — [`COMB_003`](../18_combat/COMB_003_threat_and_targeting.md)
- Stat slots + snapshot — [`DF07_001`](../DF/DF07_pc_stats/DF07_001_actor_stat_block.md) §3, §8
- Gating inputs — [`PROG_001`](../00_progression/PROG_001_progression_foundation.md) §3
- Costs — [`RES_001`](../00_resource/RES_001_resource_foundation.md) §4.1 · Statuses — [`PL_006`](../04_play_loop/PL_006_status_effects.md)
- Item entry points + effect-enum reconciliation — [`PL_007`](../04_play_loop/PL_007_item.md) §7.1
- Bounded tool vocabulary — [`11_agent_decision_standard.md`](../../11_agent_decision_standard.md) AGT-A2/A3
