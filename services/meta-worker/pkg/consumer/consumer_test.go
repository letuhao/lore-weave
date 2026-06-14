package consumer

import (
	"context"
	"errors"
	"testing"

	"github.com/loreweave/foundation/services/meta-worker/pkg/dispatch"
)

type fakeSource struct {
	batches       [][]Message
	acked         []string
	ackBatchCalls int   // number of AckBatch invocations (proves batching)
	ackBatchSizes []int // ids-per-call (proves same-stream ids collapse to one call)
	readErr       error
	ackErr        error
}

func (f *fakeSource) Read(_ context.Context, _ int) ([]Message, error) {
	if f.readErr != nil {
		return nil, f.readErr
	}
	if len(f.batches) == 0 {
		return nil, nil
	}
	out := f.batches[0]
	f.batches = f.batches[1:]
	return out, nil
}

func (f *fakeSource) AckBatch(_ context.Context, _ string, ids []string) error {
	if f.ackErr != nil {
		return f.ackErr
	}
	f.ackBatchCalls++
	f.ackBatchSizes = append(f.ackBatchSizes, len(ids))
	f.acked = append(f.acked, ids...)
	return nil
}

func TestNew_ValidatesArgs(t *testing.T) {
	if _, err := New(nil, dispatch.New()); err == nil {
		t.Error("expected nil-source error")
	}
	if _, err := New(&fakeSource{}, nil); err == nil {
		t.Error("expected nil-dispatcher error")
	}
}

func TestProcessOne_DispatchesAndAcks(t *testing.T) {
	sink := &dispatch.SkeletonSink{}
	d := dispatch.NewWithSkeletons(sink)
	src := &fakeSource{batches: [][]Message{
		{
			{Stream: "xreality.canon.promoted", ID: "1-0", Fields: map[string]any{"event_type": "xreality.canon.promoted", "entry_id": "e1"}},
			{Stream: "xreality.user.erased", ID: "1-1", Fields: map[string]any{"event_type": "xreality.user.erased", "user_id": "u1"}},
		},
	}}
	c, _ := New(src, d)
	stats, err := c.ProcessOne(context.Background(), 10)
	if err != nil {
		t.Fatal(err)
	}
	if stats.Read != 2 {
		t.Errorf("Read=%d want 2", stats.Read)
	}
	if stats.Dispatched != 2 {
		t.Errorf("Dispatched=%d want 2", stats.Dispatched)
	}
	if stats.Acked != 2 {
		t.Errorf("Acked=%d want 2", stats.Acked)
	}
	if len(src.acked) != 2 {
		t.Errorf("expected 2 Ack calls, got %v", src.acked)
	}
	if len(sink.Records()) != 2 {
		t.Errorf("expected 2 sink records, got %d", len(sink.Records()))
	}
}

func TestProcessOne_BatchesAckPerStream(t *testing.T) {
	// S12 I7 fix: N messages on ONE stream must collapse to ONE AckBatch call with
	// all N ids — the per-message XACK round-trip was the single-consumer ceiling.
	sink := &dispatch.SkeletonSink{}
	d := dispatch.NewWithSkeletons(sink)
	src := &fakeSource{batches: [][]Message{
		{
			{Stream: "xreality.canon.promoted", ID: "1-0", Fields: map[string]any{"event_type": "xreality.canon.promoted"}},
			{Stream: "xreality.canon.promoted", ID: "1-1", Fields: map[string]any{"event_type": "xreality.canon.promoted"}},
			{Stream: "xreality.canon.promoted", ID: "1-2", Fields: map[string]any{"event_type": "xreality.canon.promoted"}},
		},
	}}
	c, _ := New(src, d)
	stats, err := c.ProcessOne(context.Background(), 10)
	if err != nil {
		t.Fatal(err)
	}
	if stats.Acked != 3 {
		t.Errorf("Acked=%d want 3", stats.Acked)
	}
	if src.ackBatchCalls != 1 {
		t.Errorf("AckBatch calls=%d want 1 (3 same-stream ids MUST batch into one XACK)", src.ackBatchCalls)
	}
	if len(src.ackBatchSizes) != 1 || src.ackBatchSizes[0] != 3 {
		t.Errorf("AckBatch sizes=%v want [3]", src.ackBatchSizes)
	}
}

