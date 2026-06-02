package store

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/services/breach-notifier/internal/migrate"
)

// PG-gated test for PgDeliveryStore: applies the embedded migration, then exercises the
// idempotency guard + the failed→delivered upsert (attempts increment, delivered_at
// stamped). Gated on PIIKMS_TEST_PG_URL. Re-run-safe: fresh incident_id + cleanup.
func TestLive_PgDeliveryStore(t *testing.T) {
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping breach-notifier store PG test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	if _, err := pool.Exec(ctx, migrate.UpSQL); err != nil {
		t.Fatalf("apply migration: %v", err)
	}

	s := NewPgDeliveryStore(pool)
	id := "inc-" + time.Now().UTC().Format("20060102150405.000000")
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DELETE FROM breach_dpo_delivery WHERE incident_id=$1`, id) })

	if ok, _ := s.AlreadyDelivered(ctx, id); ok {
		t.Fatalf("a fresh id must not be already-delivered")
	}

	now := time.Now().UTC().Truncate(time.Second)
	dl := now.Add(72 * time.Hour)
	// First: a failed attempt.
	if err := s.RecordAttempt(ctx, Delivery{IncidentID: id, Subject: "s", Deadline: dl, Channel: "log", Status: StatusFailed, LastError: "boom"}, now); err != nil {
		t.Fatalf("record failed: %v", err)
	}
	if ok, _ := s.AlreadyDelivered(ctx, id); ok {
		t.Errorf("a failed attempt must not count as delivered")
	}
	// Then: delivered.
	if err := s.RecordAttempt(ctx, Delivery{IncidentID: id, Subject: "s", Deadline: dl, Channel: "log", Status: StatusDelivered}, now); err != nil {
		t.Fatalf("record delivered: %v", err)
	}
	if ok, _ := s.AlreadyDelivered(ctx, id); !ok {
		t.Errorf("should be delivered now")
	}

	var attempts int
	var deliveredAt *time.Time
	var lastErr string
	if err := pool.QueryRow(ctx,
		`SELECT attempts, delivered_at, last_error FROM breach_dpo_delivery WHERE incident_id=$1`, id).
		Scan(&attempts, &deliveredAt, &lastErr); err != nil {
		t.Fatalf("read row: %v", err)
	}
	if attempts != 2 {
		t.Errorf("attempts: want 2 (failed then delivered), got %d", attempts)
	}
	if deliveredAt == nil {
		t.Errorf("delivered_at should be set on a delivered row")
	}
	if lastErr != "" {
		t.Errorf("last_error should be cleared on the delivered upsert, got %q", lastErr)
	}
}
