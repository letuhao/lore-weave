package canary

import (
	"context"
	"errors"
	"sort"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// fakeDispatcher records every Run call.
type fakeDispatcher struct {
	mu     sync.Mutex
	runs   [][]Job
	result func(j Job) Result // per-job result strategy
}

func (f *fakeDispatcher) Run(_ context.Context, jobs []Job) []Result {
	f.mu.Lock()
	defer f.mu.Unlock()
	// Take a defensive copy so subsequent mutations by the orchestrator
	// can't change what we recorded.
	cp := make([]Job, len(jobs))
	copy(cp, jobs)
	f.runs = append(f.runs, cp)
	out := make([]Result, len(jobs))
	for i, j := range jobs {
		if f.result != nil {
			out[i] = f.result(j)
		} else {
			out[i] = Result{Job: j, Succeeded: true, Attempts: 1}
		}
	}
	return out
}

type fakeAborter struct {
	mu      sync.Mutex
	aborted []string // reality_ids
	reasons []string
}

func (a *fakeAborter) RecordAbort(_ context.Context, r, _, _, reason string) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.aborted = append(a.aborted, r)
	a.reasons = append(a.reasons, reason)
	return nil
}

func realities(n int) []string {
	out := make([]string, n)
	for i := 0; i < n; i++ {
		out[i] = "reality-" + string('a'+rune(i))
	}
	return out
}

// TestCanary_AppliesToExactlyOneRealityFirst — load-bearing assertion that
// breaking migrations route to exactly 1 reality on the first dispatcher call.
func TestCanary_AppliesToExactlyOneRealityFirst(t *testing.T) {
	disp := &fakeDispatcher{}
	abort := &fakeAborter{}
	gate := NewVerificationGate()
	// Trigger Pass after a small delay so wait() actually blocks.
	go func() { time.Sleep(5 * time.Millisecond); gate.Pass() }()

	o, err := New(&Config{Dispatcher: disp, Aborter: abort, VerificationGate: gate, VerificationDelay: time.Second})
	if err != nil {
		t.Fatal(err)
	}
	all := realities(5)
	outcome, err := o.Run(context.Background(), all, "0002_breaking")
	if err != nil {
		t.Fatal(err)
	}
	if len(disp.runs) != 2 {
		t.Fatalf("expected 2 dispatcher calls (canary + fanout), got %d", len(disp.runs))
	}
	if len(disp.runs[0]) != 1 {
		t.Errorf("first call must apply to EXACTLY 1 reality (canary); got %d", len(disp.runs[0]))
	}
	if got := disp.runs[0][0].RealityID; got != "reality-a" {
		t.Errorf("expected canary=reality-a (lexicographic first), got %s", got)
	}
	if !outcome.Verified {
		t.Error("expected outcome.Verified=true after Pass()")
	}
	if got := len(disp.runs[1]); got != 4 {
		t.Errorf("expected fanout=4 realities, got %d", got)
	}
}

// TestCanary_HardWaitNotAsync — the verification gate MUST block until
// Pass/Fail/timeout. We assert by checking that Run() does NOT call the
// fanout dispatcher before Pass() is invoked.
func TestCanary_HardWaitNotAsync(t *testing.T) {
	var fanoutSeen int64
	disp := &fakeDispatcher{result: func(j Job) Result {
		// Track when fanout calls land vs canary call.
		if len(j.RunID) >= 6 && j.RunID[:6] == "fanout" {
			atomic.AddInt64(&fanoutSeen, 1)
		}
		return Result{Job: j, Succeeded: true, Attempts: 1}
	}}
	abort := &fakeAborter{}
	gate := NewVerificationGate()

	o, _ := New(&Config{Dispatcher: disp, Aborter: abort, VerificationGate: gate, VerificationDelay: 5 * time.Second})
	all := realities(3)

	// Run in a goroutine; this MUST block at the gate.
	done := make(chan struct{})
	go func() {
		_, _ = o.Run(context.Background(), all, "0002_breaking")
		close(done)
	}()

	// Give the goroutine a moment to dispatch the canary then block.
	time.Sleep(20 * time.Millisecond)
	if atomic.LoadInt64(&fanoutSeen) != 0 {
		t.Fatal("fanout called BEFORE verification gate (async fire-and-forget bug)")
	}
	select {
	case <-done:
		t.Fatal("Run() returned without waiting for Pass/Fail")
	default:
		// expected — still blocked
	}
	gate.Pass()
	<-done
	if atomic.LoadInt64(&fanoutSeen) == 0 {
		t.Error("fanout never ran after Pass()")
	}
}

