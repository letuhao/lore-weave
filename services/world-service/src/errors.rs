//! Canonical error type for the world-service infrastructure surface
//! (provisioner, deprovisioner, capacity_planner, db_pool).
//!
//! Mirrors `crates/meta-rs::MetaError` shape so call sites that bubble both
//! library errors can keep matching uniform.

use thiserror::Error;

/// Errors surfaced by the L1.C provisioner/deprovisioner/capacity_planner
/// and L1.G db_pool modules.
#[derive(Debug, Error)]
pub enum ProvisionerError {
    /// `reality_registry` already contains a row for the requested reality.
    /// `provision_reality()` is idempotent over re-entry within the same
    /// (provisioning|seeding) state but rejects an outright duplicate.
    #[error("provisioner: reality_id {0} already provisioned")]
    AlreadyProvisioned(String),

    /// Capacity planner could not allocate a shard — every shard is at or
    /// above the FULL threshold (95% default). Caller MUST escalate; do not
    /// retry.
    #[error("provisioner: no shard has capacity (all >= full_threshold)")]
    NoShardCapacity,

    /// A planner input violated invariants (e.g., warning > full, free > total).
    #[error("provisioner: bad capacity input: {0}")]
    BadCapacity(String),

    /// `reality_registry` row not found by the deprovisioner.
    #[error("provisioner: reality_id {0} not found in registry")]
    NotFound(String),

    /// Provisioner / deprovisioner reached a state where the request is no
    /// longer valid (e.g., trying to deprovision a `dropped` reality).
    #[error("provisioner: invalid state for op: {0}")]
    InvalidState(String),

    /// Underlying meta library returned an error. Wrapped to keep the
    /// public surface flat.
    #[error("provisioner: meta error: {0}")]
    Meta(#[from] meta_rs::MetaError),

    /// db_pool registry rejected a pool registration because the same key
    /// (shard_host, role) was already present and the new config differs.
    #[error("db_pool: conflicting registration for {0:?}")]
    DbPoolConflict(crate::db_pool::DbPoolKey),

    /// db_pool registry asked for a key that wasn't registered.
    #[error("db_pool: no pool registered for {0:?}")]
    DbPoolMissing(crate::db_pool::DbPoolKey),

    /// db_pool config violates the pgbouncer transaction-mode contract
    /// (e.g., max_client_conn > 5000 virtual cap, or backend > 500 real cap).
    #[error("db_pool: invalid pool config: {0}")]
    DbPoolInvalid(String),

    /// W1.5 — the Rust→Go meta-write bridge call failed (network, auth, or a
    /// 5xx). The provisioner cannot complete the registry write without it.
    #[error("provisioner: bridge call failed: {0}")]
    Bridge(String),
    /// A DIFFERENT user already holds the live binding for this actor.
    ///
    /// Distinct from [`ProvisionerError::Bridge`] on purpose: the caller must
    /// be able to tell "the bridge is broken" from "somebody else drives this
    /// actor", because the second is a normal, expected answer and the first is
    /// an outage. Collapsing them would make a 409 look like a 500.
    #[error("actor control: actor {0} is already driven by another user")]
    ActorAlreadyDriven(String),
    /// The caller named the user it expected to revoke, and someone else holds
    /// the binding now — a stale read that must SURFACE, never blind-retry.
    #[error("actor control: expected user does not hold the live binding for actor {0}")]
    ControlCasMismatch(String),

    /// W1.5 — a bridge transition returned 409 (stale FromState / concurrent
    /// modification). The caller must reload + decide, NOT blind-retry.
    #[error("provisioner: concurrent transition: {0}")]
    ConcurrentTransition(String),

    /// W1.5 — a shard-side effect (CREATE DATABASE, role/REVOKE, skeleton
    /// migration) failed.
    #[error("provisioner: shard effect failed: {0}")]
    ShardEffect(String),

    /// `SEALED-BINDING` — the control plane refused to BIND the reality: it is
    /// frozen, archived, dropped, soft-deleted, provisioning, or absent.
    ///
    /// Its own variant because it is a statement about the WORLD, not a fault
    /// of ours, and the caller can act on it. Before this existed the bind
    /// refusal was an ad-hoc string that only the HTTP handler knew to render
    /// as a `400`; a second caller would have reported a closed world as an
    /// outage and paged someone for a reality doing exactly what it was told.
    #[error("reality {0} does not accept commands: {1}")]
    RealityClosed(String, String),

    /// `SEALED-BINDING` — the actor has no durable identity in this reality.
    ///
    /// The grant precondition. `034` could not express it as a foreign key
    /// because `actors` lives in the per-reality database, so the check lives
    /// in `actor_control_flow` — and a binding created without it is the
    /// dangling pointer `S-9` describes, discovered at turn time by a resolver
    /// instead of at the write edge by the writer.
    #[error("actor {0} does not exist in reality {1}")]
    UnknownActor(String, String),
}
