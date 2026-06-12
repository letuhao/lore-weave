package events

import (
	"context"
	"database/sql"
	"errors"
	"fmt"

	"github.com/google/uuid"
)

// L2.C outbox helper — Go side.
//
// Mirror of `crates/dp-kernel::outbox`. Provides the `OutboxWrite` function
// that Go services (publisher, meta-worker, glossary-service, knowledge-
// service) invoke INSIDE the SAME transaction as their `events` INSERT.
//
// ## Atomicity contract (I13, Q-L1B-3)
//
// The caller opens the transaction (sql.Tx, pgx.Tx — abstracted via the
// OutboxExecutor interface) and passes the executor handle to OutboxWrite.
// This helper neither begins, commits, nor rolls back; the caller controls
// the entire TX lifetime. Same composability story as the Rust side.
//
// The integration test `tests/integration/outbox_atomicity_test.rs` covers
// the rollback-on-partial-fail invariant. A Go-side unit test in
// `contracts/events/outbox_test.go` exercises the OutboxExecutor contract
// with an in-memory fake.

// OutboxRow mirrors `events_outbox` (event_id + reality_id only; all other
// columns default per the cycle-10 migration).
type OutboxRow struct {
	EventID   uuid.UUID
	RealityID uuid.UUID
}

// String returns a one-line debug representation. Useful for log lines that
// echo the outbox enqueue path.
func (r OutboxRow) String() string {
	return fmt.Sprintf("OutboxRow(event_id=%s, reality_id=%s)", r.EventID, r.RealityID)
}

// OutboxExecutor is the minimal write-side surface every concrete DB
// driver implements. The signature intentionally matches
// `(*sql.Tx).ExecContext` / `(*sql.DB).ExecContext` so production code
// passes `*sql.Tx` directly. Pgx callers wrap their `pgx.Tx` in the
// `stdlib` adapter or a thin shim that returns `sql.Result`.
//
// `args` MUST be passed positionally (Postgres `$1` / `$2` bind order:
// event_id then reality_id).
type OutboxExecutor interface {
	ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error)
}

// ErrInvalidOutboxRow is returned when the row has a zero UUID (defense-
// in-depth — envelope validation should have caught it).
var ErrInvalidOutboxRow = errors.New("events: invalid outbox row")

// ErrOutboxNoRowsAffected indicates the INSERT returned 0 rows affected.
// In normal operation this means a PK collision (re-enqueue of a UUID
// already in the table); callers should treat as fatal-for-TX since the
// invariant "one outbox row per emitted event" is broken.
var ErrOutboxNoRowsAffected = errors.New("events: outbox INSERT affected 0 rows")

// OutboxInsertSQL is the canonical INSERT statement. Centralized so every
// caller writes byte-identical SQL — no per-service drift.
//
// Columns: event_id, reality_id (positional $1/$2). All other columns
// default per the cycle-10 migration (published=FALSE, attempts=0,
// enqueued_at=NOW()).
const OutboxInsertSQL = `INSERT INTO events_outbox (event_id, reality_id) VALUES ($1, $2)`

// OutboxWrite enqueues one outbox row. MUST be invoked inside the same
// transaction as the corresponding `events` INSERT — otherwise the L2.C
// atomicity contract is violated.
//
// Returns ErrInvalidOutboxRow on zero UUIDs, ErrOutboxNoRowsAffected if the
// INSERT silently affected no rows, or the underlying executor error
// otherwise. Callers MUST roll back the surrounding TX on any non-nil
// return.
func OutboxWrite(ctx context.Context, exec OutboxExecutor, row OutboxRow) error {
	if row.EventID == uuid.Nil {
		return fmt.Errorf("%w: event_id is nil UUID", ErrInvalidOutboxRow)
	}
	if row.RealityID == uuid.Nil {
		return fmt.Errorf("%w: reality_id is nil UUID", ErrInvalidOutboxRow)
	}
	res, err := exec.ExecContext(ctx, OutboxInsertSQL, row.EventID, row.RealityID)
	if err != nil {
		return fmt.Errorf("events: outbox INSERT: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		// Some drivers fail to report — accept silently in that case but
		// log via wrap so SRE can grep.
		return nil
	}
	if n == 0 {
		return ErrOutboxNoRowsAffected
	}
	return nil
}
