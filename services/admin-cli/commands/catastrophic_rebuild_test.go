package commands

import (
	"context"
	"errors"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/loreweave/foundation/services/admin-cli/internal/rolling_rebuild"
)

type catastrophicStubRebuilder struct {
	mu          sync.Mutex
	calls       []string
	inFlight    int64
	maxInFlight int64
	failSet     map[string]bool
	sleepPerCall time.Duration
}

func (s *catastrophicStubRebuilder) RebuildReality(_ context.Context, realityID, _, _ string) (rolling_rebuild.PerRealityStats, error) {
	inFlight := atomic.AddInt64(&s.inFlight, 1)
	defer atomic.AddInt64(&s.inFlight, -1)
	for {
		cur := atomic.LoadInt64(&s.maxInFlight)
		if inFlight <= cur {
			break
		}
		if atomic.CompareAndSwapInt64(&s.maxInFlight, cur, inFlight) {
			break
		}
	}
	if s.sleepPerCall > 0 {
		time.Sleep(s.sleepPerCall)
	}
	s.mu.Lock()
	s.calls = append(s.calls, realityID)
	s.mu.Unlock()
	if s.failSet[realityID] {
		return rolling_rebuild.PerRealityStats{RealityID: realityID}, errors.New("rebuild failed: " + realityID)
	}
	return rolling_rebuild.PerRealityStats{RealityID: realityID, ProjectionsOK: 5}, nil
}

// ── Validate ────────────────────────────────────────────────────────────────

func TestCatastrophicValidate_RejectsBadScope(t *testing.T) {
	req := CatastrophicRebuildRequest{
		Scope: "bogus", RealityIDs: []string{"r1"}, Actor: "a", Reason: "r", Confirm: true,
		RollingConcurrency: 10, PerRealityTimeout: time.Minute,
	}
	err := req.Validate()
	if err == nil || !errors.Is(err, ErrInvalidCatastrophic) {
		t.Fatalf("want ErrInvalidCatastrophic, got %v", err)
	}
}

func TestCatastrophicValidate_RejectsMissingConfirm(t *testing.T) {
	req := CatastrophicRebuildRequest{
		Scope: "reality", RealityIDs: []string{"r1"}, Actor: "a", Reason: "r",
		RollingConcurrency: 10, PerRealityTimeout: time.Minute,
	}
	err := req.Validate()
	if err == nil || !errors.Is(err, ErrInvalidCatastrophic) {
		t.Fatalf("want ErrInvalidCatastrophic, got %v", err)
	}
	if !strings.Contains(err.Error(), "--confirm") {
		t.Fatalf("want --confirm in error, got %v", err)
	}
}

func TestCatastrophicValidate_RejectsConcurrencyOver50(t *testing.T) {
	req := CatastrophicRebuildRequest{
		Scope: "reality", RealityIDs: []string{"r1"}, Actor: "a", Reason: "r", Confirm: true,
		RollingConcurrency: 100, PerRealityTimeout: time.Minute,
	}
	err := req.Validate()
	if err == nil || !errors.Is(err, ErrInvalidCatastrophic) {
		t.Fatalf("want ErrInvalidCatastrophic, got %v", err)
	}
}

func TestCatastrophicValidate_RejectsTimeoutOver30min(t *testing.T) {
	req := CatastrophicRebuildRequest{
		Scope: "reality", RealityIDs: []string{"r1"}, Actor: "a", Reason: "r", Confirm: true,
		RollingConcurrency: 10, PerRealityTimeout: 60 * time.Minute,
	}
	err := req.Validate()
	if err == nil || !errors.Is(err, ErrInvalidCatastrophic) {
		t.Fatalf("want ErrInvalidCatastrophic, got %v", err)
	}
}

// ── Apply ───────────────────────────────────────────────────────────────────

func TestApplyCatastrophic_DryRun_NoCalls(t *testing.T) {
	stub := &catastrophicStubRebuilder{}
	req := CatastrophicRebuildRequest{
		Scope: "reality", RealityIDs: []string{"r1", "r2"}, Actor: "ops", Reason: "drill",
		DryRun: true, RollingConcurrency: 10, PerRealityTimeout: time.Minute,
	}
	res, err := ApplyCatastrophicRebuild(context.Background(), req, stub)
	if err != nil {
		t.Fatalf("dry-run failed: %v", err)
	}
	if !res.DryRun || res.TotalRealities != 2 {
		t.Fatalf("bad dry-run result: %+v", res)
	}
	if len(stub.calls) != 0 {
		t.Fatal("dry-run must not invoke rebuilder")
	}
}

func TestApplyCatastrophic_RollingNotBigBang(t *testing.T) {
	// 12 realities × 30ms sleep × concurrency cap = 4.
	// Wall-clock floor = ceil(12/4) * 30ms = 90ms. Big-bang would be 30ms.
	// The KEY invariant is: MaxConcurrentSeen never exceeds 4.
	stub := &catastrophicStubRebuilder{sleepPerCall: 30 * time.Millisecond}
	realities := make([]string, 12)
	for i := range realities {
		realities[i] = string(rune('a' + i))
	}
	req := CatastrophicRebuildRequest{
		Scope: "all-realities", RealityIDs: realities, Actor: "ops", Reason: "drill",
		Confirm: true, RollingConcurrency: 4, PerRealityTimeout: time.Second,
	}
	res, err := ApplyCatastrophicRebuild(context.Background(), req, stub)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}
	if res.MaxConcurrentSeen > 4 {
		t.Fatalf("ROLLING INVARIANT VIOLATED: max=%d > cap=4", res.MaxConcurrentSeen)
	}
	if res.RealitiesOK != 12 {
		t.Fatalf("want 12 OK, got %+v", res)
	}
}

func TestApplyCatastrophic_PartialFailure_DoesNotAbort(t *testing.T) {
	stub := &catastrophicStubRebuilder{failSet: map[string]bool{"r3": true, "r7": true}}
	req := CatastrophicRebuildRequest{
		Scope: "aggregate-list", RealityIDs: []string{"r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"},
		Actor: "ops", Reason: "drill", Confirm: true,
		RollingConcurrency: 3, PerRealityTimeout: time.Second,
	}
	res, err := ApplyCatastrophicRebuild(context.Background(), req, stub)
	if err != nil {
		t.Fatalf("apply: %v", err)
	}
	if res.RealitiesOK != 6 || res.RealitiesFailed != 2 {
		t.Fatalf("want 6 OK / 2 failed, got %+v", res)
	}
	if _, ok := res.PerRealityErrors["r3"]; !ok {
		t.Fatal("r3 missing from PerRealityErrors")
	}
	if _, ok := res.PerRealityErrors["r7"]; !ok {
		t.Fatal("r7 missing from PerRealityErrors")
	}
	if len(stub.calls) != 8 {
		t.Fatalf("want all 8 attempted, got %d", len(stub.calls))
	}
}
