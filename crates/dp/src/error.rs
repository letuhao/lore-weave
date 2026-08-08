//! `DP-K3` — the one error type every SDK primitive returns.
//!
//! # Why this lands before slice 4, and not with it
//!
//! [`crate`]'s own module doc says slices 3 and 4 each need *"a control plane, a
//! `channels` table, and a settled `DpError`"*. The sealed build order says the
//! same from the other side: *"`REC-65` before slice 4"*. `REC-65` was filed
//! 2026-07-26 — *"`DP-K3` is LOCKED at 21 variants; 5+ docs mint satellites"* —
//! and adjudicated 2026-08-07 by `REC-102b` on a full census. **Typing the write
//! surface against an unsettled enum bakes the drift into the first line of the
//! SDK.**
//!
//! So the variant list here is not a design choice. It is a transcription of an
//! adjudicated one, and [`crate::error`]'s oracle test parses `DP-K3` out of the
//! locked markdown to prove the transcription still matches.
//!
//! # An enum ships where the id newtypes could not
//!
//! Slice 3's `RealityId` was written and reverted the same hour: its whole point
//! is a crate-private constructor, and a crate-private constructor with no
//! in-crate caller is dead code — its producer is session bind, which needs a
//! control plane. `pub` enum variants ARE their own constructors, so this type
//! is complete the moment it is declared. That difference is why the slice
//! starts here.
//!
//! # What is DEFERRED, and why saying so beats shipping it
//!
//! Four of `DP-K3`'s variants carry types this workspace has not built:
//! `NodeId`, `Timestamp`, `ActorId`, `CausalityToken`. They are listed in
//! [`DEFERRED_VARIANTS`] with the type each waits on, and the oracle test
//! **requires that list to account for every doc variant this file omits**. A
//! variant quietly dropped fails; a variant quietly invented fails. The list is
//! the deferral's mechanism, not a comment about it.

use core::fmt;
use core::time::Duration;

// `DP-K3`'s field type is written `Tier`, and in THIS crate `Tier` is the
// sealed marker TRAIT (`T0`..`T3` implement it). The runtime enum the spec
// means — `DP-K1`'s "Tier enum (runtime)" — is `TierLevel` here, because slice 1
// found the name taken and followed the rule `aggregate.rs` states for exactly
// this: "name a thing for what it is, and when a name is taken, take a
// different one and say so" (`FLOW-24`, which lists CircuitOpen/RateLimited as
// two more of the same collision class).
//
// So a `DpError` carries a `TierLevel`, not a `Tier`. Caught by rustc
// (`E0782: expected a type, found a trait`) rather than by review, which is the
// argument for transcribing against a compiler instead of a reading.
use crate::TierLevel;

/// Doc variants deliberately not yet implemented, each with the unbuilt type
/// that blocks it.
///
/// This is read by `tests/spec_oracle.rs`, which is what stops it becoming a
/// list nobody revisits: the moment the blocking type exists, nothing here
/// changes colour by itself — but the moment a variant is dropped or invented
/// WITHOUT a row, the oracle reds naming it.
///
/// `CausalityToken` is `DP-Ch38`, `ActorId` is the turn-slot surface
/// (`DP-Ch51`), `NodeId` is `DP-K1`'s node identity and `Timestamp` is the
/// wall-clock type the channel-lifecycle variants carry. All four arrive with
/// the surfaces that construct them.
pub const DEFERRED_VARIANTS: &[(&str, &str)] = &[
    ("WrongWriterNode", "NodeId"),
    ("WrongChannelWriter", "NodeId"),
    ("ChannelPaused", "Timestamp"),
    ("CausalityWaitTimeout", "CausalityToken"),
    ("TurnSlotHeldBy", "ActorId"),
];

/// Every SDK primitive returns `Result<T, DpError>`.
#[derive(Debug)]
#[non_exhaustive]
pub enum DpError {
    /// The caller addressed a reality its session is not bound to (`DP-R1`).
    RealityMismatch { ctx: String, requested: String },

