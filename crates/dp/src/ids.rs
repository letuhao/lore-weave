//! `DP-K1` — the identity newtypes, and the one property that makes them worth
//! having.
//!
//! # The property is UNFORGEABILITY, not tidiness
//!
//! `04a_core_types_and_session.md` specifies `RealityId` as a *"newtype with
//! module-private constructor — **cannot be forged by feature code**. Produced
//! only by SDK during session bind (`DP-K10`) after verification against the
//! control plane."*
//!
//! That sentence is the whole design. A transparent `pub struct RealityId(pub
//! Uuid)` would be a rename: any feature crate could mint one from a `Uuid` it
//! parsed out of a request body, and `DP-A12`'s *"session-context-gated access"*
//! would be a convention rather than a rule. The inner field is `pub(crate)` and
//! the constructor is `pub(crate) fn new_verified`, so the ONLY way a feature
//! crate obtains one is to be handed it by [`crate::session::SessionContext::bind`]
//! — which gets it from a [`crate::session::ControlPlane`] that verified it.
//!
//! `tests/ui/forged_reality_id.rs` is that claim executed by rustc rather than
//! asserted here. Same shape as `forged_row.rs`, which exists because a refuter
//! built a `TierRow` by hand and printed it (`V1-F5`).
//!
//! # This file was written, reverted, and re-added — deliberately
//!
//! Its first version shipped without `session.rs`, and `cargo clippy -p dp
//! --all-targets -- -D warnings` said `new_verified` is never used. It was
//! right: a crate-private constructor with no in-crate caller is dead code, and
//! silencing that with `#[allow(dead_code)]` is the pragma-as-exemption shape
//! `CLAUDE.md` names by example. §0.6c is the rule that came out of it — *a type
//! with a crate-private constructor lands WITH its producer* — and `bind` is
//! that producer. **Clippy's dead-code pass is therefore the real test of
//! whether the producer exists**, which is why this file has no `#[allow]`.
//!
//! # Why `Uuid` and not `[u8; 16]`
//!
//! `uuid` is a pure data type — it opens nothing, reads nothing, spawns nothing
//! — so `S2.3`'s *"declares no I/O"* is untouched, and `crates/dp-kernel`
//! already resolves it from the workspace. `[u8; 16]` would tax every adoption
//! site: `reality_id` appears 880 times across 99 files, and a representation
//! the rest of the tree does not speak turns a mechanical migration into a
//! conversion at every boundary, which is where identity bugs live.

use core::fmt;

use uuid::Uuid;

/// Generates a UUID-backed newtype whose inner field and constructor are
/// crate-private.
///
/// A macro rather than three hand-written copies because the *point* of these
/// types is that they are identical in structure and non-interchangeable in
/// use. Hand-writing them invites exactly one to drift into a `pub` field
/// during a hurried edit, and that one would be the hole.
macro_rules! verified_uuid_newtype {
    ($(#[$meta:meta])* $name:ident, $what:literal) => {
        $(#[$meta])*
        #[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Hash)]
        pub struct $name(pub(crate) Uuid);

        impl $name {
            /// Mint one from a value this crate has VERIFIED.
            ///
            /// `pub(crate)` is the enforcement. Feature code cannot call it, so
            /// it cannot manufacture an identity for a
            #[doc = $what]
            /// it was never granted.
            pub(crate) fn new_verified(uuid: Uuid) -> Self {
                Self(uuid)
            }

            /// The underlying UUID, for logging, cache keys and the wire.
            ///
            /// Read-only on purpose: handing out the `Uuid` is harmless,
            /// because possessing a `Uuid` is not what grants access —
            /// possessing the NEWTYPE is. The asymmetry is the design.
            pub fn as_uuid(&self) -> Uuid {
                self.0
            }
        }

        impl fmt::Display for $name {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                fmt::Display::fmt(&self.0, f)
            }
        }
    };
}

verified_uuid_newtype!(
    /// Which reality a call addresses (`DP-A12`, `DP-R1`).
    ///
    /// Produced only by session bind, after the control plane confirms the
    /// caller may reach it.
    RealityId,
    "reality"
);

verified_uuid_newtype!(
    /// A bound SDK session (`DP-K2`).
    SessionId,
    "session"
);

/// Ids `DP-K1` names that are NOT built here, with the producer each waits on.
///
/// `ChannelId` was written, and clippy's dead-code pass removed it — which is
/// the mechanism working rather than an inconvenience. `RealityId`,
/// `SessionId` and `NodeId` are all minted by
/// [`crate::session::SessionContext::bind`]; nothing mints a `ChannelId`,
/// because its producer is `DP-Ch9`'s `move_session_to_channel` and that is
/// slice 5. §0.6c of the run-state seals the rule this obeys: *anything the
/// spec names that has no producer is not shipped.*
///
/// A test that constructs one does not count as a producer — the goal
/// condition names "test-only consumers" among the things that do not.
///
/// Read by `tests/spec_oracle.rs`, so this cannot quietly become permanent.
pub const DEFERRED_IDS: &[(&str, &str)] = &[
    ("ChannelId", "DP-Ch9 move_session_to_channel (slice 5)"),
];

/// The node a session is bound to (`DP-K1`).
///
/// A hostname or k8s pod id, so a `String` rather than a UUID — but the same
/// crate-private discipline applies: a node identity is observed, never
/// asserted by a caller.
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Hash)]
pub struct NodeId(pub(crate) String);

