//! `StatRules` — the DF07 stat path's CONSTANTS.
//!
//! Three groups, all previously literals in `commit-service/src/stats.rs` and
//! `combat.rs`:
//!
//! | Group | Was |
//! |---|---|
//! | `slot_defaults` | `StatSlot::default_value()`'s ten match arms (DF7-A6) |
//! | the `MoveRange` derivation | `StatTuning::default()` + the `clamp(1, …)` floor |
//! | `melee_archetype` | `CombatStats::archetype_melee`'s 12 / 2 / 450 / 100 |
//!
//! The third is genuinely *content* (IMP-A4 puts `stat_archetypes` on the
//! loaded side) and only lives in a rules struct because F1 has no loader. F2
//! moves it; it is here rather than left as a literal because a literal is
//! invisible to the digest, and an archetype that changes silently changes
//! every NPC in the reality.

use crate::canon::{Canon, CanonEncode, CanonError, CanonReader};
use crate::slots::{SLOT_COUNT, StatSlot};

/// The numbers `resolve_block` and the archetype projection read.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StatRules {
    /// DF7-A6 — every slot has an engine default, so a reality that declares
    /// nothing at all still yields a valid, balanced-enough block. "Playable
    /// with zero declaration" is a hard requirement, not a convenience.
    ///
    /// Indexed by slot ordinal, which is why `StatSlot` lives in this crate.
    pub slot_defaults: [i32; SLOT_COUNT],

    // ── the MoveRange derivation: clamp(base + speed/per_tile, 1, max) ──
    //
    // DF07_001 §5.2 `StatTuningDecl` declares exactly these three, with the
    // same defaults. The floor of 1 is deliberately NOT among them: an actor
    // that cannot move has no legal action on a grid, so it is the law's
    // structure, like `max(1, sp − armor)` in the damage chain. A configurable
    // floor of 1 is a configurable stalemate.
    pub move_base: i32,
    /// Divisor. Clamped to ≥1 at the call site — a zero here would divide by
    /// zero inside `apply` and take the island down.
    pub move_speed_per_tile: i32,
    pub move_max: i32,

    /// A plain melee archetype, as a dense per-slot declaration.
    ///
    /// `MaxHp` is overwritten per-actor by the spawn call, so its value here is
    /// the fallback for an actor spawned without one.
    pub melee_archetype: [i32; SLOT_COUNT],
}

impl StatRules {
    /// RLS-D2 `engine_default` — every value is the literal it replaced,
    /// unchanged. See the note on [`crate::CombatRules::engine_default`].
    pub const fn engine_default() -> Self {
        let mut slot_defaults = [0i32; SLOT_COUNT];
        slot_defaults[StatSlot::MaxHp as usize] = 100;
        slot_defaults[StatSlot::MaxStamina as usize] = 100;
        slot_defaults[StatSlot::StrikePower as usize] = 10;
        slot_defaults[StatSlot::Armor as usize] = 0;
        slot_defaults[StatSlot::Accuracy as usize] = 250;
        slot_defaults[StatSlot::Dodge as usize] = 50;
        slot_defaults[StatSlot::CritChance as usize] = 50;
        slot_defaults[StatSlot::CritMult as usize] = 1500;
        slot_defaults[StatSlot::Speed as usize] = 100;
        slot_defaults[StatSlot::MoveRange as usize] = 5;

        // The melee archetype is the defaults with five slots overridden —
        // written as a delta from `slot_defaults` rather than a second full
        // table, so a change to a default that the archetype does NOT override
        // reaches the archetype too. Two independent full tables would drift.
        let mut melee_archetype = slot_defaults;
        melee_archetype[StatSlot::MaxHp as usize] = 100;
        melee_archetype[StatSlot::StrikePower as usize] = 12;
        melee_archetype[StatSlot::Armor as usize] = 2;
        melee_archetype[StatSlot::Accuracy as usize] = 450;
        melee_archetype[StatSlot::Dodge as usize] = 100;

        Self {
            slot_defaults,
            move_base: 3,
            move_speed_per_tile: 50,
            move_max: 10,
            melee_archetype,
        }
    }

    pub const fn slot_default(&self, slot: StatSlot) -> i32 {
        self.slot_defaults[slot as usize]
    }
}

impl CanonEncode for StatRules {
    fn canon(&self, c: &mut Canon) {
        // EXHAUSTIVE destructuring, no `..` — see `CanonEncode`.
        let Self {
            slot_defaults,
            move_base,
            move_speed_per_tile,
            move_max,
            melee_archetype,
        } = self;

        // Length-prefixed: a change to SLOT_COUNT must move the digest even if
        // the added slot's default happens to be 0.
        c.i32_slice(slot_defaults);
        c.i32(*move_base);
        c.i32(*move_speed_per_tile);
        c.i32(*move_max);
        c.i32_slice(melee_archetype);
    }
}

impl StatRules {
    /// Read back what [`CanonEncode::canon`] wrote, in the same order.
    pub(crate) fn decode(r: &mut CanonReader<'_>) -> Result<Self, CanonError> {
        Ok(Self {
            slot_defaults: r.i32_array::<SLOT_COUNT>("slot_defaults")?,
            move_base: r.i32()?,
            move_speed_per_tile: r.i32()?,
            move_max: r.i32()?,
            melee_archetype: r.i32_array::<SLOT_COUNT>("melee_archetype")?,
        })
    }
}
