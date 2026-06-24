// Package verdict defines the conformance suite's uniform result contract.
//
// Every case — a shell lint (exit 0/1/2), a Go `-tags=integration` test, a Rust
// test, or a live probe — collapses to one of four verdicts so heterogeneous
// tools report into a single machine-readable history. This contract IS the S1
// build (test-plan §1.3; plan §2.3–2.4).
//
// The cardinal rule: only Fail breaks the gate. Notrun and Skip let the
// live-stack half of the suite degrade gracefully on a dev box that lacks the
// infra (no docker, no DATABASE_URL) instead of flapping the build red.
package verdict

import (
	"encoding/json"
	"fmt"
)

// Verdict is the uniform outcome of a single conformance case.
type Verdict string

const (
	// Pass: the case ran and met its assertion.
	Pass Verdict = "pass"
	// Fail: the case ran and violated its assertion. The ONLY gate-breaking verdict.
	Fail Verdict = "fail"
	// Notrun: the case could not run because a precondition/infra requirement was
	// unmet (e.g. docker stack absent, DATABASE_URL unset, or a harness/setup
	// error). Distinct from Skip: notrun = "wanted to run, couldn't".
	Notrun Verdict = "notrun"
	// Skip: the case is legitimately not applicable on this stack (e.g. I4 on a
	// single-superuser dev DB, I5 before the provisioner exists) OR it is
	// expunged — known-broken and tracked in Deferred-Items. Distinct from
	// Notrun: skip = "ran-or-not, deliberately not counted".
	Skip Verdict = "skip"
)

// Valid reports whether v is one of the four defined verdicts.
func (v Verdict) Valid() bool {
	switch v {
	case Pass, Fail, Notrun, Skip:
		return true
	default:
		return false
	}
}

// GateBreaking reports whether this verdict should fail the suite. Only Fail
// does — notrun/skip/pass never break the gate (see package doc).
func (v Verdict) GateBreaking() bool {
	return v == Fail
}

// Result is the outcome of one conformance case, serialized one-per-line into
// the JSONL run store (history-friendly; parallels the perf time-series §8).
type Result struct {
	ID          string  `json:"id"`
	Kind        string  `json:"kind"`
	Verdict     Verdict `json:"verdict"`
	Reason      string  `json:"reason,omitempty"`
	Invariant   string  `json:"invariant,omitempty"`
	Description string  `json:"description,omitempty"`
	DurationMS  int64   `json:"duration_ms"`
}

// MarshalLine renders the result as a single JSONL line (no trailing newline).
func (r Result) MarshalLine() ([]byte, error) {
	if !r.Verdict.Valid() {
		return nil, fmt.Errorf("verdict: result %q has invalid verdict %q", r.ID, r.Verdict)
	}
	return json.Marshal(r)
}

// ParseLine parses one JSONL line back into a Result, rejecting an unknown
// verdict so a corrupted/forward-incompatible history surfaces loudly.
func ParseLine(line []byte) (Result, error) {
	var r Result
	if err := json.Unmarshal(line, &r); err != nil {
		return Result{}, err
	}
	if !r.Verdict.Valid() {
		return Result{}, fmt.Errorf("verdict: parsed result %q has invalid verdict %q", r.ID, r.Verdict)
	}
	return r, nil
}
