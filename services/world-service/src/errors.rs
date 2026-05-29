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
}
