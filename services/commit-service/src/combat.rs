//! COMB_001 L1 — the CombatEngine: deterministic, LLM-free combat law.
//!
//! Every rule here is quoted from `COMB_001_combat_foundation.md` §4, not
//! invented. That distinction matters: **COMB-A1 says the LLM never computes
//! combat math or space.** It selects an intent from a closed vocabulary and
//! the engine resolves everything, so each function below is a *law* with one
//! correct answer rather than a knob to tune.
//!
//! ## Why the RNG is derived per-roll instead of drawn from a stream
//!
//! `DetRng` is a single SplitMix64 stream, so drawing sequentially would make
//! every roll depend on **how many draws happened before it**. Adding one new
//! random call anywhere — a future ability, a loot roll — would silently
//! renumber every subsequent roll and break replay of existing encounters.
//!
//! COMB_001 Q8 specifies the alternative and it is the reason it does:
//! `(reality_id, turn_id, actor_id, action_idx, role)` with
//! `role ∈ {damage, crit, hit, position, loot}`. Each roll gets its **own**
//! stream derived from its coordinates, so rolls are independent of draw order
//! and of each other. A new role can be added without disturbing any existing
//! one.
//!
//! Consequence worth stating: combat math needs no ambient randomness at all.
//! Everything is a function of state, which is what keeps the CNC-D5
//! concurrency conformance test green.

use ruleset_core::{CombatRules, StatRules};
use sim_core::{DetRng, EntityId};

use crate::stats::{resolve_block, StatBlock, StatSlot};

/// Which roll a derived stream is for (COMB_001 Q8). Closed set — an
//  open-ended role string would let two call sites collide on one stream and
//  correlate rolls that must be independent.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SeedRole {
    Damage,
    Crit,
    Hit,
    Position,
    Loot,
}

impl SeedRole {
    /// Distinct, stable discriminants. Values are pinned rather than derived
    /// from declaration order: reordering the enum must not change any
    /// historical roll.
    fn tag(self) -> u64 {
        match self {
            SeedRole::Damage => 0x01,
            SeedRole::Crit => 0x02,
            SeedRole::Hit => 0x03,
            SeedRole::Position => 0x04,
            SeedRole::Loot => 0x05,
        }
    }
}

/// Derive the stream for one (actor, action, role) coordinate.
///
/// SplitMix64 finalisation, the same family `DetRng` itself uses — so this
/// introduces no new randomness primitive and no dependency. Mixing each
/// coordinate through the finaliser before combining avoids the trivial
/// correlations a plain XOR of small integers would leave.
pub fn role_rng(session_seed: u64, actor: EntityId, action_idx: u32, role: SeedRole) -> DetRng {
    let mut z = session_seed;
    for part in [actor.0, action_idx as u64, role.tag()] {
        z = z.wrapping_add(part).wrapping_add(0x9E37_79B9_7F4A_7C15);
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^= z >> 31;
    }
    DetRng::new(z)
}

/// Draw a per-mille value in `0..1000`.
///
/// Integer, not a float fraction — DF7-A4 keeps floats out of the stat path,
/// and the same reasoning applies to the rolls that consume it. Float
/// arithmetic is reproducible within a build but not reliably across targets
/// (fused multiply-add, x87 80-bit intermediates), and this project REPLAYS
/// committed encounters. A roll that differs in the last bit on another
/// machine makes a replayed fight diverge.
fn roll_pm(rng: &mut DetRng) -> i64 {
    rng.range_u64(1000) as i64
}

// ───────────────────────────────── stats ────────────────────────────────────

/// The combat-relevant view of a DF07 stat block.
///
/// Slice 1 held these as `f64`, which **DF7-A4 forbids** ("no float anywhere
/// in the stat path"). They are now the DF07 slots: integers, with
/// accuracy / dodge / crit as **per-mille** (0..1000). Every law below reads
/// through this view, so swapping the SOURCE of the numbers — archetype today,
/// a resolved snapshot with equipment and progression tomorrow — touches no
/// law at all.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CombatStats {
    pub max_hp: i64,
    pub strike_power: i64,
    pub armor: i64,
    /// per-mille; ADDITIVE in the hit formula, not a multiplier.
    pub accuracy_pm: i64,
    /// per-mille
    pub dodge_pm: i64,
    /// HSR action value is `10000 / speed`, so speed is a rate: higher acts
    /// sooner. Zero is clamped in [`action_value`] rather than divided by.
    pub speed: i64,
    /// per-mille
    pub crit_chance_pm: i64,
    /// per-mille (1500 = 1.5x)
    pub crit_mult_pm: i64,
}

