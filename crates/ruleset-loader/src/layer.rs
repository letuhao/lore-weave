//! RLS-A3 — the provider stack, and why it is resolved ONCE.
//!
//! > *Presets are authoring-time templates, resolved once (early binding). At
//! > reality creation the stack is resolved top-to-bottom, validated,
//! > normalized, hashed, and stored as an immutable resolved ruleset. A later
//! > edit to the `wuxia` preset never touches a reality that already exists.*
//!
//! Replay-safety is then **structural rather than procedural**: there is no
//! path by which a reality's rules change without an event in its own log.
//!
//! The accepted cost is recorded in doc 16 so it is a decision and not a
//! discovery: **a balance fix cannot be shipped to 200 live realities.** Each
//! must be re-bound explicitly, and the bulk `RebindPreset` admin action is
//! deferred (RLS-D11) *knowing* the demand for it arrives the first time a
//! preset ships a broken loot table.

/// The five layers, in priority order (doc 16 §3).
///
/// A closed set: adding a sixth is an engine release, because the merge order
/// is part of what a digest means. `closed-set-gate` checks `ALL` against it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Layer {
    /// Priority 0 — the shipped artifact in the engine binary. RLS-D2: an
    /// artifact, not prose.
    EngineDefault,
    /// 10 — an authoring-time template (`wuxia` / `modern` / `scifi`).
    Preset,
    /// 20 — the book's authored manifest contribution.
    Book,
    /// 30 — this reality's own overrides.
    Reality,
    /// 40 — a live author edit via a `Forge:*` admin action.
    ///
    /// The one layer that is mutable after reality creation, and therefore the
    /// one that **is an event** (doc 16 §9). F2 accepts it as a file layer;
    /// epoch-switch-as-ingress is a later slice, so a Forge edit today is a
    /// re-resolution rather than an ordered live switch.
    ForgeOverride,
}

impl Layer {
    pub const COUNT: usize = 5;

    /// Ascending priority — the fold order. A later layer wins.
    pub const ALL: [Layer; Self::COUNT] = [
        Layer::EngineDefault,
        Layer::Preset,
        Layer::Book,
        Layer::Reality,
        Layer::ForgeOverride,
    ];

    /// Doc 16 §3's integer priorities, kept as the DOCUMENTED values rather
    /// than as `0..5`: the numbers appear in the spec table and in any
    /// diagnostic an author reads, and renumbering them to be dense would make
    /// the code and the document disagree for no gain. The gaps are also where
    /// a future layer lands without renumbering the rest.
    pub const fn priority(self) -> u8 {
        match self {
            Layer::EngineDefault => 0,
            Layer::Preset => 10,
            Layer::Book => 20,
            Layer::Reality => 30,
            Layer::ForgeOverride => 40,
        }
    }

    pub const fn name(self) -> &'static str {
        match self {
            Layer::EngineDefault => "engine_default",
            Layer::Preset => "preset",
            Layer::Book => "book",
            Layer::Reality => "reality",
            Layer::ForgeOverride => "forge_override",
        }
    }
}
