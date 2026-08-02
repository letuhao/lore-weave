# DF07_001 — Actor Stat Block (derived-stat layer)

> **Conversational name:** "Stat Block" (DF7). The **derived** layer between author-declared progression
> and the engine: a **declared slot vocabulary** (`D-10`, 2026-08-02 — was a closed set of 10 engine
> slots) plus the deterministic law that resolves
> PROG_001 progression values + equipment + PL_006 status into them. DF7 owns **no aggregate** and **no
> SSOT** — a stat block is a pure function of state that already exists.
>
> **Category:** DF — Big Deferred Features (DF07; V1-blocking)
> **Status:** **DRAFT 2026-07-26** (promoted from placeholder `_index.md`). Resolves **AUD-F6**
> ([`12_module_coverage_audit.md`](../../../12_module_coverage_audit.md)) — *"COMB_001's 4-step damage
> law-chain and COMB_002's `move_range = base_move + ⌊speed / K⌋` both consume stat inputs that no doc
> defines"*. **DF7-Q1..Q11 LOCKED** in this pass; DF7-A1..A11 axioms codified.
> **Stable IDs in this file:** `DF7-A*` axioms · `DF7-Q*` decisions · `DF7-D*` deferrals · `DF7-V*`
> validators · `AC-DF7-*` acceptance criteria. Owns the `stat.*` reject namespace.
> **Closure pass:** [`DF07_002`](DF07_002_edge_cases_and_closure.md) (2026-07-26) — adversarial review
> against the six same-day consumers. **4 defects fixed in this file** (EC-1 escapable Lex clamp · EC-2
> percent inversion · EC-3 hash-map block · EC-4 overflow), 11 edge cases closed, axioms **DF7-A12..A14**,
> decisions **DF7-Q12..Q14**, criteria **AC-DF7-16..21** added there.
> **Builds on:** [PROG_001](../../00_progression/PROG_001_progression_foundation.md) §3/§4 `actor_progression` + §9.2 `StatTerm` ·
> [RES_001](../../00_resource/RES_001_resource_foundation.md) §4.1 `vital_pool`/`VitalProfile` ·
> [PL_006](../../04_play_loop/PL_006_status_effects.md) `StatusFlag`/`actor_status` ·
> [COMB_001](../../18_combat/COMB_001_combat_foundation.md) §2/§4 · [COMB_002](../../18_combat/COMB_002_tactical_grid.md) TG-A3 ·
> [ACT_001](../../00_actor/ACT_001_actor_foundation.md) actor-class ref · [AIT_001](../../16_ai_tier/AIT_001_ai_tier_foundation.md) tiers ·
> [EF_001](../../00_entity/EF_001_entity_foundation.md) `EntityId`/`inventory_cap`.
> **Paired with:** **PL_007 Item / PL_007b Inventory** (DRAFT 2026-07-26, parallel; closes AUD-F5). Seam =
> ITM-A3 — *PL_007 owns what an item contributes and when; DF7 owns base stats and the resolution order*.
> PL_007 §6.3 implements this doc's `EquipmentStats` trait; **ITM-Q1's "which spelling?" reservation closes
> at zero cost** (§5.3). **Defers to:** DF4 World Rules for the Lex clamp source (DF7-D4); V1+
> element/resistance slots (DF7-D2, promoting PROG-D27/D30).
> **i18n compliance:** conforms to RES_001 §2 — stable IDs English `snake_case`/`PascalCase`; user-facing
> strings `I18nBundle`.

---

## §1 — Purpose & V1 minimum scope

### Why this feature exists

Three locked designs consume stats that **no document produces**:

| Consumer | Reads | Defined where before this doc |
|---|---|---|
| COMB_001 §4 damage law-chain | `strike_power`, `armor`, `crit_mult` | nowhere |
| COMB_001 §4 hit/dodge + initiative | `acc`, `dodge`, `speed` | nowhere |
| COMB_002 TG-A3 movement | `move_range` (from `speed`) | formula only, no `speed` source |
| RES_001 §4.1 `vital_pool` | `max_value` per Vital | static per-actor-class constant only |

PROG_001 deliberately ships an **open, author-declared** schema (`qi_cultivation`, `swordsmanship`,
`intelligence`, … — genre-specific, arbitrary `kind_id`s). The engine cannot consume that directly: a
deterministic combat engine needs **fixed slots**. DF7 is the **projection law** between the two — the
only place where "author's arbitrary kinds" becomes "engine's fixed numbers".

It is also the missing home for two orphan bindings: `VitalProfile.max_value` (RES_001 Q1 punted it to
"consumer features") and the equipment→stat fold — PL_007 (DRAFT the same day) declares what a weapon
*contributes* but deliberately does not own how contributions become an effective number (ITM-A3).

### V1 minimum scope

- **0 new aggregates** (DF7-A2). Stat blocks are derived; the only *stored* copy is the per-encounter
  snapshot inside COMB_001's already-ephemeral `combat_session`.
- **Closed `StatSlot` enum — 10 V1 active** slots (§3), 6 V1+ reserved.
- **One resolution law** with a **locked layer order** and **fixed-point integer arithmetic** (§4).
- **3 RealityManifest extensions** — `stat_slots`, `stat_archetypes`, `stat_tuning` (§5); all OPTIONAL,
  all engine-defaulted, so a reality with **zero** progression declaration is still combat-playable.
- **`StatModifier` cross-feature contract** (§5.3) — the single shape equipment (PL_007), status (PL_006),
  Lex (DF4) and Forge all use to move a slot.
- **Status→stat table V1** for the 5 PL_006 flags (§6.3), with a boundary rule that keeps combat-only
  effects out of the stat layer (DF7-A8).
- **Combat snapshot + `StatEpoch`** invalidation contract (§8).
- **Untracked-NPC archetype blocks** (§9) — AIT_001 quantum-observation parity.
- **10 V1 rule_ids** in the `stat.*` namespace + **6 validators** DF7-V1..V6.

### V1 NOT shipping

