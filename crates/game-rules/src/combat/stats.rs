//! `CombatStats` — the cold projection the hot path reads (IMP-A3).

use ruleset_core::StatRules;

use crate::stats::{resolve_block, StatBlock, StatSlot};

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

// QTY-A12 (doc 35 §6.4) — see the rationale on `StatBlock` in `stats.rs`.
//
// This is IMP-A3's cold projection: the ONLY stat shape the hot path reads.
// `resolve_attack` and `action_value` touch these eight fields and never the
// block behind them, which is what makes the width question cold in the first
// place. If this struct starts growing, that property is being lost.
const _: () = assert!(core::mem::size_of::<CombatStats>() <= 64);

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
