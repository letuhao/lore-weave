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
    // `GetTierPolicy` was here and is now SERVED — `040_tier_policy` (DF2)
    // gave DP-C4 its table, so the row's blocker is gone and the row with it.
    (
        "StreamTierPolicyUpdates",
        "nothing produces the monotonic snapshot_version a resuming subscriber          needs; the TABLE exists (040_tier_policy) but DP-C5's version sequence          does not",
    ),
    (
        "StreamRealityTransitions",
        "nothing publishes reality transitions to subscribe to",
    ),
    // `DP-A11` — the NPC-to-node binding is what decides the authoritative
    // single-writer for a non-session-scoped aggregate. The table does not
    // exist, so the rule has no subject: this row IS DP-A11's status, and
    // `tests/surface.rs` asserting it is what makes the absence noisy the day
    // the migration lands.
    // CORRECTED by DF2: the spec REFERENCES `npc_binding` twice and gives no
    // DDL for it anywhere, unlike DP-C4's two tables. The blocker is a design
    // gap, not an unwritten migration, and writing a schema would invent the
    // contract rather than transcribe it.
    ("GetNpcNode", "npc_binding (DP-A11) has no DDL in the spec — a design gap, not a migration"),
    (
        "ReportNodeHandoff",
        "a handoff has nowhere to be recorded — no npc_binding, no handoff log",
    ),
    // CORRECTED by DF2. `schema_version` is not a missing TABLE — DP-C4 makes
    // it a COLUMN of `tier_policy`, which now exists. What these three actually
    // wait on is the expand/migrate/contract STATE MACHINE: DP-C5's "both
    // active" flag, the rebuild-progress poll, and the contract-phase flip have
    // no column and no code. The old string sent a reader looking for a
    // migration that was never the blocker — DFO-3's shape, found again.
    ("GetSchemaVersion", "DP-C5's migration state machine (the `both active` flag) is not built"),
    ("AnnounceMigrationStart", "DP-C5's migration state machine is not built"),
    (
        "AnnounceMigrationComplete",
        "DP-C5's migration state machine is not built",
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

/// `DP-C3` RPCs that are **absent from the contract entirely**, each with what
/// they wait on.
///
/// # Not the same register as [`UNIMPLEMENTED_METHODS`], and the difference is
/// the whole point
///
/// A method in `UNIMPLEMENTED_METHODS` is **in the proto**: a caller can invoke
/// it and receives `UNIMPLEMENTED` naming the missing table. A row here is not
/// in the proto at all — there is no method to call, and `tests/surface.rs`
/// therefore cannot see it. Its absence is invisible to every check that talks
/// to the running server, which is exactly why it needs a register that is
/// compared against the **document**.
///
/// `crates/dp/tests/spec_oracle.rs` states the argument for the shape: a
/// transcription needs an oracle by a different method. This is the same three
/// arms as `DP-K3`'s `DEFERRED_VARIANTS`, applied to an RPC surface —
/// `dp-control-plane/tests/spec_oracle_cp.rs` reds when `DP-C3` declares an RPC
/// that is in neither the proto nor this list, when the proto invents one
/// `DP-C3` does not declare, and when a row here turns out to be implemented.
///
/// **The register shrinks or it reds.** All twelve are the four CHANNEL groups,
/// which are slice `5D`'s work: the first thing in this repo that produces a
/// `ChannelId`.
pub const DEFERRED_RPCS: &[(&str, &str)] = &[
    ("GetChannelTree", "no channel tree is served over the wire yet (slice 5D)"),
    ("StreamChannelTreeUpdates", "nothing publishes channel-tree deltas to stream"),
    ("ResolveAncestorChain", "the ancestor chain is resolved in-process by dp::ChannelTree"),
    ("GetChannelWriter", "the writer lease lives in dp-kernel, not behind the CP surface"),
    ("RequestWriterHandoff", "no CP-mediated handoff protocol exists (DP-A16, slice 5D)"),
    ("HeartbeatWriterLease", "the lease heartbeat is dp-kernel's, not the CP's"),
    ("RegisterBubbleUpAggregator", "no aggregator registry table (DP-Ch28)"),
    ("UnregisterBubbleUpAggregator", "no aggregator registry table (DP-Ch28)"),
    ("ListAggregatorsForChannel", "no aggregator registry table (DP-Ch28)"),
    ("TransitionChannelLifecycle", "channel lifecycle state is per-reality, not CP state (DP-Ch31)"),
    ("PauseChannel", "no pause state and no ack path (DP-Ch34)"),
    ("ResumeChannel", "no pause state to resume from (DP-Ch34)"),
];

/// `DP-C2` storage tables that have **no migration in this repo**, each with
/// why.
///
/// `DP-C2` lists seven tables as the control plane's own storage. Two exist —
/// `reality_registry` (`001`) and `session_registry` (`039`, the `5B`
/// amendment). The other five are named by a LOCKED document and backed by
/// nothing, which is the state `UNIMPLEMENTED_METHODS` already reports one
/// consequence of: four of the eight rows there say *"has no migration in this
/// repo"*.
///
/// Recording it here makes the claim checkable in the other direction too. The
/// oracle reds when a table appears in `DP-C2` and in neither the migration
/// tree nor this list, when a row here names a table `DP-C2` has dropped, and —
/// the arm that matters — when a row's table **gains a migration** and the row
/// outlives it.
pub const CP_TABLES_WITHOUT_A_MIGRATION: &[(&str, &str)] = &[
    // `tier_policy` was here. `040_tier_policy` (DF2) built it, and the
    // oracle demanded this row's deletion the moment it did — which is the
    // register shrinking rather than rotting, on its first opportunity.
    //
    // Its old reason is still TRUE and is no longer this register's business:
    // the rows come from a deploy manifest calling an admin API that does not
    // exist, so the table is empty in every deployment today. That is a
    // MISSING PRODUCER, not a missing table, and conflating the two is what
    // let the control plane report "no migration in this repo" for a column.
    ("npc_binding", "no NPC is bound to a node by anything in this repo"),
    ("schema_version", "DP-C5's migration coordination is unbuilt; per-reality schema_migrations is a different table with a different owner"),
    ("capability_signing_keys", "explicitly NOT BUILT — superseded by the 5B amendment on DP-C8, which ships an opaque bearer validated by lookup"),
    ("deploy_cohort", "DP-C5 deploy sequencing is unbuilt"),
];
