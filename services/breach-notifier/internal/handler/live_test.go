package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/contracts/incidents"
	"github.com/loreweave/foundation/services/breach-notifier/internal/consume"
	"github.com/loreweave/foundation/services/breach-notifier/internal/deliver"
	"github.com/loreweave/foundation/services/breach-notifier/internal/migrate"
	"github.com/loreweave/foundation/services/breach-notifier/internal/store"
)

// TestLive_ConsumeDeliverRecordRoundtrip proves the full rail on real infra: XADD a
// dpo_notice_required (as incident-bot's RedisEmitter would) → consume → LogNotifier
// delivers → breach_dpo_delivery row recorded delivered; a re-emit is skipped
// (idempotent). Gated on INCIDENT_TEST_REDIS_URL + PIIKMS_TEST_PG_URL (dev infra).
func TestLive_ConsumeDeliverRecordRoundtrip(t *testing.T) {
	redisURL := os.Getenv("INCIDENT_TEST_REDIS_URL")
	pgURL := os.Getenv("PIIKMS_TEST_PG_URL")
	if redisURL == "" || pgURL == "" {
		t.Skip("INCIDENT_TEST_REDIS_URL + PIIKMS_TEST_PG_URL required; skipping breach-notifier roundtrip")
	}
	ctx := context.Background()

	pool, err := pgxpool.New(ctx, pgURL)
	if err != nil {
		t.Fatalf("pg: %v", err)
	}
	t.Cleanup(pool.Close)
	if _, err := pool.Exec(ctx, migrate.UpSQL); err != nil {
		t.Fatalf("migrate: %v", err)
	}

	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		t.Fatalf("redis url: %v", err)
	}
	rdb := redis.NewClient(opts)
	t.Cleanup(func() { _ = rdb.Close() })
	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Fatalf("redis ping: %v", err)
	}

	stream := fmt.Sprintf("lw.incidents.breach.test.%d", time.Now().UnixNano())
	t.Cleanup(func() { _ = rdb.Del(context.Background(), stream).Err() })
	id := "inc-rt-" + time.Now().UTC().Format("150405.000000")
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM breach_dpo_delivery WHERE incident_id=$1`, id)
	})

	st := store.NewPgDeliveryStore(pool)
	h, _ := New(deliver.NewLogNotifier(slog.Default()), st, time.Now, slog.Default())
	src, err := consume.NewRedisSource(consume.Config{RDB: rdb, Stream: stream, Group: "breach-notifier-test", Consumer: "t1", Block: 2 * time.Second})
	if err != nil {
		t.Fatalf("source: %v", err)
	}
	if err := src.EnsureGroup(ctx); err != nil {
		t.Fatalf("ensure group: %v", err)
	}
	proc, _ := consume.NewProcessor(src, h.Handle)

	emit := func() {
		ev := incidents.NewGDPRDPONoticeRequiredV1(id, "GDPR Art.33 breach "+id, "body", time.Now().Add(72*time.Hour))
		b, _ := json.Marshal(ev)
		if err := rdb.XAdd(ctx, &redis.XAddArgs{Stream: stream, Values: map[string]any{
			"event_type": ev.Type, "incident_id": id, "payload": string(b),
		}}).Err(); err != nil {
			t.Fatalf("xadd: %v", err)
		}
	}

	emit()
	stats, err := proc.ProcessOne(ctx, 10)
	if err != nil {
		t.Fatalf("process: %v", err)
	}
	if stats.Delivered != 1 {
		t.Fatalf("want 1 delivered, got %+v", stats)
	}
	if ok, _ := st.AlreadyDelivered(ctx, id); !ok {
		t.Errorf("delivered notice should be recorded confirmed")
	}

	// Idempotency: re-emit the same incident → skipped, not re-delivered.
	emit()
	stats2, err := proc.ProcessOne(ctx, 10)
	if err != nil {
		t.Fatalf("process 2: %v", err)
	}
	if stats2.SkippedDuplicate != 1 {
		t.Errorf("re-delivery should be skipped as duplicate, got %+v", stats2)
	}
}
