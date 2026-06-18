package breach

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/contracts/incidents"
)

func openedEv(id string, deadlineOffset time.Duration) replayEvent {
	now := time.Now().UTC()
	o := incidents.NewGDPRBreachOpenedV1(id, now, now.Add(deadlineOffset), "email", 1)
	return replayEvent{eventType: o.Type, incidentID: id, opened: &o}
}

func TestReconstructOpen_OpenedTracked(t *testing.T) {
	recs := reconstructOpen([]replayEvent{openedEv("a", 72*time.Hour), openedEv("b", 72*time.Hour)})
	if len(recs) != 2 {
		t.Fatalf("want 2 open, got %d", len(recs))
	}
	if recs[0].IncidentID != "a" || recs[1].IncidentID != "b" {
		t.Errorf("first-opened order not preserved: %+v", recs)
	}
}

func TestReconstructOpen_MissedSkipped(t *testing.T) {
	evs := []replayEvent{
		openedEv("a", 72*time.Hour),
		openedEv("b", 72*time.Hour),
		{eventType: incidents.TypeGDPRBreachDeadlineV1, incidentID: "a", missed: true},
	}
	recs := reconstructOpen(evs)
	if len(recs) != 1 || recs[0].IncidentID != "b" {
		t.Fatalf("missed 'a' (terminal) must be skipped, got %+v", recs)
	}
}

func TestReconstructOpen_Empty(t *testing.T) {
	if recs := reconstructOpen(nil); len(recs) != 0 {
		t.Errorf("want 0, got %d", len(recs))
	}
}

func TestReconstructOpen_DupOpenedDedup(t *testing.T) {
	recs := reconstructOpen([]replayEvent{openedEv("a", 72*time.Hour), openedEv("a", 48*time.Hour)})
	if len(recs) != 1 {
		t.Fatalf("duplicate opened should dedup to 1, got %d", len(recs))
	}
}

func TestReconstructOpen_ApproachingNotTerminal(t *testing.T) {
	// An 'approaching' deadline event must NOT remove the breach — only 'missed' is terminal.
	evs := []replayEvent{
		openedEv("a", 72*time.Hour),
		{eventType: incidents.TypeGDPRBreachDeadlineV1, incidentID: "a", missed: false},
	}
	if recs := reconstructOpen(evs); len(recs) != 1 {
		t.Errorf("approaching must keep the breach open: %+v", recs)
	}
}

func TestParseReplayMessage(t *testing.T) {
	now := time.Now().UTC()
	o := incidents.NewGDPRBreachOpenedV1("inc-9", now, now.Add(72*time.Hour), "email", 2)
	pb, _ := json.Marshal(o)
	ev, ok := parseReplayMessage(map[string]any{"event_type": o.Type, "incident_id": "inc-9", "payload": string(pb)})
	if !ok || ev.opened == nil || ev.opened.IncidentID != "inc-9" {
		t.Fatalf("opened parse: %+v ok=%v", ev, ok)
	}
	// Missing event_type → not ok (skipped).
	if _, ok := parseReplayMessage(map[string]any{"payload": "{}"}); ok {
		t.Errorf("missing event_type should be !ok")
	}
	// Deadline 'missed' → ok + missed flag.
	d := incidents.NewGDPRBreachDeadlineV1("inc-9", incidents.BreachDeadlineMissed, -time.Hour)
	db, _ := json.Marshal(d)
	dev, ok := parseReplayMessage(map[string]any{"event_type": d.Type, "incident_id": "inc-9", "payload": string(db)})
	if !ok || !dev.missed {
		t.Errorf("missed deadline parse: %+v ok=%v", dev, ok)
	}
}

func TestReconstructOpen_OrphanMissedNoRecord(t *testing.T) {
	// A missed-deadline event with NO preceding opened must not produce a phantom record.
	recs := reconstructOpen([]replayEvent{{eventType: incidents.TypeGDPRBreachDeadlineV1, incidentID: "ghost", missed: true}})
	if len(recs) != 0 {
		t.Fatalf("orphan missed should yield 0 records, got %d", len(recs))
	}
}

func TestReconstructOpen_ReopenAfterMissed(t *testing.T) {
	// Ordered log, same incident_id re-declared: opened, missed, opened → the LATEST
	// event is an open, so the breach is open again (#3 last-event-wins).
	evs := []replayEvent{
		openedEv("a", 72*time.Hour),
		{eventType: incidents.TypeGDPRBreachDeadlineV1, incidentID: "a", missed: true},
		openedEv("a", 48*time.Hour),
	}
	recs := reconstructOpen(evs)
	if len(recs) != 1 || recs[0].IncidentID != "a" {
		t.Fatalf("reopen-after-missed should be open, got %+v", recs)
	}
}

