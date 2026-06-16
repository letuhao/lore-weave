// metaworker_live_smoke_test.go — L2.L + L5.B live wiring (DEFERRED 069).
//
// End-to-end on REAL Postgres + REAL Redis: the full canon fan-out spine.
//
//   seed canon.entry.created (cross_reality) in a per-reality events_outbox
//     → publisher Loop.Run  (drain → XADD xreality.book.canon.updated)
//     → meta-worker consumer.ProcessOne (XREADGROUP → canon_writer)
//     → UPSERT canon_projection on the subscribing reality + meta_write_audit
//
// Proves emit→publish→consume→project (4/5 of the P1 exit gate; the 5th —
// integrity-checker drift verify — stays deferred on the AggregateLoader).
//
// gated by `integration`; needs LW_INTEGRATION_DB (per-reality) +
// LW_INTEGRATION_META_DB (meta) + LW_INTEGRATION_REDIS.
// Bootstrap: scripts/metaworker-live-smoke.sh.
//
//go:build integration
// +build integration

package integration

import (
	"context"
	"database/sql"
	"os"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	_ "github.com/lib/pq"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/services/meta-worker/pkg/canon_writer"
	"github.com/loreweave/foundation/services/meta-worker/pkg/consumer"
	"github.com/loreweave/foundation/services/meta-worker/pkg/dispatch"
	"github.com/loreweave/foundation/services/meta-worker/pkg/pgwrite"
	"github.com/loreweave/foundation/services/meta-worker/pkg/redisconsume"

	"github.com/loreweave/foundation/services/publisher/pkg/leader_election"
	"github.com/loreweave/foundation/services/publisher/pkg/pgsource"
	pubpoll "github.com/loreweave/foundation/services/publisher/pkg/poll_loop"
	"github.com/loreweave/foundation/services/publisher/pkg/redisemit"
	"github.com/loreweave/foundation/services/publisher/pkg/retry"
	"github.com/loreweave/foundation/services/publisher/pkg/xreality_fanout"
)

