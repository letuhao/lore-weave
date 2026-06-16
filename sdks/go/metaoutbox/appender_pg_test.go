package metaoutbox

// PG-gated live test: proves Append writes a real meta_outbox row against the
// shipped migration 030 (so the SQL + the jsonb cast + the CHECK constraints
// all hold). Gated on PIIKMS_TEST_PG_URL (skips in the normal unit job), reusing
// the same env var the other meta PG-gated tests use.

import (
	"context"
	"os"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
)

// pgTxAdapter adapts a pgx.Tx to meta.Tx so the driver-clean appender can run
// against real Postgres without metaoutbox depending on metapg.
type pgTxAdapter struct{ tx pgx.Tx }

func (a pgTxAdapter) Exec(ctx context.Context, q string, args ...any) (int64, error) {
	tag, err := a.tx.Exec(ctx, q, args...)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

func TestLive_Append_WritesMetaOutboxRow(t *testing.T) {
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping meta_outbox PG test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)

	sql, rerr := os.ReadFile("../../../migrations/meta/030_meta_outbox.up.sql")
	if rerr != nil {
		t.Fatalf("read migration: %v", rerr)
	}
	if _, eerr := pool.Exec(ctx, string(sql)); eerr != nil {
		t.Fatalf("apply 030: %v", eerr)
	}

	a := New(map[string]string{"user.erased": "xreality.user.erased"})

	// Cross-reality event → xreality_topic stamped.
	erased := meta.OutboxEvent{
		EventID:     uuid.New(),
		EventName:   "user.erased",
		AggregateID: "user-pg-1",
		Payload:     map[string]any{"table": "pii_kek", "operation": "UPDATE", "pk": map[string]any{"kek_id": "k1"}},
		RecordedAt:  1717113600123456789,
	}
	// Meta-only event → NULL xreality_topic.
	consent := meta.OutboxEvent{
		EventID:     uuid.New(),
		EventName:   "user.consent.revoked",
		AggregateID: "user-pg-1",
		Payload:     map[string]any{"table": "user_consent_ledger", "operation": "UPDATE"},
		RecordedAt:  1717113600987654321,
	}

	tx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	adapter := pgTxAdapter{tx: tx}
	if err := a.Append(ctx, adapter, erased); err != nil {
		_ = tx.Rollback(ctx)
		t.Fatalf("append erased: %v", err)
	}
	if err := a.Append(ctx, adapter, consent); err != nil {
		_ = tx.Rollback(ctx)
		t.Fatalf("append consent: %v", err)
	}
	if err := tx.Commit(ctx); err != nil {
		t.Fatalf("commit: %v", err)
	}

	// Assert the cross-reality row.
	var (
		topic     *string
		published bool
		attempts  int
		recAt     int64
		payloadOK bool
	)
	if err := pool.QueryRow(ctx,
		`SELECT xreality_topic, published, attempts, recorded_at_nanos,
		        jsonb_typeof(payload) = 'object'
		   FROM meta_outbox WHERE event_id = $1`, erased.EventID).
		Scan(&topic, &published, &attempts, &recAt, &payloadOK); err != nil {
		t.Fatalf("query erased row: %v", err)
	}
	if topic == nil || *topic != "xreality.user.erased" {
		t.Errorf("erased xreality_topic mismatch: %v", topic)
	}
	if published || attempts != 0 {
		t.Errorf("fresh row must be unpublished/0 attempts, got published=%v attempts=%d", published, attempts)
	}
	if recAt != erased.RecordedAt {
		t.Errorf("recorded_at_nanos mismatch: got %d want %d", recAt, erased.RecordedAt)
	}
	if !payloadOK {
		t.Error("payload must be a jsonb object")
	}

	// Assert the meta-only row has NULL topic.
	var consentTopic *string
	if err := pool.QueryRow(ctx,
		`SELECT xreality_topic FROM meta_outbox WHERE event_id = $1`, consent.EventID).
		Scan(&consentTopic); err != nil {
		t.Fatalf("query consent row: %v", err)
	}
	if consentTopic != nil {
		t.Errorf("meta-only event must have NULL xreality_topic, got %v", *consentTopic)
	}
}
