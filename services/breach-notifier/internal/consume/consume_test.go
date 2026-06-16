package consume

import (
	"context"
	"errors"
	"testing"
	"time"
)

type fakeSource struct {
	batch   []Message
	reclaim []Message
	read    int
	acked   []string
}

func (f *fakeSource) EnsureGroup(context.Context) error { return nil }
func (f *fakeSource) Read(_ context.Context, _ int) ([]Message, error) {
	f.read++
	if f.read > 1 {
		return nil, nil // one batch, then empty
	}
	return f.batch, nil
}
func (f *fakeSource) Reclaim(_ context.Context, _ time.Duration, _ int) ([]Message, error) {
	return f.reclaim, nil
}
func (f *fakeSource) Ack(_ context.Context, m Message) error {
	f.acked = append(f.acked, m.ID)
	return nil
}

func TestProcessor_AcksNonFailureOnly(t *testing.T) {
	src := &fakeSource{batch: []Message{
		{ID: "1", Fields: map[string]any{"event_type": "x"}},
		{ID: "2", Fields: map[string]any{"event_type": "y"}},
		{ID: "3", Fields: map[string]any{"event_type": "z"}},
	}}
	h := func(_ context.Context, m Message) (Outcome, error) {
		switch m.ID {
		case "1":
			return OutcomeDelivered, nil
		case "2":
			return OutcomeFailed, errors.New("boom")
		default:
			return OutcomeSkippedDuplicate, nil
		}
	}
	p, _ := NewProcessor(src, h)
	st, err := p.ProcessOne(context.Background(), 10)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if st.Read != 3 || st.Delivered != 1 || st.Failed != 1 || st.SkippedDuplicate != 1 {
		t.Errorf("stats: %+v", st)
	}
	if len(src.acked) != 2 {
		t.Fatalf("want 2 acks (delivered+skipped), got %v", src.acked)
	}
	for _, id := range src.acked {
		if id == "2" {
			t.Errorf("failed message 2 must NOT be acked (Redis must re-deliver)")
		}
	}
}

func TestProcessor_ReclaimOnce(t *testing.T) {
	// H2: a stale pending entry (crashed-before-ack) is reclaimed + handled + acked.
	src := &fakeSource{reclaim: []Message{{ID: "stuck", Fields: map[string]any{"event_type": "x"}}}}
	h := func(_ context.Context, _ Message) (Outcome, error) { return OutcomeDelivered, nil }
	p, _ := NewProcessor(src, h)
	st, err := p.ReclaimOnce(context.Background(), time.Minute, 10)
	if err != nil {
		t.Fatalf("reclaim: %v", err)
	}
	if st.Read != 1 || st.Delivered != 1 || len(src.acked) != 1 || src.acked[0] != "stuck" {
		t.Errorf("reclaimed message should be handled + acked: stats=%+v acked=%v", st, src.acked)
	}
}

func TestProcessor_NilGuards(t *testing.T) {
	noop := func(context.Context, Message) (Outcome, error) { return OutcomeIgnored, nil }
	if _, err := NewProcessor(nil, noop); err == nil {
		t.Errorf("nil source should error")
	}
	if _, err := NewProcessor(&fakeSource{}, nil); err == nil {
		t.Errorf("nil handler should error")
	}
}

func TestMessage_EventType(t *testing.T) {
	if (Message{Fields: map[string]any{"event_type": "e"}}).EventType() != "e" {
		t.Errorf("event_type")
	}
	if (Message{Fields: map[string]any{}}).EventType() != "" {
		t.Errorf("missing event_type should be empty")
	}
}
