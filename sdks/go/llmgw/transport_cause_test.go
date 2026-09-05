package llmgw

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// 🔴 A CANCELLED REQUEST MUST STILL LOOK CANCELLED.
//
// The transport built its message with `"get_job transport failure: "+err.Error()`
// and passed only the CODE to newErrorFromCode, so the real error went into a string
// and nowhere else. errors.Is(err, context.Canceled) was false, and a caller could
// not tell "the user cancelled" from "the network broke".
//
// 🔴 WHY THIS TEST EXISTS ALONGSIDE TestWaitTerminal_ContextCancellation. That test
// cancels after 50ms while polling every 10ms, so it only catches the bug when the
// cancel happens to land MID-REQUEST — it passed alone and failed under a loaded full
// run. A defect that reproduces only under load is one that gets dismissed as flake.
// This one cancels the context BEFORE the call, so the wrap path is taken every time.
func TestATransportErrorKeepsItsCause(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(200 * time.Millisecond) // outlive the cancel below
	}))
	defer srv.Close()

	c := testClient(t, srv, "user-1")
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // already dead: the transport MUST take the error path

	_, err := c.getJob(ctx, "job-1", "")
	if err == nil {
		t.Fatal("a cancelled context produced no error — the assertions below would be vacuous")
	}
	if !errors.Is(err, ErrHTTPTransport) {
		t.Errorf("errors.Is(err, ErrHTTPTransport) = false; got %v", err)
	}
	if !errors.Is(err, context.Canceled) {
		t.Errorf("errors.Is(err, context.Canceled) = false; got %v.\n"+
			"The cause was formatted into the message and discarded, so a caller cannot "+
			"distinguish a user cancellation from a network failure.", err)
	}
}

// errors.Unwrap (the stdlib FUNCTION) returns nil for a multi-error Unwrap() []error.
// The first fix here used that signature and silently broke chain-walking callers —
// caught by TestError_Unwrap_ReturnsInner. The cause is joined into the single inner
// error instead, so both styles keep working.
func TestUnwrapStaysSingleErrorSoStdlibUnwrapKeepsWorking(t *testing.T) {
	plain := newErrorFromCode("LLM_QUOTA_EXCEEDED", "nope", 402)
	if errors.Unwrap(plain) != ErrQuotaExceeded {
		t.Fatalf("errors.Unwrap on a plain coded error = %v, want the bare sentinel",
			errors.Unwrap(plain))
	}
	wrapped := newTransportError("LLM_HTTP_ERROR", "boom", 0, context.DeadlineExceeded)
	if errors.Unwrap(wrapped) == nil {
		t.Fatal("errors.Unwrap returned nil for a transport error — a multi-error " +
			"Unwrap() []error does exactly this, and it breaks chain-walking callers")
	}
	if !errors.Is(wrapped, ErrHTTPTransport) || !errors.Is(wrapped, context.DeadlineExceeded) {
		t.Error("a joined cause must keep BOTH the sentinel and the cause matchable")
	}
}

// Teeth against over-broad joining: an error with no cause must still unwrap to the
// BARE sentinel, not to something wrapping it.
func TestACodedErrorWithNoCauseUnwrapsToTheBareSentinel(t *testing.T) {
	e := newTransportError("LLM_HTTP_ERROR", "no cause here", 0, nil)
	if errors.Unwrap(e) != ErrHTTPTransport {
		t.Errorf("Unwrap = %v, want the bare ErrHTTPTransport", errors.Unwrap(e))
	}
}
