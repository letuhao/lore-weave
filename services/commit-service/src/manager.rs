//! IMG-A5/A6 — the island manager: one process, N islands, leases kept alive.
//!
//! ## What it is, and what it deliberately is not
//!
//! A **supervisor**, not a scheduler-of-schedulers. It holds `channel →
//! (Island, HeldLease)`, renews leases, and steps islands one at a time.
//! CNC-D1 (shared-nothing) survives intact: islands never share state, and the
//! manager touches exactly one per call.
//!
//! It is a ROLE inside `commit-service`, never a separate service (IMG-A6/D8).
//! CS-A1 forces this — the DP-A16 epoch token must sit on the writer node
//! *with* the island, so whatever assigns islands and whatever hosts them are
//! the same process. Splitting them would ship the token off-node and dissolve
//! the forgery guard the whole design rests on.
//!
//! ## IMG-D6 — claim → recover → step, and the order is not negotiable
//!
//! [`Manager::adopt`] does all three in sequence and there is no public way to
//! step an island that skipped the middle one. That is deliberate: writer
//! reassignment is *precisely* the event that triggers the CNC-F6 double-apply,
//! so a manager that stepped before recovering would re-open the bug the
//! recovery replay was built to close — and would do it at the exact moment
//! the system is least able to notice.
//!
//! ## Placement is out of scope
//!
//! Which node *should* host which island is the control plane's job (IMG-D1 /
//! IMG-Q1). This manager takes what it is given: it claims the channels it is
//! asked to, and reports the ones already covered by a healthy holder.

use std::collections::BTreeMap;
use std::sync::Arc;

use dp_kernel::channel::{
    claim_writer_lease, release_writer_lease, renew_writer_lease, ChannelId, ChannelWriter,
    HeldLease, LEASE_TTL_SECS,
};
use sim_core::{Island, StepStatus};
use sqlx::postgres::PgPool;
use uuid::Uuid;

use crate::domain::CombatDomain;
use crate::recovery::{recover_writer_state, seed_seen, WriterRecovery, RECOVERY_TAIL};

/// Why an adopt attempt did not yield a running island.
#[derive(Debug, PartialEq, Eq)]
pub enum AdoptOutcome {
    /// Claimed, recovered, ready to step.
    Adopted { recovered_ids: usize, turn_number: u64 },
    /// A healthy holder still has it. A normal result, not an error — it is
    /// how a manager discovers a channel is already covered.
    HeldByAnother,
}

/// One island under management, with the lease that authorises writing it.
pub struct Managed {
    pub island: Island<CombatDomain>,
    pub lease: HeldLease,
    pub writer: ChannelWriter,
    /// What recovery restored — carried so the caller can resume its counters
    /// instead of re-deriving them.
    pub recovery: WriterRecovery,
}

pub struct Manager {
    pool: Arc<PgPool>,
    reality_id: Uuid,
    /// Stable identity for this process, minted once. Renew and release are
    /// scoped to it, so two managers in one process would be indistinguishable
    /// at the DB — hence one per process, not one per island.
    holder: Uuid,
    islands: BTreeMap<i64, Managed>,
    ttl_secs: i64,
}

impl Manager {
    pub fn new(pool: Arc<PgPool>, reality_id: Uuid) -> Self {
        Self {
            pool,
            reality_id,
            holder: Uuid::new_v4(),
            islands: BTreeMap::new(),
            ttl_secs: LEASE_TTL_SECS,
        }
    }

    /// Override the lease TTL. Tests drive failover with a short (or already
    /// expired) TTL rather than sleeping for 30 s.
    pub fn with_ttl(mut self, ttl_secs: i64) -> Self {
        self.ttl_secs = ttl_secs;
        self
    }

    pub fn holder(&self) -> Uuid {
        self.holder
    }

    pub fn hosted(&self) -> Vec<i64> {
        self.islands.keys().copied().collect()
    }

    pub fn get_mut(&mut self, channel: i64) -> Option<&mut Managed> {
        self.islands.get_mut(&channel)
    }

