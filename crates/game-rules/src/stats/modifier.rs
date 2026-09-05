//! Contributions and clamps: where a number came from, and what bounds it.

use ruleset_core::StatSlot;

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

/// How a contribution combines.
///
/// **Re-exported, not defined here (2026-08-02).** The definition moved down to
/// `ruleset-core` when the actor hub needed the same op set for its contribution
/// rows: the hub sits beneath the features and combat is a feature, so a
/// hub -> `game-rules` dependency would become a cycle the day combat becomes a
/// plugin. `game_rules::stats::ModifierOp` still names the same type and no law
/// changed — see `ruleset-core/src/modifier.rs` for the full reasoning.
pub use ruleset_core::ModifierOp;

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