    /// The session's capability has passed its expiry; re-bind required.
    CapabilityExpired,

    /// The capability is live but does not grant this aggregate at this tier.
    CapabilityDenied { aggregate: &'static str, tier: TierLevel },

    /// Backpressure. See [`DpError::is_backpressure`].
    RateLimited { tier: TierLevel, retry_after: Duration },

    /// Backpressure. See [`DpError::is_backpressure`].
    CircuitOpen { service: String },

    /// `DP-Ch37`: the operation targets a channel that has been dissolved.
    ChannelDissolved { channel: String },

    /// `DP-Ch37`: a channel with living descendants cannot itself be dissolved.
    ChannelHasDescendants { channel: String, descendant_count: u32 },

    /// `DP-Ch37`: already in the requested state; returned without effect.
    ChannelAlreadyInState { channel: String, state: String },

    /// `DP-Ch42`: the control plane has no record of this session.
    SessionNotFound { session_id: String },

    /// `DP-Ch52`: a turn slot longer than the five-minute hard ceiling.
    ExpectedDurationTooLong { requested: Duration },

    /// The aggregate's declared tier does not permit the requested operation.
    TierViolation { aggregate: &'static str, requested: TierLevel, allowed: TierLevel },

    /// No such aggregate under this scope.
    AggregateNotFound { aggregate: &'static str, id: String },

    /// The stored schema version is not the one this build expects.
    SchemaVersionMismatch { on_disk: u32, expected: u32 },

    /// The control plane could not be reached; capability cannot be refreshed.
    ControlPlaneUnavailable { reason: String },

    /// `DP-Ch18`: the resume token predates retention, so a gap-free stream
    /// cannot be served.
    ///
    /// Explicit because the alternative is delivering with a silent gap, and in
    /// an event-linear game a silent gap is missing STORY, not a stale cache.
    ResumeTokenExpired { requested: u64, earliest: u64 },

    /// `DP-Ch26`: an aggregator panicked, was replayed from its snapshot, and
    /// panicked on the same event again.
    ///
    /// Distinct from every other variant in that **no retry can clear it** — an
    /// operator must unregister the aggregator or fix its code.
    AggregatorStuck { aggregator: &'static str, channel: String, event_id: u64 },

    /// The backend failed for a reason the SDK does not model.
    BackendIo(Box<dyn std::error::Error + Send + Sync>),
}

impl DpError {
    /// Is this the store telling the caller to SLOW DOWN?
    ///
    /// `DP-R6` says backpressure *"MUST be propagated by callers"* rather than
    /// swallowed and retried, and `DP-K11`'s `forbid_swallowed_backpressure`
    /// lint is specified to flag `.ok()` / `.unwrap_or_default()` applied to a
    /// `Result<_, DpError>` *"where the error variant set intersects
    /// {RateLimited, CircuitOpen}"*.
    ///
    /// **That set is here, in code, for the same reason
    /// [`TierLevel::SURVIVES_STORE_OUTAGE`] is**: slice 1 put `REC-102c`'s degraded
    /// -mode partition in a `const` so *"a decision made in prose today cannot
    /// quietly become prose-only tomorrow."* A lint that hardcodes its own copy
    /// of this pair is a second source of truth for the partition, and the two
    /// would drift the first time a variant joined it.
    ///
    /// `#[non_exhaustive]` on the enum plus an explicit non-backpressure arm
    /// below means adding a variant without classifying it fails to compile
    /// here — the classification cannot be forgotten, only decided.
    pub fn is_backpressure(&self) -> bool {
        match self {
            Self::RateLimited { .. } | Self::CircuitOpen { .. } => true,

            // Listed rather than `_ => false`, so a new variant is a COMPILE
            // ERROR at this match instead of a silent "not backpressure".
            Self::RealityMismatch { .. }
            | Self::CapabilityExpired
            | Self::CapabilityDenied { .. }
            | Self::ChannelDissolved { .. }
            | Self::ChannelHasDescendants { .. }
            | Self::ChannelAlreadyInState { .. }
            | Self::SessionNotFound { .. }
            | Self::ExpectedDurationTooLong { .. }
            | Self::TierViolation { .. }
            | Self::AggregateNotFound { .. }
            | Self::SchemaVersionMismatch { .. }
            | Self::ControlPlaneUnavailable { .. }
            | Self::ResumeTokenExpired { .. }
            | Self::AggregatorStuck { .. }
            | Self::BackendIo(_) => false,
        }
    }

    /// The variant's name, for telemetry and for the oracle test.
    ///
    /// Deliberately NOT `Debug`-derived-and-truncated: `format!("{self:?}")`
    /// would embed the payload, so a `CircuitOpen { service }` would emit one
    /// metric label per service and produce unbounded cardinality — the class
    /// `dp-kernel::turn_errors` already solved with its own `as_str`.
    pub fn variant_name(&self) -> &'static str {
        match self {
            Self::RealityMismatch { .. } => "RealityMismatch",
            Self::CapabilityExpired => "CapabilityExpired",
            Self::CapabilityDenied { .. } => "CapabilityDenied",
            Self::RateLimited { .. } => "RateLimited",
            Self::CircuitOpen { .. } => "CircuitOpen",
            Self::ChannelDissolved { .. } => "ChannelDissolved",
            Self::ChannelHasDescendants { .. } => "ChannelHasDescendants",
            Self::ChannelAlreadyInState { .. } => "ChannelAlreadyInState",
            Self::SessionNotFound { .. } => "SessionNotFound",
            Self::ExpectedDurationTooLong { .. } => "ExpectedDurationTooLong",
            Self::TierViolation { .. } => "TierViolation",
            Self::AggregateNotFound { .. } => "AggregateNotFound",
            Self::SchemaVersionMismatch { .. } => "SchemaVersionMismatch",
            Self::ControlPlaneUnavailable { .. } => "ControlPlaneUnavailable",
            Self::ResumeTokenExpired { .. } => "ResumeTokenExpired",
            Self::AggregatorStuck { .. } => "AggregatorStuck",
            Self::BackendIo(_) => "BackendIo",
        }
    }

    /// Every variant this build implements, in declaration order.
    ///
    /// Exists so the oracle can compare SETS rather than re-listing names in a
    /// test — a second hand-written list agreeing with the first is *"the same
    /// act done twice"*, which `spec_oracle.rs` names as the thing it refuses.
    pub const IMPLEMENTED_VARIANTS: &'static [&'static str] = &[
        "RealityMismatch",
        "CapabilityExpired",
        "CapabilityDenied",
        "RateLimited",
        "CircuitOpen",
        "ChannelDissolved",
        "ChannelHasDescendants",
        "ChannelAlreadyInState",
        "SessionNotFound",
        "ExpectedDurationTooLong",
        "TierViolation",
        "AggregateNotFound",
        "SchemaVersionMismatch",
        "ControlPlaneUnavailable",
        "ResumeTokenExpired",
        "AggregatorStuck",
        "BackendIo",
    ];
}

impl fmt::Display for DpError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::RealityMismatch { ctx, requested } => {
                write!(f, "reality id mismatch: ctx={ctx} requested={requested}")
            }
            Self::CapabilityExpired => write!(f, "capability expired; refresh required"),
            Self::CapabilityDenied { aggregate, tier } => {
                write!(f, "capability denies {aggregate} on {tier:?}")
            }
            Self::RateLimited { tier, retry_after } => {
                write!(f, "rate limited on {tier:?}; retry after {retry_after:?}")
            }
            Self::CircuitOpen { service } => write!(f, "circuit open for {service}"),
            Self::ChannelDissolved { channel } => write!(f, "channel dissolved: channel={channel}"),
            Self::ChannelHasDescendants { channel, descendant_count } => write!(
                f,
                "cannot dissolve: channel {channel} has {descendant_count} non-dissolved descendants"
            ),
            Self::ChannelAlreadyInState { channel, state } => {
                write!(f, "channel already in target state: channel={channel} state={state}")
            }
            Self::SessionNotFound { session_id } => {
                write!(f, "session not found: session_id={session_id}")
            }
            Self::ExpectedDurationTooLong { requested } => {
                write!(f, "turn slot expected_duration too long: requested={requested:?} max=5min")
            }
            Self::TierViolation { aggregate, requested, allowed } => {
                write!(f, "tier violation: {aggregate} requested={requested:?} allowed={allowed:?}")
            }
            Self::AggregateNotFound { aggregate, id } => {
                write!(f, "aggregate not found: {aggregate}/{id}")
            }
            Self::SchemaVersionMismatch { on_disk, expected } => {
                write!(f, "schema version mismatch: on_disk={on_disk} expected={expected}")
            }
            Self::ControlPlaneUnavailable { reason } => {
                write!(f, "control plane unavailable: {reason}")
            }
            Self::ResumeTokenExpired { requested, earliest } => {
                write!(f, "resume token expired: requested={requested} earliest_available={earliest}")
            }
            Self::AggregatorStuck { aggregator, channel, event_id } => write!(
                f,
                "aggregator stuck: aggregator={aggregator} channel={channel} on_event={event_id}"
            ),
            Self::BackendIo(e) => write!(f, "backend io: {e}"),
        }
    }
}

