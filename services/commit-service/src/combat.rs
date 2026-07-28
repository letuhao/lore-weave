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

use sim_core::{DetRng, EntityId};

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

/// Draw a uniform fraction in [0, 1). `u64 → f64` via the top 53 bits, which
/// is exactly the mantissa width: anything wider would quantise unevenly.
fn unit(rng: &mut DetRng) -> f64 {
    (rng.next_u64() >> 11) as f64 / (1u64 << 53) as f64
}

// ───────────────────────────────── stats ────────────────────────────────────

/// The combat-relevant slice of an actor's stats.
///
/// Slice 1 fills this from a fixed archetype; DF07 stat snapshots replace the
/// source in slice 2 without touching any law below — which is the point of
/// separating them.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct StatBlock {
    pub max_hp: i64,
    pub strike_power: i64,
    pub armor: i64,
    /// Accuracy and dodge are ADDITIVE fractions in the hit formula, not
    /// multipliers — see [`hit_chance`].
    pub accuracy: f64,
    pub dodge: f64,
    /// HSR action value is `10000 / speed`, so speed is a rate: higher acts
    /// sooner. Zero is clamped in [`action_value`] rather than dividing by it.
    pub speed: i64,
    pub crit_chance: f64,
    pub crit_mult: f64,
}

impl StatBlock {
    /// A plain melee archetype. Slice 1's stand-in for DF07 — deliberately a
    /// named constructor rather than scattered literals, so slice 2 has one
    /// place to replace.
    pub fn archetype_melee(max_hp: i64) -> Self {
        Self {
            max_hp,
            strike_power: 12,
            armor: 2,
            accuracy: 0.45,
            dodge: 0.10,
            speed: 100,
            crit_chance: 0.10,
            crit_mult: 1.5,
        }
    }
}

// ──────────────────────────────── the laws ──────────────────────────────────

/// `hit_chance = clamp(0.5 + acc − dodge, 0.05, 0.95)` (COMB_001 §4).
///
/// The clamp is not cosmetic: without the 0.95 ceiling an accuracy-stacked
/// build becomes unmissable and dodge stops being a stat; without the 0.05
/// floor a high-dodge target becomes untouchable and the fight cannot end.
pub fn hit_chance(accuracy: f64, dodge: f64) -> f64 {
    (0.5 + accuracy - dodge).clamp(0.05, 0.95)
}

/// One resolved attack.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AttackOutcome {
    pub hit: bool,
    pub crit: bool,
    pub damage: i64,
}

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
    atk: &StatBlock,
    def: &StatBlock,
    defending: bool,
    session_seed: u64,
    attacker: EntityId,
    action_idx: u32,
) -> AttackOutcome {
    // Independent streams: whether a hit lands must not correlate with how
    // hard it lands, or a lucky seed produces suspiciously consistent play.
    let mut hit_rng = role_rng(session_seed, attacker, action_idx, SeedRole::Hit);
    if unit(&mut hit_rng) >= hit_chance(atk.accuracy, def.dodge) {
        return AttackOutcome { hit: false, crit: false, damage: 0 };
    }

    let mut crit_rng = role_rng(session_seed, attacker, action_idx, SeedRole::Crit);
    let crit = unit(&mut crit_rng) < atk.crit_chance;
    let crit_mult = if crit { atk.crit_mult } else { 1.0 };

    let mut dmg_rng = role_rng(session_seed, attacker, action_idx, SeedRole::Damage);
    let roll = 0.85 + unit(&mut dmg_rng) * 0.30; // 0.85 – 1.15

    const ELEM_MULT: f64 = 1.0; // V1
    const RESIST: f64 = 0.0; // V1

    let base = (atk.strike_power - def.armor).max(1) as f64;
    let mut dmg = base * ELEM_MULT * (1.0 - RESIST) * roll * crit_mult;
    if defending {
        dmg /= 2.0;
    }

    // `floor`, then a floor of 1: a defended glancing crit could otherwise
    // round to zero and read to the player as a miss that was reported as a
    // hit.
    AttackOutcome { hit: true, crit, damage: (dmg.floor() as i64).max(1) }
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

/// `av = 10000 / speed`; **lowest acts first**. Status mutates it:
/// `slowed +20%`, `hasted −20%`, `stunned +100%`.
///
/// Speed is clamped to ≥1 rather than trusted: a zero-speed actor (a bug, or a
/// future stat debuff that over-subtracts) would divide by zero and take the
/// whole island down through `apply` — which the kernel would contain as a
/// poison pill, but the encounter would still be dead.
pub fn action_value(speed: i64, status: AvStatus, is_initiator_first_turn: bool) -> i64 {
    let mut av = 10_000.0 / speed.max(1) as f64;
    if status.slowed {
        av *= 1.20;
    }
    if status.hasted {
        av *= 0.80;
    }
    if status.stunned {
        av *= 2.00;
    }
    if is_initiator_first_turn {
        // COMB_001: the initiator's first turn is AV × 0.75 — starting a fight
        // is worth a head start, not a free round.
        av *= 0.75;
    }
    av.round() as i64
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
