//! The COMB_001 §4 damage chain: hit chance, then the four ordered steps.

use ruleset_core::CombatRules;
use sim_core::EntityId;

use super::rng::{role_rng, roll_pm, SeedRole};
use super::stats::CombatStats;

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
    // F2 (DONE): `ruleset_loader::validate` REFUSES `hit_floor_pm > hit_ceiling_pm`
    // at load. This floor stays anyway: RLS-D18 forbids re-validating a STORED
    // ruleset, so an artifact written before that validator existed still has to
    // degrade predictably rather than panic.
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
    // F2 (DONE): `ruleset_loader::validate` REFUSES `defend_divisor < 1` at load.
    // The clamp stays for pre-validator artifacts (RLS-D18).
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
