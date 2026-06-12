package turn

import (
	"context"
	"sync"
	"testing"
	"time"
)

func sampleCtx() *TurnContext {
	return NewTurnContext(
		"turn-1",
		"sess-1",
		"reality-1",
		"user-1",
		time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC),
	)
}

func TestTurnContextDefaultsToPending(t *testing.T) {
	c := sampleCtx()
	if c.State() != StatePending {
		t.Fatalf("state=%q", c.State())
	}
	if c.EnvelopeVersion != TurnContextVersion {
		t.Fatalf("envelope_version=%d", c.EnvelopeVersion)
	}
}

func TestTurnContextAdvanceHappyPath(t *testing.T) {
	c := sampleCtx()
	transitions := []TurnState{
		StateValidating,
		StateRouting,
		StateExecuting,
		StateStreaming,
		StateCompleted,
	}
	for _, to := range transitions {
		if err := c.Advance(to); err != nil {
			t.Fatalf("advance %q: %v", to, err)
		}
	}
	if c.State() != StateCompleted {
		t.Fatalf("final state=%q", c.State())
	}
}

func TestTurnContextRejectsInvalidTransition(t *testing.T) {
	c := sampleCtx()
	if err := c.Advance(StateCompleted); err == nil {
		t.Fatal("pending->completed must error")
	}
}

func TestTurnContextConcurrentAdvanceSerializes(t *testing.T) {
	c := sampleCtx()
	// From Pending, two goroutines race to Validating vs Cancelled (terminal).
	// One will win and lock the state; the other's transition either succeeds
	// from the new state (validating->cancelled is legal) or fails because the
	// winner already advanced past it. We assert no data race AND that the
	// final state is reachable by SOME valid path.
	var wg sync.WaitGroup
	results := make(chan error, 2)
	wg.Add(2)
	go func() {
		defer wg.Done()
		results <- c.Advance(StateValidating)
	}()
	go func() {
		defer wg.Done()
		results <- c.Advance(StateCancelled)
	}()
	wg.Wait()
	close(results)
	// Final state must be one of Validating or Cancelled (no race corruption).
	final := c.State()
	if final != StateValidating && final != StateCancelled {
		t.Fatalf("unexpected final state %q (race?)", final)
	}
	// At least one Advance returned no error (the winner).
	atLeastOneOk := false
	for err := range results {
		if err == nil {
			atLeastOneOk = true
		}
	}
	if !atLeastOneOk {
		t.Fatal("expected at least one successful advance")
	}
}

func TestTurnContextWithFromContext(t *testing.T) {
	c := sampleCtx()
	ctx := WithTurnContext(context.Background(), c)
	got := FromContext(ctx)
	if got != c {
		t.Fatal("FromContext returned different pointer")
	}
	if FromContext(context.Background()) != nil {
		t.Fatal("empty context should return nil")
	}
}

func TestSetForceState(t *testing.T) {
	c := sampleCtx()
	if err := c.SetForceState(StateExecuting); err != nil {
		t.Fatal(err)
	}
	if c.State() != StateExecuting {
		t.Fatalf("state=%q", c.State())
	}
	if err := c.SetForceState(TurnState("bogus")); err == nil {
		t.Fatal("bogus must error")
	}
}
