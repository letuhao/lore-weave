//! Initiative: HSR action value, lowest acts first.

use ruleset_core::CombatRules;
use sim_core::EntityId;

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