func TestMetaWorkerLiveSmoke_CanonFanoutToProjection(t *testing.T) {
	perRealityDSN := os.Getenv("LW_INTEGRATION_DB")
	metaDSN := os.Getenv("LW_INTEGRATION_META_DB")
	redisURL := os.Getenv("LW_INTEGRATION_REDIS")
	if perRealityDSN == "" || metaDSN == "" || redisURL == "" {
		t.Skip("LW_INTEGRATION_DB / LW_INTEGRATION_META_DB / LW_INTEGRATION_REDIS not set")
	}
	ctx := context.Background()

	// ── DBs: migrate ─────────────────────────────────────────────────────
	rdb := openSQL(t, perRealityDSN)
	mdb := openSQL(t, metaDSN)
	mustApply(t, rdb, "contracts/migrations/per_reality/0002_events_table.up.sql")
	mustApply(t, rdb, "contracts/migrations/per_reality/0005_events_outbox_table.up.sql")
	mustApply(t, rdb, "contracts/migrations/per_reality/0009_canon_projection.up.sql")
	mustApply(t, mdb, "migrations/meta/001_reality_registry.up.sql")
	mustApply(t, mdb, "migrations/meta/013_meta_write_audit.up.sql")
	mustApply(t, mdb, "migrations/meta/026_book_reality_subscription.up.sql")

	realityID := uuid.New()
	bookID := uuid.New()
	canonEntryID := uuid.New()
	eventID := uuid.New()
	t.Cleanup(func() {
		_, _ = rdb.Exec(`DELETE FROM events_outbox WHERE reality_id=$1`, realityID)
		_, _ = rdb.Exec(`DELETE FROM events WHERE reality_id=$1`, realityID)
		_, _ = rdb.Exec(`DELETE FROM canon_projection WHERE canon_entry_id=$1`, canonEntryID)
		_, _ = mdb.Exec(`DELETE FROM book_reality_subscription WHERE book_id=$1`, bookID)
		_, _ = mdb.Exec(`DELETE FROM reality_registry WHERE reality_id=$1`, realityID)
		_, _ = mdb.Exec(`DELETE FROM meta_write_audit WHERE request_context->>'event_id'=$1`, eventID.String())
	})

	// ── Meta seed: reality_registry (active) + book subscription ─────────
	seedRegistry(t, mdb, realityID, "pg-shard-0.internal", "reality_canon", "active")
	if _, err := mdb.Exec(`INSERT INTO book_reality_subscription (book_id, reality_id) VALUES ($1,$2)`,
		bookID, realityID); err != nil {
		t.Fatalf("seed subscription: %v", err)
	}

	// ── Per-reality seed: canon.entry.created event + outbox (cross_reality) ─
	payload := `{"canon_entry_id":"` + canonEntryID.String() + `","book_id":"` + bookID.String() +
		`","attribute_path":"characters/alice/race","canon_layer":"L2_seeded","value":{"race":"elf"}}`
	seedEvent(t, rdb, eventID, realityID, "canon.entry.created", "canon", canonEntryID.String(), 3,
		payload, strPtr(`{"cross_reality":true}`))

	// ── Redis ─────────────────────────────────────────────────────────────
	rcli := newRedis(t, redisURL)
	canonStream := xreality_fanout.CanonFanoutTopic
	mainStream := redisemit.StreamFor(realityID.String())
	t.Cleanup(func() {
		_ = rcli.Del(context.Background(), mainStream).Err()
		_ = rcli.XGroupDestroy(context.Background(), canonStream, "meta-worker-smoke").Err()
	})

	// ── meta-worker consumer (create the group BEFORE the publisher XADDs) ─
	source, err := redisconsume.New(redisconsume.Config{
		RDB: rcli, Streams: []string{canonStream}, Group: "meta-worker-smoke", Consumer: "c1",
	})
	if err != nil {
		t.Fatalf("redisconsume.New: %v", err)
	}
	if err := source.EnsureGroups(ctx); err != nil {
		t.Fatalf("EnsureGroups: %v", err)
	}

	metaPool := openTestPool(t, ctx, metaDSN)
	realityPool := openTestPool(t, ctx, perRealityDSN)
	cw, err := canon_writer.New(canon_writer.Config{
		Subscribers: pgwrite.NewSubscribers(metaPool),
		DB:          pgwrite.NewCanonDB(map[string]*pgxpool.Pool{realityID.String(): realityPool}),
		Audit:       pgwrite.NewAudit(metaPool),
	})
	if err != nil {
		t.Fatalf("canon_writer.New: %v", err)
	}
	d := dispatch.New()
	for _, et := range canon_writer.EventTypes() {
		d.Register(et, cw.Handle)
	}
	if err := d.ValidateAllowlist(); err != nil {
		t.Fatalf("allowlist: %v", err)
	}
	cons, err := consumer.New(source, d)
	if err != nil {
		t.Fatalf("consumer.New: %v", err)
	}

	// ── Publisher drain → fanout to xreality.book.canon.updated ──────────
	if err := runPublisherOnce(t, ctx, perRealityDSN, rcli, realityID.String()); err != nil {
		t.Fatalf("publisher drain: %v", err)
	}

	// ── meta-worker consume → canon_writer → canon_projection ────────────
	stats, err := cons.ProcessOne(ctx, 10)
	if err != nil {
		t.Fatalf("ProcessOne: %v", err)
	}
	if stats.Dispatched != 1 {
		t.Fatalf("Dispatched=%d want 1 (read=%d noHandler=%d handlerErr=%d)",
			stats.Dispatched, stats.Read, stats.NoHandler, stats.HandlerErr)
	}

	// ── Assert canon_projection landed on the subscriber reality ─────────
	var gotBook, gotLayer, gotSource, gotValue string
	var gotAggVer int64
	err = rdb.QueryRow(`
		SELECT book_id::text, canon_layer, source_event_id::text, aggregate_version, value::text
		FROM canon_projection WHERE canon_entry_id=$1`, canonEntryID).
		Scan(&gotBook, &gotLayer, &gotSource, &gotAggVer, &gotValue)
	if err != nil {
		t.Fatalf("canon_projection row missing: %v", err)
	}
	if gotBook != bookID.String() {
		t.Errorf("book_id=%s want %s", gotBook, bookID)
	}
	if gotLayer != "L2_seeded" {
		t.Errorf("canon_layer=%s want L2_seeded", gotLayer)
	}
	if gotSource != eventID.String() {
		t.Errorf("source_event_id=%s want %s", gotSource, eventID)
	}
	if gotAggVer != 3 {
		t.Errorf("aggregate_version=%d want 3", gotAggVer)
	}
	// The canon VALUE must survive the publisher→Redis→consumer round-trip
	// (regression guard for the dropped-value HIGH bug from /review-impl).
	if gotValue != `{"race": "elf"}` {
		t.Errorf("canon value=%q want %q (value dropped?)", gotValue, `{"race": "elf"}`)
	}

	// Audit row written (Q-L1A-3).
	var auditCount int
	if err := mdb.QueryRow(`SELECT count(*) FROM meta_write_audit WHERE request_context->>'event_id'=$1`,
		eventID.String()).Scan(&auditCount); err != nil {
		t.Fatalf("audit count: %v", err)
	}
	if auditCount != 1 {
		t.Errorf("meta_write_audit rows=%d want 1", auditCount)
	}
}

// runPublisherOnce drains the per-reality outbox once with a real pgsource +
// redisemit (mirrors the publisher live-smoke), firing the canon fanout.
func runPublisherOnce(t *testing.T, ctx context.Context, dsn string, rcli *redis.Client, realityID string) error {
	t.Helper()
	pool := openTestPool(t, ctx, dsn)
	policy := retry.DefaultPolicy()
	src, err := pgsource.New(map[string]*pgxpool.Pool{realityID: pool}, policy)
	if err != nil {
		return err
	}
	fanout, err := xreality_fanout.New(redisemit.NewStreamEmitter(rcli, 0))
	if err != nil {
		return err
	}
	loop, err := pubpoll.New(pubpoll.Config{
		Leader:    leader_election.NewNoOp(),
		Source:    src,
		Emitter:   redisemit.NewEmitter(rcli, 0),
		Fanout:    fanout,
		Mode:      modeFull{},
		Policy:    policy,
		BatchSize: 100,
		Realities: []string{realityID},
	})
	if err != nil {
		return err
	}
	stats, err := loop.Run(ctx)
	if err != nil {
		return err
	}
	if stats.Published != 1 || stats.FanoutOK != 1 {
		t.Fatalf("publisher: Published=%d FanoutOK=%d want 1/1", stats.Published, stats.FanoutOK)
	}
	return nil
}

func openSQL(t *testing.T, dsn string) *sql.DB {
	t.Helper()
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("sql.Open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	return db
}

func newRedis(t *testing.T, url string) *redis.Client {
	t.Helper()
	opts, err := redis.ParseURL(url)
	if err != nil {
		t.Fatalf("redis.ParseURL: %v", err)
	}
	c := redis.NewClient(opts)
	t.Cleanup(func() { _ = c.Close() })
	if err := c.Ping(context.Background()).Err(); err != nil {
		t.Fatalf("redis ping: %v", err)
	}
	return c
}
