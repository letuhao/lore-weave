//! `5C` / `DP-C3` — the control plane's gRPC surface.
//!
//! # What this crate is, and the shape it deliberately avoids
//!
//! A gRPC server with no client is the orphan shape: it compiles, it has tests,
//! and nothing in the tree can call it. So this crate ships **both** sides,
//! generated from one contract — [`server::ControlPlaneService`] wrapping
//! `meta_rs::control_plane::MetaControlPlane`, and [`client::GrpcControlPlane`]
//! implementing [`dp::ControlPlane`] over the wire. The client is what makes the
//! server a surface something uses, and it is also what makes the cost of the
//! sealed bearer-capability deviation REAL rather than theoretical: with the
//! control plane in another process, every validation is a round trip.
//!
//! # What is implemented, and what returns UNIMPLEMENTED
//!
//! Four of the six non-channel RPC groups read state that does not exist in this
//! repo — `tier_policy`, `tier_capability`, `npc_binding` and `schema_version`
//! are absent from every migration, measured rather than assumed. Those methods
//! return `UNIMPLEMENTED` **naming the missing table**, and
//! [`UNIMPLEMENTED_METHODS`] is asserted by a test, so the list is a fact under
//! test rather than a comment that rots.
//!
//! Serving a plausible default instead would be worse than the error: a caller
//! can handle `UNIMPLEMENTED`, and cannot detect an invented answer.
//!
//! # Transport and auth
//!
//! `DP-C3` specifies gRPC over mTLS between CP and game services. This crate
//! implements the surface, not the TLS termination: `service_identity` arrives
//! as a request field, which is the caller's own assertion until a deployment
//! terminates mTLS and populates it from the peer certificate's subject.
//! `dp::ServiceIdentity` says the same thing on the Rust side, and the proto
//! says it in its header. Nothing here should be read as authentication.
//!
//! `I1` — the gateway invariant — governs PUBLIC traffic and is enforced by
//! security groups exposing only `api-gateway-bff` and `game-server`. This
//! surface is service-to-service inside the cluster, so it neither amends nor
//! violates it. `I11` is the invariant that applies: every RPC below needs an
//! ACL row naming its allowed callers and principal mode.

#![forbid(unsafe_code)]
#![warn(missing_docs, rust_2018_idioms)]

pub mod pb {
    #![allow(missing_docs, clippy::doc_markdown)]
    //! The generated types — `include_proto!` pulls in what `build.rs` produced
    //! from `contracts/proto/dp_control_plane.proto`.
    //!
    //! `missing_docs` is relaxed for this module ONLY, because the items are
    //! generated and their documentation lives in the proto. The relaxation is
    //! scoped to generated code and cannot silence a hand-written item.
    tonic::include_proto!("loreweave.dp.controlplane.v1");
}

pub mod client;
pub mod server;

/// The methods that are declared in the contract and return `UNIMPLEMENTED`,
/// each with the state that is missing.
///
/// # Why this is a const and not a comment
///
/// A comment listing unimplemented methods is right on the day it is written and
/// silently wrong afterwards — a method gets implemented and the comment still
/// names it, or a method is added and the comment does not. This list is
/// asserted against the running server by
/// `tests/surface.rs::every_unimplemented_method_says_so_and_no_other_does`,
/// which calls **every** RPC and compares the set that answered `UNIMPLEMENTED`
/// to this one. Both directions red: an implemented method still on this list,
/// and an unimplemented method missing from it.
pub const UNIMPLEMENTED_METHODS: &[(&str, &str)] = &[
    ("GetTierPolicy", "tier_policy (DP-C4) has no migration in this repo"),
    ("StreamTierPolicyUpdates", "tier_policy (DP-C4) has no migration in this repo"),
    (
        "StreamRealityTransitions",
        "nothing publishes reality transitions to subscribe to",
    ),
    ("GetNpcNode", "npc_binding (DP-C2) has no migration in this repo"),
    (
        "ReportNodeHandoff",
        "a handoff has nowhere to be recorded — no npc_binding, no handoff log",
    ),
    ("GetSchemaVersion", "schema_version (DP-C2) has no migration in this repo"),
    ("AnnounceMigrationStart", "schema_version (DP-C2) has no migration in this repo"),
    (
        "AnnounceMigrationComplete",
        "schema_version (DP-C2) has no migration in this repo",
    ),
];

/// The reason string for one unimplemented method, or `None` if it is supposed
/// to work.
pub fn unimplemented_reason(method: &str) -> Option<&'static str> {
    UNIMPLEMENTED_METHODS
        .iter()
        .find(|(m, _)| *m == method)
        .map(|(_, why)| *why)
}
