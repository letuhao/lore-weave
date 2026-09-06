//! Pool construction.
//!
//! One function, because it carries a guard that is easy to omit and impossible
//! to notice missing.

use sqlx::PgPool;
use sqlx::postgres::PgPoolOptions;

/// Open a pool and prove it works before the caller announces readiness.
///
/// Two things this does that `PgPoolOptions::new().connect()` does not:
///
/// **It pings.** `connect_lazy` would let the process bind and answer `/livez`
/// with an unreachable database; a service that starts successfully against
/// nothing is harder to diagnose than one that refuses.
///
/// **It releases every advisory lock as a connection re-enters the pool.**
/// `capacity_glue::place_reality` takes a *session* advisory lock across the
/// pick→register critical section and unlocks on every RETURN path — but an
/// axum `TimeoutLayer` **drops** the handler future mid-await, and a dropped
/// future runs no unlock. The `PoolConnection` is dropped too, so the connection
/// goes back into the pool **still holding the shard's placement lock**, and
/// session locks release only when the connection closes. Every subsequent
/// placement on that shard then blocks until the pool happens to recycle it.
///
/// The `provision` worker could not hit this: a CLI either completes or dies,
/// and dying closes the connection. Serving the same code over HTTP is what
/// introduced the cancellation point, so the guard belongs here rather than in
/// `capacity_glue` — which keeps the worker's path byte-identical to what it was.
///
/// `pg_advisory_unlock_all()` is safe at exactly this moment and nowhere else: a
/// connection being released has no owner, so there is no lock on it that anyone
/// is still entitled to.
pub async fn connect(dsn: &str, label: &str, max_connections: u32) -> Result<PgPool, String> {
    let pool = PgPoolOptions::new()
        .max_connections(max_connections)
        .after_release(|conn, _meta| {
            Box::pin(async move {
                sqlx::query("SELECT pg_advisory_unlock_all()").execute(&mut *conn).await?;
                Ok(true)
            })
        })
        .connect(dsn)
        .await
        .map_err(|e| format!("connect {label} database: {e}"))?;
    sqlx::query("SELECT 1")
        .execute(&pool)
        .await
        .map_err(|e| format!("ping {label} database: {e}"))?;
    tracing::info!(%label, "database connected");
    Ok(pool)
}