impl NodeId {
    pub(crate) fn new_verified(id: String) -> Self {
        Self(id)
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for NodeId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

/// WHO is binding — the caller's own service identity (`DP-C3`, `DP-C8`).
///
/// # The hole this closes
///
/// `BindRequest` used to be `{ reality, node }`, so the control plane could
/// confirm that a reality existed and accepted commands but never that **anyone
/// in particular was asking**. `DP-A12` calls the result *"session-context-gated
/// access"*, which reads as though the gate had a subject; it did not. Every
/// capability issued before this type was anonymous.
///
/// # Validated at construction, not checked at use
///
/// Same shape as [`crate::KeyId`], and for the same reason: a value that cannot
/// be built wrong needs no downstream check that someone will forget. There is
/// no `new_verified` here because — unlike [`RealityId`] — this is **not** an
/// unforgeable capability. A caller asserting its own name proves nothing; what
/// makes the name trustworthy is the transport (`DP-C3` specifies mTLS, and the
/// peer certificate's subject is what `5C` will put here). This type's job is
/// only to guarantee the name is *usable*: present, bounded, loggable.
///
/// Saying that plainly matters more than the code. An identity that validates
/// its own shape and nothing else can be mistaken for authentication by the
/// next reader, and then the gate has a subject that anyone may claim.
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Hash)]
pub struct ServiceIdentity(String);

impl ServiceIdentity {
    /// Longest accepted identity.
    ///
    /// A bound rather than none, because this string reaches a `TEXT` column, a
    /// log line and (at `5C`) a gRPC metadata header. 128 is comfortably above
    /// any real service name — the longest in `contracts/language-rule.yaml` is
    /// well under 40 — and far below the point where an unbounded name becomes
    /// a way to bloat every audit row a caller can provoke.
    pub const MAX_LEN: usize = 128;

    /// Build one, or `None` if the name is unusable.
    ///
    /// `Option` and not a panic, exactly as [`crate::KeyId::new`]: a malformed
    /// identity arrives from a caller, and a panic on the bind path would turn
    /// a bad request into a downed process.
    ///
    /// Rejects, each for its own reason:
    ///
    /// * **empty or whitespace-only** — the anonymous capability this type
    ///   exists to abolish. `"   "` is the interesting case: it is non-empty,
    ///   so a naive `is_empty()` admits it and stores a blank name.
    /// * **longer than [`Self::MAX_LEN`]** — see the constant.
    /// * **containing an ASCII control character** — a `\n` in a service name
    ///   forges a second line in every structured log that renders it, which is
    ///   log injection with the identity field as the vector.
    ///
    /// The stored value is TRIMMED, so `" commit-service "` and
    /// `"commit-service"` are the same identity rather than two rows that look
    /// identical in every report.
    pub fn new(raw: impl Into<String>) -> Option<Self> {
        let raw: String = raw.into();
        let trimmed = raw.trim();
        if trimmed.is_empty() || trimmed.len() > Self::MAX_LEN {
            return None;
        }
        if trimmed.chars().any(|c| c.is_control()) {
            return None;
        }
        Some(Self(trimmed.to_string()))
    }

    /// The name, for the registry row and the audit trail.
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for ServiceIdentity {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn display_is_the_plain_uuid() {
        let id = RealityId::new_verified(Uuid::from_u128(0));
        assert_eq!(id.to_string(), "00000000-0000-0000-0000-000000000000");
    }

    #[test]
    fn as_uuid_round_trips() {
        let raw = Uuid::from_u128(42);
        assert_eq!(RealityId::new_verified(raw).as_uuid(), raw);
        assert_eq!(SessionId::new_verified(raw).as_uuid(), raw);
    }

    #[test]
    fn a_node_id_round_trips_its_string() {
        let n = NodeId::new_verified("pod-7".to_string());
        assert_eq!(n.as_str(), "pod-7");
        assert_eq!(n.to_string(), "pod-7");
    }

    #[test]
    fn a_service_identity_is_trimmed_so_two_spellings_are_one_identity() {
        let a = ServiceIdentity::new(" commit-service ").expect("valid");
        let b = ServiceIdentity::new("commit-service").expect("valid");
        assert_eq!(a, b, "padding must not create a second identity");
        assert_eq!(a.as_str(), "commit-service");
        assert_eq!(a.to_string(), "commit-service");
    }

    #[test]
    fn an_anonymous_service_identity_cannot_be_constructed() {
        assert!(ServiceIdentity::new("").is_none(), "empty");
        // The case a naive `is_empty()` admits — non-empty, but nameless.
        assert!(ServiceIdentity::new("   ").is_none(), "whitespace-only");
        assert!(ServiceIdentity::new("\t\n").is_none(), "whitespace-only, other forms");
    }

    #[test]
    fn a_control_character_is_refused_because_it_forges_a_log_line() {
        assert!(ServiceIdentity::new("commit\nservice").is_none(), "newline");
        assert!(ServiceIdentity::new("commit\rservice").is_none(), "carriage return");
        assert!(ServiceIdentity::new("commit\u{0}service").is_none(), "nul");
        // And the boundary: a name made only of legitimate characters passes.
        assert!(ServiceIdentity::new("commit-service").is_some());
    }

    #[test]
    fn length_is_bounded_at_the_stated_constant() {
        let ok = "s".repeat(ServiceIdentity::MAX_LEN);
        let too_long = "s".repeat(ServiceIdentity::MAX_LEN + 1);
        assert!(ServiceIdentity::new(ok).is_some(), "MAX_LEN itself must be accepted");
        assert!(ServiceIdentity::new(too_long).is_none(), "one over must not");
    }

    #[test]
    fn the_length_bound_is_applied_after_trimming() {
        // Otherwise padding could push a legal name over the limit, and a
        // caller would be refused for whitespace it did not know it sent.
        let padded = format!("  {}  ", "s".repeat(ServiceIdentity::MAX_LEN));
        assert!(ServiceIdentity::new(padded).is_some());
    }
}
