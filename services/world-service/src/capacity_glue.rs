//! W1.1 — Capacity routing glue (production wiring of [`CapacityPlanner`]).
//!
//! The planner (`capacity_planner.rs`) is a pure function: snapshot in, shard
//! out. Until now nothing supplied the snapshot at provision time — that gap is
//! `D-S13-CAPACITY-ROUTING-GLUE`. This module is the live read + the
//! placement critical section.
//!
//! ## Where the snapshot comes from (self-review, plan §W1.1)
//!
//! - **`total` (per-shard capacity)** + the **shard list** come from
//!   `shard_utilization` — the latest snapshot row per `shard_host`. That table
//!   is where a shard's `capacity_max_dbs` is *declared* when the shard is
//!   registered; it is the authoritative "which shards exist + their caps".
//! - **`used` (live occupancy)** comes from a fresh `COUNT(*)` over
//!   `reality_registry` GROUP BY `db_host` — NOT from `shard_utilization.
//!   current_db_count`. The metrics job that refreshes `current_db_count` is
//!   unbuilt, so trusting it would either return stale/zero counts (→
//!   over-subscription) or, if no snapshot exists, refuse everything. The
//!   registry count is always present and always current.
//!
//! So `shard_utilization` supplies the cap (cold config); `reality_registry`
//! supplies occupancy (live). There is deliberately **no** `current_db_count <=
//! capacity_max_dbs` DB CHECK — the metrics table must be able to *observe* a
//! transient over-subscription, not forbid recording it. Enforcement is here,
//! at provision time, via [`place_reality`].
//!
//! ## Live occupancy states
//!
//! [`LIVE_STATES`] counts every reality whose physical per-reality DB still
//! occupies a slot on the shard. A DB physically exists from `CREATE DATABASE`
//! (provisioning step 4, after the `register_pending` row at step 3) until
//! `DROP DATABASE`. We count the in-flight + live + quiescing states and treat
//! the archive/drop tail as already reclaiming the slot. This is conservative
//! against the failure that matters (under-counting → over-subscription): the
//! only states excluded are ones whose DB is gone or being torn down.
//!
//! ## TOCTOU (plan review #2)
//!
//! `count → pick → register` is not atomic: two concurrent provisions read the
//! same counts, pick the same least-full shard, both register → over by one.
//! [`place_reality`] closes this with a **per-shard session advisory lock** held
//! across the critical section: a second provision targeting the same shard
//! blocks until the first has registered (and released), then **recounts under
//! the lock** and re-picks if the shard filled. The lock is session-level (not
//! `xact`) so it can span the `register` callback even when that callback writes
//! through a *different* connection — i.e. the Go meta-write bridge (W1.5),
//! whose audited INSERT commits on the Go side before we release. If the lock
//! connection dies, Postgres releases the session lock automatically (safety
//! net against a leaked lock).

use std::future::Future;

use sqlx::postgres::PgPool;
use sqlx::Acquire;

use crate::capacity_planner::{CapacityPlanner, ShardCapacity, ShardId};
use crate::errors::ProvisionerError;

/// Reality lifecycle states whose per-reality DB still occupies a shard slot.
///
/// Excluded (slot freed / being reclaimed): `archived`, `archived_verified`,
/// `soft_deleted`, `dropped`. `frozen` is **included** — a frozen reality's DB
/// is intact (frozen for migration/closure), so it still consumes a slot.
pub const LIVE_STATES: [&str; 6] = [
    "provisioning",
    "seeding",
    "active",
    "migrating",
    "pending_close",
    "frozen",
];

/// Advisory-lock namespace (first key of the two-int `pg_advisory_lock` form).
/// Distinguishes capacity-placement locks from any other advisory lock the
/// platform takes. ASCII "CP" (0x4350).
const LOCK_NAMESPACE: i32 = 0x4350;

/// Read the live capacity snapshot: every registered shard with its declared
/// cap (`shard_utilization`, latest row per host) and its live occupancy
/// (`reality_registry` count over [`LIVE_STATES`]).
///
/// Shards with no `reality_registry` rows still appear (LEFT JOIN, used=0) so a
/// fresh shard is eligible. A shard absent from `shard_utilization` does NOT
/// appear — registering a shard means seeding its `shard_utilization` cap row.
pub async fn live_snapshot(pool: &PgPool) -> Result<Vec<ShardCapacity>, ProvisionerError> {
    let mut conn = pool
        .acquire()
        .await
        .map_err(|e| ProvisionerError::BadCapacity(format!("acquire: {e}")))?;
    snapshot_on(&mut conn).await
}