func TestParseReplayMessage_ForeignAndMissing(t *testing.T) {
	// An unknown event_type parses (default branch, total) but is inert in reconstruct.
	ev, ok := parseReplayMessage(map[string]any{"event_type": "some.other.v1", "incident_id": "x"})
	if !ok {
		t.Fatalf("unknown event_type should parse (total), got !ok")
	}
	if ev.opened != nil || ev.missed {
		t.Errorf("foreign entry should be inert: %+v", ev)
	}
	if recs := reconstructOpen([]replayEvent{ev}); len(recs) != 0 {
		t.Errorf("foreign entry must not produce a record")
	}
	// An opened event with no payload → !ok (skipped, not fatal).
	if _, ok := parseReplayMessage(map[string]any{"event_type": incidents.TypeGDPRBreachOpenedV1}); ok {
		t.Errorf("opened with no payload should be !ok")
	}
}

// captureEmitter records the deadline events emitted (for the restart-reemit test).
type captureEmitter struct {
	deadlines []incidents.GDPRBreachDeadlineV1
}

func (c *captureEmitter) EmitBreachOpened(context.Context, incidents.GDPRBreachOpenedV1) error {
	return nil
}
func (c *captureEmitter) EmitDPONoticeRequired(context.Context, incidents.GDPRDPONoticeRequiredV1) error {
	return nil
}
func (c *captureEmitter) EmitBreachDeadline(_ context.Context, ev incidents.GDPRBreachDeadlineV1) error {
	c.deadlines = append(c.deadlines, ev)
	return nil
}

func TestReplayedBreach_ReemitsApproachingAfterRestart(t *testing.T) {
	// #5 (at-least-once, INTENDED): a breach reconstructed from the stream + Tracked
	// into a fresh Monitor re-emits 'approaching' on the first tick if inside the
	// window — replay carries no emitted-flag memory. Pins this as designed behavior so
	// a future reader doesn't "fix" it as a bug.
	recs := reconstructOpen([]replayEvent{openedEv("a", 6*time.Hour)}) // 6h out ≤ 12h ApproachingThreshold
	if len(recs) != 1 {
		t.Fatalf("setup: want 1 reconstructed record, got %d", len(recs))
	}
	cap := &captureEmitter{}
	mon := NewMonitor(cap, time.Now, time.Minute)
	mon.Track(recs[0])
	mon.tick(context.Background())
	if len(cap.deadlines) != 1 || cap.deadlines[0].State != incidents.BreachDeadlineApproaching {
		t.Fatalf("expected one 'approaching' re-emit after restart, got %+v", cap.deadlines)
	}
}

// TestLive_EmitReplayRoundtrip proves the durability claim on a REAL Redis stream:
// emit opened(A) + opened(B) + missed-deadline(B), then ReplayOpenBreaches must
// return only A (B is terminal). Gated on INCIDENT_TEST_REDIS_URL (dev infra-redis-1).
func TestLive_EmitReplayRoundtrip(t *testing.T) {
	url := os.Getenv("INCIDENT_TEST_REDIS_URL")
	if url == "" {
		t.Skip("INCIDENT_TEST_REDIS_URL not set; skipping breach Redis roundtrip")
	}
	opts, err := redis.ParseURL(url)
	if err != nil {
		t.Fatalf("parse url: %v", err)
	}
	rdb := redis.NewClient(opts)
	t.Cleanup(func() { _ = rdb.Close() })
	ctx := context.Background()
	if err := rdb.Ping(ctx).Err(); err != nil {
		t.Fatalf("ping: %v", err)
	}

	// Unique stream per run for isolation; deleted on cleanup.
	stream := fmt.Sprintf("lw.incidents.breach.test.%d", time.Now().UnixNano())
	t.Cleanup(func() { _ = rdb.Del(context.Background(), stream).Err() })

	em, err := NewRedisEmitter(rdb, stream, 0, nil) // trim 0: keep all events for this small roundtrip
	if err != nil {
		t.Fatalf("emitter: %v", err)
	}
	now := time.Now().UTC()
	evA := incidents.NewGDPRBreachOpenedV1("inc-A", now, now.Add(72*time.Hour), "email", 1)
	evB := incidents.NewGDPRBreachOpenedV1("inc-B", now.Add(-80*time.Hour), now.Add(-8*time.Hour), "email", 1)
	if err := em.EmitBreachOpened(ctx, evA); err != nil {
		t.Fatalf("emit A: %v", err)
	}
	if err := em.EmitBreachOpened(ctx, evB); err != nil {
		t.Fatalf("emit B: %v", err)
	}
	if err := em.EmitBreachDeadline(ctx, incidents.NewGDPRBreachDeadlineV1("inc-B", incidents.BreachDeadlineMissed, -8*time.Hour)); err != nil {
		t.Fatalf("emit B missed-deadline: %v", err)
	}

	recs, err := ReplayOpenBreaches(ctx, rdb, stream)
	if err != nil {
		t.Fatalf("replay: %v", err)
	}
	if len(recs) != 1 || recs[0].IncidentID != "inc-A" {
		t.Fatalf("expected only inc-A open after replay, got %+v", recs)
	}
	if !recs[0].Deadline.Equal(evA.Deadline) {
		t.Errorf("deadline round-trip: want %s, got %s", evA.Deadline, recs[0].Deadline)
	}
}
