//! L2.C outbox helper — Rust side.
//!
//! Provides the `write` function that callers (the eventual
//! `crates/dp-kernel::EventStore::append_event` in cycle 11/L4 and the
//! Rust services that bypass the Go EventStore for performance — world-service
//! tick loops, travel-service routing) use to enqueue an outbox row in the
//! SAME transaction as the `events` INSERT.
//!
//! ## Atomicity contract (I13, Q-L1B-3)
//!
//! The caller is RESPONSIBLE for opening the transaction and passing the
//! `Tx` handle into `write`. The function does not begin / commit / rollback
//! on its own. This keeps the helper composable with arbitrary domain logic
//! (e.g. a single command might write 1 event + 1 aggregate snapshot + 1
//! outbox row + N projection updates — all in one TX).
//!
//! The integration test `tests/integration/outbox_atomicity_test.rs` covers
//! the rollback-on-partial-fail invariant.
//!
//! ## Hosting note (V1 vs cycle-9)
//!
//! The cycle-9 events table is partitioned; cycle-10 outbox is NOT
//! partitioned (sized to peak in-flight ≈ outbox lag × event rate, hundreds
//! of thousands of rows even at V3 ≈ 10K realities × 100 events/s × 1s lag).
//! No partitioning needed for that volume; an INDEX-only table satisfies the
//! L2.D publisher poll loop.
//!
//! ## V1 transport-agnostic contract
//!
//! This file is intentionally TRANSPORT-AGNOSTIC: it does not depend on
//! `sqlx`, `tokio-postgres`, or any other concrete database driver. The
//! caller provides an `OutboxWriter` impl. World-service (sqlx) and
//! travel-service (sqlx) wire their own concrete writers in their cycle-12
//! integration cycles. This separation lets the cycle-10 unit suite run
//! without spinning up a Postgres process — same pattern as cycle 8's
//! validator + cycle 6's `Effects` trait.

use std::fmt;

use uuid::Uuid;

/// Errors emitted by the outbox write path.
#[derive(Debug, thiserror::Error)]
pub enum OutboxError {
    /// The underlying writer returned an error. The caller's TX should be
    /// rolled back; the event MUST NOT be considered durably appended.
    #[error("outbox writer error: {0}")]
    Writer(String),

    /// The caller passed an invalid envelope (zero UUID, missing reality_id,
    /// …). Cycle-8 envelope validation should have caught this earlier; this
    /// is the defense-in-depth check.
    #[error("invalid outbox row: {0}")]
    Invalid(String),
}

/// One row to insert into `events_outbox`. Mirrors the SQL schema
/// declared in `contracts/migrations/per_reality/0005_events_outbox_table.up.sql`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OutboxRow {
    pub event_id: Uuid,
    pub reality_id: Uuid,
}

impl fmt::Display for OutboxRow {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "OutboxRow(event_id={}, reality_id={})",
            self.event_id, self.reality_id
        )
    }
}

/// Abstract outbox writer. Concrete implementations bind to
/// `sqlx::Transaction` / `tokio-postgres::Transaction` and execute the
/// canonical INSERT statement returned by [`insert_sql`].
///
/// Implementations MUST execute the INSERT inside the caller-supplied TX
/// so that the rollback-on-event-fail invariant holds.
pub trait OutboxWriter {
    /// Returns an error iff the underlying transaction rejects the INSERT
    /// (constraint violation, connection drop). The caller MUST treat any
    /// returned error as fatal for the surrounding TX (i.e., bubble up so
    /// the TX rollback runs).
    fn write_row(&mut self, row: &OutboxRow) -> Result<(), OutboxError>;
}

/// The canonical INSERT statement for `events_outbox`. Kept centralized so
/// every concrete `OutboxWriter` writes identical SQL (no per-service
/// drift). Uses positional parameters `$1` / `$2` (Postgres-compatible).
///
/// Columns: `event_id`, `reality_id`. All other columns take their default
/// values per the cycle-10 migration (published=FALSE, attempts=0,
/// enqueued_at=NOW(), etc.).
pub fn insert_sql() -> &'static str {
    "INSERT INTO events_outbox (event_id, reality_id) VALUES ($1, $2)"
}

