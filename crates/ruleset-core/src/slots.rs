//! DF7-A1 — the closed slot vocabulary.
//!
//! **Why this lives in `ruleset-core` and not with the laws.** The ruleset
//! declares a *value per slot* (`StatRules::slot_defaults`), so it has to be
//! able to NAME the slots. Holding a bare `[i32; 10]` in the ruleset and the
//! `StatSlot` enum in the service would put an ordinal contract across a crate
//! boundary with nothing checking it — the exact untyped-index drift the dense
//! array is otherwise safe from.
//!
//! What did NOT move: `default_value()`. Slot defaults are **values**, and
//! IMP-A1 puts values in config. They are now `StatRules::slot_defaults`,
//! inside the hashed struct, which is what lets F3 ask *"edit a constant, does
//! the digest move?"*
//!
//! What stays closed: the variant set. Authors declare how their progression
//! kinds PROJECT INTO these slots; they never add one (DF7-A1). Doc 31 **R02**
//! proposes making the slot set ruleset-declared with digest-pinned ordinals —
//! that amendment is PROPOSED, not applied, and applying it here would be scope
//! creep into a decision still open.

/// DF7-A1 — the closed engine vocabulary. Extending it is an engine release
/// plus a boundary-matrix registration.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
#[repr(usize)]
pub enum StatSlot {
    // vitals
    MaxHp = 0,
    MaxStamina = 1,
    // offense / defense — feed the COMB_001 §4 law-chain
    StrikePower = 2,
    Armor = 3,
    /// per-mille
    Accuracy = 4,
    /// per-mille
    Dodge = 5,
    /// per-mille
    CritChance = 6,
    /// per-mille (1500 = 1.5×)
    CritMult = 7,
    // tempo
    Speed = 8,
    /// Derived, not authored — see `StatBlock::derive_move_range`.
    MoveRange = 9,
}

pub const SLOT_COUNT: usize = 10;

impl StatSlot {
    pub const ALL: [StatSlot; SLOT_COUNT] = [
        StatSlot::MaxHp,
        StatSlot::MaxStamina,
        StatSlot::StrikePower,
        StatSlot::Armor,
        StatSlot::Accuracy,
        StatSlot::Dodge,
        StatSlot::CritChance,
        StatSlot::CritMult,
        StatSlot::Speed,
        StatSlot::MoveRange,
    ];

    /// Slots whose unit is per-mille (0..1000 = 0..100%).
    ///
    /// A UNIT is shape, not config: changing which slots are per-mille would
    /// redefine what every other number in the ruleset means, rather than tune
    /// one of them. It stays in code for the same reason the `/1000` divisor
    /// does.
    pub const fn is_per_mille(self) -> bool {
        matches!(
            self,
            StatSlot::Accuracy | StatSlot::Dodge | StatSlot::CritChance | StatSlot::CritMult
        )
    }
}
