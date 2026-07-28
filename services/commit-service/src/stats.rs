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

// F1 — the closed slot vocabulary now lives in `ruleset-core`, because the
// ruleset declares a VALUE PER SLOT (`StatRules::slot_defaults`) and therefore
// has to be able to name the slots. Re-exported so every existing
// `commit_service::stats::StatSlot` import keeps working: one definition, two
// paths, no ordinal contract crossing a crate boundary untyped.
//
// What went with it: `default_value()`. Slot defaults are VALUES, and IMP-A1
// puts values in config — they are `StatRules::slot_defaults` now, inside the
// hashed struct, which is what makes XST-D5's *"edit a constant → the digest
// moves"* writable at all.
pub use ruleset_core::{SLOT_COUNT, StatRules, StatSlot};

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

impl ModifierSource {
    /// DF7-A3 — the locked layer order, enumerated once.
    ///
    /// **XST-D7 (fixed 2026-07-28).** `resolve_block` used to iterate an inline
    /// `[Progression, Equipment, Status]` literal, so `Base`, `Archetype` and
    /// `Lex` **flat** modifiers were constructible, accepted, and silently
    /// discarded — while the *percent* filter was not source-filtered at all, so
    /// a `Lex` Percent applied and a `Lex` Flat vanished. A world rule worked or
    /// did nothing depending on which operator the author happened to pick.
    ///
    /// The enum must not be able to express something the resolver ignores, so
    /// the order lives here and [`ModifierSource::layer_index`] is a `match`
    /// with **no wildcard arm** — a seventh variant is a compile error there.
    ///
    /// ## What this does NOT close, stated so nobody trusts it too far
    ///
    /// This is a **closed set plus a hand-written companion list**, and Rust can
    /// force you to *handle* every variant (an exhaustive `match`) but cannot
    /// force an *array* to *contain* every variant. So:
    ///
    /// | Forget | Result |
    /// |---|---|
    /// | `ALL` only | `[_; COUNT]` gets 6 elements for a `COUNT` of 7 ⇒ **compile error** |
    /// | `COUNT` only | 7 elements for a `[_; 6]` ⇒ **compile error** |
    /// | `layer_index` | **compile error** (no wildcard arm) |
    /// | **all three** | compiles, and the source is silently dropped again |
    ///
    /// The last row is the residual. It is **discipline, not a mechanism** —
    /// do not describe it as a guard. A successor-chain (`next_layer() ->
    /// Option<Self>`) *looks* like it closes it and does not: an exhaustive
    /// `match` forces a variant to be HANDLED, never to be REACHED, so a variant
    /// nothing points at is still skipped.
    ///
    /// **That repo-level gate now EXISTS** — `scripts/closed-set-gate.py`
    /// (pre-commit) compares every `const NAME: [Enum; _]` against the enum it
    /// is typed over, so the last row is caught outside the compiler rather
    /// than by discipline. Done once for the whole tree, because `StatSlot`,
    /// `EffectOp`, `StatusFlag`, `DiscardReason` and `SeedRole` are all the
    /// same shape. A derive macro would still be stronger (it sees the variant
    /// list at expansion time); the gate is what shipped.
    /// (`StatSlot::ALL` is accidentally safer: its length is tied to
    /// `SLOT_COUNT`, which `StatBlock` also depends on.)
    ///
    /// **`Lex` as a MODIFIER is consumed, not rejected (PO-confirmed 2026-07-28).**
    /// DF7-A3's written layer order names `Lex` only as a *clamp*, and the Lex
    /// clamp already arrives through `resolve_block`'s separate `lex_clamps`
    /// parameter. So a `StatModifier` carrying `source: Lex` is a world-rule
    /// **contribution**, applied last among the flat layers — which is what this
    /// variant's own doc-comment says ("applied LAST and therefore inescapable")
    /// and what removes the asymmetry the audit found: `Lex` Percent applied
    /// while `Lex` Flat vanished, so a world rule worked or did nothing
    /// depending on the author's choice of operator. The alternative considered
    /// and rejected was forbidding `Lex` modifiers in the type system.
    /// How many layers there are. Naming it ties `ALL`'s length to something a
    /// reader must also change, which converts one silent-drop hole into a
    /// compile error — see the note on `ALL`.
    pub const COUNT: usize = 6;

    pub const ALL: [ModifierSource; Self::COUNT] = [
        ModifierSource::Base,
        ModifierSource::Archetype,
        ModifierSource::Progression,
        ModifierSource::Equipment,
        ModifierSource::Status,
        ModifierSource::Lex,
    ];