impl CombatStats {
    /// Project a resolved DF07 block into the combat view. The mapping is
    /// DF07 §8.1's table, in one place — a law reading a slot directly would
    /// be a second mapping to keep in sync.
    pub fn from_block(b: &StatBlock) -> Self {
        Self {
            max_hp: b.get(StatSlot::MaxHp) as i64,
            strike_power: b.get(StatSlot::StrikePower) as i64,
            armor: b.get(StatSlot::Armor) as i64,
            accuracy_pm: b.get(StatSlot::Accuracy) as i64,
            dodge_pm: b.get(StatSlot::Dodge) as i64,
            speed: b.get(StatSlot::Speed) as i64,
            crit_chance_pm: b.get(StatSlot::CritChance) as i64,
            crit_mult_pm: b.get(StatSlot::CritMult) as i64,
        }
    }

    /// A plain melee archetype at `max_hp`, resolved through the real DF07
    /// path rather than hand-written literals — so the defaults, the clamps
    /// and the MoveRange derivation are all exercised even by a bare NPC.
    ///
    /// F1: the archetype's five numbers were `12 / 2 / 450 / 100` inline here.
    /// They are `StatRules::melee_archetype` now — genuinely *content*
    /// (IMP-A4 files `stat_archetypes` on the loaded side), and an archetype
    /// that can change without moving the digest changes every NPC in the
    /// reality silently.
    pub fn archetype_melee(rules: &StatRules, max_hp: i64) -> Self {
        let mut arch = StatBlock::from_slots(&rules.melee_archetype);
        arch.set(StatSlot::MaxHp, max_hp as i32);
        let block = resolve_block(&arch, &[], &[], &[], rules);
        Self::from_block(&block)
    }
}

// ──────────────────────────────── the laws ──────────────────────────────────

/// `hit_chance = clamp(0.5 + acc − dodge, 0.05, 0.95)` (COMB_001 §4), in
/// per-mille: `clamp(500 + acc − dodge, 50, 950)`.
///
/// The clamps are not cosmetic: without the ceiling an accuracy-stacked build
/// becomes unmissable and dodge stops being a stat; without the floor a
/// high-dodge target becomes untouchable and the fight cannot end. **That the
/// clamps EXIST is the law; their values are the ruleset's** (IMP-D1).
pub fn hit_chance_pm(rules: &CombatRules, accuracy_pm: i64, dodge_pm: i64) -> i64 {
    // Floor wins if a ruleset declares floor > ceiling — `i64::clamp` panics
    // otherwise, and a panic here takes the island down through `apply`.
    // TODO(F2): the loader should refuse that ruleset at load time.
    let (lo, hi) = (rules.hit_floor_pm, rules.hit_ceiling_pm.max(rules.hit_floor_pm));
    // i128, because `hit_base_pm` is author-supplied now: the sum overflows in
    // i64 for an extreme ruleset, and the shipped profile has overflow-checks
    // OFF, so it would wrap into a wildly wrong hit chance in production while
    // panicking in tests. The clamp bounds are i64, so the cast back is exact.
    let raw = rules.hit_base_pm as i128 + accuracy_pm as i128 - dodge_pm as i128;
    raw.clamp(lo as i128, hi as i128) as i64
}

/// One resolved attack.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AttackOutcome {
    pub hit: bool,
    pub crit: bool,
    pub damage: i64,
    /// True when `damage` is the declared ceiling rather than the number the
    /// chain computed — see `CombatRules::max_hit` and XST-D2.
    ///
    /// Surfaced for the same reason `crit` is surfaced on the event: it is the
    /// difference between *"the numbers are swingy"* and *"the numbers are
    /// wrong"*. A ceiling that binds silently is a content bug wearing the
    /// costume of a balance decision.
    pub capped: bool,
}

