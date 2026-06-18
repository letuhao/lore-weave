package closure

import (
	"context"
	"errors"
	"testing"
	"time"
)

// fakeTransitioner records every transition and can fail a specific one.
type fakeTransitioner struct {
	calls  []string // "from->to"
	failOn string
}

func (f *fakeTransitioner) Transition(_ context.Context, _, from, to string) error {
	f.calls = append(f.calls, from+"->"+to)
	if f.failOn == from+"->"+to {
		return errors.New("forced failure")
	}
	return nil
}

// fakeOutbox returns a scripted sequence of unpublished counts (last value
// repeats once exhausted).
type fakeOutbox struct {
	seq []int64
	i   int
}

func (f *fakeOutbox) UnpublishedCount(context.Context, string) (int64, error) {
	v := f.seq[f.i]
	if f.i < len(f.seq)-1 {
		f.i++
	}
	return v, nil
}

func noSleep(context.Context, time.Duration) {}

func orch(tr Transitioner, ob OutboxReader) *Orchestrator {
	return &Orchestrator{
		Tr: tr, Outbox: ob,
		PollInterval: time.Millisecond, DrainTimeout: 10 * time.Millisecond, // maxPolls = 10
		Sleep: noSleep,
	}
}

func TestDrainsThenFreezes(t *testing.T) {
	tr := &fakeTransitioner{}
	// backlog 3 → 2 → 0: freezes on the 3rd poll.
	res, err := orch(tr, &fakeOutbox{seq: []int64{3, 2, 0}}).Close(context.Background(), "r1")
	if err != nil {
		t.Fatalf("Close: %v", err)
	}
	if res.FinalState != "frozen" || res.Aborted {
		t.Fatalf("want frozen/not-aborted, got %+v", res)
	}
	want := []string{"active->pending_close", "pending_close->frozen"}
	if !equal(tr.calls, want) {
		t.Fatalf("transitions = %v, want %v", tr.calls, want)
	}
}

// The headline W1.3 invariant: it must NOT freeze while the outbox is non-empty.
func TestNeverFreezesWithUndrainedOutbox(t *testing.T) {
	tr := &fakeTransitioner{}
	// backlog never drains (always 5) → must abort, never reach ->frozen.
	res, err := orch(tr, &fakeOutbox{seq: []int64{5}}).Close(context.Background(), "r1")
	if err != nil {
		t.Fatalf("Close: %v", err)
	}
	if !res.Aborted || res.AbortReason != "drain_timeout" || res.FinalState != "active" {
		t.Fatalf("want aborted/drain_timeout/active, got %+v", res)
	}
	for _, c := range tr.calls {
		if c == "pending_close->frozen" {
			t.Fatal("froze a reality with an undrained outbox — the drain gate failed")
		}
	}
	want := []string{"active->pending_close", "pending_close->active"}
	if !equal(tr.calls, want) {
		t.Fatalf("transitions = %v, want %v (enter then abort-restore)", tr.calls, want)
	}
}

func TestEnterPendingCloseFailureSurfaces(t *testing.T) {
	tr := &fakeTransitioner{failOn: "active->pending_close"}
	_, err := orch(tr, &fakeOutbox{seq: []int64{0}}).Close(context.Background(), "r1")
	if err == nil {
		t.Fatal("expected an error when entering pending_close fails")
	}
}

func equal(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