| Feature | Defer to | Why |
|---|---|---|
| Equipment modifier **content** (which weapon gives what) | authoring / balance (DF7-D1, reduced) | **PL_007 DRAFT landed 2026-07-26** — the mechanism is live (§6.2); only the per-item numbers are authoring work |
| Element / resistance slots | V1+ (DF7-D2; promotes PROG-D27 + PROG-D30) | COMB_001 §4 already pins `elem_mult`=1.0, `resist`=0 for V1 |
| `carry_capacity` slot → EF_001 `inventory_cap` enforcement | V1+30d (DF7-D3) | `inventory_cap` is itself schema-reserved (EF/RES Q6) |
| Lex clamp source populated | DF4 World Rules (DF7-D4) | hook only V1; COMB_001 Q4 disparity cap covers anti-grief meanwhile |
| `vision_range` / perception slot | V2+ (DF7-D5) | consumer is TMP_001 fog-of-war (TMP-D3), itself V2+ |
| Diminishing-returns / soft-cap curves on slots | V1+30d (DF7-D6) | PROG_001 curves already shape `raw_value`; double-curving is the trap (DF7-Q10) |
| Materialized `actor_stat_block` cache table | V1+30d (DF7-D7) | profile first; PC is Tier 0 eager, reads are O(#terms) |
| Equipment set bonuses / conditional modifiers | V1+ (DF7-D8) | needs PL_007 |
| Per-slot growth telemetry / balance dashboard | V1+30d (DF7-D9) | ops concern |
| Player-visible stat sheet UI | V1+30d (DF7-D10) | §12 defines the data; client-build track owns pixels |
| Temporary non-status buffs (potion with duration) | V1+ (DF7-D11) | model as PL_006 `Buffed` flag when it lands |
| Cross-reality stat translation on xuyên không | V2+ (DF7-D12) | PROG_001 §10 `BodyOrSoul` already carries the inputs; slots re-derive automatically |
| Monotonic `equipment_version` counter (vs turn-stamped) | V1+ if multi-action turns ship (DF7-D13) | V1 grants one action per turn (COMB_001 §3 / TG-A3), so a same-turn equip→unequip→equip cannot occur; tracked jointly with PL_007 ITM-Q1 (§6.2) |

---

## §2 — Domain concepts & axioms

| Concept | Maps to | Notes |
|---|---|---|
| **StatSlot** | Closed engine enum, 10 V1 | The *only* stat vocabulary the engine knows. Authors never extend it. |
| **StatBlock** | `[i32; STAT_SLOT_COUNT]` indexed by slot ordinal — dense, fixed-size, **never a hash map** (EC-3: hash iteration order would break the DF7-V4 byte-identical assertion the moment any consumer serialises a block) | Derived value; never an SSOT row. |
| **StatSlotDecl** | RealityManifest per-slot declaration | `base` + `terms` (PROG kinds × weights) + `clamp`. |
| **StatTerm** | **Reused from PROG_001 §9.2** — `{ kind_id, weight, instrument_match }` | Same shape; DF7 becomes its owner-of-record (§16 closure 1). |
| **StatModifier** | `{ slot: StatSlot, op: ModifierOp, value, source }` | The universal contribution shape (equipment / status / Lex). Produced by PL_007 §6.3, defined here. |
| **ModifierSource** | `Progression \| Equipment(EntityId) \| Status(StatusFlag) \| Lex(rule_id) \| Archetype \| Base` | Determines layer + iteration order. |
| **StatArchetypeDecl** | Per-actor-class flat block | Untracked NPCs (no `actor_progression` row) still have stats. |
| **StatEpoch** | 5-tuple of input versions | Snapshot invalidation + replay determinism assertion (§8.2). |
| **milli-unit** | i64 fixed-point ×1000 | All intermediate math; single `floor` at emit (DF7-A4). |
| **per-mille slot** | slot whose unit is ‰ (0..1000) | `accuracy`, `dodge`, `crit_chance`, `crit_mult`. |

### Axioms

- **DF7-A1 (Closed resolution, declared vocabulary).** The engine closes the **mechanism** of stat
  resolution — that layers are totally ordered, that per-mille factors sum rather than chain, that a
  block is dense and ordinal-indexed, that exactly one `floor` happens at emit. The **slot vocabulary is
  declared by the manifest**, with ordinals assigned by the engine and pinned inside the hashed bytes,
  exactly as [QTY-A5](../../../35_quantity_architecture.md) already does for L2 quantities.

  > **⚠ REVERSED 2026-08-02 — `D-10` / [`2026-08-02-actor-data-structure.md`](../../../../../specs/2026-08-02-actor-hub/analysis/2026-08-02-actor-data-structure.md) §7.1.** A1 previously read
  > *"the engine consumes a **fixed, closed** `StatSlot` enum; authors declare how their kinds project
  > into slots, never new slots"*, and the 2026-07-28 amendment below upheld it against
  > [`WSA-R02`](../../../31_world_simulation_architecture.md). **The PO reversed it: a closed set belongs
  > in the manifest, not in our source — the engine is an environment in the sense an OS or a DB is one,
  > and a hardcoded noun is a manifest that cannot grow.**
  >
  > The amendment below is kept rather than deleted, because **each of its three reasons has since
  > lapsed, and that is worth being able to read**:
  >
  > | its reason | status 2026-08-02 |
  > |---|---|
  > | *"the laws read 9 of 10 slots **by name**, so opening the set buys one dead slot"* | **Dissolved.** Those laws are being rewritten (`D-14`); a property of code being discarded cannot fix the shape of its replacement. |
  > | *"moving `SLOT_COUNT` makes every stored `.canon` undecodable … reds the golden digest with no legal repin"* | **Cost is currently zero.** No production reality exists — [35 §12](../../../35_quantity_architecture.md) states it: *"zero production realities exist, so the clock is under our control."* |
  > | *"`upcaster.rs` versions **event** schemas, not **rules** — there is no migration story"* | **Shipped 2026-07-29 as `Q0a`**: the version-dispatched codec, `upcast v1→v2`, and the epoch switch. The blocker was cleared and the question was never re-opened. |
  >
  > What does **not** change: `QTY-A10(c)` still forbids removing or reusing a declared ordinal, and a
  > vocabulary change is still an epoch switch rather than a silent edit. Opening the set moves *who
  > declares the names*; it does not loosen what happens to artifacts already written.

  > **AMENDED 2026-07-28 — [QTY-D6](../../../35_quantity_architecture.md). A1 is UPHELD, and its scope
  > is now stated.** [WSA-R02](../../../31_world_simulation_architecture.md) previously proposed making
  > the slot set ruleset-declared; that is retired
  > ([QTY-D4/D5](../../../35_quantity_architecture.md)) — the laws read 9 of 10 slots **by name**, so
  > opening the set buys one dead slot. Three clarifications, none of which weaken A1:
  >
  > 1. **Slots are the DERIVED layer (L1) only.** The open layer is **L2 declared quantities**
  >    (primary stats · resources · elements), which are ruleset-declared with ordinals pinned by the
  >    digest. *"A person is not ten numbers"* ([ONT-F2](../../../29_ontology_existence_self_others.md))
  >    is answered there, not by more slots.
  > 2. **`StatTerm.kind_id` refers to an L2 declared-quantity ordinal**, not a free string. This is
  >    the `primary → derived` arrow, which does not exist in the shipped code — `melee_archetype`
  >    lets an author write derived values directly, which is why `ModifierSource::Progression` is
  >    passed an empty slice in production.
  > 3. **A pool is not a stat** ([QTY-A4](../../../35_quantity_architecture.md)) — but **no slot is
  >    removed.** A pool is `{current, max, min, regen, zero-behaviour}`: a declared row whose *max*
  >    **binds to** `MaxHp`/`MaxStamina`, exactly as `RES_001:1083` already specifies. Those two slots
  >    stay. (An earlier draft said pools "leave the slot array" — that is a slot **removal**, which
  >    `QTY-A10(c)` forbids: a declared ordinal is never reused and never removed, because every
  >    artifact written at the wider `n` would be refused on decode.) A law reads the pool bound to the
  >    **`Vital` role**, so a reality may bind `Vital → qi` with no engine release
  >    ([QTY-A3](../../../35_quantity_architecture.md)); `Effort` was cut — an ability's cost names its
  >    own pool.
  >
  > **And A1 gains an obligation it did not have:** *"extending the set is an engine release"* is only
  > acceptable if that release is **bounded**. Today it is not — moving `SLOT_COUNT` makes every
  > stored `.canon` undecodable (`canon.rs:213-226`) and reds the golden digest with no legal repin.
  > [QTY-A10/A11](../../../35_quantity_architecture.md) make an additive slot a
  > canon-version + upcast + **epoch-switch event**, which is what lets A1 stay closed *and* grow.
- **DF7-A2 (Derived, never stored as truth).** A stat block is a **pure function** of
  `(reality manifest, actor_progression, equipment, actor_status, archetype)`. No aggregate holds it as
  SSOT. Any cache is invalidated by `StatEpoch`, never repaired by hand. *(This is what makes MV12
  time-travel and EVT-A9 replay work with zero stat-specific machinery.)*
- **DF7-A3 (Locked layer order).** `base → archetype → progression terms → equipment flat → status flat →
  Σ percent (all sources) → slot clamp → **Lex clamp (last — a world rule is never escapable)**`. The order
  is **inviolable for V1+**; changing it is a balance-visible breaking change, like the COMB_001 law-chain
  order. (This is the ordering PL_007 §6.3 asks DF7 to own — a V1+ `SetFloor` op would slot between percent
  and the slot clamp, i.e. still under the Lex clamp.)
  > **Corrected 2026-07-26 (edge-case pass, [DF07_002](DF07_002_edge_cases_and_closure.md) EC-1).** The
  > first DRAFT ran `Lex clamp → slot clamp` with the rationale "so an author clamp cannot escape a world
  > rule" — which is exactly backwards: a slot clamp whose `min` exceeds the Lex ceiling *raises the value
  > back through it*. Whichever clamp runs last wins, so the world rule runs last.
- **DF7-A4 (Byte-stable arithmetic).** A value that enters a digest or a replayed comparison must have
  **exactly one byte representation per value**. Stat resolution runs in **i64 milli-units** with exactly
  one `floor` at slot emit, and gets that property for free: these numbers are integers on a fixed scale,
  so `NaN`, `-0.0` and rounding order do not arise. Same inputs → byte-identical block on any machine
  (TDIL-A9).

  > **⚠ REVISED 2026-08-02 — this axiom previously read *"Integer determinism … no float anywhere in the
  > stat path"*, and justified itself with the claim that floating point does not reproduce across
  > targets. That claim is false, and this repo's own code disproves it.** IEEE 754 basic operations
  > (`+ - * /`, `sqrt`) are correctly rounded and reproduce bit-for-bit on any conforming target; Rust
  > enables neither fast-math nor FMA contraction, and x86-64 and ARM64 both mandate SSE2/NEON, so there
  > are no 80-bit x87 intermediates to worry about. Meanwhile `crates/world-gen` uses `f64` across **41
  > files**, and `civ_bundle_hash_is_deterministic_per_seed` (`civ_adapter.rs:1985`) **hashes output
  > derived from it** and asserts the hash is stable. Float and a stable digest already coexist here.
  >
  > **The performance argument does not rescue the old wording either.** On x86-64/ARM64 scalar `f64`
  > add and multiply have latency comparable to `i64`, and **integer division is typically slower than
  > float division** — while the milli-unit design divides by 1000 constantly. Fixed-point is the right
  > choice for stat resolution because of **what these numbers are** (integers on a fixed scale), not
  > because it is faster and not because float is unreproducible.
  >
  > **What IS forbidden in the replayed path** — the three things that genuinely do not reproduce:
  >
  > 1. **transcendental libm functions** (`sin`, `cos`, `exp`, `ln`, `powf`) — IEEE 754 does not require
  >    correct rounding for these and implementations differ across platforms. This is what
  >    [`MAP_001 §5`](../../00_map/MAP_001_map_foundation.md) withdrew `f32` trig for, and that
  >    withdrawal stands unchanged;
  > 2. **order-dependent reductions** — a sum folded in a different order gives a different result. This
  >    bites when *we* parallelise, not from the compiler, which will not reorder float reductions
  >    without fast-math;
  > 3. **unnormalised `NaN` / `-0.0` reaching hashed bytes** — `NaN` has many bit patterns and is never
  >    equal to itself, while `0.0 == -0.0` with differing bits. Canonicalise before hashing, or exclude.
  >
  > **Choose the representation by what the number IS**, not by fear of float: integers on a fixed scale
  > ⇒ fixed-point; continuous fields over a wide dynamic range ⇒ float. A lint for the three hazards is
  > deliberately **not** built yet — the replayed path contains no float today, so the check would have
  > no subject, which is the `NV-2` vacuity this repo has already shipped once. Its trigger is the first
  > float to enter a replayed path.
- **DF7-A5 (Additive percent).** Percent modifiers **sum** into one factor: `(base+flat) × (1000+Σpct)/1000`.
  They are never chained multiplicatively — this kills exponential buff stacking.
  > **⚠ RATIONALE CORRECTED 2026-07-30 (`WSA-R03` / [REC-88](../../../19_reconciliation_register.md)).**
  > This axiom previously justified itself with *"this makes the result **order-independent**"*. **That
  > reason is false: multiplication commutes too**, so chaining `×1.1 × 1.1 × 1.5` in any order also
  > yields one value. Order-independence was never the thing summing bought.
  > **The behaviour is correct and unchanged; only its stated reason was wrong** — which is the more
  > dangerous defect of the two, because a false principle teaches the next author to reach for summing
  > whenever they want order-independence, and to believe multiplication would have cost it.
  > **The real rule, stated properly:** *one commutative operator per stage; stages are ordered.*
  > Order-independence comes from **commutativity within a stage** (both `+` and `×` have it) and from
  > the stage order being **declared** (§4 steps 4–6), not from the choice of operator. What summing
  > actually buys is a **linear** rather than exponential response to buff count, and a floor that can
  > be expressed at all (`max(0, 1000+Σpct)` — a product has no equivalent, since one zero term
  > annihilates it). See [`XST-F12`](../../../27_extensibility_stress_test.md) for the finding and
  > [`QTY-D11`](../../../35_quantity_architecture.md) for `combine: Sum | Product`, which makes the
  > operator a **declared per-stage choice** — the shape this axiom's true rule implies.
- **DF7-A6 (Playable with zero declaration).** Every slot has an engine default. A reality that declares no
  `progression_kinds` and no `stat_slots` still yields a valid, balanced-enough block (§5.4) — mirrors
  PROG_001 §9.4's default-formula discipline.
- **DF7-A7 (Actor-wide, not PC-only).** One shape covers PC + NPC (`ActorId::{Pc, Npc}`), exactly as
  PL_006 `actor_status` and PROG_001 `actor_progression` do. The "PC stats" name is historical. Synthetic
  actors have no stat block.
- **DF7-A8 (Stat-layer vs resolution-time boundary).** A modifier belongs to the **stat layer** only if it
  is meaningful **outside** combat resolution. Effects that exist only inside the damage/initiative
  computation — COMB_001's `defending` 50% next-hit reduction, the `slowed/hasted/stunned` **action-value**
  mutations, `knocked_out` turn removal — stay **resolution-time, COMB-owned**, and are *not* stat
  modifiers. Rationale: applying them in both places double-counts, and the AV mutations are pinned to
  exact locked percentages (+20/−20/+100 % on AV) that a `speed` modifier could not reproduce
  (`av = 10000/speed` is non-linear).
- **DF7-A9 (No power rating).** DF7 exposes **no** aggregate "level", "power score" or `combat_rating`
  derived from slots. Per the PROG_001 §1 user direction (*no level / no power-rating concept*), outcomes
  come from relevant slots only. Opponent legibility is COMB_001 Q6's 5-tier vague label — a **per-HP-bar**
  label, not a global score.
- **DF7-A10 (Visibility discipline).** Exact numbers go to the **human UI** for self + party; hostiles show
  only the COMB_001 Q6 vague tier. **No LLM-bound payload carries a raw slot value — not even the actor's
  own** (tightened 2026-07-26, EC-9: COMB_003 THR-A4 and ABL_001 §8.3 both already assume the stricter
  form). Numbers in a prompt leak into prose and trip the A6 canon-drift detector; qualitative labels do not.
- **DF7-A11 (Slot units are declared, not inferred).** Each slot's unit (integer count vs per-mille) is
  part of the closed enum definition (§3). Authors cannot redefine a unit; `stat.percent_out_of_range`
  rejects a per-mille slot declared outside `0..=1000` after clamp.
- **DF7-A12..A14** (archetype is terminal for Untracked · `Percent` is relative, never percentage-points ·
  clamp order is a security property) are added by the closure pass —
  [`DF07_002 §2`](DF07_002_edge_cases_and_closure.md). They constrain §4, §6 and §9 below.

### Event-model mapping

DF7 introduces **no new aggregate, no new EVT-T\* category, and no new event sub-type.** It is a law, not a
store. It *triggers* two existing, already-owned events:

| Trigger | Event | Owner |
|---|---|---|
| `max_hp` / `max_stamina` slot changes (progression, equipment, manifest hot-reload) | **EVT-T3 Derived** `aggregate_type=vital_pool`, `delta_kind=VitalMaxRecomputed` | **RES_001** (§7) |
| Combat snapshot refresh on `StatEpoch` change | **EVT-T3 Derived** `aggregate_type=combat_session`, `delta_kind=CombatRoundDelta` (existing) | **COMB_001** (§8) |

Consequently DF7 needs **no Forge admin action**: author-side stat intervention goes through the existing
`Forge:GrantProgression` (PROG_001) or `Forge:ApplyStatus` (PL_006) paths, which re-derive the block for
free. Adding a `Forge:SetStat` would create the SSOT that DF7-A2 forbids.

---

## §3 — The slot set (DF7-Q2 LOCKED)

```rust
/// Closed engine vocabulary. Extension = engine release + boundary-matrix registration (DF7-A1).
pub enum StatSlot {
    // ─── vitals (feed RES_001 vital_pool.max_value) ───
    MaxHp,          // integer      default 100
    MaxStamina,     // integer      default 100
    // ─── offense / defense (feed COMB_001 §4 law-chain) ───
    StrikePower,    // integer      default  10   → law-chain `atk.strike_power`
    Armor,          // integer      default   0   → law-chain `def.armor`
    Accuracy,       // per-mille    default 250   → `hit = clamp(0.5 + acc − dodge, 0.05, 0.95)`
    Dodge,          // per-mille    default  50
    CritChance,     // per-mille    default  50   (5%)
    CritMult,       // per-mille    default 1500  (1.5×) → law-chain `crit_mult`
    // ─── tempo (feed initiative + tactical grid) ───
    Speed,          // integer ≥1   default 100   → `av = 10000/speed` (COMB_001 Q7)
    MoveRange,      // integer      derived       → tiles per turn (COMB_002 TG-A3)

    // V1+ reserved (DF7-D2/D3/D5): ElemPower(ElementId), Resist(ElementId), CarryCapacity,
    // VisionRange, BlockChance, CastSpeed — each lands with its consumer, never speculatively.
}
```

**`MoveRange` is special** — it is the one slot with an engine *derivation* rather than an author term list:

```
move_range = clamp(stat_tuning.base_move + floor(speed / stat_tuning.speed_per_tile), 1, stat_tuning.max_move)
defaults:   base_move = 3 · speed_per_tile = 50 · max_move = 10   → default speed 100 ⇒ 5 tiles on a 16×16 grid
```

Authors may override the three tuning constants (§5.2) but **not** replace the formula — COMB_002 TG-A3
locked `move_range` as a function of speed, and the double-dip note there (fast units both act more often
*and* reach farther) is tuned via `speed_per_tile`, not by decoupling the slots.

**Why these 10 and no more.** Each slot exists because a *locked* consumer reads it (§1 table). None was
added on speculation — `ElemPower`/`Resist` are the obvious next pair and are deliberately reserved rather
than shipped, because COMB_001 §4 pins `elem_mult = 1.0` and `resist = 0` for V1. Shipping unread slots
invites authors to declare balance that the engine silently ignores.

---

## §4 — The resolution law (DF7-Q3 LOCKED)

```pseudo
fn resolve_stat_block(actor, reality, at_turn) -> StatBlock:
  // 0. inputs (all already-existing state; DF7-A2)
  prog      = read_actor_progression(actor)        // may be absent → untracked path §9
  status    = read_actor_status(actor)             // PL_006
  equipment = equipped_modifiers(actor)            // PL_007 §6.3 impl; ∅ if no impl registered
  decls     = reality.stat_slots                   // author; missing slots use engine defaults

  // Untracked actors hold no per-actor rows to read (AIT-A8), so the archetype is terminal:
  // archetype values over engine defaults, no progression / equipment / status layer.
  // One block serves N group members (DF7-A12 / DF07_002 EC-7).
  if prog.is_none(): return archetype_block(actor, reality)

  for slot in StatSlot::ALL:                       // fixed iteration order = enum order (determinism);
                                                   // Speed precedes MoveRange, the only dependency
    d = decls.get(slot) ?? engine_default_decl(slot)

    // 1. base (milli-units from here on; DF7-A4)
    if slot == MoveRange:
      // derived base: no author terms allowed (stat.derived_slot_terms_forbidden, DF7-V1);
      // Speed is already final at this point because the enum orders it first.
      v = milli(move_range_from(block[Speed], reality.stat_tuning))
    else:
      v = milli(d.base)

    // 2. progression terms — sorted by (kind_id, weight) for order-stable summation
    //    (skipped for MoveRange: derived slots take no terms)
    for term in d.terms.sorted():
      // active_instrument = the EQUIPPED main-hand instance (PL_007), never a per-action `tool` — EC-10
      if term.instrument_match.is_none() or matches(term.instrument_match, equipped_instrument(actor)):
        v += saturating_milli_mul(prog[term.kind_id].raw_value, term.weight)   // weight is milli too (EC-4)

    // 3. flat modifiers — equipment then status, each sorted by (source_key, slot)
    flat_sum = Σ m.value for m in (equipment ++ status_modifiers(status)) where m.op == Flat and m.slot == slot
    v += milli(flat_sum)

    // 4. percent modifiers — ALL sources summed once, applied once (DF7-A5)
    pct_sum  = Σ m.value for m in (equipment ++ status_modifiers(status)) where m.op == Percent and m.slot == slot
    factor   = max(0, 1000 + pct_sum)                                // EC-2: −100% floors at zero, never inverts
    v = saturating_mul_div(v, factor, 1000)                          // i64, truncating; saturating (EC-4)

    // 5. slot clamp, then 6. Lex clamp — the world rule runs LAST so it cannot be escaped (EC-1)
    v = clamp(v, milli(d.clamp.min), milli(d.clamp.max))
    v = lex_clamp(reality, slot, v)                                  // DF4 hook; ∅ V1 — DF7-D4

    if slot == Speed: v = max(v, milli(1))                           // av = 10000/speed guard, pre-emit
    block[slot] = floor_to_int(v)                                    // the ONE rounding point

  return block

fn archetype_block(actor, reality) -> StatBlock:                     // the Untracked path
  for slot in StatSlot::ALL:                                         // same enum order ⇒ Speed before MoveRange
    v = (slot == MoveRange)                                          // derived here too; an archetype entry
      ? milli(move_range_from(block[Speed], reality.stat_tuning))    //   for MoveRange is ignored, not honoured
      : milli(reality.stat_archetypes[actor.actor_class]?[slot] ?? engine_default_decl(slot).base)
    v = clamp(v, slot_clamp(slot))
    v = lex_clamp(reality, slot, v)      // world rules bind archetypes too — else EC-1 returns by the back door
    block[slot] = floor_to_int(v)
  return block
```

> **⚠ CORRECTED 2026-07-26 (REC-43 / AUD-F17 #33): the archetype base is consulted on the
> progression path too.** As written, step 1 read `v = milli(d.base)` — the reality-global
> `StatSlotDecl` base — for **every** actor holding `actor_progression`. Consequence: RES_001's
> NPC-peasant 50/50 default was **unreachable by any DF07 path** — a Tracked NPC has
> `actor_progression`, so it resolved through the reality-global `MaxHp` base and got the PC's
> 100. Per the register's resolution, step 1 for non-derived slots becomes a **per-class base
> override**:
>
> ```pseudo
> v = milli(reality.stat_archetypes[actor.actor_class]?[slot] ?? d.base)
> ```
>
> — i.e. when the actor's `actor_class` has a `stat_archetypes` entry declaring this slot, that
> archetype value is the `base`, **even on the progression path**; progression terms, equipment,
> status, clamps and the Lex clamp then layer on top exactly as before. Actors with no archetype
> entry (PCs by default) are unchanged. The Untracked `archetype_block` path is unchanged — this
> makes the Tracked path consistent with it instead of silently diverging from RES_001 §9.2.

**Why `MoveRange` still runs steps 3–6.** Its *base* derives from the resolved `Speed`, but equipment and
status must still move it (boots of striding; `Exhausted` shortening a stride) — only steps 1–2 differ.
Declaring `terms` on a derived slot is an author error, not a silent no-op:
`stat.derived_slot_terms_forbidden` (DF7-V1).

**Complexity** `O(Σ terms + modifiers)` — ~30 terms for a typical reality; PCs are AIT Tier 0 (eager), so a
full resolve sits well inside the turn-based latency budget. That is why V1 ships **no cache table** (DF7-D7).
**Rounding, stated once:** milli-units throughout, one `floor` at slot emit, percent division truncating
toward zero; negative intermediates are legal (a heavy debuff) and land on the slot clamp (`Armor` at 0,
`Speed` at 1).

---

## §5 — RealityManifest extensions

### §5.1 `stat_slots` — author projection

```rust
pub struct RealityManifest {
    // ... PROG_001 / RES_001 / COMB_001 / … existing fields ...

    /// Author-declared slot projections. Absent slot ⇒ engine default decl (DF7-A6).
    pub stat_slots: Vec<StatSlotDecl>,
    /// Per-actor-class flat blocks for actors without an `actor_progression` row (§9).
    pub stat_archetypes: HashMap<ActorClassRef, StatArchetypeDecl>,
    /// Global tuning constants (move-range formula + default clamps).
    pub stat_tuning: Option<StatTuningDecl>,
}

pub struct StatSlotDecl {
    pub slot: StatSlot,
    pub base: i32,                       // flat starting point before any term
    pub terms: Vec<StatTerm>,            // PROG_001 §9.2 shape — kind_id × weight (+ instrument_match)
    pub clamp: StatClamp,                // { min: i32, max: i32 } — min ≤ max (stat.clamp_invalid)
}
```

`StatTerm.weight` is declared as a decimal in the manifest and **stored/evaluated as milli** (`1.5` →
`1500`) — authors write readable numbers; the resolved value is a fixed-scale integer (DF7-A4).

### §5.2 `stat_tuning`

```rust
pub struct StatTuningDecl {
    pub base_move: u8,            // default 3    — must be ≤ max_move
    pub speed_per_tile: u16,      // default 50   — must be ≥ 1 (it is a divisor: 0 panics, EC-5)
    pub max_move: u8,             // default 10   — must be ≥ 1
}
```

Validated by DF7-V1 at Stage 0; violations reject `stat.tuning_invalid` **before** any actor resolves.

### §5.3 `StatModifier` — the cross-feature contract

```rust
pub struct StatModifier {
    pub slot: StatSlot,                  // a DECLARED slot ordinal (§3, D-10) — not a free-form
                                         // string either: a machine key with an assigned ordinal
    pub op: ModifierOp,
    pub value: i32,                      // signed
    pub source: ModifierSource,          // who contributed — sets the layer + iteration order
}

/// `Percent` values are **per-mille of the multiplier**: `+10%` ⇒ `100`, `−5%` ⇒ `−50`.
/// §4 step 4 applies them once, summed: `v × (1000 + Σpct) / 1000` (DF7-A5).
/// V1+ reserved: `SetFloor` (raise-to-at-least, never lowers) — applies after percent, before clamps.
pub enum ModifierOp { Flat, Percent }

pub enum ModifierSource {
    Base, Archetype, Progression,
    Equipment(EntityId),                 // PL_007 `actor_equipment`, equipped slots only (ITM §6.5)
    Status(StatusFlag),                  // PL_006 (§6.3)
    Lex(RuleId),                         // DF4 (DF7-D4)
}
```

**This is the whole extension surface for future systems.** A crafting bonus, an enchantment, a faction
boon or a Lex axiom does not need new stat machinery — it emits `StatModifier`s from a registered source.

> **ITM-Q1 (PL_007's `StatRef` question) — closed on arrival, 2026-07-26.** PL_007 reserved the
> possibility that DF7 would spell its stat identities differently and budgeted "a two-string rename in
> `item_defs`". It costs nothing: PL_007's two V1-minimum refs are `strike_power` + `armor`, which are
> exactly `StatSlot::StrikePower` / `StatSlot::Armor`. The identity is the **closed enum**, not a free-form
> string, which is what lets DF7-V1 reject a typo'd modifier at manifest validation
> (`stat.slot_unknown`) instead of silently dropping it at runtime.

### §5.4 Engine defaults (no declaration)

| Slot | `base` | `clamp` | Note |
|---|---|---|---|
| `MaxHp` | 100 | 1 .. 100 000 | matches RES_001's documented `SumClamped{max_value:100}` default |
| `MaxStamina` | 100 | 1 .. 100 000 | |
| `StrikePower` | 10 | 0 .. 100 000 | vs `Armor` 0 ⇒ default unarmed blow ≈ 10 |
| `Armor` | 0 | 0 .. 100 000 | |
| `Accuracy` | 250 | 0 .. 1000 | with default Dodge ⇒ hit chance 0.70 |
| `Dodge` | 50 | 0 .. 1000 | |
| `CritChance` | 50 | 0 .. 1000 | |
| `CritMult` | 1500 | 1000 .. 5000 | 1.0×..5.0× |
| `Speed` | 100 | 1 .. 10 000 | `av = 10000/speed` ⇒ default AV 100 |
| `MoveRange` | (derived) | 1 .. `max_move` | 5 tiles at default speed |

A sandbox reality with no progression schema is therefore fully combat-valid: every actor is identical,
fights resolve, nothing divides by zero. This is the DF7 analogue of PROG_001 §9.4.

---

## §6 — The four contribution layers

### §6.1 Progression (V1 active)

`StatTerm { kind_id, weight, instrument_match }` reads `actor_progression.values[kind_id].raw_value`.
`instrument_match` (PROG_001's existing field) is what makes *"+ swordsmanship, but only when wielding a
sword"* expressible. It matches the **equipped main-hand instance** (PL_007 `actor_equipment`), never a
per-action `tool` — an unequipped tool contributes nothing (EC-10), which is both PL_007 §6.5's rule and
what keeps the instrument inside `StatEpoch.equipment_version` instead of being a hidden per-action input
the snapshot cannot see.

**Worked example — the SPIKE_01 Wuxia preset:**

```rust
StatSlotDecl { slot: StrikePower, base: 5,
  terms: vec![ StatTerm { kind_id: "physical_strength", weight: 1.0,  instrument_match: None },
               StatTerm { kind_id: "swordsmanship",     weight: 0.5,  instrument_match: Some(Blade) } ],
  clamp: { min: 0, max: 5000 } }
// STR 15, swordsmanship 8, wielding a blade ⇒ 5 + 15 + 4 = 24 strike_power
// same actor bare-handed                     ⇒ 5 + 15     = 20
```

Tu tiên parity (the PROG_001 §9.5 example) becomes `StrikePower.terms = [qi_cultivation × 1.5]` — same law,
different declaration. **No genre logic lives in the engine.**

### §6.2 Equipment (V1 active — **PL_007 shipped the body the same day**)

DF7 defines the *shape*; **PL_007 Item** defines which item yields which modifiers — the EF_001 discipline
(*"EF_001 owns the contracts; consumer features own the bodies"*), restated as PL_007 ITM-A3.

```rust
/// PL_007 implements (its §6.3); DF7 calls. No impl registered ⇒ ∅ (reality stays playable).
pub trait EquipmentStats {
    fn equipped_modifiers(&self, actor: ActorId) -> Vec<StatModifier>;   // source = Equipment(item entity id)
    fn equipment_version(&self, actor: ActorId) -> u64;                  // feeds StatEpoch (§8.2)
}
```

- **When contributions apply (PL_007 §6.5):** equipped **only** — held-but-unequipped, in a container, on the
  ground, or `lifecycle_state ≠ Existing` contribute nothing (*"carrying a sword in a sack does not arm you"*).
- **Iteration order:** DF7 sorts the returned modifiers by `(source_key, slot)` before summation (§4 step 3);
  the impl need not. Required by DF7-A4 — the sums commute, the milli truncation does not.
- **Double-count guard (PL_007 §6.3):** a two-handed weapon holds two slots with the *same* instance; the impl
  filters `blocked_by_primary`, and DF7 holds the engine-side invariant that `equipped_modifiers` returns at
  most one entry per `(instance_id, slot)` (AC-DF7-15).
- **Invalidation:** stats change on `Item:Equip` / `Item:Unequip` and the EF_001 destroy-cascade **and at no
  other time**, so `equipment_version` (= `actor_equipment.last_modified_at_turn`) suffices as a `StatEpoch`
  input under V1's one-action-per-turn rule (COMB_001 §3 / TG-A3). A same-turn equip→unequip→equip would not
  bump a turn stamp — impossible in V1; becomes a monotonic counter if that changes (**DF7-D13**, tracked
  jointly with PL_007 ITM-Q1).

**DF7-D1 is therefore reduced to authoring, not mechanism** — what remains is the modifier *content* (which
weapon gives what) plus set bonuses / conditional modifiers (DF7-D8). Weapons also reach `StrikePower` via
§6.1's `instrument_match`, which stays valid for realities with progression but no item defs.

### §6.3 Status (V1 active — PL_006 5 flags)

Engine table, magnitude `m ∈ 1..=10` (PL_006 range, **clamped to 10 by DF7** rather than trusted — PL_006's
`Sum` stack policy can push Drunk/Wounded past the documented ceiling, EC-11), applied as
`ModifierSource::Status(flag)`:

| `StatusFlag` | Modifiers | Rationale |
|---|---|---|
| `Drunk` | `Accuracy` Flat −20·m ‰ · `Dodge` Flat −10·m ‰ | can't aim, can't duck; PL_006's canonical Use:wine outcome finally has mechanics |
| `Exhausted` | `Speed` Pct −5·m % · `StrikePower` Pct −3·m % | slower turns + weaker blows |
| `Wounded` | `StrikePower` Pct −4·m % · `Dodge` Flat −15·m ‰ | **never touches `MaxHp`** — see note |
| `Frightened` | `Accuracy` Flat −15·m ‰ · `StrikePower` Pct −3·m % | shaking hands |
| `Hungry` | `Speed` Pct −2·m % · `StrikePower` Pct −2·m % | RES_001 owns the starvation→mortality path; DF7 only adds the drag |

**Note (`Wounded` ≠ `MaxHp`).** Lowering `MaxHp` while `current_value` is unchanged forces an immediate
clamp — i.e. a status effect that silently deals damage, breaking the COMB_001 invariant that *status
applies AFTER damage*. Wounded therefore degrades output, never the pool. Any future flag that legitimately
resizes a pool must go through §7's `VitalMaxRecomputed` path, not a raw clamp.

**Not in this table, by DF7-A8:** `defending` (COMB resolution-time), `slowed`/`hasted`/`stunned` (AV
mutation, COMB-owned), `knocked_out` (turn removal, COMB-owned). When PL_006 registers those flags per
COMB_001 closure item 3, they are marked `stat_layer: false` in the same table.

### §6.4 Lex clamp (hook only V1 — DF7-D4)

`lex_clamp(reality, slot, value)` is a no-op V1. DF4 World Rules will register per-reality axioms (e.g.
*"in the Mortal Realm no actor exceeds strike_power 100"*). It runs **last — after the slot clamp** — because
the clamp that runs last is the clamp that wins; running it first lets an author `clamp.min` above the Lex
ceiling raise the value straight back through it (EC-1). COMB_001 Q4's disparity cap is unaffected — it caps
**damage at resolution time**, not stats, and the two must not be merged (double-capping).

---

## §7 — Vitals binding (DF7-Q6 LOCKED)

`MaxHp` / `MaxStamina` are **authoritative** over `vital_pool.vitals[kind].max_value`.
`VitalProfile.max_value` (RES_001 §4.1, previously the only source) becomes the **`base`** of the
corresponding slot decl when the reality declares no `stat_slots` entry — so RES_001's per-actor-class
profiles keep working untouched, and DF7 layers on top.

**Max-change rule (locked):** when a recomputed max differs from the stored one, RES_001 emits
`VitalMaxRecomputed { kind, old_max, new_max }` and applies:

- `max` **increases** → `current_value` unchanged (growth does not heal — otherwise a level-up is a full heal, and mid-combat equipment swaps become a healing exploit).
- `max` **decreases** → `current_value = min(current_value, new_max)` (clamped, **no death trigger**: reaching 0 by clamp does *not* fire `OnZeroEffect`; only damage does).
- `RegenRule` / `DepletionRule` / `OnZeroEffect` remain **RES_001-owned** — DF7 supplies the ceiling only.
- Mid-encounter, the snapshot rule (§8) applies a max change at the next round boundary, never mid-resolution.

---

## §8 — Combat binding (DF7-Q5 LOCKED)

### §8.1 Snapshot at encounter start

At `CombatSessionBorn`, the engine resolves each combatant's block **once** and stores it in the
already-ephemeral `combat_session` (COMB_001 §2) alongside its `StatEpoch`. Every law-chain read in §4 of
COMB_001 reads the snapshot, not live state.

```rust
pub struct StatSnapshot {
    pub stats: StatBlock,                          // the resolved block (§4)
    pub prog:  BTreeMap<ProgressionKindId, u64>,   // ONLY the kinds referenced by a declared
                                                   //   PowerTerm.scale (ABL_001 §4.3) — bounded,
                                                   //   known at schema stage via ABL-V3
    pub epoch: StatEpoch,                          // §8.2
}
```

**Why the snapshot carries progression values too** (added 2026-07-26 by the `/review-impl` seam pass —
[DF07_002 §1.5 HIGH-2](DF07_002_edge_cases_and_closure.md)): ABL_001's `PowerTerm.scale` read
`actor_progression` **live** at cast time. PROG_001's `Action` trigger trains *during* combat — striking
trains swordsmanship — so ability damage drifted mid-encounter while every slot stayed frozen, breaking
COMB_001's AC-COMB-15 and AC-COMB-16. **DF7-V4 could not catch it**: the epoch guards the block, and a
direct progression read goes around the block entirely. Capturing the referenced kinds in the snapshot puts
them under the same `progression_turn` epoch, so scaling and slots move together or not at all.

| COMB_001 §4 symbol | Slot |
|---|---|
| `atk.strike_power` | `StrikePower` |
| `def.armor` | `Armor` |
| `acc` / `dodge` (as fractions) | `Accuracy` / `Dodge` ÷ 1000 |
| `crit_mult` (+ crit roll) | `CritMult` / `CritChance` |
| `av = 10000/speed` | `Speed` |
| move budget (TG-A3) | `MoveRange` |

**Why snapshot rather than live-read:** a progression tick or manifest reload mid-encounter would otherwise
retroactively change how earlier rounds *should* have resolved, breaking replay of the encounter as a unit.

**Snapshot-set boundaries** (closed by the DF07_002 pass): the set is fixed at Born because COMB_001 fixes
`sides` there (mid-fight reinforcements are COMB_005's SPN-D4). Within that set — a **tier promotion**
(COMB_005 §7) swaps an actor from the archetype path to the derived one; it is epoch-visible via
`progression_turn` and therefore lands at a round boundary like any other change, with RES_001's
max-increase rule leaving current HP untouched (EC-6). KO / `Dying` / `Flee` do not suspend the rule: those
are statuses and side changes, and a KO'd actor's block simply stops being read.
Store the outer map as a `BTreeMap<ActorRef, …>` — the per-round checkpoint serialises it, and DF7-V4's
byte-identical assertion is only as stable as the least stable container in the path (EC-3).

### §8.2 `StatEpoch` — invalidation + determinism assertion

```rust
pub struct StatEpoch {
    pub manifest_version:   u32,   // reality manifest
    pub progression_turn:   u64,   // actor_progression.last_modified_at_turn
    pub status_turn:        u64,   // actor_status.last_modified_at_turn
    pub equipment_version:  u64,   // PL_007 `EquipmentStats::equipment_version` (= actor_equipment.last_modified_at_turn)
    pub vital_profile_turn: u64,   // RES_001 profile changes
}
```

- **Refresh:** at each **round boundary**, if any combatant's current epoch ≠ snapshot epoch, re-resolve
  that combatant's block and record it in the round's `CombatRoundDelta`. Never mid-action.
- **Assertion (DF7-V4, non-vacuous):** on replay, if the epoch is *equal*, the recomputed block MUST be
  byte-identical; a mismatch is `stat.snapshot_epoch_mismatch` and fails the replay. This check can fail —
  any float, any hash-map iteration order, any un-versioned input leaking into resolution trips it. That is
  precisely what it is for.

---

## §9 — Tracking tiers (DF7-Q4 LOCKED; AIT_001 parity)

| Tier | `actor_progression` | Stat block |
|---|---|---|
| PC (AIT Tier 0) | eager | full resolve per read (§4) |
| Tracked NPC (Major/Minor) | lazy materialization on observation | materialize progression **first** (PROG_001 §7.5), then resolve — identical law |
| Untracked NPC | **absent by design** | `stat_archetypes[actor_class]` flat block, **terminal** — no progression / equipment / status layer (DF7-A12), but both clamps still apply |
| Synthetic (orchestrators) | none | none — `stat.synthetic_actor_forbidden` |

```rust
pub struct StatArchetypeDecl {
    pub archetype_id: ArchetypeId,
    pub display_name: I18nBundle,
    pub slots: Vec<(StatSlot, i32)>,     // sparse; unlisted slots fall to engine defaults
}
```

This keeps COMB_001's `EngineDriver` bulk path honest: a 40-bandit mob resolves **one** archetype block, not
40. **DF7 supplies the group pool's ceiling — `archetype.MaxHp × count` — but owns no combat state and
therefore does not own the pool itself** (`combat_session` has no field for it today; see the review finding
in [DF07_002 §1](DF07_002_edge_cases_and_closure.md), raised to COMB_001). It is the quantum-observation rule applied to stats: an
unobserved NPC has no individuated numbers, and promotion to Tracked (PROG-D22 / COMB_005 §7) materializes
progression, at which point the identical law produces its individuated block — at a round boundary, current
HP preserved (EC-6). A missing archetype entry falls back to engine defaults here; COMB_005's **SPN-V2** is
deliberately stricter for *spawns* (a spawner naming an undeclared class is an authoring error, EC-13).

---

## §10 — Decisions (DF7-Q1..Q11 — LOCKED 2026-07-26)

| # | Question | Resolution & reasoning |
|---|---|---|
| **DF7-Q1** | Where does the derived-stat layer live — extend PROG_001 / new aggregate / standalone law? | **Standalone law, zero aggregates.** Extending PROG_001 would put a *closed* engine set inside an *open* author schema (category error). A new aggregate would create a second SSOT that can drift from its own inputs — the classic derived-data bug. DF7-A2 instead makes the block a pure function; the only stored copy is the per-encounter snapshot, which is ephemeral and epoch-checked. **Also resolves PCS-Q4 / PCS-D4** — `pc_stats_v1_stub` is not deferred, it is *unnecessary*. |
| **DF7-Q2** | Closed engine slot set vs author-declared slots? | **Closed, 10 V1.** Author-declared slots cannot be consumed by a deterministic engine (COMB_001's law-chain names its inputs literally). Closed also honors the PC-C3 / F4 "no D&D mechanics" constraint: authors gain *no* new mechanics, only a projection of kinds they already declared. |
| **DF7-Q3** | Layer order + arithmetic? | **§4 order, locked for V1+**, fixed-point i64 milli-units, one floor at emit. Floats in a replayed, event-sourced engine are a determinism liability (TDIL-A9); the COMB_001 seeded roll stays where it is, in the *resolution* layer, not the stat layer. |
| **DF7-Q4** | PC-only or actor-wide? | **Actor-wide** (DF7-A7). Combat needs NPC stats on day one; PL_006 and PROG_001 already set the one-shape precedent. Untracked NPCs get archetypes (§9), not per-actor blocks. |
| **DF7-Q5** | Live-read or snapshot during combat? | **Snapshot at `CombatSessionBorn`, epoch-refreshed at round boundaries.** Preserves per-encounter replay atomicity and gives O(1) hot-path reads. Mid-action refresh is forbidden. |
| **DF7-Q6** | Who owns `max_hp` — DF7 or RES_001 `VitalProfile`? | **DF7 computes the ceiling; RES_001 owns the pool.** `VitalProfile.max_value` degrades to the slot `base`, so existing RES_001 declarations keep working. Growth-doesn't-heal + clamp-doesn't-kill rules locked in §7 — both are exploit-shaped if left implicit. |
| **DF7-Q7** | Equipment layer with PL_007 unwritten? | **Contract now, body later** (§6.2) — the EF_001 pattern. `instrument_match` already gives V1 weapons mechanical weight, so the V1 slice is not blocked on AUD-F5. |
| **DF7-Q8** | Where does the status→stat mapping live? | **DF7 owns the mapping; PL_006 owns the flags + lifecycle; COMB owns resolution-time effects** (DF7-A8). Splitting it any other way either duplicates the table or double-applies the effect. |
| **DF7-Q9** | Reality with no declaration at all? | **Engine defaults, fully playable** (§5.4, DF7-A6). |
| **DF7-Q10** | Soft caps / diminishing returns on slots? | **No — V1 is linear terms + hard clamp** (DF7-D6). PROG_001 curves (`Log`, `Stage`, `CapRule`) already shape `raw_value` growth. Adding a second curve at projection makes balance non-inspectable: the author tunes one dial and two curves move. |
| **DF7-Q11** | Crit in V1 — PROG-D25 defers crit, COMB_001 §4 uses `crit_mult` in the V1 chain. | **Crit is V1 active** via `CritChance` + `CritMult` slots. This is an **explicit reversal of PROG-D25**, made necessary by the COMB_001 DRAFT that already pins crit into the locked V1 law-chain and its seed roles (`role ∈ {damage, crit, hit, position}`). Defaults (5% / 1.5×) mean a reality that ignores crit still behaves sanely. Recorded as closure item 2 (§11). |

---

## §11 — Closure-pass-extensions

Applied as **dated additive notes** on each target (the track's behavioral-closure pattern). Items 1–5 are
applied in this commit; 6–9 are declared and land when each feature is next opened.

| # | Target | Change |
|---|---|---|
| 1 | **PROG_001 §9** | `StrikeFormulaDecl.offense_terms` / `.defense_terms` are **superseded** by the `StrikePower` / `Armor` slot decls (same `StatTerm` shape, one owner). `post_damage_hooks` stays COMB-side. PROG-D24/D30's "DF7-equivalent" is *this* doc. |
| 2 | **COMB_001 §4** | Law-chain inputs formally bound to slots (§8.1 table); fixed-point discipline (DF7-A4); snapshot rule (DF7-Q5); **PROG-D25 crit reversal** (DF7-Q11). |
| 3 | **RES_001 §4.1** | `VitalProfile.max_value` → slot `base`; new `VitalMaxRecomputed` delta_kind + the growth/clamp rules (§7). Closes RES-Q1 ("what max_value for PC vs NPC?" — *derived*, not declared per class). |
| 4 | **PL_006** | Status→stat table (§6.3) + `stat_layer: bool` marking on each flag; `Wounded` explicitly does not resize `MaxHp`. |
| 5 | **PCS_001 §3.3 / §8.5** | `pc_stats_v1_stub` (PCS-D4) marked **RESOLVED — not needed** (DF7-Q1). `vision_range` reserved for the §4 fog-of-war consumer hook (DF7-D5). |
| 6 | **COMB_002 §3** | `move_range` formula constants relocate to `stat_tuning` (§5.2); TG-A3 semantics unchanged. |
| 7 | **AIT_001** | Untracked-tier actors resolve `stat_archetypes`, not per-actor blocks (§9); `EngineDriver` bulk pool = `archetype.MaxHp × count`. |
| 8 | **EF_001** | `inventory_cap` ← V1+ `CarryCapacity` slot (DF7-D3); coordinate with PL_007b's capacity model when that slot activates. |
| 8b | **PL_007 §6.3** | **ITM-Q1 answered** — the stat identity is the closed `StatSlot` enum (not a free-form string), so no `item_defs` rename; DF7-A3 is the `ModifierOp` ordering PL_007 asked DF7 to own; the seam's two silent-bug risks (two-handed double-count, same-turn `equipment_version` churn) are mirrored at §6.2 with DF7-D13. |
| 9 | **ACT_001** | `ActorClassRef` on `CanonicalActorDecl` is the archetype key (§9) — reuses the existing field, no schema change. |

---

## §12 — Failure-mode UX (`stat.*` namespace)

| Reject rule | Stage | User-facing message (I18nBundle `default`) | When |
|---|---|---|---|
| `stat.slot_unknown` | 0 schema | (schema-level) | a term names a slot **this reality did not declare** (inverted 2026-08-02, `D-10` — it previously fired when a manifest declared a slot outside the engine's closed enum, which is now the normal case) |
| `stat.duplicate_slot_decl` | 0 schema | (schema-level) | two `StatSlotDecl` for one slot |
| `stat.term_kind_unknown` | 0 schema | "Stat formula references an unknown progression kind" | `StatTerm.kind_id` ∉ `progression_kinds` |
| `stat.clamp_invalid` | 0 schema | (schema-level) | `clamp.min > clamp.max`, or `MaxHp.clamp.min < 1` |
| `stat.percent_out_of_range` | 0 schema | (schema-level) | per-mille slot clamp outside `0..=1000` (DF7-A11) |
| `stat.derived_slot_terms_forbidden` | 0 schema | "This stat is computed by the engine and takes no formula" | `terms` declared on a derived slot (`MoveRange` V1) — an author error, never a silent no-op |
| `stat.tuning_invalid` | 0 schema | (schema-level) | `stat_tuning.speed_per_tile == 0` (a divisor), `max_move == 0`, or `base_move > max_move` (EC-5) |
| `stat.archetype_unknown` | 0 schema | (schema-level) | untracked actor's `actor_class` has no archetype and no defaults path |
| `stat.synthetic_actor_forbidden` | 0 schema | (schema-level) | stat resolution attempted for `ActorId::Synthetic` |
| `stat.snapshot_epoch_mismatch` | replay | (ops-level; fails replay) | DF7-V4 determinism assertion (§8.2) |

Per RES_001 §2: every `stat.*` reject carries `RejectReason.user_message: I18nBundle` with English
`default` + Vietnamese translation from day one.

**Player-visible surface (data contract; UI is DF7-D10):** self/party → exact slot values + a per-slot
source breakdown (`base / progression / equipment / status`), which is what makes a debuff legible;
hostiles → COMB_001 Q6 vague tier only (DF7-A10).

---

## §13 — Validators

| ID | Stage | Check |
|---|---|---|
| **DF7-V1** | 0 schema | slot decls: known slot, no duplicates, clamp sane, per-mille bounds, no `terms` on a derived slot, `stat_tuning` divisor/bounds sane |
| **DF7-V2** | 0 schema | every `StatTerm.kind_id` resolves in `progression_kinds` |
| **DF7-V3** | 0 schema | every referenced `ActorClassRef` has an archetype **or** falls back to engine defaults explicitly |
| **DF7-V4** | replay | epoch-equal ⇒ block byte-identical (§8.2) |
| **DF7-V5** | runtime | `MaxHp ≥ 1` and `Speed ≥ 1` post-clamp (division/mortality guards) |
| **DF7-V6** | runtime | no `StatModifier` with `source = Status(flag)` for a flag marked `stat_layer: false` (DF7-A8 double-count guard) |

---

## §14 — Acceptance criteria (AC-DF7-1..15; **AC-DF7-16..21 in [DF07_002 §4](DF07_002_edge_cases_and_closure.md)**)

1. **Default reality plays** — manifest with no `progression_kinds` and no `stat_slots`: two actors fight, blows land ~70%, damage ≈ 10, nobody divides by zero.
2. **Wuxia projection** — §6.1 example yields `strike_power` 24 with a blade / 20 bare-handed.
3. **Tu tiên projection** — `qi_cultivation × 1.5` reproduces the PROG_001 §9.5 magnitude without engine changes.
4. **Determinism** — same inputs resolve byte-identical on two machines; every value on the path has one
   byte representation (DF7-A4, revised 2026-08-02).
5. **Order independence** — applying two +10% and one +50 flat modifier in any input order yields one value (DF7-A5).
6. **Layer order** — a percent buff applies after flats; a Lex clamp beats an author clamp (§4 steps 4–6).
7. **Status mechanics** — `Drunk` m=3 lowers `Accuracy` by 60‰ and the resulting hit chance by exactly 0.06.
8. **Boundary guard** — registering `defending` as a stat modifier trips DF7-V6 (proves the double-count guard bites).
9. **Vital ceiling** — a progression tick raising `MaxHp` 100→120 leaves `current_value` unchanged; lowering 120→80 clamps current to 80 and fires **no** mortality trigger.
10. **Snapshot atomicity** — a progression tick mid-round does not change that round's damage; it applies at the next round boundary via `CombatRoundDelta`.
11. **Epoch assertion** — a deliberately un-versioned input (bite test) makes DF7-V4 fail with `stat.snapshot_epoch_mismatch`.
12. **Archetype path** — 40 untracked bandits resolve one archetype block; the `EngineDriver` group pool equals `archetype.MaxHp × 40`.
13. **Tier promotion** — an untracked NPC promoted to Tracked materializes progression, then resolves an individuated block by the identical law.
14. **Visibility** — the narration prompt for a hostile carries only the 5-tier vague label; no raw slot value appears in any LLM-bound payload (DF7-A10).
15. **Equipment fold (PL_007 seam)** — equipping a `+3 strike_power` sword raises the slot by exactly 3; unequipping restores the prior value; the same sword held-but-unequipped, dropped, or destroyed contributes **0** (PL_007 §6.5), and each transition bumps `StatEpoch.equipment_version`. **A two-handed weapon occupying two slots contributes once, not twice** (the seam's silent-bug case).

---

## §15 — Cross-references

- **Closure pass / edge cases** — [`DF07_002`](DF07_002_edge_cases_and_closure.md) (EC-1..EC-15, DF7-A12..A14, DF7-Q12..Q14, AC-DF7-16..21)
- Audit finding that mandated this doc — [`12_module_coverage_audit.md`](../../../12_module_coverage_audit.md) AUD-F6 (and AUD-F5 for the PL_007 dependency)
- Progression substrate — [`PROG_001`](../../00_progression/PROG_001_progression_foundation.md) §3/§4/§9
- Vitals — [`RES_001`](../../00_resource/RES_001_resource_foundation.md) §4.1
- Status — [`PL_006`](../../04_play_loop/PL_006_status_effects.md)
- Items / equipment (the paired seam) — [`PL_007`](../../04_play_loop/PL_007_item.md) §6.3/§6.5 (ITM-A3, ITM-Q1) · [`PL_007b`](../../04_play_loop/PL_007b_inventory.md)
- Combat law-chain + snapshot host — [`COMB_001`](../../18_combat/COMB_001_combat_foundation.md) §2/§4/§6
- Tactical grid / `move_range` — [`COMB_002`](../../18_combat/COMB_002_tactical_grid.md) TG-A3
- PC substrate (stub resolution) — [`PCS_001`](../../06_pc_systems/PCS_001_pc_substrate.md) §3.3/§8.5
- Tiering — [`AIT_001`](../../16_ai_tier/AIT_001_ai_tier_foundation.md)
- Boundary registration — [`_boundaries/01_feature_ownership_matrix.md`](../../../_boundaries/01_feature_ownership_matrix.md) · [`_boundaries/02_extension_contracts.md`](../../../_boundaries/02_extension_contracts.md)