/// **Where the ceiling went (F1).** `MAX_HIT` was a `const` here with a
/// `TODO(IMP-D5)` saying it belonged in the ruleset. It is now
/// `CombatRules::max_hit`, hashed into the digest — that TODO is retired. The
/// reasoning below is kept because it is *why the field exists*, and a
/// constant that moves into config loses its rationale otherwise.
///
/// **XST-D2 (fixed 2026-07-28).** The chain used to run in `i64` with
/// `saturating_mul`, so above a base of ~1.6 M **every hit returned the
/// identical saturated number, silently.** The irony was in the file: the
/// comment on the divisor congratulates fixed-point for making a scale error
/// *"fail LOUDLY"* — and the line below it used `saturating_mul`, which makes
/// overflow fail in total silence. Same pattern as `saturating_mul` in the stat
/// path and the `Substitute` admission fallback: **a degrade path absorbs the
/// bug and reports success.** That is three times now, which is why this one is
/// both widened AND made observable rather than just widened.
///
/// The intermediates are now `i128`, so nothing overflows for any `i64` input.
/// A ceiling is still required because the result must return to `i64`, and a
/// ceiling that is *declared* is a different object from one that *emerges*:
/// this one has a number, a reason, and a flag that fires when it binds.
///
/// 1e9 is ~1000× beyond any plausible content (a normal hit is ~10; a boss
/// might reach 1e3; an extreme cultivation ruleset 1e6) and far below `i64`
/// overflow. Damage above it is a content defect, not a balance choice — which
/// is exactly what [27 §7.1](../../../docs/03_planning/LLM_MMO_RPG/27_extensibility_stress_test.md)
/// decided when it put true incremental-game numeric range out of scope.
///
/// The 4-step damage law-chain (COMB_001 §4, order LOCKED for V1+):
///
/// ```text
/// base = max(1, strike_power − armor)
///      × elem_mult      (V1 = 1.0)
///      × (1 − resist)   (V1 = 0)
///      × roll(0.85–1.15) × crit_mult
/// V1 collapse: floor(max(1, sp − armor) × roll × crit)
/// ```
///
/// `max(1, …)` is the floor that keeps a heavily-armoured target *killable*:
/// without it, armor ≥ strike_power makes damage zero and the encounter can
/// never resolve — a stalemate the win/lose rule has no answer for.
///
/// The elemental and resist steps are applied at V1 identity values rather
/// than omitted. Keeping them in the chain preserves the locked ORDER, so
/// promoting them later is filling in a constant instead of re-deriving where
/// they multiply — and multiplication order stops being a thing to rediscover.
///
/// `defending` halves the result (COMB_001: consumed by the next hit), applied
/// last because it is a resolution-time flag and explicitly **not** a stat
/// modifier (DF7-A8).
pub fn resolve_attack(
    rules: &CombatRules,
    atk: &CombatStats,
    def: &CombatStats,
    defending: bool,
    session_seed: u64,
    attacker: EntityId,
    action_idx: u32,
) -> AttackOutcome {
    // Independent streams: whether a hit lands must not correlate with how
    // hard it lands, or a lucky seed produces suspiciously consistent play.
    let mut hit_rng = role_rng(session_seed, attacker, action_idx, SeedRole::Hit);
    if roll_pm(&mut hit_rng) >= hit_chance_pm(rules, atk.accuracy_pm, def.dodge_pm) {
        return AttackOutcome { hit: false, crit: false, damage: 0, capped: false };
    }

    let mut crit_rng = role_rng(session_seed, attacker, action_idx, SeedRole::Crit);
    let crit = roll_pm(&mut crit_rng) < atk.crit_chance_pm;
    let crit_mult_pm = if crit { atk.crit_mult_pm } else { 1000 };

    // Variance band, as per-mille and INCLUSIVE at both ends (850..=1150 by
    // default). `roll_band_width()` derives the number of distinct values from
    // lo/hi rather than storing a third number that could disagree with them —
    // which is how XST-D3 happened.
    //
    // XST-D3 (fixed 2026-07-28) — this was `850 + roll_pm(..) * 300 / 1000`
    // over a `0..=999` draw, which yields **850..=1149**: the top of the
    // declared band was unreachable and the mean came out at 999.400‰ instead
    // of 1000‰. That is a permanent, systematic −0.06 % damage shortfall — a
    // BIAS, not noise, so it never averages out over a long game.
    //
    // Drawing the offset directly at its true width (301 values, 0..=300) makes
    // the band exactly the one the spec declares, with mean 150 and no
    // truncation anywhere. Cheaper than the old form, and it removes the
    // division rather than correcting it.
    let mut dmg_rng = role_rng(session_seed, attacker, action_idx, SeedRole::Damage);
    let roll_band_pm = rules.roll_band_lo_pm + dmg_rng.range_u64(rules.roll_band_width()) as i64;

    let base = (atk.strike_power - def.armor).max(1);

    // One expression, integer throughout, with the divisions carried to the
    // END so intermediate precision is never lost to repeated truncation —
    // the integer equivalent of DF7-A4's "exactly one floor at emit".
    // i128, NOT i64-with-saturating_mul. XST-D2: four per-mille factors over an
    // i64 base overflowed above ~1.6 M (at a modest 5× crit) and `saturating_mul`
    // then returned the SAME clipped number for every larger hit, in silence.
    // i128 holds `i64::MAX × 5.75e15` with four orders of magnitude to spare, so
    // the arithmetic itself can no longer overflow for any i64 input.
    //
    // This also unblocks the extensions: every ADDITIONAL per-mille factor
    // divides an i64 ceiling by 1000, so an element factor plus one
    // multiplicative bucket would have taken the safe base from 1.6 M to ~1600.
    // Widening is a prerequisite for XST-R6/R7, not an optimisation.
    let numer: i128 = (base as i128)
        * (rules.elem_mult_pm as i128)
        // NOTE the cast placement: `(1000 - resist) as i128` would do the
        // subtraction in i64 and overflow for an extreme `resist_pm`. The
        // widening happens FIRST.
        * (1000i128 - rules.resist_pm as i128)
        * (roll_band_pm as i128)
        * (crit_mult_pm as i128);
    // FOUR per-mille factors are multiplied in (elem, resist-complement,
    // roll band, crit), so the divisor is 1000^4 — not 1000^3. Getting this
    // wrong scales every hit by 1000×, which the damage-band test caught
    // immediately; it is the kind of error that fixed-point arithmetic trades
    // for float's rounding drift, and it fails loudly rather than subtly.
    //
    // `1000` here is the per-mille UNIT, not a tunable: it is what "‰" MEANS.
    // Making it configurable would not tune a rule, it would redefine every
    // other number in the ruleset underneath itself. The unit is shape; the
    // values expressed in it are config (IMP-A1).
    //
    // `defend_divisor` IS config. Clamped to ≥1 — a ruleset declaring 0 would
    // divide by zero inside `apply` and take the island down.
    // TODO(F2): the loader should refuse `defend_divisor < 1` at load time.
    let denom: i128 =
        1_000i128.pow(4) * if defending { rules.defend_divisor.max(1) as i128 } else { 1 };

    // The result must come back to i64, so a ceiling is unavoidable — but it is
    // DECLARED and it REPORTS. `capped` rides out on the outcome and onto the
    // committed `Struck` event, so a bound ceiling is a fact in the log rather
    // than a number nobody can explain (CS-D5/EVT-L5: nothing silent).
    let raw = numer / denom;
    let capped = raw > rules.max_hit as i128;
    // Floor of 1: a defended glancing hit could otherwise round to zero and
    // read to the player as a miss that was reported as a hit. The floor's
    // VALUE is 1 by structure — "a hit did something" is the law, not a knob.
    let damage = if capped { rules.max_hit } else { raw as i64 }.max(1);

    AttackOutcome { hit: true, crit, damage, capped }
}

