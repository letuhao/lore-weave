// publisher_live_smoke_test.go — L2.D live wiring (DEFERRED 054).
//
// End-to-end smoke against REAL Postgres + REAL Redis (the foundation-dev
// stack). Proves the publisher's pgx Source/Batch + redis Emitter/fanout
// actually drain a per-reality events_outbox into Redis Streams — the bug
// surface mock-only tests can't reach (cf. F7 PgEventStore live-smoke).
//
// Flow:
//  1. Apply per-reality migrations to LW_INTEGRATION_DB.
//  2. Seed one normal + one cross_reality event+outbox row.
//  3. Run ONE poll_loop.Run with the live pgsource + redisemit.
//  4. Assert: both outbox rows published=TRUE; the per-reality stream got
//     ≥2 entries; the xreality.<type> stream got ≥1.
//  5. Failure path: a broken Redis client leaves the row unpublished with
//     attempts incremented + last_error set (retry, not dead-letter).
//
// gated by `integration`; needs LW_INTEGRATION_DB + LW_INTEGRATION_REDIS.
// Bootstrap: scripts/publisher-live-smoke.sh.
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

	"github.com/loreweave/foundation/services/publisher/pkg/leader_election"
	"github.com/loreweave/foundation/services/publisher/pkg/pgsource"
	"github.com/loreweave/foundation/services/publisher/pkg/poll_loop"
	"github.com/loreweave/foundation/services/publisher/pkg/realityreg"
	"github.com/loreweave/foundation/services/publisher/pkg/redisemit"
	"github.com/loreweave/foundation/services/publisher/pkg/retry"
	"github.com/loreweave/foundation/services/publisher/pkg/xreality_fanout"
)

// TestPublisherLiveSmoke_ActiveRealities exercises the bootstrap discovery
// path (realityreg.ActiveRealities against a live meta reality_registry) that
// the drain smoke injects pools around — closing the otherwise-untested SQL.
func TestPublisherLiveSmoke_ActiveRealities(t *testing.T) {
	dsn := os.Getenv("LW_INTEGRATION_DB")
	if dsn == "" {
		t.Skip("LW_INTEGRATION_DB not set; live stack unavailable")
	}
	ctx := context.Background()

	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("sql.Open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	mustApply(t, db, "migrations/meta/001_reality_registry.up.sql")

	activeID := uuid.New()
	droppedID := uuid.New()
	t.Cleanup(func() {
		_, _ = db.Exec(`DELETE FROM reality_registry WHERE reality_id = ANY($1)`,
			[]string{activeID.String(), droppedID.String()})
	})
	seedRegistry(t, db, activeID, "pg-shard-0.internal", "reality_live_a", "active")
	seedRegistry(t, db, droppedID, "pg-shard-1.internal", "reality_dead_b", "dropped")

	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("pgxpool.New: %v", err)
	}
	t.Cleanup(pool.Close)

	got, err := realityreg.ActiveRealities(ctx, pool)
	if err != nil {
		t.Fatalf("ActiveRealities: %v", err)
	}
	// The active row must appear with its routing; the dropped row must not.
	var foundActive, foundDropped bool
	for _, r := range got {
		switch r.ID {
		case activeID.String():
			foundActive = true
			if r.DBHost != "pg-shard-0.internal" || r.DBName != "reality_live_a" {
				t.Errorf("active reality routing wrong: %+v", r)
			}
		case droppedID.String():
			foundDropped = true
		}
	}
	if !foundActive {
		t.Error("ActiveRealities omitted the active reality")
	}
	if foundDropped {
		t.Error("ActiveRealities returned a dropped reality (must be excluded)")
	}
}

func seedRegistry(t *testing.T, db *sql.DB, id uuid.UUID, dbHost, dbName, status string) {
	t.Helper()
	if _, err := db.Exec(`
		INSERT INTO reality_registry
		    (reality_id, db_host, db_name, status, locale,
		     session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
		VALUES ($1,$2,$3,$4,'en',5,5,10,0)
	`, id, dbHost, dbName, status); err != nil {
		t.Fatalf("seed reality_registry %s: %v", id, err)
	}
}

