package consumer

// #297 — the fail-fast watchers. amqp091 delivers on NotifyClose for a broker
// restart AND for a local Close(); these tests pin both responses to that signal
// with hand-closed channels (the exact event shape NotifyClose hands back), so no
// live broker is needed. The issue's observed symptom — the silent WARN-and-return
// on the closed delivery channel — is pinned too: it now escalates to the same
// exit unless the close was graceful.

import (
	"context"
	"log/slog"
	"testing"
	"time"

	rabbitmq "github.com/rabbitmq/amqp091-go"
)

func expectConsumerExit(t *testing.T, exited <-chan int, what string) {
	t.Helper()
	select {
	case code := <-exited:
		if code != 1 {
			t.Fatalf("%s: exit code = %d, want 1", what, code)
		}
	case <-time.After(2 * time.Second):
		t.Fatalf("%s: consumer did not exit on the closed notification", what)
	}
}

func expectNoConsumerExit(t *testing.T, exited <-chan int, what string) {
	t.Helper()
	select {
	case code := <-exited:
		t.Fatalf("%s: unexpected exit(%d)", what, code)
	case <-time.After(150 * time.Millisecond):
	}
}

func newFailFastConsumer() (*Consumer, <-chan int) {
	exited := make(chan int, 4)
	c := &Consumer{logger: slog.Default(), exit: func(code int) { exited <- code }}
	return c, exited
}

func TestWatchClose_BrokerDropExits(t *testing.T) {
	c, exited := newFailFastConsumer()

	closed := make(chan *rabbitmq.Error, 1)
	close(closed)
	c.watchClose("connection", closed)
	expectConsumerExit(t, exited, "broker drop")
}

func TestWatchClose_GracefulCloseDoesNotExit(t *testing.T) {
	c, exited := newFailFastConsumer()
	c.closed.Store(true) // Close() stores this BEFORE the local Closes fire

	closed := make(chan *rabbitmq.Error, 1)
	close(closed)
	c.watchClose("channel", closed)
	expectNoConsumerExit(t, exited, "graceful Close")
}

func TestRun_ClosedDeliveriesEscalateToFailFast(t *testing.T) {
	c, exited := newFailFastConsumer()

	// The issue's observed log line: the delivery channel closed and run() returned
	// with only a WARN. It must now escalate to the fail-fast exit.
	deliveries := make(chan rabbitmq.Delivery)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan struct{})
	go func() { c.run(ctx, deliveries); close(done) }()
	close(deliveries)

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("run did not return on the closed delivery channel")
	}
	expectConsumerExit(t, exited, "closed deliveries")
}

func TestRun_GracefulClosedDeliveriesDoNotExit(t *testing.T) {
	c, exited := newFailFastConsumer()
	c.closed.Store(true)

	deliveries := make(chan rabbitmq.Delivery)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan struct{})
	go func() { c.run(ctx, deliveries); close(done) }()
	close(deliveries)

	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("run did not return on the closed delivery channel")
	}
	expectNoConsumerExit(t, exited, "graceful closed deliveries")
}
