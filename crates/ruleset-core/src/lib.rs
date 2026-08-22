//! `ruleset-core` — F1 of the doc-26 build order.
//!
//! The resolved [`Ruleset`], its canonical encoding, and the **real** content
//! digest (RLS-A13). No I/O: the provider stack, presets, merge algebra,
//! tombstones and validation are F2 (`ruleset-loader`).
//!
//! ## What F1 is actually for
//!
//! `RulesetDigest([0u8; 32])` appeared in 15 places (IMP-D6). An all-zero
//! digest makes RLS-A13's pin inert — two realities with different rules
//! produce indistinguishable events, and replay cannot detect that the rules
//! moved underneath it.
//!
//! But a digest over a struct that holds no game constants is **worse than an
//! inert one**: it answers *"did the rules change?"* with a confident **No**
//! while `MAX_HIT`, the variance band, the hit floor/ceiling and all ten slot
//! defaults sit in `commit-service` as Rust literals where no digest can see
//! them. So F1 also pulls those constants in — the work doc 26 §6 lists under
//! `D1`, moved forward because
//! [XST-D5](../../../docs/03_planning/LLM_MMO_RPG/27_extensibility_stress_test.md)'s
//! test (*edit one constant → the digest moves*) has nothing to edit until it
//! happens. **That the test could not be written was the tell.**
//!
//! ## The line this crate sits on
//!
//! **IMP-A1 — code owns SHAPE, config owns VALUES.** So: the damage chain's
//! order, its `max(1, …)` floors, the `/1000` per-mille divisor and the closed
//! [`StatSlot`] set stay in code; every number those laws multiply by lives
//! here and is hashed. The line is not "is it data" — it is *who may add a new
//! variant*.
//!
//! ## Dependency direction (F1-D1)
//!
//! [`sim_core::RulesetDigest`] stays in the kernel and this crate depends on
//! `sim-core`, not the other way round. `sim-core` states a zero-runtime-
//! dependency invariant (*"determinism is the product, and every dependency is
//! a determinism liability to audit"*) and only ever CARRIES the digest;
//! producing one from canonical bytes needs `blake3` and is this crate's job.

mod canon;
mod classification;
mod combat;
mod limits;
mod provenance;
mod modifier;
mod never_reuse;
mod quantity;
mod progression;
mod resource;
mod ruleset;
// `QTY-A12`'s resident-size budget for `Ruleset` and its repin log. No exports:
// the module IS one `const` assertion and the decision log behind it.
mod ruleset_size;
mod ruleset_codec;
mod slots;
mod stats;
mod verb;

pub use canon::{Canon, CanonEncode, CanonError, CanonReader};
// S1a — the field classification (RLS-A4/A16/A17, 16a). `FORBIDDEN_KEYS` is
// what the loader refuses a layer with; the rest is the classified table whose
// totality is a compile error to break.
pub use classification::{
    FieldClass, Floor, Mutability, Strategy, FORBIDDEN_KEYS, FORBIDDEN_VERB_KEYS,
};
pub use combat::CombatRules;
// `LIM-1` — the reality declares its own size; the engine only states what the
// binary can physically hold. `OrdinalSpace` doubles as the register of every
// author-extensible ordinal space, which is what nothing in the tree had.
pub use limits::{LimitError, Limits, OrdinalSpace};
// Q1 — L2 declared quantities (QTY-A5/A6): identities an author invents,
// ordinals the engine assigns, both inside the hashed bytes.
pub use never_reuse::OrdinalReuse;
// 2026-08-02 (actor hub, feature #1) — `ModifierOp` moved DOWN from
// `game-rules::stats::modifier` so the hub and the laws share ONE definition.
// `game_rules::stats::ModifierOp` re-exports it; no law changed.
pub use modifier::{ModifierOp, OpKind};
pub use quantity::{
    QuantityError, QuantityName, QuantityTable, MAX_DECLARED_QUANTITIES, MAX_QUANTITY_NAME_LEN,
};
pub use progression::{
    assert_paths_are_total, required_paths, schema_fingerprint, schema_paths,
    validate as validate_progression, Askable, FieldPath, BodyOrSoul, BreakthroughCondition, CapRule, CurveKind,
    Derivation, ProgressionDigest, ProgressionInvalid, ProgressionKindDecl, ProgressionTable,
    ProgressionType,
    TierDecl, WithinTierCurve, MAX_DECLARED_PROGRESSION_KINDS, MAX_TIERS_PER_KIND,
};
pub use provenance::{Provenance, RulesetEpoch};
// Q2 — QTY-A4 declared pools. A resource IS a declared quantity (one identity,
// one ordinal); this is the row that says it is a POOL and how it behaves.
pub use resource::{
    CeilingBinding, EngineRole, RegenType, ResourceDecl, ResourceError, ResourceTable,
    ZeroBehaviour,
};
pub use resource::MAX_DECLARED_RESOURCES;
// `M2` — CMD-1: a verb is a declared ROW with an ordinal, append-only and never
// reused. The engine resolves it and never branches on its name (CMD-6).
pub use verb::{
    EffectRow, RequirementRow, TargetRole, VerbDecl, VerbError, VerbTable, MAX_DECLARED_CUES, MAX_DECLARED_VERBS,
};
pub use ruleset::{
    LAW_VERSION, LAW_VERSION_UNVERSIONED, RULESET_SCHEMA_VERSION, ResolvedRuleset, Ruleset,
    SCHEMA_VERSION_OLDEST,
};
pub use slots::{SLOT_COUNT, StatSlot};
pub use stats::StatRules;

// Re-exported so a consumer of the rules does not also need a direct
// `sim-core` dependency just to name the digest type.
pub use sim_core::RulesetDigest;
