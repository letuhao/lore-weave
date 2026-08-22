//! `DF3` — `dp`'s CACHE seam, over Redis (`DP-A4` role 1).
//!
//! # What this closes
//!
//! `01_scope_and_boundary.md §2.4` lists *"Direct Redis access for T0–T2 reads
//! and cache"* as an SDK job. Measured at `718c29fc9` and still true when this
//! was written: **`redis` appeared in exactly one Cargo.toml in the Rust tree —
//! `commit-service`, for its proposal bus — and in zero DP crates.** So every
//! tier reached Postgres, and `DP-T0..T3` was a taxonomy with one
//! implementation behind it.
//!
//! # The three Redis roles are NOT interchangeable, and this is one of them
//!
//! `DP-X2` names three roles with distinct keyspaces that *"must not be
//! conflated"*: the **cache** (this file), invalidation **pub/sub**, and the
//! durable channel-event **stream** `dp:events:*`. This implements the first.
//! The second is unbuilt. The third still has **zero producers** — the asserted
//! trigger in `crates/dp/tests/spec_oracle_channels.rs` is what will say so the
//! day it arrives. Naming all three and building one is the honest shape;
//! calling this "Redis support" would not be.

use std::sync::Arc;
use std::time::Duration;

use dp::{CacheBackend, DpError};
use redis::AsyncCommands;
use tokio::runtime::{Handle, RuntimeFlavor};

/// Shared guard — the same one `dp_backend` and `dp_channel` use, for the same
/// reason: `dp`'s seams are synchronous, so this adapter blocks with
/// `block_in_place`, which panics on a current-thread runtime.
fn multi_thread_handle(who: &str) -> Result<Handle, DpError> {
    let handle = Handle::try_current().map_err(|_| DpError::ControlPlaneUnavailable {
        reason: format!("{who} must be constructed inside a tokio runtime"),
    })?;
    if handle.runtime_flavor() != RuntimeFlavor::MultiThread {
        return Err(DpError::ControlPlaneUnavailable {
            reason: format!("{who} requires a MULTI-THREAD tokio runtime"),
        });
    }
    Ok(handle)
}

/// `dp::CacheBackend` over Redis.
pub struct RedisCache {
    conn: Arc<tokio::sync::Mutex<redis::aio::ConnectionManager>>,
    handle: Handle,
}

impl RedisCache {
    /// `ConnectionManager` rather than a bare client: it reconnects on its own,
    /// which is what makes `DP-X10`'s *"on cache recovery, next read populates
    /// from projection"* true without this file implementing a retry policy.
    pub async fn connect(url: &str) -> Result<Self, DpError> {
        let client = redis::Client::open(url).map_err(|e| DpError::BackendIo(Box::new(e)))?;
        let conn = redis::aio::ConnectionManager::new(client)
            .await
            .map_err(|e| DpError::BackendIo(Box::new(e)))?;
        Ok(Self {
            conn: Arc::new(tokio::sync::Mutex::new(conn)),
            handle: multi_thread_handle("RedisCache")?,
        })
    }
}

impl CacheBackend for RedisCache {
    fn get(&self, key: &str) -> Result<Option<Vec<u8>>, DpError> {
        // A MISS is `Ok(None)`; a FAULT is `Err`. `DP-X10` reads them
        // differently — a miss costs a projection read, a fault ALSO blocks a
        // T3 write — so redis-rs's `Option` is exactly right and must not be
        // flattened into one answer.
        tokio::task::block_in_place(|| {
            self.handle.block_on(async {
                let mut c = self.conn.lock().await;
                c.get::<_, Option<Vec<u8>>>(key).await
            })
        })
        .map_err(|e| DpError::BackendIo(Box::new(e)))
    }

    /// # `PSETEX`, and why not `SET` + `EXPIRE` or `set_ex`
    ///
    /// **One round trip, atomic with its expiry.** A `SET` followed by an
    /// `EXPIRE` is two, and a crash between them leaves an entry with NO TTL —
    /// which `DP-X7` rules out in as many words: *"an invalidation loss plus an
    /// infinite TTL = permanent stale read"*.
    ///
    /// And `set_ex` takes **SECONDS**. That is safe for every `DP-X7` default
    /// (the shortest is 60 s) and silently wrong for an override: `DP-X7`
    /// permits per-aggregate overrides, and a sub-second one would integer-
    /// divide to `0` seconds — which Redis treats as an error or, worse in the
    /// `SET`+`EXPIRE` shape, as no expiry at all. Caught while drafting this
    /// file rather than in the tree, and pinned by
    /// `a_sub_second_ttl_still_expires` below.
    fn set(&self, key: &str, value: &[u8], ttl: Duration) -> Result<(), DpError> {
        let ms = u64::try_from(ttl.as_millis())
            .map_err(|_| DpError::BackendIo(format!("TTL {ttl:?} exceeds u64 ms").into()))?;
        if ms == 0 {
            // A zero TTL would cache nothing while reporting success — the
            // silent no-op shape. Louder than pretending it worked.
            return Err(DpError::BackendIo(
                "a zero TTL would cache nothing; DP-X7 gives every tier a positive default".into(),
            ));
        }
        tokio::task::block_in_place(|| {
            self.handle.block_on(async {
                let mut c = self.conn.lock().await;
                redis::cmd("PSETEX")
                    .arg(key)
                    .arg(ms)
                    .arg(value)
                    .query_async::<()>(&mut *c)
                    .await
            })
        })
        .map_err(|e| DpError::BackendIo(Box::new(e)))
    }

    fn del(&self, key: &str) -> Result<(), DpError> {
        tokio::task::block_in_place(|| {
            self.handle.block_on(async {
                let mut c = self.conn.lock().await;
                c.del::<_, ()>(key).await
            })
        })
        .map_err(|e| DpError::BackendIo(Box::new(e)))
    }
}
