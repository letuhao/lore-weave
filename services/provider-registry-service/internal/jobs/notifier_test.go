package jobs

import (
	"context"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestTerminalEvent_RoutingKeyShape(t *testing.T) {
	ev := TerminalEvent{
		JobID:       uuid.MustParse("019dca03-0317-703a-b6e2-04da628890d8"),
		OwnerUserID: uuid.MustParse("019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"),
		Operation:   "chat",
		Status:      "completed",
	}
	got := ev.RoutingKey()
	want := "user.019d5e3c-7cc5-7e6a-8b27-1344e148bf7c.llm.chat.completed"
	if got != want {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestTerminalEvent_RoutingKeyAllStatuses(t *testing.T) {
	// Pin the routing-key shape per terminal status so notification-
	// service can pattern-match `user.*.llm.*.completed` etc.
	for _, status := range []string{"completed", "failed", "cancelled"} {
		ev := TerminalEvent{
			OwnerUserID: uuid.New(),
			Operation:   "entity_extraction",
			Status:      status,
		}
		key := ev.RoutingKey()
		if !strings.HasSuffix(key, "."+status) {
			t.Errorf("status %q missing from routing key %q", status, key)
		}
		if !strings.Contains(key, ".llm.entity_extraction.") {
			t.Errorf("operation segment missing from key %q", key)
		}
	}
}

func TestNoopNotifier_NeverErrors(t *testing.T) {
	var n Notifier = NoopNotifier{}
	if err := n.PublishTerminal(context.Background(), TerminalEvent{
		JobID: uuid.New(), OwnerUserID: uuid.New(),
		Operation: "chat", Status: "completed",
	}); err != nil {
		t.Errorf("noop must never error: %v", err)
	}
	if err := n.Close(); err != nil {
		t.Errorf("noop close must never error: %v", err)
	}
}

func TestNewWorker_NilNotifierFallsBackToNoop(t *testing.T) {
	// Phase 2c — test/dev callers may pass nil; constructor must not
	// crash and must default to NoopNotifier so worker.publish is safe.
	w := NewWorker(nil, nil, nil, nil, nil)
	if _, ok := w.notifier.(NoopNotifier); !ok {
		t.Errorf("expected NoopNotifier fallback, got %T", w.notifier)
	}
}
