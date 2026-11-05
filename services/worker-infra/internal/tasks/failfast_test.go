package tasks

// #297 — the WS-push fail-fast watcher. amqp091 delivers on NotifyClose for a
// broker restart AND for a local Close(); this pins the exit on the broker-drop
// signal and the stand-down on Run's ctx (cancelled on SIGTERM before Run returns),
// with hand-closed/open channels so no live broker is needed.

import (
	"context"
	"testing"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

func expectWorkerExit(t *testing.T, exited <-chan int, what string) {
	t.Helper()
	select {
	case code := <-exited:
		if code != 1 {
			t.Fatalf("%s: exit code = %d, want 1", what, code)
		}
	case <-time.After(2 * time.Second):
		t.Fatalf("%s: watcher did not exit on the closed notification", what)
	}
}

func TestWatchAMQP_BrokerDropExits(t *testing.T) {
	tk := &ImportProcessor{}
	exited := make(chan int, 4)
	orig := osExit
	osExit = func(code int) { exited <- code }
	t.Cleanup(func() { osExit = orig })

	closed := make(chan *amqp.Error, 1)
	close(closed)
	tk.watchAMQP(context.Background(), "connection", closed)
	expectWorkerExit(t, exited, "broker drop")
}

func TestWatchAMQP_ContextCancelStandsDown(t *testing.T) {
	tk := &ImportProcessor{}
	exited := make(chan int, 4)
	orig := osExit
	osExit = func(code int) { exited <- code }
	t.Cleanup(func() { osExit = orig })

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // SIGTERM ordering: Run's ctx cancels before anything closes
	tk.watchAMQP(ctx, "channel", make(chan *amqp.Error, 1)) // stays open
	select {
	case code := <-exited:
		t.Fatalf("unexpected exit(%d) after ctx cancellation", code)
	case <-time.After(150 * time.Millisecond):
	}
}