func TestCanary_CanaryFailureAbortsFanout(t *testing.T) {
	disp := &fakeDispatcher{result: func(j Job) Result {
		// Canary fails (it's the only run for now).
		return Result{Job: j, Succeeded: false, Attempts: 3, FinalError: errors.New("apply failed")}
	}}
	abort := &fakeAborter{}
	o, _ := New(&Config{Dispatcher: disp, Aborter: abort, VerificationGate: NewVerificationGate(), VerificationDelay: 100 * time.Millisecond})
	all := realities(4)

	outcome, err := o.Run(context.Background(), all, "0002_breaking")
	if err != nil {
		t.Fatal(err)
	}
	if !outcome.Aborted {
		t.Fatal("expected outcome.Aborted on canary failure")
	}
	if outcome.AbortReason != "canary_apply_failed" {
		t.Errorf("expected reason canary_apply_failed, got %q", outcome.AbortReason)
	}
	if len(disp.runs) != 1 {
		t.Errorf("expected exactly 1 dispatcher call (canary only); got %d", len(disp.runs))
	}
	abort.mu.Lock()
	defer abort.mu.Unlock()
	if len(abort.aborted) != 3 {
		t.Errorf("expected 3 abort audit rows (remaining realities); got %d", len(abort.aborted))
	}
	sort.Strings(abort.aborted)
	want := []string{"reality-b", "reality-c", "reality-d"}
	for i := range want {
		if abort.aborted[i] != want[i] {
			t.Errorf("aborted[%d] = %q, want %q", i, abort.aborted[i], want[i])
		}
	}
}

func TestCanary_VerificationFailureAbortsFanout(t *testing.T) {
	disp := &fakeDispatcher{}
	abort := &fakeAborter{}
	gate := NewVerificationGate()
	go func() { time.Sleep(5 * time.Millisecond); gate.Fail("post-apply-tests-red") }()

	o, _ := New(&Config{Dispatcher: disp, Aborter: abort, VerificationGate: gate, VerificationDelay: time.Second})
	outcome, err := o.Run(context.Background(), realities(3), "0002_breaking")
	if err != nil {
		t.Fatal(err)
	}
	if !outcome.Aborted {
		t.Fatal("expected aborted on verification failure")
	}
	if outcome.AbortReason != "canary_verification_post-apply-tests-red" {
		t.Errorf("got reason %q", outcome.AbortReason)
	}
	if outcome.Verified {
		t.Error("Verified must be false on Fail")
	}
}

func TestCanary_VerificationTimeoutAborts(t *testing.T) {
	disp := &fakeDispatcher{}
	abort := &fakeAborter{}
	gate := NewVerificationGate() // never Pass/Fail-ed
	o, _ := New(&Config{Dispatcher: disp, Aborter: abort, VerificationGate: gate, VerificationDelay: 5 * time.Millisecond})
	outcome, _ := o.Run(context.Background(), realities(3), "0002_breaking")
	if !outcome.Aborted {
		t.Fatal("expected aborted on timeout")
	}
	if outcome.AbortReason != "canary_verification_verification_timeout" {
		t.Errorf("got reason %q", outcome.AbortReason)
	}
}

func TestLexicographicSelector(t *testing.T) {
	s := LexicographicSelector{}
	got, err := s.Pick([]string{"reality-z", "reality-a", "reality-m"})
	if err != nil {
		t.Fatal(err)
	}
	if got != "reality-a" {
		t.Errorf("got %q, want reality-a", got)
	}
}

func TestConfigValidate(t *testing.T) {
	if _, err := New(nil); err == nil {
		t.Error("nil cfg must error")
	}
	if _, err := New(&Config{Aborter: &fakeAborter{}}); err == nil {
		t.Error("missing Dispatcher must error")
	}
	if _, err := New(&Config{Dispatcher: &fakeDispatcher{}}); err == nil {
		t.Error("missing Aborter must error")
	}
}
