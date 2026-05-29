// xreality_propagation_test.go — L2.L.6 (RAID cycle 10).
//
// End-to-end propagation test:
//  1. Build a xreality.canon.promoted outbox row in "reality A".
//  2. Publisher (in-memory) drains it → main XADD + xreality_fanout XADD.
//  3. meta-worker consumer (in-memory) reads from xreality topic →
//     dispatches to skeleton handler.
//  4. Assert the skeleton sink captured the event with correct
//     source_reality_id.
//
// This is the publisher → xreality stream → meta-worker dispatcher
// end-to-end wiring contract. Real projection writes to "reality B"
// are deferred to cycle 12+ (canon_projection table doesn't exist yet).
//
//go:build integration
// +build integration

package integration

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/lifecycle"
	"github.com/loreweave/foundation/services/meta-worker/pkg/consumer"
	"github.com/loreweave/foundation/services/meta-worker/pkg/dispatch"
	"github.com/loreweave/foundation/services/publisher/pkg/leader_election"
	"github.com/loreweave/foundation/services/publisher/pkg/poll_loop"
	"github.com/loreweave/foundation/services/publisher/pkg/retry"
	"github.com/loreweave/foundation/services/publisher/pkg/types"
	"github.com/loreweave/foundation/services/publisher/pkg/xreality_fanout"
)

// ── In-memory Redis Streams substitute ─────────────────────────────────

type inMemRedis struct {
	mu      sync.Mutex
	streams map[string][]consumer.Message
	nextID  int
}

func newInMemRedis() *inMemRedis {
	return &inMemRedis{streams: map[string][]consumer.Message{}}
}

// XAdd impl — satisfies xreality_fanout.StreamEmitter.
func (r *inMemRedis) XAdd(_ context.Context, stream string, fields map[string]any) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.nextID++
	id := uuid.New().String()
	msg := consumer.Message{Stream: stream, ID: id, Fields: copyFields(fields)}
	r.streams[stream] = append(r.streams[stream], msg)
	return nil
}

// Read drains every pending message across xreality.* streams.
// Satisfies consumer.MessageSource.
func (r *inMemRedis) Read(_ context.Context, _ int) ([]consumer.Message, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	var out []consumer.Message
	for stream, msgs := range r.streams {
		out = append(out, msgs...)
		r.streams[stream] = nil
	}
	return out, nil
}

// Ack — no-op (no PEL in this test).
func (r *inMemRedis) Ack(_ context.Context, _ consumer.Message) error { return nil }

func copyFields(in map[string]any) map[string]any {
	out := make(map[string]any, len(in))
	for k, v := range in {
		out[k] = v
	}
	return out
}

// ── Stub publisher dependencies ────────────────────────────────────────

type stubFetcher struct {
	rows []types.OutboxRow
	done bool
}

func (f *stubFetcher) FetchPending(_ context.Context, _ string, _ int) ([]types.OutboxRow, error) {
	if f.done {
		return nil, nil
	}
	f.done = true
	return f.rows, nil
}

// stubEmitter is the per-reality XADD sink. We don't care what it stores
// for THIS test — the assertion is on the xreality fanout side.
type stubEmitter struct{}

func (stubEmitter) Emit(_ context.Context, _ types.OutboxRow) error { return nil }

type stubMode struct{}

func (stubMode) Mode() lifecycle.ServiceMode { return lifecycle.ModeFull }

// ── Test ───────────────────────────────────────────────────────────────

func TestXRealityPropagation_PublisherToMetaWorker(t *testing.T) {
	// 1. Build a xreality outbox row.
	realityA := uuid.New()
	eventID := uuid.New()
	row := types.OutboxRow{
		EventID:          eventID,
		RealityID:        realityA,
		Attempts:         0,
		EventType:        "xreality.canon.promoted",
		EventVersion:     1,
		AggregateType:    "reality",
		AggregateID:      realityA.String(),
		AggregateVersion: 7,
		Payload: map[string]any{
			"entry_id":   "canon-entry-42",
			"entry_type": "world.gazetteer",
		},
		Metadata: map[string]any{"cross_reality": true},
	}

	// 2. Wire the in-memory Redis + publisher xreality fanout.
	redis := newInMemRedis()
	fanout, err := xreality_fanout.New(redis)
	if err != nil {
		t.Fatalf("xreality_fanout.New: %v", err)
	}

	// 3. Build the poll loop.
	loop, err := poll_loop.New(poll_loop.Config{
		Leader:    leader_election.NewNoOp(),
		Fetcher:   &stubFetcher{rows: []types.OutboxRow{row}},
		Emitter:   stubEmitter{},
		Fanout:    fanout,
		StateW:    &xrealityStateW{},
		Mode:      stubMode{},
		Policy:    retry.DefaultPolicy(),
		BatchSize: 10,
		Realities: []string{realityA.String()},
	})
	if err != nil {
		t.Fatalf("poll_loop.New: %v", err)
	}

	// 4. Drain — fanout pushes onto in-mem Redis.
	stats, err := loop.Run(context.Background())
	if err != nil {
		t.Fatalf("loop.Run: %v", err)
	}
	if stats.Published != 1 {
		t.Fatalf("Published=%d want 1", stats.Published)
	}
	if stats.FanoutOK != 1 {
		t.Fatalf("FanoutOK=%d want 1 — xreality fanout did not fire", stats.FanoutOK)
	}

	// 5. Build the meta-worker consumer over the SAME in-mem Redis.
	sink := &dispatch.SkeletonSink{}
	d := dispatch.NewWithSkeletons(sink)
	if err := d.ValidateAllowlist(); err != nil {
		t.Fatalf("dispatcher allowlist: %v", err)
	}
	c, err := consumer.New(redis, d)
	if err != nil {
		t.Fatalf("consumer.New: %v", err)
	}

	// 6. ProcessOne — meta-worker consumes & dispatches.
	cstats, err := c.ProcessOne(context.Background(), 10)
	if err != nil {
		t.Fatalf("consumer.ProcessOne: %v", err)
	}
	if cstats.Dispatched != 1 {
		t.Fatalf("Dispatched=%d want 1", cstats.Dispatched)
	}

	// 7. Assert the skeleton sink captured the event with
	// correct source_reality_id propagation.
	records := sink.Records()
	if len(records) != 1 {
		t.Fatalf("sink records=%d want 1", len(records))
	}
	got := records[0]
	if got.EventType != "xreality.canon.promoted" {
		t.Errorf("event_type=%s want xreality.canon.promoted", got.EventType)
	}
	if got.Fields["source_reality_id"] != realityA.String() {
		t.Errorf("source_reality_id=%v want %s", got.Fields["source_reality_id"], realityA.String())
	}
	if got.Fields["event_id"] != eventID.String() {
		t.Errorf("event_id=%v want %s", got.Fields["event_id"], eventID.String())
	}
}

// xrealityStateW satisfies poll_loop.StateWriter.
type xrealityStateW struct{}

func (xrealityStateW) MarkPublished(_ context.Context, _ string) error { return nil }
func (xrealityStateW) MarkRetry(_ context.Context, _ string, _ int, _ string, _ time.Time) error {
	return nil
}
func (xrealityStateW) MarkDeadLetter(_ context.Context, _ string, _ int, _ string) error {
	return nil
}
