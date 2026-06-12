package rolling_rebuild

import (
	"context"
	"errors"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// stubRebuilder records calls + tracks concurrency.
type stubRebuilder struct {
	mu              sync.Mutex
	calls           []string
	inFlight        int64
	maxInFlight     int64
	sleepPerCall    time.Duration
	failRealitySet  map[string]bool // realityIDs that should fail
}

func (s *stubRebuilder) RebuildReality(_ context.Context, realityID, _, _ string) (PerRealityStats, error) {
	inFlight := atomic.AddInt64(&s.inFlight, 1)
	defer atomic.AddInt64(&s.inFlight, -1)
	for {
		current := atomic.LoadInt64(&s.maxInFlight)
		if inFlight <= current {
			break
		}
		if atomic.CompareAndSwapInt64(&s.maxInFlight, current, inFlight) {
			break
		}
	}
	if s.sleepPerCall > 0 {
		time.Sleep(s.sleepPerCall)
	}
	s.mu.Lock()
	s.calls = append(s.calls, realityID)
	s.mu.Unlock()
	if s.failRealitySet[realityID] {
		return PerRealityStats{RealityID: realityID}, errors.New("simulated rebuild failure for " + realityID)
	}
	return PerRealityStats{RealityID: realityID, ProjectionsOK: 5, AggregatesRebuilt: 100, EventsReplayed: 1000}, nil
}

// ── Config validation ────────────────────────────────────────────────────────

func TestConfig_Validate_RejectsZeroConcurrency(t *testing.T) {
	cfg := Config{RollingConcurrency: 0, PerRealityTimeout: time.Minute}
	if err := cfg.Validate(); err == nil || !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("want ErrInvalidConfig, got %v", err)
	}
}

func TestConfig_Validate_RejectsOver50Concurrency(t *testing.T) {
	cfg := Config{RollingConcurrency: 51, PerRealityTimeout: time.Minute}
	err := cfg.Validate()
	if err == nil || !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("want ErrInvalidConfig, got %v", err)
	}
	if !strings.Contains(err.Error(), "50") {
		t.Fatalf("error must mention 50 cap, got %v", err)
	}
}

func TestConfig_Validate_RejectsZeroTimeout(t *testing.T) {
	cfg := Config{RollingConcurrency: 10, PerRealityTimeout: 0}
	if err := cfg.Validate(); err == nil || !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("want ErrInvalidConfig, got %v", err)
	}
}

func TestNew_RejectsNilRebuilder(t *testing.T) {
	_, err := New(Config{RollingConcurrency: 10, PerRealityTimeout: time.Minute}, nil)
	if err == nil || !errors.Is(err, ErrInvalidConfig) {
		t.Fatalf("want ErrInvalidConfig, got %v", err)
	}
}

// ── Rolling concurrency ─────────────────────────────────────────────────────

func TestRun_ConcurrencyNeverExceedsConfig(t *testing.T) {
	// 20 realities × 50ms each, concurrency cap = 5. MaxInFlight must NEVER
	// exceed 5 (this is the load-bearing R02 §12B.5 invariant).
	stub := &stubRebuilder{sleepPerCall: 50 * time.Millisecond}
	o, err := New(Config{RollingConcurrency: 5, PerRealityTimeout: time.Second}, stub)
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	realities := make([]string, 20)
	for i := range realities {
		realities[i] = "r" + string(rune('a'+i))
	}
	res := o.Run(context.Background(), realities, "ops", "drill")
	if res.MaxConcurrentSeen > 5 {
		t.Fatalf("ROLLING INVARIANT VIOLATED: max concurrent = %d (cap = 5)", res.MaxConcurrentSeen)
	}
	if atomic.LoadInt64(&stub.maxInFlight) > 5 {
		t.Fatalf("stub also saw > 5 concurrent: %d", stub.maxInFlight)
	}
	if res.RealitiesOK != 20 {
		t.Fatalf("want 20 OK, got %d (failed=%d)", res.RealitiesOK, res.RealitiesFailed)
	}
	if len(stub.calls) != 20 {
		t.Fatalf("want 20 calls, got %d", len(stub.calls))
	}
}

func TestRun_AllSucceed(t *testing.T) {
	stub := &stubRebuilder{}
	o, _ := New(Config{RollingConcurrency: 3, PerRealityTimeout: time.Second}, stub)
	res := o.Run(context.Background(), []string{"r1", "r2", "r3"}, "ops", "x")
	if res.TotalRealities != 3 || res.RealitiesOK != 3 || res.RealitiesFailed != 0 {
		t.Fatalf("bad summary: %+v", res)
	}
	if len(res.PerReality) != 3 {
		t.Fatalf("want 3 per-reality stats, got %d", len(res.PerReality))
	}
}

func TestRun_PartialFailure_ContinuesAndRecords(t *testing.T) {
	stub := &stubRebuilder{failRealitySet: map[string]bool{"r2": true, "r4": true}}
	o, _ := New(Config{RollingConcurrency: 2, PerRealityTimeout: time.Second}, stub)
	res := o.Run(context.Background(), []string{"r1", "r2", "r3", "r4", "r5"}, "ops", "x")
	if res.RealitiesOK != 3 || res.RealitiesFailed != 2 {
		t.Fatalf("want 3 OK / 2 failed, got %+v", res)
	}
	if _, ok := res.PerRealityErrors["r2"]; !ok {
		t.Fatal("r2 missing from PerRealityErrors")
	}
	if _, ok := res.PerRealityErrors["r4"]; !ok {
		t.Fatal("r4 missing from PerRealityErrors")
	}
	if len(stub.calls) != 5 {
		t.Fatalf("partial failure must NOT abort run, want 5 calls, got %d", len(stub.calls))
	}
}

func TestRun_EmptyRealityList_NoOp(t *testing.T) {
	stub := &stubRebuilder{}
	o, _ := New(Config{RollingConcurrency: 5, PerRealityTimeout: time.Second}, stub)
	res := o.Run(context.Background(), nil, "ops", "x")
	if res.TotalRealities != 0 || res.RealitiesOK != 0 || res.RealitiesFailed != 0 {
		t.Fatalf("empty run produced non-zero summary: %+v", res)
	}
	if len(stub.calls) != 0 {
		t.Fatal("stub called on empty input")
	}
}