    /// Take over a channel: claim the lease, rebuild dedup state from the log,
    /// then install the island. IMG-D6 — all three, in that order.
    ///
    /// `build` constructs the island. It is a callback rather than a value so
    /// that a channel already held by someone else costs nothing: there is no
    /// point building an encounter's state for a channel this node will not be
    /// allowed to write.
    pub async fn adopt<F>(
        &mut self,
        channel: i64,
        build: F,
    ) -> Result<AdoptOutcome, sqlx::Error>
    where
        F: FnOnce() -> Island<CombatDomain>,
    {
        // IMG-D4 — spawn is idempotent per channel. Two proposals arriving
        // together for one new encounter must not produce two islands.
        if let Some(existing) = self.islands.get(&channel) {
            return Ok(AdoptOutcome::Adopted {
                recovered_ids: existing.recovery.seen_input_ids.len(),
                turn_number: existing.recovery.turn_number,
            });
        }

        let ch = ChannelId(channel);
        let Some(lease) =
            claim_writer_lease(&self.pool, self.reality_id, ch, self.holder, self.ttl_secs)
                .await
                .map_err(unwrap_db)?
        else {
            return Ok(AdoptOutcome::HeldByAnother);
        };

        // RECOVER before the island is reachable for stepping.
        let recovery =
            recover_writer_state(&self.pool, self.reality_id, channel, RECOVERY_TAIL).await?;
        let mut island = build();
        let at = island.tick_now();
        seed_seen(&mut island, &recovery.seen_input_ids, at);

        let writer = ChannelWriter::new(self.pool.clone(), self.reality_id, lease.lease);
        let out = AdoptOutcome::Adopted {
            recovered_ids: recovery.seen_input_ids.len(),
            turn_number: recovery.turn_number,
        };
        self.islands.insert(channel, Managed { island, lease, writer, recovery });
        Ok(out)
    }

    /// Renew every held lease. Channels whose renewal FAILED are dropped and
    /// returned — this process is no longer their writer.
    ///
    /// IMG-D7: losing a lease stops that island; it does not kill the process.
    /// Exiting would throw away every other warm island for what may be a
    /// transient blip, and stopping is already safe because the fence means
    /// nothing this process produces for that channel can be committed.
    pub async fn renew_all(&mut self) -> Result<Vec<i64>, sqlx::Error> {
        let mut lost = Vec::new();
        for (channel, managed) in &self.islands {
            let ok = renew_writer_lease(&self.pool, self.reality_id, managed.lease, self.ttl_secs)
                .await
                .map_err(unwrap_db)?;
            if !ok {
                lost.push(*channel);
            }
        }
        for channel in &lost {
            self.islands.remove(channel);
        }
        Ok(lost)
    }

    /// Step one island until its ingress drains. Returns how many items were
    /// processed, or `None` if this manager does not hold that channel —
    /// which is the only honest answer, and better than a silent 0.
    pub fn drain(&mut self, channel: i64) -> Option<usize> {
        let managed = self.islands.get_mut(&channel)?;
        let mut n = 0;
        while matches!(managed.island.step(), StepStatus::Processed(_)) {
            n += 1;
        }
        Some(n)
    }

    /// Give up a channel cleanly: dissolve nothing (the island is simply
    /// dropped) and RELEASE the lease so the channel is claimable at once.
    ///
    /// IMG-D5 — without the release, a clean shutdown leaves the channel
    /// unclaimable for a full TTL, turning every deploy into a per-channel
    /// outage. That is the kind of self-inflicted downtime that ends with
    /// someone disabling failover.
    pub async fn relinquish(&mut self, channel: i64) -> Result<bool, sqlx::Error> {
        let Some(managed) = self.islands.remove(&channel) else {
            return Ok(false);
        };
        release_writer_lease(&self.pool, self.reality_id, managed.lease)
            .await
            .map_err(unwrap_db)
    }

    /// Release everything — the shutdown path.
    pub async fn relinquish_all(&mut self) -> Result<usize, sqlx::Error> {
        let channels = self.hosted();
        let mut n = 0;
        for c in channels {
            if self.relinquish(c).await? {
                n += 1;
            }
        }
        Ok(n)
    }
}

/// `ChannelError` wraps `sqlx::Error`; the manager's surface speaks sqlx so
/// callers are not forced to match on a kernel error type to find a DB
/// failure. A non-DB `ChannelError` here would mean the lease row vanished
/// mid-operation, which is not a case this layer can paper over.
fn unwrap_db(e: dp_kernel::channel::ChannelError) -> sqlx::Error {
    match e {
        dp_kernel::channel::ChannelError::Db(e) => e,
        other => sqlx::Error::Protocol(other.to_string()),
    }
}
