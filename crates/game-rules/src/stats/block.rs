//! `StatBlock` — the dense resolved array (EC-3: never a map).

use ruleset_core::{StatRules, SLOT_COUNT, StatSlot};

/// A resolved block. Derived, never an SSOT row (DF7-A2).
///
/// **`impl Default` was REMOVED in F1, deliberately.** It used to mean *the
/// engine-default block*, which is now a function of `StatRules` and cannot be
/// produced from nothing. Redefining it as "zeroed" would have left every
/// existing `StatBlock::default()` call site compiling with silently different
/// semantics — so it is gone, and each site had to say which it meant:
/// [`StatBlock::zeroed`] for an accumulator, [`StatBlock::from_defaults`] for
/// the engine defaults. Mechanism over discipline.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StatBlock([i32; SLOT_COUNT]);

// ── QTY-A12 — the memory budget is an ASSERTION, not a doc ──────────────────
//
// The prior project (`chaos-backend-service`) had an active design doc claiming
// "~22 KB per system instance" against a stated budget of "acceptable up to
// 20 KB", while the real figure was 41.5 KiB — computed from a four-field
// illustrative struct rather than the fifty-seven-field real one, and wrong for
// months BECAUSE NOTHING CHECKED IT. Two other of its docs claimed 2-3 KB, off
// by ~15x. It has no `size_of` assertion anywhere. Neither did we: before this
// line, `grep size_of::< crates/ services/` returned ZERO hits.
//
// Budgets are the CURRENT MEASURED size, so any growth reds and shrinkage is
// free. A deliberate increase re-states the number here — the same conscious
// repin the golden ruleset digest already forces.
//
// This check is only possible because QTY-A6 was reversed (doc 35 §4.2): under
// a runtime per-reality width the payload sits behind a pointer, `size_of`
// reports 16 bytes for every `n`, and the assertion could never fire. A guard
// that cannot fire is worse than no guard, because it reads as one.
const _: () = assert!(core::mem::size_of::<StatBlock>() <= 40);

impl StatBlock {
    /// All slots at zero: "no contribution", the accumulator `resolve_block`
    /// fills. NOT a playable actor — a zeroed block has 0 max HP.
    pub const fn zeroed() -> Self {
        Self([0i32; SLOT_COUNT])
    }

    /// Build a block from a dense per-slot declaration.
    ///
    /// The ONE place a ruleset array becomes a block. Both the engine defaults
    /// and the melee archetype come through here rather than each writing its
    /// own ordinal loop — two copies of an index mapping is how the ordinals
    /// drift apart.
    pub fn from_slots(slots: &[i32; SLOT_COUNT]) -> Self {
        Self(*slots)
    }

    /// DF7-A6 — the engine-default block. "Playable with zero declaration" is a
    /// hard requirement, and this is where that requirement is now met from:
    /// the ruleset, not a `match` arm in the binary.
    pub fn from_defaults(rules: &StatRules) -> Self {
        Self::from_slots(&rules.slot_defaults)
    }

    pub fn get(&self, slot: StatSlot) -> i32 {
        self.0[slot as usize]
    }

    pub fn set(&mut self, slot: StatSlot, v: i32) {
        self.0[slot as usize] = v;
    }

    /// `MoveRange` is the one slot with an engine derivation rather than an
    /// author term list (DF07 §):
    /// `clamp(base + floor(speed / per_tile), 1, max)`.
    ///
    /// The derivation's SHAPE — and its floor of 1 — are here; its three
    /// numbers come from the ruleset (DF07_001 §5.2 `StatTuningDecl`).
    pub fn derive_move_range(&mut self, rules: &StatRules) {
        let speed = self.get(StatSlot::Speed).max(1) as i64;
        // i64 intermediate: `move_base` is author-supplied, so the sum
        // overflows i32 for an extreme ruleset — and the shipped profile has
        // overflow-checks OFF, so it wraps rather than panicking. The clamp
        // below brings it back into i32 range exactly.
        let derived = rules.move_base as i64 + speed / rules.move_speed_per_tile.max(1) as i64;
        // `i32::clamp` PANICS when min > max, and `move_max` is now
        // author-supplied. Floor wins — the same deterministic, never-panicking
        // rule `intersect_clamps` applies to a contradictory clamp pair.
        // F2 (DONE): `ruleset_loader::validate` implements DF7-V1's Stage-0 refusal
        // (`max_move >= 1`, `speed_per_tile >= 1`, `base_move <= max_move` ->
        // `stat.tuning_invalid`). This runtime floor keeps a bad ruleset
        // predictable until the loader enforces it; it does not bless one.
        self.set(StatSlot::MoveRange, derived.clamp(1, rules.move_max.max(1) as i64) as i32);
    }
}
