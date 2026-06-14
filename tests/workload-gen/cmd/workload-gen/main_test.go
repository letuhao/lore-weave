package main

import (
	"bytes"
	"encoding/json"
	"io"
	"strings"
	"testing"
	"time"

	events "github.com/loreweave/foundation/contracts/events"
	"github.com/loreweave/foundation/tests/workload-gen/internal/gen"
)

func TestPaceSleep(t *testing.T) {
	// rate 0 → never pace.
	if d := paceSleep(1000, 0, time.Second); d != 0 {
		t.Errorf("rate=0 must not pace, got %v", d)
	}
	// 100 emitted at 100 eps → target elapsed 1s; only 200ms in → sleep ~800ms.
	if d := paceSleep(100, 100, 200*time.Millisecond); d < 790*time.Millisecond || d > 810*time.Millisecond {
		t.Errorf("expected ~800ms sleep, got %v", d)
	}
	// Already behind (2s elapsed, target 1s) → no sleep.
	if d := paceSleep(100, 100, 2*time.Second); d != 0 {
		t.Errorf("behind schedule must not sleep, got %v", d)
	}
}

func TestRunUnknownProfile(t *testing.T) {
	if code := run(io.Discard, 1, "nope", false, false, false, false, "", 0, 0); code != 2 {
		t.Errorf("unknown profile must exit 2, got %d", code)
	}
}

func TestRunEmitRequiresDSN(t *testing.T) {
	if code := run(io.Discard, 1, "micro", true, false, false, false, "", 0, 0); code != 2 {
		t.Errorf("-emit without -dsn must exit 2, got %d", code)
	}
}

func TestRunVerifyRequiresDSN(t *testing.T) {
	if code := run(io.Discard, 1, "micro", false, true, false, false, "", 0, 0); code != 2 {
		t.Errorf("-verify without -dsn must exit 2, got %d", code)
	}
}

func TestRunCheckProjectionsRequiresDSN(t *testing.T) {
	if code := run(io.Discard, 1, "micro", false, false, true, false, "", 0, 0); code != 2 {
		t.Errorf("-check-projections without -dsn must exit 2, got %d", code)
	}
}

func TestRunDryRunEmitsValidJSONL(t *testing.T) {
	var buf bytes.Buffer
	if code := run(&buf, 1, "micro", false, false, false, false, "", 0, 0); code != 0 {
		t.Fatalf("dry-run must exit 0, got %d", code)
	}
	var stream gen.Stream
	for _, ln := range strings.Split(strings.TrimSpace(buf.String()), "\n") {
		var e events.Envelope
		if err := json.Unmarshal([]byte(ln), &e); err != nil {
			t.Fatalf("emitted line is not a valid envelope: %v\nline: %s", err, ln)
		}
		stream = append(stream, e)
	}
	if len(stream) == 0 {
		t.Fatal("dry-run produced no events")
	}
	// The JSONL must round-trip back into a stream that still passes validation.
	if err := gen.Validate(stream); err != nil {
		t.Errorf("round-tripped JSONL fails validation: %v", err)
	}
}
