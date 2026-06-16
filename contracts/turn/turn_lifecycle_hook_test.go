package turn

import (
	"context"
	"sync"
	"testing"
	"time"
)

func TestTrackerStartEnd(t *testing.T) {
	tr := NewTurnInFlightTracker()
	if tr.InFlight() != 0 {
		t.Fatal("initial inflight != 0")
	}
	done := tr.Start()
	if tr.InFlight() != 1 {
		t.Fatalf("inflight=%d", tr.InFlight())
	}
	done()
	if tr.InFlight() != 0 {
		t.Fatalf("inflight after End=%d", tr.InFlight())
	}
}

func TestTrackerWaitForDrainAllowsRunningTurnsToFinish(t *testing.T) {
	tr := NewTurnInFlightTracker()
	endTurn := tr.Start()
	go func() {
		time.Sleep(40 * time.Millisecond)
		endTurn()
	}()
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	if err := tr.WaitForDrain(ctx); err != nil {
		t.Fatalf("drain: %v", err)
	}
}

func TestTrackerWaitForDrainHonorsContextDeadline(t *testing.T) {
	tr := NewTurnInFlightTracker()
	_ = tr.Start() // never ends
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	err := tr.WaitForDrain(ctx)
	if err == nil {
		t.Fatal("expected timeout error")
	}
}

func TestTrackerHandlesConcurrentStartEnd(t *testing.T) {
	tr := NewTurnInFlightTracker()
	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			done := tr.Start()
			time.Sleep(time.Millisecond)
			done()
		}()
	}
	wg.Wait()
	if tr.InFlight() != 0 {
		t.Fatalf("inflight=%d", tr.InFlight())
	}
}

func TestTrackerOverflowPanics(t *testing.T) {
	defer func() {
		if r := recover(); r == nil {
			t.Fatal("expected panic")
		}
	}()
	tr := NewTurnInFlightTracker()
	tr.End()
}
