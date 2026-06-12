// publisher_heartbeat_test.go — L2.D.5 (RAID cycle 10).
//
// Asserts the publisher writes a heartbeat row on every 10s tick. In the
// in-memory variant we drive Tick() directly (instead of waiting wall-clock
// 30s) and assert the writer was called the expected number of times.
//
//go:build integration
// +build integration

package integration

import (
	"context"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/lifecycle"
	"github.com/loreweave/foundation/services/publisher/pkg/heartbeat"
)

type recordingWriter struct{ count int }

func (w *recordingWriter) WriteHeartbeat(_ context.Context, _, _ string, _ time.Time) error {
	w.count++
	return nil
}

type fakeClock struct{ t time.Time }

func (c *fakeClock) Now() time.Time { return c.t }

func TestPublisher_HeartbeatLoop_WritesEveryTick(t *testing.T) {
	w := &recordingWriter{}
	c := &fakeClock{t: time.Now()}
	loop, err := heartbeat.New("publisher-1", "shard-h1", w, c)
	if err != nil {
		t.Fatalf("heartbeat.New: %v", err)
	}
	// Simulate 3 ticks over 30s (10s each).
	for i := 0; i < 3; i++ {
		if err := loop.Tick(context.Background()); err != nil {
			t.Fatalf("tick %d: %v", i, err)
		}
		c.t = c.t.Add(10 * time.Second)
	}
	if w.count != 3 {
		t.Errorf("expected 3 heartbeat writes, got %d", w.count)
	}
	if loop.Mode() != lifecycle.ModeFull {
		t.Errorf("expected ModeFull after happy-path ticks, got %v", loop.Mode())
	}
}
