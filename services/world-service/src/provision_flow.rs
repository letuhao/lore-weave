//! The end-to-end provisioning flow, extracted so every caller runs the SAME
//! code rather than its own arrangement of the parts.
//!
//! [`Provisioner::provision_reality`](crate::provisioner::Provisioner::provision_reality)
//! is the 11-step core, but it is not the whole job. Around it sit three
//! decisions that are easy to get subtly wrong and that used to live only in
//! the `provision` binary:
//!
//! 1. **Resume before place.** A reality already in `reality_registry` has
//!    already claimed its capacity slot (`capacity_glue::LIVE_STATES` counts
//!    `provisioning` and `seeding`), so placing it again double-counts the
//!    shard. It must be resumed pinned to the shard the registry names.
//! 2. **The whole provision runs INSIDE the advisory lock**, not just the shard
//!    pick. The registry row written by step 3 is what claims the slot; steps 4+
//!    must not run against a shard that filled in between.
//! 3. **The snapshot handed to the planner is re-read under the lock and
//!    filtered to the locked shard**, so the planner necessarily returns it. A
//!    fabricated snapshot here is exactly the defect that made `provision-drill`
//!    unfit as the product path — it never made the one decision provisioning
//!    exists to make.
//!
//! ## Why this is a module and not a copy
//!
//! `1b14-01` was found because a unit test was green against
//! `FakeEffects::apply_migrations` — a `HashSet::insert` — while the live code
//! was not idempotent. The mock had the property and the implementation did
//! not. `provisioner_live::apply_pending` was extracted for that reason, with
//! the note that *"a second re-implementation, this time in a test, would repeat
//! exactly that."* A second re-implementation, this time in an HTTP handler,
//! would too. The HTTP surface added in `WS3` calls these functions; it does not
//! restate them.

use sqlx::PgPool;
use tokio::runtime::Handle;
use uuid::Uuid;

use crate::capacity_glue::{live_snapshot, place_reality};
use crate::capacity_planner::{CapacityPlanner, CapacityThresholds, ShardCapacity, ShardId};
use crate::errors::ProvisionerError;
use crate::provisioner::{ProvisionReport, ProvisionRequest, Provisioner, db_name_for};
use crate::provisioner_live::{BridgeClient, LiveEffects};

/// Statuses past the point where re-running provisioning is meaningful.
///
/// A reality in one of these has finished provisioning (or moved beyond it);
/// re-entering the flow would either no-op through all 11 steps or act on a
/// reality that is being torn down.
pub const SETTLED_STATUSES: [&str; 6] =
    ["active", "migrating", "pending_close", "frozen", "archived", "soft_deleted"];

/// What `reality_registry` already knows about a reality.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Registration {
    /// The shard host the registry names for this reality.
    pub db_host: String,
    /// The per-reality database name the registry names.
    pub db_name: String,
    /// Lifecycle status.
    pub status: String,
}

impl Registration {
    /// True when the reality has moved past the point where provisioning is
    /// meaningful — see [`SETTLED_STATUSES`].
    pub fn is_settled(&self) -> bool {
        SETTLED_STATUSES.contains(&self.status.as_str())
    }
}

/// Everything [`LiveEffects`] needs, minus the pools and the runtime handle.
///
/// Deliberately owned `String`s: the effects run on a `spawn_blocking` thread,
/// so every field has to be moved across a thread boundary anyway.
#[derive(Debug, Clone)]
pub struct EffectsConfig {
    /// Base URL of the Go meta-write bridge (I8 — Rust cannot write meta directly).
    pub bridge_url: String,
    /// Shared token for the bridge.
    pub bridge_token: String,
    /// `host:port` of the shard, used to connect to the freshly-created database.
    pub shard_hostport: String,
    /// Role used for the per-reality connection.
    pub pg_user: String,
    /// Password for that role. May legitimately be empty (peer/trust auth).
    pub pg_pass: String,
    /// Directory holding `<id>.up.sql` (`contracts/migrations/per_reality`).
    pub sql_dir: String,
    /// The polyglot allowlist the control plane validates against — needed to
    /// BIND a reality before touching its actor control, so a frozen or
    /// archived world refuses the grant rather than accepting it.
    pub meta_allowlist: String,
}

impl EffectsConfig {
    fn effects(&self, handle: Handle, shard_admin: PgPool) -> LiveEffects {
        LiveEffects::new(
            handle,
            BridgeClient::new(self.bridge_url.clone(), self.bridge_token.clone()),
            shard_admin,
            self.shard_hostport.clone(),
            self.pg_user.clone(),
            self.pg_pass.clone(),
            self.sql_dir.clone(),
        )
    }
}

/// Read the reality's existing registry row, if any.
///
/// Callers MUST do this before placing: see the module doc, decision 1.
pub async fn existing_registration(
    meta: &PgPool,
    reality_id: Uuid,
) -> Result<Option<Registration>, ProvisionerError> {
    let row: Option<(String, String, String)> =
        sqlx::query_as("SELECT db_host, db_name, status FROM reality_registry WHERE reality_id = $1")
            .bind(reality_id)
            .fetch_optional(meta)
            .await
            .map_err(|e| ProvisionerError::InvalidState(format!("read reality_registry: {e}")))?;
    Ok(row.map(|(db_host, db_name, status)| Registration { db_host, db_name, status }))
}