/// Enqueue one outbox row for the supplied event. The caller MUST invoke
/// this inside an open transaction that ALSO contains the `events` INSERT
/// — otherwise the L2.C atomicity contract is violated.
///
/// # Errors
///
/// - [`OutboxError::Invalid`] if the row carries a zero UUID for either
///   `event_id` or `reality_id`. This is a programmer error; cycle-8
///   envelope validation should have caught it.
/// - [`OutboxError::Writer`] if the underlying writer fails. The caller
///   MUST roll back the surrounding TX.
pub fn write<W: OutboxWriter>(writer: &mut W, row: OutboxRow) -> Result<(), OutboxError> {
    if row.event_id.is_nil() {
        return Err(OutboxError::Invalid("event_id is nil UUID".into()));
    }
    if row.reality_id.is_nil() {
        return Err(OutboxError::Invalid("reality_id is nil UUID".into()));
    }
    writer.write_row(&row)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// In-memory fake writer for unit tests. Captures every row + can be
    /// primed to fail on the Nth call (simulates DB error / partial-fail).
    struct FakeWriter {
        rows: Vec<OutboxRow>,
        fail_at_call: Option<usize>,
        call_count: usize,
    }

    impl FakeWriter {
        fn new() -> Self {
            Self {
                rows: vec![],
                fail_at_call: None,
                call_count: 0,
            }
        }

        fn fail_on_call(&mut self, n: usize) {
            self.fail_at_call = Some(n);
        }
    }

    impl OutboxWriter for FakeWriter {
        fn write_row(&mut self, row: &OutboxRow) -> Result<(), OutboxError> {
            self.call_count += 1;
            if let Some(n) = self.fail_at_call {
                if self.call_count == n {
                    return Err(OutboxError::Writer("simulated db error".into()));
                }
            }
            self.rows.push(row.clone());
            Ok(())
        }
    }

    fn sample_row() -> OutboxRow {
        OutboxRow {
            event_id: Uuid::parse_str("11111111-1111-1111-1111-111111111111").unwrap(),
            reality_id: Uuid::parse_str("22222222-2222-2222-2222-222222222222").unwrap(),
        }
    }

    #[test]
    fn write_happy_path_persists_row() {
        let mut w = FakeWriter::new();
        write(&mut w, sample_row()).expect("happy path");
        assert_eq!(w.rows.len(), 1);
        assert_eq!(w.rows[0], sample_row());
    }

    #[test]
    fn write_rejects_nil_event_id() {
        let mut w = FakeWriter::new();
        let row = OutboxRow {
            event_id: Uuid::nil(),
            reality_id: sample_row().reality_id,
        };
        let err = write(&mut w, row).expect_err("should reject nil event_id");
        assert!(matches!(err, OutboxError::Invalid(_)));
        assert!(w.rows.is_empty(), "no row should have been written");
    }

    #[test]
    fn write_rejects_nil_reality_id() {
        let mut w = FakeWriter::new();
        let row = OutboxRow {
            event_id: sample_row().event_id,
            reality_id: Uuid::nil(),
        };
        let err = write(&mut w, row).expect_err("should reject nil reality_id");
        assert!(matches!(err, OutboxError::Invalid(_)));
        assert!(w.rows.is_empty());
    }

    #[test]
    fn writer_error_propagates() {
        let mut w = FakeWriter::new();
        w.fail_on_call(1);
        let err = write(&mut w, sample_row()).expect_err("writer should fail");
        assert!(matches!(err, OutboxError::Writer(_)));
        assert!(w.rows.is_empty(), "row must not be cached on writer fail");
    }

    /// Atomicity contract — simulates a TX with two intents (event append
    /// + outbox write). If the outbox write fails, the caller MUST roll
    /// back and the simulated event row MUST be discarded. This test is
    /// the unit-level mirror of the integration test in
    /// `tests/integration/outbox_atomicity_test.rs` (which runs against a
    /// real Postgres).
    #[test]
    fn atomicity_simulation_rollback_on_outbox_fail() {
        // Simulate an in-memory "TX": events_written stays empty unless
        // BOTH the event "INSERT" and the outbox INSERT succeed.
        let mut events_written: Vec<Uuid> = vec![];

        let mut w = FakeWriter::new();
        w.fail_on_call(1);

        let row = sample_row();
        // "Begin TX" — stage the event in memory.
        let staged_event = row.event_id;

        // Attempt outbox write inside the TX.
        let result = write(&mut w, row);

        // "Commit OR rollback" — emulate sqlx's rollback-on-Err pattern.
        match result {
            Ok(()) => {
                events_written.push(staged_event);
            }
            Err(_) => {
                // ROLLBACK — events_written stays empty.
            }
        }

        assert!(
            events_written.is_empty(),
            "atomicity violated: event should NOT be durable when outbox fails"
        );
    }

    #[test]
    fn insert_sql_uses_two_positional_params() {
        let sql = insert_sql();
        assert!(sql.contains("INSERT INTO events_outbox"));
        assert!(sql.contains("$1"));
        assert!(sql.contains("$2"));
        assert!(
            !sql.contains("$3"),
            "outbox INSERT should bind exactly 2 params (event_id, reality_id)"
        );
    }
}
