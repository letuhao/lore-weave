package main

import (
	"bytes"
	"encoding/json"
	"io"
	"strings"
	"testing"

	events "github.com/loreweave/foundation/contracts/events"
	"github.com/loreweave/foundation/tests/workload-gen/internal/gen"
)

func TestRunUnknownProfile(t *testing.T) {
	if code := run(io.Discard, 1, "nope", false, ""); code != 2 {
		t.Errorf("unknown profile must exit 2, got %d", code)
	}
}

func TestRunEmitRequiresDSN(t *testing.T) {
	if code := run(io.Discard, 1, "micro", true, ""); code != 2 {
		t.Errorf("-emit without -dsn must exit 2, got %d", code)
	}
}

func TestRunDryRunEmitsValidJSONL(t *testing.T) {
	var buf bytes.Buffer
	if code := run(&buf, 1, "micro", false, ""); code != 0 {
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
