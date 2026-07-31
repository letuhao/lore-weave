//! `PGN-A2` — the answerable positions of the target schema, exported so the
//! pipeline's question set can be **asserted total** instead of assumed so.
//!
//! ## The problem this solves, stated as the red team stated it
//!
//! Doc 39 v1 claimed a `schema_fingerprint` made coverage *computable*. It did
//! not: comparing a brief's recorded version to the type's version is green for
//! a brief with **zero questions**, because deleting a question row moves
//! neither operand. `NV-2`, the subject cannot vary.
//!
//! The second half of the finding is the harder one. The schema is **Rust** and
//! the brief lives in a **Python** service, so any list of "what must be asked"
//! computed on the Python side is *a second implementation of a Rust type — a
//! mirror nothing forces to agree*, which is `CPL-A2`'s own objection one tier
//! up.
//!
//! So the list is exported from the side that owns it. Rust is the SoT, the
//! JSON under `contracts/` is generated from it, and a drift test fails if the
//! committed file stops matching. Python reads the JSON and never re-derives
//! anything.
//!
//! ## Why the list is hand-written and still cannot drift
//!
//! There is no derive walking the type graph, and adding one would be a large
//! dependency for a small job. Instead [`assert_paths_are_total`] destructures
//! every type **exhaustively, with no `..`** — the same mechanism
//! `CanonEncode for Ruleset` already relies on, and the one that caught
//! `law_version` when it was added. A new field is a **compile error** until it
//! is given a path here, and the pinned counts in the tests are a second,
//! independent proof of the same property.

use super::{
    BodyOrSoul, BreakthroughCondition, CapRule, CurveKind, Derivation, ProgressionKindDecl,
    ProgressionType, TierDecl, WithinTierCurve,
};

/// Whether the pipeline must ASK for a position, or may fill it without asking.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Askable {
    /// A human or a source must supply it. The brief owes it a question.
    Required,
    /// May be filled without asking — and the reason is carried, because
    /// *"defaultable"* with no reason is how a required field quietly becomes
    /// optional.
    Defaultable(&'static str),
    /// Computed by the procedural stage from shape × policy. **Never asked, and
    /// never answered by a model** (`PGN-A5`).
    Magnitude(&'static str),
}

/// One answerable position.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FieldPath {
    /// Dotted, with `[]` for a repeated element: `kind.tier[].tier_max`.
    pub path: &'static str,
    pub askable: Askable,
}

/// Every position in the reachable graph of [`ProgressionKindDecl`].
///
/// **Flat, not nested**, because the consumer is a question set and a question
/// is asked about a position rather than about a subtree. `kind.tier[]`
/// positions are asked once and expanded per tier by the fold (`PGN-A11`: the
/// approval unit is the assertion class, not the row).
pub fn schema_paths() -> &'static [FieldPath] {
    use Askable::*;
    &[
        FieldPath { path: "kind.quantity", askable: Required },
        FieldPath { path: "kind.progression_type", askable: Required },
        FieldPath {
            path: "kind.body_or_soul",
            askable: Defaultable("PROG_001 §4.3 makes Body the V1 default; a soul-bound kind is an explicit authorial choice"),
        },
        FieldPath { path: "kind.curve", askable: Required },
        FieldPath {
            path: "kind.curve.rate_milli",
            askable: Magnitude("a training rate is a balance decision, not a fact the book states"),
        },
        FieldPath {
            path: "kind.curve.base_rate_milli",
            askable: Magnitude("the initial gain of a Log curve - a tuning value, and a book that says a skill starts fast says nothing about how fast"),
        },
        FieldPath {
            path: "kind.curve.difficulty_milli",
            askable: Magnitude("how sharply a Log curve approaches its ceiling; pure balance, and the shape token in the creative structure is what a source CAN support"),
        },
        FieldPath { path: "kind.cap_rule", askable: Required },
        FieldPath {
            path: "kind.cap_rule.cap",
            askable: Magnitude("a ceiling is a balance decision; PROG_001 §5.4's cap is a raw count nobody writes in a novel"),
        },
        FieldPath {
            path: "kind.initial_value",
            askable: Magnitude("where an ordinary person starts NUMERICALLY; the ordinal start is `kind.initial_tier`, which IS asked"),
        },
        FieldPath { path: "kind.initial_tier", askable: Required },
        FieldPath {
            path: "kind.derives_from",
            askable: Defaultable("most kinds derive from nothing; absence is a complete statement"),
        },
        FieldPath {
            path: "kind.derives_from.rate_factor_milli",
            askable: Magnitude("how MUCH a derivation helps is balance"),
        },
        FieldPath { path: "kind.tier_count", askable: Required },
        FieldPath { path: "kind.tier[].tier_index", askable: Required },
        FieldPath {
            path: "kind.tier[].tier_max",
            askable: Magnitude("PGN-A5's headline case - the book names tiers and never their cost"),
        },
        FieldPath { path: "kind.tier[].within_tier_curve", askable: Required },
        FieldPath {
            path: "kind.tier[].breakthrough",
            askable: Required,
        },
        FieldPath {
            path: "kind.tier[].initial_value_on_advance",
            askable: Defaultable("PROG_001 Q2g: typically 0, rarely a carry-over"),
        },
        // PGN-A18 — not in the hashed bytes, and still ANSWERABLE: a ladder with
        // no names ships `tier_9` to a player. Excluding them here because they
        // are unhashed would be the exact category error that left T10 NOT
        // ENFORCED for three slices.
        FieldPath { path: "kind.name", askable: Required },
        FieldPath {
            path: "kind.description",
            askable: Defaultable("prose about a kind is enrichment, and a reality with none is complete"),
        },
        FieldPath { path: "kind.tier[].name", askable: Required },
    ]
}