func TestProcessOne_PartialDispatchAcksOnlySuccesses(t *testing.T) {
	// Mixed batch on ONE stream: a no-handler message in the middle must NOT be
	// acked, while its successful neighbors ARE — the batch carries only successes.
	d := dispatch.New()
	d.Register("xreality.ok.event", func(_ context.Context, _ map[string]any) error { return nil })
	src := &fakeSource{batches: [][]Message{
		{
			{Stream: "xreality.s", ID: "1-0", Fields: map[string]any{"event_type": "xreality.ok.event"}},
			{Stream: "xreality.s", ID: "1-1", Fields: map[string]any{"event_type": "xreality.no.handler"}},
			{Stream: "xreality.s", ID: "1-2", Fields: map[string]any{"event_type": "xreality.ok.event"}},
		},
	}}
	c, _ := New(src, d)
	stats, _ := c.ProcessOne(context.Background(), 10)
	if stats.Acked != 2 || stats.NoHandler != 1 {
		t.Errorf("Acked=%d NoHandler=%d want 2/1", stats.Acked, stats.NoHandler)
	}
	if len(src.acked) != 2 || src.acked[0] != "1-0" || src.acked[1] != "1-2" {
		t.Errorf("acked=%v want [1-0 1-2] (the no-handler id 1-1 MUST re-deliver)", src.acked)
	}
}

func TestProcessOne_NoHandlerSkipsAck(t *testing.T) {
	d := dispatch.New() // empty dispatcher
	src := &fakeSource{batches: [][]Message{
		{{Stream: "xreality.unknown.event", ID: "1-0", Fields: map[string]any{"event_type": "xreality.unknown.event"}}},
	}}
	c, _ := New(src, d)
	stats, err := c.ProcessOne(context.Background(), 10)
	if err != nil {
		t.Fatal(err)
	}
	if stats.NoHandler != 1 {
		t.Errorf("NoHandler=%d want 1", stats.NoHandler)
	}
	if stats.Acked != 0 {
		t.Errorf("Acked=%d MUST be 0 when no handler (re-delivery contract)", stats.Acked)
	}
}

func TestProcessOne_HandlerErrorSkipsAck(t *testing.T) {
	d := dispatch.New()
	d.Register("xreality.x.y", func(_ context.Context, _ map[string]any) error {
		return errors.New("handler boom")
	})
	src := &fakeSource{batches: [][]Message{
		{{Stream: "xreality.x.y", ID: "1-0", Fields: map[string]any{"event_type": "xreality.x.y"}}},
	}}
	c, _ := New(src, d)
	stats, err := c.ProcessOne(context.Background(), 10)
	if err != nil {
		t.Fatal(err)
	}
	if stats.HandlerErr != 1 {
		t.Errorf("HandlerErr=%d want 1", stats.HandlerErr)
	}
	if stats.Acked != 0 {
		t.Errorf("Acked=%d MUST be 0 on handler error", stats.Acked)
	}
}

func TestProcessOne_SourceReadErrorPropagates(t *testing.T) {
	src := &fakeSource{readErr: errors.New("redis down")}
	c, _ := New(src, dispatch.New())
	if _, err := c.ProcessOne(context.Background(), 10); err == nil {
		t.Fatal("expected propagated read error")
	}
}

func TestMessage_EventTypePrefersFieldOverStream(t *testing.T) {
	m := Message{Stream: "xreality.canon.promoted", Fields: map[string]any{"event_type": "xreality.canon.promoted"}}
	if m.EventType() != "xreality.canon.promoted" {
		t.Errorf("EventType=%s", m.EventType())
	}
	// Falls back to stream when field missing.
	m2 := Message{Stream: "xreality.user.erased", Fields: map[string]any{}}
	if m2.EventType() != "xreality.user.erased" {
		t.Errorf("EventType fallback=%s", m2.EventType())
	}
}
