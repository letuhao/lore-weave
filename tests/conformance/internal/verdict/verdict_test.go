package verdict

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestVerdictValid(t *testing.T) {
	for _, v := range []Verdict{Pass, Fail, Notrun, Skip} {
		if !v.Valid() {
			t.Errorf("%q should be Valid()", v)
		}
	}
	for _, v := range []Verdict{"", "PASS", "error", "unknown"} {
		if v.Valid() {
			t.Errorf("%q should NOT be Valid()", v)
		}
	}
}

func TestGateBreakingOnlyFail(t *testing.T) {
	if !Fail.GateBreaking() {
		t.Error("Fail must be gate-breaking")
	}
	for _, v := range []Verdict{Pass, Notrun, Skip} {
		if v.GateBreaking() {
			t.Errorf("%q must NOT be gate-breaking (only Fail breaks the gate)", v)
		}
	}
}

func TestResultRoundTrip(t *testing.T) {
	in := Result{
		ID:          "projection-coverage",
		Kind:        "lint",
		Verdict:     Pass,
		Invariant:   "PRR-32",
		Description: "every event type accounted for",
		DurationMS:  42,
	}
	line, err := in.MarshalLine()
	if err != nil {
		t.Fatalf("MarshalLine: %v", err)
	}
	if strings.Contains(string(line), "\n") {
		t.Errorf("JSONL line must not contain a newline: %q", line)
	}
	out, err := ParseLine(line)
	if err != nil {
		t.Fatalf("ParseLine: %v", err)
	}
	if out != in {
		t.Errorf("round-trip mismatch:\n in=%+v\nout=%+v", in, out)
	}
}

func TestOmitemptyOptionalFields(t *testing.T) {
	// A pass with no reason/invariant should not serialize those keys.
	line, err := Result{ID: "x", Kind: "lint", Verdict: Pass}.MarshalLine()
	if err != nil {
		t.Fatalf("MarshalLine: %v", err)
	}
	var m map[string]any
	if err := json.Unmarshal(line, &m); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	for _, k := range []string{"reason", "invariant"} {
		if _, present := m[k]; present {
			t.Errorf("empty %q should be omitted, got line %q", k, line)
		}
	}
	// duration_ms has no omitempty — it is always present (0 is meaningful).
	if _, present := m["duration_ms"]; !present {
		t.Errorf("duration_ms must always be present, got line %q", line)
	}
}

func TestMarshalLineRejectsInvalidVerdict(t *testing.T) {
	if _, err := (Result{ID: "x", Kind: "lint", Verdict: "bogus"}).MarshalLine(); err == nil {
		t.Error("MarshalLine must reject an invalid verdict")
	}
}

func TestParseLineRejectsInvalidVerdict(t *testing.T) {
	if _, err := ParseLine([]byte(`{"id":"x","kind":"lint","verdict":"bogus","duration_ms":0}`)); err == nil {
		t.Error("ParseLine must reject an invalid verdict")
	}
}
