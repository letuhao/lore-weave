//! DF07 — the actor stat block: closed slots, integer determinism, locked
//! layer order.
//!
//! ## The axiom that shapes every line here
//!
//! **DF7-A4 (Integer determinism):** all resolution runs in **i64 milli-units**
//! with exactly one `floor` at slot emit, and **no float anywhere in the stat
//! path**. Same inputs → byte-identical block on any machine.
//!
//! That is not stylistic. Float arithmetic is reproducible *within* a build but
//! not reliably *across* targets — different optimisation levels can fuse a
//! multiply-add, x87 can keep 80-bit intermediates — and this project replays
//! committed encounters as its recovery model (EVT-A9, CNC-D5). A stat block
//! that differs in the last bit on another machine means a replayed fight
//! diverges, which is exactly the failure the whole event-sourced design exists
//! to prevent.
//!
//! **This corrects slice 1**, which stored `accuracy`/`dodge`/`crit` as `f64`.
//! The fractional slots are **per-mille integers** (0..1000), as DF07 specifies.
//!
//! ## Dense array, never a map (EC-3)
//!
//! `StatBlock` is `[i32; SLOT_COUNT]` indexed by slot ordinal. A `HashMap`
//! would put iteration order into the bytes the moment any consumer serialises
//! a block, breaking the DF7-V4 byte-identical assertion nondeterministically —
//! the worst kind of failure, since it passes locally and fails in CI on a
//! different seed.

/// DF7-A1 — the closed engine vocabulary. Authors declare how their kinds
/// *project into* these slots; they never add one. Extending the set is an
/// engine release plus a boundary-matrix registration.
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
    /// Derived, not authored — see [`StatBlock::derive_move_range`].
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

    /// DF7-A6 — every slot has an engine default, so a reality that declares
    /// nothing at all still yields a valid, balanced-enough block. "Playable
    /// with zero declaration" is a hard requirement, not a convenience.
    pub const fn default_value(self) -> i32 {
        match self {
            StatSlot::MaxHp => 100,
            StatSlot::MaxStamina => 100,
            StatSlot::StrikePower => 10,
            StatSlot::Armor => 0,
            StatSlot::Accuracy => 250,
            StatSlot::Dodge => 50,
            StatSlot::CritChance => 50,
            StatSlot::CritMult => 1500,
            StatSlot::Speed => 100,
            StatSlot::MoveRange => 5,
        }
    }

    /// Slots whose unit is per-mille (0..1000 = 0..100%).
    pub const fn is_per_mille(self) -> bool {
        matches!(
            self,
            StatSlot::Accuracy | StatSlot::Dodge | StatSlot::CritChance | StatSlot::CritMult
        )
    }
}

/// A resolved block. Derived, never an SSOT row (DF7-A2).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StatBlock([i32; SLOT_COUNT]);

impl Default for StatBlock {
    fn default() -> Self {
        let mut v = [0i32; SLOT_COUNT];
        for slot in StatSlot::ALL {
            v[slot as usize] = slot.default_value();
        }
        Self(v)
    }
}

impl StatBlock {
    pub fn get(&self, slot: StatSlot) -> i32 {
        self.0[slot as usize]
    }

    pub fn set(&mut self, slot: StatSlot, v: i32) {
        self.0[slot as usize] = v;
    }

    /// `MoveRange` is the one slot with an engine derivation rather than an
    /// author term list (DF07 §): `clamp(base + floor(speed / per_tile), 1, max)`.
    pub fn derive_move_range(&mut self, tuning: &StatTuning) {
        let speed = self.get(StatSlot::Speed).max(1);
        let derived = tuning.base_move + speed / tuning.speed_per_tile.max(1);
        self.set(StatSlot::MoveRange, derived.clamp(1, tuning.max_move));
    }
}

/// Engine tuning for the derived slot. Defaults give 5 tiles at speed 100 on
/// a 16×16 grid.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StatTuning {
    pub base_move: i32,
    pub speed_per_tile: i32,
    pub max_move: i32,
}

impl Default for StatTuning {
    fn default() -> Self {
        Self { base_move: 3, speed_per_tile: 50, max_move: 10 }
    }
}