    /// Position in the locked layer order. Exhaustive by construction.
    pub const fn layer_index(self) -> usize {
        match self {
            ModifierSource::Base => 0,
            ModifierSource::Archetype => 1,
            ModifierSource::Progression => 2,
            ModifierSource::Equipment => 3,
            ModifierSource::Status => 4,
            ModifierSource::Lex => 5,
        }
    }
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

/// Intersect EVERY clamp declared for `slot`, returning `(min, max)`.
///
/// **XST-D8 (fixed 2026-07-28).** This was `clamps.iter().find(|c| c.slot == slot)`,
/// which takes the **first** clamp and discards the rest — so two content packs
/// both clamping `MaxHp` had their winner decided by `Vec` position, i.e. by
/// **load order**, reintroducing order-dependence through the back door of the
/// one mechanism advertised as order-independent (DF7-A5).
///
/// Intersection is order-independent *by construction*: `max` and `min` are both
/// commutative and associative, so shuffling the slice cannot change the result.
/// That is what makes the shuffle test in this module non-vacuous.
fn intersect_clamps(slot: StatSlot, clamps: &[Clamp]) -> Option<(i32, i32)> {
    let mut acc: Option<(i32, i32)> = None;
    for c in clamps.iter().filter(|c| c.slot == slot) {
        acc = Some(match acc {
            None => (c.min, c.max),
            Some((lo, hi)) => (lo.max(c.min), hi.min(c.max)),
        });
    }
    acc.map(|(lo, hi)| {
        // Contradictory declarations (`[50,100]` ∩ `[200,300]`) leave an EMPTY
        // range, and `i32::clamp` PANICS when min > max. The floor wins, which
        // is deterministic and never panics.
        //
        // DEFERRED past F2, with the reason. The loader validates the RULESET,
        // and clamps are not ruleset fields — they arrive per-actor from
        // equipment, status and world rules, which are content the loader never
        // sees. The refusal belongs wherever those clamps get declared, which
        // does not exist yet. Refusing here at RUNTIME instead is the wrong
        // trade: it would kill a live encounter over an author's contradiction.
        // This runtime rule exists so a contradiction degrades predictably, not
        // so contradictions are acceptable.
        (lo, hi.max(lo))
    })
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
    rules: &StatRules,
) -> StatBlock {
    // Zeroed, not defaults: the loop below `set`s EVERY slot, so the starting
    // values are dead. Starting from the defaults would look like they matter
    // and hide a future slot the loop stops covering.
    let mut out = StatBlock::zeroed();

    for slot in StatSlot::ALL {
        // base → archetype
        let mut flat: i64 = archetype.get(slot) as i64;

        // Flat layers, in source order. Iterating the ORDERED source list
        // rather than the modifier list keeps the result independent of the
        // order modifiers happen to arrive in.
        //
        // XST-D7: this iterates ALL SIX sources. It previously iterated three.
        for source in ModifierSource::ALL {
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

        // Exactly one division, at emit. `(base+flat) × max(0, 1000+Σpct) / 1000`.
        //
        // XST-D1 (fixed 2026-07-28) — the `max(0, …)` is DF07_002 **EC-2**, an
        // already-found, already-fixed SPEC defect that this implementation
        // reintroduced by writing the formula from the axiom list instead of
        // from the edge-case document. Without it, `Σpct = −1200` (two −60%
        // debuffs, ordinary play in a debuff-dense reality) yields a factor of
        // −0.2 and a **negative StrikePower**. AC-DF7-17 names this exact
        // mutation: *"drop the max(0, …) on factor → yields a negative stat."*
        // −100% is the floor; further debuffs are absorbed.
        let factor = (1000 + pct).max(0);
        let value = flat.saturating_mul(factor) / 1000;
        let mut value = value.clamp(i32::MIN as i64, i32::MAX as i64) as i32;

        // Author clamp, then world rule — in that order, see above.
        value = apply_clamps(value, slot, slot_clamps, lex_clamps);
        out.set(slot, value);
    }

    // Speed feeds the derivation, so MoveRange can only be derived once the
    // loop has finalised Speed.
    //
    // XST-D6 (fixed 2026-07-28) — the derivation used to be the LAST statement,
    // overwriting MoveRange with its own `clamp(1, tuning.max_move)` and
    // **discarding the Lex ceiling**. A Lex clamp of `max = 2` on MoveRange
    // produced 5. The Lex-clamp-last property is a recorded correction
    // (DF07_002 EC-1) with a dedicated test — and that test covers
    // `StrikePower`, so nothing covered the one slot where the invariant was
    // actually broken. Deriving and THEN re-clamping restores DF7-A3: a world
    // rule is applied last and is therefore inescapable.
    out.derive_move_range(rules);
    let mr = StatSlot::MoveRange;
    let ranged = apply_clamps(out.get(mr), mr, slot_clamps, lex_clamps);
    out.set(mr, ranged);

    out
}

/// Author clamp, then world rule — the DF7-A3 order, in one place so both the
/// per-slot loop and the `MoveRange` derivation cannot drift apart (XST-D6).
fn apply_clamps(value: i32, slot: StatSlot, slot_clamps: &[Clamp], lex_clamps: &[Clamp]) -> i32 {
    let mut value = value;
    if let Some((lo, hi)) = intersect_clamps(slot, slot_clamps) {
        value = value.clamp(lo, hi);
    }
    if let Some((lo, hi)) = intersect_clamps(slot, lex_clamps) {
        value = value.clamp(lo, hi);
    }
    value
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
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StatSnapshot {
    pub stats: StatBlock,
    pub epoch: StatEpoch,
}

impl Default for StatSnapshot {
    /// A snapshot that has never been resolved: a ZEROED block at epoch zero.
    ///
    /// Hand-written because `StatBlock` no longer has `Default` (see its doc).
    /// Zeroed is the honest value here — `is_stale` against any real epoch
    /// returns true, so an unresolved snapshot is one that must be re-resolved
    /// before it is read, which is exactly what it is.
    fn default() -> Self {
        Self { stats: StatBlock::zeroed(), epoch: StatEpoch::default() }
    }
}

impl StatSnapshot {
    /// True when any input version has moved since resolution. The caller
    /// re-resolves; nothing is ever patched in place (DF7-A2).
    pub fn is_stale(&self, current: &StatEpoch) -> bool {
        &self.epoch != current
    }
}
