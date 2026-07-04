package migrate

// P2·F review MED-3 — real-PG proof of the load-bearing coalescing invariant.
//
// The api-package unit test only asserts the INSERT text contains "ON CONFLICT
// … DO NOTHING". That does NOT prove the ON CONFLICT target
// (actor_id, book_id, outcome, coalesce_bucket) actually binds to a real unique
// constraint — if a future edit dropped or re-columned uq_tenant_audit_window, the
// insert would raise "there is no unique constraint matching the ON CONFLICT
// specification" at RUNTIME (a 500 caught only live). This test runs the real DDL
// (Up) on an ephemeral Postgres and asserts the EFFECT: a duplicate insert in the
// same window collapses to ONE row, and a different outcome is a distinct row.
// Needs GLOSSARY_TEST_DB_URL (skips otherwise; ephemeral DB, safe).

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestTenantAccessAudit_DedupsWithinWindow(t *testing.T) {
	pool := ephemeralPool(t, "tenantaudit")
	ctx := context.Background()
	if err := Up(ctx, pool); err != nil {
		t.Fatalf("migrate Up: %v", err)
	}

	// Mirrors glossary api.insertTenantAudit exactly (4 cols, no owner_id). If the
	// ON CONFLICT columns don't match uq_tenant_audit_window, this INSERT errors.
	const insertSQL = `
		INSERT INTO tenant_access_audit (actor_id, book_id, outcome, coalesce_bucket)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (actor_id, book_id, outcome, coalesce_bucket) DO NOTHING`

	actor, book := uuid.New(), uuid.New()
	bucket := time.Date(2026, 7, 5, 10, 0, 0, 0, time.UTC)

	// Two inserts, same key, same window → the ON CONFLICT must collapse to ONE row.
	for i := range 2 {
		if _, err := pool.Exec(ctx, insertSQL, actor, book, "granted", bucket); err != nil {
			t.Fatalf("insert %d (proves ON CONFLICT binds to the real unique index): %v", i, err)
		}
	}
	var n int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM tenant_access_audit WHERE actor_id=$1 AND book_id=$2`, actor, book,
	).Scan(&n); err != nil {
		t.Fatalf("count: %v", err)
	}
	if n != 1 {
		t.Fatalf("coalescing failed: want 1 row after a duplicate insert, got %d", n)
	}

	// A different OUTCOME is a distinct key → a second row (granted↔denied both kept).
	if _, err := pool.Exec(ctx, insertSQL, actor, book, "denied", bucket); err != nil {
		t.Fatalf("insert denied: %v", err)
	}
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM tenant_access_audit WHERE actor_id=$1 AND book_id=$2`, actor, book,
	).Scan(&n); err != nil {
		t.Fatalf("count 2: %v", err)
	}
	if n != 2 {
		t.Fatalf("a distinct outcome must be a distinct row: want 2, got %d", n)
	}

	// The outcome CHECK enum must reject an out-of-set value (schema integrity).
	if _, err := pool.Exec(ctx, insertSQL, actor, book, "bogus", bucket); err == nil {
		t.Fatal("outcome CHECK must reject a value outside ('granted','denied')")
	}
}
