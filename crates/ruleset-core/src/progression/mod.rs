//! `S-1a` — the L2 **progression** declaration, and the first thing in this crate
//! that is deliberately NOT inline in [`crate::Ruleset`].
//!
//! ## Why this table lives outside the `Ruleset` struct
//!
//! Every other declared table here is a fixed-size array, because
//! `Ruleset::engine_default` is a `const fn` and a heap pointer would put the
//! payload where `size_of` cannot see it — the `QTY-A6 ⊥ QTY-A12` trap.
//! Progression cannot follow that pattern and the reason is structural, not a
//! matter of degree:
//!
//! * `size_of::<Ruleset>()` is **exactly 2312**, and
//!   [`crate::ruleset`]'s assertion is `<= 2312`. Headroom is zero — measured,
//!   not assumed. Any inline addition trips it.
//! * A `TierDecl` in `PROG_001` §5.2 transitively owns `String` (`I18nBundle`,
//!   `PlaceTypeRef`), `Vec` and `HashMap` (`BreakthroughCondition::AtMaxPlus`'s
//!   four heap-carrying `Option`s). It can never be `Copy`, never be
//!   `const`-constructed, and **cannot be measured by `size_of` at all.**
//! * `PROG_001` §5.6's own worked example is **24 tiers in one kind**, and the
//!   count is per-reality. There is no honest fixed width.
//!
//! So `Ruleset` carries a **32-byte digest** of this table and the bytes live in
//! a content-addressed store (`PGN-R1`). That is the shape
//! `ruleset-loader`'s store already uses one level up — *"the envelope carries
//! the digest, not the ruleset"* — applied one level down.
//!
//! ## What is NOT in these bytes, and why
//!
//! **No strings.** Not one. `PROG_001` requires `display_name`, `description`
//! and `TierDecl.name` as `I18nBundle`s, and every one of them lives in a
//! separate label artifact that is **not hashed** (`PGN-A18`). If a tier name
//! were in here, fixing a Vietnamese translation would move the reality's
//! digest and strand a running world. [`crate::quantity`] already made this
//! call for declared quantities — the hashed name is *"a MACHINE key … its
//! human-readable label is localized content and lives elsewhere"* — and this
//! module inherits it rather than re-deciding it.
//!
//! **No `AtMaxPlus`.** `PROG_001` §5.3's third variant carries four fields and
//! **every one is a cross-element reference**: an item, a place, an actor class,
//! a fiction-time window. None of those element modules exists. `PGN-A20` is
//! explicit that an out-of-scope element is *a refusal that names its owner,
//! never a smaller schema* — so the refusal is produced by the **pipeline** at
//! admission, where it can carry the owning module's name in its findings, and
//! this enum simply leaves discriminant `2..` free. Reserving the fields here
//! instead would put dead bytes in every reality's digest that `QTY-A10(c)`
//! then forbids removing — the mistake `QTY-A4`'s unbuilt `deps`/`tags` avoided.
//!
//! **No `TrainingRuleDecl`.** Same reason, decided by the PO: it crosses the
//! world-generation pipeline (`LocationMatch` → a place, `InstrumentMatch` → an
//! item) and cannot complete now.

mod table;
mod validate;

pub use table::ProgressionTable;
pub use validate::{validate, ProgressionInvalid};

use crate::quantity::MAX_DECLARED_QUANTITIES;

/// The ordinal capacity for declared progression kinds.
///
/// **An alias, not a second constant.** A progression kind *is* a declared
/// quantity — `qi_cultivation` is one named per-actor number — so it shares the
/// `QTY-A5` ordinal space with pools and every other declared identity. Two
/// numbering schemes for one identity is precisely what `QTY-A5` exists to
/// prevent, and two constants that must stay equal are two constants that can
/// stop being equal. This is the same correction the PO forced on `Q2 B1`.
pub const MAX_DECLARED_PROGRESSION_KINDS: usize = MAX_DECLARED_QUANTITIES;

/// The most tiers one staged kind may declare.
///
/// A **decode** bound, not a layout one: nothing here is a fixed-size array, so
/// raising this is a code change that moves no existing digest (only `0..n` is
/// encoded — the same property [`crate::quantity`] documents for `N`). It exists
/// so a malformed or hostile buffer cannot ask us to allocate without limit.
/// `PROG_001` §5.6's worked example uses 24.
pub const MAX_TIERS_PER_KIND: usize = 64;

/// `PROG_001` §4.2. `ResourceBound` is `V1+30d` and deliberately absent.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum ProgressionType {
    /// Innate, slow-changing, soft-capped — 悟性, `STR`, `INT`.
    Attribute = 0,
    /// Learned by doing — 劍術, swordsmanship, negotiation.
    Skill = 1,
    /// Tier-based with breakthrough — 內功, 練氣 → 築基.
    Stage = 2,
}

