//! RLS-A15 — the third side, and the one that must NOT reach the digest.
//!
//! > *There is a third side, `Provenance` — stored with the reality, **excluded
//! > from the digest**, never sent to an island.*
//!
//! Discovered by the doc-16a field sweep: `authoring_metadata` carries
//! `author_user_id`, `total_llm_cost_usd` and authoring timestamps. Include
//! them and two behaviourally identical realities never dedupe, and
//! re-authoring emits a spurious epoch for a change that altered nothing.
//!
//! **The test RLS-A15 gives is worth keeping in front of you when adding a
//! field anywhere in this crate:** *can this differ between two behaviourally
//! identical realities?* → Provenance.
//!
//! ## The exclusion is structural
//!
//! `Provenance` deliberately has **no [`crate::CanonEncode`] impl**. It is not
//! omitted from a hand-written encoder that someone must remember not to
//! extend — it cannot be hashed, because the trait bound would not be
//! satisfied. Adding one would be the visible decision it should be.

/// RLS-A13 — per-reality monotonic. **Ordering, not identity.**
///
/// The digest answers "are these the same rules?"; the epoch answers "which
/// came first?", so `which came first` needs no hash comparison. Keeping the
/// two apart is why a mutable `ruleset_version` row was rejected (RLS-D7): a
/// version number that is also identity can be edited in place, and the
/// resulting replay divergence is invisible until an oracle disagrees.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Default)]
pub struct RulesetEpoch(pub u32);

/// Authoring lineage. Stored with the reality, excluded from the digest, never
/// sent to an island.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Provenance {
    /// Which user authored the reality this ruleset was resolved for.
    pub author_user_id: String,
    /// RLS-D20 — the preset lineage is RECORDED here rather than versioned,
    /// because early binding (RLS-A3) means a preset edit can affect no
    /// existing reality, and the resolved bytes on disk are a strictly better
    /// answer to "what did this reality come from?" than preset archaeology.
    pub preset_ref: String,
    pub preset_version: u32,
    /// Authoring wall-clock, in ms. **This is why Provenance exists as a
    /// separate side**: RLS-D13 forbids anything wall-clock-derived inside the
    /// determinism-pinned artifact, and this is the field that would otherwise
    /// have smuggled one in.
    pub created_at_ms: u64,
    /// Authoring spend, in USD milli-units. Integer because RLS-A8 keeps floats
    /// out of stored rules artifacts — even the ones that are not hashed, so
    /// the discipline has no exception to learn.
    pub total_llm_cost_usd_milli: u64,
}
