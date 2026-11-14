package jobs

// #297 — the fail-fast watchers. amqp091 delivers on NotifyClose for a broker
// restart AND for a local Close(); these tests pin both responses to that signal,
// using hand-closed channels (the exact event shape NotifyClose hands back) so no
// live broker is needed. The live broker-restart round-trip stays the infra-level
// scenario the issue documents.

import (
	"log/slog"
	"testing"
	"time"

	rabbitmq "github.com/rabbitmq/amqp091-go"
)

// exitRecorder swaps the package-level osExit for a channel-returning stub and
// restores it on cleanup. Tests in this package run sequentially (no t.Parallel),
// so the swap is safe.
func exitRecorder(t *testing.T) <-chan int {
	t.Helper()
	exited := make(chan int, 4)
	orig := osExit
	osExit = func(code int) { exited <- code }
	t.Cleanup(func() { osExit = orig })
	return exited
}

func expectExit(t *testing.T, exited <-chan int, what string) {
	t.Helper()
	select {
	case code := <-exited:
		if code != 1 {
			t.Fatalf("%s: exit code = %d, want 1", what, code)
		}
	case <-time.After(2 * time.Second):
		t.Fatalf("%s: process did not exit on the closed notification", what)
	}
}

func expectNoExit(t *testing.T, exited <-chan int, what string) {
	t.Helper()
	select {
	case code := <-exited:
		t.Fatalf("%s: unexpected exit(%d) on the graceful path", what, code)
	case <-time.After(150 * time.Millisecond):
	}
}

func TestFailFastOnClose_BrokerDropExits(t *testing.T) {
	q := &JobQueue{logger: slog.Default()}
	exited := exitRecorder(t)

	closed := make(chan *rabbitmq.Error, 1)
	close(closed) // the exact event NotifyClose delivers on a broker drop
	q.failFastOnClose("connection", closed)
	expectExit(t, exited, "broker drop")
}

func TestFailFastOnClose_GracefulCloseDoesNotExit(t *testing.T) {
	q := &JobQueue{logger: slog.Default()}
	exited := exitRecorder(t)
	q.closed.Store(true) // Close() stores this BEFORE the local Closes fire

	closed := make(chan *rabbitmq.Error, 1)
	close(closed)
	q.failFastOnClose("publish channel", closed)
	expectNoExit(t, exited, "graceful Close")
}

func TestNotifierWatchClose_BrokerDropExits(t *testing.T) {
	n := &rabbitMQNotifier{logger: slog.Default()}
	exited := exitRecorder(t)

	closed := make(chan *rabbitmq.Error, 1)
	close(closed)
	n.watchClose("notifier channel", closed)
	expectExit(t, exited, "notifier broker drop")
}

func TestNotifierWatchClose_GracefulCloseDoesNotExit(t *testing.T) {
	n := &rabbitMQNotifier{logger: slog.Default()}
	exited := exitRecorder(t)
	n.closed.Store(true)

	closed := make(chan *rabbitmq.Error, 1)
	close(closed)
	n.watchClose("notifier connection", closed)
	expectNoExit(t, exited, "notifier graceful Close")
}

// An OPEN channel (nothing closed, nothing graceful) never exits — the watcher
// parks forever until either the broker drops or Close marks graceful.
func TestFailFastOnClose_OpenChannelParksSilently(t *testing.T) {
	q := &JobQueue{logger: slog.Default()}
	exited := exitRecorder(t)

	q.failFastOnClose("consumer channel", make(chan *rabbitmq.Error, 1))
	expectNoExit(t, exited, "open channel")
}
