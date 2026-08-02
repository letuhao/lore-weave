//! Who produced this item — the model, or the engine standing in for it.
//!
//! # The defect
//!
//! `L3Result` and `L4Result` each promise "every input classified/narrated **exactly once** —
//! the disjoint union of LLM-accepted results and §6 canonical-default fallbacks", and each
//! reports how many came from the fallback half in a single `fallback_count`.
//!
//! That count is real and it is *beside* the data. A consumer holding a `Vec<L4Narration>`
//! holds a mix of a model's work and engine boilerplate with nothing on the items to tell them
//! apart, so the only way to know is to have carried the count along and divided the set by
//! subtraction — which nothing obliges it to do, and which cannot identify *which* ones anyway.
//!
//! Measured before writing this, because the registry's severity claim deserved checking: the
//! narrations never leave the harness today. Both consumers are report formatters and both
//! already print `fallback_count`. So this is a type-level gap, not a live one — and the fix
//! is cheap precisely because it is early. The moment one of these is persisted or served,
//! "the model wrote this" and "the engine filled it in" become the same row.
//!
//! # Why on the item and not only in the result
//!
//! The same reason `critic_policy` blanks a refused critic's fields instead of setting a flag,
//! and the same reason `guardstatus.Report` carries `Unchecked` instead of leaving the caller
//! to infer it: a fact that travels WITH the data cannot be dropped by a consumer that forgot
//! to look for it. `fallback_count` stays — it is the aggregate, and a test now pins the two
//! against each other so they cannot disagree.

use serde::{Deserialize, Serialize};

/// Where one classification or narration came from.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Provenance {
    /// The model produced it and it passed validation.
    Llm,
    /// The §6 engine default, standing in for a zone/object the model never narrated validly.
    CanonicalDefault,
}

/// The serde default for a field deserialised **out of the model's tool call**.
///
/// Named rather than derived via `#[derive(Default)]`, because a bare `Default` that returns
/// `Llm` is a fail-OPEN default: it would silently attribute any future construction site that
/// forgets the field to the model. This function has exactly one legitimate caller — serde,
/// filling a field the LLM's JSON does not carry because the LLM is the one sending it — and
/// its name is there to say so at the point of use.
pub fn from_tool_call() -> Provenance {
    Provenance::Llm
}

impl Provenance {
    /// True when the engine, not a model, produced this item.
    pub fn is_engine_default(self) -> bool {
        matches!(self, Provenance::CanonicalDefault)
    }
}