/// `PROG_001` §4.3 — which half of a `xuyên không` transfer this follows.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum BodyOrSoul {
    /// Martial, body-cultivation, motor skill. The V1 default.
    Body = 0,
    /// Academic, social, cognitive — travels with the soul to a new body.
    Soul = 1,
    /// Rare, and an authorial choice rather than a derivable property.
    Both = 2,
}

/// `PROG_001` §5.4. The `cap` is in raw units, not milli-units — it bounds a
/// `raw_value`, and `raw_value` is a count.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CapRule {
    /// Training past `cap` still accrues, with diminishing returns.
    SoftCap { cap: u64 },
    /// Training past `cap` is **refused**. `raw_value` is strictly `<= cap`.
    ///
    /// Not a shade of `SoftCap` — the opposite. One is a slow grind, the other
    /// is a wall, and an author who meant one and got the other spends an
    /// afternoon wondering why.
    HardCap { cap: u64 },
    /// The cap is the current tier's `tier_max`, and advances on breakthrough.
    TierBased,
    /// No cap. Rare.
    Unbounded,
}

/// `PROG_001` §5.1, with the closure-pass extension applied: the two `f32`
/// fields are **fixed-point milli-units**, because *"floats in a replayed,
/// event-sourced engine are a determinism liability"* (`DF7-A4`, `TDIL-A9`).
/// `1.5` is authored as a decimal and normalized to `1500` at load (`RLS-A7`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CurveKind {
    /// `rate_per_train_unit`, ×1000. `1000` = standard.
    Linear { rate_milli: u32 },
    /// Diminishing approach to the cap.
    Log { base_rate_milli: u32, difficulty_milli: u32 },
    /// The tiers carry the shape; see [`ProgressionKindDecl::tiers`].
    Stage,
}

/// `PROG_001` §5.2's per-tier override. Same milli-unit rule as [`CurveKind`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WithinTierCurve {
    Linear { rate_milli: u32 },
    Log { base_rate_milli: u32, difficulty_milli: u32 },
}

/// `PROG_001` §5.3, minus the variant whose every field is a cross-element
/// reference. See the module doc — the absence is `PGN-A20`, not an oversight.
///
/// Discriminant `2..` is **reserved for `AtMaxPlus`**. Adding a variant later
/// moves no existing digest, because a discriminant nothing encodes costs
/// nothing; adding its four unused *fields* now would cost every reality bytes
/// it can never remove.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum BreakthroughCondition {
    /// `raw_value == tier_max` is sufficient; advance automatically.
    AtMax = 0,
    /// Only an explicit `Forge:TriggerBreakthrough` advances this tier.
    AuthorOnly = 1,
}

/// One tier of a staged kind. **Carries no name** — see the module doc.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TierDecl {
    /// 0-based, dense, and equal to this row's index. Encoded anyway so a
    /// decoder can refuse a buffer whose order was lost, rather than trusting
    /// position.
    pub tier_index: u8,
    /// The `raw_value` ceiling at this tier.
    pub tier_max: u64,
    pub within_tier_curve: WithinTierCurve,
    pub breakthrough: BreakthroughCondition,
    /// `PROG_001` Q2g — typically 0, rarely a carry-over.
    pub initial_value_on_advance: u64,
}

/// `PROG_001` §4.4's `DerivationDecl`. V1 is Skill ← Attribute, training-rate
/// only; the query-value bonus is `PROG-D9` and not built.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Derivation {
    /// The source kind, by its **quantity ordinal** — not a free string.
    /// `QTY-D6`: a `kind_id` refers to an L2 declared quantity ordinal.
    pub source_quantity: u16,
    /// `training_rate_factor` ×1000. The multiplier is
    /// `1000 + source_value * rate_factor_milli`, in saturating integer maths.
    pub rate_factor_milli: u32,
}

/// One declared progression kind.
///
/// Not `Copy`: `tiers` is a `Vec`, which is the whole point of this module.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProgressionKindDecl {
    /// The declared quantity this kind IS, by its `QTY-A5` ordinal.
    pub quantity: u16,
    pub progression_type: ProgressionType,
    pub body_or_soul: BodyOrSoul,
    pub curve: CurveKind,
    /// Non-empty **iff** `curve` is [`CurveKind::Stage`]. Enforced by
    /// [`validate`], not by convention.
    pub tiers: Vec<TierDecl>,
    pub cap_rule: CapRule,
    pub initial_value: u64,
    /// `Some` iff staged. `PROG_001` §4.4: *"None for Attribute/Skill"*.
    pub initial_tier: Option<u8>,
    pub derives_from: Option<Derivation>,
}
