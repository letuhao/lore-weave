//! `Actor` — the per-combatant state, and the only thing that crosses an
//! island boundary (`Domain::extract`/`install`).

use game_rules::combat::{action_value, AvStatus, CombatStats, Side};
use game_rules::stats::StatSnapshot;
use ruleset_core::Ruleset;

use super::payload::Stance;

// PartialEq only: `StatBlock` carries f64 (accuracy/dodge/crit), and floats
// have no total equality. Deriving Eq here would be a lie the compiler
// happens to catch.
#[derive(Debug, Clone, PartialEq)]
pub struct Actor {
    pub hp: i64,
    pub max_hp: i64,
    pub defending: bool,
    pub stance: Option<Stance>,
    pub fled: bool,
    /// COMB_001 Q5 — two sides in V1. Win/lose is evaluated per side, so an
    /// actor with no side could never be counted and the encounter could
    /// never end.
    pub side: Side,
    /// DF07 §8.1 — the block RESOLVED AT ENCOUNTER START, not read live.
    ///
    /// A progression tick or manifest reload mid-encounter would otherwise
    /// retroactively change how earlier rounds *should* have resolved,
    /// breaking replay of the encounter as a unit. And that is the normal
    /// case, not an exotic one: striking trains swordsmanship, and PROG_001
    /// trains on Action.
    pub snapshot: StatSnapshot,
    /// The combat-facing projection of `snapshot.stats` (DF07 §8.1 table).
    pub stats: CombatStats,
    /// HSR action value. LOWEST acts; reset on act (COMB_001 §4).
    pub av: i64,
    pub status: AvStatus,
    /// COMB_001: KO is REVIVABLE for a bounded number of rounds — it is not
    /// death. `Some(n)` counts rounds remaining before it becomes permanent.
    pub knocked_out: Option<u8>,
    /// IAS-D6 — the turn economy, as a RESOURCE rather than a timestamp.
    ///
    /// One slot per actor per turn; an action consumes it and `EndTurn`
    /// refills it. A resource works where a cooldown timestamp cannot: the
    /// domain never sees the clock, so "has it been long enough?" is not a
    /// question it can answer, while "do you still have your action?" is.
    ///
    /// This is the layer-3 defence of doc 22 §5 and the one that actually
    /// stops action spam. Layers 1-2 (transport rate limit, in-flight cap)
    /// shape traffic; only this one enforces the RULES of play, which is why
    /// it binds NPCs exactly as it binds players (IAS-A9).
    pub turn_slots: i64,
}

// QTY-A12 (doc 35 §6.4) — see the rationale on `StatBlock` in `stats.rs`.
//
// `Actor` is THE dense per-actor struct: one per combatant, cloned across every
// `Domain::extract`/`install` island handoff. 80 of these 192 bytes are
// `snapshot: StatSnapshot`, which is written at construction and read nowhere
// outside tests today — it is pre-wired for the Q2/Q4 progression slices, and
// if those land without consuming it, it must go rather than stay as a shape
// with no consumer.
const _: () = assert!(core::mem::size_of::<Actor>() <= 192);

impl Actor {
    /// Slice-1 constructor: a melee archetype at `max_hp`, on side B.
    /// `with_side` is the one to use when the side matters.
    ///
    /// F1 added the `rules` parameter: an actor's opening stats are the
    /// reality's melee archetype resolved through the DF07 path, and there is
    /// no such thing as an archetype without a ruleset to read it from.
    pub fn new(rules: &Ruleset, max_hp: i64) -> Self {
        Self::with_side(rules, max_hp, Side::B)
    }

    pub fn with_side(rules: &Ruleset, max_hp: i64, side: Side) -> Self {
        let stats = CombatStats::archetype_melee(&rules.stats, max_hp);
        Self {
            hp: max_hp,
            max_hp,
            defending: false,
            stance: None,
            fled: false,
            side,
            snapshot: StatSnapshot::default(),
            stats,
            av: action_value(&rules.combat, stats.speed, AvStatus::default(), false),
            status: AvStatus::default(),
            knocked_out: None,
            turn_slots: 1,
        }
    }

    /// The SL-A12 **empty case**: `Domain::extract` is TOTAL, so an entity with
    /// no domain rows must still be able to depart, and this is the portable
    /// that encodes "there was nothing here".
    ///
    /// It takes no `rules` on purpose, and that is the whole point of splitting
    /// it out of `Actor::new`. `extract` has no rules parameter (the kernel's
    /// trait gives it none), so building a placeholder from an *archetype*
    /// would mean reaching for an ambient `Ruleset::engine_default()` — exactly
    /// the ambient-configuration reach RLS-A12 added the `Rules` seam to
    /// prevent. A fabricated actor is not an archetype instance; it is a hole,
    /// and it now looks like one.
    ///
    /// Zeroed is behaviour-preserving here: the initiative queue filters on
    /// [`Actor::alive`] before it ever reads `av`, and `hp = 0` keeps this out
    /// of it either way.
    ///
    /// **Pre-existing hazard, now visible and NOT fixed here:** installing this
    /// on the arrival island materialises a side-B actor at 0 HP, which
    /// `outcome_of` counts as *present but not standing* — i.e. an empty-case
    /// handoff can read as a Victory. That is a sim-core handoff-semantics
    /// question, out of F1's scope; tracked as `D-EMPTY-PORTABLE-SIDE`.
    pub fn absent() -> Self {
        Self {
            hp: 0,
            max_hp: 0,
            defending: false,
            stance: None,
            fled: false,
            side: Side::B,
            snapshot: StatSnapshot::default(),
            stats: CombatStats::from_block(&crate::stats::StatBlock::zeroed()),
            av: 0,
            status: AvStatus::default(),
            knocked_out: None,
            turn_slots: 0,
        }
    }

    /// Able to act. A knocked-out actor is NOT alive for this purpose even
    /// though its KO is revivable — it holds a place in the encounter without
    /// holding a turn.
    pub fn alive(&self) -> bool {
        self.hp > 0 && !self.fled && self.knocked_out.is_none()
    }
}
