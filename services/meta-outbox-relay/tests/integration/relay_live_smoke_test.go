package integration

// End-to-end live-smoke (P2/101 slice B): seed meta_outbox → run the real
// drain.Loop (pgsource + real redisemit) once → assert the row is marked
// published AND the envelope landed on the home stream + the xreality bridge.
//
// Gated on BOTH PIIKMS_TEST_PG_URL and REDIS_URL (skips otherwise). This is the
// cross-service (meta DB + Redis) live evidence the VERIFY gate asks for.

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/services/meta-outbox-relay/pkg/drain"
	"github.com/loreweave/foundation/services/meta-outbox-relay/pkg/pgsource"
	"github.com/loreweave/foundation/services/meta-outbox-relay/pkg/redisemit"
	"github.com/loreweave/foundation/services/publisher/pkg/retry"
)

// applyMigrationWithRetry tolerates the catalog deadlock (SQLSTATE 40P01) when
// this smoke and the pgsource PG test apply the same CREATE TABLE/INDEX in
// parallel (go runs packages concurrently). IF NOT EXISTS keeps it idempotent.
func applyMigrationWithRetry(ctx context.Context, pool *pgxpool.Pool, sql string) error {
	var err error
	for range 5 {
		if _, err = pool.Exec(ctx, sql); err == nil {
			return nil
		}
		if !strings.Contains(err.Error(), "deadlock") {
			return err
		}
		time.Sleep(50 * time.Millisecond)
	}
	return err
}

func TestLive_Relay_EndToEnd(t *testing.T) {
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	redisURL := os.Getenv("REDIS_URL")
	if dsn == "" || redisURL == "" {
		t.Skip("PIIKMS_TEST_PG_URL and/or REDIS_URL not set; skipping relay e2e smoke")
	}
	ctx := context.Background()

	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("pg connect: %v", err)
	}
	t.Cleanup(pool.Close)
	sql, rerr := os.ReadFile("../../../../migrations/meta/030_meta_outbox.up.sql")
	if rerr != nil {
		t.Fatalf("read migration: %v", rerr)
	}
	if eerr := applyMigrationWithRetry(ctx, pool, string(sql)); eerr != nil {
		t.Fatalf("apply 030: %v", eerr)
	}

	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		t.Fatalf("redis url: %v", err)
	}
	rdb := redis.NewClient(opts)
	t.Cleanup(func() { _ = rdb.Close() })
	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Skipf("redis unreachable: %v", err)
	}

	// Unique streams per run so assertions are isolated.
	run := uuid.New().String()[:8]
	homeStream := "lw.meta.events.smoke." + run
	xrealTopic := "xreality.user.erased.smoke." + run
	t.Cleanup(func() {
		_ = rdb.Del(context.Background(), homeStream, xrealTopic).Err()
	})

	// Seed one cross-reality row whose xreality_topic targets our unique topic.
	// Payload is the DOMAIN shape (P2/113): user_id + erased_at, plus a "big"
	// field = 2^53+1 (a value float64 CANNOT represent exactly — proves the
	// relay preserves int64 precision via json.Number, not a lossy round-trip).
	evID := uuid.New()
	userID := uuid.New()
	if _, err := pool.Exec(ctx,
		`INSERT INTO meta_outbox (event_id, event_name, aggregate_id, payload, xreality_topic, recorded_at_nanos)
		 VALUES ($1,'user.erased',$2,
		         jsonb_build_object('user_id',$2::text,'erased_at','2026-05-31T00:00:00Z','big',9007199254740993::bigint),
		         $3,42)`,
		evID, userID, xrealTopic); err != nil {
		t.Fatalf("seed: %v", err)
	}

	policy := retry.DefaultPolicy()
	src, err := pgsource.New(pool, policy)
	if err != nil {
		t.Fatalf("pgsource: %v", err)
	}
	em, err := redisemit.New(rdb, homeStream, 0)
	if err != nil {
		t.Fatalf("emitter: %v", err)
	}
	loop, err := drain.New(drain.Config{Source: src, Emitter: em, Policy: policy, BatchSize: 100})
	if err != nil {
		t.Fatalf("loop: %v", err)
	}

	stats, err := loop.Run(ctx)
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if stats.Published < 1 || stats.XRealityOK < 1 {
		t.Fatalf("expected ≥1 published + ≥1 xreality, got %+v", stats)
	}

	// The row must be published in the DB.
	var published bool
	if err := pool.QueryRow(ctx, `SELECT published FROM meta_outbox WHERE event_id=$1`, evID).Scan(&published); err != nil {
		t.Fatalf("requery: %v", err)
	}
	if !published {
		t.Error("row not marked published after drain")
	}

	// Both streams must carry the envelope (same event_id); each verified per its
	// contract: home = generic (payload-as-json, no promotion); xreality = the
	// domain fields promoted to top-level (so 071 reads user_id directly).
	for _, stream := range []string{homeStream, xrealTopic} {
		msgs, err := rdb.XRange(ctx, stream, "-", "+").Result()
		if err != nil {
			t.Fatalf("XRANGE %s: %v", stream, err)
		}
		found := false
		for _, msg := range msgs {
			if msg.Values["event_id"] != evID.String() {
				continue
			}
			found = true
			if msg.Values["event_name"] != "user.erased" {
				t.Errorf("%s: event_name mismatch: %v", stream, msg.Values["event_name"])
			}
			payload, _ := msg.Values["payload"].(string)
			if !strings.Contains(payload, "9007199254740993") {
				t.Errorf("%s: payload lost int64 precision: %q", stream, payload)
			}
			if stream == xrealTopic {
				// event_type = the xreality topic → explicit consumer routing (071).
				if msg.Values["event_type"] != xrealTopic {
					t.Errorf("xreality: event_type must equal the topic for explicit routing, got %v", msg.Values["event_type"])
				}
				// Promotion: domain keys are top-level fields (071 reads these).
				if msg.Values["user_id"] != userID.String() {
					t.Errorf("xreality: user_id not promoted to a top-level field: %v", msg.Values["user_id"])
				}
				if msg.Values["erased_at"] != "2026-05-31T00:00:00Z" {
					t.Errorf("xreality: erased_at not promoted: %v", msg.Values["erased_at"])
				}
				// json.Number promotion preserves the 2^53+1 int exactly.
				if msg.Values["big"] != "9007199254740993" {
					t.Errorf("xreality: promoted int lost precision: %v", msg.Values["big"])
				}
			} else {
				// Home stream must NOT promote — domain keys stay inside payload.
				if _, promoted := msg.Values["user_id"]; promoted {
					t.Errorf("home stream must not promote payload keys; found top-level user_id")
				}
			}
		}
		if !found {
			t.Errorf("stream %s missing event %s", stream, evID)
		}
	}
}
