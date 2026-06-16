package live

import (
	"context"
	"strings"
	"sync"
	"testing"

	"github.com/loreweave/foundation/contracts/realityreg"
	"github.com/loreweave/foundation/services/migration-orchestrator/pkg/runner"
)

// fakeApplier records applies and can poison specific realities (return a
// permanent error so the canary/runner treats it as a hard failure).
type fakeApplier struct {
	mu      sync.Mutex
	poison  map[string]bool
	applied []string
}

func (a *fakeApplier) Apply(_ context.Context, realityID, _ string) (bool, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	if a.poison[realityID] {
		return false, &permErr{realityID}
	}
	a.applied = append(a.applied, realityID)
	return true, nil
}

type permErr struct{ id string }

func (e *permErr) Error() string { return "boom on " + e.id }

// recorder satisfies runner.Auditor + runner.StateWriter + canary.AbortAuditor.
type recorder struct {
	mu      sync.Mutex
	events  []runner.AuditEvent
	applied []string
	failed  []string
	aborts  []string
}

func (r *recorder) RecordEvent(_ context.Context, e runner.AuditEvent) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.events = append(r.events, e)
	return nil
}
func (r *recorder) MarkApplied(_ context.Context, id, _ string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.applied = append(r.applied, id)
	return nil
}
func (r *recorder) MarkFailed(_ context.Context, id, _, _ string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.failed = append(r.failed, id)
	return nil
}
func (r *recorder) RecordAbort(_ context.Context, id, _, _, reason string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.aborts = append(r.aborts, id+"@"+reason)
	return nil
}

func (r *recorder) fanoutStarted() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	n := 0
	for _, e := range r.events {
		if e.EventType == "migration_started" && strings.HasPrefix(e.RunID, "fanout-") {
			n++
		}
	}
	return n
}

func fleet(ids ...string) []realityreg.Reality {
	out := make([]realityreg.Reality, len(ids))
	for i, id := range ids {
		out[i] = realityreg.Reality{ID: id, DBHost: "pg-shard-0.internal", DBName: "db_" + id}
	}
	return out
}

func TestNonBreakingFansOutToWholeFleet(t *testing.T) {
	ap := &fakeApplier{}
	rec := &recorder{}
	out, err := RunMigration(context.Background(), Options{
		MigrationID: "0001_initial",
		Breaking:    false,
		Fleet:       fleet("r1", "r2", "r3"),
		Applier:     ap,
		Auditor:     rec,
		StateWriter: rec,
	})
	if err != nil {
		t.Fatalf("RunMigration: %v", err)
	}
	if len(out.Results) != 3 {
		t.Fatalf("want 3 results, got %d", len(out.Results))
	}
	for _, r := range out.Results {
		if !r.Succeeded {
			t.Fatalf("reality %s did not succeed", r.RealityID)
		}
	}
	if len(rec.applied) != 3 {
		t.Fatalf("want 3 applied marks, got %d", len(rec.applied))
	}
}

// The headline W1.2 invariant: a breaking migration broken on the canary aborts
// fan-out — the rest are NEVER attempted.
func TestBreakingCanaryFailureAbortsFanout(t *testing.T) {
	// Canary = lexicographically smallest = "r0". Poison it.
	ap := &fakeApplier{poison: map[string]bool{"r0": true}}
	rec := &recorder{}
	out, err := RunMigration(context.Background(), Options{
		MigrationID: "0009_breaking",
		Breaking:    true,
		Fleet:       fleet("r0", "r1", "r2", "r3"),
		Applier:     ap,
		Auditor:     rec,
		StateWriter: rec,
		Aborter:     rec,
		Verifier:    func(context.Context, string, string) (bool, string) { return true, "" },
	})
	if err != nil {
		t.Fatalf("RunMigration: %v", err)
	}
	if !out.Aborted || out.AbortReason != "canary_apply_failed" {
		t.Fatalf("want abort canary_apply_failed, got aborted=%v reason=%q", out.Aborted, out.AbortReason)
	}
	if got := rec.fanoutStarted(); got != 0 {
		t.Fatalf("fan-out was attempted (%d migration_started with fanout- RunID) despite canary failure", got)
	}
	// The 3 non-canary realities must each be recorded as aborted, not applied.
	if len(rec.aborts) != 3 {
		t.Fatalf("want 3 abort records, got %d (%v)", len(rec.aborts), rec.aborts)
	}
	for _, id := range ap.applied {
		if id != "r0" {
			t.Fatalf("a non-canary reality (%s) was applied despite the abort", id)
		}
	}
}

// Fail-closed default: a breaking migration with no Verifier must abort at the
// verification gate (the V1 "suite not wired" posture), not silently fan out.
func TestBreakingFailsClosedWithoutVerifier(t *testing.T) {
	ap := &fakeApplier{}
	rec := &recorder{}
	out, err := RunMigration(context.Background(), Options{
		MigrationID: "0009_breaking",
		Breaking:    true,
		Fleet:       fleet("r0", "r1"),
		Applier:     ap,
		Auditor:     rec,
		StateWriter: rec,
		Aborter:     rec,
		// Verifier nil → fail-closed.
	})
	if err != nil {
		t.Fatalf("RunMigration: %v", err)
	}
	if !out.Aborted || !strings.Contains(out.AbortReason, "verification_suite_not_wired") {
		t.Fatalf("want fail-closed verification abort, got aborted=%v reason=%q", out.Aborted, out.AbortReason)
	}
	if got := rec.fanoutStarted(); got != 0 {
		t.Fatalf("fan-out attempted (%d) despite the fail-closed gate", got)
	}
}
