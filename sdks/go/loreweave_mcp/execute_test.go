package loreweave_mcp

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"github.com/google/uuid"
)

// fakeSpec builds an OpSpec whose Handler returns the supplied detail/err,
// recording each invocation order via the shared *[]string log. All the
// registry invariants (Idempotent, Handler, IdentityKey) are satisfied so
// NewRegistry does not panic.
func fakeSpec(typ string, tier int, destructive bool, detail any, err error, log *[]string) OpSpec {
	return OpSpec{
		Type:        typ,
		Tier:        tier,
		Destructive: destructive,
		Idempotent:  true,
		IdentityKey: func(json.RawMessage) (string, error) { return typ, nil },
		Handler: func(_ context.Context, _, _ uuid.UUID, _ json.RawMessage, _ string) (any, error) {
			if log != nil {
				*log = append(*log, typ)
			}
			return detail, err
		},
	}
}

func op(id, typ string) Op { return Op{ID: id, Type: typ} }

// TestExecuteSentinelMapping checks each sentinel maps to the correct
// status+reason per the §5 table.
func TestExecuteSentinelMapping(t *testing.T) {
	cases := []struct {
		name       string
		err        error
		wantStatus string
		wantReason string
		bucket     string // "applied" | "skipped" | "failed"
	}{
		{"success", nil, StatusApplied, "", "applied"},
		{"unique", ErrUniqueViolation, StatusSkipped, ReasonAlreadyExists, "skipped"},
		{"already_done", ErrAlreadyDone, StatusSkipped, ReasonAlreadyDone, "skipped"},
		{"not_found", ErrNotFound, StatusFailed, ReasonTargetGone, "failed"},
		{"stale", ErrStaleVersion, StatusFailed, ReasonChangedSincePlanned, "failed"},
		{"bad_params", ErrBadParams, StatusFailed, ReasonBadParams, "failed"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			reg := NewRegistry(fakeSpec("t", 0, false, "d", tc.err, nil))
			p := Plan{BookID: uuid.New(), Ops: []Op{op("op-1", "t")}}
			s := Execute(context.Background(), uuid.New(), p, nil, reg)

			if s.Aborted {
				t.Fatalf("did not expect Aborted for a sentinel error")
			}
			var got []OpOutcome
			switch tc.bucket {
			case "applied":
				got = s.Applied
			case "skipped":
				got = s.Skipped
			case "failed":
				got = s.Failed
			}
			if len(got) != 1 {
				t.Fatalf("expected 1 outcome in %s, got applied=%d skipped=%d failed=%d",
					tc.bucket, len(s.Applied), len(s.Skipped), len(s.Failed))
			}
			o := got[0]
			if o.Status != tc.wantStatus || o.Reason != tc.wantReason {
				t.Fatalf("status/reason = %q/%q, want %q/%q", o.Status, o.Reason, tc.wantStatus, tc.wantReason)
			}
			if o.OpID != "op-1" || o.Type != "t" {
				t.Fatalf("OpID/Type = %q/%q, want op-1/t", o.OpID, o.Type)
			}
			if tc.err == nil && o.Detail != "d" {
				t.Fatalf("Detail = %v, want d", o.Detail)
			}
			if tc.bucket == "failed" && o.Message != tc.err.Error() {
				t.Fatalf("Message = %q, want %q", o.Message, tc.err.Error())
			}
		})
	}
}

// TestExecuteWrappedSentinel confirms errors.Is matches a wrapped sentinel
// (handlers wrap the sentinel with context — the mapping must still fire).
func TestExecuteWrappedSentinel(t *testing.T) {
	reg := NewRegistry(fakeSpec("t", 0, false, nil,
		errorsJoin(ErrUniqueViolation), nil))
	p := Plan{BookID: uuid.New(), Ops: []Op{op("op-1", "t")}}
	s := Execute(context.Background(), uuid.New(), p, nil, reg)
	if len(s.Skipped) != 1 || s.Skipped[0].Reason != ReasonAlreadyExists {
		t.Fatalf("wrapped unique violation should skip already_exists, got %+v", s)
	}
}

func errorsJoin(sentinel error) error {
	return errors.Join(errors.New("layer"), sentinel)
}

// TestExecuteInternalAborts checks a non-sentinel error aborts: ops after it are
// NOT run and Aborted=true.
func TestExecuteInternalAborts(t *testing.T) {
	var log []string
	reg := NewRegistry(
		fakeSpec("a", 0, false, "ok", nil, &log),
		fakeSpec("b", 1, false, nil, errors.New("db down"), &log),
		fakeSpec("c", 2, false, "ok", nil, &log),
	)
	p := Plan{BookID: uuid.New(), Ops: []Op{op("op-1", "a"), op("op-2", "b"), op("op-3", "c")}}
	s := Execute(context.Background(), uuid.New(), p, nil, reg)

	if !s.Aborted {
		t.Fatalf("expected Aborted=true after internal error")
	}
	if len(s.Applied) != 1 || s.Applied[0].OpID != "op-1" {
		t.Fatalf("expected only op-1 applied, got %+v", s.Applied)
	}
	if len(s.Failed) != 1 || s.Failed[0].Reason != ReasonInternal || s.Failed[0].OpID != "op-2" {
		t.Fatalf("expected op-2 failed internal, got %+v", s.Failed)
	}
	// "c" must NOT have run.
	for _, ran := range log {
		if ran == "c" {
			t.Fatalf("op c ran after an internal abort; log=%v", log)
		}
	}
	if len(log) != 2 {
		t.Fatalf("expected exactly 2 handlers to run, got %v", log)
	}
}