/// Where a contribution came from. The source determines which LAYER it lands
/// in, and the layers are ordered (DF7-A3) — so this is not merely
/// bookkeeping for a debug view.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum ModifierSource {
    Base,
    Archetype,
    Progression,
    Equipment,
    Status,
    /// A world rule. Applied LAST and therefore inescapable.
    Lex,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModifierOp {
    Flat(i32),
    /// Per-mille percentage. DF7-A5 — percent modifiers SUM into one factor
    /// rather than chaining multiplicatively, which makes the result
    /// order-independent and kills exponential buff stacking.
    Percent(i32),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StatModifier {
    pub slot: StatSlot,
    pub op: ModifierOp,
    pub source: ModifierSource,
}

/// An inclusive clamp on a slot.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Clamp {
    pub slot: StatSlot,
    pub min: i32,
    pub max: i32,
}

/// Resolve a block from its inputs — a pure function (DF7-A2), in the locked
/// layer order (DF7-A3):
///
/// ```text
/// base → archetype → progression → equipment flat → status flat
///      → Σ percent (all sources) → slot clamp → LEX CLAMP (last)
/// ```
///
/// **The Lex clamp runs last and that ordering is a recorded correction.** The
/// first DRAFT ran `Lex → slot` reasoning that "an author clamp cannot escape a
/// world rule" — which is backwards: whichever clamp runs last wins, so a slot
/// clamp whose `min` exceeds the Lex ceiling would raise the value *back
/// through* it (DF07_002 EC-1). A world rule is never escapable, therefore it
/// is applied last.
///
/// All arithmetic is i64 milli-units with a single emit-time division —
/// DF7-A4.
pub fn resolve_block(
    archetype: &StatBlock,
    modifiers: &[StatModifier],
    slot_clamps: &[Clamp],
    lex_clamps: &[Clamp],
    tuning: &StatTuning,
) -> StatBlock {
    let mut out = StatBlock::default();

    for slot in StatSlot::ALL {
        // base → archetype
        let mut flat: i64 = archetype.get(slot) as i64;

        // Flat layers, in source order. Iterating the ORDERED source list
        // rather than the modifier list keeps the result independent of the
        // order modifiers happen to arrive in.
        for source in
            [ModifierSource::Progression, ModifierSource::Equipment, ModifierSource::Status]
        {
            for m in modifiers.iter().filter(|m| m.slot == slot && m.source == source) {
                if let ModifierOp::Flat(v) = m.op {
                    flat += v as i64;
                }
            }
        }

        // Σ percent across ALL sources, summed not chained (DF7-A5).
        let pct: i64 = modifiers
            .iter()
            .filter(|m| m.slot == slot)
            .filter_map(|m| match m.op {
                ModifierOp::Percent(v) => Some(v as i64),
                _ => None,
            })
            .sum();

        // Exactly one division, at emit. `(base+flat) × (1000+Σpct) / 1000`.
        let value = flat.saturating_mul(1000 + pct) / 1000;
        let mut value = value.clamp(i32::MIN as i64, i32::MAX as i64) as i32;

        // Author clamp, then world rule — in that order, see above.
        if let Some(c) = slot_clamps.iter().find(|c| c.slot == slot) {
            value = value.clamp(c.min, c.max);
        }
        if let Some(c) = lex_clamps.iter().find(|c| c.slot == slot) {
            value = value.clamp(c.min, c.max);
        }
        out.set(slot, value);
    }

    // Speed feeds the derivation, so it must run after the loop.
    out.derive_move_range(tuning);
    out
}

/// DF07 §8.2 — the 5-tuple of input versions a snapshot was resolved under.
///
/// Its job is to make staleness *detectable*: if any input version moves, the
/// snapshot is invalid and must be re-resolved rather than repaired.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct StatEpoch {
    pub manifest_version: u64,
    pub progression_turn: u64,
    pub equipment_version: u64,
    pub status_version: u64,
    pub archetype_version: u64,
}

/// DF07 §8.1 — resolved once at encounter start and read by every law-chain
/// step thereafter.
///
/// **Why a snapshot rather than a live read:** a progression tick or manifest
/// reload mid-encounter would retroactively change how *earlier rounds should
/// have resolved*, breaking replay of the encounter as a unit. Striking trains
/// swordsmanship, and PROG_001 trains on Action — so this is the normal case,
/// not an exotic one.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct StatSnapshot {
    pub stats: StatBlock,
    pub epoch: StatEpoch,
}

impl StatSnapshot {
    /// True when any input version has moved since resolution. The caller
    /// re-resolves; nothing is ever patched in place (DF7-A2).
    pub fn is_stale(&self, current: &StatEpoch) -> bool {
        &self.epoch != current
    }
}