// ─────────────────────────────── initiative ─────────────────────────────────

/// Round-scoped status flags that mutate action value (COMB_001 §4).
///
/// Deliberately NOT stat modifiers: DF7-A8 puts `defending` / `slowed` /
/// `hasted` / `stunned` / `knocked_out` on the resolution-time side of the
/// boundary, and registering one as a stat modifier trips validator DF7-V6.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct AvStatus {
    pub slowed: bool,
    pub hasted: bool,
    pub stunned: bool,
}

/// `av = av_base / speed`; **lowest acts first**. Status mutates it by a
/// per-mille factor each (by default: `slowed +20%`, `hasted −20%`,
/// `stunned +100%`).
///
/// WHICH statuses exist and that each contributes one commutative factor is the
/// law; the factors themselves are the ruleset's.
///
/// Speed is clamped to ≥1 rather than trusted: a zero-speed actor (a bug, or a
/// future stat debuff that over-subtracts) would divide by zero and take the
/// whole island down through `apply` — which the kernel would contain as a
/// poison pill, but the encounter would still be dead.
pub fn action_value(
    rules: &CombatRules,
    speed: i64,
    status: AvStatus,
    is_initiator_first_turn: bool,
) -> i64 {
    // Integer throughout — the last float in the combat path lived here.
    // Each status is a per-mille factor accumulated into ONE numerator and
    // denominator so there is a single division at the end, rather than a
    // chain of `x * 1200 / 1000` steps each shedding a milli-unit.
    let mut num: i64 = rules.av_base;
    let mut den: i64 = speed.max(1);

    // Speed is clamped to >=1 rather than trusted: a zero-speed actor (a bug,
    // or a future debuff that over-subtracts) would divide by zero and take
    // the island down through `apply` — contained by the kernel as a poison
    // pill, but the encounter would still be dead.
    let mut apply = |pm: i64| {
        num = num.saturating_mul(pm);
        den = den.saturating_mul(1000);
    };
    if status.slowed {
        apply(rules.av_slowed_pm);
    }
    if status.hasted {
        apply(rules.av_hasted_pm);
    }
    if status.stunned {
        apply(rules.av_stunned_pm);
    }
    if is_initiator_first_turn {
        // COMB_001: the initiator's first turn is discounted — starting a
        // fight is worth a head start, not a free round.
        apply(rules.av_initiator_first_pm);
    }

    // Round to nearest rather than truncate: truncation would bias every
    // status toward acting sooner than the multiplier says.
    (num.saturating_add(den / 2)) / den
}