impl std::error::Error for DpError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::BackendIo(e) => Some(&**e),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exactly_two_variants_are_backpressure() {
        let backpressure = [
            DpError::RateLimited { tier: TierLevel::T1, retry_after: Duration::from_secs(1) },
            DpError::CircuitOpen { service: "store".into() },
        ];
        for e in &backpressure {
            assert!(e.is_backpressure(), "{} must be backpressure", e.variant_name());
        }

        // The other side, which is the half that actually catches a mistake: a
        // variant wrongly classified as backpressure would make DP-R6 demand
        // propagation of an error a caller may legitimately handle.
        let not = [
            DpError::CapabilityExpired,
            DpError::AggregatorStuck { aggregator: "a", channel: "c".into(), event_id: 1 },
            DpError::ControlPlaneUnavailable { reason: "down".into() },
        ];
        for e in &not {
            assert!(!e.is_backpressure(), "{} must not be backpressure", e.variant_name());
        }
    }

    #[test]
    fn variant_name_matches_the_implemented_list() {
        // Guards the pair of hand-maintained lists against each other: a
        // variant added to IMPLEMENTED_VARIANTS but not to variant_name (or the
        // reverse) is what this catches. The DOC comparison is spec_oracle's.
        assert_eq!(DpError::IMPLEMENTED_VARIANTS.len(), 17);
        let names = [
            DpError::CapabilityExpired.variant_name(),
            DpError::CircuitOpen { service: String::new() }.variant_name(),
            DpError::BackendIo("x".into()).variant_name(),
        ];
        for n in names {
            assert!(
                DpError::IMPLEMENTED_VARIANTS.contains(&n),
                "{n} is returned by variant_name but missing from IMPLEMENTED_VARIANTS"
            );
        }
    }

    #[test]
    fn display_carries_the_payload_and_variant_name_does_not() {
        let e = DpError::CircuitOpen { service: "provider-registry".into() };
        assert!(e.to_string().contains("provider-registry"));
        // Unbounded-cardinality guard: the telemetry label must not embed it.
        assert_eq!(e.variant_name(), "CircuitOpen");
    }

    #[test]
    fn backend_io_exposes_its_source() {
        use std::error::Error;
        let inner: Box<dyn Error + Send + Sync> = "disk gone".into();
        let e = DpError::BackendIo(inner);
        assert!(e.source().is_some(), "BackendIo must not swallow its cause");
        assert!(DpError::CapabilityExpired.source().is_none());
    }
}
