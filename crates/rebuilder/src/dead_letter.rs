//! Dead-letter store for aggregates that exhausted retries.
//!
//! Production wiring writes to a `projection_rebuild_errors` per-reality
//! table; SRE runbook (`runbooks/disaster/projection_loss.md` cycle 14 / DPS 3)
//! tells the operator how to inspect + re-queue.
//!
//! ## Schema (target, cycle 15+ migration)
//!
//! ```sql
//! CREATE TABLE projection_rebuild_errors (
//!   id               BIGSERIAL PRIMARY KEY,
//!   projection_name  TEXT        NOT NULL,
//!   aggregate_type   TEXT        NOT NULL,
//!   aggregate_id     TEXT        NOT NULL,
//!   reality_id       UUID        NOT NULL,
//!   last_error       TEXT        NOT NULL,
//!   attempts         INT         NOT NULL,
//!   recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
//! );
//! ```

use std::sync::Mutex;

use crate::AggregateRef;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeadLetterEntry {
    pub agg: AggregateRef,
    pub projection_name: String,
    pub last_error: String,
    pub attempts: u32,
}

pub trait DeadLetterStore: Send + Sync {
    fn record(&self, entry: DeadLetterEntry) -> Result<(), String>;
}

#[derive(Default)]
pub struct InMemoryDeadLetterStore {
    inner: Mutex<Vec<DeadLetterEntry>>,
}

impl InMemoryDeadLetterStore {
    pub fn list(&self) -> Vec<DeadLetterEntry> {
        self.inner.lock().unwrap().clone()
    }
}

impl DeadLetterStore for InMemoryDeadLetterStore {
    fn record(&self, entry: DeadLetterEntry) -> Result<(), String> {
        self.inner
            .lock()
            .map_err(|e| e.to_string())?
            .push(entry);
        Ok(())
    }
}