/// Snapshot on a caller-supplied connection (so [`place_reality`] can recount
/// on the same connection that holds the advisory lock).
async fn snapshot_on(
    conn: &mut sqlx::PgConnection,
    ) -> Result<Vec<ShardCapacity>, ProvisionerError> {
    // Bind LIVE_STATES as a text[] so the IN-list is a single parameter.
    let live: Vec<String> = LIVE_STATES.iter().map(|s| s.to_string()).collect();
    let rows: Vec<(String, i32, i64)> = sqlx::query_as(
        r#"
        WITH shards AS (
            SELECT DISTINCT ON (shard_host) shard_host, capacity_max_dbs
              FROM shard_utilization
             ORDER BY shard_host, snapshot_at DESC
        ),
        used AS (
            SELECT db_host, count(*)::bigint AS n
              FROM reality_registry
             WHERE status = ANY($1)
             GROUP BY db_host
        )
        SELECT s.shard_host,
               s.capacity_max_dbs,
               COALESCE(u.n, 0) AS used
          FROM shards s
          LEFT JOIN used u ON u.db_host = s.shard_host
         ORDER BY s.shard_host
        "#,
    )
    .bind(&live)
    .fetch_all(&mut *conn)
    .await
    .map_err(|e| ProvisionerError::BadCapacity(format!("live_snapshot query: {e}")))?;

    rows.into_iter()
        .map(|(host, cap, used)| {
            let total = u32::try_from(cap).map_err(|_| {
                ProvisionerError::BadCapacity(format!("shard {host}: negative cap {cap}"))
            })?;
            let used = u32::try_from(used.max(0)).unwrap_or(u32::MAX);
            Ok(ShardCapacity {
                shard_id: ShardId::new(host),
                total_realities: total,
                used_realities: used,
            })
        })
        .collect()
}

/// Fresh occupancy count for a single shard host (recount under the lock).
async fn count_used(
    conn: &mut sqlx::PgConnection,
    host: &str,
) -> Result<u32, ProvisionerError> {
    let live: Vec<String> = LIVE_STATES.iter().map(|s| s.to_string()).collect();
    let (n,): (i64,) = sqlx::query_as(
        "SELECT count(*)::bigint FROM reality_registry WHERE db_host = $1 AND status = ANY($2)",
    )
    .bind(host)
    .bind(&live)
    .fetch_one(&mut *conn)
    .await
    .map_err(|e| ProvisionerError::BadCapacity(format!("recount {host}: {e}")))?;
    Ok(u32::try_from(n.max(0)).unwrap_or(u32::MAX))
}

/// Cap (`capacity_max_dbs`) for a single shard host, latest snapshot.
async fn shard_cap(
    conn: &mut sqlx::PgConnection,
    host: &str,
) -> Result<u32, ProvisionerError> {
    let row: Option<(i32,)> = sqlx::query_as(
        r#"SELECT capacity_max_dbs FROM shard_utilization
            WHERE shard_host = $1 ORDER BY snapshot_at DESC LIMIT 1"#,
    )
    .bind(host)
    .fetch_optional(&mut *conn)
    .await
    .map_err(|e| ProvisionerError::BadCapacity(format!("shard_cap {host}: {e}")))?;
    match row {
        Some((cap,)) => u32::try_from(cap)
            .map_err(|_| ProvisionerError::BadCapacity(format!("shard {host}: negative cap"))),
        None => Err(ProvisionerError::BadCapacity(format!(
            "shard {host} vanished from shard_utilization between pick and lock"
        ))),
    }
}

/// Stable 32-bit key for a shard host (advisory-lock second key).
fn shard_lock_key(host: &str) -> i32 {
    // FNV-1a 32-bit, reinterpreted as i32 (advisory locks take signed ints).
    let mut h: u32 = 0x811c_9dc5;
    for b in host.as_bytes() {
        h ^= *b as u32;
        h = h.wrapping_mul(0x0100_0193);
    }
    h as i32
}

