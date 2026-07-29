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
mod provenance;
mod quantity;
mod ruleset;
mod slots;
mod stats;

pub use canon::{Canon, CanonEncode, CanonError, CanonReader};
// S1a — the field classification (RLS-A4/A16/A17, 16a). `FORBIDDEN_KEYS` is
// what the loader refuses a layer with; the rest is the classified table whose
// totality is a compile error to break.
pub use classification::{FieldClass, Floor, Mutability, Strategy, FORBIDDEN_KEYS};
pub use combat::CombatRules;
// Q1 — L2 declared quantities (QTY-A5/A6): identities an author invents,
// ordinals the engine assigns, both inside the hashed bytes.
pub use quantity::{
    QuantityError, QuantityName, QuantityTable, MAX_DECLARED_QUANTITIES, MAX_QUANTITY_NAME_LEN,
};
pub use provenance::{Provenance, RulesetEpoch};
pub use ruleset::{
    LAW_VERSION, LAW_VERSION_UNVERSIONED, RULESET_SCHEMA_VERSION, ResolvedRuleset, Ruleset,
    SCHEMA_VERSION_OLDEST,
};
pub use slots::{SLOT_COUNT, StatSlot};
pub use stats::StatRules;

// Re-exported so a consumer of the rules does not also need a direct
// `sim-core` dependency just to name the digest type.
pub use sim_core::RulesetDigest;
