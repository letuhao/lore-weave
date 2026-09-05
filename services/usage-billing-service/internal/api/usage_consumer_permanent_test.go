package api

import (
	"errors"
	"fmt"
	"testing"

	"github.com/jackc/pgx/v5/pgconn"
)

// F6 — a violated CHECK is decided by the ROW, so retrying sends the identical row at the
// identical constraint and gets the identical answer.
//
// 🔴 MEASURED 2026-09-04. Two stream entries (1781773507908-0, 1781773507909-0) carried
// `model_source: "openai"` — a PROVIDER KIND in a field whose CHECK admits only `user_model`
// and `platform_model` — and were retried 50,529 times in 24 hours, each logged as
// "usage consumer transient failure (will retry)". `XINFO GROUPS` reported `lag: 0` with
// `pending: 3`: the stream had long moved on and the consumer group was spinning on its own
// Pending Entries List.
//
// The producer was ALREADY correct — `usage_outbox` holds only `user_model` today, with
// `provider_kind` in a separate column — so nothing about asking again was ever going to work.
//
// ⚠️ THE USAGE IS LOST EITHER WAY. That is what a violated CHECK means, and this change does not
// pretend otherwise. What it changes is that the loss is recorded ONCE and the group moves on,
// rather than being re-attempted twice a second forever while burying every genuine transient
// failure in the same log line.
func TestAConstraintViolationIsPermanent(t *testing.T) {
	// The exact code and constraint from the measured failure.
	err := fmt.Errorf("insert usage log: %w", &pgconn.PgError{
		Code:           "23514",
		ConstraintName: "usage_logs_model_source_check",
		Message:        `new row for relation "usage_logs" violates check constraint`,
	})
	if !isConstraintViolation(err) {
		t.Fatalf("a 23514 check violation must be PERMANENT — retrying it sent the same row at "+
			"the same constraint 50,529 times in 24 hours; got permanent=false for %v", err)
	}
}

// 🔴 THE ARM THAT KEEPS THIS HONEST. A DB blip must stay TRANSIENT and stay pending, or a
// restart-and-retry becomes a silent data loss — which is the opposite defect and the more
// expensive one, because the row was never wrong.
func TestATransientDatabaseErrorIsNotDropped(t *testing.T) {
	for _, err := range []error{
		errors.New("begin: connection reset by peer"),
		fmt.Errorf("commit: %w", errors.New("server closed the connection unexpectedly")),
		&pgconn.PgError{Code: "40001", Message: "could not serialize access"}, // serialization_failure
		&pgconn.PgError{Code: "57P01", Message: "terminating connection due to administrator command"},
		&pgconn.PgError{Code: "53300", Message: "too many connections"},
	} {
		if isConstraintViolation(err) {
			t.Fatalf("a transient failure was classified PERMANENT and would be DROPPED, losing "+
				"an audit row that was never wrong: %v", err)
		}
	}
}

// A unique violation is deliberately absent: `writeUsageLog` inserts ON CONFLICT DO NOTHING, so
// a duplicate is already a success and can never reach the failure branch. Listing it would be a
// classification for a case that cannot occur — a mechanism with no defect to catch.
func TestAUniqueViolationIsNotInTheSet(t *testing.T) {
	if isConstraintViolation(&pgconn.PgError{Code: "23505", Message: "duplicate key"}) {
		t.Fatal("23505 is handled by ON CONFLICT DO NOTHING and must not be classified here")
	}
}

// A non-Postgres error must not be mistaken for one. `errors.As` returning false is the whole
// safety of the check, and a nil error must never read as permanent.
func TestANonPostgresErrorIsNotAConstraintViolation(t *testing.T) {
	if isConstraintViolation(errors.New("redis: connection refused")) {
		t.Fatal("a non-Postgres error was classified as a constraint violation")
	}
	if isConstraintViolation(nil) {
		t.Fatal("nil must not classify as permanent")
	}
}

// The other payload-shaped codes travel the same path: a bad uuid or an over-long string is a
// property of the event, not of the database.
func TestThePayloadShapedCodesAreAlsoPermanent(t *testing.T) {
	for _, code := range []string{"23502", "23503", "22P02", "22001"} {
		if !isConstraintViolation(&pgconn.PgError{Code: code}) {
			t.Fatalf("%s is decided by the row and must be permanent", code)
		}
	}
}