// TestExecuteDestructiveConfirm checks a destructive op not in enabledOps is
// skipped not_confirmed; in enabledOps it runs.
func TestExecuteDestructiveConfirm(t *testing.T) {
	t.Run("not enabled -> skipped not_confirmed", func(t *testing.T) {
		var log []string
		reg := NewRegistry(fakeSpec("del", 5, true, "gone", nil, &log))
		p := Plan{BookID: uuid.New(), Ops: []Op{op("op-1", "del")}}
		s := Execute(context.Background(), uuid.New(), p, nil, reg)
		if len(s.Skipped) != 1 || s.Skipped[0].Reason != ReasonNotConfirmed {
			t.Fatalf("expected skipped not_confirmed, got %+v", s)
		}
		if len(log) != 0 {
			t.Fatalf("destructive handler must not run when not enabled; log=%v", log)
		}
	})

	t.Run("enabled -> runs", func(t *testing.T) {
		var log []string
		reg := NewRegistry(fakeSpec("del", 5, true, "gone", nil, &log))
		p := Plan{BookID: uuid.New(), Ops: []Op{op("op-1", "del")}}
		s := Execute(context.Background(), uuid.New(), p, map[string]bool{"op-1": true}, reg)
		if len(s.Applied) != 1 || s.Applied[0].Detail != "gone" {
			t.Fatalf("expected applied with detail when enabled, got %+v", s)
		}
		if len(log) != 1 {
			t.Fatalf("destructive handler should run once when enabled; log=%v", log)
		}
	})
}

// TestExecuteTierOrdering checks ops execute in Tier order regardless of input
// order, preserving original order within a tier.
func TestExecuteTierOrdering(t *testing.T) {
	var log []string
	reg := NewRegistry(
		fakeSpec("adopt", 0, false, nil, nil, &log),
		fakeSpec("kind", 1, false, nil, nil, &log),
		fakeSpec("attr", 2, false, nil, nil, &log),
	)
	// Input order is deliberately reversed vs tier order.
	p := Plan{BookID: uuid.New(), Ops: []Op{
		op("op-1", "attr"),
		op("op-2", "kind"),
		op("op-3", "adopt"),
	}}
	s := Execute(context.Background(), uuid.New(), p, nil, reg)

	if s.Aborted || len(s.Applied) != 3 {
		t.Fatalf("expected 3 applied, no abort; got %+v", s)
	}
	want := []string{"adopt", "kind", "attr"}
	if len(log) != len(want) {
		t.Fatalf("ran %v, want %v", log, want)
	}
	for i := range want {
		if log[i] != want[i] {
			t.Fatalf("execution order = %v, want %v", log, want)
		}
	}
}

// TestExecuteWithinTierOrder checks original plan order is preserved within a tier.
func TestExecuteWithinTierOrder(t *testing.T) {
	var log []string
	reg := NewRegistry(
		fakeSpec("x", 1, false, nil, nil, &log),
		fakeSpec("y", 1, false, nil, nil, &log),
	)
	p := Plan{BookID: uuid.New(), Ops: []Op{op("op-1", "y"), op("op-2", "x")}}
	Execute(context.Background(), uuid.New(), p, nil, reg)
	if len(log) != 2 || log[0] != "y" || log[1] != "x" {
		t.Fatalf("within-tier order not preserved; log=%v", log)
	}
}

// TestExecuteCleanMultiOp checks a clean multi-op plan yields all Applied,
// Aborted=false, with non-nil empty slices for the empty buckets.
func TestExecuteCleanMultiOp(t *testing.T) {
	reg := NewRegistry(
		fakeSpec("a", 0, false, "da", nil, nil),
		fakeSpec("b", 1, false, "db", nil, nil),
	)
	p := Plan{BookID: uuid.New(), Ops: []Op{op("op-1", "a"), op("op-2", "b")}}
	s := Execute(context.Background(), uuid.New(), p, nil, reg)

	if s.Aborted {
		t.Fatalf("clean plan must not abort")
	}
	if len(s.Applied) != 2 {
		t.Fatalf("expected 2 applied, got %d", len(s.Applied))
	}
	// Empty buckets must be non-nil so JSON renders [] not null.
	if s.Skipped == nil || s.Failed == nil {
		t.Fatalf("Skipped/Failed must be non-nil empty slices, got skipped=%v failed=%v", s.Skipped, s.Failed)
	}
	b, err := json.Marshal(s)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if !contains(string(b), `"skipped":[]`) || !contains(string(b), `"failed":[]`) {
		t.Fatalf("empty slices must render as [], got %s", b)
	}
}

// TestExecuteDoesNotMutatePlan confirms the tier sort runs on a copy.
func TestExecuteDoesNotMutatePlan(t *testing.T) {
	reg := NewRegistry(
		fakeSpec("hi", 5, false, nil, nil, nil),
		fakeSpec("lo", 0, false, nil, nil, nil),
	)
	p := Plan{BookID: uuid.New(), Ops: []Op{op("op-1", "hi"), op("op-2", "lo")}}
	Execute(context.Background(), uuid.New(), p, nil, reg)
	if p.Ops[0].Type != "hi" || p.Ops[1].Type != "lo" {
		t.Fatalf("Execute mutated p.Ops order: %v", p.Ops)
	}
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
