//! Per-aggregate checkpoint store (resumability anchor).
//!
//! Production wiring writes to a `projection_rebuild_checkpoint` per-reality
//! table (cycle 15+); cycle 14 ships the trait + an in-memory impl so the
//! rebuilder is fully tested without DB.
//!
//! ## Schema (target, cycle 15+ migration)
//!
//! ```sql
//! CREATE TABLE projection_rebuild_checkpoint (
//!   projection_name      TEXT        NOT NULL,
//!   aggregate_type       TEXT        NOT NULL,
//!   aggregate_id         TEXT        NOT NULL,
//!   reality_id           UUID        NOT NULL,
//!   last_applied_version BIGINT      NOT NULL,
//!   completed            BOOLEAN     NOT NULL DEFAULT FALSE,
//!   updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
//!   PRIMARY KEY (projection_name, aggregate_type, aggregate_id, reality_id)
//! );
//! ```
//!
//! Updates MUST be atomic with the corresponding `apply_batch` (UPSERT in the
//! same TX) — the in-memory impl honors this by being a single map insert per
//! call.

use std::collections::HashMap;
use std::sync::Mutex;

use crate::AggregateRef;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Checkpoint {
    pub last_applied_version: u64,
    pub completed: bool,
}

pub trait CheckpointStore: Send + Sync {
    fn get(&self, projection_name: &str, agg: &AggregateRef) -> Result<Option<Checkpoint>, String>;
    fn set(&self, projection_name: &str, agg: &AggregateRef, cp: Checkpoint) -> Result<(), String>;
}

/// In-memory impl for tests. Key = (projection_name, agg).
#[derive(Default)]
pub struct InMemoryCheckpointStore {
    inner: Mutex<HashMap<(String, AggregateRef), Checkpoint>>,
}

impl CheckpointStore for InMemoryCheckpointStore {
    fn get(&self, projection_name: &str, agg: &AggregateRef) -> Result<Option<Checkpoint>, String> {
        Ok(self
            .inner
            .lock()
            .map_err(|e| e.to_string())?
            .get(&(projection_name.to_string(), agg.clone()))
            .cloned())
    }

    fn set(&self, projection_name: &str, agg: &AggregateRef, cp: Checkpoint) -> Result<(), String> {
        self.inner
            .lock()
            .map_err(|e| e.to_string())?
            .insert((projection_name.to_string(), agg.clone()), cp);
        Ok(())
    }
}
