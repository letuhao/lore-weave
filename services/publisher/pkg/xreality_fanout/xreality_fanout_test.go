package xreality_fanout

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/publisher/pkg/types"
)

type fakeStreamEmitter struct {
	calls []struct {
		stream string
		fields map[string]any
	}
	failOnStream string
}

func (f *fakeStreamEmitter) XAdd(_ context.Context, stream string, fields map[string]any) error {
	if f.failOnStream != "" && stream == f.failOnStream {
		return errors.New("simulated redis fail")
	}
	f.calls = append(f.calls, struct {
		stream string
		fields map[string]any
	}{stream, fields})
	return nil
}

func TestNew_RequiresEmitter(t *testing.T) {
	if _, err := New(nil); err == nil {
		t.Fatal("expected nil-emitter error")
	}
}

func TestTopicFor_ValidatesConvention(t *testing.T) {
	good := []string{
		"xreality.canon.promoted",
		"xreality.user.erased",
		"xreality.reality.stats_updated",
	}
	for _, et := range good {
		topic, err := TopicFor(et)
		if err != nil {
			t.Errorf("TopicFor(%q) unexpected err: %v", et, err)
		}
		if topic != et {
			t.Errorf("TopicFor(%q) = %q; want passthrough", et, topic)
		}
	}
	bad := []string{
		"",
		"npc.said",                       // missing xreality prefix
		"xreality.canon",                 // missing verb
		"xreality.canon.promoted.extra",  // too many segments
		"xreality..promoted",             // empty entity
	}
	for _, et := range bad {
		if _, err := TopicFor(et); err == nil {
			t.Errorf("TopicFor(%q) should error", et)
		}
	}
}

func sampleXRealityRow() types.OutboxRow {
	return types.OutboxRow{
		EventID:          uuid.New(),
		RealityID:        uuid.New(),
		EventType:        "xreality.canon.promoted",
		EventVersion:     1,
		AggregateType:    "canon",
		AggregateID:      "entry-42",
		AggregateVersion: 7,
		Payload:          map[string]any{"entry_id": "entry-42"},
		Metadata:         map[string]any{"cross_reality": true, "actor": "system"},
	}
}

func TestFanout_HappyPath(t *testing.T) {
	em := &fakeStreamEmitter{}
	f, _ := New(em)
	row := sampleXRealityRow()
	if err := f.Fanout(context.Background(), row); err != nil {
		t.Fatal(err)
	}
	if len(em.calls) != 1 {
		t.Fatalf("expected 1 XAdd, got %d", len(em.calls))
	}
	if em.calls[0].stream != "xreality.canon.promoted" {
		t.Errorf("stream=%q want xreality.canon.promoted", em.calls[0].stream)
	}
	got := em.calls[0].fields
	if got["event_id"] != row.EventID.String() {
		t.Errorf("event_id missing")
	}
	if got["source_reality_id"] != row.RealityID.String() {
		t.Errorf("source_reality_id missing")
	}
}

func TestFanout_RejectsNonCrossReality(t *testing.T) {
	em := &fakeStreamEmitter{}
	f, _ := New(em)
	row := sampleXRealityRow()
	row.Metadata = map[string]any{"cross_reality": false}
	err := f.Fanout(context.Background(), row)
	if err == nil {
		t.Fatal("expected ErrNotXReality")
	}
	if !errors.Is(err, ErrNotXReality) {
		t.Errorf("expected ErrNotXReality, got %v", err)
	}
	if len(em.calls) != 0 {
		t.Error("emitter should not have been called")
	}
}

func TestFanout_RejectsBadEventType(t *testing.T) {
	em := &fakeStreamEmitter{}
	f, _ := New(em)
	row := sampleXRealityRow()
	row.EventType = "npc.said"
	err := f.Fanout(context.Background(), row)
	if err == nil {
		t.Fatal("expected ErrInvalidEventType")
	}
	if !errors.Is(err, ErrInvalidEventType) {
		t.Errorf("expected ErrInvalidEventType, got %v", err)
	}
}

func TestFanout_PropagatesEmitterError(t *testing.T) {
	em := &fakeStreamEmitter{failOnStream: "xreality.canon.promoted"}
	f, _ := New(em)
	err := f.Fanout(context.Background(), sampleXRealityRow())
	if err == nil {
		t.Fatal("expected propagated error")
	}
	if !strings.Contains(err.Error(), "simulated redis fail") {
		t.Errorf("expected wrapped fail, got %v", err)
	}
}
