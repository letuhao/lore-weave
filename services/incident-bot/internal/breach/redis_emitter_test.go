package breach

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"

	"github.com/loreweave/foundation/contracts/incidents"
)

// capturingCmdable embeds redis.Cmdable and overrides ONLY XAdd to capture the args
// (the emitter calls no other method). Any other call would panic on the nil embedded
// interface — that is the point: it proves the emitter touches only XAdd.
type capturingCmdable struct {
	redis.Cmdable
	lastArgs *redis.XAddArgs
	calls    int
	err      error
}

func (c *capturingCmdable) XAdd(ctx context.Context, a *redis.XAddArgs) *redis.StringCmd {
	c.calls++
	c.lastArgs = a
	cmd := redis.NewStringCmd(ctx)
	if c.err != nil {
		cmd.SetErr(c.err)
	} else {
		cmd.SetVal("0-1")
	}
	return cmd
}

func TestBreachXAddArgs_FieldShaping(t *testing.T) {
	now := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)
	ev := incidents.NewGDPRBreachOpenedV1("inc-1", now, now.Add(72*time.Hour), "email", 3)
	args, err := breachXAddArgs("lw.incidents.breach", ev.Type, ev.IncidentID, ev, "")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if args.Stream != "lw.incidents.breach" {
		t.Errorf("stream: %v", args.Stream)
	}
	vals := args.Values.(map[string]any)
	if vals["event_type"] != incidents.TypeGDPRBreachOpenedV1 {
		t.Errorf("event_type: %v", vals["event_type"])
	}
	if vals["incident_id"] != "inc-1" {
		t.Errorf("incident_id: %v", vals["incident_id"])
	}
	var back incidents.GDPRBreachOpenedV1
	if e := json.Unmarshal([]byte(vals["payload"].(string)), &back); e != nil {
		t.Fatalf("payload unmarshal: %v", e)
	}
	if back.IncidentID != "inc-1" || back.AffectedCount != 3 {
		t.Errorf("payload round-trip mismatch: %+v", back)
	}
	if args.MinID != "" || args.Approx {
		t.Errorf("no-trim args should set neither MinID nor Approx, got MinID=%q approx=%v", args.MinID, args.Approx)
	}
}

func TestBreachXAddArgs_MinIDTrim(t *testing.T) {
	args, err := breachXAddArgs("s", "t", "i", map[string]string{}, "1700000000000-0")
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if args.MinID != "1700000000000-0" || !args.Approx {
		t.Errorf("minid/approx: %q %v", args.MinID, args.Approx)
	}
}

func TestRedisEmitter_TrimHorizonSetsMinID(t *testing.T) {
	fake := &capturingCmdable{}
	fixed := time.Date(2026, 6, 1, 12, 0, 0, 0, time.UTC)
	em, err := NewRedisEmitter(fake, "", 7*24*time.Hour, func() time.Time { return fixed })
	if err != nil {
		t.Fatalf("ctor: %v", err)
	}
	ev := incidents.NewGDPRBreachOpenedV1("inc-1", fixed, fixed.Add(72*time.Hour), "email", 1)
	if err := em.EmitBreachOpened(context.Background(), ev); err != nil {
		t.Fatalf("emit: %v", err)
	}
	wantMinID := fmt.Sprintf("%d-0", fixed.Add(-7*24*time.Hour).UnixMilli())
	if fake.lastArgs.MinID != wantMinID || !fake.lastArgs.Approx {
		t.Errorf("trim MinID: want %q approx, got %q approx=%v", wantMinID, fake.lastArgs.MinID, fake.lastArgs.Approx)
	}
}

func TestRedisEmitter_ValidateBeforeEmit(t *testing.T) {
	fake := &capturingCmdable{}
	em, err := NewRedisEmitter(fake, "", 0, nil)
	if err != nil {
		t.Fatalf("ctor: %v", err)
	}
	// Invalid event (zero value: missing type/incident_id) → error, and NO XAdd.
	if err := em.EmitBreachOpened(context.Background(), incidents.GDPRBreachOpenedV1{}); err == nil {
		t.Errorf("expected validation error for empty event")
	}
	if fake.calls != 0 {
		t.Errorf("XAdd must NOT be called on an invalid event, got %d calls", fake.calls)
	}
	// Valid → XAdd once, to the default stream.
	now := time.Now()
	ev := incidents.NewGDPRBreachOpenedV1("inc-2", now, now.Add(72*time.Hour), "email", 1)
	if err := em.EmitBreachOpened(context.Background(), ev); err != nil {
		t.Fatalf("emit: %v", err)
	}
	if fake.calls != 1 {
		t.Fatalf("XAdd should be called once, got %d", fake.calls)
	}
	if fake.lastArgs.Stream != DefaultBreachStream {
		t.Errorf("default stream: got %q want %q", fake.lastArgs.Stream, DefaultBreachStream)
	}
	if !strings.Contains(fake.lastArgs.Values.(map[string]any)["payload"].(string), "inc-2") {
		t.Errorf("payload missing incident id")
	}
}

func TestNewRedisEmitter_NilClient(t *testing.T) {
	if _, err := NewRedisEmitter(nil, "", 0, nil); err == nil {
		t.Errorf("expected nil-client error")
	}
}
