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
}