/// The positions a question set MUST cover.
pub fn required_paths() -> Vec<&'static str> {
    schema_paths()
        .iter()
        .filter(|f| matches!(f.askable, Askable::Required))
        .map(|f| f.path)
        .collect()
}

/// A digest over the whole path list, including each position's `askable`.
///
/// Moves when a position is added, removed, **or reclassified** — the last one
/// matters most: silently turning a `Required` into a `Defaultable` is how a
/// question disappears without the list getting shorter.
pub fn schema_fingerprint() -> String {
    let mut h = blake3::Hasher::new();
    h.update(b"lw.progression.schema.v1");
    for f in schema_paths() {
        h.update(f.path.as_bytes());
        h.update(&[0]);
        h.update(match f.askable {
            Askable::Required => b"R".as_slice(),
            Askable::Defaultable(_) => b"D".as_slice(),
            Askable::Magnitude(_) => b"M".as_slice(),
        });
        h.update(&[0]);
    }
    h.finalize().to_hex().to_string()
}

/// **The totality proof.** Destructures every type in the reachable graph with
/// no `..`, so a new field is a COMPILE ERROR until [`schema_paths`] names it.
///
/// Takes a value rather than being a `const` because that is what makes the
/// destructure real; it is called from a test, which is what keeps it from
/// being deleted as dead code. Exactly the shape
/// `assert_classification_is_total` already uses.
pub fn assert_paths_are_total(d: &ProgressionKindDecl) {
    let ProgressionKindDecl {
        quantity: _,
        progression_type,
        body_or_soul,
        curve,
        tiers,
        cap_rule,
        initial_value: _,
        initial_tier: _,
        derives_from,
    } = d;

    match progression_type {
        ProgressionType::Attribute | ProgressionType::Skill | ProgressionType::Stage => {}
    }
    match body_or_soul {
        BodyOrSoul::Body | BodyOrSoul::Soul | BodyOrSoul::Both => {}
    }
    match curve {
        CurveKind::Linear { rate_milli: _ } => {}
        CurveKind::Log { base_rate_milli: _, difficulty_milli: _ } => {}
        CurveKind::Stage => {}
    }
    match cap_rule {
        CapRule::SoftCap { cap: _ } | CapRule::HardCap { cap: _ } => {}
        CapRule::TierBased | CapRule::Unbounded => {}
    }
    if let Some(Derivation { source_quantity: _, rate_factor_milli: _ }) = derives_from {}
    for t in tiers {
        let TierDecl {
            tier_index: _,
            tier_max: _,
            within_tier_curve,
            breakthrough,
            initial_value_on_advance: _,
        } = t;
        match within_tier_curve {
            WithinTierCurve::Linear { rate_milli: _ } => {}
            WithinTierCurve::Log { base_rate_milli: _, difficulty_milli: _ } => {}
        }
        match breakthrough {
            BreakthroughCondition::AtMax | BreakthroughCondition::AuthorOnly => {}
        }
    }
}
