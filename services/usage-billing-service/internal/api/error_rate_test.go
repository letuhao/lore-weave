package api

import (
	"os"
	"strings"
	"testing"
)

// Widening request_status would have silently redefined a USER-FACING number.
//
// The summary's errorRate counted every row that was not 'success'. That was correct while the
// CHECK permitted only success | provider_error | billing_rejected. Once 'cancelled' and 'aborted'
// can be written, the same expression reports a request the AUTHOR cancelled as the AUTHOR's error
// — a fix to one defect quietly creating another, in a number a person reads.

func serverSrc(t *testing.T) string {
	t.Helper()
	b, err := os.ReadFile("server.go")
	if err != nil {
		t.Fatalf("read server.go: %v", err)
	}
	return string(b)
}

func TestTheErrorRateENUMERATESFailuresRatherThanNegatingSuccess(t *testing.T) {
	src := serverSrc(t)
	if strings.Contains(src, "request_status!='success'") {
		t.Fatal("errorRate still negates success — a cancelled request now counts as the user's error")
	}
	if n := strings.Count(src, "('provider_error','billing_rejected','failed')"); n != 2 {
		t.Fatalf("expected both summary queries to enumerate the failure statuses, found %d", n)
	}
}

func TestACancelledRequestIsNotAnError(t *testing.T) {
	// The whole point, stated as the property rather than as a string: cancelled and aborted are
	// terminal outcomes the AUTHOR chose, and must not appear in the failure set.
	src := serverSrc(t)
	i := strings.Index(src, "('provider_error','billing_rejected','failed')")
	if i < 0 {
		t.Fatal("no enumerated failure set")
	}
	set := src[i : i+50]
	for _, notAnError := range []string{"cancelled", "aborted"} {
		if strings.Contains(set, notAnError) {
			t.Errorf("%q is counted as an error in the user-facing error rate", notAnError)
		}
	}
}
