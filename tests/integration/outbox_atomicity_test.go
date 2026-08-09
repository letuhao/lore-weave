// outbox_atomicity_test.go — L2.C.5 (RAID cycle 10).
//
// Asserts the I13 / Q-L1B-3 atomicity contract: an event INSERT + an
// events_outbox INSERT bind to the SAME transaction. If the outbox INSERT
// fails (constraint violation, connection drop), the surrounding TX rolls
// back and NEITHER row is durable.
//
// Live-Postgres test; gated by the `integration` build tag + LW_INTEGRATION_DB
// env var (DSN). Mirrors cycle-9's pattern.
//
//go:build integration
// +build integration

package integration

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"testing"

	"github.com/google/uuid"
	_ "github.com/lib/pq"

	events "github.com/loreweave/foundation/contracts/events"
)

func TestOutboxAtomicity_RollbackOnPartialFail(t *testing.T) {
	dsn := os.Getenv("LW_INTEGRATION_DB")
	if dsn == "" {
		t.Skip("LW_INTEGRATION_DB not set; integration DB unavailable")
	}
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("sql.Open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })

	// Apply cycle-9 events table + cycle-10 outbox migration.
	//
	// `0001_initial` was applied here too, and the comment claimed the set was
	// idempotent. It was not: 0001 creates a plain `outbox` whose FK references
	// `events(event_id)`, and 0002 then DROPs `events` and recreates it PARTITIONED,
	// where `event_id` alone carries no unique constraint. First run on a virgin DB
	// passes because 0001 sees no `events` yet; every run after that dies in 0001 with
	// `no unique constraint matching given keys for referenced table "events" (42830)`.
	// Invisible in CI, which hands each run a fresh database, and immediate for anyone
	// re-running against a persistent one.
	//
	// This test never touches the plain `outbox` table — every assertion is against
	// `events_outbox` from 0005 — so 0001 was pure setup for a table nobody reads.
	// Dropped rather than reordered: the two migrations disagree about what `events` is,
	// and applying both was always going to be a coin toss on run order.
	mustApply(t, db, "contracts/migrations/per_reality/0002_events_table.up.sql")
	mustApply(t, db, "contracts/migrations/per_reality/0005_events_outbox_table.up.sql")

	realityID := uuid.New()
	eventID := uuid.New()
	dupEventID := uuid.New()

	// ── Happy path: event + outbox in same TX ─────────────────────────
	tx, err := db.BeginTx(context.Background(), nil)
	if err != nil {
		t.Fatalf("BeginTx: %v", err)
	}
	if _, err := tx.Exec(`
		INSERT INTO events
		    (event_id, reality_id, aggregate_type, aggregate_id,
		     aggregate_version, event_type, event_version, payload,
		     occurred_at, recorded_at)
		VALUES ($1, $2, 'reality', 'r1', 1, 'reality.created', 1, '{"x":1}', NOW(), NOW())
	`, eventID, realityID); err != nil {
		_ = tx.Rollback()
		t.Fatalf("event INSERT: %v", err)
	}
	if err := events.OutboxWrite(context.Background(), tx, events.OutboxRow{EventID: eventID, RealityID: realityID}); err != nil {
		_ = tx.Rollback()
		t.Fatalf("OutboxWrite: %v", err)
	}
	if err := tx.Commit(); err != nil {
		t.Fatalf("Commit: %v", err)
	}

	// Verify both rows landed.
	assertCount(t, db, "events", "WHERE event_id=$1", 1, eventID)
	assertCount(t, db, "events_outbox", "WHERE event_id=$1", 1, eventID)

	// ── Atomicity test: event INSERT succeeds, outbox INSERT collides ─
	// We force the outbox INSERT to fail by pre-inserting the SAME event_id
	// to events_outbox OUTSIDE the TX, then re-trying inside a TX with the
	// dupEventID as the event row + the SAME dup pkey to trigger PK conflict.
	if _, err := db.Exec(`INSERT INTO events_outbox (event_id, reality_id) VALUES ($1, $2)`, dupEventID, realityID); err != nil {
		t.Fatalf("seed outbox row: %v", err)
	}

	tx2, err := db.BeginTx(context.Background(), nil)
	if err != nil {
		t.Fatalf("BeginTx 2: %v", err)
	}
	stagedEventID := uuid.New()
	if _, err := tx2.Exec(`
		INSERT INTO events
		    (event_id, reality_id, aggregate_type, aggregate_id,
		     aggregate_version, event_type, event_version, payload,
		     occurred_at, recorded_at)
		VALUES ($1, $2, 'reality', 'r2', 1, 'reality.created', 1, '{"x":2}', NOW(), NOW())
	`, stagedEventID, realityID); err != nil {
		_ = tx2.Rollback()
		t.Fatalf("staged event INSERT: %v", err)
	}
	// Outbox INSERT with the duplicate event_id forces a unique-violation.
	werr := events.OutboxWrite(context.Background(), tx2, events.OutboxRow{EventID: dupEventID, RealityID: realityID})
	if werr == nil {
		_ = tx2.Rollback()
		t.Fatal("expected duplicate-key error on outbox INSERT")
	}
	if rberr := tx2.Rollback(); rberr != nil && !errors.Is(rberr, sql.ErrTxDone) {
		t.Fatalf("Rollback: %v", rberr)
	}

	// CRITICAL invariant: the staged event MUST NOT be durable.
	assertCount(t, db, "events", "WHERE event_id=$1", 0, stagedEventID)
}

func assertCount(t *testing.T, db *sql.DB, table, where string, want int, args ...any) {
	t.Helper()
	var n int
	row := db.QueryRow("SELECT count(*) FROM "+table+" "+where, args...)
	if err := row.Scan(&n); err != nil {
		t.Fatalf("count %s %s: %v", table, where, err)
	}
	if n != want {
		t.Errorf("table %s: expected %d rows, got %d", table, want, n)
	}
}