func TestPublisherLiveSmoke_DrainsOutboxToRedis(t *testing.T) {
	dsn := os.Getenv("LW_INTEGRATION_DB")
	redisURL := os.Getenv("LW_INTEGRATION_REDIS")
	if dsn == "" || redisURL == "" {
		t.Skip("LW_INTEGRATION_DB / LW_INTEGRATION_REDIS not set; live stack unavailable")
	}
	ctx := context.Background()

	// ── DB: migrate + a clean per-reality slate ──────────────────────────
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("sql.Open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	// Apply 0002 (events) + 0005 (events_outbox) only. We deliberately skip
	// 0001_initial: it scaffolds skeleton tables that 0002 immediately DROPs,
	// and its `outbox`→`events(event_id)` FK is NOT re-runnable once 0002 has
	// repartitioned `events` (event_id is no longer a standalone unique key).
	// 0002's `DROP TABLE IF EXISTS events` makes 0002+0005 idempotent across
	// re-runs (matches scripts/foundation-dev-smoke-db.sh, which also skips 0001).
	mustApply(t, db, "contracts/migrations/per_reality/0002_events_table.up.sql")
	mustApply(t, db, "contracts/migrations/per_reality/0005_events_outbox_table.up.sql")

	realityID := uuid.New()
	normalID := uuid.New()
	xrealID := uuid.New()
	// Re-run safety: scope assertions to THIS run's reality_id.
	t.Cleanup(func() {
		_, _ = db.Exec(`DELETE FROM events_outbox WHERE reality_id=$1`, realityID)
		_, _ = db.Exec(`DELETE FROM events WHERE reality_id=$1`, realityID)
	})

	seedEvent(t, db, normalID, realityID, "npc.said", "npc", "npc-1", 1, `{"text":"hi"}`, nil)
	seedEvent(t, db, xrealID, realityID, "xreality.canon.promoted", "reality", realityID.String(), 7,
		`{"entry_id":"canon-42"}`, strPtr(`{"cross_reality":true}`))

	// ── Redis: real client; clean the target streams first ───────────────
	rOpts, err := redis.ParseURL(redisURL)
	if err != nil {
		t.Fatalf("redis.ParseURL: %v", err)
	}
	rdb := redis.NewClient(rOpts)
	t.Cleanup(func() { _ = rdb.Close() })
	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Fatalf("redis ping: %v", err)
	}
	mainStream := redisemit.StreamFor(realityID.String())
	xrealStream := "xreality.canon.promoted"
	_ = rdb.Del(ctx, mainStream).Err()
	// Per-reality stream is unique to this run — clean it up so the dev Redis
	// doesn't accumulate one stream per invocation. (The shared xreality
	// stream is left intact.)
	t.Cleanup(func() { _ = rdb.Del(context.Background(), mainStream).Err() })
	// Don't wipe the shared xreality stream; snapshot its length instead.
	xrealBefore := rdb.XLen(ctx, xrealStream).Val()

	// ── pgsource + emitters ───────────────────────────────────────────────
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("pgxpool.New: %v", err)
	}
	t.Cleanup(pool.Close)

	loop := buildLoop(t, map[string]*pgxpool.Pool{realityID.String(): pool}, rdb, realityID.String())

	stats, err := loop.Run(ctx)
	if err != nil {
		t.Fatalf("loop.Run: %v", err)
	}

	// ── Assertions: outbox marked, streams populated ──────────────────────
	if stats.Published != 2 {
		t.Errorf("Published=%d want 2", stats.Published)
	}
	if stats.FanoutOK != 1 {
		t.Errorf("FanoutOK=%d want 1 (one cross_reality row)", stats.FanoutOK)
	}
	assertPublished(t, db, normalID, true)
	assertPublished(t, db, xrealID, true)

	if got := rdb.XLen(ctx, mainStream).Val(); got < 2 {
		t.Errorf("per-reality stream %s XLEN=%d want >=2", mainStream, got)
	}
	if got := rdb.XLen(ctx, xrealStream).Val(); got < xrealBefore+1 {
		t.Errorf("xreality stream %s XLEN=%d want >=%d", xrealStream, got, xrealBefore+1)
	}

	// ── Failure path: broken Redis → retry, not published ─────────────────
	failID := uuid.New()
	seedEvent(t, db, failID, realityID, "npc.said", "npc", "npc-2", 1, `{"text":"x"}`, nil)
	broken := redis.NewClient(&redis.Options{Addr: "127.0.0.1:1", MaxRetries: -1})
	t.Cleanup(func() { _ = broken.Close() })
	failLoop := buildLoop(t, map[string]*pgxpool.Pool{realityID.String(): pool}, broken, realityID.String())
	fstats, err := failLoop.Run(ctx)
	if err != nil {
		t.Fatalf("failure-path loop.Run returned error (should classify+continue): %v", err)
	}
	if fstats.Retried != 1 {
		t.Errorf("Retried=%d want 1 on broken redis", fstats.Retried)
	}
	assertPublished(t, db, failID, false)
	var attempts int
	var lastErr sql.NullString
	if err := db.QueryRow(`SELECT attempts, last_error FROM events_outbox WHERE event_id=$1`, failID).
		Scan(&attempts, &lastErr); err != nil {
		t.Fatalf("scan failed row: %v", err)
	}
	if attempts != 1 {
		t.Errorf("attempts=%d want 1 after one failed XADD", attempts)
	}
	if !lastErr.Valid || lastErr.String == "" {
		t.Error("expected last_error to be recorded on retry")
	}
}