/// Run the 11 steps on a thread that may block, against a snapshot pinned to
/// one shard.
///
/// The effects chain is synchronous and blocks on a tokio `Handle` internally,
/// so calling it on a runtime worker thread would block the reactor — and
/// `Handle::block_on` **panics** from inside a runtime thread. Every caller goes
/// through here, so no caller has to remember that.
async fn run_steps_blocking(
    shard_admin: PgPool,
    cfg: &EffectsConfig,
    req: ProvisionRequest,
    pinned: Vec<ShardCapacity>,
) -> Result<ProvisionReport, ProvisionerError> {
    let handle = Handle::current();
    let cfg = cfg.clone();
    tokio::task::spawn_blocking(move || {
        let mut effects = cfg.effects(handle, shard_admin);
        Provisioner::new(CapacityThresholds::default()).provision_reality(req, &pinned, &mut effects)
    })
    .await
    .map_err(|e| ProvisionerError::InvalidState(format!("join: {e}")))?
}

/// The **placement** path: pick a shard under a per-shard advisory lock and run
/// the whole 11-step provision inside that critical section.
///
/// Returns the shard the reality landed on together with its report. Only valid
/// when [`existing_registration`] returned `None` — a reality that already has a
/// row must go through [`resume_on_registered_shard`] instead, or its slot is
/// counted twice.
pub async fn place_and_provision(
    meta: &PgPool,
    shard_admin: &PgPool,
    planner: &CapacityPlanner,
    req: ProvisionRequest,
    cfg: &EffectsConfig,
) -> Result<(ShardId, ProvisionReport), ProvisionerError> {
    // `place_reality` takes an FnOnce returning a future and gives us no way to
    // return a value out of it, so the report comes back through a slot. A
    // std::sync::Mutex is right here: it is never held across an await.
    let slot: std::sync::Arc<std::sync::Mutex<Option<ProvisionReport>>> = Default::default();

    let placed = place_reality(meta, planner, true, |shard_id| {
        let shard_id = shard_id.clone();
        let slot = std::sync::Arc::clone(&slot);
        let meta = meta.clone();
        let shard_admin = shard_admin.clone();
        let cfg = cfg.clone();
        async move {
            // Re-read live capacity under the lock and keep ONLY the locked
            // shard, so the planner inside provision_reality necessarily
            // returns it. A fabricated snapshot here would reintroduce the
            // drill's defect.
            let pinned: Vec<ShardCapacity> = live_snapshot(&meta)
                .await?
                .into_iter()
                .filter(|s| s.shard_id == shard_id)
                .collect();
            let report = run_steps_blocking(shard_admin, &cfg, req, pinned).await?;
            *slot.lock().expect("report slot poisoned") = Some(report);
            Ok(())
        }
    })
    .await?;

    let report = slot.lock().expect("report slot poisoned").take().ok_or_else(|| {
        ProvisionerError::InvalidState(
            "placement reported success but no provision report was produced".into(),
        )
    })?;
    Ok((placed, report))
}

/// The **resume** path: re-run the provision pinned to the shard the registry
/// already names.
///
/// No advisory lock and no placement — the slot is already claimed by the
/// existing row, so taking it again would double-count the shard.
///
/// Refuses when the registry's `db_name` is not the one this build derives:
/// the name is a deterministic function of `reality_id`, so a mismatch means
/// the row was written under a different naming rule, and provisioning over it
/// would create a second database for one reality.
pub async fn resume_on_registered_shard(
    meta: &PgPool,
    shard_admin: &PgPool,
    req: ProvisionRequest,
    registration: &Registration,
    cfg: &EffectsConfig,
) -> Result<ProvisionReport, ProvisionerError> {
    let expected = db_name_for(req.reality_id);
    if registration.db_name != expected {
        return Err(ProvisionerError::InvalidState(format!(
            "registry names database {} for reality {} but this build derives {expected}; \
             refusing to act on a row written under a different naming rule",
            registration.db_name, req.reality_id
        )));
    }

    let host = registration.db_host.clone();
    let pinned: Vec<ShardCapacity> = live_snapshot(meta)
        .await?
        .into_iter()
        .filter(|s| s.shard_id.as_str() == host)
        .collect();
    if pinned.is_empty() {
        return Err(ProvisionerError::InvalidState(format!(
            "reality {} is registered on shard {host}, which is not in shard_utilization; \
             the shard must be re-registered before the provision can be resumed",
            req.reality_id
        )));
    }

    run_steps_blocking(shard_admin.clone(), cfg, req, pinned).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn settled_statuses_cover_every_state_past_provisioning() {
        // The two LIVE states must NOT be settled — a reality in either is
        // mid-flow and is exactly what the resume path exists for.
        assert!(!SETTLED_STATUSES.contains(&"provisioning"));
        assert!(!SETTLED_STATUSES.contains(&"seeding"));
        assert!(SETTLED_STATUSES.contains(&"active"));
    }

    #[test]
    fn is_settled_reads_the_status_not_the_shard() {
        let r = Registration {
            db_host: "pg-shard-0.internal".into(),
            db_name: "lw_reality_abc".into(),
            status: "seeding".into(),
        };
        assert!(!r.is_settled());
        assert!(Registration { status: "archived".into(), ..r }.is_settled());
    }
}