/// Whose turn it is: the lowest action value acts.
///
/// Ties break on `EntityId`, which is stable across runs — arrival order or a
/// hash would make the queue depend on something that is not replay state, and
/// the CNC-D5 conformance test would (correctly) start failing.
pub fn next_actor(queue: &[(EntityId, i64)]) -> Option<EntityId> {
    queue
        .iter()
        .filter(|(_, av)| *av >= 0)
        .min_by_key(|(id, av)| (*av, id.0))
        .map(|(id, _)| *id)
}

// ────────────────────────────── win / lose ──────────────────────────────────

/// Which side an actor fights for. Capped at 2 for V1 (COMB_001 Q5 / COMB-Q2):
/// three-sided combat is *unreachable by construction* in V1, so there is no
/// undefined behaviour to guard — V1+ multi-side is a relaxation, not a
/// redesign.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Side {
    A,
    B,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EncounterOutcome {
    /// All of side B at 0 HP.
    Victory,
    /// All of side A at 0 HP.
    Defeat,
    /// Everyone still standing has fled.
    Disengaged,
}

/// Evaluate the end condition (COMB_001 §4).
///
/// A **fled** actor counts as neither alive-for-victory nor dead: fleeing
/// removes you from the fight without handing the other side a kill. Treating
/// flight as death would make running away a loss condition for your own team;
/// treating it as presence would leave the encounter unable to end.
pub fn evaluate_outcome(
    actors: impl Iterator<Item = (Side, i64, bool)> + Clone,
) -> Option<EncounterOutcome> {
    let standing = |side: Side| {
        actors.clone().any(|(s, hp, fled)| s == side && hp > 0 && !fled)
    };
    let any_present = |side: Side| actors.clone().any(|(s, _, _)| s == side);

    let a_standing = standing(Side::A);
    let b_standing = standing(Side::B);

    // Everyone who survived has fled — nobody was defeated.
    let anyone_alive = actors.clone().any(|(_, hp, _)| hp > 0);
    if anyone_alive && !a_standing && !b_standing {
        return Some(EncounterOutcome::Disengaged);
    }
    if any_present(Side::B) && !b_standing {
        return Some(EncounterOutcome::Victory);
    }
    if any_present(Side::A) && !a_standing {
        return Some(EncounterOutcome::Defeat);
    }
    None
}