async fn advisory_lock(
    conn: &mut sqlx::PgConnection,
    host: &str,
) -> Result<(), ProvisionerError> {
    sqlx::query("SELECT pg_advisory_lock($1, $2)")
        .bind(LOCK_NAMESPACE)
        .bind(shard_lock_key(host))
        .execute(&mut *conn)
        .await
        .map_err(|e| ProvisionerError::BadCapacity(format!("advisory_lock {host}: {e}")))?;
    Ok(())
}

async fn advisory_unlock(conn: &mut sqlx::PgConnection, host: &str) {
    // Best-effort: a failed unlock is harmless (session end releases it). We do
    // NOT propagate — the caller's result for the placement itself is what matters.
    let _ = sqlx::query("SELECT pg_advisory_unlock($1, $2)")
        .bind(LOCK_NAMESPACE)
        .bind(shard_lock_key(host))
        .execute(&mut *conn)
        .await;
}

/// Place a reality on the least-full shard with capacity, TOCTOU-safe.
///
/// `register` performs the actual `reality_registry` reservation INSERT for the
/// chosen shard — in production it goes through the Go meta-write bridge (W1.5,
/// so the I8 audit lands); the W1.1 live drill passes a direct INSERT. It is
/// invoked **exactly once**, while the per-shard advisory lock is held (when
/// `lock_enabled`), after a fresh recount confirms room.
///
/// Set `lock_enabled = false` for the non-vacuity **bite**: it skips the lock +
/// recount and registers against the stale snapshot, so K concurrent
/// placements onto M<K free slots over-subscribe — the exact race the lock
/// prevents.
///
/// Returns the chosen [`ShardId`], or [`ProvisionerError::NoShardCapacity`] when
/// every shard is full.
pub async fn place_reality<F, Fut>(
    pool: &PgPool,
    planner: &CapacityPlanner,
    lock_enabled: bool,
    register: F,
) -> Result<ShardId, ProvisionerError>
where
    F: FnOnce(&ShardId) -> Fut,
    Fut: Future<Output = Result<(), ProvisionerError>>,
{
    let mut conn = pool
        .acquire()
        .await
        .map_err(|e| ProvisionerError::BadCapacity(format!("acquire: {e}")))?;
    let conn = conn.acquire().await.map_err(|e| {
        ProvisionerError::BadCapacity(format!("acquire inner: {e}"))
    })?;

    // Re-pick loop: each iteration either commits to a shard (holding its lock)
    // or finds the picked shard filled under the lock and retries. Bounded so a
    // pathological churn can't spin forever — every retry has eliminated one
    // now-full shard from contention.
    let mut held: Option<ShardId> = None;
    let mut guard_attempts = 0usize;
    let chosen = loop {
        let snap = snapshot_on(conn).await?;
        let max_attempts = snap.len() + 2;
        let picked = planner.pick_shard(&snap)?.shard_id.clone();

        if !lock_enabled {
            // BITE: no lock, no recount — register against the (stale) snapshot.
            break picked;
        }

        advisory_lock(conn, picked.as_str()).await?;
        let used = count_used(conn, picked.as_str()).await?;
        let cap = shard_cap(conn, picked.as_str()).await?;
        if used < cap {
            held = Some(picked.clone());
            break picked;
        }
        // Filled while we waited — release and re-pick.
        advisory_unlock(conn, picked.as_str()).await;
        guard_attempts += 1;
        if guard_attempts > max_attempts {
            return Err(ProvisionerError::NoShardCapacity);
        }
    };

    let res = register(&chosen).await;
    if let Some(h) = held {
        advisory_unlock(conn, h.as_str()).await;
    }
    res.map(|()| chosen)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lock_key_is_stable_and_host_specific() {
        assert_eq!(
            shard_lock_key("pg-shard-0.internal"),
            shard_lock_key("pg-shard-0.internal")
        );
        assert_ne!(
            shard_lock_key("pg-shard-0.internal"),
            shard_lock_key("pg-shard-1.internal")
        );
    }

    #[test]
    fn live_states_excludes_terminal_and_archive() {
        for s in ["archived", "archived_verified", "soft_deleted", "dropped"] {
            assert!(!LIVE_STATES.contains(&s), "{s} must not count as occupying");
        }
        for s in ["provisioning", "seeding", "active", "migrating", "pending_close", "frozen"] {
            assert!(LIVE_STATES.contains(&s), "{s} must count as occupying");
        }
    }
}