// TestPublisherLiveSmoke_BackoffExcludesRecentRetry proves the pgsource
// pending-scan honors the exponential backoff: a row that failed recently
// (attempts=5, last_attempt_at=NOW()) is invisible to the drain until its
// 1.6s backoff window elapses, so a stuck shard isn't hammered every tick.
func TestPublisherLiveSmoke_BackoffExcludesRecentRetry(t *testing.T) {
	dsn := os.Getenv("LW_INTEGRATION_DB")
	redisURL := os.Getenv("LW_INTEGRATION_REDIS")
	if dsn == "" || redisURL == "" {
		t.Skip("LW_INTEGRATION_DB / LW_INTEGRATION_REDIS not set; live stack unavailable")
	}
	ctx := context.Background()

	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatalf("sql.Open: %v", err)
	}
	t.Cleanup(func() { _ = db.Close() })
	mustApply(t, db, "contracts/migrations/per_reality/0002_events_table.up.sql")
	mustApply(t, db, "contracts/migrations/per_reality/0005_events_outbox_table.up.sql")

	realityID := uuid.New()
	recentID := uuid.New()
	t.Cleanup(func() {
		_, _ = db.Exec(`DELETE FROM events_outbox WHERE reality_id=$1`, realityID)
		_, _ = db.Exec(`DELETE FROM events WHERE reality_id=$1`, realityID)
	})
	// Seed the event, then an outbox row that already failed 5× a moment ago.
	seedEvent(t, db, recentID, realityID, "npc.said", "npc", "npc-9", 1, `{"text":"z"}`, nil)
	if _, err := db.Exec(`
		UPDATE events_outbox SET attempts=5, last_attempt_at=NOW(), last_error='boom'
		WHERE event_id=$1`, recentID); err != nil {
		t.Fatalf("set recent retry: %v", err)
	}

	rOpts, _ := redis.ParseURL(redisURL)
	rdb := redis.NewClient(rOpts)
	t.Cleanup(func() { _ = rdb.Close() })

	loop := buildLoop(t, map[string]*pgxpool.Pool{realityID.String(): openTestPool(t, ctx, dsn)}, rdb, realityID.String())
	stats, err := loop.Run(ctx)
	if err != nil {
		t.Fatalf("loop.Run: %v", err)
	}
	// The recent-retry row is still in its backoff window → NOT drained.
	if stats.Published != 0 || stats.Fetched != 0 {
		t.Errorf("recent-retry row should be excluded by backoff; got Fetched=%d Published=%d", stats.Fetched, stats.Published)
	}
	assertPublished(t, db, recentID, false)
}

func openTestPool(t *testing.T, ctx context.Context, dsn string) *pgxpool.Pool {
	t.Helper()
	p, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("pgxpool.New: %v", err)
	}
	t.Cleanup(p.Close)
	return p
}

func buildLoop(t *testing.T, pools map[string]*pgxpool.Pool, rdb *redis.Client, realityID string) *poll_loop.Loop {
	t.Helper()
	policy := retry.DefaultPolicy()
	src, err := pgsource.New(pools, policy)
	if err != nil {
		t.Fatalf("pgsource.New: %v", err)
	}
	fanout, err := xreality_fanout.New(redisemit.NewStreamEmitter(rdb, 0))
	if err != nil {
		t.Fatalf("xreality_fanout.New: %v", err)
	}
	loop, err := poll_loop.New(poll_loop.Config{
		Leader:    leader_election.NewNoOp(),
		Source:    src,
		Emitter:   redisemit.NewEmitter(rdb, 0),
		Fanout:    fanout,
		Mode:      modeFull{},
		Policy:    policy,
		BatchSize: 100,
		Realities: []string{realityID},
	})
	if err != nil {
		t.Fatalf("poll_loop.New: %v", err)
	}
	return loop
}

func seedEvent(t *testing.T, db *sql.DB, eventID, realityID uuid.UUID, eventType, aggType, aggID string, aggVer int, payload string, metadata *string) {
	t.Helper()
	if _, err := db.Exec(`
		INSERT INTO events
		    (event_id, reality_id, aggregate_type, aggregate_id, aggregate_version,
		     event_type, event_version, payload, metadata, occurred_at, recorded_at)
		VALUES ($1,$2,$3,$4,$5,$6,1,$7::jsonb,$8::jsonb,NOW(),NOW())
	`, eventID, realityID, aggType, aggID, aggVer, eventType, payload, metadata); err != nil {
		t.Fatalf("seed event %s: %v", eventID, err)
	}
	if _, err := db.Exec(`
		INSERT INTO events_outbox (event_id, reality_id, published, attempts)
		VALUES ($1,$2,FALSE,0)
	`, eventID, realityID); err != nil {
		t.Fatalf("seed outbox %s: %v", eventID, err)
	}
}

func assertPublished(t *testing.T, db *sql.DB, eventID uuid.UUID, want bool) {
	t.Helper()
	var got bool
	if err := db.QueryRow(`SELECT published FROM events_outbox WHERE event_id=$1`, eventID).Scan(&got); err != nil {
		t.Fatalf("scan published %s: %v", eventID, err)
	}
	if got != want {
		t.Errorf("event %s published=%v want %v", eventID, got, want)
	}
}

func strPtr(s string) *string { return &s }
